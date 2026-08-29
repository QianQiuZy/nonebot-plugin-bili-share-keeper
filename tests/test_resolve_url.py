from __future__ import annotations

import anyio
import httpx
import nonebot

nonebot.init()
import nonebot_plugin_bili_share_keeper as plugin


def test_resolve_url_reads_b23_redirect_without_requesting_bilibili(
    monkeypatch,
) -> None:
    short_url = "https://b23.tv/Besm3Fg"
    resolved_url = "https://www.bilibili.com/video/BV1cmgE6JEtr"
    requests: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append((request.method, request.url.host or ""))
        if request.url.host == "b23.tv":
            return httpx.Response(
                302,
                headers={"location": resolved_url},
                request=request,
            )
        return httpx.Response(412, request=request)

    transport = httpx.MockTransport(handler)
    original_client = httpx.AsyncClient

    def client_factory(*args: object, **kwargs: object) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        return original_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", client_factory)

    result = anyio.run(plugin._resolve_url, short_url)

    assert result == resolved_url
    assert requests == [("HEAD", "b23.tv")]
