"""表格渲染：Table → HTML + CSS → pytakumi（无浏览器）→ PNG。

格内文本按列宽自动折行，画布宽度封顶，避免整张图被客户端等比缩小后字号不可读。
不用 ``<table>``：takumi 0.1.5 忽略 ``<col>`` / ``<colgroup>`` 的宽度（写百分比或
px 都会被均分），所以表格用 flex 手搭，列宽以像素写死在格子上。
"""
from __future__ import annotations

import base64
import html as htmllib
import os
import threading
from dataclasses import dataclass, field
from io import BytesIO

from PIL import Image, ImageFont

from render.expr_render import render_expr_image
from render.font import find_font_spec, font_family
from render.html_render import render_document
from render.parser import InlineExpr, split_inline_math
from render.table_domain import RichCell, Span, Table

# 颜色预设（与代码块、公式图的深色底一致）
_RGB_BG = (26, 26, 46)
_RGB_FONT = (220, 220, 230)
_RGB_HEADER_BG = (40, 40, 65)
_RGB_GRID = (80, 80, 110)
_RGB_BOLD = (255, 210, 160)
_RGB_ITALIC = (180, 210, 240)
_RGB_STRIKE = (140, 140, 150)
_RGB_CODE_BG = (50, 50, 70)
_RGB_CODE = (150, 220, 150)
_RGB_LINK = (120, 180, 255)

_FONT_SIZE = 34   # 正文字号（px）
_PAD_X = 18       # 单元格左右内边距（px）
_PAD_Y = 14       # 单元格上下内边距（px）
_BORDER = 1       # 边框宽度（px）
_CODE_PAD = 4     # 行内代码左右内边距（px）
_MAX_WIDTH = 1080  # 画布宽度上限
_FLOOR_MAX = 300   # 短列阈值：自然宽不超过它的列不参与压缩
_TWO_CHARS = _FONT_SIZE * 2

# 首选比例中文字体：Noto Sans CJK SC。等宽 face 留给代码块，表格正文要比例。
_NOTO_CJK = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
_NOTO_FACE = 2          # ttc 内的 Noto Sans CJK SC
_NOTO_FAMILY = "Noto Sans CJK SC"


@dataclass(frozen=True)
class _Face:
    """测量与渲染共用的字体身份。

    Attributes:
        path: 字体文件路径。
        index: ttc 集合内的 face 序号。
        family: CSS 引用的族名。
    """

    path: str
    index: int
    family: str


@dataclass
class _Cell:
    """单元格的 HTML 片段与单行排开宽度。

    Attributes:
        html: 已转义、已带格式标签的 HTML 片段。
        width: 单行排开所需的像素宽（含内边距与边框）。
        align: 列对齐方式；空串表示不写。
    """

    html: str
    width: int
    align: str = ""


@dataclass
class _Layout:
    """一次渲染所需的全部度量统计。

    Attributes:
        header: 表头各格。
        rows: 表体各格。
        n_cols: 列数。
    """

    header: list[_Cell] = field(default_factory=list)
    rows: list[list[_Cell]] = field(default_factory=list)
    n_cols: int = 1


_lock = threading.Lock()
_face: _Face | None = None
_measure_font: ImageFont.FreeTypeFont | None = None


def _rgb_hex(color: tuple[int, int, int]) -> str:
    """把 RGB 元组转成 CSS 十六进制颜色。"""
    return "#{:02x}{:02x}{:02x}".format(*color)


def _read_face() -> _Face:
    """确定表格使用的字体：优先比例中文，系统缺失时回退 font.py 的发现结果。

    Returns:
        字体身份。

    Raises:
        RuntimeError: 找不到任何中文字体。
    """
    if os.path.exists(_NOTO_CJK):
        return _Face(_NOTO_CJK, _NOTO_FACE, _NOTO_FAMILY)
    spec = find_font_spec()
    if spec is None:
        raise RuntimeError("未找到中文字体，表格无法渲染")
    return _Face(spec.path, spec.index, font_family(spec) or "sans-serif")


def _resources() -> tuple[_Face, ImageFont.FreeTypeFont]:
    """惰性确定字体身份与测量字体。线程安全。

    Returns:
        (字体身份, 测量用 Pillow 字体)。
    """
    global _face, _measure_font
    with _lock:
        if _face is None or _measure_font is None:
            face = _read_face()
            _measure_font = ImageFont.truetype(face.path, _FONT_SIZE, index=face.index)
            _face = face
    assert _face is not None and _measure_font is not None
    return _face, _measure_font


