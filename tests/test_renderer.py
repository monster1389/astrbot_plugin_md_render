"""takumi 出图口测试：初始化、宽度语义、字体注册。"""
import io

import pytest
from PIL import Image

from render import font, renderer

NOTO = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"


@pytest.fixture(autouse=True)
def _restore() -> None:
    """每个用例结束后恢复成真实渲染器，避免污染其它测试模块。"""
    yield
    renderer.init(None, 1000)


class TestInit:
    def test_records_html_width(self):
        """HTML 文档宽度来自配置，随初始化记录。"""
        renderer.init(None, 720)
        assert renderer.html_width() == 720

    def test_registers_each_font_file_once(self, tmp_path, monkeypatch):
        """注册的是 font_files() 的路径，同一文件只注册一次。"""
        first = tmp_path / "a.ttc"
        second = tmp_path / "b.ttf"
        first.write_bytes(b"font-a")
        second.write_bytes(b"font-b")
        registered: list[bytes] = []

        class FakeRenderer:
            def register_font(self, data):
                registered.append(data)

        monkeypatch.setattr("render.renderer.Renderer", FakeRenderer)
        monkeypatch.setattr(
            font, "font_files", lambda: [str(first), str(second)]
        )
        renderer.init(None, 1000)
        assert registered == [b"font-a", b"font-b"]


class TestRenderPage:
    def test_uninitialized_raises(self, monkeypatch):
        """未初始化时明确报错，不静默出空图。"""
        monkeypatch.setattr("render.renderer._renderer", None)
        with pytest.raises(RuntimeError, match="未初始化"):
            renderer.render_page("<html><body>x</body></html>")

    def test_width_none_follows_content(self):
        """width=None 时按内容自适应，不铺满默认宽度。"""
        renderer.init(None, 1000)
        png = renderer.render_page(
            '<html><body><pre style="margin:0">ab</pre></body></html>'
        )
        assert Image.open(io.BytesIO(png)).width < 100

    def test_width_is_respected(self):
        """显式宽度直接决定画布宽度。"""
        renderer.init(None, 1000)
        png = renderer.render_page("<html><body>文本</body></html>", width=360)
        assert Image.open(io.BytesIO(png)).width == 360

    def test_empty_css_is_not_passed(self):
        """空样式表不传，避免 takumi 收到空串。"""
        renderer.init(None, 1000)
        png = renderer.render_page("<html><body>x</body></html>", "  ")
        assert png.startswith(b"\x89PNG")
