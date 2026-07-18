"""消息链组装与分段测试。"""
import asyncio
from unittest.mock import patch

from astrbot.api.message_components import Plain, Image, File as AstrFile

from render.parser import BlockExpr, CodeBlock, Divider, InlineExpr, RichCell, Segment, Span, Table
from render.utils import RenderConfig, CleanConfig


def _make_cfg(**overrides):
    """构造测试用 RenderConfig，支持按需覆盖。"""
    defaults = {
        "code_mode": "不处理",
        "table_mode": "不处理",
        "expr_mode": "不处理",
        "divider_mode": "不处理",
        "font_color": "#000",
        "bg_color": "#FFF",
        "temp_ttl": 5,
    }
    return RenderConfig(**(defaults | overrides))


def _make_clean_cfg(**overrides):
    """构造测试用 CleanConfig。"""
    defaults = {k: True for k in vars(CleanConfig())}
    defaults.update(overrides)
    return CleanConfig(**defaults)


class TestBuildChain:
    def test_noop_plain_text(self):
        """不处理的 Plain 文本原样传出。"""
        from render.chain import build_chain

        segments = [Segment(text="Hello")]
        cfg = _make_cfg()
        result = asyncio.run(build_chain(segments, cfg, None, "/tmp"))
        assert len(result) == 1
        assert isinstance(result[0], Plain)
        assert result[0].text == "Hello"

    def test_code_noop_keeps_original(self):
        """代码块不处理：还原为 markdown 原文。"""
        from render.chain import build_chain

        segments = [CodeBlock(lang="py", code="x=1")]
        cfg = _make_cfg(code_mode="不处理")
        result = asyncio.run(build_chain(segments, cfg, None, "/tmp"))
        assert len(result) == 1
        assert isinstance(result[0], Plain)
        assert "```py" in result[0].text

    @patch("render.chain.render_code")
    def test_code_render_image(self, mock_render):
        """代码块渲染图像模式：只有 Image 没有 File 也没有原文。"""
        from render.chain import build_chain

        mock_render.return_value = (b"fake_png_data", "```py\nx=1\n```")
        segments = [CodeBlock(lang="py", code="x=1")]
        cfg = _make_cfg(code_mode="渲染图像")
        result = asyncio.run(build_chain(segments, cfg, None, "/tmp"))
        assert len(result) == 1
        assert isinstance(result[0], Image)

    @patch("render.chain.render_code")
    def test_code_render_with_md(self, mock_render):
        """渲染且md文件：Image + File。"""
        from render.chain import build_chain

        mock_render.return_value = (b"fake_png_data", "```py\nx=1\n```")
        segments = [CodeBlock(lang="py", code="x=1")]
        cfg = _make_cfg(code_mode="渲染且md文件")
        result = asyncio.run(build_chain(segments, cfg, None, "/tmp"))
        assert isinstance(result[0], Image)
        assert isinstance(result[1], AstrFile)

    @patch("render.chain.render_code")
    def test_code_keep_original(self, mock_render):
        """渲染且保留原文：原文 Plain + Image，无 File。"""
        from render.chain import build_chain

        mock_render.return_value = (b"fake_png_data", "```py\nx=1\n```")
        segments = [CodeBlock(lang="py", code="x=1")]
        cfg = _make_cfg(code_mode="渲染且保留原文")
        result = asyncio.run(build_chain(segments, cfg, None, "/tmp"))
        assert len(result) == 2
        assert isinstance(result[0], Plain)
        assert "x=1" in result[0].text
        assert isinstance(result[1], Image)

    @patch("render.chain.render_table")
    def test_table_render_image(self, mock_render):
        """表格渲染图像模式。"""
        from render.chain import build_chain

        mock_render.return_value = b"fake_png_data"
        segments = [Table(headers=[RichCell(spans=[Span(text="A")])], rows=[[RichCell(spans=[Span(text="1")])]])]
        cfg = _make_cfg(table_mode="渲染图像")
        result = asyncio.run(build_chain(segments, cfg, None, "/tmp"))
        assert isinstance(result[0], Image)

    def test_divider_split(self):
        """分隔线切分模式：不产生 Component（保留给外部 splitter）。"""
        from render.chain import build_chain

        segments = [Segment(text="上"), Divider(), Segment(text="下")]
        cfg = _make_cfg(divider_mode="切分")
        result = asyncio.run(build_chain(segments, cfg, None, "/tmp"))
        assert len(result) == 2
        assert all(isinstance(c, Plain) for c in result)

    @patch("render.chain.render_inline_expr")
    def test_inline_expr_render_image(self, mock_render):
        """行内表达式渲染图像模式。"""
        from render.chain import build_chain

        mock_render.return_value = b"fake_png_data"
        segments = [InlineExpr(expr="E=mc^2")]
        cfg = _make_cfg(expr_mode="渲染图像")
        result = asyncio.run(build_chain(segments, cfg, None, "/tmp"))
        assert len(result) == 1
        assert isinstance(result[0], Image)

    @patch("render.chain.render_block_expr")
    def test_block_expr_noop(self, mock_render):
        """块级表达式不处理：还原为 markdown 原文。"""
        from render.chain import build_chain

        segments = [BlockExpr(expr="\\int x dx")]
        cfg = _make_cfg(expr_mode="不处理")
        result = asyncio.run(build_chain(segments, cfg, None, "/tmp"))
        assert len(result) == 1
        assert isinstance(result[0], Plain)
        assert "$$" in result[0].text
        mock_render.assert_not_called()

    @patch("render.chain.render_code")
    def test_code_render_failure_fallback(self, mock_render):
        """代码块渲染失败时回退为 Plain 原文，不影响后续段落。"""
        from render.chain import build_chain
        from render.utils import RenderConfig

        mock_render.side_effect = RuntimeError("Pygments crashed")
        cfg = RenderConfig(
            code_mode="渲染图像", table_mode="不处理",
            expr_mode="不处理", divider_mode="不处理",
            font_color="#000", bg_color="#FFF",
            temp_ttl=5,
        )
        segments = [CodeBlock(lang="py", code="x=1"), Segment(text="后续文本")]
        result = asyncio.run(build_chain(segments, cfg, None, "/tmp"))
        assert isinstance(result[0], Plain)
        assert "```py" in result[0].text
        assert isinstance(result[1], Plain)
        assert result[1].text == "后续文本"

    @patch("render.chain.render_code")
    def test_code_render_failure_keep_original_mode(self, mock_render):
        """渲染且保留原文模式下渲染失败，只回退为原文（不重复）。"""
        from render.chain import build_chain
        from render.utils import RenderConfig

        mock_render.side_effect = RuntimeError("Pygments crashed")
        cfg = RenderConfig(
            code_mode="渲染且保留原文", table_mode="不处理",
            expr_mode="不处理", divider_mode="不处理",
            font_color="#000", bg_color="#FFF",
            temp_ttl=5,
        )
        segments = [CodeBlock(lang="py", code="x=1")]
        result = asyncio.run(build_chain(segments, cfg, None, "/tmp"))
        assert len(result) == 1
        assert isinstance(result[0], Plain)

    @patch("render.chain.render_code")
    def test_code_md_only(self, mock_render):
        """仅md文件模式：只有 File 没有 Image，不调渲染。"""
        from render.chain import build_chain

        segments = [CodeBlock(lang="py", code="x=1")]
        cfg = _make_cfg(code_mode="仅md文件")
        result = asyncio.run(build_chain(segments, cfg, None, "/tmp"))
        assert len(result) == 1
        assert isinstance(result[0], AstrFile)
        mock_render.assert_not_called()

    @patch("render.chain.render_table")
    def test_table_md_only(self, mock_render):
        """仅md文件模式：只有 File 没有 Image，不调渲染。"""
        from render.chain import build_chain

        segments = [Table(headers=[RichCell(spans=[Span(text="A")])], rows=[[RichCell(spans=[Span(text="1")])]])]
        cfg = _make_cfg(table_mode="仅md文件")
        result = asyncio.run(build_chain(segments, cfg, None, "/tmp"))
        assert len(result) == 1
        assert isinstance(result[0], AstrFile)
        mock_render.assert_not_called()

    @patch("render.chain.render_table")
    def test_table_render_and_md(self, mock_render):
        """渲染且md文件模式：Image + File，无 Plain 原文。"""
        from render.chain import build_chain

        mock_render.return_value = b"fake_png_data"
        segments = [Table(headers=[RichCell(spans=[Span(text="A")])], rows=[[RichCell(spans=[Span(text="1")])]])]
        cfg = _make_cfg(table_mode="渲染且md文件")
        result = asyncio.run(build_chain(segments, cfg, None, "/tmp"))
        assert len(result) == 2
        assert isinstance(result[0], Image)
        assert isinstance(result[1], AstrFile)

    @patch("render.chain.render_code")
    def test_code_zero_ttl_uses_frombytes(self, mock_render):
        """temp_ttl=0 时代码块用 Image.fromBytes，不走文件落盘。"""
        from render.chain import build_chain

        mock_render.return_value = (b"fake_png_data", "```py\nx=1\n```")
        segments = [CodeBlock(lang="py", code="x=1")]
        cfg = _make_cfg(code_mode="渲染图像", temp_ttl=0)
        result = asyncio.run(build_chain(segments, cfg, None, "/tmp"))
        assert len(result) == 1
        img = result[0]
        assert isinstance(img, Image)
        assert hasattr(img, "data") and img.data == b"fake_png_data"
        assert not hasattr(img, "file")

    @patch("render.chain.render_table")
    def test_table_zero_ttl_uses_frombytes(self, mock_render):
        """temp_ttl=0 时表格用 Image.fromBytes，不走文件落盘。"""
        from render.chain import build_chain

        mock_render.return_value = b"fake_png_data"
        segments = [Table(headers=[RichCell(spans=[Span(text="A")])], rows=[[RichCell(spans=[Span(text="1")])]])]
        cfg = _make_cfg(table_mode="渲染图像", temp_ttl=0)
        result = asyncio.run(build_chain(segments, cfg, None, "/tmp"))
        assert len(result) == 1
        img = result[0]
        assert isinstance(img, Image)
        assert hasattr(img, "data") and img.data == b"fake_png_data"
        assert not hasattr(img, "file")

    @patch("render.chain.render_inline_expr")
    def test_expr_zero_ttl_uses_frombytes(self, mock_render):
        """temp_ttl=0 时表达式用 Image.fromBytes，不走文件落盘。"""
        from render.chain import build_chain

        mock_render.return_value = b"fake_png_data"
        segments = [InlineExpr(expr="E=mc^2")]
        cfg = _make_cfg(expr_mode="渲染图像", temp_ttl=0)
        result = asyncio.run(build_chain(segments, cfg, None, "/tmp"))
        assert len(result) == 1
        img = result[0]
        assert isinstance(img, Image)
        assert hasattr(img, "data") and img.data == b"fake_png_data"
        assert not hasattr(img, "file")
