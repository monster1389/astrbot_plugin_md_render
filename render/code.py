"""代码块渲染。

用 pygments 语法高亮 + pillow 绘制为 PNG，同时输出 .txt 原文。
"""
from __future__ import annotations

import logging
import os

from PIL import ImageFont
from pygments import highlight
from pygments.formatters.img import ImageFormatter
from pygments.lexers import get_lexer_by_name, guess_lexer

from render.glyph import fallback_text
from render.utils import RenderConfig, build_temp_path

logger = logging.getLogger(__name__)

def _find_mono_font_path(data_dir: str) -> str | None:
    """返回第一个可用的等宽字体路径，都不存在返回 None。

    优先使用捆绑的更纱等宽黑体（中英 2:1 等宽），
    不存在时 fallback 到系统 DejaVu Sans Mono。

    Args:
        data_dir: 插件数据目录路径。
    """
    candidates = [
        os.path.join(data_dir, "fonts", "SarasaMonoSC-Regular.ttf"),
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


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

    font = _load_mono_font(data_dir)

    code_for_glyph = fallback_text(code, cfg.glyph_mapping, font)

    # pygments 语法高亮 → 图片
    try:
        lexer = get_lexer_by_name(lang)
    except Exception:
        logger.warning("代码块语言 '%s' 无对应 lexer，已回退到 guess_lexer", lang)
        lexer = guess_lexer(code)
    formatter = ImageFormatter(
        style="material",
        font_size=14,
        line_numbers=False,
        font_name=_find_mono_font_path(data_dir) or "DejaVuSansMono",
    )
    png_data = highlight(code_for_glyph, lexer, formatter)

    # 写入 PNG
    png_path = build_temp_path(data_dir, "code", ".png")
    with open(png_path, "wb") as f:
        f.write(png_data)

    # 写入 TXT
    txt_path = build_temp_path(data_dir, "code", ".txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(code)

    return png_path, txt_path


def _load_mono_font(data_dir: str) -> ImageFont.FreeTypeFont | None:
    """加载等宽字体用于字形检测。

    Args:
        data_dir: 插件数据目录路径。

    Returns:
        PIL 字体对象，未找到合适字体返回 None。
    """
    path = _find_mono_font_path(data_dir)
    if path:
        return ImageFont.truetype(path, 14)
    return ImageFont.load_default()
