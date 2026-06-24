"""代码块渲染。

用 pygments 语法高亮 + pillow 绘制为 PNG，同时输出 .txt 原文。
"""
from __future__ import annotations

import os
from datetime import datetime

from PIL import ImageFont
from pygments import highlight
from pygments.formatters.img import ImageFormatter
from pygments.lexers import get_lexer_by_name, guess_lexer

from render.glyph import fallback_text, load_glyph_mapping


def render_code(
    codeblock: object,
    config: dict,
    data_dir: str,
) -> tuple[str, str]:
    """渲染代码块为 PNG 图片和 TXT 文本文件。

    Args:
        codeblock: CodeBlock 实例，含 lang 和 code 属性。
        config: 插件配置字典。
        data_dir: 插件数据目录路径。

    Returns:
        (png_path, txt_path) 渲染产物文件路径元组。
    """
    lang: str = getattr(codeblock, "lang", "") or ""
    code: str = getattr(codeblock, "code", "")

    glyph_mapping = load_glyph_mapping(config.get("字形映射", "{}"))
    font = _load_mono_font()

    code_for_glyph = fallback_text(code, glyph_mapping, font)

    # pygments 语法高亮 → 图片
    try:
        lexer = get_lexer_by_name(lang)
    except Exception:
        lexer = guess_lexer(code)
    formatter = ImageFormatter(
        style="material",
        font_size=14,
        line_numbers=False,
    )
    png_data = highlight(code_for_glyph, lexer, formatter)

    # 写入 PNG
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    temp_dir = os.path.join(data_dir, "temp")
    os.makedirs(temp_dir, exist_ok=True)
    png_path = os.path.join(temp_dir, f"code_{ts}.png")
    with open(png_path, "wb") as f:
        f.write(png_data)

    # 写入 TXT
    txt_path = os.path.join(temp_dir, f"code_{ts}.txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(code)

    return png_path, txt_path


def _load_mono_font() -> ImageFont.FreeTypeFont | None:
    """加载等宽字体，优先文泉驿微米黑等宽。

    Returns:
        PIL 字体对象，未找到合适字体返回 None。
    """
    candidate = "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"
    if os.path.exists(candidate):
        return ImageFont.truetype(candidate, 14)
    try:
        return ImageFont.truetype("DejaVuSansMono", 14)
    except (OSError, IOError):
        return ImageFont.load_default()
