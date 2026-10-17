"""代码块渲染测试。"""
from unittest.mock import MagicMock, patch

import pytest
from pygments.formatters.img import STYLES

from render.code_render import _FaceFontManager, _FaceFormatter, render_code
from render.font import FontSpec
from render.parser import CodeBlock

DEJAVU = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
NOTO = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"


class TestRenderCode:
    @patch(
        "render.code_render.find_font_spec",
        return_value=FontSpec(DEJAVU),
    )
    def test_renders_python_code(self, mock_spec):
        """Python 代码块渲染返回 PNG bytes。"""
        cb = CodeBlock(lang="python", code="def f(): pass")
        png_bytes = render_code(cb)

        assert isinstance(png_bytes, bytes)
        assert len(png_bytes) > 0

    @patch(
        "render.code_render.find_font_spec",
        return_value=FontSpec(DEJAVU),
    )
    def test_code_without_lang(self, mock_spec):
        """无语言标注的代码块仍可渲染。"""
        cb = CodeBlock(lang="", code="plain text")
        png_bytes = render_code(cb)

        assert isinstance(png_bytes, bytes)
        assert len(png_bytes) > 0

    @patch(
        "render.code_render.find_font_spec",
        return_value=FontSpec(DEJAVU),
    )
    def test_empty_code(self, mock_spec):
        """空代码块也能渲染。"""
        cb = CodeBlock(lang="python", code="")
        png_bytes = render_code(cb)

        assert isinstance(png_bytes, bytes)
        assert len(png_bytes) > 0

    @patch("render.code_render.find_font_spec", return_value=None)
    def test_raises_without_font(self, mock_spec):
        """没有任何可用字体时明确报错，交由上层降级为原文。"""
        cb = CodeBlock(lang="python", code="def f(): pass")
        with pytest.raises(RuntimeError, match="字体"):
            render_code(cb)


class TestFaceIndexLoading:
    @patch("render.code_render.ImageFont.truetype")
    def test_manager_loads_given_face(self, mock_truetype):
        """字体管理器把 face 序号传给 Pillow，四种样式共用同一字体。"""
        font = MagicMock()
        mock_truetype.return_value = font

        manager = _FaceFontManager(NOTO, 38, 7)

        mock_truetype.assert_called_once_with(NOTO, 38, index=7)
        assert set(manager.fonts) == set(STYLES)
        assert all(f is font for f in manager.fonts.values())

    @patch("render.code_render.ImageFont.truetype")
    def test_formatter_rebuilds_manager_with_index(self, mock_truetype):
        """Formatter 初始化后按同一路径与字号重建带 index 的字体管理器。"""
        font = MagicMock()
        font.getbbox.return_value = (0, 0, 19, 38)
        mock_truetype.return_value = font

        formatter = _FaceFormatter(
            font_name=NOTO,
            font_size=38,
            face_index=7,
            style="material",
            line_numbers=False,
        )

        assert isinstance(formatter.fonts, _FaceFontManager)
        assert (formatter.fontw, formatter.fonth) == (19, 38)
        assert mock_truetype.call_args_list[-1].kwargs["index"] == 7
