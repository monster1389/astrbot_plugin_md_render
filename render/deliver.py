"""送达模块。

按序消费流水线：除末条外每条就绪即发，末条留作 result.chain 原地展示。
只认产物（render.artifacts），不认识 AstrBot 组件，发送经回调注入。

每条发送完成后立即删除其临时文件（文件在发送时已被读走）；
末条交棒前刷新其临时文件时间戳，保证清理线程不误删尚未发出的文件。
"""
from __future__ import annotations

import asyncio
import os
import random
import time
from collections.abc import AsyncIterable, Awaitable, Callable

from astrbot.api import logger
from render.artifacts import (
    Artifact,
    Message,
    Picture,
    Text,
    has_media,
    temp_paths,
)
from render.config import SegmentConfig
from render.tempstore import delete, touch

# 发送延时范围（秒）：媒体消息 1~3s 防风控，纯文本 0.3~1s
_DELAY_RANGES: dict[bool, tuple[float, float]] = {
    True: (1.0, 3.0),
    False: (0.3, 1.0),
}


def _has_content(artifacts: list[Artifact]) -> bool:
    """判断产物列表是否含实质内容（有媒体，或文本非空白）。

    Args:
        artifacts: 产物列表。

    Returns:
        True 表示含实质内容。
    """
    if has_media(artifacts):
        return True
    return any(isinstance(a, Text) and a.text.strip() for a in artifacts)


def _summarize(artifacts: list[Artifact]) -> str:
    """将一条消息的产物压缩为日志摘要。

    Args:
        artifacts: 产物列表。

    Returns:
        摘要文本，如 `文本「…」 图片 code.png 文件 x.md`。
    """
    parts: list[str] = []
    for artifact in artifacts:
        if isinstance(artifact, Text):
            stripped = artifact.text.strip()
            if not stripped:
                parts.append("空")
            elif len(stripped) <= 24:
                parts.append(f"文本「{stripped}」")
            else:
                parts.append(f"文本「{stripped[:24]}…」")
        elif isinstance(artifact, Picture):
            parts.append(f"图片 {os.path.basename(artifact.path)}" if artifact.path else "图片")
        else:
            parts.append(f"文件 {artifact.name}")
    return " ".join(parts)


async def deliver(
    send: Callable[[list[Artifact]], Awaitable[None]],
    pipeline: AsyncIterable[Message],
    cfg: SegmentConfig,
) -> list[Artifact]:
    """按序消费流水线，发送除末条外的所有消息，末条留作返回。

    就绪即发，不等后续消息（末条由 is_tail 标记，无需向前多取一条）。
    跳过纯空白消息；send_delay 开启时，两条消息的间隔按已消耗的时间补足——
    上一条发出后到本条渲染完成之间的等待已计入间隔，媒体 1~3 秒、纯文本 0.3~1 秒，
    不足才补，不叠加。每条发送后打一条 DEBUG 摘要日志。

    Args:
        send: 发送一条消息产物的异步回调。
        pipeline: 流水线，逐条产出 Message。
        cfg: 分段配置。

    Returns:
        末条消息的产物列表，作为 result.chain 留尾。
    """
    tail: list[Artifact] = []
    sent = 0
    last_sent: float | None = None
    async for message in pipeline:
        if message.is_tail:
            tail = message.artifacts
            continue
        if not _has_content(message.artifacts):
            continue
        if cfg.send_delay and last_sent is not None:
            gap = random.uniform(*_DELAY_RANGES[has_media(message.artifacts)])
            remaining = gap - (time.monotonic() - last_sent)
            if remaining > 0:
                await asyncio.sleep(remaining)
        await send(message.artifacts)
        last_sent = time.monotonic()
        sent += 1
        logger.debug("第 %d 条已发送 %s", sent, _summarize(message.artifacts))
        delete(temp_paths(message.artifacts))
    touch(temp_paths(tail))
    return tail
