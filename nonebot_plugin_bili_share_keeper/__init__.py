from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Iterable
from datetime import datetime
from typing import TYPE_CHECKING, Any

import httpx
from nonebot import get_driver, logger, on_message
from nonebot.plugin import PluginMetadata

try:
    from redis.asyncio import Redis as RedisClient
    from redis.exceptions import RedisError, WatchError
except ImportError:  # pragma: no cover
    RedisClient = None
    RedisError = Exception
    WatchError = Exception

if TYPE_CHECKING:  # pragma: no cover
    from redis.asyncio import Redis as RedisType
else:
    RedisType = Any

try:
    from nonebot import get_plugin_config
except ImportError:  # pragma: no cover
    get_plugin_config = None

from nonebot.adapters.onebot.v11 import (
    Bot,
    GroupMessageEvent,
    Message,
    MessageEvent,
    MessageSegment,
)

from .config import Config

__plugin_meta__ = PluginMetadata(
    name="B站重复分享记录",
    description="记录指定群内的 B 站视频分享，并在重复分享时进行引用提醒。",
    usage="配置目标群后加载插件即可；可选接入 Redis，不接入时使用内存记录。",
    config=Config,
)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
)
B23_URL_RE = re.compile(r"(?:https?://)?b23\.tv/[0-9A-Za-z]+(?:\?[^\s\"'\]]*)?")
BV_RE = re.compile(r"BV[0-9A-Za-z]{10}")

driver = get_driver()
share_matcher = on_message(priority=15, block=False)
_redis_client: RedisType | None = None
_memory_store: dict[str, dict[str, str]] = {}
_memory_store_lock = asyncio.Lock()
_memory_fallback_logged = False


def _load_config() -> Config:
    if get_plugin_config is not None:
        return get_plugin_config(Config)

    driver_config = get_driver().config
    if hasattr(driver_config, "model_dump"):
        raw_config = driver_config.model_dump()
    elif hasattr(driver_config, "dict"):
        raw_config = driver_config.dict()
    else:
        raw_config = dict(driver_config)

    if hasattr(Config, "model_validate"):
        return Config.model_validate(raw_config)
    return Config(**raw_config)


plugin_config = _load_config()


@driver.on_shutdown
async def _close_redis() -> None:
    global _redis_client
    if _redis_client is None:
        return

    try:
        await _redis_client.aclose()
    except AttributeError:  # pragma: no cover
        await _redis_client.close()
    finally:
        _redis_client = None


def _log_memory_fallback(reason: str) -> None:
    global _memory_fallback_logged
    if _memory_fallback_logged:
        return

    logger.warning(f"B站分享记录插件将使用内存存储：{reason}")
    _memory_fallback_logged = True


async def _get_redis() -> RedisType | None:
    global _redis_client
    redis_url = plugin_config.bilibili_share_keeper_redis_url.strip()
    if RedisClient is None:
        _log_memory_fallback("未安装 redis 依赖")
        return None
    if not redis_url:
        _log_memory_fallback("未配置 Redis 地址")
        return None
    if _redis_client is None:
        _redis_client = RedisClient.from_url(
            redis_url,
            decode_responses=True,
        )
    redis = _redis_client
    if redis is None:
        return None
    try:
        await redis.ping()
    except Exception as exc:
        _log_memory_fallback(f"Redis 不可用 ({exc!r})")
        await _close_redis()
        return None
    return redis


def _iter_strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
        return

    if isinstance(value, dict):
        for item in value.values():
            yield from _iter_strings(item)
        return

    if isinstance(value, list):
        for item in value:
            yield from _iter_strings(item)


def _extract_json_object(raw_text: str) -> dict[str, Any] | None:
    raw_text = raw_text.strip()
    if not raw_text:
        return None

    candidates = [raw_text]
    start = raw_text.find("{")
    end = raw_text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidates.append(raw_text[start : end + 1])

    for candidate in candidates:
        try:
            loaded = json.loads(candidate)
        except json.JSONDecodeError:
            continue

        if isinstance(loaded, dict):
            return loaded
    return None


def _collect_payloads(message: Message) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []

    for segment in message:
        if getattr(segment, "type", "") != "json":
            continue

        value = segment.data.get("data")
        if not isinstance(value, str):
            continue
        payload = _extract_json_object(value)
        if payload:
            payloads.append(payload)

    return payloads


def _normalize_url(url: str) -> str:
    normalized = url.strip().strip('"').strip("'")
    if normalized.startswith("//"):
        return "https:" + normalized
    if normalized.startswith("http://") or normalized.startswith("https://"):
        return normalized
    return "https://" + normalized.lstrip("/")


def _extract_b23_urls(payload: dict[str, Any]) -> list[str]:
    found: list[str] = []
    seen = set()

    for source in _iter_strings(payload):
        for match in B23_URL_RE.findall(source):
            normalized = _normalize_url(match)
            if normalized in seen:
                continue
            seen.add(normalized)
            found.append(normalized)

    return found


async def _resolve_url(short_url: str) -> str:
    timeout = plugin_config.bilibili_share_keeper_http_timeout
    async with httpx.AsyncClient(
        follow_redirects=False,
        timeout=timeout,
        headers={"User-Agent": USER_AGENT},
    ) as client:
        try:
            response = await client.head(short_url)
            if response.headers.get("location"):
                return str(response.url.join(response.headers["location"]))
            response.raise_for_status()
        except httpx.HTTPError:
            response = await client.get(short_url)
            if response.headers.get("location"):
                return str(response.url.join(response.headers["location"]))
            response.raise_for_status()

        location = response.headers.get("location")
        if location:
            return str(response.url.join(location))
        return str(response.url)


