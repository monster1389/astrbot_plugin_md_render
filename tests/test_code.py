"""代码块渲染测试。"""
import os
from unittest.mock import MagicMock, patch

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
        "font_color": "#9CDCFE",
        "bg_color": "#1E1E1E",
        "glyph_mapping": {},
        "temp_ttl": 5,
    }
    return RenderConfig(**(defaults | overrides))


def _mock_font(*args, **kwargs):
    """返回一个 mock 字体对象，供 glyph fallback 检测使用。"""
    font = MagicMock()
    font.getmask.return_value = MagicMock()
    return font


class TestRenderCode:
    @patch("render.code._load_mono_font", side_effect=_mock_font)
    def test_renders_python_code(self, mock_load):
        """Python 代码块渲染返回 png 和 txt 文件路径。"""
        cb = CodeBlock(lang="python", code="def f(): pass")
        cfg = _make_cfg()
        png_path, txt_path = render_code(cb, cfg, data_dir="/tmp")

        assert png_path.endswith(".png")
        assert txt_path.endswith(".txt")
        assert os.path.basename(png_path).startswith("code_")
        assert os.path.basename(txt_path).startswith("code_")

        # txt 文件包含原始代码
        with open(txt_path, "r") as f:
            assert "def f(): pass" in f.read()

        # png 文件存在且非空
        assert os.path.getsize(png_path) > 0

        # 清理
        os.remove(png_path)
        os.remove(txt_path)

    @patch("render.code._load_mono_font", side_effect=_mock_font)
    def test_code_without_lang(self, mock_load):
        """无语言标注的代码块仍可渲染。"""
        cb = CodeBlock(lang="", code="plain text")
        cfg = _make_cfg()
        png_path, txt_path = render_code(cb, cfg, data_dir="/tmp")

        assert os.path.getsize(png_path) > 0
        os.remove(png_path)
        os.remove(txt_path)

    @patch("render.code._load_mono_font", side_effect=_mock_font)
    def test_empty_code(self, mock_load):
        """空代码块也能渲染。"""
        cb = CodeBlock(lang="python", code="")
        cfg = _make_cfg()
        png_path, txt_path = render_code(cb, cfg, data_dir="/tmp")

        assert os.path.getsize(png_path) > 0
        os.remove(png_path)
        os.remove(txt_path)
