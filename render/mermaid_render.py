"""Mermaid 图表渲染（mermaid.ink 外部服务）。

本地渲染 mermaid 需要 JS 与 DOM，代价是往运行时塞一个浏览器；这里改走
外部服务。它是免费公共资源，并发会被直接拒绝（实测 17 个请求同时打过去
15 个 503），所以进程内只留一条通道，一次一个请求。4xx 是源码本身的问题
（语法错、URL 超长），重试无意义；5xx 是服务端抖动（实测约 15%），重试
一次即可恢复。仍失败则抛给上层，由上层改发 .md 文件交给客户端渲染。
"""
from __future__ import annotations

import asyncio
import base64
from typing import Any

import httpx

# bgColor 必须给：默认输出 RGBA 透明底，QQ 客户端会把透明渲染成黑或白，
# 和插件其他图片的 #1E1E1E 底色对不上。
_ENDPOINT = "https://mermaid.ink/img/{payload}?type=png&theme=dark&bgColor=1E1E1E"
# 单张预算：实测轻图 p50 1.2s，重图冷启 6.3s，留 1.6 倍余量。
_TIMEOUT = 10.0
_RETRY_DELAY = 1.0
_ATTEMPTS = 2

_PNG_MAGIC = b"\x89PNG"

_client = httpx.AsyncClient(timeout=_TIMEOUT)

# 进程级单通道：记录所属事件循环，插件重载或测试换 loop 时重建，
# 避免锁绑定到已关闭的循环。
_channel: tuple[asyncio.AbstractEventLoop, asyncio.Lock] | None = None


def _channel_lock() -> asyncio.Lock:
    """取当前事件循环下的单通道锁。

    Returns:
        当前事件循环独占的锁，后到的渲染任务在它后面排队。
    """
    global _channel
    loop = asyncio.get_running_loop()
    if _channel is None or _channel[0] is not loop:
        _channel = (loop, asyncio.Lock())
    return _channel[1]


def build_url(code: str) -> str:
    """把 mermaid 源码编码为 mermaid.ink 的图片 URL。

    Args:
        code: mermaid 源码。

    Returns:
        可直接 GET 的图片 URL。
    """
    payload = base64.urlsafe_b64encode(code.encode("utf-8")).decode("ascii")
    return _ENDPOINT.format(payload=payload)


async def render_mermaid(seg: Any) -> bytes:
    """把 mermaid 代码块渲染为 PNG。

    Args:
        seg: MermaidBlock 实例，含 code 属性。

    Returns:
        PNG 图片字节。

    Raises:
        RuntimeError: 服务端返回 4xx、响应不是 PNG，或 5xx 重试后仍失败。
        httpx.HTTPError: 网络超时或连接失败，重试后仍失败。
    """
    url = build_url(getattr(seg, "code", ""))
    async with _channel_lock():
        error: Exception = RuntimeError("mermaid.ink 渲染失败")
        for attempt in range(_ATTEMPTS):
            try:
                response = await _client.get(url)
            except httpx.HTTPError as exc:
                error = exc
            else:
                if response.status_code == 200 and response.content.startswith(_PNG_MAGIC):
                    return response.content
                error = RuntimeError(f"mermaid.ink 返回 HTTP {response.status_code}")
                if response.status_code < 500:
                    raise error
            if attempt + 1 < _ATTEMPTS:
                await asyncio.sleep(_RETRY_DELAY)
        raise error
