"""版面 —— 自绘图的装配与编码。

三种自绘图（代码块、表格、公式）共用的底色、字号阶梯、调色板、页面骨架、
字体栈与宽度上限都在这里；改一处，三张图同时对齐。渲染器只交「片段 + CSS」
或「一张带透明通道的图」，装成 PNG 由这里负责。

不管出图后端（takumi / typst / mermaid.ink），也不管量化与临时文件：量化在
``render.png`` / chain 出口，落盘在 ``render.tempstore``。HTML 文档不走这里——
它的底色与字体由文档自身样式决定。
"""
from __future__ import annotations

from typing import Literal

from render import font, renderer

# 所有自绘图的底色；与 mermaid.ink 请求的 bgColor 一致
BG = "#1E1E1E"

# 自绘图画布宽度上限（像素）：代码块由 CSS 折行，表格由列宽压缩
MAX_WIDTH = 1080

# 字号阶梯（像素）：代码块最大、表格最小，公式另有一套基准
CODE_SIZE = 38
TABLE_SIZE = 34
EXPR_SIZE = 50

# 调色板：自绘图共用的文字与装饰色。代码高亮色不在此列，来自 pygments 主题。
TEXT = "#dcdce6"
HEADER_BG = "#282841"
GRID = "#50506e"
BOLD = "#ffd2a0"
ITALIC = "#b4d2f0"
STRIKE = "#8c8c96"
CODE_TEXT = "#96dc96"
CODE_BG = "#323246"
LINK = "#78b4ff"
EXPR_COLOR = "#9CDCFE"


def font_stack(kind: Literal["mono", "body"]) -> str:
    """自绘图的 CSS 字体栈。

    Args:
        kind: ``mono`` 用于代码块，``body`` 用于表格与页面正文。

    Returns:
        可直接写进 ``font-family`` 的值；没有字体时退回通用族。
    """
    if kind == "mono":
        family = font.font_family(font.find_font_spec())
        return f"'{family}', monospace" if family else "monospace"
    family = font.body_family()
    return f'"{family}"' if family else "sans-serif"


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


def fragment(
    body: str,
    css: str | None = None,
    *,
    width: int | None = None,
) -> bytes:
    """把 HTML 片段装成页面并渲染为 PNG。

    Args:
        body: 页面主体 HTML 片段。
        css: 样式表文本；为空时不传。
        width: 渲染宽度（像素）；None 表示按内容自适应。

    Returns:
        PNG 图片字节。
    """
    return renderer.render_page(page(body), css, width=width)
