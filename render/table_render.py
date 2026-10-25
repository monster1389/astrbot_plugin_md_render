"""表格渲染：Table → HTML + CSS → pytakumi（无浏览器）→ PNG。

格内文本按列宽自动折行，画布宽度封顶，避免整张图被客户端等比缩小后字号不可读。
不用 ``<table>``：takumi 0.1.5 忽略 ``<col>`` / ``<colgroup>`` 的宽度（写百分比或
px 都会被均分），所以表格用 flex 手搭，列宽以像素写死在格子上。

字体与底色都来自公共层：字体栈与调色板取自 ``render.canvas``，度量字体取自
``render.font``，出图交给 ``render.canvas.fragment``。
"""
from __future__ import annotations

import base64
import html as htmllib
from dataclasses import dataclass, field

from astrbot.api import logger
from PIL import ImageFont

from render import canvas, font
from render.expr_render import formula_image
from render.parser import InlineExpr, split_inline_math
from render.table_domain import RichCell, Span, Table

_PAD_X = 18       # 单元格左右内边距（px）
_PAD_Y = 14       # 单元格上下内边距（px）
_BORDER = 1       # 边框宽度（px）
_CODE_PAD = 4     # 行内代码左右内边距（px）
_FLOOR_MAX = 300   # 短列阈值：自然宽不超过它的列不参与压缩
_TWO_CHARS = canvas.TABLE_SIZE * 2


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


def _css(stack: str) -> str:
    """拼出表格样式表。

    Args:
        stack: CSS 字体栈，来自版面层。

    Returns:
        CSS 文本。
    """
    return f"""
body {{ margin: 0; background: {canvas.BG};
        font-family: {stack}; font-size: {canvas.TABLE_SIZE}px; line-height: 1.5; }}
.rows {{ display: flex; flex-direction: column;
         border-left: {_BORDER}px solid {canvas.GRID};
         border-top: {_BORDER}px solid {canvas.GRID}; }}
.row {{ display: flex; }}
.cell {{ box-sizing: border-box; flex: none;
         border-right: {_BORDER}px solid {canvas.GRID};
         border-bottom: {_BORDER}px solid {canvas.GRID};
         padding: {_PAD_Y}px {_PAD_X}px; color: {canvas.TEXT};
         word-break: break-word; overflow-wrap: anywhere; }}
.hd {{ background: {canvas.HEADER_BG}; color: {canvas.BOLD}; }}
b {{ color: {canvas.BOLD}; }}
i {{ color: {canvas.ITALIC}; }}
s {{ color: {canvas.STRIKE}; }}
code {{ background: {canvas.CODE_BG}; color: {canvas.CODE_TEXT};
        padding: 0 {_CODE_PAD}px; }}
a {{ color: {canvas.LINK}; text-decoration: underline; }}
"""


def _span_color(span: Span) -> str | None:
    """格内公式的文字色：只有带显式格式的片段才覆盖角色默认色。

    Args:
        span: 富文本片段。

    Returns:
        CSS 颜色值；纯文本片段返回 None，由公式角色决定。
    """
    if span.code:
        return canvas.CODE_TEXT
    if span.link_url:
        return canvas.LINK
    if span.strike:
        return canvas.STRIKE
    if span.bold:
        return canvas.BOLD
    if span.italic:
        return canvas.ITALIC
    return None


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


def _data_uri(png: bytes) -> str:
    """把公式图转成可内嵌的 data URI。

    Args:
        png: PNG 字节。

    Returns:
        data URI 字符串。
    """
    return "data:image/png;base64," + base64.b64encode(png).decode()


def _cell(
    cell: RichCell,
    measure: ImageFont.FreeTypeFont,
    *,
    header: bool = False,
) -> _Cell:
    """把一个富文本单元格转成 HTML 片段并量出单行宽度。

    Args:
        cell: 富文本单元格。
        measure: 测量用字体。
        header: 是否表头行，决定格内公式的默认颜色。

    Returns:
        单元格片段、宽度与对齐方式。
    """
    parts: list[str] = []
    width = _PAD_X * 2 + _BORDER * 2
    for span in cell.spans:
        color = _span_color(span)
        for part in split_inline_math(span.text):
            if isinstance(part, InlineExpr):
                try:
                    formula = formula_image(
                        part.expr,
                        role="table_header" if header else "table",
                        color=color,
                    )
                except RuntimeError as exc:
                    # 一格失败只坏这一格：退回原文，其余格子照常出图
                    literal = f"${part.expr}$"
                    logger.warning(
                        "格内公式渲染失败，改用原文：%s（%s）", part.expr, exc
                    )
                    parts.append(_decorate(htmllib.escape(literal), span))
                    width += int(measure.getlength(literal))
                    continue
                parts.append(
                    f'<img src="{_data_uri(formula.png)}" '
                    f'style="height:{formula.height}px; width:{formula.width}px; '
                    f'vertical-align:middle">'
                )
                width += formula.width
            elif part.text:
                parts.append(_decorate(htmllib.escape(part.text), span))
                width += int(measure.getlength(part.text))
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
    avail = canvas.MAX_WIDTH - _BORDER * (n_cols + 1)
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
    """拼出表格主体片段（表头 + 表体，flex 手搭）。

    Args:
        layout: 已量好的布局。
        widths: 各列像素宽。

    Returns:
        HTML 片段，页面骨架与底色由版面层补。
    """
    head = _row_html(layout.header, widths, "hd") if layout.header else ""
    body = "".join(_row_html(row, widths, "") for row in layout.rows)
    return f'<div class="rows">{head}{body}</div>'


def render_table(table: Table) -> bytes:
    """渲染表格为 PNG 图片。

    Args:
        table: Table 实例，含 headers 和 rows 属性（均为 RichCell）。

    Returns:
        PNG 图片字节。
    """
    measure = font.measure_font(canvas.TABLE_SIZE)
    layout = _Layout(
        header=[_cell(c, measure, header=True) for c in table.headers],
        rows=[[_cell(c, measure) for c in row] for row in table.rows],
        n_cols=max([len(table.headers)] + [len(r) for r in table.rows] + [1]),
    )
    natural, header = _natural_widths(layout)
    widths = plan_widths(natural, header)
    return canvas.fragment(
        _document(layout, widths),
        _css(canvas.font_stack("body")),
        width=max(sum(widths) + _BORDER, 1),
    )
