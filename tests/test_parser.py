"""解析器测试：从 Plain 文本提取代码块/表格/表达式/分隔线。"""
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
    parse,
    split_inline_math,
)
from render.table_domain import Table, table_to_markdown


class TestCodeBlock:
    def test_single_code_block(self):
        """单个代码块。"""
        text = '```python\ndef f(): pass\n```'
        segments = parse(text)
        assert len(segments) == 1
        seg = segments[0]
        assert isinstance(seg, CodeBlock)
        assert seg.lang == "python"
        assert seg.code == "def f(): pass"

    def test_inline_backticks_not_parsed(self):
        """行内 ``` 不算代码块分隔符。"""
        text = "用 ``` 包裹颜文字 ```吧"
        segments = parse(text)
        assert all(not isinstance(s, CodeBlock) for s in segments)

    def test_text_before_code_block(self):
        """代码块前的文本保留为 Segment。"""
        text = "看这段:\n```python\ndef f(): pass\n```"
        segments = parse(text)
        assert len(segments) == 2
        assert segments[0].text.strip() == "看这段:"
        assert isinstance(segments[1], CodeBlock)

    def test_text_after_code_block(self):
        """代码块后的文本保留为 Segment。"""
        text = "```python\ndef f(): pass\n```\n结束了"
        segments = parse(text)
        assert len(segments) == 2
        assert isinstance(segments[0], CodeBlock)
        assert segments[1].text.strip() == "结束了"


class TestExpr:
    def test_inline_expr(self):
        """行内表达式 $...$。"""
        text = "公式 $E=mc^2$ 在此"
        segments = parse(text)
        assert any(isinstance(s, InlineExpr) and s.expr == "E=mc^2" for s in segments)

    def test_escaped_dollar(self):
        r"""转义的 \$ 不作为表达式分隔符。"""
        text = r"价格 \$100 和 $E=mc^2$"
        segments = parse(text)
        inline_exprs = [s for s in segments if isinstance(s, InlineExpr)]
        assert len(inline_exprs) == 1
        assert inline_exprs[0].expr == "E=mc^2"
        plain_text = "".join(s.text for s in segments if isinstance(s, Segment))
        assert "\\$100" in plain_text or "$100" in plain_text

    def test_block_expr(self):
        """块级表达式 $$...$$。"""
        text = "$$\n\\int_0^\\infty e^{-x} dx\n$$"
        segments = parse(text)
        block_exprs = [s for s in segments if isinstance(s, BlockExpr)]
        assert len(block_exprs) == 1
        assert "\\int" in block_exprs[0].expr

    def test_unpaired_dollar_currency(self):
        """孤 $ 货币符号不视为表达式。"""
        text = "首月 $5、之后 $10。"
        segments = parse(text)
        inline_exprs = [s for s in segments if isinstance(s, InlineExpr)]
        assert len(inline_exprs) == 0
        plain_text = "".join(s.text for s in segments if isinstance(s, Segment))
        assert "$5" in plain_text
        assert "$10" in plain_text

    def test_mixed_currency_and_expr(self):
        """货币 $ 与表达式 $...$ 混合时只匹配后者。"""
        text = "$5，不打折 $E=mc^2$"
        segments = parse(text)
        inline_exprs = [s for s in segments if isinstance(s, InlineExpr)]
        assert len(inline_exprs) == 1
        assert inline_exprs[0].expr == "E=mc^2"
        plain_text = "".join(s.text for s in segments if isinstance(s, Segment))
        assert "$5" in plain_text

    def test_single_char_expr(self):
        """单字符行内表达式 $x$。"""
        text = "$x$"
        segments = parse(text)
        inline_exprs = [s for s in segments if isinstance(s, InlineExpr)]
        assert len(inline_exprs) == 1
        assert inline_exprs[0].expr == "x"

    def test_numeric_expr(self):
        """数字开头表达式 $1+2=3$。"""
        text = "$1+2=3$"
        segments = parse(text)
        inline_exprs = [s for s in segments if isinstance(s, InlineExpr)]
        assert len(inline_exprs) == 1
        assert inline_exprs[0].expr == "1+2=3"

    def test_escaped_dollar_inside_expr(self):
        r"""表达式内的 \$ 是内容，不是闭合符。"""
        text = r"美元 $\$9.99$，下划线 $a\_b$"
        segments = parse(text)
        inline_exprs = [s for s in segments if isinstance(s, InlineExpr)]
        assert [s.expr for s in inline_exprs] == [r"\$9.99", r"a\_b"]

    def test_inline_code_not_treated_as_expr(self):
        """行内代码里的 $...$ 保持原文，不渲染。"""
        text = "行内代码：`$\\frac{a}{b}$`、`\\alpha`、`$$E=mc^2$$`。"
        segments = parse(text)
        assert not any(isinstance(s, InlineExpr) for s in segments)
        assert not any(isinstance(s, BlockExpr) for s in segments)
        plain = "".join(s.text for s in segments if isinstance(s, Segment))
        assert "`$\\frac{a}{b}$`" in plain


