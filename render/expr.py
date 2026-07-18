"""数学表达式渲染。

用 pillowlatex 渲染 LaTeX 表达式，合成到配置的背景色上输出 PNG。
行内 $...$ 和块级 $$...$$ 分别处理。
"""
from __future__ import annotations

from io import BytesIO

from PIL import Image

from pillowlatex import GetLaTeXObjs, RenderLaTeX

from render.utils import RenderConfig

# VS Code dark theme 配色
_FONT_COLOR = "#9CDCFE"
_BG_COLOR = "#1E1E1E"


def _render_latex(latex_src: str, cfg: RenderConfig, data_dir: str) -> bytes:
    """核心渲染逻辑：LaTeX 源码 → 合成背景色 PNG。

    pillowlatex 渲染黑字透明背景，用 alpha 通道将文字着色后
    合成到配置的背景色上，确保 QQ 可正常显示。

    Args:
        latex_src: LaTeX 源码（不含 $ 或 \\[ \\] 分隔符）。
        cfg: 渲染配置。
        data_dir: 插件数据目录路径。

    Returns:
        渲染产物 PNG 字节串。
    """
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


def render_inline_expr(
    expr: object,
    cfg: RenderConfig,
    data_dir: str,
) -> bytes:
    """渲染行内表达式 $...$ 为 PNG。

    Args:
        expr: InlineExpr 实例，含 expr 属性（不含 $ 分隔符）。
        cfg: 渲染配置。
        data_dir: 插件数据目录路径。

    Returns:
        渲染产物 PNG 字节串。
    """
    latex = getattr(expr, "expr", "")
    return _render_latex(latex, cfg, data_dir)


def render_block_expr(
    expr: object,
    cfg: RenderConfig,
    data_dir: str,
) -> bytes:
    """渲染块级表达式 $$...$$ 为 PNG。

    Args:
        expr: BlockExpr 实例，含 expr 属性（不含 \\[ \\] 分隔符）。
        cfg: 渲染配置。
        data_dir: 插件数据目录路径。

    Returns:
        渲染产物 PNG 字节串。
    """
    latex = getattr(expr, "expr", "")
    return _render_latex(latex, cfg, data_dir)
