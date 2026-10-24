"""元素注册表 —— 「一种元素怎么活」的唯一出处。

每种 markdown 元素在这里登记一份 ``Element``：怎么渲染、怎么还原文本、走哪个配置
项、产物文件名前缀、由哪个清洗开关管、是否块级、是否自带超时预算。分组、模式查表、
产物命名、配置读取、日志汇总全部从这张表派生，加一种元素只改这里。

**元素类型**与**元素族**是两个概念：``InlineExpr`` 与 ``BlockExpr`` 是两个元素类型，
共用 ``expr`` 族 —— 同一个配置项、同一个产物前缀。``FAMILIES`` 是族的视图。
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from render.code_render import render_code
from render.expr_render import render_expr
from render.html_render import render_html
from render.md_cleaner import clean_markdown
from render.mermaid_render import render_mermaid
from render.parser import (
    BlockExpr,
    CodeBlock,
    Divider,
    HtmlDoc,
    InlineExpr,
    MermaidBlock,
    Segment,
    codeblock_to_markdown,
    codeblock_to_plain,
    expr_to_markdown,
    expr_to_plain,
)
from render.table_domain import Table, table_to_markdown, table_to_plain
from render.table_render import render_table

if TYPE_CHECKING:
    from render.config import CleanConfig


@dataclass(frozen=True)
class ModeSpec:
    """模式 → 产物配方：text/image/file 三个插槽是否填充。

    Attributes:
        text: 是否产出原文 Plain。
        image: 是否产出渲染 PNG。
        file: 是否产出 .md 文件。
    """
    text: bool
    image: bool
    file: bool


# 联合能力表：模式字符串 → 产物配方。配置边界（_conf_schema.json）保持中文字符串，
# 此表即这些字符串唯一的解释处。各元素族的可达模式是其子集（表达式与 HTML 无 md 文件模式）。
_MODE_SPECS: dict[str, ModeSpec] = {
    "不处理":           ModeSpec(text=True,  image=False, file=False),
    "渲染图像":         ModeSpec(text=False, image=True,  file=False),
    "渲染且保留原文":     ModeSpec(text=True,  image=True,  file=False),
    "渲染且md文件":      ModeSpec(text=False, image=True,  file=True),
    "仅md文件":         ModeSpec(text=False, image=False, file=True),
}

# 无配置模式的元素（纯文本段 / 分隔线）固定只产纯文本
_TEXT_ONLY = ModeSpec(text=True, image=False, file=False)

# 可达模式子集，顺序即 _conf_schema.json 里 options 的顺序
_ALL_MODES: tuple[str, ...] = tuple(_MODE_SPECS)
_NO_FILE_MODES: tuple[str, ...] = ("不处理", "渲染图像", "渲染且保留原文")


@dataclass(frozen=True)
class ElementConfig:
    """元素族的配置身份：配置项、默认值、可达模式。

    Attributes:
        key: 族键，同时是产物文件名前缀与 ``RenderConfig.modes`` 的键。
        label: 中文配置项名，同时是日志里的元素标签。
        default: 该元素的默认模式。
        modes: 可达模式子集。
    """
    key: str
    label: str
    default: str
    modes: tuple[str, ...]


@dataclass(frozen=True)
class TextRecipe:
    """元素的两种文本形态。

    Attributes:
        to_plain: 清洗开时的裸文本（只含内容，不含 markdown 包裹）。
        to_markdown: markdown 原文（清洗关、需要原文或落 .md 文件时用）。
    """
    to_plain: Callable[[Any, CleanConfig], str]
    to_markdown: Callable[[Any], str]


def _plain_of(fn: Callable[[Any], str]) -> Callable[[Any, CleanConfig], str]:
    """把只吃 segment 的还原函数适配成裸文本配方。

    Args:
        fn: 接收 segment、返回裸文本的函数。

    Returns:
        符合 ``TextRecipe.to_plain`` 签名的函数。
    """
    def plain(seg: Any, _clean: CleanConfig) -> str:
        return fn(seg)
    return plain


def _prose_plain(seg: Segment, clean: CleanConfig) -> str:
    """纯文本段清洗后的文本。"""
    return clean_markdown(seg.text, clean)


def _prose_markdown(seg: Segment) -> str:
    """纯文本段原文。"""
    return seg.text


def _divider_plain(_seg: Divider, _clean: CleanConfig) -> str:
    """分隔线清洗后只剩段落间隔。"""
    return "\n\n"


def _divider_markdown(_seg: Divider) -> str:
    """分隔线原文。"""
    return "\n\n---\n\n"


_CODE_TEXT = TextRecipe(to_plain=_plain_of(codeblock_to_plain), to_markdown=codeblock_to_markdown)
_TABLE_TEXT = TextRecipe(to_plain=_plain_of(table_to_plain), to_markdown=table_to_markdown)
_EXPR_TEXT = TextRecipe(to_plain=_plain_of(expr_to_plain), to_markdown=expr_to_markdown)
_PROSE_TEXT = TextRecipe(to_plain=_prose_plain, to_markdown=_prose_markdown)
_DIVIDER_TEXT = TextRecipe(to_plain=_divider_plain, to_markdown=_divider_markdown)


@dataclass(frozen=True)
class Element:
    """一种元素的全部事实。

    Attributes:
        render: 渲染函数，返回 PNG bytes；None 表示不渲染（纯文本元素）。
            这是链上入口，不是元素图的唯一入口：表格格内的公式走
            ``expr_render.formula_image``，不进 chain。
        text: 两种文本配方。
        config: 配置身份；None 表示该元素没有配置模式（纯文本段 / 分隔线）。
        clean: 管这个元素的 ``CleanConfig`` 字段名；None 表示无单一开关，
            只要配置存在就走清洗（纯文本段）。
        block: 是否块级元素（自身独立成组，前后文本各自成组）。
        budgeted: 渲染器自带超时预算（如外部 HTTP），不套通用保险丝。
    """
    render: Callable[[Any], bytes] | None
    text: TextRecipe
    config: ElementConfig | None = None
    clean: str | None = None
    block: bool = False
    budgeted: bool = False

    @property
    def prefix(self) -> str:
        """产物文件名前缀。

        Returns:
            族键。

        Raises:
            RuntimeError: 该元素没有配置模式，也就不产生产物。
        """
        if self.config is None:
            raise RuntimeError("该元素没有配置模式，不产生产物文件")
        return self.config.key


_CODE_CFG = ElementConfig(key="code", label="代码块", default="渲染且md文件", modes=_ALL_MODES)
_TABLE_CFG = ElementConfig(key="table", label="表格", default="渲染图像", modes=_ALL_MODES)
_MERMAID_CFG = ElementConfig(key="mermaid", label="Mermaid", default="渲染图像", modes=_ALL_MODES)
_EXPR_CFG = ElementConfig(key="expr", label="表达式", default="渲染图像", modes=_NO_FILE_MODES)
_HTML_CFG = ElementConfig(key="html", label="HTML", default="渲染图像", modes=_NO_FILE_MODES)


ELEMENTS: dict[type, Element] = {
    CodeBlock: Element(
        render=render_code,
        text=_CODE_TEXT,
        config=_CODE_CFG,
        clean="code",
        block=True,
    ),
    Table: Element(
        render=render_table,
        text=_TABLE_TEXT,
        config=_TABLE_CFG,
        clean="table",
        block=True,
    ),
    HtmlDoc: Element(
        render=render_html,
        text=_CODE_TEXT,
        config=_HTML_CFG,
        clean="code",
        block=True,
    ),
    MermaidBlock: Element(
        render=render_mermaid,
        text=_CODE_TEXT,
        config=_MERMAID_CFG,
        clean="code",
        block=True,
        budgeted=True,
    ),
    InlineExpr: Element(
        render=render_expr,
        text=_EXPR_TEXT,
        config=_EXPR_CFG,
        clean="expr",
    ),
    BlockExpr: Element(
        render=render_expr,
        text=_EXPR_TEXT,
        config=_EXPR_CFG,
        clean="expr",
        block=True,
    ),
    Segment: Element(render=None, text=_PROSE_TEXT),
    Divider: Element(render=None, text=_DIVIDER_TEXT, clean="divider"),
}


FAMILIES: dict[str, ElementConfig] = {
    element.config.key: element.config
    for element in ELEMENTS.values()
    if element.config is not None
}


def recipe_for(element: Element, modes: dict[str, str]) -> ModeSpec:
    """元素本次应填充的产物配方。

    Args:
        element: 元素条目。
        modes: 元素族键 → 模式字符串（来自 RenderConfig.modes）。

    Returns:
        该元素本次的产物配方；无配置模式的元素固定产文本。
    """
    if element.config is None:
        return _TEXT_ONLY
    return _MODE_SPECS[modes[element.config.key]]


def writes_file(element: Element) -> bool:
    """该元素是否可能产出 .md 文件。

    由可达模式派生（哪个模式填了 file 插槽），不再单独维护能力位。

    Args:
        element: 元素条目。

    Returns:
        True 表示某条可达模式会写 .md。
    """
    if element.config is None:
        return False
    return any(_MODE_SPECS[mode].file for mode in element.config.modes)


def text_for(element: Element, seg: Any, clean: CleanConfig | None) -> str:
    """按清洗配置选该元素的文本形态。

    清洗未配置、或管这个元素的开关关着，都给 markdown 原文；否则给裸文本。
    ``clean_cfg`` 为 None 表示调用方没有清洗配置，一律原文。

    Args:
        element: 元素条目。
        seg: segment 实例。
        clean: 清洗配置，None 表示没有清洗配置。

    Returns:
        该元素本次应输出的文本。
    """
    if clean is not None and (element.clean is None or getattr(clean, element.clean)):
        return element.text.to_plain(seg, clean)
    return element.text.to_markdown(seg)
