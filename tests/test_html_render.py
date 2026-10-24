"""HTML 渲染测试（pytakumi 无浏览器）。"""
import io
import os

import pytest

from PIL import Image

from render.html_render import extract_styles, init_html, render_document, render_html
from render.parser import HtmlDoc


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
        init_html(360)
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
        init_html(1000)


class TestRenderDocument:
    """共享渲染器入口：宽度可控。"""

    def test_width_is_respected(self):
        init_html(1000)
        png = render_document("<html><body>文本</body></html>", 360)
        assert Image.open(io.BytesIO(png)).width == 360
        init_html(1000)


class TestFontRegistration:
    """注册不传 name：ttc 自带的各族名都可寻址。"""

    _NOTO = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"

    def test_sc_and_jp_faces_differ(self):
        """SC 与 JP 的渲染结果必须不同，否则说明 ttc 被归成了单一 face。"""
        if not os.path.exists(self._NOTO):
            pytest.skip("容器内无 Noto CJK 字体")
        init_html(1000)
        body = "<html><body>直骨次角</body></html>"
        sc = render_document(body, 400, "body{font-family:'Noto Sans CJK SC';font-size:40px}")
        jp = render_document(body, 400, "body{font-family:'Noto Sans CJK JP';font-size:40px}")
        assert sc != jp
