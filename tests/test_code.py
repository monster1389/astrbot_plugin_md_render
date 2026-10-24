"""代码块渲染测试（pygments 高亮 + pytakumi 出图）。"""
import io
from unittest.mock import patch

import pytest
from PIL import Image

from render import canvas, renderer
from render.code_render import build_page, render_code
from render.parser import CodeBlock


@pytest.fixture(scope="module", autouse=True)
def _init() -> None:
    """代码块走共享渲染器，测试前先初始化。"""
    renderer.init(None, 1000)


class TestBuildPage:
    def test_uses_pygments_class_based_highlighting(self):
        """高亮以 CSS 类表达，配色由同一 formatter 的 style_defs 提供。"""
        page, css = build_page("def f(): pass", "python")
        assert '<pre class="hl">' in page
        assert "<span" in page
        assert ".hl .k" in css  # material 的关键字规则

    def test_layout_css_is_appended_last(self):
        """布局规则排在配色之后，才能覆盖 pygments 的底色与字体样式。"""
        _, css = build_page("x = 1", "python")
        assert css.index(".hl .k") < css.index("pre.hl{")
        assert f"max-width:{canvas.MAX_WIDTH}px" in css
        assert "white-space:pre-wrap" in css
        assert "tab-size:4" in css
        assert "font-style:normal" in css  # 关掉合成斜体

    def test_strips_trailing_newlines(self):
        """pygments 输出恒带尾部换行，不剥会在 <pre> 里多一行空白。"""
        page, _ = build_page("a = 1\n\n\n", "python")
        assert "\n" not in page

    def test_empty_code_keeps_one_line(self):
        """空代码块用零宽空格占一行，否则图片只剩内边距。"""
        page, _ = build_page("", "python")
        assert "&#8203;" in page

    def test_unknown_language_falls_back_to_text(self):
        """没有对应 lexer 时不猜，按纯文本渲染并转义。"""
        page, _ = build_page("x < y", "nosuchlang")
        assert "x &lt; y" in page

    def test_raises_without_font(self):
        """没有任何可用字体时明确报错，交由上层降级。"""
        with patch("render.code_render.find_font_spec", return_value=None):
            with pytest.raises(RuntimeError, match="字体"):
                build_page("x = 1", "python")


class TestRenderCode:
    def test_renders_png(self):
        """Python 代码块渲染出 PNG。"""
        png = render_code(CodeBlock(lang="python", code="def f(): pass"))
        assert png.startswith(b"\x89PNG")

    def test_no_language_still_renders(self):
        """无语言标注的代码块仍可渲染。"""
        png = render_code(CodeBlock(lang="", code="plain text"))
        assert png.startswith(b"\x89PNG")

    def test_width_follows_content(self):
        """宽度按内容自适应：短行不出宽画布。"""
        narrow = Image.open(io.BytesIO(
            render_code(CodeBlock(lang="python", code="a = 1"))
        )).width
        wide = Image.open(io.BytesIO(
            render_code(CodeBlock(lang="python", code="a = 1 + 2 + 3 + 4 + 5 + 6"))
        )).width
        assert 27 * 2 < narrow < wide < canvas.MAX_WIDTH

    def test_long_line_is_wrapped_at_max_width(self):
        """超长行由 CSS max-width 折行，画布封顶 MAX_WIDTH，不做二次渲染。"""
        code = "x = " + " + ".join(f"value_{i}" for i in range(40))
        image = Image.open(io.BytesIO(render_code(CodeBlock(lang="python", code=code))))
        assert image.width == canvas.MAX_WIDTH
        assert image.height > 53 + 27 * 2  # 至少两行

    def test_empty_code_keeps_legacy_size(self):
        """空代码块尺寸与 pillow 版一致：左右各 27px 内边距、一行 53px。"""
        image = Image.open(io.BytesIO(render_code(CodeBlock(lang="python", code=""))))
        assert image.size == (54, 107)
