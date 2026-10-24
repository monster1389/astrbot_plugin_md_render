"""字体发现、族名与度量。

字体是全局基础设施：``main`` 用 ``init_font(data_dir)`` 记录数据目录，
渲染器通过 ``font_files()`` 取需要注册给 takumi 的字体文件，通过
``font_family()`` / ``body_family()`` 取 CSS 与 Typst 用的族名，
表格通过 ``measure_font()`` 取 Pillow 度量字体。发现每次刷新，
规格变化时清空度量缓存，保证手动放入的字体落地后能被拾取。

两条候选链各自独立：等宽链给代码块，正文链给表格与页面正文。ttc 集合必须
指定 face：第 0 个 face 常是比例字体（CJK 变体之一），拿来渲染代码会让列对齐
歪掉；反过来正文要的就是比例体，等宽的宽字距只适合代码。
"""
from __future__ import annotations

import os
import threading
from dataclasses import dataclass

from PIL import ImageFont

# AstrBot 官方镜像自带（fonts-noto-cjk）
_NOTO_CJK = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
# 无中文字形，仅作最后保底（中文会显示为豆腐块）
_DEJAVU = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"

# 不列文泉驿：不少镜像上那个路径躺着的是 Noto 的副本，写死的 face 序号
# 会指向日文/韩文比例体，静默出怪字形比没有退路更糟。

# 等宽候选：Noto ttc 第 7 个 face 为 Noto Sans Mono CJK SC
_MONO_CANDIDATES: tuple[tuple[str, int], ...] = (
    (_NOTO_CJK, 7),
    (_DEJAVU, 0),
)
# 正文候选：Noto ttc 第 2 个 face 为比例体 Noto Sans CJK SC
_BODY_CANDIDATES: tuple[tuple[str, int], ...] = (
    (_NOTO_CJK, 2),
    (_DEJAVU, 0),
)

# 手动放置的字体文件名
_MANUAL_FONT = "SarasaMonoSC-Regular.ttf"


@dataclass(frozen=True)
class FontSpec:
    """字体文件与其中 face 的位置。

    Attributes:
        path: 字体文件路径。
        index: ttc 集合内的 face 序号，单 face 字体为 0。
    """

    path: str
    index: int = 0


# 已知字体在 CSS / Typst 里的族名
_FAMILY_NAMES: dict[FontSpec, str] = {
    FontSpec(_NOTO_CJK, 7): "Noto Sans Mono CJK SC",
    FontSpec(_NOTO_CJK, 2): "Noto Sans CJK SC",
    FontSpec(_DEJAVU, 0): "DejaVu Sans Mono",
}
# 手动放置的字体按文件名推断族名
_MANUAL_FAMILIES: dict[str, str] = {
    _MANUAL_FONT: "Sarasa Mono SC",
}

_font_dir: str | None = None
_measure_spec: FontSpec | None = None
_measure_cache: dict[tuple[FontSpec, int], ImageFont.FreeTypeFont] = {}
_lock = threading.Lock()


def init_font(data_dir: str | None = None) -> None:
    """记录字体搜索目录；为 None 时只搜系统字体。

    Args:
        data_dir: 插件数据目录路径，手动放置的字体在其 fonts/ 子目录。
    """
    global _font_dir
    _font_dir = data_dir


def find_font_spec() -> FontSpec | None:
    """发现等宽中文字体（代码块用），每次调用刷新。

    Returns:
        第一个存在的字体规格，都没找到返回 None。
    """
    return _discover(_font_dir, _MONO_CANDIDATES)


def body_spec() -> FontSpec | None:
    """发现比例中文字体（表格与页面正文用）。

    手动放置的字体是等宽的，不参与正文候选；系统没有比例体时回退到等宽体，
    宁可字距宽一点也不出豆腐块。

    Returns:
        正文字体规格，都没找到返回 None。
    """
    return _discover(None, _BODY_CANDIDATES) or find_font_spec()


def body_family() -> str | None:
    """返回正文比例体的族名。

    Returns:
        族名；没有字体或字体未知时返回 None。
    """
    return font_family(body_spec())


def font_family(spec: FontSpec | None) -> str | None:
    """返回字体在 CSS / Typst 里的族名。

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


def font_files() -> list[str]:
    """返回需要注册给 takumi 的字体文件，去重。

    Returns:
        字体路径列表：等宽体在前、正文体在后；同一文件只出现一次。
    """
    paths: list[str] = []
    for spec in (find_font_spec(), body_spec()):
        if spec is not None and spec.path not in paths:
            paths.append(spec.path)
    return paths


def typst_fonts() -> tuple[list[str], list[str]]:
    """返回 Typst 需要的额外字体目录与系统字体族名。

    Typst 默认能看见系统字体；只有手动放进 data_dir 的字体需要显式注册目录。

    Returns:
        (字体目录列表, 族名列表)。没有可用字体时两者都为空。
    """
    spec = find_font_spec()
    family = font_family(spec)
    search_dir = font_search_dir(spec)
    dirs = [search_dir] if search_dir else []
    families = [family] if family else []
    return dirs, families


def measure_font(size: int) -> ImageFont.FreeTypeFont:
    """获取比例体的 Pillow 字体对象，按 (规格, 字号) 缓存。线程安全。

    Args:
        size: 字号（像素）。

    Returns:
        Pillow 字体对象。

    Raises:
        RuntimeError: 没有任何可用字体，无法度量文本。
    """
    global _measure_spec
    spec = body_spec()
    if spec is None:
        raise RuntimeError("未找到可用字体，无法度量文本")
    with _lock:
        if spec != _measure_spec:
            _measure_cache.clear()
            _measure_spec = spec
        key = (spec, size)
        if key not in _measure_cache:
            _measure_cache[key] = ImageFont.truetype(
                spec.path, size, index=spec.index
            )
        return _measure_cache[key]


def _discover(
    data_dir: str | None,
    candidates: tuple[tuple[str, int], ...],
) -> FontSpec | None:
    """按候选顺序发现第一个存在的字体规格。

    Args:
        data_dir: 插件数据目录路径，非空时手动放置的字体排在最前。
        candidates: 系统候选 (路径, face 序号) 列表。

    Returns:
        第一个存在的字体规格，都没找到返回 None。
    """
    specs: list[FontSpec] = []
    if data_dir:
        specs.append(FontSpec(os.path.join(data_dir, "fonts", _MANUAL_FONT)))
    specs += [FontSpec(path, index) for path, index in candidates]
    for spec in specs:
        if os.path.exists(spec.path):
            return spec
    return None
