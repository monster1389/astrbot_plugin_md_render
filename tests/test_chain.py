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
        "temp_ttl": 5,
    }
    return RenderConfig(**(defaults | overrides))


def _make_clean_cfg(**overrides):
    """构造测试用 CleanConfig，经典字段默认 True，code/table/expr 默认 False。"""
    defaults = vars(CleanConfig()).copy()
    for k in defaults:
        if k not in ("code", "table", "expr"):
            defaults[k] = True
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

    def test_divider_split_mode_consumes_divider(self):
        """分隔线切分模式：去掉 ---，两侧独立为 Plain 不黏连。"""
        from render.chain import build_chain

        segments = [Segment(text="上"), Divider(), Segment(text="下")]
        cfg = _make_cfg(divider_mode="切分")
        result = asyncio.run(build_chain(segments, cfg, None, "/tmp"))
        assert len(result) == 2
        assert all(isinstance(c, Plain) for c in result)
        assert result[0].text == "上"
        assert result[1].text == "下"

    def test_divider_noop_outputs_text(self):
        """分隔线不处理模式：输出 --- 文本，保留段落分隔。"""
        from render.chain import build_chain

        segments = [Segment(text="上"), Divider(), Segment(text="下")]
        cfg = _make_cfg(divider_mode="不处理")
        result = asyncio.run(build_chain(segments, cfg, None, "/tmp"))
        assert len(result) == 3
        assert isinstance(result[1], Plain)
        assert "---" in result[1].text

    def test_divider_noop_with_cleaning_keeps_breaks(self):
        """分隔线不处理 + 清洗：Segment 末尾 \n\n 清洗后保留，配合 Divider 的 \n\n 分段。"""
        from render.chain import build_chain

        segments = [Segment(text="前面\n\n"), Divider(), Segment(text="**后面**")]
        cfg = _make_cfg(divider_mode="不处理")
        clean_cfg = _make_clean_cfg()
        result = asyncio.run(build_chain(segments, cfg, clean_cfg, "/tmp"))
        full = "".join(c.text for c in result)
        # Segment 末尾 \n\n 被清洗保留 + Divider 输出 \n\n---\n\n，共 4 个 \n
        assert "前面\n\n\n\n---\n\n后面" in full

    def test_divider_split_with_cleaning_preserves_separation(self):
        """切分模式 + 清洗：Divider 两侧段落保留 \n\n 分隔，不会被 splitter 合并。"""
        from render.chain import build_chain

        segments = [Segment(text="好，第一轮回顾 (。-`ω´-)\n\n"), Divider(), Segment(text="**测试 1：纯闲聊**")]
        cfg = _make_cfg(divider_mode="切分")
        clean_cfg = _make_clean_cfg()
        result = asyncio.run(build_chain(segments, cfg, clean_cfg, "/tmp"))
        assert len(result) == 2
        assert isinstance(result[0], Plain)
        assert isinstance(result[1], Plain)
        # 清洗保留末尾 \n\n，确保分割器能识别段落边界
        assert result[0].text == "好，第一轮回顾 (。-`ω´-)\n\n"
        assert result[1].text == "测试 1：纯闲聊"

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


