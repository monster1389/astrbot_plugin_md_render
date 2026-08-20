"""表格子域测试：表格解析、格内占位符还原、markdown 还原。"""
from render.parser import parse
from render.table_domain import RichCell, Span, Table, table_to_markdown


class TestTable:
    def test_simple_table(self):
        """简单表格解析。"""
        text = "| A | B |\n|---|---|\n| 1 | 2 |"
        segments = parse(text)
        assert len(segments) == 1
        seg = segments[0]
        assert isinstance(seg, Table)
        assert seg.headers == [RichCell(spans=[Span(text="A")]), RichCell(spans=[Span(text="B")])]
        assert seg.rows == [[RichCell(spans=[Span(text="1")]), RichCell(spans=[Span(text="2")])]]

    def test_table_with_padding(self):
        """含空格填充的表格。"""
        text = "| 姓名 | 年龄 |\n|------|------|\n| 张三 |  20  |"
        segments = parse(text)
        assert len(segments) == 1
        seg = segments[0]
        assert isinstance(seg, Table)
        assert seg.headers == [RichCell(spans=[Span(text="姓名")]), RichCell(spans=[Span(text="年龄")])]
        assert seg.rows == [[RichCell(spans=[Span(text="张三")]), RichCell(spans=[Span(text="20")])]]


class TestBlockMathInCell:
    """$$...$$ 位于表格单元格内时还原为文本，不泄漏占位符。"""

    def test_single_line_cell_restored(self):
        """格内单行 $$...$$ 还原为 $expr$。"""
        text = "| a |\n| --- |\n| $$E=mc^2$$ |"
        segments = parse(text)
        table = segments[0]
        assert isinstance(table, Table)
        assert table.rows[0][0].spans == [Span(text="$E=mc^2$")]

    def test_multi_line_cell_restored_literal(self):
        """格内多行 $$...$$ 还原为字面文本。"""
        text = "| a |\n| --- |\n| $$x^2\n\nmore$$ |"
        segments = parse(text)
        table = segments[0]
        assert isinstance(table, Table)
        assert table.rows[0][0].spans == [Span(text="$x^2\n\nmore$")]

    def test_cell_math_in_markdown_roundtrip(self):
        """格内 $$...$$ 经 table_to_markdown 还原为 $...$。"""
        text = "| a | b |\n| --- | --- |\n| $$E=mc^2$$ | x |"
        segments = parse(text)
        table = segments[0]
        assert isinstance(table, Table)
        assert table_to_markdown(table) == "| a | b |\n|---|---|\n| $E=mc^2$ | x |"