class TestMathPipes:
    """公式里的竖线不能被 markdown 表格当成列分隔符。"""

    _HEAD = "| a | b | c | d |\n|---|---|---|---|\n"

    def _row(self, row: str):
        table = [
            s for s in parse(self._HEAD + row) if isinstance(s, Table)
        ][0]
        return table, table.rows[0]

    def test_pipe_inside_math_keeps_table_shape(self):
        """$|\\rho| > 0.8$ 留在同一格里，后两格不再被截掉。"""
        table, row = self._row(
            "| 判定 | 当 $|\\rho| > 0.8$ 时认为强相关 | 文字与公式混排 | 纯文本 |"
        )
        assert len(table.headers) == 4
        cells = ["".join(span.text for span in c.spans) for c in row]
        assert cells[1] == "当 $|\\rho| > 0.8$ 时认为强相关"
        assert cells[2] == "文字与公式混排"
        assert cells[3] == "纯文本"

    def test_pipe_math_becomes_inline_expr(self):
        """还原后的格内文本仍能被拆成行内公式。"""
        _, row = self._row("| 判定 | 当 $|x| > 0$ 时成立 | 说明 | 备注 |")
        parts = split_inline_math("".join(span.text for span in row[1].spans))
        exprs = [p.expr for p in parts if isinstance(p, InlineExpr)]
        assert exprs == ["|x| > 0"]

    def test_currency_dollars_do_not_change_shape(self):
        """两个货币 $ 之间的 | 仍是列分隔符。"""
        _, row = self._row("| 价格 | $5 | $10 | 备注 |")
        cells = ["".join(span.text for span in c.spans) for c in row]
        assert cells == ["价格", "$5", "$10", "备注"]

    def test_escaped_norm_is_preserved(self):
        """用户自己写的 \\| 是范数记号，不能被改成单竖线。"""
        _, row = self._row("| 范数 | $\\|v\\|$ | 双竖线 | 备注 |")
        cells = ["".join(span.text for span in c.spans) for c in row]
        assert cells[1] == "$\\|v\\|$"

    def test_pipe_math_in_paragraph(self):
        """正文里的竖线公式照常识别。"""
        segments = parse("绝对值 $|x|$ 与 $\\left|y\\right|$")
        exprs = [s.expr for s in segments if isinstance(s, InlineExpr)]
        assert exprs == ["|x|", "\\left|y\\right|"]

    def test_placeholder_never_leaks(self):
        """表格还原成 markdown 时不含任何控制字符。"""
        table, _ = self._row("| 判定 | 当 $|x| > 0$ 时成立 | 说明 | 备注 |")
        markdown = table_to_markdown(table)
        assert "\x01" not in markdown
        assert "\x04" not in markdown


class TestBlockExpr:
    def test_double_dollar_in_code_does_not_swallow(self):
        """正文里被反引号包住的 $$ 不会开启块级匹配，后续章节保留。"""
        text = (
            "裸文本里的危险货：`$`、`$$`、`\\`。\n\n"
            "## 5. Unicode\n\n上标：x²。\n\n"
            "## 6. 对齐\n\n$$\n\\begin{aligned}\na &= b\n\\end{aligned}\n$$\n\n结尾"
        )
        segments = parse(text)
        block_exprs = [s for s in segments if isinstance(s, BlockExpr)]
        assert len(block_exprs) == 1
        assert "begin{aligned}" in block_exprs[0].expr
        plain = "".join(s.text for s in segments if isinstance(s, Segment))
        assert "## 5. Unicode" in plain
        assert "上标：x²" in plain

    def test_unclosed_block_stays_text(self):
        """没有闭合的 $$ 按原文保留，不吃后续内容。"""
        text = "$$\n未闭合的公式\n\n后续正文"
        segments = parse(text)
        assert not any(isinstance(s, BlockExpr) for s in segments)
        plain = "".join(s.text for s in segments if isinstance(s, Segment))
        assert "后续正文" in plain

    def test_single_line_block_expr(self):
        """同一行内的 $$...$$ 仍是块级表达式。"""
        segments = parse("$$E=mc^2$$")
        block_exprs = [s for s in segments if isinstance(s, BlockExpr)]
        assert [s.expr for s in block_exprs] == ["E=mc^2"]

    def test_code_fence_double_dollar_untouched(self):
        """代码围栏里的 $$ 不抽取。"""
        text = "```latex\n$$x^2$$\n```"
        segments = parse(text)
        assert isinstance(segments[0], CodeBlock)
        assert segments[0].code == "$$x^2$$"


