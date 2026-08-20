"""字体发现与缓存。

字体是全局基础设施：initialize() 用 init_font(data_dir) 记录数据目录，
渲染器按需取字体名（pygments）或字体对象（Pillow）。发现每次刷新，
路径变化时清空字号缓存，保证异步下载中的捆绑字体落地后能被拾取。
"""
from __future__ import annotations

import logging
import os
import threading

from PIL import ImageFont

logger = logging.getLogger(__name__)

_font_dir: str | None = None
_font_path: str | None = None
_font_cache: dict[int, ImageFont.FreeTypeFont] = {}
_lock = threading.Lock()


def init_font(data_dir: str | None = None) -> None:
    """记录字体搜索目录；为 None 时只搜系统字体。

    Args:
        data_dir: 插件数据目录路径，捆绑字体在其 fonts/ 子目录。
    """
    global _font_dir
    _font_dir = data_dir


def find_font_path() -> str | None:
    """发现可用中文字体路径，每次调用刷新。

    Returns:
        第一个存在的字体路径，都没找到返回 None。
    """
    return _discover_font_path(_font_dir)


def get_font(size: int) -> ImageFont.FreeTypeFont:
    """获取缓存的字体对象，按字号缓存。线程安全。

    路径变化时清空缓存，重新加载新路径的字体。

    Args:
        size: 字号（像素）。

    Returns:
        PIL 字体对象。字体不可用时回退为默认位图字体。
    """
    global _font_path
    path = find_font_path()
    with _lock:
        if path != _font_path:
            _font_cache.clear()
            _font_path = path
        if size not in _font_cache:
            if path is None:
                logger.warning("未找到中文字体，将使用默认位图字体，中文将显示为豆腐块")
                _font_cache[size] = ImageFont.load_default()
            else:
                _font_cache[size] = ImageFont.truetype(path, size)
        return _font_cache[size]


def _discover_font_path(data_dir: str | None) -> str | None:
    """在捆绑字体与系统字体间发现第一个存在的路径。

    Args:
        data_dir: 插件数据目录路径，为 None 时只搜系统字体。

    Returns:
        第一个存在的字体路径，都没找到返回 None。
    """
    candidates: list[str] = []
    if data_dir:
        candidates.append(os.path.join(data_dir, "fonts", "SarasaMonoSC-Regular.ttf"))
    candidates += [
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None
