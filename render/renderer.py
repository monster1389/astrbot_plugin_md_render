"""takumi 渲染器的唯一出图口（无浏览器）。

代码块、表格、HTML 文档共用同一个 ``Renderer``：字体只注册一份，二十来兆的
CJK 集合不必常驻两份。渲染过程持锁，因为 takumi 渲染器的线程安全性未作保证。
"""
from __future__ import annotations

import threading

from pytakumi import Renderer

from render import font

_DEFAULT_WIDTH = 1000

_lock = threading.Lock()
_renderer: Renderer | None = None
_width = _DEFAULT_WIDTH


def init(data_dir: str | None, width: int = _DEFAULT_WIDTH) -> None:
    """发现字体、建渲染器、注册字体，并记录 HTML 文档的渲染宽度。

    只注册 ``font.font_files()`` 给出的文件（去重后通常就是一个 ttc）：
    字体是本插件最贵的常驻资源，重复注册同一文件纯属浪费。

    Args:
        data_dir: 插件数据目录路径，手动放置的字体在其 fonts/ 子目录。
        width: HTML 文档的渲染宽度（像素），高度按内容自适应。
    """
    global _renderer, _width
    font.init_font(data_dir)
    renderer = Renderer()
    for path in font.font_files():
        with open(path, "rb") as f:
            renderer.register_font(f.read())
    with _lock:
        _width = int(width)
        _renderer = renderer


def html_width() -> int:
    """返回 HTML 文档的渲染宽度。

    Returns:
        宽度像素数。
    """
    return _width


def render_page(
    html: str,
    css: str | None = None,
    *,
    width: int | None = None,
) -> bytes:
    """渲染一页 HTML 为 PNG。

    Args:
        html: 完整 HTML 文档或片段。
        css: 样式表文本；为空时不传。
        width: 渲染宽度（像素）；None 表示按内容自适应。

    Returns:
        PNG 图片字节。

    Raises:
        RuntimeError: 渲染器尚未初始化。
    """
    with _lock:
        renderer = _renderer
        if renderer is None:
            raise RuntimeError("renderer 未初始化，先调用 renderer.init()")
        return renderer.render_html(
            html,
            width=width,
            stylesheets=[css] if css and css.strip() else None,
        )
