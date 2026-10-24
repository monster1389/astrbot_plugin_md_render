"""版面测试：底色、页面骨架、字体栈与出图。"""
import pytest

from render import canvas, renderer


@pytest.fixture(scope="module", autouse=True)
def _init() -> None:
    """fragment 走共享渲染器，测试前先初始化。"""
    renderer.init(None, 1000)


class TestPalette:
    def test_background_is_unified_dark(self):
        """所有自绘图片共用一个底色。"""
        assert canvas.BG == "#1E1E1E"

    def test_page_wraps_body_with_background(self):
        html = canvas.page("<p>正文</p>")
        assert html.startswith("<html><body")
        assert f"background:{canvas.BG}" in html
        assert "<p>正文</p>" in html


class TestFontStack:
    def test_mono_has_fallback_family(self):
        """等宽栈带 monospace 兜底，字体缺失时仍能排。"""
        stack = canvas.font_stack("mono")
        assert stack.endswith("monospace")

    def test_body_stack_is_a_single_family(self):
        """正文栈只给一个族名，兜底由 CSS 的通用族负责。"""
        assert canvas.font_stack("body") == f'"{canvas.font.body_family()}"'


class TestFragment:
    def test_renders_png(self):
        """片段装成页面后能出图。"""
        png = canvas.fragment("<p>正文</p>", "body{margin:0;font-size:20px}")
        assert png.startswith(b"\x89PNG")
