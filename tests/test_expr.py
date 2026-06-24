"""表达式渲染测试。"""
import os
from unittest.mock import MagicMock, patch

from render.parser import InlineExpr, BlockExpr


class TestRenderExpr:
    @patch("render.expr.pillowlatex")
    def test_inline_expr(self, mock_latex):
        """行内表达式渲染返回 png 路径。"""
        mock_img = MagicMock()
        mock_latex.render.return_value = mock_img
        mock_img.size = (100, 20)
        mock_img.save = MagicMock()

        expr = InlineExpr(expr="E=mc^2")
        config = {
            "背景颜色": "#1E1E1E (VS Code 深色)",
        }
        from render.expr import render_inline_expr
        png_path = render_inline_expr(expr, config, data_dir="/tmp")

        assert png_path.endswith(".png")
        assert os.path.basename(png_path).startswith("expr_")
        mock_latex.render.assert_called_once()

    @patch("render.expr.pillowlatex")
    def test_block_expr(self, mock_latex):
        """块级表达式渲染返回 png 路径。"""
        mock_img = MagicMock()
        mock_latex.render.return_value = mock_img
        mock_img.size = (200, 50)
        mock_img.save = MagicMock()

        expr = BlockExpr(expr="\\int_0^\\infty e^{-x} dx = 1")
        config = {
            "背景颜色": "#1E1E1E (VS Code 深色)",
        }
        from render.expr import render_block_expr
        png_path = render_block_expr(expr, config, data_dir="/tmp")

        assert png_path.endswith(".png")
        assert os.path.basename(png_path).startswith("expr_")
        mock_latex.render.assert_called_once()
