"""HTML 渲染测试（pytakumi 无浏览器）。"""
import io

from PIL import Image

from render.html_render import extract_styles, init_html, render_html
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
