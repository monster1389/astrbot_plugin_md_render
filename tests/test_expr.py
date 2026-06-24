"""表达式渲染测试。"""
import os
from unittest.mock import MagicMock, patch

from render.expr import render_inline_expr, render_block_expr
from render.parser import InlineExpr, BlockExpr


class TestRenderExpr:
    @patch("render.expr.RenderLaTeX")
    def test_inline_expr(self, mock_render):
        """行内表达式渲染返回 png 路径，传入原始表达式不含 $ 分隔符。"""
        mock_img = MagicMock()
        mock_render.return_value = mock_img

        expr = InlineExpr(expr="E=mc^2")
        config = {
            "背景颜色": "#1E1E1E (VS Code 深色)",
        }
        png_path = render_inline_expr(expr, config, data_dir="/tmp")

        assert png_path.endswith(".png")
        assert os.path.basename(png_path).startswith("expr_")
        mock_render.assert_called_once_with("E=mc^2")
        mock_img.img.save.assert_called_once()

    @patch("render.expr.RenderLaTeX")
    def test_block_expr(self, mock_render):
        """块级表达式渲染，传入原始表达式不含 \\[ \\] 分隔符。"""
        mock_img = MagicMock()
        mock_render.return_value = mock_img

        expr = BlockExpr(expr="\\int_0^\\infty e^{-x} dx = 1")
        config = {
            "背景颜色": "#1E1E1E (VS Code 深色)",
        }
        png_path = render_block_expr(expr, config, data_dir="/tmp")

        assert png_path.endswith(".png")
        assert os.path.basename(png_path).startswith("expr_")
        mock_render.assert_called_once_with(
            "\\int_0^\\infty e^{-x} dx = 1"
        )
        mock_img.img.save.assert_called_once()
