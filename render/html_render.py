"""HTML 文档渲染（pytakumi，无浏览器）。

pytakumi 不解析 HTML 里的 ``<style>`` 标签，样式必须抽出来经
``stylesheets`` 参数传入才会生效；字体也必须先注册，否则中文是豆腐块。
"""
from __future__ import annotations

import logging
import os
import re
import threading
from typing import Any

from pytakumi import Renderer

from render.font import find_font_path

logger = logging.getLogger(__name__)

_STYLE_RE = re.compile(r"<style[^>]*>(.*?)</style>", re.DOTALL | re.IGNORECASE)

# HTML artifact 的 CSS 通常直接写 "Noto Sans CJK SC"，按名字注册才能命中。
_SYSTEM_CJK_FONTS: tuple[tuple[str, str], ...] = (
    ("Noto Sans CJK SC", "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
    ("WenQuanYi Micro Hei", "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"),
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
    for name, path in _SYSTEM_CJK_FONTS:
        if not os.path.exists(path):
            continue
        with open(path, "rb") as f:
            renderer.register_font(f.read(), name=name)
        registered = True
        break

    # 系统没有中文字体时，回退到插件自带字体，避免输出豆腐块。
    if not registered:
        fallback = find_font_path()
        if fallback:
            with open(fallback, "rb") as f:
                renderer.register_font(f.read(), name="Sarasa Mono SC")

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


def render_html(seg: Any) -> bytes:
    """把 HTML 文档渲染为 PNG。

    Args:
        seg: HtmlDoc 实例，含 code 属性。

    Returns:
        PNG 图片字节。
    """
    html: str = getattr(seg, "code", "")
    styles = extract_styles(html)
    with _lock:
        renderer = _renderer
        width = _width
        if renderer is None:
            raise RuntimeError("html_render 未初始化，先调用 init_html()")
        return renderer.render_html(
            html,
            width=width,
            stylesheets=[styles] if styles.strip() else None,
        )
