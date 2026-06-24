"""临时文件清理。

周期性扫描 temp/ 目录，按配置的存活时长删除过期渲染文件。
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from datetime import datetime

logger = logging.getLogger(__name__)

_FILENAME_RE = re.compile(
    r"^(code|table|expr)_(\d{8})_(\d{6})\.(png|txt)$"
)


def _parse_file_ts(filename: str) -> datetime | None:
    """从渲染产物文件名解析时间戳。

    Args:
        filename: 文件名，如 table_20260624_114940.png。

    Returns:
        解析出的 datetime，格式不符返回 None。
    """
    m = _FILENAME_RE.match(filename)
    if not m:
        return None
    date_part = m.group(2)
    time_part = m.group(3)
    try:
        return datetime.strptime(f"{date_part}_{time_part}", "%Y%m%d_%H%M%S")
    except ValueError:
        return None


def _scan_and_clean(
    temp_dir: str, ttl_minutes: int, _now: datetime | None = None
) -> None:
    """单次扫描并清理过期文件。

    Args:
        temp_dir: 临时文件目录路径。
        ttl_minutes: 存活时长（分钟）。0=立即删，-1=不删。
        _now: 当前时间（仅测试用，默认取系统时间）。
    """
    if ttl_minutes < 0:
        return

    try:
        filenames = os.listdir(temp_dir)
    except OSError:
        return

    now = _now if _now is not None else datetime.now()
    for name in filenames:
        ts = _parse_file_ts(name)
        if ts is None:
            continue

        age_minutes = (now - ts).total_seconds() / 60.0
        if ttl_minutes == 0 or age_minutes >= ttl_minutes:
            path = os.path.join(temp_dir, name)
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
        ttl_minutes: 存活时长（分钟）。0=立即清理，-1=不启动。
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
