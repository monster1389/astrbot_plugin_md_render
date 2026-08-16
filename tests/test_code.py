"""代码块渲染测试。"""
from unittest.mock import patch

from render.code import render_code
from render.parser import CodeBlock


class TestRenderCode:
    @patch("render.code.find_font_path", return_value="/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf")
    def test_renders_python_code(self, mock_load):
        """Python 代码块渲染返回 PNG bytes。"""
        cb = CodeBlock(lang="python", code="def f(): pass")
        png_bytes = render_code(cb, data_dir="/tmp")

        assert isinstance(png_bytes, bytes)
        assert len(png_bytes) > 0

    @patch("render.code.find_font_path", return_value="/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf")
    def test_code_without_lang(self, mock_load):
        """无语言标注的代码块仍可渲染。"""
        cb = CodeBlock(lang="", code="plain text")
        png_bytes = render_code(cb, data_dir="/tmp")

        assert isinstance(png_bytes, bytes)
        assert len(png_bytes) > 0

    @patch("render.code.find_font_path", return_value="/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf")
    def test_empty_code(self, mock_load):
        """空代码块也能渲染。"""
        cb = CodeBlock(lang="python", code="")
        png_bytes = render_code(cb, data_dir="/tmp")

        assert isinstance(png_bytes, bytes)
        assert len(png_bytes) > 0
