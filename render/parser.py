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

# 匹配纯分隔线行：至少 3 个 - / * / _，允许空格穿插
_HR_LINE_RE = re.compile(
    r"^[ \t]*((?:-[ \t]*){3,}|(?:\*[ \t]*){3,}|(?:_[ \t]*){3,})[ \t]*$"
)

# 匹配闭合的 $...$ 对：内容 1-100 非 $ 非换行字符，首尾非空格
_INLINE_EXPR_RE = re.compile(
    r"(?<!\\)\$"
    r"([^\s$]"
    r"(?:[^$\n]{0,100}"
    r"[^\s$])?)"
    r"\$"
)
# 用于拆分行内表达式占位符
_INLINE_PLACEHOLDER_RE = re.compile(r"\x02INLINEEXPR(\d+)\x02")


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


def _cell_spans(tokens: list[Token]) -> list[Span]:
    """从单元格 token 序列提取 Span 列表。

    Args:
        tokens: 单元格内 token 列表。

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
    return spans


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
                    row.append(RichCell(spans=_cell_spans(cell_tokens)))
                k += 1
            if in_head and not headers:
                headers = row
            else:
                rows.append(row)
        j += 1
    return Table(headers=headers, rows=rows), j + 1


def _split_hr_from_segments(
    segments: list[Segment | CodeBlock | Table | InlineExpr | BlockExpr | Divider],
) -> list[Segment | CodeBlock | Table | InlineExpr | BlockExpr | Divider]:
    """后处理：从 Segment 文本中识别有空行包裹的分隔线，拆分为 Divider。

    仅当 --- / *** / ___ 前后有空行（\\n\\n）时才视为分隔线，
    歌词等场景中的无空行 --- 不会被误判。

    Args:
        segments: 初次解析后的片段列表。

    Returns:
        插入 Divider 后的片段列表。
    """
    result: list[Segment | CodeBlock | Table | InlineExpr | BlockExpr | Divider] = []
    for seg in segments:
        if not isinstance(seg, Segment):
            result.append(seg)
            continue
        paragraphs = seg.text.split("\n\n")
        non_hr_parts: list[str] = []
        for para in paragraphs:
            if _HR_LINE_RE.match(para):
                if non_hr_parts:
                    result.append(Segment(text="\n\n".join(non_hr_parts) + "\n\n"))
                    non_hr_parts.clear()
                result.append(Divider())
            else:
                if para:
                    non_hr_parts.append(para)
                elif non_hr_parts:
                    non_hr_parts.append("")
        if non_hr_parts:
            result.append(Segment(text="\n\n".join(non_hr_parts)))
    return result


def _is_valid_inline_expr(content: str) -> bool:
    """检查 $...$ 内容是否像 LaTeX 表达式而非自然语言。

    Args:
        content: $...$ 之间的内容。

    Returns:
        True 表示应作为表达式渲染。
    """
    if not content or not content.strip():
        return False
    if len(content) > 100:
        return False
    if "\n" in content:
        return False
    for c in content:
        if "一" <= c <= "鿿":
            return False
    return True


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

        # 在普通文本中查找闭合 $...$ 对，校验后替换为占位符
        inline_exprs: dict[int, str] = {}
        idx = 0

        def _replace(m: re.Match) -> str:
            nonlocal idx
            expr = m.group(1)
            if _is_valid_inline_expr(expr):
                inline_exprs[idx] = expr
                placeholder = f"\x02INLINEEXPR{idx}\x02"
                idx += 1
                return placeholder
            return m.group(0)

        processed = _INLINE_EXPR_RE.sub(_replace, part)

        # 按占位符切分，交替组装 Segment / InlineExpr
        inline_parts = _INLINE_PLACEHOLDER_RE.split(processed)
        for sub_i, sub_part in enumerate(inline_parts):
            if sub_i % 2 == 1 and sub_part.isdigit():
                expr_idx = int(sub_part)
                if expr_idx in inline_exprs:
                    result.append(InlineExpr(expr=inline_exprs[expr_idx]))
            else:
                if sub_part:
                    result.append(Segment(text=sub_part))

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

    md = MarkdownIt("zero").enable(["table", "strikethrough", "fence", "emphasis", "backticks", "link"])
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

        if t.content:
            text_buf.append(t.content)
        i += 1

    flush_buf()
    return _split_hr_from_segments(segments)
