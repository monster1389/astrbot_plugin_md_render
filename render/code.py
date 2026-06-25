"""代码块渲染。

用 pygments 语法高亮 + pillow 绘制为 PNG，同时输出 .txt 原文。
"""
from __future__ import annotations

import logging

from PIL import ImageFont
from pygments import highlight
from pygments.formatters.img import ImageFormatter
from pygments.lexers import get_lexer_by_name, guess_lexer

from render.glyph import fallback_text
from render.utils import RenderConfig, build_temp_path, find_font_path

logger = logging.getLogger(__name__)


def render_code(
    codeblock: object,
    cfg: RenderConfig,
    data_dir: str,
) -> tuple[str, str]:
    """渲染代码块为 PNG 图片和 TXT 文本文件。

    Args:
        codeblock: CodeBlock 实例，含 lang 和 code 属性。
        cfg: 渲染配置。
        data_dir: 插件数据目录路径。

    Returns:
        (png_path, txt_path) 渲染产物文件路径元组。
    """
    lang: str = getattr(codeblock, "lang", "") or ""
    code: str = getattr(codeblock, "code", "")

    mono_path = find_font_path(data_dir)
    font = ImageFont.truetype(mono_path, 14) if mono_path else ImageFont.load_default()

    code_for_glyph = fallback_text(code, cfg.glyph_mapping, font)

    # pygments 语法高亮 → 图片
    try:
        lexer = get_lexer_by_name(lang)
    except Exception:
        logger.warning("代码块语言 '%s' 无对应 lexer，已回退到 guess_lexer", lang)
        lexer = guess_lexer(code)
    formatter = ImageFormatter(
        style="material",
        font_size=38,  # 18pt @ 150 DPI (150/72 * 18 ≈ 38)
        line_numbers=False,
        image_pad=27,  # 10pt @ 150 DPI
        line_pad=8,    # 4px @ 150 DPI
        font_name=mono_path or "DejaVuSansMono",
    )
    png_data = highlight(code_for_glyph, lexer, formatter)

    # 写入 PNG
    png_path = build_temp_path(data_dir, "code", ".png")
    with open(png_path, "wb") as f:
        f.write(png_data)

    # 写入 MD
    md_path = build_temp_path(data_dir, "code", ".md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(f"```{lang}\n{code}\n```")

    return png_path, md_path