def _css(family: str) -> str:
    """拼出表格样式表。

    Args:
        family: 字体族名。

    Returns:
        CSS 文本。
    """
    return f"""
body {{ margin: 0; background: {_rgb_hex(_RGB_BG)};
        font-family: "{family}"; font-size: {_FONT_SIZE}px; line-height: 1.5; }}
.rows {{ display: flex; flex-direction: column;
         border-left: {_BORDER}px solid {_rgb_hex(_RGB_GRID)};
         border-top: {_BORDER}px solid {_rgb_hex(_RGB_GRID)}; }}
.row {{ display: flex; }}
.cell {{ box-sizing: border-box; flex: none;
         border-right: {_BORDER}px solid {_rgb_hex(_RGB_GRID)};
         border-bottom: {_BORDER}px solid {_rgb_hex(_RGB_GRID)};
         padding: {_PAD_Y}px {_PAD_X}px; color: {_rgb_hex(_RGB_FONT)};
         word-break: break-word; overflow-wrap: anywhere; }}
.hd {{ background: {_rgb_hex(_RGB_HEADER_BG)}; color: {_rgb_hex(_RGB_BOLD)}; }}
b {{ color: {_rgb_hex(_RGB_BOLD)}; }}
i {{ color: {_rgb_hex(_RGB_ITALIC)}; }}
s {{ color: {_rgb_hex(_RGB_STRIKE)}; }}
code {{ background: {_rgb_hex(_RGB_CODE_BG)}; color: {_rgb_hex(_RGB_CODE)};
        padding: 0 {_CODE_PAD}px; }}
a {{ color: {_rgb_hex(_RGB_LINK)}; text-decoration: underline; }}
"""


def _span_color(span: Span) -> tuple[int, int, int]:
    """根据 Span 格式状态返回对应文字颜色。"""
    if span.code:
        return _RGB_CODE
    if span.link_url:
        return _RGB_LINK
    if span.strike:
        return _RGB_STRIKE
    if span.bold:
        return _RGB_BOLD
    if span.italic:
        return _RGB_ITALIC
    return _RGB_FONT


def _decorate(inner: str, span: Span) -> str:
    """给一段已转义的文本套上格式标签。

    Args:
        inner: 已转义的文本或图片标签。
        span: 该片段的格式状态。

    Returns:
        套好标签的 HTML 片段。
    """
    if span.code:
        inner = f"<code>{inner}</code>"
    if span.strike:
        inner = f"<s>{inner}</s>"
    if span.italic:
        inner = f"<i>{inner}</i>"
    if span.bold:
        inner = f"<b>{inner}</b>"
    if span.link_url:
        inner = f'<a href="{htmllib.escape(span.link_url)}">{inner}</a>'
    return inner


def _data_uri(image: Image.Image) -> str:
    """把公式图转成可内嵌的 data URI。"""
    buf = BytesIO()
    image.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _cell(cell: RichCell, font: ImageFont.FreeTypeFont,
          math_cache: dict[tuple[str, str], Image.Image]) -> _Cell:
    """把一个富文本单元格转成 HTML 片段并量出单行宽度。

    Args:
        cell: 富文本单元格。
        font: 测量用字体。
        math_cache: 公式源码 + 颜色 → 公式图，同一表格内复用。

    Returns:
        单元格片段、宽度与对齐方式。
    """
    parts: list[str] = []
    width = _PAD_X * 2 + _BORDER * 2
    for span in cell.spans:
        color = _rgb_hex(_span_color(span))
        for part in split_inline_math(span.text):
            if isinstance(part, InlineExpr):
                key = (part.expr, color)
                image = math_cache.get(key)
                if image is None:
                    image = render_expr_image(part.expr, color=color, size=_FONT_SIZE)
                    math_cache[key] = image
                w, h = image.size
                parts.append(
                    f'<img src="{_data_uri(image)}" '
                    f'style="height:{h}px; width:{w}px; vertical-align:middle">'
                )
                width += w
            elif part.text:
                parts.append(_decorate(htmllib.escape(part.text), span))
                width += int(font.getlength(part.text))
                if span.code:
                    width += _CODE_PAD * 2
    return _Cell(html="".join(parts) or "&nbsp;", width=width, align=cell.align)


