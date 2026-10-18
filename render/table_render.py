"""表格渲染。

Pillow 手绘表格，支持格内加粗/斜体/删除线/行内代码/链接混排；
格内的 $...$ 公式按行内图片嵌入，不再显示 LaTeX 源码。
"""
from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont

from render.expr_render import render_expr_image
from render.font import get_font
from render.parser import InlineExpr, split_inline_math
from render.table_domain import RichCell, Span, Table

# 硬编码颜色预设（后续可能从配置推算）
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

_FONT_SIZE = 38  # 18pt @ 150 DPI 等效 (150/72*18≈38)
_PAD_X = 27      # 10pt @ 150 DPI 等效
_PAD_Y = 20      # 7pt @ 150 DPI 等效
_DPI = 2
_MARGIN = 20     # 10px 外边距 @ 2x 内部分辨率
_STRIKE_Y_OFFSET = -4  # 删除线相对基线偏移（内部 px，按 _DPI 缩放后）
_MATH_GAP = 3    # 公式与相邻文字的间距 @ 2x 内部分辨率


@dataclass
class _TextPiece:
    """单元格内的一段文字。"""

    text: str
    span: Span


@dataclass
class _MathPiece:
    """单元格内的一枚公式图。"""

    image: Image.Image
    span: Span


def _rgb_hex(color: tuple[int, int, int]) -> str:
    """把 RGB 元组转成 pillowlatex 需要的十六进制颜色。"""
    return "#{:02x}{:02x}{:02x}".format(*color)


def _build_pieces(
    spans: list[Span],
    math_cache: dict[tuple[str, str], Image.Image],
) -> list[_TextPiece | _MathPiece]:
    """把单元格的 Span 拆成文字/公式图两种绘制片段。

    Args:
        spans: 单元格 Span 列表。
        math_cache: 公式源码 + 颜色 → 公式图，同一表格内复用。

    Returns:
        按出现顺序排列的绘制片段。
    """
    pieces: list[_TextPiece | _MathPiece] = []
    for span in spans:
        for part in split_inline_math(span.text):
            if isinstance(part, InlineExpr):
                color = _rgb_hex(_span_color(span))
                key = (part.expr, color)
                image = math_cache.get(key)
                if image is None:
                    image = render_expr_image(
                        part.expr, color=color, size=_FONT_SIZE * _DPI
                    )
                    math_cache[key] = image
                pieces.append(_MathPiece(image=image, span=span))
            elif part.text:
                pieces.append(_TextPiece(text=part.text, span=span))
    return pieces


