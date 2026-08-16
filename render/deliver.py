"""送达模块。

按序发送除末条外的所有消息，末条留作 result.chain 原地展示。
"""
from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable

from render.chain import has_media
from render.utils import RenderConfig

# 发送延时范围（秒）：媒体消息 1~3s 防风控，纯文本 0.3~1s
_DELAY_RANGES: dict[bool, tuple[float, float]] = {
    True: (1.0, 3.0),
    False: (0.3, 1.0),
}


def _has_content(comps: list) -> bool:
    """判断组件列表是否含实质内容（有非 Plain，或 Plain 文本非空白）。

    Args:
        comps: 消息组件列表。

    Returns:
        True 表示含实质内容。
    """
    if has_media(comps):
        return True
    return any((c.text or "").strip() for c in comps)


async def deliver(
    send: Callable[[list], Awaitable[None]],
    messages: list[list],
    cfg: RenderConfig,
) -> list:
    """按序发送除末条外的所有消息，末条留作返回。

    跳过纯空白消息；send_delay 开启时在两条消息间随机延时，
    媒体消息间隔 1~3 秒，纯文本间隔 0.3~1 秒。

    Args:
        send: 发送一条消息的异步回调。
        messages: build_chain 产出的消息列表。
        cfg: 渲染配置。

    Returns:
        末条消息组件列表，作为 result.chain 留尾。
    """
    for message in messages[:-1]:
        if not _has_content(message):
            continue
        await send(message)
        if cfg.send_delay:
            await asyncio.sleep(random.uniform(*_DELAY_RANGES[has_media(message)]))
    return messages[-1]
