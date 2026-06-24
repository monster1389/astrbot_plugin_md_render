"""表格渲染。

用 matplotlib.table 将 markdown 表格渲染为深色主题 PNG。
超长文本自动换行，列宽按内容自适应，上限 5 英寸/列。
"""
from __future__ import annotations

import logging

import matplotlib
from matplotlib.font_manager import FontProperties
from PIL import ImageFont

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from render.glyph import fallback_text
from render.utils import RenderConfig, build_temp_path, find_font_path

logger = logging.getLogger(__name__)

_MAX_COL_INCHES = 5.0
_LINE_HEIGHT = 0.22
_CELL_FONTSIZE = 11


def _wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width_px: float) -> tuple[str, int]:
    """按像素宽度折行，返回 (带换行符的文本, 行数)。

    Args:
        text: 原始文本。
        font: 测量用字体。
        max_width_px: 每行最大像素宽度。

    Returns:
        (折行后文本, 总行数)。
    """
    if font.getlength(text) <= max_width_px:
        return text, 1

    lines: list[str] = []
    cur = ""
    for ch in text:
        if font.getlength(cur + ch) > max_width_px and cur:
            lines.append(cur)
            cur = ch
        else:
            cur += ch
    if cur:
        lines.append(cur)
    return "\n".join(lines), len(lines)


def render_table(
    table: object,
    cfg: RenderConfig,
    data_dir: str,
) -> str:
    """渲染表格为 PNG 图片。

    Args:
        table: Table 实例，含 headers 和 rows 属性。
        cfg: 渲染配置。
        data_dir: 插件数据目录路径。

    Returns:
        png_path 渲染产物文件路径。
    """
    headers: list[str] = getattr(table, "headers", [])
    rows: list[list[str]] = getattr(table, "rows", [])

    font_path = find_font_path(data_dir)
    if font_path is None:
        logger.warning("未找到 CJK 字体，表格中文可能显示为豆腐块")
    font = ImageFont.truetype(font_path, 14) if font_path else ImageFont.load_default()

    # 字形回退
    headers = [fallback_text(h, cfg.glyph_mapping, font) for h in headers]
    rows = [[fallback_text(cell, cfg.glyph_mapping, font) for cell in row] for row in rows]

    n_rows = len(rows) + 1
    n_cols = max(len(headers), 1)
    cell_text = [headers] + rows

    measure_font = ImageFont.truetype(font_path, _CELL_FONTSIZE) if font_path else ImageFont.load_default()

    # 1) 测量每列原始文本宽度，转为英寸
    raw_widths: list[float] = []
    for c in range(n_cols):
        max_px = 0.0
        for r in range(n_rows):
            w = measure_font.getlength(cell_text[r][c])
            if w > max_px:
                max_px = w
        raw_widths.append(max_px / 90 + 0.6)

    # 2) 限制列宽上限
    col_widths = [min(w, _MAX_COL_INCHES) for w in raw_widths]

    # 3) 对超出列宽的单元格折行，同时记录每行最大行数
    row_lines: list[int] = []
    for r in range(n_rows):
        max_lines = 1
        for c in range(n_cols):
            avail_px = (col_widths[c] - 0.6) * 90
            wrapped, lines = _wrap_text(cell_text[r][c], measure_font, max(avail_px, 1))
            cell_text[r][c] = wrapped
            if lines > max_lines:
                max_lines = lines
        row_lines.append(max_lines)

    # 4) 计算画布尺寸
    fig_width = sum(col_widths)
    fig_height = sum(rl * _LINE_HEIGHT for rl in row_lines) + 0.3

    fig, ax = plt.subplots(figsize=(fig_width, fig_height))
    fig.patch.set_facecolor(cfg.bg_color)
    ax.set_facecolor(cfg.bg_color)

    tbl = ax.table(
        cellText=cell_text,
        cellLoc="center",
        loc="center",
        colWidths=[w / fig_width for w in col_widths],
    )
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(_CELL_FONTSIZE)

    font_prop = FontProperties(fname=font_path) if font_path else None

    for (r, c), cell in tbl.get_celld().items():
        cell.set_facecolor(cfg.bg_color)
        cell.set_edgecolor(cfg.font_color)
        if r == 0 and font_prop:
            cell.set_text_props(weight="bold", color=cfg.font_color, fontproperties=font_prop)
        elif r == 0:
            cell.set_text_props(weight="bold", color=cfg.font_color)
        elif font_prop:
            cell.set_text_props(color=cfg.font_color, fontproperties=font_prop)
        else:
            cell.set_text_props(color=cfg.font_color)

    ax.axis("off")

    png_path = build_temp_path(data_dir, "table", ".png")
    plt.savefig(png_path, bbox_inches="tight", facecolor=cfg.bg_color, dpi=150)
    plt.close(fig)

    return png_path
