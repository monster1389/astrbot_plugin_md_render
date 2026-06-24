"""表格渲染。

用 matplotlib.table 将 markdown 表格渲染为深色主题 PNG。
"""
from __future__ import annotations

import os
from datetime import datetime

import matplotlib
from matplotlib.font_manager import FontProperties
from PIL import ImageFont

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from render.glyph import fallback_text, load_glyph_mapping


def _parse_color(value: str) -> str:
    """从 '#HEX (描述)' 格式的配置值中提取 hex 颜色。"""
    return value.split(" ")[0]


def _find_font_path() -> str | None:
    """查找可用的 CJK 字体，退化为 DejaVu Sans Mono。

    Returns:
        字体文件路径，找不到返回 None。
    """
    candidates = [
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


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

    font_path = _find_font_path()
    font = ImageFont.truetype(font_path, 14) if font_path else ImageFont.load_default()

    # 字形回退
    headers = [fallback_text(h, glyph_mapping, font) for h in headers]
    rows = [[fallback_text(cell, glyph_mapping, font) for cell in row] for row in rows]

    n_rows = len(rows) + 1
    n_cols = max(len(headers), 1)

    fig, ax = plt.subplots(figsize=(n_cols * 2.5, n_rows * 0.45 + 0.3))
    fig.patch.set_facecolor(bg_color)
    ax.set_facecolor(bg_color)

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
        cell.set_facecolor(bg_color)
        cell.set_edgecolor(font_color)
        if r == 0 and font_prop:
            cell.set_text_props(weight="bold", color=font_color, fontproperties=font_prop)
        elif r == 0:
            cell.set_text_props(weight="bold", color=font_color)
        elif font_prop:
            cell.set_text_props(color=font_color, fontproperties=font_prop)
        else:
            cell.set_text_props(color=font_color)

    ax.axis("off")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    temp_dir = os.path.join(data_dir, "temp")
    os.makedirs(temp_dir, exist_ok=True)
    png_path = os.path.join(temp_dir, f"table_{ts}.png")
    plt.savefig(png_path, bbox_inches="tight", facecolor=bg_color, dpi=150)
    plt.close(fig)

    return png_path
