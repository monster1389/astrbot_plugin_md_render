"""表格渲染。

用 matplotlib.table 将 markdown 表格渲染为深色主题 PNG。
"""
from __future__ import annotations

import os
from datetime import datetime

import matplotlib
from PIL import ImageFont

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from render.glyph import fallback_text, load_glyph_mapping


def _parse_color(value: str) -> str:
    """从 '#HEX (描述)' 格式的配置值中提取 hex 颜色。

    Args:
        value: 形如 '#9CDCFE (浅蓝)' 的字符串。

    Returns:
        纯 hex 字符串，如 '#9CDCFE'。
    """
    return value.split(" ")[0]


def render_table(
    table: object,
    config: dict,
    data_dir: str,
) -> str:
    """渲染表格为 PNG 图片。

    Args:
        table: Table 实例，含 headers 和 rows 属性。
        config: 插件配置字典。
        data_dir: 插件数据目录路径。

    Returns:
        png_path 渲染产物文件路径。
    """
    headers: list[str] = getattr(table, "headers", [])
    rows: list[list[str]] = getattr(table, "rows", [])

    font_color = _parse_color(config.get("字体颜色", "#9CDCFE (浅蓝)"))
    bg_color = _parse_color(config.get("背景颜色", "#1E1E1E (VS Code 深色)"))
    glyph_mapping = load_glyph_mapping(config.get("字形映射", "{}"))
    font = _load_table_font()

    # 字形回退
    headers = [fallback_text(h, glyph_mapping, font) for h in headers]
    rows = [[fallback_text(cell, glyph_mapping, font) for cell in row] for row in rows]

    n_rows = len(rows) + 1  # +1 表头行
    n_cols = max(len(headers), 1)

    fig, ax = plt.subplots(figsize=(n_cols * 2.5, n_rows * 0.45 + 0.3))
    fig.patch.set_facecolor(bg_color)

    cell_text = [headers] + rows
    tbl = ax.table(
        cellText=cell_text,
        cellLoc="center",
        loc="center",
    )
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(11)

    for (r, c), cell in tbl.get_celld().items():
        cell.set_facecolor(bg_color)
        cell.set_edgecolor(font_color)
        cell.set_text_props(color=font_color, fontname="sans-serif")
        if r == 0:
            cell.set_text_props(weight="bold", color=font_color)

    ax.axis("off")
    ax.set_facecolor(bg_color)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    temp_dir = os.path.join(data_dir, "temp")
    os.makedirs(temp_dir, exist_ok=True)
    png_path = os.path.join(temp_dir, f"table_{ts}.png")
    plt.savefig(png_path, bbox_inches="tight", facecolor=bg_color, dpi=150)
    plt.close(fig)

    return png_path


def _load_table_font() -> ImageFont.FreeTypeFont | None:
    """加载表格用字体，优先中文字体。

    Returns:
        PIL 字体对象，未找到返回 None。
    """
    candidate = "/usr/share/fonts/truetype/wqy/wqy-microhei-mono.ttc"
    if os.path.exists(candidate):
        return ImageFont.truetype(candidate, 14)
    try:
        return ImageFont.truetype("DejaVuSansMono", 14)
    except (OSError, IOError):
        return None
