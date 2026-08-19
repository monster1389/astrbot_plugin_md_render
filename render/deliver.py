"""送达模块。

按序发送除末条外的所有消息，末条留作 result.chain 原地展示。

每条发送完成后立即删除其临时文件（文件在发送时已被读走）；
末条交棒前刷新其临时文件时间戳，保证清理线程不误删尚未发出的文件。
"""
from __future__ import annotations

import asyncio
import os
import random
from collections.abc import Awaitable, Callable

from astrbot.api import logger

from render.chain import has_media
from render.utils import SegmentConfig, is_temp_file

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

    只匹配 code/table/expr_时间戳.{png,md} 命名模式，避免误伤
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


def _delete_temp_files(comps: list) -> None:
    """删除消息中本插件生成的临时磁盘文件，已不存在则忽略。

    Args:
        comps: 消息组件列表。
    """
    for path in _temp_paths(comps):
        try:
            os.remove(path)
        except OSError:
            pass


def _touch_temp_files(comps: list) -> None:
    """刷新消息中本插件生成的临时磁盘文件的写盘时间，延长存活窗口。

    Args:
        comps: 消息组件列表。
    """
    for path in _temp_paths(comps):
        try:
            os.utime(path, None)
        except OSError:
            pass


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
    cfg: SegmentConfig,
) -> list:
    """按序发送除末条外的所有消息，末条留作返回。

    跳过纯空白消息；send_delay 开启时在两条消息间随机延时，
    媒体消息间隔 1~3 秒，纯文本间隔 0.3~1 秒。每条发送后打一条 DEBUG
    摘要日志，延时是否生效可从相邻日志行的时间戳间隔观察。

    Args:
        send: 发送一条消息的异步回调。
        messages: build_chain 产出的消息列表。
        cfg: 分段配置。

    Returns:
        末条消息组件列表，作为 result.chain 留尾。
    """
    n = len(messages)
    for i, message in enumerate(messages[:-1], 1):
        if not _has_content(message):
            continue
        await send(message)
        logger.debug("第 %d/%d 条已发送 %s", i, n, _summarize(message))
        _delete_temp_files(message)
        if cfg.send_delay:
            await asyncio.sleep(random.uniform(*_DELAY_RANGES[has_media(message)]))
    tail = messages[-1]
    _touch_temp_files(tail)
    return tail
