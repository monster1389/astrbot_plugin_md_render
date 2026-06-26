"""表格渲染测试。"""
from unittest.mock import MagicMock, patch

from render.parser import RichCell, Span, Table
from render.utils import RenderConfig


def _make_cfg(**overrides):
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


def _cell(text: str) -> RichCell:
    return RichCell(spans=[Span(text=text)])


class TestRenderTable:
    @patch("render.table.ImageDraw")
    @patch("render.table.Image")
    @patch("render.table.get_font")
    def test_renders_simple_table(self, mock_get_font, mock_img_cls, mock_draw_cls):
        """简单表格渲染返回字节数据。"""
        mock_font = MagicMock()
        mock_font.getbbox.return_value = (0, 0, 100, 20)
        mock_get_font.return_value = mock_font
        mock_img = MagicMock()
        mock_img.resize.return_value = mock_img
        mock_img_cls.new.return_value = mock_img

        def save_side_effect(buf, *args, **kwargs):
            buf.write(b"fake_png_data")
        mock_img.save.side_effect = save_side_effect

        tbl = Table(
            headers=[_cell("姓名"), _cell("年龄")],
            rows=[[_cell("张三"), _cell("20")], [_cell("李四"), _cell("25")]],
        )
        cfg = _make_cfg()

        from render.table import render_table
        png_bytes = render_table(tbl, cfg, data_dir="/tmp")

        assert isinstance(png_bytes, bytes)
        assert len(png_bytes) > 0
        mock_img.save.assert_called_once()

    @patch("render.table.ImageDraw")
    @patch("render.table.Image")
    @patch("render.table.get_font")
    def test_empty_table(self, mock_get_font, mock_img_cls, mock_draw_cls):
        """空表格也能渲染。"""
        mock_font = MagicMock()
        mock_font.getbbox.return_value = (0, 0, 100, 20)
        mock_get_font.return_value = mock_font
        mock_img = MagicMock()
        mock_img.resize.return_value = mock_img
        mock_img_cls.new.return_value = mock_img

        def save_side_effect(buf, *args, **kwargs):
            buf.write(b"fake_png_data")
        mock_img.save.side_effect = save_side_effect

        tbl = Table(headers=[_cell("A")], rows=[])
        cfg = _make_cfg()

        from render.table import render_table
        png_bytes = render_table(tbl, cfg, data_dir="/tmp")

        assert isinstance(png_bytes, bytes)
        assert len(png_bytes) > 0
        mock_img.save.assert_called_once()

    @patch("render.table.ImageDraw")
    @patch("render.table.Image")
    @patch("render.table.get_font")
    def test_rich_cell_with_bold_and_italic(self, mock_get_font, mock_img_cls, mock_draw_cls):
        """包含加粗和斜体 Span 的富文本单元格正确渲染。"""
        mock_font = MagicMock()
        mock_font.getbbox.return_value = (0, 0, 100, 20)
        mock_get_font.return_value = mock_font
        mock_img = MagicMock()
        mock_img.resize.return_value = mock_img
        mock_img_cls.new.return_value = mock_img

        def save_side_effect(buf, *args, **kwargs):
            buf.write(b"fake_png_data")
        mock_img.save.side_effect = save_side_effect

        tbl = Table(
            headers=[_cell("格式"), _cell("内容")],
            rows=[
                [
                    RichCell(spans=[Span(text="加粗", bold=True)]),
                    RichCell(spans=[Span(text="普通"), Span(text="斜体", italic=True)]),
                ]
            ],
        )
        cfg = _make_cfg()

        from render.table import render_table
        png_bytes = render_table(tbl, cfg, data_dir="/tmp")

        assert isinstance(png_bytes, bytes)
        assert len(png_bytes) > 0
        mock_img.save.assert_called_once()

    @patch("render.table.ImageDraw")
    @patch("render.table.Image")
    @patch("render.table.get_font")
    def test_all_span_formats(self, mock_get_font, mock_img_cls, mock_draw_cls):
        """全部 5 种格式 Span 均能渲染。"""
        mock_font = MagicMock()
        mock_font.getbbox.return_value = (0, 0, 100, 20)
        mock_get_font.return_value = mock_font
        mock_img = MagicMock()
        mock_img.resize.return_value = mock_img
        mock_img_cls.new.return_value = mock_img

        def save_side_effect(buf, *args, **kwargs):
            buf.write(b"fake_png_data")
        mock_img.save.side_effect = save_side_effect

        tbl = Table(
            headers=[_cell("类型")],
            rows=[
                [RichCell(spans=[
                    Span(text="粗", bold=True),
                    Span(text="斜", italic=True),
                    Span(text="删", strike=True),
                    Span(text="码", code=True),
                    Span(text="链", link_url="https://x.com"),
                ])],
            ],
        )
        cfg = _make_cfg()

        from render.table import render_table
        png_bytes = render_table(tbl, cfg, data_dir="/tmp")

        assert isinstance(png_bytes, bytes)
        assert len(png_bytes) > 0
        mock_img.save.assert_called_once()


class TestTableToText:
    """_table_to_text 从 RichCell 重建 markdown。"""

    def test_plain_cell(self):
        from render.chain import _table_to_text
        t = Table(headers=[_cell("A")], rows=[[_cell("1")]])
        result = _table_to_text(t)
        assert "| A |" in result
        assert "| 1 |" in result

    def test_bold_cell(self):
        from render.chain import _table_to_text
        t = Table(
            headers=[_cell("H")],
            rows=[[RichCell(spans=[Span(text="bold", bold=True)])]],
        )
        result = _table_to_text(t)
        assert "| **bold** |" in result

    def test_mixed_cell(self):
        from render.chain import _table_to_text
        t = Table(
            headers=[_cell("H")],
            rows=[[RichCell(spans=[
                Span(text="b", bold=True),
                Span(text="i", italic=True),
                Span(text="s", strike=True),
                Span(text="c", code=True),
                Span(text="l", link_url="https://a.b"),
            ])]],
        )
        result = _table_to_text(t)
        assert "**b**" in result
        assert "*i*" in result
        assert "~~s~~" in result
        assert "`c`" in result
        assert "[l](https://a.b)" in result
