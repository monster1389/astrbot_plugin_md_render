"""代码块渲染。

用 pygments 语法高亮 + pillow 绘制为 PNG，同时输出 .md 围栏代码块。
"""
from __future__ import annotations

import io
import logging

from PIL import Image
from pygments import highlight
from pygments.formatters.img import ImageFormatter
from pygments.lexers import TextLexer, get_lexer_by_name
from pygments.util import ClassNotFound

from render.font import find_font_path

logger = logging.getLogger(__name__)


def render_code(
    codeblock: object,
) -> bytes:
    """渲染代码块为 PNG 图片。

    Args:
        codeblock: CodeBlock 实例，含 lang 和 code 属性。

    Returns:
        PNG 图片字节。
    """
    lang: str = getattr(codeblock, "lang", "") or ""
    code: str = getattr(codeblock, "code", "")

    # pygments 语法高亮 → 图片
    try:
        lexer = get_lexer_by_name(lang)
    except ClassNotFound:
        # 不猜：guess_lexer 会把 mermaid 认成 ECLLexer、调用树认成 ScdocLexer，
        # 出来的颜色与内容无关，不如按纯文本渲染。
        logger.warning("代码块语言 '%s' 无对应 lexer，按纯文本渲染", lang)
        lexer = TextLexer()
    formatter = ImageFormatter(
        style="material",
        font_size=38,  # 18pt @ 150 DPI (150/72 * 18 ≈ 38)
        line_numbers=False,
        image_pad=27,  # 10pt @ 150 DPI
        line_pad=8,    # 4px @ 150 DPI
        font_name=find_font_path() or "DejaVuSansMono",
    )
    png_data = highlight(code, lexer, formatter)

    # 转自适应调色板以压缩体积（语法高亮颜色数有限，128 色足够无损）
    img = Image.open(io.BytesIO(png_data))
    img = img.convert("P", palette=Image.Palette.ADAPTIVE, colors=128)
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)

    return buf.getvalue()


