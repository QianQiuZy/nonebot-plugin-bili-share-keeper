from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

from pydantic import BaseModel, validator


def _normalize_target_groups(value: Any) -> list[int]:
    if isinstance(value, int):
        return [value]

    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []

        try:
            loaded = json.loads(stripped)
        except json.JSONDecodeError:
            separators = [",", "\n", " "]
            items = [stripped]
            for separator in separators:
                if separator in stripped:
                    items = [item for item in stripped.replace("\n", ",").replace(" ", ",").split(",") if item]
                    break
            return [int(item) for item in items]

        return _normalize_target_groups(loaded)

    if isinstance(value, Iterable):
        groups: list[int] = []
        for item in value:
            groups.extend(_normalize_target_groups(item))
        return groups

    raise TypeError("bilibili_share_keeper_target_group must be an int or a list of ints")


class Config(BaseModel):
    bilibili_share_keeper_redis_url: str = "redis://localhost:6379/0"
    bilibili_share_keeper_target_group: list[int] = [202781936]
    bilibili_share_keeper_key_prefix: str = "nb2:bili_share_keeper"
    bilibili_share_keeper_http_timeout: float = 10.0

    @validator("bilibili_share_keeper_target_group", pre=True)
    def validate_target_groups(cls, value: Any) -> list[int]:
        return _normalize_target_groups(value)