def render_table(
    table: Table,
) -> bytes:
    """渲染表格为 PNG 图片。

    Args:
        table: Table 实例，含 headers 和 rows 属性（均为 RichCell）。

    Returns:
        png_path 渲染产物文件路径。
    """
    headers: list[RichCell] = table.headers
    rows: list[list[RichCell]] = table.rows

    font_reg = get_font(_FONT_SIZE * _DPI)

    all_rows: list[list[RichCell]] = []
    if headers:
        all_rows.append(headers)
    all_rows.extend(rows)

    n_rows = len(all_rows)
    n_cols = max((len(r) for r in all_rows), default=1)

    math_cache: dict[tuple[str, str], Image.Image] = {}
    grid: list[list[list[_TextPiece | _MathPiece]]] = [
        [
            _build_pieces(row[c].spans, math_cache) if c < len(row) else []
            for c in range(n_cols)
        ]
        for row in all_rows
    ]

    # 一次遍历同时算列宽和行高
    col_widths = [0] * n_cols
    row_heights = [0] * n_rows
    for r in range(n_rows):
        for c in range(n_cols):
            w, h = _cell_size(grid[r][c], font_reg)
            col_widths[c] = max(col_widths[c], w + _PAD_X * 2 * _DPI)
            row_heights[r] = max(row_heights[r], h + _PAD_Y * 2 * _DPI)

    total_w = sum(col_widths)
    total_h = sum(row_heights)

    canvas_w = total_w + _MARGIN * 2 + 1
    canvas_h = total_h + _MARGIN * 2 + 1
    img = Image.new("RGBA", (canvas_w, canvas_h), _RGB_BG)
    draw = ImageDraw.Draw(img)

    y = _MARGIN
    for r in range(n_rows):
        rh = row_heights[r]
        draw.line([(_MARGIN, y), (_MARGIN + total_w, y)], fill=_RGB_GRID, width=1 * _DPI)

        for c in range(n_cols):
            pieces = grid[r][c]
            x = sum(col_widths[:c]) + _MARGIN
            w = col_widths[c]

            draw.line([(x, y), (x, y + rh)], fill=_RGB_GRID, width=1 * _DPI)

            is_header = r == 0 and bool(headers)
            bg = _RGB_HEADER_BG if is_header else _RGB_BG
            draw.rectangle([x + 1, y + 1, x + w - 1, y + rh - 1], fill=bg)

            text_h = max(
                (_text_size(p.text, font_reg)[1] for p in pieces if isinstance(p, _TextPiece)),
                default=0,
            )
            text_top = y + (rh - text_h) // 2
            cursor = x + _PAD_X * _DPI
            for piece in pieces:
                if isinstance(piece, _MathPiece):
                    gap = _MATH_GAP * _DPI
                    top = y + (rh - piece.image.height) // 2
                    cursor += gap
                    img.paste(piece.image, (cursor, top), piece.image)
                    cursor += piece.image.width + gap
                    continue

                span = piece.span
                color = _span_color(span)
                draw.text((cursor, text_top), piece.text, fill=color, font=font_reg)
                bbox = font_reg.getbbox(piece.text)
                w_span = bbox[2] - bbox[0]

                if span.code:
                    h_span = bbox[3] - bbox[1]
                    draw.rectangle(
                        [cursor - 2, text_top - 2, cursor + w_span + 2, text_top + h_span + 2],
                        fill=_RGB_CODE_BG,
                    )
                    draw.text((cursor, text_top), piece.text, fill=color, font=font_reg)

                if span.strike:
                    mid_y = text_top + _STRIKE_Y_OFFSET * _DPI
                    draw.line(
                        [(cursor, mid_y), (cursor + w_span, mid_y)],
                        fill=_RGB_STRIKE,
                        width=1 * _DPI,
                    )

                if span.link_url:
                    ul_y = text_top + text_h + 1 * _DPI
                    draw.line(
                        [(cursor, ul_y), (cursor + w_span, ul_y)],
                        fill=_RGB_LINK,
                        width=1 * _DPI,
                    )

                cursor += w_span

        y += rh

    draw.line([(_MARGIN, y), (_MARGIN + total_w, y)], fill=_RGB_GRID, width=1 * _DPI)
    draw.line([(_MARGIN + total_w, _MARGIN), (_MARGIN + total_w, y)], fill=_RGB_GRID, width=1 * _DPI)

    img = img.resize((canvas_w // _DPI, canvas_h // _DPI), Image.LANCZOS)

    buf = BytesIO()
    img.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def _span_color(span: Span) -> tuple[int, int, int]:
    """根据 Span 格式状态返回对应颜色。"""
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


def _text_size(text: str, font_reg: ImageFont.FreeTypeFont) -> tuple[int, int]:
    """计算一段文字在给定字体下的宽高。"""
    bbox = font_reg.getbbox(text)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def _cell_size(
    pieces: list[_TextPiece | _MathPiece],
    font_reg: ImageFont.FreeTypeFont,
) -> tuple[int, int]:
    """计算单元格片段组合的总宽高。

    Args:
        pieces: 绘制片段列表。
        font_reg: 字体。

    Returns:
        (总宽度, 最大行高)。
    """
    total_w = 0
    max_h = 0
    for piece in pieces:
        if isinstance(piece, _MathPiece):
            total_w += piece.image.width + 2 * _MATH_GAP * _DPI
            max_h = max(max_h, piece.image.height)
            continue
        width, height = _text_size(piece.text, font_reg)
        total_w += width
        max_h = max(max_h, height)
    return total_w, max_h
