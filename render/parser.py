"""Markdown 解析器 —— 使用 markdown-it-py 提取代码块/HTML 文档/图表/表格/表达式/分隔线。"""
from __future__ import annotations

import re
from dataclasses import dataclass

from markdown_it import MarkdownIt
from markdown_it.token import Token

from astrbot.api import logger
from render.table_domain import Table, parse_table

# 块级数学表达式只认行首 $$：行中出现的 $$ 属于正文（比如被反引号包住的 $$）
_BLOCK_MATH_OPEN_RE = re.compile(r"^[ \t]*\$\$")
_MATH_PLACEHOLDER_PREFIX = "\x01MATHBLOCK"
_MATH_PLACEHOLDER_RE = re.compile(r"\x01MATHBLOCK(\d+)\x01")

# 行内代码 span 占位符：识别 $...$ 前先屏蔽代码，避免把代码里的公式当公式
_CODE_PLACEHOLDER_PREFIX = "\x03CODE"
_CODE_PLACEHOLDER_RE = re.compile(r"\x03CODE(\d+)\x03")

# 判定 ```html 是否是完整文档：避免把讨论 HTML 片段的代码块渲染成图
_HTML_DOC_RE = re.compile(r"<!doctype|<html[\s>]", re.IGNORECASE)

# 匹配纯分隔线行：至少 3 个 - / * / _，允许空格穿插
_HR_LINE_RE = re.compile(
    r"^[ \t]*((?:-[ \t]*){3,}|(?:\*[ \t]*){3,}|(?:_[ \t]*){3,})[ \t]*$"
)

# 匹配闭合的 $...$ 对：内容 1-100 字符，首尾非空格，允许用 \$ 转义美元符
_INLINE_EXPR_RE = re.compile(
    r"(?<!\\)\$"
    r"((?:\\.|[^\s$])"
    r"(?:(?:\\.|[^$\n]){0,100}?"
    r"[^\s$])?)"
    r"(?<!\\)\$"
)

# 匹配围栏开行：行首（允许空白缩进）出现 3+ 个 ` 或 ~
_FENCE_OPEN_RE = re.compile(r"^[ \t]*(`{3,}|~{3,})")


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
class HtmlDoc:
    """完整 HTML 文档：```html 且含 <!DOCTYPE 或 <html>。"""
    code: str
    lang: str = "html"


@dataclass
class MermaidBlock:
    """Mermaid 图表源码。"""
    code: str
    lang: str = "mermaid"


def codeblock_to_markdown(cb: CodeBlock | HtmlDoc | MermaidBlock) -> str:
    """将代码块还原为 markdown 围栏原文。

    Args:
        cb: 代码块。

    Returns:
        带围栏标记的 markdown 文本。
    """
    return f"```{cb.lang}\n{cb.code}\n```"


def codeblock_to_plain(cb: CodeBlock | HtmlDoc | MermaidBlock) -> str:
    """将代码块还原为精简纯文本：仅代码。

    Args:
        cb: 代码块。

    Returns:
        不带围栏的纯代码文本。
    """
    return cb.code


@dataclass
class InlineExpr:
    """行内数学表达式 $...$。"""
    expr: str


@dataclass
class BlockExpr:
    """块级数学表达式 $$...$$。"""
    expr: str


def expr_to_markdown(e: InlineExpr | BlockExpr) -> str:
    """将表达式还原为 markdown 原文：行内 $..$ / 块级 $$..$$。

    Args:
        e: 行内或块级表达式。

    Returns:
        带 $ 分隔符的 markdown 文本。
    """
    if isinstance(e, BlockExpr):
        return f"$$\n{e.expr}\n$$"
    return f"${e.expr}$"


def expr_to_plain(e: InlineExpr | BlockExpr) -> str:
    """将表达式还原为精简纯文本：仅公式。

    Args:
        e: 行内或块级表达式。

    Returns:
        不带 $ 分隔符的公式文本。
    """
    return e.expr


@dataclass
class Divider:
    """分隔线 ---。"""
    pass


def _is_fence_close(line: str, fence_char: str, fence_len: int) -> bool:
    """判断行是否为当前围栏的闭合行。

    Args:
        line: 待判断行。
        fence_char: 开围栏字符（` 或 ~）。
        fence_len: 开围栏字符数。

    Returns:
        True 表示是闭合行。
    """
    stripped = line.lstrip()
    if not stripped.startswith(fence_char):
        return False
    count = len(stripped) - len(stripped.lstrip(fence_char))
    return count >= fence_len and stripped[count:].strip() == ""


