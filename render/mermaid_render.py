"""Mermaid 图表渲染（mermaid.ink 外部服务）。

本地渲染 mermaid 需要 JS 与 DOM，代价是往运行时塞一个浏览器；这里改走
外部服务。服务端 5xx 或网络错误重试一次，仍失败则抛给上层回退源码。
"""
from __future__ import annotations

import base64
import time
from typing import Any

import httpx

# bgColor 必须给：默认输出 RGBA 透明底，QQ 客户端会把透明渲染成黑或白，
# 和插件其他图片的 #1E1E1E 底色对不上。
_ENDPOINT = "https://mermaid.ink/img/{payload}?type=png&theme=dark&bgColor=1E1E1E"
_TIMEOUT = 5.0
_RETRY_DELAY = 0.5

_PNG_MAGIC = b"\x89PNG"

_client = httpx.Client(timeout=_TIMEOUT)


def build_url(code: str) -> str:
    """把 mermaid 源码编码为 mermaid.ink 的图片 URL。

    Args:
        code: mermaid 源码。

    Returns:
        可直接 GET 的图片 URL。
    """
    payload = base64.urlsafe_b64encode(code.encode("utf-8")).decode("ascii")
    return _ENDPOINT.format(payload=payload)


def render_mermaid(seg: Any) -> bytes:
    """把 mermaid 代码块渲染为 PNG。

    Args:
        seg: MermaidBlock 实例，含 code 属性。

    Returns:
        PNG 图片字节。

    Raises:
        RuntimeError: 服务端返回非 200 或响应不是 PNG。
        httpx.HTTPError: 网络超时或连接失败，重试一次后仍失败。
    """
    url = build_url(getattr(seg, "code", ""))
    error: Exception = RuntimeError("mermaid.ink 渲染失败")
    for attempt in range(2):
        try:
            response = _client.get(url)
        except httpx.HTTPError as exc:
            error = exc
        else:
            if response.status_code == 200 and response.content.startswith(_PNG_MAGIC):
                return response.content
            error = RuntimeError(f"mermaid.ink 返回 HTTP {response.status_code}")
            if response.status_code < 500:
                raise error
        if attempt == 0:
            time.sleep(_RETRY_DELAY)
    raise error
