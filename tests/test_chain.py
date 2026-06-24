"""消息链组装与分段测试。"""
from unittest.mock import patch

from render.parser import BlockExpr, CodeBlock, Divider, InlineExpr, Segment, Table
from render.utils import RenderConfig


def _make_cfg(**overrides):
    """构造测试用 RenderConfig，支持按需覆盖。"""
    defaults = {
        "code_mode": "不处理",
        "table_mode": "不处理",
        "expr_mode": "不处理",
        "divider_mode": "不处理",
        "font_color": "#000",
        "bg_color": "#FFF",
        "glyph_mapping": {},
        "temp_ttl": 5,
    }
    return RenderConfig(**(defaults | overrides))


class TestBuildChain:
    def test_noop_plain_text(self):
        """不处理的 Plain 文本原样传出。"""
        from render.chain import build_chain

        segments = [Segment(text="Hello")]
        cfg = _make_cfg()
        result = build_chain(segments, cfg, "/tmp")
        assert len(result) == 1
        assert result[0]["type"] == "Plain"
        assert result[0]["text"] == "Hello"

    def test_code_noop_keeps_original(self):
        """代码块不处理：还原为 markdown 原文。"""
        from render.chain import build_chain

        segments = [CodeBlock(lang="py", code="x=1")]
        cfg = _make_cfg(code_mode="不处理")
        result = build_chain(segments, cfg, "/tmp")
        assert len(result) == 1
        assert result[0]["type"] == "Plain"
        assert "```py" in result[0]["text"]

    @patch("render.chain.render_code")
    def test_code_render_image(self, mock_render):
        """代码块渲染图像模式：只有 Image 没有 File 也没有原文。"""
        from render.chain import build_chain

        mock_render.return_value = ("/tmp/code_001.png", "/tmp/code_001.txt")
        segments = [CodeBlock(lang="py", code="x=1")]
        cfg = _make_cfg(code_mode="渲染图像")
        result = build_chain(segments, cfg, "/tmp")
        assert len(result) == 1  # Image only, no File
        assert result[0]["type"] == "Image"

    @patch("render.chain.render_code")
    def test_code_render_with_txt(self, mock_render):
        """渲染且txt：Image + File。"""
        from render.chain import build_chain

        mock_render.return_value = ("/tmp/code_001.png", "/tmp/code_001.txt")
        segments = [CodeBlock(lang="py", code="x=1")]
        cfg = _make_cfg(code_mode="渲染且txt")
        result = build_chain(segments, cfg, "/tmp")
        assert result[0]["type"] == "Image"
        assert result[1]["type"] == "File"

    @patch("render.chain.render_code")
    def test_code_keep_original(self, mock_render):
        """渲染且保留原文：原文 Plain + Image，无 File。"""
        from render.chain import build_chain

        mock_render.return_value = ("/tmp/code_001.png", "/tmp/code_001.txt")
        segments = [CodeBlock(lang="py", code="x=1")]
        cfg = _make_cfg(code_mode="渲染且保留原文")
        result = build_chain(segments, cfg, "/tmp")
        assert len(result) == 2  # Plain + Image only, no File
        assert result[0]["type"] == "Plain"
        assert "x=1" in result[0]["text"]
        assert result[1]["type"] == "Image"

    @patch("render.chain.render_table")
    def test_table_render_image(self, mock_render):
        """表格渲染图像模式。"""
        from render.chain import build_chain

        mock_render.return_value = "/tmp/table_001.png"
        segments = [Table(headers=["A"], rows=[["1"]])]
        cfg = _make_cfg(table_mode="渲染图像")
        result = build_chain(segments, cfg, "/tmp")
        assert result[0]["type"] == "Image"

    def test_divider_split(self):
        """分隔线切分模式：产生 divider 标记。"""
        from render.chain import build_chain

        segments = [Segment(text="上"), Divider(), Segment(text="下")]
        cfg = _make_cfg(divider_mode="切分")
        result = build_chain(segments, cfg, "/tmp")
        types = [c["type"] for c in result]
        assert "divider" in types

    @patch("render.chain.render_inline_expr")
    def test_inline_expr_render_image(self, mock_render):
        """行内表达式渲染图像模式。"""
        from render.chain import build_chain

        mock_render.return_value = "/tmp/expr_001.png"
        segments = [InlineExpr(expr="E=mc^2")]
        cfg = _make_cfg(expr_mode="渲染图像")
        result = build_chain(segments, cfg, "/tmp")
        assert len(result) == 1
        assert result[0]["type"] == "Image"

    @patch("render.chain.render_block_expr")
    def test_block_expr_noop(self, mock_render):
        """块级表达式不处理：还原为 markdown 原文。"""
        from render.chain import build_chain

        segments = [BlockExpr(expr="\\int x dx")]
        cfg = _make_cfg(expr_mode="不处理")
        result = build_chain(segments, cfg, "/tmp")
        assert len(result) == 1
        assert result[0]["type"] == "Plain"
        assert "$$" in result[0]["text"]
        mock_render.assert_not_called()


class TestSplitChain:
    def test_single_plain(self):
        """单个 Plain 段留在末段。"""
        from render.chain import split_chain

        chain = [{"type": "Plain", "text": "你好"}]
        front, last = split_chain(chain)
        assert len(front) == 0
        assert len(last) == 1

    def test_plain_with_attachments(self):
        """Plain + Image → 同段，最后一段留末段。"""
        from render.chain import split_chain

        chain = [
            {"type": "Plain", "text": "看:"},
            {"type": "Image", "path": "/tmp/code.png"},
            {"type": "Plain", "text": "结束"},
        ]
        front, last = split_chain(chain)
        assert len(front) == 1
        assert len(front[0]) == 2
        assert len(last) == 1
        assert last[0]["text"] == "结束"

    def test_divider_splits(self):
        """divider 标记处断开。"""
        from render.chain import split_chain

        chain = [
            {"type": "Plain", "text": "上"},
            {"type": "divider"},
            {"type": "Plain", "text": "下"},
        ]
        front, last = split_chain(chain)
        assert len(front) == 1
        assert front[0][0]["text"] == "上"
        assert len(last) == 1
        assert last[0]["text"] == "下"
