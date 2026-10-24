"""表格渲染测试（pytakumi + CSS 折行）。"""
import io
import os

import pytest
from PIL import Image

from render.html_render import init_html
from render.parser import parse
from render.table_domain import RichCell, Span, Table
from render.table_domain import table_to_markdown
from render.table_render import (
    _MAX_WIDTH,
    _Layout,
    _cell,
    _decorate,
    _document,
    _natural_widths,
    _resources,
    plan_widths,
    render_table,
)

_NOTO = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"


@pytest.fixture(scope="module", autouse=True)
def _renderer() -> None:
    """表格共用 html_render 的渲染器，测试前先初始化。"""
    init_html(1000)


def _text_cell(text: str, align: str = "") -> RichCell:
    return RichCell(spans=[Span(text=text)], align=align)


def _layout_of(table: Table) -> _Layout:
    face, font = _resources()
    cache: dict = {}
    return _Layout(
        header=[_cell(c, font, cache) for c in table.headers],
        rows=[[_cell(c, font, cache) for c in row] for row in table.rows],
        n_cols=max([len(table.headers)] + [len(r) for r in table.rows] + [1]),
    )


def _first_table(md: str) -> Table:
    return next(s for s in parse(md) if isinstance(s, Table))


class TestPlanWidths:
    """列宽分配：三档。"""

    def test_short_table_keeps_natural(self):
        """整表放得下：按自然宽返回，不拉满上限。"""
        natural = [100, 120, 140]
        assert plan_widths(natural, [80, 80, 80]) == natural

    def test_short_column_not_compressed(self):
        """一列超长：短列保持自然宽，长列吃掉余额。"""
        widths = plan_widths([200, 4000], [200, 100])
        assert widths[0] == 200
        assert widths[1] > widths[0] * 3
        assert sum(widths) <= _MAX_WIDTH

    def test_many_columns_compressed(self):
        """列太多：等比压缩，总宽不超上限，各列等宽。"""
        widths = plan_widths([600] * 8, [100] * 8)
        assert sum(widths) <= _MAX_WIDTH
        assert len(set(widths)) == 1

    def test_header_raises_floor(self):
        """表头比内容宽时，保底宽按表头算。"""
        widths = plan_widths([50, 4000], [200, 100])
        assert widths[0] == 50

    def test_empty(self):
        assert plan_widths([], []) == []


class TestCellSerialization:
    """单元格 → HTML：转义、格式嵌套、公式图。"""

    def test_escapes_markup(self):
        _, font = _resources()
        cell = _cell(_text_cell("<div> & 引号"), font, {})
        assert "&lt;div&gt;" in cell.html
        assert "&amp;" in cell.html
        assert "<div>" not in cell.html

    def test_escapes_link_url(self):
        _, font = _resources()
        span = Span(text="链接", link_url='https://x.y/?a=1&b="2"')
        html = _cell(RichCell(spans=[span]), font, {})
        assert 'href="https://x.y/?a=1&amp;b=&quot;2&quot;"' in html.html

    def test_nested_format_order(self):
        span = Span(text="x", bold=True, italic=True, code=True)
        assert _decorate("x", span) == "<b><i><code>x</code></i></b>"

    def test_empty_cell_keeps_height(self):
        _, font = _resources()
        cell = _cell(RichCell(spans=[Span(text="")]), font, {})
        assert cell.html == "&nbsp;"

    def test_math_rendered_as_image(self, monkeypatch):
        """格内 $...$ 变成 img，纯货币符号不触发渲染。"""
        calls: list[str] = []
        image = Image.new("RGBA", (40, 20), (0, 0, 0, 255))
        monkeypatch.setattr(
            "render.table_render.render_expr_image",
            lambda src, **kw: calls.append(src) or image,
        )
        _, font = _resources()
        _cell(_text_cell("$x^2+1$"), font, {})
        _cell(_text_cell("$5"), font, {})
        assert calls == ["x^2+1"]


class TestAlignment:
    """markdown 表格对齐（:---: 等）。"""

    def test_parse_sets_align(self):
        md = "| a | b | c |\n|:---|:---:|---:|\n| 1 | 2 | 3 |\n"
        table = _first_table(md)
        assert [c.align for c in table.headers] == ["left", "center", "right"]
        assert [c.align for c in table.rows[0]] == ["left", "center", "right"]

    def test_document_writes_text_align(self):
        table = _first_table("| a | b |\n|:---:|---:|\n| 1 | 2 |\n")
        layout = _layout_of(table)
        natural, header = _natural_widths(layout)
        html = _document(layout, plan_widths(natural, header))
        assert "text-align:center" in html
        assert "text-align:right" in html

    def test_no_align_specified(self):
        table = _first_table("| a | b |\n|---|---|\n| 1 | 2 |\n")
        layout = _layout_of(table)
        natural, header = _natural_widths(layout)
        html = _document(layout, plan_widths(natural, header))
        assert "text-align" not in html


class TestRenderTable:
    """真实渲染冒烟。"""

    def test_long_cell_wraps_within_max_width(self):
        if not os.path.exists(_NOTO):
            pytest.skip("容器内无 Noto CJK 字体")
        table = Table(
            headers=[_text_cell("配置项"), _text_cell("说明")],
            rows=[[_text_cell("表格"), _text_cell("很长的说明文字。" * 40)]],
        )
        png = render_table(table)
        assert png.startswith(b"\x89PNG")
        image = Image.open(io.BytesIO(png))
        assert _MAX_WIDTH - 6 <= image.width <= _MAX_WIDTH
        assert image.height > 100

    def test_short_table_shrinks_canvas(self):
        if not os.path.exists(_NOTO):
            pytest.skip("容器内无 Noto CJK 字体")
        table = Table(
            headers=[_text_cell("姓名"), _text_cell("年龄")],
            rows=[[_text_cell("张三"), _text_cell("20")]],
        )
        image = Image.open(io.BytesIO(render_table(table)))
        assert image.width < 400

    def test_header_only_table(self):
        if not os.path.exists(_NOTO):
            pytest.skip("容器内无 Noto CJK 字体")
        png = render_table(Table(headers=[_text_cell("A")], rows=[]))
        assert png.startswith(b"\x89PNG")


class TestTableToText:
    """table_to_markdown 从 RichCell 重建 markdown。"""

    def test_plain_cell(self):
        t = Table(headers=[_text_cell("A")], rows=[[_text_cell("1")]])
        result = table_to_markdown(t)
        assert "| A |" in result
        assert "| 1 |" in result

    def test_bold_cell(self):
        t = Table(
            headers=[_text_cell("H")],
            rows=[[RichCell(spans=[Span(text="bold", bold=True)])]],
        )
        result = table_to_markdown(t)
        assert "| **bold** |" in result

    def test_mixed_cell(self):
        t = Table(
            headers=[_text_cell("H")],
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
