"""表达式渲染测试。"""
import os
from unittest.mock import MagicMock, patch

from render.expr import render_inline_expr, render_block_expr
from render.parser import InlineExpr, BlockExpr


class TestRenderExpr:
    @patch("render.expr.Image")
    @patch("render.expr.RenderLaTeX")
    def test_inline_expr(self, mock_render, mock_pil_image):
        """行内表达式渲染返回 png 路径，传入原始表达式不含 $ 分隔符。"""
        mock_render_img = MagicMock()
        mock_render_img.size = (100, 20)
        mock_alpha = MagicMock()
        mock_render_img.split.return_value = (None, None, None, mock_alpha)
        mock_render.return_value.img = mock_render_img

        mock_result = MagicMock()
        mock_pil_image.new.return_value = mock_result

        expr = InlineExpr(expr="E=mc^2")
        config = {
            "字体颜色": "#9CDCFE (浅蓝)",
            "背景颜色": "#1E1E1E (VS Code 深色)",
        }
        png_path = render_inline_expr(expr, config, data_dir="/tmp")

        assert png_path.endswith(".png")
        assert os.path.basename(png_path).startswith("expr_")
        mock_render.assert_called_once_with("E=mc^2")
        mock_result.save.assert_called_once()

    @patch("render.expr.Image")
    @patch("render.expr.RenderLaTeX")
    def test_block_expr(self, mock_render, mock_pil_image):
        """块级表达式渲染，传入原始表达式不含 \\[ \\] 分隔符。"""
        mock_render_img = MagicMock()
        mock_render_img.size = (200, 30)
        mock_alpha = MagicMock()
        mock_render_img.split.return_value = (None, None, None, mock_alpha)
        mock_render.return_value.img = mock_render_img

        mock_result = MagicMock()
        mock_pil_image.new.return_value = mock_result

        expr = BlockExpr(expr="\\int_0^\\infty e^{-x} dx = 1")
        config = {
            "字体颜色": "#9CDCFE (浅蓝)",
            "背景颜色": "#1E1E1E (VS Code 深色)",
        }
        png_path = render_block_expr(expr, config, data_dir="/tmp")

        assert png_path.endswith(".png")
        assert os.path.basename(png_path).startswith("expr_")
        mock_render.assert_called_once_with(
            "\\int_0^\\infty e^{-x} dx = 1"
        )
        mock_result.save.assert_called_once()