class TestBuildChainWithCleaning:
    def test_cleaning_applied_to_segment_text(self):
        """清洗在 Segment 文本上执行，去除 markdown 格式。"""
        from render.chain import build_chain

        segments = [Segment(text="**粗体** 普通 *斜体*")]
        cfg = _make_cfg()
        clean_cfg = _make_clean_cfg()
        result = asyncio.run(build_chain(segments, cfg, clean_cfg, "/tmp"))
        assert len(result) == 1
        assert isinstance(result[0], Plain)
        assert result[0].text == "粗体 普通 斜体"

    def test_cleaning_skipped_when_none(self):
        """clean_cfg=None 时不清洗，原样保留。"""
        from render.chain import build_chain

        segments = [Segment(text="**粗体**")]
        cfg = _make_cfg()
        result = asyncio.run(build_chain(segments, cfg, None, "/tmp"))
        assert result[0].text == "**粗体**"

    def test_cleaning_all_off_preserves_text(self):
        """清洗全关时原样保留。"""
        from render.chain import build_chain

        segments = [Segment(text="**粗体**")]
        cfg = _make_cfg()
        clean_cfg = _make_clean_cfg(bold=False, italic=False, strikethrough=False,
                                     inline_code=False, link=False, heading=False,
                                     list_unordered=False, list_ordered=False,
                                     blockquote=False, image=False)
        result = asyncio.run(build_chain(segments, cfg, clean_cfg, "/tmp"))
        assert result[0].text == "**粗体**"

    @patch("render.chain.render_code")
    def test_code_render_unaffected_by_cleaning(self, mock_render):
        """代码块渲染不受清洗影响，只有 Segment 被清洗。"""
        from render.chain import build_chain

        mock_render.return_value = (b"fake_png", "```py\nx=1\n```")
        segments = [CodeBlock(lang="py", code="x=1"), Segment(text="**尾注**")]
        cfg = _make_cfg(code_mode="渲染图像")
        clean_cfg = _make_clean_cfg()
        result = asyncio.run(build_chain(segments, cfg, clean_cfg, "/tmp"))
        assert len(result) == 2
        assert isinstance(result[0], Image)  # 代码块正常渲染
        assert isinstance(result[1], Plain)
        assert result[1].text == "尾注"  # Segment 被清洗

    def test_clean_code_block_on_unprocessed(self):
        """代码块清洗：不处理模式下去除 fence 标记。"""
        from render.chain import build_chain

        segments = [CodeBlock(lang="py", code="x=1")]
        cfg = _make_cfg(code_mode="不处理")
        clean_cfg = _make_clean_cfg(code=True)
        result = asyncio.run(build_chain(segments, cfg, clean_cfg, "/tmp"))
        assert len(result) == 1
        assert isinstance(result[0], Plain)
        assert result[0].text == "x=1"

    def test_clean_code_off_unprocessed_preserves_fence(self):
        """默认关：代码块原文保留 fence。"""
        from render.chain import build_chain

        segments = [CodeBlock(lang="py", code="x=1")]
        cfg = _make_cfg(code_mode="不处理")
        clean_cfg = _make_clean_cfg()  # code=False by default
        result = asyncio.run(build_chain(segments, cfg, clean_cfg, "/tmp"))
        assert "```py" in result[0].text

    @patch("render.chain.render_code")
    def test_clean_code_with_keep_original(self, mock_render):
        """渲染且保留原文 + 清洗：原文去 fence，图片正常。"""
        from render.chain import build_chain

        mock_render.return_value = (b"fake_png", "```py\nx=1\n```")
        segments = [CodeBlock(lang="py", code="x=1")]
        cfg = _make_cfg(code_mode="渲染且保留原文")
        clean_cfg = _make_clean_cfg(code=True)
        result = asyncio.run(build_chain(segments, cfg, clean_cfg, "/tmp"))
        assert len(result) == 2
        assert isinstance(result[0], Plain)
        assert result[0].text == "x=1"
        assert isinstance(result[1], Image)

    def test_clean_table_on_unprocessed(self):
        """表格清洗：不处理模式下精简表格格式。"""
        from render.chain import build_chain

        tbl = Table(
            headers=[
                RichCell(spans=[Span(text="名称")]),
                RichCell(spans=[Span(text="版本")]),
            ],
            rows=[[
                RichCell(spans=[Span(text="A")]),
                RichCell(spans=[Span(text="v1")]),
            ]],
        )
        segments = [tbl]
        cfg = _make_cfg(table_mode="不处理")
        clean_cfg = _make_clean_cfg(table=True)
        result = asyncio.run(build_chain(segments, cfg, clean_cfg, "/tmp"))
        assert len(result) == 1
        assert isinstance(result[0], Plain)
        assert "名称 | 版本" in result[0].text
        assert "A | v1" in result[0].text
        assert "|---" not in result[0].text

    def test_clean_expr_on_unprocessed(self):
        """表达式清洗：不处理模式下去除 $ 定界符。"""
        from render.chain import build_chain

        segments = [InlineExpr(expr="E=mc^2")]
        cfg = _make_cfg(expr_mode="不处理")
        clean_cfg = _make_clean_cfg(expr=True)
        result = asyncio.run(build_chain(segments, cfg, clean_cfg, "/tmp"))
        assert len(result) == 1
        assert isinstance(result[0], Plain)
        assert result[0].text == "E=mc^2"


class TestMergeChain:
    def test_image_preserved(self):
        """原链中的 Image 组件在合并后保留。"""
        from render.chain import merge_chain

        original = [Image.fromFileSystem("/tmp/ava.png"), Plain("角色数据")]
        built = [Plain("角色数据")]
        result = merge_chain(original, built)
        assert len(result) == 2
        assert isinstance(result[0], Image)
        assert isinstance(result[1], Plain)
        assert result[1].text == "角色数据"

    def test_file_preserved(self):
        """原链中的 File 组件在合并后保留。"""
        from render.chain import merge_chain

        original = [AstrFile(name="doc.md", file="/tmp/doc.md"), Plain("文本")]
        built = [Plain("文本")]
        result = merge_chain(original, built)
        assert len(result) == 2
        assert isinstance(result[0], AstrFile)
        assert isinstance(result[1], Plain)

    def test_multiple_non_plain_preserved(self):
        """多个非 Plain 组件均保留，按原顺序前置。"""
        from render.chain import merge_chain

        original = [
            Image.fromFileSystem("/tmp/a.png"),
            AstrFile(name="b.md", file="/tmp/b.md"),
            Plain("文本"),
        ]
        built = [Plain("文本")]
        result = merge_chain(original, built)
        assert len(result) == 3
        assert isinstance(result[0], Image)
        assert isinstance(result[1], AstrFile)
        assert isinstance(result[2], Plain)

    def test_plain_only_chain_unchanged(self):
        """纯 Plain 原链：built 直接返回，不添加额外组件。"""
        from render.chain import merge_chain

        original = [Plain("Hello")]
        built = [Plain("Hello")]
        result = merge_chain(original, built)
        assert len(result) == 1
        assert isinstance(result[0], Plain)
        assert result[0].text == "Hello"

    def test_empty_original_preserves_built(self):
        """空原链直接返回 built。"""
        from render.chain import merge_chain

        built = [Plain("text")]
        result = merge_chain([], built)
        assert result == built