class TestDivider:
    def test_divider_with_blank_lines(self):
        """空行包裹的 --- 识别为分隔线。"""
        text = "上面\n\n---\n\n下面"
        segments = parse(text)
        dividers = [s for s in segments if isinstance(s, Divider)]
        assert len(dividers) == 1

    def test_divider_star_variant(self):
        """空行包裹的 *** 识别为分隔线。"""
        text = "上面\n\n***\n\n下面"
        segments = parse(text)
        dividers = [s for s in segments if isinstance(s, Divider)]
        assert len(dividers) == 1

    def test_divider_underscore_variant(self):
        """空行包裹的 ___ 识别为分隔线。"""
        text = "上面\n\n___\n\n下面"
        segments = parse(text)
        dividers = [s for s in segments if isinstance(s, Divider)]
        assert len(dividers) == 1

    def test_hr_in_lyrics_not_divider(self):
        """歌词中无极行包裹的 --- 不是分隔线，保留为文本。"""
        text = "寄り添うことだけさ\n---\nそう　僕らは"
        segments = parse(text)
        assert not any(isinstance(s, Divider) for s in segments)
        plain = "".join(s.text for s in segments if hasattr(s, "text"))
        assert "---" in plain

    def test_hr_without_blank_lines_not_divider(self):
        """无空行包裹的 --- 不是分隔线。"""
        text = "上面\n---\n下面"
        segments = parse(text)
        assert not any(isinstance(s, Divider) for s in segments)

    def test_divider_double_dash_not_divider(self):
        """只有两个 -- 不算分隔线。"""
        text = "上面\n\n--\n\n下面"
        segments = parse(text)
        assert not any(isinstance(s, Divider) for s in segments)

    def test_divider_splits_correctly(self):
        """分隔线正确分割段落。"""
        text = "上面\n\n---\n\n下面"
        segments = parse(text)
        assert len(segments) == 3
        assert isinstance(segments[0], Segment)
        assert isinstance(segments[1], Divider)
        assert isinstance(segments[2], Segment)
        assert segments[0].text == "上面"
        assert segments[2].text == "下面\n\n"


class TestMixed:
    def test_code_then_table(self):
        """代码块后跟表格。"""
        text = "```python\n1+1\n```\n| A |\n|---|\n| x |"
        segments = parse(text)
        types = [type(s) for s in segments]
        assert CodeBlock in types
        assert Table in types

    def test_plain_text_only(self):
        """纯文本无 markdown 元素。"""
        text = "这是一段普通文本，没有 markdown 元素。"
        segments = parse(text)
        assert len(segments) == 1
        assert isinstance(segments[0], Segment)
        assert not isinstance(segments[0], (CodeBlock, Table, InlineExpr, BlockExpr, Divider))


class TestBlankLineSplit:
    def test_split_blank_lines(self):
        """空行切分：段落各自独立成 Segment，丢弃 \\n\\n。"""
        text = "段落A\n\n段落B\n\n段落C"
        segments = parse(text, split_blank_lines=True)
        plains = [s for s in segments if isinstance(s, Segment)]
        assert [s.text for s in plains] == ["段落A", "段落B", "段落C"]

    def test_no_split_by_default(self):
        """默认不切分：段落拼回单个 Segment，保留 \\n\\n。"""
        text = "段落A\n\n段落B"
        segments = parse(text)
        assert len(segments) == 1
        assert isinstance(segments[0], Segment)
        assert segments[0].text == "段落A\n\n段落B\n\n"

    def test_split_single_paragraph(self):
        """无空行的单段文本：切分后仍是单个 Segment，丢弃段尾 \\n\\n。"""
        text = "段落A"
        segments = parse(text, split_blank_lines=True)
        assert len(segments) == 1
        assert isinstance(segments[0], Segment)
        assert segments[0].text == "段落A"

    def test_split_with_divider(self):
        """空行切分 + 分隔线：--- 仍识别为 Divider，普通段落独立。"""
        text = "段落A\n\n---\n\n段落B"
        segments = parse(text, split_blank_lines=True)
        assert len(segments) == 3
        assert isinstance(segments[0], Segment)
        assert isinstance(segments[1], Divider)
        assert isinstance(segments[2], Segment)
        assert segments[0].text == "段落A"
        assert segments[2].text == "段落B"

    def test_split_keeps_divider_blank_line_requirement(self):
        """空行切分不改变 --- 判定：无空行包裹的 --- 仍是文本。"""
        text = "上面\n---\n下面"
        segments = parse(text, split_blank_lines=True)
        assert not any(isinstance(s, Divider) for s in segments)
        plain = "".join(s.text for s in segments if isinstance(s, Segment))
        assert "---" in plain


