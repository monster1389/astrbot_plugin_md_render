"""表格渲染。

用 matplotlib.table 将 markdown 表格渲染为深色主题 PNG。
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

    fig, ax = plt.subplots(figsize=(n_cols * 2.5, n_rows * 0.45 + 0.3))
    fig.patch.set_facecolor(cfg.bg_color)
    ax.set_facecolor(cfg.bg_color)

    cell_text = [headers] + rows
    tbl = ax.table(
        cellText=cell_text,
        cellLoc="center",
        loc="center",
    )
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(11)

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
