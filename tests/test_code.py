"""代码块渲染测试。"""
from unittest.mock import patch

from render.code import render_code
from render.parser import CodeBlock
from render.utils import RenderConfig


def _make_cfg(**overrides):
    """构造测试用 RenderConfig。"""
    defaults = {
        "code_mode": "渲染且txt",
        "table_mode": "渲染图像",
        "expr_mode": "渲染图像",
        "divider_mode": "不处理",
        "blank_line_mode": "不处理",
        "temp_ttl": 5,
    }
    return RenderConfig(**(defaults | overrides))


class TestRenderCode:
    @patch("render.code.find_font_path", return_value="/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf")
    def test_renders_python_code(self, mock_load):
        """Python 代码块渲染返回 PNG bytes。"""
        cb = CodeBlock(lang="python", code="def f(): pass")
        cfg = _make_cfg()
        png_bytes = render_code(cb, cfg, data_dir="/tmp")

        assert isinstance(png_bytes, bytes)
        assert len(png_bytes) > 0

    @patch("render.code.find_font_path", return_value="/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf")
    def test_code_without_lang(self, mock_load):
        """无语言标注的代码块仍可渲染。"""
        cb = CodeBlock(lang="", code="plain text")
        cfg = _make_cfg()
        png_bytes = render_code(cb, cfg, data_dir="/tmp")

        assert isinstance(png_bytes, bytes)
        assert len(png_bytes) > 0

    @patch("render.code.find_font_path", return_value="/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf")
    def test_empty_code(self, mock_load):
        """空代码块也能渲染。"""
        cb = CodeBlock(lang="python", code="")
        cfg = _make_cfg()
        png_bytes = render_code(cb, cfg, data_dir="/tmp")

        assert isinstance(png_bytes, bytes)
        assert len(png_bytes) > 0
