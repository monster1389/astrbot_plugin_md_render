"""临时文件清理。

周期性扫描 temp/ 目录，按文件实际写盘时间与配置的存活时长删除过期渲染文件。
文件由 deliver 在发送完成后删除；此处时间窗只兜底尾条与异常中断残留的文件。
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime

from render.utils import is_temp_file

logger = logging.getLogger(__name__)

# 存活 0 分钟时按一个清扫周期（60 秒）兜底，避免误删尚未发送的渲染产物
_MIN_TTL_MINUTES = 1.0


def _scan_and_clean(
    temp_dir: str, ttl_minutes: int, _now: datetime | None = None
) -> None:
    """单次扫描并清理过期文件。

    Args:
        temp_dir: 临时文件目录路径。
        ttl_minutes: 存活时长（分钟）。0=尽快删除（最短保留 1 分钟），-1=不删。
        _now: 当前时间（仅测试用，默认取系统时间）。
    """
    if ttl_minutes < 0:
        return

    try:
        filenames = os.listdir(temp_dir)
    except OSError:
        return

    now = _now if _now is not None else datetime.now()
    effective_ttl = _MIN_TTL_MINUTES if ttl_minutes == 0 else float(ttl_minutes)
    for name in filenames:
        if not is_temp_file(name):
            continue
        path = os.path.join(temp_dir, name)
        try:
            mtime = datetime.fromtimestamp(os.path.getmtime(path))
        except OSError:
            continue
        age_minutes = (now - mtime).total_seconds() / 60.0
        if age_minutes >= effective_ttl:
            try:
                os.remove(path)
                logger.debug("已清理过期临时文件: %s", name)
            except OSError:
                pass


async def _cleanup_loop(data_dir: str, ttl_minutes: int) -> None:
    """后台清理循环，每 60 秒扫描一次。

    Args:
        data_dir: 插件数据目录路径。
        ttl_minutes: 存活时长（分钟）。
    """
    temp_dir = os.path.join(data_dir, "temp")
    while True:
        try:
            _scan_and_clean(temp_dir, ttl_minutes)
        except Exception:
            logger.exception("临时文件清理异常")
        await asyncio.sleep(60)


_cleanup_task: asyncio.Task | None = None


def start(data_dir: str, ttl_minutes: int) -> None:
    """启动后台清理任务。

    Args:
        data_dir: 插件数据目录路径。
        ttl_minutes: 存活时长（分钟）。0=尽快删除，-1=不启动。
    """
    global _cleanup_task
    if ttl_minutes < 0:
        return
    if _cleanup_task is not None:
        return
    _cleanup_task = asyncio.create_task(_cleanup_loop(data_dir, ttl_minutes))


async def stop() -> None:
    """停止后台清理任务。"""
    global _cleanup_task
    if _cleanup_task is None:
        return
    _cleanup_task.cancel()
    try:
        await _cleanup_task
    except asyncio.CancelledError:
        pass
    _cleanup_task = None
