"""表格渲染测试。"""
import os
from unittest.mock import MagicMock, patch

from render.parser import Table

_FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"


class TestRenderTable:
    @patch("render.table.plt")
    @patch("render.table._find_font_path", return_value=_FONT_PATH)
    def test_renders_simple_table(self, mock_font, mock_plt):
        """简单表格渲染返回 png 路径。"""
        mock_fig = MagicMock()
        mock_plt.subplots.return_value = (mock_fig, MagicMock())

        tbl = Table(headers=["姓名", "年龄"], rows=[["张三", "20"], ["李四", "25"]])
        config = {
            "字体颜色": "#9CDCFE (浅蓝)",
            "背景颜色": "#1E1E1E (VS Code 深色)",
            "字形映射": "{}",
        }

        from render.table import render_table
        png_path = render_table(tbl, config, data_dir="/tmp")

        assert png_path.endswith(".png")
        assert os.path.basename(png_path).startswith("table_")
        mock_plt.savefig.assert_called_once()
        mock_plt.close.assert_called_once()

    @patch("render.table.plt")
    @patch("render.table._find_font_path", return_value=_FONT_PATH)
    def test_empty_table(self, mock_font, mock_plt):
        """空表格也能渲染。"""
        mock_fig = MagicMock()
        mock_plt.subplots.return_value = (mock_fig, MagicMock())

        tbl = Table(headers=["A"], rows=[])
        config = {
            "字体颜色": "#9CDCFE (浅蓝)",
            "背景颜色": "#1E1E1E (VS Code 深色)",
            "字形映射": "{}",
        }

        from render.table import render_table
        png_path = render_table(tbl, config, data_dir="/tmp")

        assert os.path.basename(png_path).startswith("table_")
        mock_plt.savefig.assert_called_once()
        mock_plt.close.assert_called_once()