def _natural_widths(layout: _Layout) -> tuple[list[int], list[int]]:
    """统计每列的自然宽（最长一格单行排开）与表头宽。

    Args:
        layout: 已量好各单元格的布局。

    Returns:
        (自然宽列表, 表头宽列表)，长度均为 n_cols。
    """
    natural = [0] * layout.n_cols
    header = [0] * layout.n_cols
    for c in range(layout.n_cols):
        if c < len(layout.header):
            header[c] = layout.header[c].width
        natural[c] = max([header[c]] + [
            row[c].width for row in layout.rows if c < len(row)
        ])
    return natural, header


def plan_widths(natural: list[int], header: list[int]) -> list[int]:
    """按内容分配列宽。

    三档：整表放得下就按自然宽（画布跟着收窄）；放不下时短列（自然宽不超过
    ``_FLOOR_MAX``）给足自然宽、长列退回保底宽，余量只分给长列；长列都不够分时
    整表等比压缩。短列不参与压缩，因为它折行只会更难读。

    Args:
        natural: 每列自然宽（最长一格单行排开，含内边距与边框）。
        header: 每列表头自然宽。

    Returns:
        每列像素宽。
    """
    n_cols = len(natural)
    if n_cols == 0:
        return []
    avail = _MAX_WIDTH - _BORDER * (n_cols + 1)
    if sum(natural) <= avail:
        return list(natural)
    floor = [
        min(w, max(h, _TWO_CHARS + _PAD_X * 2 + _BORDER * 2), _FLOOR_MAX)
        for w, h in zip(natural, header)
    ]
    base = [w if w <= _FLOOR_MAX else f for w, f in zip(natural, floor)]
    total_base = sum(base)
    if total_base >= avail:
        return [max(1, int(b * avail / total_base)) for b in base]
    spare = avail - total_base
    deficits = [w - b for w, b in zip(natural, base)]
    total_deficit = sum(deficits)
    return [int(b + spare * d / total_deficit) for b, d in zip(base, deficits)]


def _row_html(cells: list[_Cell], widths: list[int], cls: str) -> str:
    """把一行单元格拼成 HTML，盒宽写死为算好的列宽，不足的列补空单元格。

    Args:
        cells: 该行的单元格片段。
        widths: 各列像素宽。
        cls: 附加类名（表头行传 ``hd``，表体传空串）。

    Returns:
        一行 HTML。
    """
    body = "".join(
        f'<div class="cell {cls}" style="width:{widths[c]}px{_align_style(cells, c)}">'
        f"{cells[c].html if c < len(cells) else '&nbsp;'}</div>"
        for c in range(len(widths))
    )
    return f'<div class="row">{body}</div>'


def _align_style(cells: list[_Cell], index: int) -> str:
    """取出该格的对齐方式，拼成 CSS 声明片段。

    Args:
        cells: 该行的单元格片段。
        index: 列索引。

    Returns:
        ``;text-align:center`` 形式；未指定时为空串。
    """
    if index >= len(cells) or not cells[index].align:
        return ""
    return f";text-align:{cells[index].align}"


def _document(layout: _Layout, widths: list[int]) -> str:
    """拼出完整 HTML 文档（表头 + 表体，flex 手搭）。

    Args:
        layout: 已量好的布局。
        widths: 各列像素宽。

    Returns:
        完整的 HTML 文档字符串。
    """
    head = _row_html(layout.header, widths, "hd") if layout.header else ""
    body = "".join(_row_html(row, widths, "") for row in layout.rows)
    return f'<html><body><div class="rows">{head}{body}</div></body></html>'


def render_table(table: Table) -> bytes:
    """渲染表格为 PNG 图片。

    Args:
        table: Table 实例，含 headers 和 rows 属性（均为 RichCell）。

    Returns:
        PNG 图片字节。
    """
    face, font = _resources()
    math_cache: dict[tuple[str, str], Image.Image] = {}
    layout = _Layout(
        header=[_cell(c, font, math_cache) for c in table.headers],
        rows=[[_cell(c, font, math_cache) for c in row] for row in table.rows],
        n_cols=max([len(table.headers)] + [len(r) for r in table.rows] + [1]),
    )
    natural, header = _natural_widths(layout)
    widths = plan_widths(natural, header)
    return render_document(
        _document(layout, widths), max(sum(widths) + _BORDER, 1), _css(face.family)
    )
