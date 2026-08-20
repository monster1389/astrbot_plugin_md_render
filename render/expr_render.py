"""数学表达式渲染。

用 pillowlatex 渲染 LaTeX 表达式，合成到配置的背景色上输出 PNG。
行内 $...$ 与块级 $$...$$ 共用同一渲染路径，差异在 chain 层区分。
"""
from __future__ import annotations

from io import BytesIO

from PIL import Image

from pillowlatex import GetLaTeXObjs, RenderLaTeX

# VS Code dark theme 配色
_FONT_COLOR = "#9CDCFE"
_BG_COLOR = "#1E1E1E"


def render_expr(expr: object) -> bytes:
    """渲染数学表达式为 PNG。

    pillowlatex 渲染黑字透明背景，用 alpha 通道将文字着色后
    合成到配置的背景色上，确保 QQ 可正常显示。

    Args:
        expr: InlineExpr/BlockExpr 实例，含 expr 属性（不含 $ 分隔符）。

    Returns:
        渲染产物 PNG 字节串。
    """
    latex_src = getattr(expr, "expr", "")
    objs = GetLaTeXObjs(latex_src)
    rendered = RenderLaTeX(objs)
    render_img = rendered.img  # RGBA，黑字透明背景

    w, h = render_img.size
    pad = 10

    result = Image.new("RGB", (w + pad * 2, h + pad * 2), _BG_COLOR)
    text_layer = Image.new("RGB", render_img.size, _FONT_COLOR)
    result.paste(text_layer, (pad, pad), render_img.split()[3])

    buf = BytesIO()
    result.save(buf, "PNG", optimize=True)
    return buf.getvalue()
