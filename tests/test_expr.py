"""表达式渲染测试。"""
from unittest.mock import MagicMock, patch

from render.expr import render_inline_expr, render_block_expr
from render.parser import BlockExpr, InlineExpr
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


class TestRenderExpr:
    @patch("render.expr.Image")
    @patch("render.expr.RenderLaTeX")
    @patch("render.expr.GetLaTeXObjs")
    def test_inline_expr(self, mock_getlatex, mock_render, mock_pil_image):
        """行内表达式渲染返回 PNG 字节串，先解析 LaTeX 再渲染。"""
        parsed = MagicMock()
        mock_getlatex.return_value = parsed

        mock_render_img = MagicMock()
        mock_render_img.size = (100, 20)
        mock_alpha = MagicMock()
        mock_render_img.split.return_value = (None, None, None, mock_alpha)
        mock_render.return_value.img = mock_render_img

        mock_result = MagicMock()
        mock_result.save.side_effect = lambda buf, fmt=None: buf.write(b"fake_png")
        mock_pil_image.new.return_value = mock_result

        expr = InlineExpr(expr="E=mc^2")
        cfg = _make_cfg()
        png_bytes = render_inline_expr(expr, cfg, data_dir="/tmp")

        assert isinstance(png_bytes, bytes)
        assert len(png_bytes) > 0
        mock_getlatex.assert_called_once_with("E=mc^2")
        mock_render.assert_called_once_with(parsed)
        mock_result.save.assert_called_once()

    @patch("render.expr.Image")
    @patch("render.expr.RenderLaTeX")
    @patch("render.expr.GetLaTeXObjs")
    def test_block_expr(self, mock_getlatex, mock_render, mock_pil_image):
        """块级表达式渲染返回 PNG 字节串，先解析 LaTeX 再渲染。"""
        parsed = MagicMock()
        mock_getlatex.return_value = parsed

        mock_render_img = MagicMock()
        mock_render_img.size = (200, 30)
        mock_alpha = MagicMock()
        mock_render_img.split.return_value = (None, None, None, mock_alpha)
        mock_render.return_value.img = mock_render_img

        mock_result = MagicMock()
        mock_result.save.side_effect = lambda buf, fmt=None: buf.write(b"fake_png")
        mock_pil_image.new.return_value = mock_result

        expr = BlockExpr(expr="\\int_0^\\infty e^{-x} dx = 1")
        cfg = _make_cfg()
        png_bytes = render_block_expr(expr, cfg, data_dir="/tmp")

        assert isinstance(png_bytes, bytes)
        assert len(png_bytes) > 0
        mock_getlatex.assert_called_once_with(
            "\\int_0^\\infty e^{-x} dx = 1"
        )
        mock_render.assert_called_once_with(parsed)
        mock_result.save.assert_called_once()
