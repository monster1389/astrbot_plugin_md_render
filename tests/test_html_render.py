"""HTML 渲染测试（pytakumi 无浏览器）。"""
import io
import os

import pytest
from PIL import Image

from render import renderer
from render.html_render import extract_styles, render_html
from render.parser import HtmlDoc

_NOTO = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"


@pytest.fixture(autouse=True)
def _init() -> None:
    """每个用例前初始化渲染器，结束后恢复默认宽度。"""
    renderer.init(None, 1000)
    yield
    renderer.init(None, 1000)


class TestExtractStyles:
    def test_single_style_block(self):
        html = "<html><head><style>body{color:red}</style></head></html>"
        assert extract_styles(html) == "body{color:red}"

    def test_multiple_style_blocks(self):
        html = "<style>a{}</style><style>b{}</style>"
        assert extract_styles(html) == "a{}\nb{}"

    def test_no_style(self):
        assert extract_styles("<html></html>") == ""


class TestRenderHtml:
    def test_renders_document(self):
        """完整文档渲染出 PNG，宽度等于配置值。"""
        renderer.init(None, 360)
        doc = HtmlDoc(
            code=(
                "<!DOCTYPE html><html><head><style>body{background:#0d1117;color:#e6edf3}</style>"
                "</head><body><h1>标题</h1><p>中文段落</p></body></html>"
            )
        )
        png = render_html(doc)
        assert isinstance(png, bytes)
        assert png.startswith(b"\x89PNG")
        assert Image.open(io.BytesIO(png)).width == 360


class TestFontRegistration:
    """字体由 renderer.init 统一注册：ttc 自带的各族名都可寻址。"""

    def test_sc_and_jp_faces_differ(self):
        """SC 与 JP 的渲染结果必须不同，否则说明 ttc 被归成了单一 face。"""
        if not os.path.exists(_NOTO):
            pytest.skip("容器内无 Noto CJK 字体")
        body = "<html><body>直骨次角</body></html>"
        sc = renderer.render_page(body, "body{font-family:'Noto Sans CJK SC';font-size:40px}", width=400)
        jp = renderer.render_page(body, "body{font-family:'Noto Sans CJK JP';font-size:40px}", width=400)
        assert sc != jp
