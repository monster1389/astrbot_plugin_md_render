"""全局视觉主题。

自绘图片（代码块、表格、公式）共用的底色与页面骨架。HTML 文档不在此列：
它的底色与字体由文档自身的样式决定，插件不覆盖。
"""
from __future__ import annotations

# 所有自绘图片的背景色；与 mermaid.ink 请求的 bgColor 一致
BG = "#1E1E1E"


def page(body: str) -> str:
    """把 HTML 片段包成完整文档，统一去掉外边距并铺上底色。

    Args:
        body: 页面主体 HTML 片段。

    Returns:
        完整 HTML 文档字符串。
    """
    return (
        f'<html><body style="margin:0;padding:0;background:{BG}">'
        f"{body}</body></html>"
    )
