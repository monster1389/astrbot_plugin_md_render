"""数学表达式渲染。

用 pillowlatex 渲染 LaTeX 表达式，合成到配置的背景色上输出 PNG。
行内 $...$ 和块级 $$...$$ 分别处理。
"""
from __future__ import annotations

from PIL import Image, ImageFont

from pillowlatex import RenderLaTeX

from render.glyph import fallback_text
from render.utils import RenderConfig, build_temp_path, find_font_path


def _render_latex(latex_src: str, cfg: RenderConfig, data_dir: str) -> str:
    """核心渲染逻辑：LaTeX 源码 → 合成背景色 PNG。

    pillowlatex 渲染黑字透明背景，用 alpha 通道将文字着色后
    合成到配置的背景色上，确保 QQ 可正常显示。

    Args:
        latex_src: LaTeX 源码（不含 $ 或 \\[ \\] 分隔符）。
        cfg: 渲染配置。
        data_dir: 插件数据目录路径。

    Returns:
        png_path 渲染产物文件路径。
    """
    # 字形回退
    font_path = find_font_path()
    if cfg.glyph_mapping and font_path:
        font = ImageFont.truetype(font_path, size=20)
        latex_src = fallback_text(latex_src, cfg.glyph_mapping, font)

    rendered = RenderLaTeX(latex_src)
    render_img = rendered.img  # RGBA，黑字透明背景

    w, h = render_img.size
    pad = 10

    result = Image.new("RGB", (w + pad * 2, h + pad * 2), cfg.bg_color)
    text_layer = Image.new("RGB", render_img.size, cfg.font_color)
    result.paste(text_layer, (pad, pad), render_img.split()[3])

    png_path = build_temp_path(data_dir, "expr", ".png")
    result.save(png_path)
    return png_path


def render_inline_expr(
    expr: object,
    cfg: RenderConfig,
    data_dir: str,
) -> str:
    """渲染行内表达式 $...$ 为 PNG。

    Args:
        expr: InlineExpr 实例，含 expr 属性（不含 $ 分隔符）。
        cfg: 渲染配置。
        data_dir: 插件数据目录路径。

    Returns:
        png_path 渲染产物文件路径。
    """
    latex = getattr(expr, "expr", "")
    return _render_latex(latex, cfg, data_dir)


def render_block_expr(
    expr: object,
    cfg: RenderConfig,
    data_dir: str,
) -> str:
    """渲染块级表达式 $$...$$ 为 PNG。

    Args:
        expr: BlockExpr 实例，含 expr 属性（不含 \\[ \\] 分隔符）。
        cfg: 渲染配置。
        data_dir: 插件数据目录路径。

    Returns:
        png_path 渲染产物文件路径。
    """
    latex = getattr(expr, "expr", "")
    return _render_latex(latex, cfg, data_dir)
