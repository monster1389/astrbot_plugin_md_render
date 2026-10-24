"""表格渲染测试（pytakumi + CSS 折行）。"""
import io
import os

import pytest
from PIL import Image

from render import canvas, font, renderer
from render.expr_render import Formula
from render.parser import parse
from render.table_domain import RichCell, Span, Table
from render.table_domain import table_to_markdown
from render.table_render import (
    _Layout,
    _cell,
    _decorate,
    _document,
    _natural_widths,
    plan_widths,
    render_table,
)

_NOTO = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"


@pytest.fixture(scope="module", autouse=True)
def _init() -> None:
    """表格共用 renderer 的出图口，测试前先初始化。"""
    renderer.init(None, 1000)


def _text_cell(text: str, align: str = "") -> RichCell:
    return RichCell(spans=[Span(text=text)], align=align)


def _layout_of(table: Table) -> _Layout:
    measure = font.measure_font(canvas.TABLE_SIZE)
    return _Layout(
        header=[_cell(c, measure, header=True) for c in table.headers],
        rows=[[_cell(c, measure) for c in row] for row in table.rows],
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
        assert sum(widths) <= canvas.MAX_WIDTH

    def test_many_columns_compressed(self):
        """列太多：等比压缩，总宽不超上限，各列等宽。"""
        widths = plan_widths([600] * 8, [100] * 8)
        assert sum(widths) <= canvas.MAX_WIDTH
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
        measure = font.measure_font(canvas.TABLE_SIZE)
        cell = _cell(_text_cell("<div> & 引号"), measure)
        assert "&lt;div&gt;" in cell.html
        assert "&amp;" in cell.html
        assert "<div>" not in cell.html

    def test_escapes_link_url(self):
        measure = font.measure_font(canvas.TABLE_SIZE)
        span = Span(text="链接", link_url='https://x.y/?a=1&b="2"')
        html = _cell(RichCell(spans=[span]), measure)
        assert 'href="https://x.y/?a=1&amp;b=&quot;2&quot;"' in html.html

    def test_nested_format_order(self):
        span = Span(text="x", bold=True, italic=True, code=True)
        assert _decorate("x", span) == "<b><i><code>x</code></i></b>"

    def test_empty_cell_keeps_height(self):
        measure = font.measure_font(canvas.TABLE_SIZE)
        cell = _cell(RichCell(spans=[Span(text="")]), measure)
        assert cell.html == "&nbsp;"

    def test_math_rendered_as_image(self, monkeypatch):
        """格内 $...$ 变成 img，尺寸来自公式图；纯货币符号不触发渲染。"""
        calls: list[str] = []
        monkeypatch.setattr(
            "render.table_render.formula_image",
            lambda src, **kw: calls.append(src) or Formula(png=b"png", width=40, height=20),
        )
        measure = font.measure_font(canvas.TABLE_SIZE)
        cell = _cell(_text_cell("$x^2+1$"), measure)
        _cell(_text_cell("$5"), measure)
        assert calls == ["x^2+1"]
        assert "width:40px" in cell.html
        assert "height:20px" in cell.html

    def test_broken_formula_falls_back_to_literal(self, monkeypatch):
        """一格公式失败只坏这一格：退回 $...$ 原文，不拖整表。"""
        def boom(src, **kw):
            raise RuntimeError("LaTeX 渲染失败：\\ce{H2O}")

        monkeypatch.setattr("render.table_render.formula_image", boom)
        measure = font.measure_font(canvas.TABLE_SIZE)
        cell = _cell(_text_cell("$\\ce{H2O}$"), measure)
        assert "<img" not in cell.html
        assert "$\\ce{H2O}$" in cell.html

    def test_header_cell_uses_header_role(self, monkeypatch):
        """表头格内公式按表头角色取默认色。"""
        seen: dict = {}

        def fake(src, **kw):
            seen.update(kw)
            return Formula(png=b"png", width=10, height=10)

        monkeypatch.setattr("render.table_render.formula_image", fake)
        measure = font.measure_font(canvas.TABLE_SIZE)
        _cell(_text_cell("$x$"), measure, header=True)
        assert seen["role"] == "table_header"
        assert seen["color"] is None

    def test_formatted_span_overrides_role_color(self, monkeypatch):
        """带显式格式的片段给公式一个覆盖色，纯文本片段交给角色。"""
        seen: dict = {}

        def fake(src, **kw):
            seen.update(kw)
            return Formula(png=b"png", width=10, height=10)

        monkeypatch.setattr("render.table_render.formula_image", fake)
        measure = font.measure_font(canvas.TABLE_SIZE)
        _cell(RichCell(spans=[Span(text="$x$", bold=True)]), measure)
        assert seen["role"] == "table"
        assert seen["color"] == canvas.BOLD

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
        assert canvas.MAX_WIDTH - 6 <= image.width <= canvas.MAX_WIDTH
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
