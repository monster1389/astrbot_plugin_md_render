"""临时文件存储。

管理本插件渲染产物的临时文件生命周期：命名模式匹配、路径生成、
发送期删除/刷新、后台按 TTL 清扫。AstrBot 无关。

文件由 deliver 在发送完成后删除；后台清扫只兜底尾条与异常中断残留的文件。
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from datetime import datetime

logger = logging.getLogger(__name__)

# 本插件渲染产物命名模式：code/table/expr_时间戳_微秒.{png,md}
_TEMP_FILE_RE = re.compile(r"^(code|table|expr)_\d{8}_\d{6}_\d{6}\.(png|md)$")

# 存活 0 分钟时按一个清扫周期（60 秒）兜底，避免误删尚未发送的渲染产物
_MIN_TTL_MINUTES = 1.0


def is_temp_file(name_or_path: str) -> bool:
    """判断文件名是否为本插件生成的临时渲染文件。

    Args:
        name_or_path: 文件名或完整路径。

    Returns:
        True 表示匹配 code/table/expr_时间戳.{png,md} 命名模式。
    """
    return bool(_TEMP_FILE_RE.match(os.path.basename(name_or_path)))


def build_temp_path(data_dir: str, prefix: str, ext: str) -> str:
    """在 data_dir/temp/ 下建带时间戳的文件路径。

    Args:
        data_dir: 插件数据目录路径。
        prefix: 文件名前缀（如 'code'、'table'、'expr'）。
        ext: 文件扩展名（如 '.png'、'.md'）。

    Returns:
        完整文件路径。
    """
    temp_dir = os.path.join(data_dir, "temp")
    os.makedirs(temp_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    return os.path.join(temp_dir, f"{prefix}_{ts}{ext}")


def delete(paths: list[str]) -> None:
    """删除给定临时文件路径，已不存在则忽略。

    Args:
        paths: 临时文件路径列表。
    """
    for path in paths:
        try:
            os.remove(path)
        except OSError:
            pass


def touch(paths: list[str]) -> None:
    """刷新给定临时文件路径的写盘时间，延长存活窗口。

    Args:
        paths: 临时文件路径列表。
    """
    for path in paths:
        try:
            os.utime(path, None)
        except OSError:
            pass


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
