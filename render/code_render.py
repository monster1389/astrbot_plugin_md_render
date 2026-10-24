"""代码块渲染。

高亮仍由 pygments 负责：``HtmlFormatter(nowrap=True)`` 产出带 CSS 类的 span，
配色由同一 formatter 的 ``get_style_defs`` 生成，样式只有一处来源；图片交给
``render.renderer`` 的唯一出图口（pytakumi，无浏览器）。

宽度按内容自适应，超过上限由 CSS ``max-width`` 折行——一次渲染即可，不需要
先量宽度再来一遍。
"""
from __future__ import annotations

from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import TextLexer, get_lexer_by_name
from pygments.util import ClassNotFound

from astrbot.api import logger
from render import renderer
from render.font import find_font_spec, font_family
from render.theme import BG

_STYLE = "material"
_FONT_SIZE = 38
_PAD = 27
_LINE_HEIGHT = 53  # 与 pillow 版一致：字号 38 的字高 + 8px 行间距
_TAB_SIZE = 4
_MAX_WIDTH = 1080  # 画布宽度上限（含两侧内边距），超出即折行

# 空代码块要占一行，否则图片只剩内边距
_BLANK = "&#8203;"


def _css(family: str) -> str:
    """拼出代码块样式表。

    Args:
        family: 代码字体族名。

    Returns:
        CSS 文本。
    """
    stack = f"'{family}', monospace" if family else "monospace"
    return f"""
html,body{{margin:0;padding:0;background:{BG};}}
pre.hl{{margin:0;padding:{_PAD}px;font-family:{stack};
  font-size:{_FONT_SIZE}px;line-height:{_LINE_HEIGHT}px;tab-size:{_TAB_SIZE};
  white-space:pre-wrap;overflow-wrap:anywhere;
  max-width:{_MAX_WIDTH}px;background:{BG};}}
pre.hl span[class]{{font-style:normal;font-weight:normal;}}
"""


def _lexer(lang: str):
    """按语言标注取 lexer。

    Args:
        lang: 代码块语言标注，空串表示未标注。

    Returns:
        pygments lexer；没有对应 lexer 时为纯文本 lexer。
    """
    try:
        return get_lexer_by_name(lang)
    except ClassNotFound:
        # 不猜：guess_lexer 会把 mermaid 认成 ECLLexer、调用树认成 ScdocLexer，
        # 出来的颜色与内容无关，不如按纯文本渲染。
        logger.warning("代码块语言 '%s' 无对应 lexer，按纯文本渲染", lang)
        return TextLexer()


def build_page(code: str, lang: str) -> tuple[str, str]:
    """把代码块转成待渲染的 HTML 与样式表。

    pygments 的 ``nowrap`` 输出恒带一个尾部换行，在 ``<pre>`` 里会多渲染出
    一行空白；代码首尾的空行 pillow 版也是吞掉的，这里同样剥掉。

    Args:
        code: 代码原文。
        lang: 代码块语言标注，空串表示未标注。

    Returns:
        (HTML 文档, CSS 文本)。

    Raises:
        RuntimeError: 系统与插件目录都没有可用字体。
    """
    spec = find_font_spec()
    if spec is None:
        raise RuntimeError("未找到可用字体，无法渲染代码块")
    formatter = HtmlFormatter(style=_STYLE, nowrap=True, cssclass="hl")
    body = highlight(code.rstrip("\n"), _lexer(lang), formatter).rstrip("\n")
    page = f'<html><body><pre class="hl">{body or _BLANK}</pre></body></html>'
    return page, formatter.get_style_defs(".hl") + _css(font_family(spec) or "")


def render_code(seg: object) -> bytes:
    """渲染代码块为 PNG 图片。

    Args:
        seg: CodeBlock 实例，含 lang 和 code 属性。

    Returns:
        PNG 图片字节。

    Raises:
        RuntimeError: 系统与插件目录都没有可用字体。
    """
    lang: str = getattr(seg, "lang", "") or ""
    page, css = build_page(getattr(seg, "code", ""), lang)
    return renderer.render_page(page, css)
