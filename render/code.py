"""代码块渲染。

用 pygments 语法高亮 + pillow 绘制为 PNG，同时输出 .md 围栏代码块。
"""
from __future__ import annotations

import io
import logging

from PIL import Image

from pygments import highlight
from pygments.formatters.img import ImageFormatter
from pygments.lexers import get_lexer_by_name, guess_lexer

from render.utils import RenderConfig, find_font_path

logger = logging.getLogger(__name__)


def render_code(
    codeblock: object,
    cfg: RenderConfig,
    data_dir: str,
) -> tuple[bytes, str]:
    """渲染代码块为 PNG 图片和 MD 围栏代码文本。

    Args:
        codeblock: CodeBlock 实例，含 lang 和 code 属性。
        cfg: 渲染配置。
        data_dir: 插件数据目录路径。

    Returns:
        (png_bytes, md_text) PNG 图片字节和 MD 围栏代码文本。
    """
    lang: str = getattr(codeblock, "lang", "") or ""
    code: str = getattr(codeblock, "code", "")

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
        font_name=find_font_path(data_dir) or "DejaVuSansMono",
    )
    png_data = highlight(code, lexer, formatter)

    # 转自适应调色板以压缩体积（语法高亮颜色数有限，128 色足够无损）
    img = Image.open(io.BytesIO(png_data))
    img = img.convert("P", palette=Image.Palette.ADAPTIVE, colors=128)
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    png_data = buf.getvalue()

    return png_data, f"```{lang}\n{code}\n```"