class TestFenceClassification:
    """围栏语言与内容分型：HTML 文档 / Mermaid / 普通代码块。"""

    def test_html_doc(self):
        """含 <!DOCTYPE 的 html 围栏识别为 HTML 文档。"""
        text = "```html\n<!DOCTYPE html>\n<html><body>x</body></html>\n```"
        segments = parse(text)
        assert isinstance(segments[0], HtmlDoc)
        assert segments[0].lang == "html"

    def test_html_doc_without_doctype(self):
        """含 <html> 标签同样识别为文档。"""
        text = "```html\n<html><body>x</body></html>\n```"
        assert isinstance(parse(text)[0], HtmlDoc)

    def test_html_fragment_is_code_block(self):
        """HTML 片段仍是普通代码块，不渲染成网页图。"""
        text = "```html\n<div>hi</div>\n```"
        assert isinstance(parse(text)[0], CodeBlock)

    def test_mermaid(self):
        """mermaid 围栏识别为图表。"""
        text = "```mermaid\nsequenceDiagram\n  A->>B: hi\n```"
        segments = parse(text)
        assert isinstance(segments[0], MermaidBlock)
        assert segments[0].lang == "mermaid"

    def test_mermaid_uppercase(self):
        """语言标注大小写不敏感。"""
        text = "```Mermaid\ngraph LR\n  A-->B\n```"
        assert isinstance(parse(text)[0], MermaidBlock)


class TestBlockMathInFence:
    """$$...$$ 位于代码围栏内时原样保留，不预提取。"""

    def test_fence_content_preserved(self):
        """围栏内 $$...$$ 字节级保留。"""
        text = "```python\nx = 1\n$$E=mc^2$$\n```"
        segments = parse(text)
        assert len(segments) == 1
        assert isinstance(segments[0], CodeBlock)
        assert segments[0].code == "x = 1\n$$E=mc^2$$"

    def test_fence_with_info_string(self):
        """带 info 串的围栏内容同样保留。"""
        text = "``` python\ny = 2\n$$z$$\n```"
        segments = parse(text)
        assert isinstance(segments[0], CodeBlock)
        assert segments[0].lang == "python"
        assert segments[0].code == "y = 2\n$$z$$"

    def test_tilde_fence(self):
        """~~~ 围栏内 $$...$$ 保留。"""
        text = "~~~\n$$w$$\n~~~"
        segments = parse(text)
        assert isinstance(segments[0], CodeBlock)
        assert segments[0].code == "$$w$$"

    def test_unclosed_fence(self):
        """未闭合围栏到 EOF，$$...$$ 仍保留。"""
        text = "```\n$$y$$\n"
        segments = parse(text)
        assert isinstance(segments[0], CodeBlock)
        assert segments[0].code == "$$y$$"

    def test_math_outside_fence_still_extracted(self):
        """围栏外的 $$...$$ 仍是 BlockExpr。"""
        text = "$$\nE=mc^2\n$$\n\n```\n$$literal$$\n```"
        segments = parse(text)
        block_exprs = [s for s in segments if isinstance(s, BlockExpr)]
        assert len(block_exprs) == 1
        assert block_exprs[0].expr == "E=mc^2"
        code = next(s for s in segments if isinstance(s, CodeBlock))
        assert code.code == "$$literal$$"


class TestSerialization:
    """元素 → 原文序列化：与类型同居的还原函数。"""

    def test_codeblock_markdown(self):
        """代码块还原为围栏原文。"""
        assert codeblock_to_markdown(CodeBlock(lang="py", code="x=1")) == "```py\nx=1\n```"

    def test_codeblock_markdown_no_lang(self):
        """无语言标注的代码块围栏不带 info。"""
        assert codeblock_to_markdown(CodeBlock(lang="", code="x=1")) == "```\nx=1\n```"

    def test_codeblock_plain(self):
        """代码块还原为纯代码。"""
        assert codeblock_to_plain(CodeBlock(lang="py", code="x=1")) == "x=1"

    def test_inline_expr_markdown(self):
        """行内表达式还原为 $ 包裹原文。"""
        assert expr_to_markdown(InlineExpr(expr="E=mc^2")) == "$E=mc^2$"

    def test_block_expr_markdown(self):
        """块级表达式还原为 $$ 包裹原文。"""
        assert expr_to_markdown(BlockExpr(expr="E=mc^2")) == "$$\nE=mc^2\n$$"

    def test_expr_plain(self):
        """表达式还原为纯公式，行内/块级无差。"""
        assert expr_to_plain(InlineExpr(expr="x")) == "x"
        assert expr_to_plain(BlockExpr(expr="x")) == "x"
