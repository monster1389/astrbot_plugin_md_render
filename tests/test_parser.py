"""解析器测试：从 Plain 文本提取代码块/表格/表达式/分隔线。"""
from render.parser import (
    parse,
    table_to_markdown,
    Segment,
    CodeBlock,
    RichCell,
    Span,
    Table,
    InlineExpr,
    BlockExpr,
    Divider,
)


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
