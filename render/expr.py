"""数学表达式渲染。

用 pillowlatex 渲染 LaTeX 表达式为 PNG。
行内 $...$ 和块级 $$...$$ 分别处理。
"""
from __future__ import annotations

import os
from datetime import datetime

import pillowlatex


def _render_latex(latex_src: str, config: dict, data_dir: str) -> str:
    """核心渲染逻辑：LaTeX 源码 → PNG。

    Args:
        latex_src: 完整 LaTeX 源码。
        config: 插件配置字典。
        data_dir: 插件数据目录路径。

    Returns:
        png_path 渲染产物文件路径。
    """
    img = pillowlatex.render(latex_src)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    temp_dir = os.path.join(data_dir, "temp")
    os.makedirs(temp_dir, exist_ok=True)
    png_path = os.path.join(temp_dir, f"expr_{ts}.png")
    img.save(png_path)
    return png_path


def render_inline_expr(
    expr: object,
    config: dict,
    data_dir: str,
) -> str:
    """渲染行内表达式 $...$ 为 PNG。

    Args:
        expr: InlineExpr 实例，含 expr 属性。
        config: 插件配置字典。
        data_dir: 插件数据目录路径。

    Returns:
        png_path 渲染产物文件路径。
    """
    latex = getattr(expr, "expr", "")
    return _render_latex(f"${latex}$", config, data_dir)


def render_block_expr(
    expr: object,
    config: dict,
    data_dir: str,
) -> str:
    """渲染块级表达式 $$...$$ 为 PNG。

    Args:
        expr: BlockExpr 实例，含 expr 属性。
        config: 插件配置字典。
        data_dir: 插件数据目录路径。

    Returns:
        png_path 渲染产物文件路径。
    """
    latex = getattr(expr, "expr", "")
    return _render_latex(f"\\[{latex}\\]", config, data_dir)