def _extract_bv(*texts: str) -> str | None:
    for text in texts:
        match = BV_RE.search(text)
        if match:
            return match.group(0)
    return None


def _display_name(event: GroupMessageEvent) -> str:
    sender = getattr(event, "sender", None)
    if sender is not None:
        card = getattr(sender, "card", "") or ""
        nickname = getattr(sender, "nickname", "") or ""
        if card:
            return str(card)
        if nickname:
            return str(nickname)
    return str(event.user_id)


def _redis_key(group_id: int, bv: str) -> str:
    prefix = plugin_config.bilibili_share_keeper_key_prefix.rstrip(":")
    return f"{prefix}:group:{group_id}:bv:{bv}"


def _build_first_record(
    *,
    message_id: int,
    user_id: int,
    user_name: str,
    bv: str,
    short_url: str,
    resolved_url: str,
) -> dict[str, str]:
    return {
        "bv": bv,
        "first_message_id": str(message_id),
        "first_user_id": str(user_id),
        "first_user_name": user_name,
        "first_share_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "first_short_url": short_url,
        "first_resolved_url": resolved_url,
        "count": "1",
    }


async def _register_share_in_memory(
    *,
    group_id: int,
    message_id: int,
    user_id: int,
    user_name: str,
    bv: str,
    short_url: str,
    resolved_url: str,
) -> tuple[bool, dict[str, str]]:
    key = _redis_key(group_id, bv)
    first_record = _build_first_record(
        message_id=message_id,
        user_id=user_id,
        user_name=user_name,
        bv=bv,
        short_url=short_url,
        resolved_url=resolved_url,
    )

    async with _memory_store_lock:
        existing = _memory_store.get(key)
        if not existing:
            _memory_store[key] = first_record.copy()
            return False, first_record

        count = int(existing.get("count", "1")) + 1
        existing["count"] = str(count)
        return True, existing.copy()


async def _register_share_in_redis(
    redis: RedisType,
    *,
    group_id: int,
    message_id: int,
    user_id: int,
    user_name: str,
    bv: str,
    short_url: str,
    resolved_url: str,
) -> tuple[bool, dict[str, str]]:
    key = _redis_key(group_id, bv)
    first_record = _build_first_record(
        message_id=message_id,
        user_id=user_id,
        user_name=user_name,
        bv=bv,
        short_url=short_url,
        resolved_url=resolved_url,
    )

    while True:
        try:
            async with redis.pipeline(transaction=True) as pipe:
                await pipe.watch(key)
                existing = await pipe.hgetall(key)
                if not existing:
                    pipe.multi()
                    pipe.hset(key, mapping=first_record)
                    await pipe.execute()
                    return False, first_record

                pipe.multi()
                pipe.hsetnx(key, "count", existing.get("count") or "1")
                pipe.hincrby(key, "count", 1)
                result = await pipe.execute()
                existing["count"] = str(result[-1])
                return True, existing
        except WatchError:
            continue


async def _register_share(
    *,
    group_id: int,
    message_id: int,
    user_id: int,
    user_name: str,
    bv: str,
    short_url: str,
    resolved_url: str,
) -> tuple[bool, dict[str, str]]:
    redis = await _get_redis()
    if redis is None:
        return await _register_share_in_memory(
            group_id=group_id,
            message_id=message_id,
            user_id=user_id,
            user_name=user_name,
            bv=bv,
            short_url=short_url,
            resolved_url=resolved_url,
        )

    try:
        return await _register_share_in_redis(
            redis,
            group_id=group_id,
            message_id=message_id,
            user_id=user_id,
            user_name=user_name,
            bv=bv,
            short_url=short_url,
            resolved_url=resolved_url,
        )
    except RedisError as exc:
        _log_memory_fallback(f"Redis 读写失败 ({exc!r})")
        await _close_redis()
        return await _register_share_in_memory(
            group_id=group_id,
            message_id=message_id,
            user_id=user_id,
            user_name=user_name,
            bv=bv,
            short_url=short_url,
            resolved_url=resolved_url,
        )


def _is_target_group(group_id: int) -> bool:
    return group_id in plugin_config.bilibili_share_keeper_target_group


@share_matcher.handle()
async def handle_group_bilibili_share(bot: Bot, event: MessageEvent) -> None:
    if not isinstance(event, GroupMessageEvent):
        return

    if not _is_target_group(event.group_id):
        return

    payloads = _collect_payloads(event.message)
    if not payloads:
        return

    for payload in payloads:
        short_urls = _extract_b23_urls(payload)
        if not short_urls:
            continue

        short_url = short_urls[0]
        try:
            resolved_url = await _resolve_url(short_url)
        except Exception as exc:
            logger.warning(f"解析 b23.tv 失败 {short_url}: {exc!r}")
            continue

        bv = _extract_bv(
            resolved_url,
            short_url,
            json.dumps(payload, ensure_ascii=False),
        )
        if not bv:
            logger.debug(f"未能从分享消息中提取 BV 号，short_url={short_url}")
            continue

        duplicate, record = await _register_share(
            group_id=event.group_id,
            message_id=event.message_id,
            user_id=event.user_id,
            user_name=_display_name(event),
            bv=bv,
            short_url=short_url,
            resolved_url=resolved_url,
        )
        if not duplicate:
            return

        first_time = record.get("first_share_time", "未知时间")
        first_user_name = record.get("first_user_name", "未知群友")
        count = record.get("count", "2")

        reply_message = Message()
        reply_message.append(MessageSegment.reply(event.message_id))
        reply_message += (
            f"此视频已于{first_time}被群友{first_user_name}分享过，"
            f"这是第{count}次被分享"
        )
        await bot.send(event, reply_message)
        return
