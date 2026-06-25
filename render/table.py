"""表格渲染。

Pillow 手绘表格，支持格内加粗/斜体/删除线/行内代码/链接混排。
"""
from __future__ import annotations

import logging

from PIL import Image, ImageDraw, ImageFont

from render.glyph import fallback_spans
from render.parser import RichCell, Span
from render.utils import RenderConfig, build_temp_path, find_font_path

logger = logging.getLogger(__name__)

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


def render_table(
    table: object,
    cfg: RenderConfig,
    data_dir: str,
) -> str:
    """渲染表格为 PNG 图片。

    Args:
        table: Table 实例，含 headers 和 rows 属性（均为 RichCell）。
        cfg: 渲染配置。
        data_dir: 插件数据目录路径。

    Returns:
        png_path 渲染产物文件路径。
    """
    headers: list[RichCell] = getattr(table, "headers", [])
    rows: list[list[RichCell]] = getattr(table, "rows", [])

    font_path = find_font_path(data_dir)
    if font_path is None:
        logger.warning("未找到 CJK 字体，表格中文可能显示为豆腐块")

    font_reg = ImageFont.truetype(font_path, _FONT_SIZE * _DPI) if font_path else ImageFont.load_default()
    font_bold = ImageFont.truetype(font_path, _FONT_SIZE * _DPI) if font_path else ImageFont.load_default()

    # 字形回退
    all_rows: list[list[RichCell]] = []
    if headers:
        all_rows.append(headers)
    all_rows.extend(rows)
    fallback_spans(all_rows, cfg.glyph_mapping, font_reg)

    n_rows = len(all_rows)
    n_cols = max((len(r) for r in all_rows), default=1)

    # 列宽
    col_widths: list[int] = []
    for c in range(n_cols):
        max_w = 0
        for r in range(n_rows):
            if c < len(all_rows[r]):
                w = _cell_w(all_rows[r][c].spans, font_reg, font_bold)
                if w > max_w:
                    max_w = w
        col_widths.append(max_w + _PAD_X * 2 * _DPI)

    # 行高
    row_heights: list[int] = []
    for r in range(n_rows):
        max_h = 0
        for c in range(n_cols):
            if c < len(all_rows[r]):
                _, h = _cell_size(all_rows[r][c].spans, font_reg, font_bold)
                if h > max_h:
                    max_h = h
        row_heights.append(max_h + _PAD_Y * 2 * _DPI)

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

        for c in range(min(n_cols, len(all_rows[r]))):
            cell = all_rows[r][c]
            x = sum(col_widths[:c]) + _MARGIN
            w = col_widths[c]

            draw.line([(x, y), (x, y + rh)], fill=_RGB_GRID, width=1 * _DPI)

            is_header = r == 0 and bool(headers)
            bg = _RGB_HEADER_BG if is_header else _RGB_BG
            draw.rectangle([x + 1, y + 1, x + w - 1, y + rh - 1], fill=bg)

            _, text_h = _cell_size(cell.spans, font_reg, font_bold)
            baseline = y + (rh - text_h) // 2
            cursor = x + _PAD_X * _DPI
            for span in cell.spans:
                font = font_bold if span.bold else font_reg
                color = _span_color(span)

                draw.text((cursor, baseline), span.text, fill=color, font=font)
                bbox = font.getbbox(span.text)
                w_span = bbox[2] - bbox[0]

                if span.code:
                    h_span = bbox[3] - bbox[1]
                    draw.rectangle(
                        [cursor - 2, baseline - 2, cursor + w_span + 2, baseline + h_span + 2],
                        fill=_RGB_CODE_BG,
                    )
                    draw.text((cursor, baseline), span.text, fill=color, font=font)

                if span.strike:
                    mid_y = baseline + _STRIKE_Y_OFFSET * _DPI
                    draw.line(
                        [(cursor, mid_y), (cursor + w_span, mid_y)],
                        fill=_RGB_STRIKE,
                        width=1 * _DPI,
                    )

                if span.link_url:
                    ul_y = baseline + text_h + 1 * _DPI
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

    png_path = build_temp_path(data_dir, "table", ".png")
    img.save(png_path, "PNG")

    return png_path


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


def _cell_size(
    spans: list[Span],
    font_reg: ImageFont.FreeTypeFont,
    font_bold: ImageFont.FreeTypeFont,
) -> tuple[int, int]:
    """计算 Span 组合的总宽高。

    Args:
        spans: Span 列表。
        font_reg: 常规字体。
        font_bold: 粗体字体。

    Returns:
        (总宽度, 最大行高)。
    """
    tw = 0
    mh = 0
    for s in spans:
        f = font_bold if s.bold else font_reg
        bbox = f.getbbox(s.text)
        tw += bbox[2] - bbox[0]
        mh = max(mh, bbox[3] - bbox[1])
    return tw, mh


def _cell_w(
    spans: list[Span],
    font_reg: ImageFont.FreeTypeFont,
    font_bold: ImageFont.FreeTypeFont,
) -> int:
    """计算 Span 组合的总宽度（不含行高）。"""
    w, _ = _cell_size(spans, font_reg, font_bold)
    return w
