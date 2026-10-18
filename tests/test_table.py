"""表格渲染测试。"""
from unittest.mock import MagicMock, patch

from render.table_domain import RichCell, Span, Table
from render.table_render import render_table


def _cell(text: str) -> RichCell:
    return RichCell(spans=[Span(text=text)])


class TestRenderTable:
    @patch("render.table_render.ImageDraw")
    @patch("render.table_render.Image")
    @patch("render.font.get_font")
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

        png_bytes = render_table(tbl)

        assert isinstance(png_bytes, bytes)
        assert len(png_bytes) > 0
        mock_img.save.assert_called_once()

    @patch("render.table_render.ImageDraw")
    @patch("render.table_render.Image")
    @patch("render.font.get_font")
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

        png_bytes = render_table(tbl)

        assert isinstance(png_bytes, bytes)
        assert len(png_bytes) > 0
        mock_img.save.assert_called_once()

    @patch("render.table_render.ImageDraw")
    @patch("render.table_render.Image")
    @patch("render.font.get_font")
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

        png_bytes = render_table(tbl)

        assert isinstance(png_bytes, bytes)
        assert len(png_bytes) > 0
        mock_img.save.assert_called_once()

    @patch("render.table_render.ImageDraw")
    @patch("render.table_render.Image")
    @patch("render.font.get_font")
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

        png_bytes = render_table(tbl)

        assert isinstance(png_bytes, bytes)
        assert len(png_bytes) > 0
        mock_img.save.assert_called_once()


class TestTableCellMath:
    """格内 $...$ 渲染为公式图。"""

    @patch("render.table_render.render_expr_image")
    def test_cell_expr_rendered(self, mock_expr):
        """公式单元格调用表达式渲染，而不是画源码。"""
        from PIL import Image as PILImage

        mock_expr.return_value = PILImage.new("RGBA", (30, 20), (0, 0, 0, 255))
        tbl = Table(headers=[_cell("公式")], rows=[[_cell("$x^2$")]])

        png_bytes = render_table(tbl)

        assert isinstance(png_bytes, bytes)
        assert len(png_bytes) > 0
        mock_expr.assert_called_once()
        assert mock_expr.call_args.args[0] == "x^2"

    @patch("render.table_render.render_expr_image")
    def test_currency_not_rendered(self, mock_expr):
        """孤立的 $ 货币符号不当作公式。"""
        tbl = Table(headers=[_cell("价格")], rows=[[_cell("$5")]])
        render_table(tbl)

        mock_expr.assert_not_called()


class TestTableToText:
    """table_to_markdown 从 RichCell 重建 markdown。"""

    def test_plain_cell(self):
        from render.table_domain import table_to_markdown
        t = Table(headers=[_cell("A")], rows=[[_cell("1")]])
        result = table_to_markdown(t)
        assert "| A |" in result
        assert "| 1 |" in result

    def test_bold_cell(self):
        from render.table_domain import table_to_markdown
        t = Table(
            headers=[_cell("H")],
            rows=[[RichCell(spans=[Span(text="bold", bold=True)])]],
        )
        result = table_to_markdown(t)
        assert "| **bold** |" in result

    def test_mixed_cell(self):
        from render.table_domain import table_to_markdown
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
        result = table_to_markdown(t)
        assert "**b**" in result
        assert "*i*" in result
        assert "~~s~~" in result
        assert "`c`" in result
        assert "[l](https://a.b)" in result
