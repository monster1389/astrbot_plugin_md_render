"""数学表达式渲染。

用 pillowlatex 渲染 LaTeX 表达式，合成到配置的背景色上输出 PNG。
行内 $...$ 和块级 $$...$$ 分别处理。
"""
from __future__ import annotations

import os
from datetime import datetime

from PIL import Image

from pillowlatex import RenderLaTeX


def _parse_color(value: str) -> str:
    """从 '#HEX (描述)' 格式的配置值中提取 hex 颜色。"""
    return value.split(" ")[0]


def _render_latex(latex_src: str, config: dict, data_dir: str) -> str:
    """核心渲染逻辑：LaTeX 源码 → 合成背景色 PNG。

    pillowlatex 渲染黑字透明背景，用 alpha 通道将文字着色后
    合成到配置的背景色上，确保 QQ 可正常显示。

    Args:
        latex_src: LaTeX 源码（不含 $ 或 \\[ \\] 分隔符）。
        config: 插件配置字典。
        data_dir: 插件数据目录路径。

    Returns:
        png_path 渲染产物文件路径。
    """
    rendered = RenderLaTeX(latex_src)
    render_img = rendered.img  # RGBA，黑字透明背景

    font_color = _parse_color(config.get("字体颜色", "#9CDCFE (浅蓝)"))
    bg_color = _parse_color(config.get("背景颜色", "#1E1E1E (VS Code 深色)"))

    w, h = render_img.size
    pad = 10

    result = Image.new("RGB", (w + pad * 2, h + pad * 2), bg_color)
    text_layer = Image.new("RGB", render_img.size, font_color)
    result.paste(text_layer, (pad, pad), render_img.split()[3])

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    temp_dir = os.path.join(data_dir, "temp")
    os.makedirs(temp_dir, exist_ok=True)
    png_path = os.path.join(temp_dir, f"expr_{ts}.png")
    result.save(png_path)
    return png_path


def render_inline_expr(
    expr: object,
    config: dict,
    data_dir: str,
) -> str:
    """渲染行内表达式 $...$ 为 PNG。

    Args:
        expr: InlineExpr 实例，含 expr 属性（不含 $ 分隔符）。
        config: 插件配置字典。
        data_dir: 插件数据目录路径。

    Returns:
        png_path 渲染产物文件路径。
    """
    latex = getattr(expr, "expr", "")
    return _render_latex(latex, config, data_dir)


def render_block_expr(
    expr: object,
    config: dict,
    data_dir: str,
) -> str:
    """渲染块级表达式 $$...$$ 为 PNG。

    Args:
        expr: BlockExpr 实例，含 expr 属性（不含 \\[ \\] 分隔符）。
        config: 插件配置字典。
        data_dir: 插件数据目录路径。

    Returns:
        png_path 渲染产物文件路径。
    """
    latex = getattr(expr, "expr", "")
    return _render_latex(latex, config, data_dir)
