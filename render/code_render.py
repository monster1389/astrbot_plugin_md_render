"""代码块渲染。

用 pygments 语法高亮 + pillow 绘制为 PNG，同时输出 .md 围栏代码块。
"""
from __future__ import annotations

import io
import logging
from typing import Any

from PIL import Image, ImageFont
from pygments import highlight
from pygments.formatters.img import STYLES, FontManager, ImageFormatter
from pygments.lexers import TextLexer, get_lexer_by_name
from pygments.util import ClassNotFound

from render.font import find_font_spec

logger = logging.getLogger(__name__)

_FONT_SIZE = 38  # 18pt @ 150 DPI (150/72 * 18 ≈ 38)


class _FaceFontManager(FontManager):
    """固定 face 的 pygments 字体管理器，四种样式共用同一字体。

    pygments 只把路径交给 ImageFont.truetype，默认取 ttc 的第 0 个 face；
    这里显式带上 index，才能拿到等宽的中文 face。
    """

    def __init__(self, path: str, size: int, index: int) -> None:
        """加载指定 face。

        Args:
            path: 字体文件路径。
            size: 字号（像素）。
            index: ttc 集合内的 face 序号。
        """
        self.font_name = path
        self.font_size = size
        self.fonts: dict[str, ImageFont.FreeTypeFont] = {}
        self.encoding = None
        self.variable = True
        font = ImageFont.truetype(path, size, index=index)
        for style in STYLES:
            self.fonts[style] = font


class _FaceFormatter(ImageFormatter):
    """支持 ttc face index 的 ImageFormatter。

    父类初始化时按路径建字体管理器（落到第 0 个 face），随后用同一路径
    重建一次，把 face 序号带进去。
    """

    def __init__(
        self,
        *,
        font_name: str,
        font_size: int,
        face_index: int,
        **options: Any,
    ) -> None:
        """初始化并替换字体管理器。

        Args:
            font_name: 字体文件路径。
            font_size: 字号（像素）。
            face_index: ttc 集合内的 face 序号。
            options: 其余 pygments ImageFormatter 选项。
        """
        super().__init__(font_name=font_name, font_size=font_size, **options)
        self.fonts = _FaceFontManager(font_name, font_size, face_index)
        self.fontw, self.fonth = self.fonts.get_char_size()


def render_code(
    codeblock: object,
) -> bytes:
    """渲染代码块为 PNG 图片。

    Args:
        codeblock: CodeBlock 实例，含 lang 和 code 属性。

    Returns:
        PNG 图片字节。

    Raises:
        RuntimeError: 系统与插件目录都没有可用字体。
    """
    lang: str = getattr(codeblock, "lang", "") or ""
    code: str = getattr(codeblock, "code", "")

    spec = find_font_spec()
    if spec is None:
        raise RuntimeError("未找到可用字体，无法渲染代码块")

    # pygments 语法高亮 → 图片
    try:
        lexer = get_lexer_by_name(lang)
    except ClassNotFound:
        # 不猜：guess_lexer 会把 mermaid 认成 ECLLexer、调用树认成 ScdocLexer，
        # 出来的颜色与内容无关，不如按纯文本渲染。
        logger.warning("代码块语言 '%s' 无对应 lexer，按纯文本渲染", lang)
        lexer = TextLexer()
    formatter = _FaceFormatter(
        style="material",
        font_size=_FONT_SIZE,
        line_numbers=False,
        image_pad=27,  # 10pt @ 150 DPI
        line_pad=8,    # 4px @ 150 DPI
        font_name=spec.path,
        face_index=spec.index,
    )
    png_data = highlight(code, lexer, formatter)

    # 转自适应调色板以压缩体积（语法高亮颜色数有限，128 色足够无损）
    img = Image.open(io.BytesIO(png_data))
    img = img.convert("P", palette=Image.Palette.ADAPTIVE, colors=128)
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)

    return buf.getvalue()