def _mask_code_spans(text: str) -> tuple[str, list[str]]:
    """把行内代码 span 换成占位符，原样留存。

    行内代码里的 $ 不是公式分隔符，识别公式前必须先遮住。
    按 CommonMark 规则寻找等长的反引号闭合串，找不到闭合就当作普通文本。

    Args:
        text: 一段行内 markdown 源码。

    Returns:
        (遮住代码的文本, 代码 span 原文列表)。
    """
    out: list[str] = []
    codes: list[str] = []
    i = 0
    size = len(text)
    while i < size:
        if text[i] != "`":
            out.append(text[i])
            i += 1
            continue
        j = i
        while j < size and text[j] == "`":
            j += 1
        run = j - i
        close = -1
        k = j
        while k < size:
            k = text.find("`" * run, k)
            if k < 0:
                break
            end = k + run
            if (k == 0 or text[k - 1] != "`") and (end >= size or text[end] != "`"):
                close = k
                break
            k = end
        if close < 0:
            out.append(text[i:j])
            i = j
            continue
        codes.append(text[i:close + run])
        out.append(f"{_CODE_PLACEHOLDER_PREFIX}{len(codes) - 1}\x03")
        i = close + run
    return "".join(out), codes


def _unmask_code_spans(text: str, codes: list[str]) -> str:
    """把代码占位符还原为原文。

    Args:
        text: 含代码占位符的文本。
        codes: 代码 span 原文列表。

    Returns:
        还原后的文本。
    """
    def _replace(m: re.Match) -> str:
        return codes[int(m.group(1))]
    return _CODE_PLACEHOLDER_RE.sub(_replace, text)


def _find_unescaped(text: str, token: str, start: int = 0) -> int:
    """查找未被反斜杠转义的目标串。

    Args:
        text: 待搜索文本。
        token: 目标串，如 ``$$``。
        start: 开始搜索的位置。

    Returns:
        首次出现的位置；未找到或均被转义时返回 -1。
    """
    idx = start
    while True:
        idx = text.find(token, idx)
        if idx < 0:
            return -1
        backslashes = 0
        pos = idx - 1
        while pos >= 0 and text[pos] == "\\":
            backslashes += 1
            pos -= 1
        if backslashes % 2 == 0:
            return idx
        idx += len(token)


def _trailing_block_math_close(line: str) -> int:
    """判断行尾是否有未转义的 ``$$``，返回其位置。

    多行块级公式的闭合行可以是 ``$$``，也可以是 ``x = 1$$``。

    Args:
        line: 待判断行（可带换行）。

    Returns:
        行尾 ``$$`` 的起始位置；不是闭合行时返回 -1。
    """
    stripped = line.rstrip("\r\n").rstrip(" \t")
    if not stripped.endswith("$$"):
        return -1
    idx = len(stripped) - 2
    if _find_unescaped(stripped, "$$") != idx:
        return -1
    return idx


def _replace_inline_block_math(line: str, placeholders: dict[int, str]) -> str:
    """替换一行内成对的 ``$$...$$``。

    只在一行之内配对，不跨行：正文里零散的 ``$$`` 不会吞掉后续内容；
    表格单元格里的 ``$$E=mc^2$$`` 也能正常识别。

    Args:
        line: 单行文本（可带换行）。
        placeholders: 占位符索引到表达式内容的映射，原地填充。

    Returns:
        替换为占位符后的行。
    """
    out: list[str] = []
    cursor = 0
    while True:
        start = _find_unescaped(line, "$$", cursor)
        if start < 0:
            break
        end = _find_unescaped(line, "$$", start + 2)
        if end < 0:
            break
        expr = line[start + 2:end].strip()
        if not expr:
            cursor = end + 2
            continue
        out.append(line[cursor:start])
        placeholders[len(placeholders)] = expr
        out.append(f"{_MATH_PLACEHOLDER_PREFIX}{len(placeholders) - 1}\x01")
        cursor = end + 2
    out.append(line[cursor:])
    return "".join(out)


