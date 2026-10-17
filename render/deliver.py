"""送达模块。

按序消费流水线：除末条外每条就绪即发，末条留作 result.chain 原地展示。

每条发送完成后立即删除其临时文件（文件在发送时已被读走）；
末条交棒前刷新其临时文件时间戳，保证清理线程不误删尚未发出的文件。
"""
from __future__ import annotations

import asyncio
import os
import random
import time
from collections.abc import Awaitable, Callable

from astrbot.api import logger
from render.chain import Pipeline, has_media
from render.config import SegmentConfig
from render.tempstore import delete, is_temp_file, touch

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


def _temp_paths(comps: list) -> list[str]:
    """收集组件中本插件生成的临时磁盘文件路径（去重）。

    只匹配 code/table/expr/html/mermaid_时间戳.{png,md} 命名模式，避免误伤
    消息链中用户或 LLM 的原始图片等外部文件。

    Args:
        comps: 消息组件列表。

    Returns:
        匹配本插件临时文件命名模式的磁盘路径列表。
    """
    paths = []
    for c in comps:
        for attr in ("path", "file_"):
            p = getattr(c, attr, None)
            if isinstance(p, str) and p and is_temp_file(p):
                paths.append(p)
    return list(dict.fromkeys(paths))


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
    pipeline: Pipeline,
    cfg: SegmentConfig,
) -> list:
    """按序消费流水线，发送除末条外的所有消息，末条留作返回。

    就绪即发，不等后续消息（末条由 is_tail 标记，无需向前多取一条）。
    跳过纯空白消息；send_delay 开启时，两条消息的间隔按已消耗的时间补足——
    上一条发出后到本条渲染完成之间的等待已计入间隔，媒体 1~3 秒、纯文本 0.3~1 秒，
    不足才补，不叠加。每条发送后打一条 DEBUG 摘要日志。

    Args:
        send: 发送一条消息的异步回调。
        pipeline: plan_chain 产出的流水线。
        cfg: 分段配置。

    Returns:
        末条消息组件列表，作为 result.chain 留尾。
    """
    tail: list = []
    sent = 0
    last_sent: float | None = None
    async for message in pipeline:
        if message.is_tail:
            tail = message.chain
            continue
        if not _has_content(message.chain):
            continue
        if cfg.send_delay and last_sent is not None:
            gap = random.uniform(*_DELAY_RANGES[has_media(message.chain)])
            remaining = gap - (time.monotonic() - last_sent)
            if remaining > 0:
                await asyncio.sleep(remaining)
        await send(message.chain)
        last_sent = time.monotonic()
        sent += 1
        logger.debug("第 %d 条已发送 %s", sent, _summarize(message.chain))
        delete(_temp_paths(message.chain))
    touch(_temp_paths(tail))
    return tail
