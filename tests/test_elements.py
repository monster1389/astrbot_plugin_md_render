"""元素注册表测试。

覆盖三件事：表自身的完整性与不变量、文本配方的参数化（一种元素一条用例）、
以及注册表与 _conf_schema.json 的一致性。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from render.config import CleanConfig
from render.elements import (
    _MODE_SPECS,
    _TEXT_ONLY,
    ELEMENTS,
    FAMILIES,
    ModeSpec,
    recipe_for,
    text_for,
    writes_file,
)
from render.parser import (
    BlockExpr,
    CodeBlock,
    Divider,
    HtmlDoc,
    InlineExpr,
    MermaidBlock,
    Segment,
)
from render.table_domain import RichCell, Span, Table

_ROOT = Path(__file__).resolve().parent.parent


def _table() -> Table:
    return Table(
        headers=[RichCell(spans=[Span(text="名称")]), RichCell(spans=[Span(text="版本")])],
        rows=[[RichCell(spans=[Span(text="A")]), RichCell(spans=[Span(text="v1")])]],
    )


# 元素类型 → (样本, 裸文本期望, markdown 原文期望)
_SAMPLES: dict[type, tuple[object, str, str]] = {
    CodeBlock: (CodeBlock(lang="py", code="x=1"), "x=1", "```py\nx=1\n```"),
    HtmlDoc: (HtmlDoc(code="<html></html>"), "<html></html>", "```html\n<html></html>\n```"),
    MermaidBlock: (MermaidBlock(code="graph LR"), "graph LR", "```mermaid\ngraph LR\n```"),
    Table: (_table(), "名称 | 版本\nA | v1", "| 名称 | 版本 |\n|---|---|\n| A | v1 |"),
    InlineExpr: (InlineExpr(expr="x"), "x", "$x$"),
    BlockExpr: (BlockExpr(expr="x"), "x", "$$\nx\n$$"),
    Segment: (Segment(text="**加粗**"), "加粗", "**加粗**"),
    Divider: (Divider(), "\n\n", "\n\n---\n\n"),
}

# 清洗开关全开：三个元素族的开关默认是关的，这里显式打开
_CLEAN_ON = CleanConfig(code=True, table=True, expr=True)
# 清洗全关（含所有行内格式开关）
_CLEAN_OFF = CleanConfig(**{name: False for name in vars(CleanConfig())})

_IDS = lambda kind: kind.__name__  # noqa: E731


class TestRegistryShape:
    def test_covers_every_parser_type(self):
        """parse() 能产出的每种 segment 都在表里，不多不少。"""
        assert set(ELEMENTS) == set(_SAMPLES)

    def test_block_elements(self):
        """块级集合由注册表决定，不再另有一份元组。"""
        blocks = {kind for kind, element in ELEMENTS.items() if element.block}
        assert blocks == {CodeBlock, HtmlDoc, MermaidBlock, Table, BlockExpr}

    def test_only_mermaid_is_budgeted(self):
        """自带超时预算的只有走外部 HTTP 的 mermaid。"""
        budgeted = [kind for kind, element in ELEMENTS.items() if element.budgeted]
        assert budgeted == [MermaidBlock]

    def test_rendered_elements_have_config(self):
        """能渲染的元素都必须有配置身份，否则模式无处可查。"""
        for kind, element in ELEMENTS.items():
            if element.render is not None:
                assert element.config is not None, kind

    def test_text_only_elements_have_no_config(self):
        """纯文本段与分隔线没有配置模式。"""
        assert ELEMENTS[Segment].config is None
        assert ELEMENTS[Divider].config is None

    def test_families_share_one_config_object(self):
        """同一元素族的两个类型共用同一份配置身份。"""
        assert ELEMENTS[InlineExpr].config is ELEMENTS[BlockExpr].config
        assert FAMILIES["expr"] is ELEMENTS[InlineExpr].config

    def test_family_labels_are_unique(self):
        """族标签唯一：它同时是中文配置项名。"""
        labels = [config.label for config in FAMILIES.values()]
        assert len(labels) == len(set(labels))

    def test_family_defaults_are_reachable_modes(self):
        """默认值必须是该族可达的模式，且模式都能在 _MODE_SPECS 里查到。"""
        for config in FAMILIES.values():
            assert config.default in config.modes
            assert set(config.modes) <= set(_MODE_SPECS)
            assert len(set(config.modes)) == len(config.modes)

    def test_families_are_the_temp_prefixes(self):
        """产物前缀就是族键：tempstore 的正则由它派生。"""
        assert set(FAMILIES) == {"code", "table", "html", "mermaid", "expr"}
        assert ELEMENTS[Table].prefix == "table"

    def test_prefix_requires_config(self):
        """没有配置模式的元素不产生产物，取前缀直接报错。"""
        with pytest.raises(RuntimeError):
            ELEMENTS[Segment].prefix


class TestRecipe:
    def test_recipe_follows_mode(self):
        """模式 → 三插槽配方。"""
        element = ELEMENTS[CodeBlock]
        assert recipe_for(element, {"code": "不处理"}) == ModeSpec(text=True, image=False, file=False)
        assert recipe_for(element, {"code": "渲染图像"}) == ModeSpec(text=False, image=True, file=False)
        assert recipe_for(element, {"code": "渲染且md文件"}) == ModeSpec(text=False, image=True, file=True)

    def test_recipe_for_text_only_element(self):
        """无配置模式的元素固定只产文本。"""
        assert recipe_for(ELEMENTS[Segment], {}) == _TEXT_ONLY
        assert recipe_for(ELEMENTS[Divider], {}) == _TEXT_ONLY

    def test_unknown_mode_raises(self):
        """模式不认识就报错，不静默降级。"""
        with pytest.raises(KeyError):
            recipe_for(ELEMENTS[CodeBlock], {"code": "渲染且txt"})

    def test_writes_file_is_derived_from_modes(self):
        """.md 能力由可达模式派生，没有单独的能力位。"""
        assert writes_file(ELEMENTS[CodeBlock])
        assert writes_file(ELEMENTS[Table])
        assert writes_file(ELEMENTS[MermaidBlock])
        assert not writes_file(ELEMENTS[HtmlDoc])  # HTML 只支持前三种模式
        assert not writes_file(ELEMENTS[InlineExpr])
        assert not writes_file(ELEMENTS[Divider])


class TestTextRecipe:
    @pytest.mark.parametrize("kind", list(ELEMENTS), ids=_IDS)
    def test_cleaning_on_gives_plain_form(self, kind):
        """清洗开：给只含内容的裸文本。"""
        seg, plain, _markdown = _SAMPLES[kind]
        assert text_for(ELEMENTS[kind], seg, _CLEAN_ON) == plain

    @pytest.mark.parametrize("kind", list(ELEMENTS), ids=_IDS)
    def test_no_clean_config_gives_markdown(self, kind):
        """没有清洗配置：一律 markdown 原文。"""
        seg, _plain, markdown = _SAMPLES[kind]
        assert text_for(ELEMENTS[kind], seg, None) == markdown

    @pytest.mark.parametrize("kind", list(ELEMENTS), ids=_IDS)
    def test_every_switch_off_gives_markdown(self, kind):
        """管这个元素的开关关着：同样回到 markdown 原文。"""
        seg, _plain, markdown = _SAMPLES[kind]
        assert text_for(ELEMENTS[kind], seg, _CLEAN_OFF) == markdown

    def test_prose_switch_is_the_whole_config(self):
        """纯文本段没有单一开关：只要给了清洗配置就走整体清洗。"""
        seg = Segment(text="**粗** 与 *斜*")
        assert text_for(ELEMENTS[Segment], seg, CleanConfig()) == "粗 与 斜"
        assert text_for(ELEMENTS[Segment], seg, CleanConfig(bold=False)) == "**粗** 与 斜"

    def test_code_like_family_shares_one_recipe(self):
        """代码块、HTML 文档、Mermaid 共用同一份文本配方。"""
        code_text = ELEMENTS[CodeBlock].text
        assert ELEMENTS[HtmlDoc].text is code_text
        assert ELEMENTS[MermaidBlock].text is code_text


class TestSchemaConsistency:
    """_conf_schema.json 是静态文件派生不了，但能被钉住。"""

    @staticmethod
    def _items() -> dict:
        schema = json.loads((_ROOT / "_conf_schema.json").read_text(encoding="utf-8"))
        return schema["渲染"]["items"]

    def test_options_match_reachable_modes(self):
        """每个元素的 options 顺序与注册表的可达模式一致。"""
        items = self._items()
        for config in FAMILIES.values():
            assert items[config.label]["options"] == list(config.modes)

    def test_defaults_match(self):
        """配置默认值与注册表一致。"""
        items = self._items()
        for config in FAMILIES.values():
            assert items[config.label]["default"] == config.default

    def test_non_mode_render_keys_present(self):
        """「渲染」块里两个非元素配置项仍在 schema 中。"""
        items = self._items()
        assert {"HTML 宽度", "临时文件存活"} <= set(items)