def _extract_block_math(chunk: str, placeholders: dict[int, str]) -> str:
    """从一段（无围栏的）文本中按行提取块级数学表达式。

    只认行首的 ``$$``：正文里随手出现的 ``$$``（比如被反引号
    包住的）不会开启匹配，不会把后续内容吃进一张图里。找不到闭合
    时整块按原文保留。

    Args:
        chunk: 不含围栏的 markdown 文本，行内代码已遮住。
        placeholders: 占位符索引到表达式内容的映射，原地填充。

    Returns:
        替换为占位符后的文本。
    """
    lines = chunk.splitlines(keepends=True)
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        m = _BLOCK_MATH_OPEN_RE.match(line)
        if not m:
            out.append(_replace_inline_block_math(line, placeholders))
            i += 1
            continue

        # 单行形式 $$expr$$（后面允许跟正文）
        after_open = line[m.end():]
        close = _find_unescaped(after_open, "$$")
        if close >= 0:
            expr = after_open[:close].strip()
            if expr:
                placeholders[len(placeholders)] = expr
                out.append(f"{_MATH_PLACEHOLDER_PREFIX}{len(placeholders) - 1}\x01")
                tail = after_open[close + 2:]
                if not tail.endswith("\n"):
                    tail += "\n"
                out.append(tail)
            else:
                out.append(line)
            i += 1
            continue

        # 多行形式：$$ 开行，闭合 $$ 在后续某行行尾
        body = [after_open]
        closed_at = -1
        for j in range(i + 1, len(lines)):
            pos = _trailing_block_math_close(lines[j])
            if pos >= 0:
                body.append(lines[j][:pos])
                closed_at = j
                break
            body.append(lines[j])

        expr = "".join(body).strip()
        if closed_at < 0 or not expr:
            out.append(line)
            i += 1
            continue
        placeholders[len(placeholders)] = expr
        out.append(f"{_MATH_PLACEHOLDER_PREFIX}{len(placeholders) - 1}\x01\n")
        i = closed_at + 1
    return "".join(out)


def _pre_extract_block_math(text: str) -> tuple[str, dict[int, str]]:
    """预提取块级数学表达式，替换为占位符。

    逐行扫描识别 ``` / ~~~ 围栏，围栏内的 $$...$$ 不提取，
    保证代码块内容字节级原样保留（markdown-it 的 fence token
    不走行内还原路径）。围栏外的行内代码也先遮住，
    代码里的 $$ 同样不能开启块级公式。

    Args:
        text: 原始 markdown 文本。

    Returns:
        (处理后的文本, {占位符索引: 表达式内容})
    """
    placeholders: dict[int, str] = {}
    out: list[str] = []
    buf: list[str] = []

    def flush() -> None:
        if not buf:
            return
        masked, codes = _mask_code_spans("".join(buf))
        buf.clear()
        first_new = len(placeholders)
        extracted = _extract_block_math(masked, placeholders)
        for idx in range(first_new, len(placeholders)):
            placeholders[idx] = _unmask_code_spans(placeholders[idx], codes)
        out.append(_unmask_code_spans(extracted, codes))

    fence_char: str | None = None
    fence_len = 0
    for line in text.splitlines(keepends=True):
        if fence_char is None:
            m = _FENCE_OPEN_RE.match(line)
            if m:
                flush()
                fence_char = m.group(1)[0]
                fence_len = len(m.group(1))
                out.append(line)
            else:
                buf.append(line)
        else:
            out.append(line)
            if _is_fence_close(line, fence_char, fence_len):
                fence_char = None
    flush()
    return "".join(out), placeholders


def _restore_block_math(text: str, block_math: dict[int, str]) -> str:
    """将文本中的块级数学占位符还原为 $expr$ 形式。

    用于表格单元格等未走 extract_inline_content 的路径，
    避免占位符作为可见文本泄漏。

    Args:
        text: 可能含占位符的文本。
        block_math: 占位符索引到表达式内容的映射。

    Returns:
        还原后的文本，未知占位符原样保留。
    """
    def _replace(m: re.Match) -> str:
        expr = block_math.get(int(m.group(1)))
        return f"${expr}$" if expr is not None else m.group(0)
    return _MATH_PLACEHOLDER_RE.sub(_replace, text)


