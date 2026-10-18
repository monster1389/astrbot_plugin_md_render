"""字体发现与缓存。

字体是全局基础设施：initialize() 用 init_font(data_dir) 记录数据目录，
渲染器按需取字体规格（pygments）或字体对象（Pillow）。发现每次刷新，
规格变化时清空字号缓存，保证手动放入的字体落地后能被拾取。

候选按「中英文覆盖 + 等宽」排序。ttc 集合必须指定 face：第 0 个 face
常是比例字体（CJK 变体之一），拿来渲染代码会让列对齐歪掉。
"""
from __future__ import annotations

import os
import threading
from dataclasses import dataclass

from PIL import ImageFont

from astrbot.api import logger

# AstrBot 官方镜像自带（fonts-noto-cjk），第 7 个 face 为 Noto Sans Mono CJK SC
_NOTO_CJK = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
# 非官方镜像可能装了文泉驿，第 1 个 face 为 WenQuanYi Micro Hei Mono
_WQY = "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"
# 无中文字形，仅作最后保底（中文会显示为豆腐块）
_DEJAVU = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"

_SYSTEM_CANDIDATES: tuple[tuple[str, int], ...] = (
    (_NOTO_CJK, 7),
    (_WQY, 1),
    (_DEJAVU, 0),
)


@dataclass(frozen=True)
class FontSpec:
    """字体文件与其中 face 的位置。

    Attributes:
        path: 字体文件路径。
        index: ttc 集合内的 face 序号，单 face 字体为 0。
    """

    path: str
    index: int = 0


# 系统候选在 Typst/fontconfig 里的族名
_FAMILY_NAMES: dict[FontSpec, str] = {
    FontSpec(_NOTO_CJK, 7): "Noto Sans Mono CJK SC",
    FontSpec(_WQY, 1): "WenQuanYi Micro Hei Mono",
    FontSpec(_DEJAVU, 0): "DejaVu Sans Mono",
}
# 手动放置的字体按文件名推断族名
_MANUAL_FAMILIES: dict[str, str] = {
    "SarasaMonoSC-Regular.ttf": "Sarasa Mono SC",
}

_font_dir: str | None = None
_font_spec: FontSpec | None = None
_font_cache: dict[int, ImageFont.FreeTypeFont] = {}
_lock = threading.Lock()


def init_font(data_dir: str | None = None) -> None:
    """记录字体搜索目录；为 None 时只搜系统字体。

    Args:
        data_dir: 插件数据目录路径，手动放置的字体在其 fonts/ 子目录。
    """
    global _font_dir
    _font_dir = data_dir


def find_font_spec() -> FontSpec | None:
    """发现可用中文字体，每次调用刷新。

    Returns:
        第一个存在的字体规格，都没找到返回 None。
    """
    return _discover_font_spec(_font_dir)


def font_family(spec: FontSpec | None) -> str | None:
    """返回字体在 Typst 里的族名。

    Args:
        spec: 字体规格；None 表示没找到字体。

    Returns:
        字体族名；未知字体返回 None。
    """
    if spec is None:
        return None
    family = _FAMILY_NAMES.get(spec)
    if family is not None:
        return family
    return _MANUAL_FAMILIES.get(os.path.basename(spec.path))


def font_search_dir(spec: FontSpec | None) -> str | None:
    """返回需要额外注册给 Typst 的字体目录。

    Typst 默认能看见系统字体，只有手动放进 data_dir 的字体需要显式注册。

    Args:
        spec: 字体规格。

    Returns:
        字体所在目录；系统字体或没有字体时返回 None。
    """
    if spec is None or spec in _FAMILY_NAMES:
        return None
    return os.path.dirname(spec.path)


def get_font(size: int) -> ImageFont.FreeTypeFont:
    """获取缓存的字体对象，按字号缓存。线程安全。

    规格变化时清空缓存，重新加载新规格的字体。

    Args:
        size: 字号（像素）。

    Returns:
        PIL 字体对象。字体不可用时回退为默认位图字体。
    """
    global _font_spec
    spec = find_font_spec()
    with _lock:
        if spec != _font_spec:
            _font_cache.clear()
            _font_spec = spec
        if size not in _font_cache:
            if spec is None:
                logger.warning("未找到中文字体，将使用默认位图字体，中文将显示为豆腐块")
                _font_cache[size] = ImageFont.load_default()
            else:
                _font_cache[size] = ImageFont.truetype(
                    spec.path, size, index=spec.index
                )
        return _font_cache[size]


def _discover_font_spec(data_dir: str | None) -> FontSpec | None:
    """在插件字体与系统字体间发现第一个存在的规格。

    Args:
        data_dir: 插件数据目录路径，为 None 时只搜系统字体。

    Returns:
        第一个存在的字体规格，都没找到返回 None。
    """
    candidates: list[FontSpec] = []
    if data_dir:
        manual = os.path.join(data_dir, "fonts", "SarasaMonoSC-Regular.ttf")
        candidates.append(FontSpec(manual))
    candidates += [FontSpec(path, index) for path, index in _SYSTEM_CANDIDATES]
    for spec in candidates:
        if os.path.exists(spec.path):
            return spec
    return None
