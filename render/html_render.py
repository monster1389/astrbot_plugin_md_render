"""HTML 文档渲染（pytakumi，无浏览器）。

pytakumi 不解析 HTML 里的 ``<style>`` 标签，样式必须抽出来经 ``stylesheets``
参数传入才会生效；字体由 ``render.renderer.init()`` 统一注册，否则中文是豆腐块。

文档的底色与字体由文档自身的样式决定，插件不覆盖——这是「渲染别人的文档」
该有的语义。
"""
from __future__ import annotations

import re
from typing import Any

from render import renderer

_STYLE_RE = re.compile(r"<style[^>]*>(.*?)</style>", re.DOTALL | re.IGNORECASE)


def extract_styles(html: str) -> str:
    """抽取 HTML 中所有 ``<style>`` 块的内容。

    Args:
        html: 完整 HTML 文本。

    Returns:
        拼接后的 CSS 文本；没有 style 块时返回空串。
    """
    return "\n".join(match.group(1) for match in _STYLE_RE.finditer(html))


def render_html(seg: Any) -> bytes:
    """把 HTML 文档渲染为 PNG。

    Args:
        seg: HtmlDoc 实例，含 code 属性。

    Returns:
        PNG 图片字节。
    """
    html: str = getattr(seg, "code", "")
    return renderer.render_page(
        html, extract_styles(html), width=renderer.html_width()
    )
