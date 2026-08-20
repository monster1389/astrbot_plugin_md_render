"""表格子域 —— 富文本数据模型与表格解析/还原。

从 parser 提炼：Span/RichCell/Table 模型、inline 格式栈遍历、
cell_to_markdown/table_to_markdown/table_to_plain 还原。
parse_table 是 markdown-it token 流的唯一入口，格内占位符还原
通过 restore 回调注入，本模块不依赖 parser 的数学占位符机制。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from markdown_it.token import Token


@dataclass
class Span:
    """富文本 Span——携带格式状态。"""
    text: str
    bold: bool = False
    italic: bool = False
    strike: bool = False
    code: bool = False
    link_url: str = ""


@dataclass
class RichCell:
    """富文本单元格。"""
    spans: list[Span]


@dataclass
class Table:
    """表格。"""
    headers: list[RichCell]
    rows: list[list[RichCell]]


def cell_to_markdown(cell: RichCell) -> str:
    """将单元格按装饰顺序还原为 markdown 文本。

    Args:
        cell: 富文本单元格。

    Returns:
        还原的 markdown 文本。
    """
    parts: list[str] = []
    for span in cell.spans:
        s = span.text
        if span.code:
            s = f"`{s}`"
        if span.strike:
            s = f"~~{s}~~"
        if span.italic:
            s = f"*{s}*"
        if span.bold:
            s = f"**{s}**"
        if span.link_url:
            s = f"[{s}]({span.link_url})"
        parts.append(s)
    return "".join(parts)


def table_to_markdown(table: Table) -> str:
    """将 Table 还原为 markdown 表格原文。

    Args:
        table: Table 实例。

    Returns:
        markdown 表格文本。
    """
    lines: list[str] = []
    lines.append("| " + " | ".join(cell_to_markdown(h) for h in table.headers) + " |")
    lines.append("|" + "|".join(["---" for _ in table.headers]) + "|")
    for row in table.rows:
        lines.append("| " + " | ".join(cell_to_markdown(c) for c in row) + " |")
    return "\n".join(lines)


def table_to_plain(table: Table) -> str:
    """将 Table 还原为精简纯文本：无外管、无分隔行。

    Args:
        table: Table 实例。

    Returns:
        以空格分隔的精简表格文本。
    """
    lines: list[str] = []
    lines.append(" | ".join(cell_to_markdown(h) for h in table.headers))
    for row in table.rows:
        lines.append(" | ".join(cell_to_markdown(c) for c in row))
    return "\n".join(lines)


def _extract_spans_from_children(tokens: list[Token]) -> list[Span]:
    """从 inline token 的 children 中提取 Span 列表。

    追踪 strong_open/close、em_open/close、s_open/close、
    code_inline、link_open/close 状态开关，为每段 text 生成
    携带当前格式状态的 Span。

    Args:
        tokens: inline token 的 children 列表。

    Returns:
        解析后的 Span 列表。
    """
    spans: list[Span] = []
    bold = False
    italic = False
    strike = False
    code = False
    link_url = ""
    for t in tokens:
        if t.type == "text":
            if t.content:
                spans.append(Span(t.content, bold=bold, italic=italic,
                                  strike=strike, code=code, link_url=link_url))
        elif t.type == "strong_open":
            bold = True
        elif t.type == "strong_close":
            bold = False
        elif t.type == "em_open":
            italic = True
        elif t.type == "em_close":
            italic = False
        elif t.type == "s_open":
            strike = True
        elif t.type == "s_close":
            strike = False
        elif t.type == "code_inline":
            spans.append(Span(t.content, bold=bold, italic=italic,
                              strike=strike, code=True, link_url=link_url))
        elif t.type == "link_open":
            link_url = t.attrs.get("href", "")
        elif t.type == "link_close":
            link_url = ""
        elif t.type == "softbreak":
            spans.append(Span(" ", bold=bold, italic=italic,
                              strike=strike, code=code, link_url=link_url))
    return spans


def _cell_spans(tokens: list[Token], restore: Callable[[str], str]) -> list[Span]:
    """从单元格 token 序列提取 Span 列表。

    Args:
        tokens: 单元格内 token 列表。
        restore: 文本后处理回调，用于还原格内占位符。

    Returns:
        解析后的 Span 列表。
    """
    spans: list[Span] = []
    for t in tokens:
        if t.type == "inline" and t.children:
            spans.extend(_extract_spans_from_children(t.children))
        elif t.type == "inline":
            spans.append(Span(text=t.content))
        elif t.type == "text":
            spans.append(Span(text=t.content))
        elif t.type == "softbreak":
            spans.append(Span(text=" "))
    for span in spans:
        span.text = restore(span.text)
    return spans


def parse_table(tokens: list[Token], start_idx: int, restore: Callable[[str], str]) -> tuple[Table, int]:
    """从 token 流中解析一个表格。

    Args:
        tokens: markdown-it-py token 列表。
        start_idx: table_open token 的索引。
        restore: 文本后处理回调，传给 _cell_spans 还原格内占位符。

    Returns:
        (解析后的 Table 对象, table_close 的下一个索引)。
    """
    headers: list[RichCell] = []
    rows: list[list[RichCell]] = []
    j = start_idx + 1
    in_head = True
    while j < len(tokens) and tokens[j].type != "table_close":
        tok = tokens[j]
        if tok.type == "thead_open":
            in_head = True
        elif tok.type == "tbody_open":
            in_head = False
        elif tok.type == "tr_open":
            row: list[RichCell] = []
            k = j + 1
            while k < len(tokens) and tokens[k].type != "tr_close":
                if tokens[k].type in ("th_open", "td_open"):
                    cell_tokens: list[Token] = []
                    k += 1
                    while k < len(tokens) and tokens[k].type not in ("th_close", "td_close"):
                        cell_tokens.append(tokens[k])
                        k += 1
                    row.append(RichCell(spans=_cell_spans(cell_tokens, restore)))
                k += 1
            if in_head and not headers:
                headers = row
            else:
                rows.append(row)
        j += 1
    return Table(headers=headers, rows=rows), j + 1