def _classify_fence(info: str, code: str) -> CodeBlock | HtmlDoc | MermaidBlock:
    """按围栏语言与内容分型。

    只有完整 HTML 文档才走 HTML 渲染；HTML 片段仍是普通代码块，
    否则「讨论 HTML 语法」的代码块会被渲染成一张网页图。

    Args:
        info: 围栏语言标注原文。
        code: 围栏内代码。

    Returns:
        普通代码块、HTML 文档或 Mermaid 图表。
    """
    lang = info.split()[0].lower() if info else ""
    if lang in ("html", "htm") and _HTML_DOC_RE.search(code):
        return HtmlDoc(code=code)
    if lang == "mermaid":
        return MermaidBlock(code=code)
    return CodeBlock(lang=info, code=code)


def _split_hr_from_segments(
    segments: list[Segment | CodeBlock | HtmlDoc | MermaidBlock | Table | InlineExpr | BlockExpr | Divider],
    split_blank_lines: bool = False,
) -> list[Segment | CodeBlock | HtmlDoc | MermaidBlock | Table | InlineExpr | BlockExpr | Divider]:
    """后处理：从 Segment 文本中识别有空行包裹的分隔线，拆分为 Divider。

    仅当 --- / *** / ___ 前后有空行（\\n\\n）时才视为分隔线，
    歌词等场景中的无空行 --- 不会被误判。

    Args:
        segments: 初次解析后的片段列表。
        split_blank_lines: 为 True 时，非分隔线段落按空行各自独立成
            Segment 并丢弃段间 \\n\\n；为 False 时拼回单个 Segment。

    Returns:
        插入 Divider 后的片段列表。
    """
    result: list[Segment | CodeBlock | Table | InlineExpr | BlockExpr | Divider] = []
    for seg in segments:
        if not isinstance(seg, Segment):
            result.append(seg)
            continue
        paragraphs = seg.text.split("\n\n")
        if split_blank_lines:
            for para in paragraphs:
                if _HR_LINE_RE.match(para):
                    result.append(Divider())
                elif para.strip():
                    result.append(Segment(text=para))
            continue
        non_hr_parts: list[str] = []
        for para in paragraphs:
            if _HR_LINE_RE.match(para):
                if non_hr_parts:
                    result.append(Segment(text="\n\n".join(non_hr_parts)))
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


def split_inline_math(text: str) -> list[Segment | InlineExpr]:
    """把一段行内 markdown 源码拆成文本段与 ``$...$`` 表达式。

    行内代码 span 里的 ``$`` 不参与识别，原样留在文本段里。

    Args:
        text: 行内文本源码（可含反引号代码）。

    Returns:
        按出现顺序交替的 Segment / InlineExpr 列表。
    """
    masked, codes = _mask_code_spans(text)
    result: list[Segment | InlineExpr] = []
    cursor = 0
    for match in _INLINE_EXPR_RE.finditer(masked):
        expr = match.group(1)
        if not _is_valid_inline_expr(expr):
            continue
        if match.start() > cursor:
            result.append(Segment(text=_unmask_code_spans(masked[cursor:match.start()], codes)))
        result.append(InlineExpr(expr=expr))
        cursor = match.end()
    if cursor < len(masked):
        result.append(Segment(text=_unmask_code_spans(masked[cursor:], codes)))
    return result


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

        result.extend(split_inline_math(part))

    return result


def parse(text: str, split_blank_lines: bool = False) -> list[Segment | CodeBlock | HtmlDoc | MermaidBlock | Table | InlineExpr | BlockExpr | Divider]:
    """解析 markdown 文本，提取结构元素。

    Args:
        text: 原始 markdown 文本。
        split_blank_lines: 为 True 时，空行分隔的普通段落各自独立成 Segment。

    Returns:
        解析后的结构元素列表，按文本出现顺序排列。
    """
    # 预提取 $$...$$ 块级数学表达式，避免 markdown-it 将其当作文本处理
    processed_text, block_math = _pre_extract_block_math(text)

    md = MarkdownIt("zero").enable(["table", "strikethrough", "fence", "emphasis", "backticks", "link"])
    md.options["html"] = False
    tokens: list[Token] = md.parse(processed_text)
    segments: list[Segment | CodeBlock | HtmlDoc | MermaidBlock | Table | InlineExpr | BlockExpr | Divider] = []
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
            info = t.info.strip() if t.info else ""
            segments.append(_classify_fence(info, t.content.rstrip("\n")))
            i += 1
            continue

        if t.type == "table_open":
            flush_buf()
            table, i = parse_table(tokens, i, lambda s: _restore_block_math(s, block_math))
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
    return _split_hr_from_segments(segments, split_blank_lines)
