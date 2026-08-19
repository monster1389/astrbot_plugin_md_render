"""表达式渲染测试。"""
from unittest.mock import MagicMock, patch

from render.expr import render_expr
from render.parser import BlockExpr, InlineExpr


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
        mock_result.save.side_effect = lambda *args, **kw: args[0].write(b"fake_png")
        mock_pil_image.new.return_value = mock_result

        png_bytes = render_expr(InlineExpr(expr="E=mc^2"), "/tmp")

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
        mock_result.save.side_effect = lambda *args, **kw: args[0].write(b"fake_png")
        mock_pil_image.new.return_value = mock_result

        png_bytes = render_expr(BlockExpr(expr="\\int_0^\\infty e^{-x} dx = 1"), "/tmp")

        assert isinstance(png_bytes, bytes)
        assert len(png_bytes) > 0
        mock_getlatex.assert_called_once_with(
            "\\int_0^\\infty e^{-x} dx = 1"
        )
        mock_render.assert_called_once_with(parsed)
        mock_result.save.assert_called_once()
