"""解析器测试：从 Plain 文本提取代码块/表格/表达式/分隔线。"""
from render.parser import parse, Segment, CodeBlock, Table, InlineExpr, BlockExpr, Divider


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
        assert seg.headers == ["A", "B"]
        assert seg.rows == [["1", "2"]]

    def test_table_with_padding(self):
        """含空格填充的表格。"""
        text = "| 姓名 | 年龄 |\n|------|------|\n| 张三 |  20  |"
        segments = parse(text)
        assert len(segments) == 1
        seg = segments[0]
        assert isinstance(seg, Table)
        assert seg.headers == ["姓名", "年龄"]
        assert seg.rows == [["张三", "20"]]


class TestExpr:
    def test_inline_expr(self):
        """行内表达式 $...$。"""
        text = "公式 $E=mc^2$ 在此"
        segments = parse(text)
        assert any(isinstance(s, InlineExpr) and s.expr == "E=mc^2" for s in segments)

    def test_block_expr(self):
        """块级表达式 $$...$$。"""
        text = "$$\n\\int_0^\\infty e^{-x} dx\n$$"
        segments = parse(text)
        assert any(isinstance(s, BlockExpr) for s in segments)


class TestDivider:
    def test_divider(self):
        """分隔线 ---。"""
        text = "上面\n---\n下面"
        segments = parse(text)
        dividers = [s for s in segments if isinstance(s, Divider)]
        assert len(dividers) == 1

    def test_divider_with_spaces(self):
        """含空格分隔线 - - -。"""
        text = "上面\n- - -\n下面"
        segments = parse(text)
        assert any(isinstance(s, Divider) for s in segments)


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
