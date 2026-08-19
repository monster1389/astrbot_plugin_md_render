"""送达模块。

按序发送除末条外的所有消息，末条留作 result.chain 原地展示。
"""
from __future__ import annotations

import asyncio
import os
import random
from collections.abc import Awaitable, Callable

from astrbot.api import logger

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


def _summarize(comps: list) -> str:
    """将一条消息的组件压缩为日志摘要。

    Args:
        comps: 消息组件列表。

    Returns:
        摘要文本，如 `文本「…」 图片 code.png 文件 x.md`。
    """
    parts: list[str] = []
    for c in comps:
        text = getattr(c, "text", None)
        if text is not None:
            stripped = text.strip()
            if not stripped:
                parts.append("空")
            elif len(stripped) <= 24:
                parts.append(f"文本「{stripped}」")
            else:
                parts.append(f"文本「{stripped[:24]}…」")
        elif getattr(c, "name", None):
            parts.append(f"文件 {c.name}")
        else:
            fname = getattr(c, "file", None)
            parts.append(f"图片 {os.path.basename(fname)}" if fname else "图片")
    return " ".join(parts)


async def deliver(
    send: Callable[[list], Awaitable[None]],
    messages: list[list],
    cfg: RenderConfig,
) -> list:
    """按序发送除末条外的所有消息，末条留作返回。

    跳过纯空白消息；send_delay 开启时在两条消息间随机延时，
    媒体消息间隔 1~3 秒，纯文本间隔 0.3~1 秒。每条发送后打一条 DEBUG
    摘要日志，延时是否生效可从相邻日志行的时间戳间隔观察。

    Args:
        send: 发送一条消息的异步回调。
        messages: build_chain 产出的消息列表。
        cfg: 渲染配置。

    Returns:
        末条消息组件列表，作为 result.chain 留尾。
    """
    n = len(messages)
    for i, message in enumerate(messages[:-1], 1):
        if not _has_content(message):
            continue
        await send(message)
        logger.debug("第 %d/%d 条已发送 %s", i, n, _summarize(message))
        if cfg.send_delay:
            await asyncio.sleep(random.uniform(*_DELAY_RANGES[has_media(message)]))
    return messages[-1]
