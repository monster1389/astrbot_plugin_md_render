"""HTML 文档渲染（pytakumi，无浏览器）。

pytakumi 不解析 HTML 里的 ``<style>`` 标签，样式必须抽出来经
``stylesheets`` 参数传入才会生效；字体也必须先注册，否则中文是豆腐块。
"""
from __future__ import annotations

import os
import re
import threading
from typing import Any

from pytakumi import Renderer

from render.font import find_font_spec

_STYLE_RE = re.compile(r"<style[^>]*>(.*?)</style>", re.DOTALL | re.IGNORECASE)

# 系统 CJK 字体的 ttc：注册时不传 name，让 ttc 自带族名生效（JP/KR/SC/TC/HK
# 与各自的 Mono 变体共 10 个），HTML artifact 里的 font-family 才能点名到 SC。
# 传 name= 会把所有 face 归到一个名下，takumi 实际只用 face 0（日文字形）。
_SYSTEM_CJK_FONTS: tuple[str, ...] = (
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
)

_DEFAULT_WIDTH = 1000

_lock = threading.Lock()
_renderer: Renderer | None = None
_width = _DEFAULT_WIDTH


def init_html(width: int = _DEFAULT_WIDTH) -> None:
    """初始化 HTML 渲染器：记录渲染宽度并注册可用的中文字体。

    Args:
        width: 渲染宽度（像素），高度按内容自适应。
    """
    global _renderer, _width
    renderer = Renderer()
    registered = False
    # 只注册第一个可用的系统 CJK 字体：HTML artifact 的字体栈基本都点名 Noto，
    # 多注一份就是白占内存。
    for path in _SYSTEM_CJK_FONTS:
        if not os.path.exists(path):
            continue
        with open(path, "rb") as f:
            renderer.register_font(f.read())
        registered = True
        break

    # 系统没有中文字体时，回退到插件自带字体，避免输出豆腐块。
    if not registered:
        fallback = find_font_spec()
        if fallback:
            with open(fallback.path, "rb") as f:
                renderer.register_font(f.read())

    with _lock:
        _width = int(width)
        _renderer = renderer


def extract_styles(html: str) -> str:
    """抽取 HTML 中所有 ``<style>`` 块的内容。

    Args:
        html: 完整 HTML 文本。

    Returns:
        拼接后的 CSS 文本；没有 style 块时返回空串。
    """
    return "\n".join(match.group(1) for match in _STYLE_RE.finditer(html))


def render_document(html: str, width: int, css: str | None = None) -> bytes:
    """用共享渲染器渲染任意 HTML 文档。

    HTML 文档与表格共用一个 ``Renderer``：字体只注册一份，二十来兆不必常驻两份。
    渲染过程持锁，因为 takumi 渲染器的线程安全性未作保证。

    Args:
        html: 完整 HTML 文本。
        width: 渲染宽度（像素），高度按内容自适应。
        css: 样式表文本；为空时不传。

    Returns:
        PNG 图片字节。

    Raises:
        RuntimeError: 渲染器尚未初始化。
    """
    with _lock:
        renderer = _renderer
        if renderer is None:
            raise RuntimeError("html_render 未初始化，先调用 init_html()")
        return renderer.render_html(
            html,
            width=int(width),
            stylesheets=[css] if css and css.strip() else None,
        )


def render_html(seg: Any) -> bytes:
    """把 HTML 文档渲染为 PNG。

    Args:
        seg: HtmlDoc 实例，含 code 属性。

    Returns:
        PNG 图片字节。
    """
    html: str = getattr(seg, "code", "")
    return render_document(html, _width, extract_styles(html))
