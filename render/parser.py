"""Markdown 解析器 —— 使用 markdown-it-py 提取代码块/表格/表达式/分隔线。"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from markdown_it import MarkdownIt
from markdown_it.token import Token

logger = logging.getLogger(__name__)

# 用于标记预提取的 $$...$$ 块级数学表达式
_MATH_BLOCK_RE = re.compile(r"\$\$(.+?)\$\$", re.DOTALL)
_MATH_PLACEHOLDER_PREFIX = "\x01MATHBLOCK"
_MATH_PLACEHOLDER_RE = re.compile(r"\x01MATHBLOCK(\d+)\x01")


@dataclass
class Segment:
    """纯文本片段。"""
    text: str


@dataclass
class CodeBlock:
    """代码块。"""
    lang: str
    code: str


@dataclass
class Table:
    """表格。"""
    headers: list[str]
    rows: list[list[str]]


@dataclass
class InlineExpr:
    """行内数学表达式 $...$。"""
    expr: str


@dataclass
class BlockExpr:
    """块级数学表达式 $$...$$。"""
    expr: str


@dataclass
class Divider:
    """分隔线 ---。"""
    pass


def _extract_text(tokens: list[Token]) -> str:
    """从 token 序列中提取纯文本内容。

    Args:
        tokens: markdown-it-py token 列表。

    Returns:
        拼接后的纯文本字符串。
    """
    parts: list[str] = []
    for t in tokens:
        if t.type == "inline":
            parts.append(t.content)
        elif t.type in ("text", "code_inline"):
            parts.append(t.content)
        elif t.children:
            parts.append(_extract_text(t.children))
    return "".join(parts)


def _cell_text(tokens: list[Token]) -> str:
    """提取表格单元格的纯文本（去除 markdown 标记）。

    Args:
        tokens: 单元格内 token 列表。

    Returns:
        去除首尾空格后的纯文本字符串。
    """
    return _extract_text(tokens).strip()


def _pre_extract_block_math(text: str) -> tuple[str, dict[int, str]]:
    """预提取 $$...$$ 块级数学表达式，替换为占位符。

    Args:
        text: 原始 markdown 文本。

    Returns:
        (处理后的文本, {占位符索引: 表达式内容})
    """
    placeholders: dict[int, str] = {}
    idx = 0

    def _replace(m: re.Match) -> str:
        nonlocal idx
        expr = m.group(1).strip()
        placeholders[idx] = expr
        placeholder = f"{_MATH_PLACEHOLDER_PREFIX}{idx}\x01"
        idx += 1
        return placeholder

    processed = _MATH_BLOCK_RE.sub(_replace, text)
    return processed, placeholders


def _parse_table(tokens: list[Token], start_idx: int) -> tuple[Table, int]:
    """从 token 流中解析一个表格。

    Args:
        tokens: markdown-it-py token 列表。
        start_idx: table_open token 的索引。

    Returns:
        (解析后的 Table 对象, table_close 的下一个索引)。
    """
    headers: list[str] = []
    rows: list[list[str]] = []
    j = start_idx + 1
    in_head = True
    while j < len(tokens) and tokens[j].type != "table_close":
        tok = tokens[j]
        if tok.type == "thead_open":
            in_head = True
        elif tok.type == "tbody_open":
            in_head = False
        elif tok.type == "tr_open":
            row: list[str] = []
            k = j + 1
            while k < len(tokens) and tokens[k].type != "tr_close":
                if tokens[k].type in ("th_open", "td_open"):
                    cell_tokens: list[Token] = []
                    k += 1
                    while k < len(tokens) and tokens[k].type not in ("th_close", "td_close"):
                        cell_tokens.append(tokens[k])
                        k += 1
                    row.append(_cell_text(cell_tokens))
                k += 1
            if in_head:
                headers = row
            else:
                rows.append(row)
        j += 1
    return Table(headers=headers, rows=rows), j + 1


def extract_inline_content(
    content: str,
    block_math: dict[int, str],
) -> list[Segment | InlineExpr | BlockExpr]:
    """从行内文本中拆出占位符（块级表达式）和 $...$ 行内表达式。

    优先级：先检查块级表达式占位符，再拆分 $...$。

    Args:
        content: 行内文本内容。
        block_math: 块级数学表达式占位符映射，键为占位符索引，值为表达式内容。

    Returns:
        解析后的 Segment/InlineExpr/BlockExpr 列表。
    """
    result: list[Segment | InlineExpr | BlockExpr] = []

    # 按块级表达式占位符切分
    parts = _MATH_PLACEHOLDER_RE.split(content)
    for part_idx, part in enumerate(parts):
        # 偶数索引为普通文本（可能含 $），奇数索引为占位符序号
        if part_idx % 2 == 1:
            # 占位符序号 —— 转换为 BlockExpr
            if part.isdigit():
                math_idx = int(part)
                if math_idx in block_math:
                    result.append(BlockExpr(expr=block_math[math_idx]))
                else:
                    logger.warning(
                        "找不到占位符索引 %d 的块级数学表达式，block_math 中无对应条目",
                        math_idx,
                    )
            continue

        if not part:
            continue

        # 在普通文本中拆分 $...$ 行内表达式
        dollar_parts = part.split("$")
        for i, p in enumerate(dollar_parts):
            if i % 2 == 1:
                if p.strip():
                    result.append(InlineExpr(expr=p.strip()))
            else:
                if p:
                    result.append(Segment(text=p))

    return result


def parse(text: str) -> list[Segment | CodeBlock | Table | InlineExpr | BlockExpr | Divider]:
    """解析 markdown 文本，提取结构元素。

    Args:
        text: 原始 markdown 文本。

    Returns:
        解析后的结构元素列表，按文本出现顺序排列。
    """
    # 预提取 $$...$$ 块级数学表达式，避免 markdown-it 将其当作文本处理
    processed_text, block_math = _pre_extract_block_math(text)

    md = MarkdownIt("zero").enable(["table", "strikethrough", "fence", "hr"])
    md.options["html"] = False
    tokens: list[Token] = md.parse(processed_text)
    segments: list[Segment | CodeBlock | Table | InlineExpr | BlockExpr | Divider] = []
    text_buf: list[str] = []

    def flush_buf() -> None:
        """将文本缓冲区内容作为 Segment 输出。"""
        content = "".join(text_buf)
        if content:
            segments.append(Segment(text=content))
        text_buf.clear()

    i = 0
    while i < len(tokens):
        t = tokens[i]

        if t.type == "fence":
            flush_buf()
            lang = t.info.strip() if t.info else ""
            segments.append(CodeBlock(lang=lang, code=t.content.rstrip("\n")))
            i += 1
            continue

        if t.type == "table_open":
            flush_buf()
            table, i = _parse_table(tokens, i)
            segments.append(table)
            continue

        if t.type == "inline" and t.content:
            # 检查是否包含 $ 或块级表达式占位符
            if "$" in t.content or _MATH_PLACEHOLDER_PREFIX in t.content:
                flush_buf()
                segments.extend(extract_inline_content(t.content, block_math))
            else:
                text_buf.append(t.content)
            i += 1
            continue

        if t.type == "hr":
            flush_buf()
            segments.append(Divider())
            i += 1
            continue

        # markdown-it-py 结构 token，仅用于嵌套关系，不承载文本
        if t.type in ("paragraph_open", "paragraph_close", "bullet_list_open",
                       "bullet_list_close", "list_item_open", "list_item_close",
                       "ordered_list_open", "ordered_list_close", "blockquote_open",
                       "blockquote_close", "em_open", "em_close", "strong_open",
                       "strong_close", "heading_open", "heading_close", "link_open",
                       "link_close", "code_block", "softbreak", "hardbreak",
                       "s_open", "s_close", "tbody_open", "tbody_close",
                       "thead_open", "thead_close", "th_open", "th_close",
                       "td_open", "td_close", "tr_open", "tr_close",
                       "math_inline", "math_block"):
            if t.type == "paragraph_close":
                text_buf.append("\n\n")
            i += 1
            continue

        text_content = _extract_text([t])
        if text_content:
            text_buf.append(text_content)
        i += 1

    flush_buf()
    return segments
