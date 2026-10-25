"""消息链组装与分段测试。"""
import asyncio
from functools import partial
from unittest.mock import MagicMock, patch

import pytest
from factories import clean_cfg as _clean_cfg
from factories import collect as _collect
from factories import render_cfg as _render_cfg_base
from factories import segment_cfg as _segment_cfg

from render.artifacts import Picture, SourceFile, Text
from render.parser import (
    BlockExpr,
    CodeBlock,
    Divider,
    HtmlDoc,
    InlineExpr,
    MermaidBlock,
    Segment,
)
from render.table_domain import RichCell, Span, Table

# 这些用例测链组装与顺序，fake 渲染器返回假字节，量化由 test_png.py 覆盖
pytestmark = pytest.mark.usefixtures("no_quantize")

# 本文件测落盘产物：默认 ttl=5，图片写进 data_dir
_render_cfg = partial(_render_cfg_base, temp_ttl=5)

# 默认分段配置：不切分、无延时。需定制的用例在方法内局部覆盖。
seg_cfg = _segment_cfg()


class TestBuildChain:
    def test_noop_plain_text(self, tmp_path):
        """不处理的纯文本原样传出。"""
        from render.chain import build_chain

        segments = [Segment(text="Hello")]
        cfg = _render_cfg()
        result = asyncio.run(build_chain(segments, cfg, None, str(tmp_path)))
        assert len(result) == 1
        assert isinstance(result[0], Text)
        assert result[0].text == "Hello"

    def test_code_noop_keeps_original(self, tmp_path):
        """代码块不处理：还原为 markdown 原文。"""
        from render.chain import build_chain

        segments = [CodeBlock(lang="py", code="x=1")]
        cfg = _render_cfg(code="不处理")
        result = asyncio.run(build_chain(segments, cfg, None, str(tmp_path)))
        assert len(result) == 1
        assert isinstance(result[0], Text)
        assert "```py" in result[0].text

    def test_code_render_image(self, tmp_path):
        """代码块渲染图像模式：只有 Image 没有 File 也没有原文。"""
        from render.chain import build_chain

        fake = MagicMock(return_value=b"fake_png_data")
        segments = [CodeBlock(lang="py", code="x=1")]
        cfg = _render_cfg(code="渲染图像")
        result = asyncio.run(build_chain(segments, cfg, None, str(tmp_path), renderers={CodeBlock: fake}))
        assert len(result) == 1
        assert isinstance(result[0], Picture)

    def test_async_renderer_is_awaited(self, tmp_path):
        """协程渲染器直接 await，不丢进线程池。"""
        from render.chain import build_chain

        async def fake(seg):
            return b"fake_png_data"

        cfg = _render_cfg(code="渲染图像")
        result = asyncio.run(
            build_chain([CodeBlock(lang="py", code="x=1")], cfg, None, str(tmp_path), renderers={CodeBlock: fake})
        )
        assert len(result) == 1
        assert isinstance(result[0], Picture)

    def test_html_render_image(self, tmp_path):
        """HTML 文档渲染图像模式。"""
        from render.chain import build_chain

        fake = MagicMock(return_value=b"fake_png_data")
        cfg = _render_cfg(html="渲染图像")
        result = asyncio.run(
            build_chain([HtmlDoc(code="<html></html>")], cfg, None, str(tmp_path), renderers={HtmlDoc: fake})
        )
        assert len(result) == 1
        assert isinstance(result[0], Picture)

    def test_html_noop_keeps_fence(self, tmp_path):
        """HTML 文档不处理：还原为 ```html 围栏原文。"""
        from render.chain import build_chain

        cfg = _render_cfg(html="不处理")
        result = asyncio.run(build_chain([HtmlDoc(code="<html></html>")], cfg, None, str(tmp_path)))
        assert len(result) == 1
        assert isinstance(result[0], Text)
        assert "```html" in result[0].text

    def test_html_keep_original(self, tmp_path):
        """HTML 渲染且保留原文：文本 + 图片。"""
        from render.chain import build_chain

        fake = MagicMock(return_value=b"fake_png_data")
        cfg = _render_cfg(html="渲染且保留原文")
        result = asyncio.run(
            build_chain([HtmlDoc(code="<html></html>")], cfg, None, str(tmp_path), renderers={HtmlDoc: fake})
        )
        assert len(result) == 2
        assert isinstance(result[0], Text)
        assert isinstance(result[1], Picture)

    def test_mermaid_render_and_md(self, tmp_path):
        """Mermaid 渲染且md文件：Image + File。"""
        from render.chain import build_chain

        fake = MagicMock(return_value=b"fake_png_data")
        cfg = _render_cfg(mermaid="渲染且md文件")
        result = asyncio.run(
            build_chain([MermaidBlock(code="graph LR")], cfg, None, str(tmp_path), renderers={MermaidBlock: fake})
        )
        assert len(result) == 2
        assert isinstance(result[0], Picture)
        assert isinstance(result[1], SourceFile)

    def test_mermaid_render_image(self, tmp_path):
        """Mermaid 图表渲染图像模式。"""
        from render.chain import build_chain

        fake = MagicMock(return_value=b"fake_png_data")
        cfg = _render_cfg(mermaid="渲染图像")
        result = asyncio.run(
            build_chain([MermaidBlock(code="graph LR")], cfg, None, str(tmp_path), renderers={MermaidBlock: fake})
        )
        assert len(result) == 1
        assert isinstance(result[0], Picture)

    def test_render_failure_emits_md_file(self, tmp_path):
        """渲染异常时出 .md 文件（文件是保底形态），不回退源码文本。"""
        from render.chain import build_chain

        def boom(_seg):
            raise RuntimeError("boom")

        cfg = _render_cfg(mermaid="渲染图像")
        result = asyncio.run(
            build_chain([MermaidBlock(code="graph LR")], cfg, None, str(tmp_path), renderers={MermaidBlock: boom})
        )
        assert len(result) == 1
        assert isinstance(result[0], SourceFile)
        with open(result[0].path, encoding="utf-8") as f:
            assert "```mermaid" in f.read()

    def test_expr_render_failure_falls_back_to_text(self, tmp_path):
        """表达式不支持 .md 文件，渲染异常时回退原文。"""
        from render.chain import build_chain

        def boom(_seg):
            raise RuntimeError("boom")

        cfg = _render_cfg(expr="渲染图像")
        result = asyncio.run(
            build_chain([InlineExpr(expr="x")], cfg, None, str(tmp_path), renderers={InlineExpr: boom})
        )
        assert isinstance(result[0], Text)

    def test_render_failure_with_md_mode_still_writes_file(self, tmp_path):
        """图渲染失败但配置了 md 文件：仍写 .md，不回退原文。"""
        from render.chain import build_chain

        def boom(_seg):
            raise RuntimeError("boom")

        cfg = _render_cfg(mermaid="渲染且md文件")
        result = asyncio.run(
            build_chain([MermaidBlock(code="graph LR")], cfg, None, str(tmp_path), renderers={MermaidBlock: boom})
        )
        assert len(result) == 1
        assert isinstance(result[0], SourceFile)
        with open(result[0].path, encoding="utf-8") as f:
            assert "```mermaid" in f.read()

    def test_mermaid_md_only(self, tmp_path):
        """仅md文件模式：只有 File 没有 Image，不调渲染。"""
        from render.chain import build_chain

        fake = MagicMock(return_value=b"fake_png_data")
        cfg = _render_cfg(mermaid="仅md文件")
        result = asyncio.run(
            build_chain([MermaidBlock(code="graph LR")], cfg, None, str(tmp_path), renderers={MermaidBlock: fake})
        )
        assert len(result) == 1
        assert isinstance(result[0], SourceFile)
        fake.assert_not_called()

    def test_code_render_with_md(self, tmp_path):
        """渲染且md文件：Image + File。"""
        from render.chain import build_chain

        fake = MagicMock(return_value=b"fake_png_data")
        segments = [CodeBlock(lang="py", code="x=1")]
        cfg = _render_cfg(code="渲染且md文件")
        result = asyncio.run(build_chain(segments, cfg, None, str(tmp_path), renderers={CodeBlock: fake}))
        assert isinstance(result[0], Picture)
        assert isinstance(result[1], SourceFile)

    def test_code_keep_original(self, tmp_path):
        """渲染且保留原文：原文文本 + 图片，无源文件。"""
        from render.chain import build_chain

        fake = MagicMock(return_value=b"fake_png_data")
        segments = [CodeBlock(lang="py", code="x=1")]
        cfg = _render_cfg(code="渲染且保留原文")
        result = asyncio.run(build_chain(segments, cfg, None, str(tmp_path), renderers={CodeBlock: fake}))
        assert len(result) == 2
        assert isinstance(result[0], Text)
        assert "x=1" in result[0].text
        assert isinstance(result[1], Picture)

    def test_table_render_image(self, tmp_path):
        """表格渲染图像模式。"""
        from render.chain import build_chain

        fake = MagicMock(return_value=b"fake_png_data")
        segments = [Table(headers=[RichCell(spans=[Span(text="A")])], rows=[[RichCell(spans=[Span(text="1")])]])]
        cfg = _render_cfg(table="渲染图像")
        result = asyncio.run(build_chain(segments, cfg, None, str(tmp_path), renderers={Table: fake}))
        assert isinstance(result[0], Picture)

    def test_divider_noop_outputs_text(self, tmp_path):
        """分隔线不处理模式：输出 --- 文本，保留段落分隔。"""
        from render.chain import build_chain

        segments = [Segment(text="上"), Divider(), Segment(text="下")]
        cfg = _render_cfg()
        result = asyncio.run(build_chain(segments, cfg, None, str(tmp_path)))
        assert len(result) == 3
        assert isinstance(result[1], Text)
        assert "---" in result[1].text

    def test_divider_noop_with_cleaning_removes_mark(self, tmp_path):
        """分隔线不处理 + 清洗分隔线开：去掉 --- 标记，保留段落分隔。"""
        from render.chain import build_chain

        segments = [Segment(text="前面\n\n"), Divider(), Segment(text="**后面**")]
        cfg = _render_cfg()
        clean_cfg = _clean_cfg(divider=True)
        result = asyncio.run(build_chain(segments, cfg, clean_cfg, str(tmp_path)))
        full = "".join(c.text for c in result)
        assert "---" not in full
        assert "前面\n\n后面" in full

    def test_divider_noop_without_cleaning_keeps_mark(self, tmp_path):
        """分隔线不处理 + 清洗分隔线关：保留 --- 标记。"""
        from render.chain import build_chain

        segments = [Segment(text="上"), Divider(), Segment(text="下")]
        cfg = _render_cfg()
        clean_cfg = _clean_cfg(divider=False)
        result = asyncio.run(build_chain(segments, cfg, clean_cfg, str(tmp_path)))
        assert "---" in "".join(c.text for c in result)

    def test_inline_expr_render_image(self, tmp_path):
        """行内表达式渲染图像模式。"""
        from render.chain import build_chain

        fake = MagicMock(return_value=b"fake_png_data")
        segments = [InlineExpr(expr="E=mc^2")]
        cfg = _render_cfg(expr="渲染图像")
        result = asyncio.run(build_chain(segments, cfg, None, str(tmp_path), renderers={InlineExpr: fake}))
        assert len(result) == 1
        assert isinstance(result[0], Picture)

    @patch("render.expr_render.typst.compile")
    def test_inline_expr_real_renderer_contract(self, mock_compile, tmp_path):
        """真实 render_expr 经 build_chain 统一契约调用，不抛参数不匹配。"""
        from io import BytesIO

        from PIL import Image as PILImage

        from render.chain import build_chain
        from render.expr_render import render_expr

        buf = BytesIO()
        PILImage.new("RGBA", (100, 20), (0, 0, 0, 255)).save(buf, "PNG")
        mock_compile.return_value = buf.getvalue()

        segments = [InlineExpr(expr="E=mc^2")]
        cfg = _render_cfg(expr="渲染图像")
        result = asyncio.run(build_chain(segments, cfg, None, str(tmp_path), renderers={InlineExpr: render_expr}))

        assert len(result) == 1
        assert isinstance(result[0], Picture)

    def test_block_expr_noop(self, tmp_path):
        """块级表达式不处理：还原为 markdown 原文，不调渲染。"""
        from render.chain import build_chain

        fake = MagicMock(return_value=b"fake_png_data")
        segments = [BlockExpr(expr="\\int x dx")]
        cfg = _render_cfg(expr="不处理")
        result = asyncio.run(build_chain(segments, cfg, None, str(tmp_path), renderers={BlockExpr: fake}))
        assert len(result) == 1
        assert isinstance(result[0], Text)
        assert "$$" in result[0].text
        fake.assert_not_called()

    def test_code_render_failure_fallback(self, tmp_path):
        """代码块渲染失败时出 .md 文件（文件是保底形态），不影响后续段落。"""
        from render.chain import build_chain

        fake = MagicMock(side_effect=RuntimeError("Pygments crashed"))
        cfg = _render_cfg(code="渲染图像")
        segments = [CodeBlock(lang="py", code="x=1"), Segment(text="后续文本")]
        result = asyncio.run(build_chain(segments, cfg, None, str(tmp_path), renderers={CodeBlock: fake}))
        assert isinstance(result[0], SourceFile)
        with open(result[0].path, encoding="utf-8") as f:
            assert "```py" in f.read()
        assert isinstance(result[1], Text)
        assert result[1].text == "后续文本"

    def test_code_render_failure_keep_original_mode(self, tmp_path):
        """渲染且保留原文模式下渲染失败，只回退为原文（不重复）。"""
        from render.chain import build_chain

        fake = MagicMock(side_effect=RuntimeError("Pygments crashed"))
        cfg = _render_cfg(code="渲染且保留原文")
        segments = [CodeBlock(lang="py", code="x=1")]
        result = asyncio.run(build_chain(segments, cfg, None, str(tmp_path), renderers={CodeBlock: fake}))
        assert len(result) == 1
        assert isinstance(result[0], Text)

    def test_code_md_only(self, tmp_path):
        """仅md文件模式：只有 File 没有 Image，不调渲染。"""
        from render.chain import build_chain

        fake = MagicMock(return_value=b"fake_png_data")
        segments = [CodeBlock(lang="py", code="x=1")]
        cfg = _render_cfg(code="仅md文件")
        result = asyncio.run(build_chain(segments, cfg, None, str(tmp_path), renderers={CodeBlock: fake}))
        assert len(result) == 1
        assert isinstance(result[0], SourceFile)
        fake.assert_not_called()

    def test_table_md_only(self, tmp_path):
        """仅md文件模式：只有 File 没有 Image，不调渲染。"""
        from render.chain import build_chain

        fake = MagicMock(return_value=b"fake_png_data")
        segments = [Table(headers=[RichCell(spans=[Span(text="A")])], rows=[[RichCell(spans=[Span(text="1")])]])]
        cfg = _render_cfg(table="仅md文件")
        result = asyncio.run(build_chain(segments, cfg, None, str(tmp_path), renderers={Table: fake}))
        assert len(result) == 1
        assert isinstance(result[0], SourceFile)
        fake.assert_not_called()

    def test_table_render_and_md(self, tmp_path):
        """渲染且md文件模式：图片 + 源文件，无原文文本。"""
        from render.chain import build_chain

        fake = MagicMock(return_value=b"fake_png_data")
        segments = [Table(headers=[RichCell(spans=[Span(text="A")])], rows=[[RichCell(spans=[Span(text="1")])]])]
        cfg = _render_cfg(table="渲染且md文件")
        result = asyncio.run(build_chain(segments, cfg, None, str(tmp_path), renderers={Table: fake}))
        assert len(result) == 2
        assert isinstance(result[0], Picture)
        assert isinstance(result[1], SourceFile)

    def test_code_zero_ttl_uses_frombytes(self, tmp_path):
        """temp_ttl=0 时代码块图片不落盘，只带字节。"""
        from render.chain import build_chain

        fake = MagicMock(return_value=b"fake_png_data")
        segments = [CodeBlock(lang="py", code="x=1")]
        cfg = _render_cfg(code="渲染图像", temp_ttl=0)
        result = asyncio.run(build_chain(segments, cfg, None, str(tmp_path), renderers={CodeBlock: fake}))
        assert len(result) == 1
        img = result[0]
        assert isinstance(img, Picture)
        assert img.png == b"fake_png_data"
        assert img.path is None

    def test_table_zero_ttl_uses_frombytes(self, tmp_path):
        """temp_ttl=0 时表格图片不落盘，只带字节。"""
        from render.chain import build_chain

        fake = MagicMock(return_value=b"fake_png_data")
        segments = [Table(headers=[RichCell(spans=[Span(text="A")])], rows=[[RichCell(spans=[Span(text="1")])]])]
        cfg = _render_cfg(table="渲染图像", temp_ttl=0)
        result = asyncio.run(build_chain(segments, cfg, None, str(tmp_path), renderers={Table: fake}))
        assert len(result) == 1
        img = result[0]
        assert isinstance(img, Picture)
        assert img.png == b"fake_png_data"
        assert img.path is None

    def test_expr_zero_ttl_uses_frombytes(self, tmp_path):
        """temp_ttl=0 时表达式图片不落盘，只带字节。"""
        from render.chain import build_chain

        fake = MagicMock(return_value=b"fake_png_data")
        segments = [InlineExpr(expr="E=mc^2")]
        cfg = _render_cfg(expr="渲染图像", temp_ttl=0)
        result = asyncio.run(build_chain(segments, cfg, None, str(tmp_path), renderers={InlineExpr: fake}))
        assert len(result) == 1
        img = result[0]
        assert isinstance(img, Picture)
        assert img.png == b"fake_png_data"
        assert img.path is None


class TestBuildChainWithCleaning:
    def test_cleaning_applied_to_segment_text(self, tmp_path):
        """清洗在 Segment 文本上执行，去除 markdown 格式。"""
        from render.chain import build_chain

        segments = [Segment(text="**粗体** 普通 *斜体*")]
        cfg = _render_cfg()
        clean_cfg = _clean_cfg()
        result = asyncio.run(build_chain(segments, cfg, clean_cfg, str(tmp_path)))
        assert len(result) == 1
        assert isinstance(result[0], Text)
        assert result[0].text == "粗体 普通 斜体"

    def test_cleaning_skipped_when_none(self, tmp_path):
        """clean_cfg=None 时不清洗，原样保留。"""
        from render.chain import build_chain

        segments = [Segment(text="**粗体**")]
        cfg = _render_cfg()
        result = asyncio.run(build_chain(segments, cfg, None, str(tmp_path)))
        assert result[0].text == "**粗体**"

    def test_cleaning_all_off_preserves_text(self, tmp_path):
        """清洗全关时原样保留。"""
        from render.chain import build_chain

        segments = [Segment(text="**粗体**")]
        cfg = _render_cfg()
        clean_cfg = _clean_cfg(bold=False, italic=False, strikethrough=False,
                                     inline_code=False, link=False, heading=False,
                                     list_unordered=False, list_ordered=False,
                                     blockquote=False, image=False)
        result = asyncio.run(build_chain(segments, cfg, clean_cfg, str(tmp_path)))
        assert result[0].text == "**粗体**"

    def test_code_render_unaffected_by_cleaning(self, tmp_path):
        """代码块渲染不受清洗影响，只有 Segment 被清洗。"""
        from render.chain import build_chain

        fake = MagicMock(return_value=b"fake_png")
        segments = [CodeBlock(lang="py", code="x=1"), Segment(text="**尾注**")]
        cfg = _render_cfg(code="渲染图像")
        clean_cfg = _clean_cfg()
        result = asyncio.run(build_chain(segments, cfg, clean_cfg, str(tmp_path), renderers={CodeBlock: fake}))
        assert len(result) == 2
        assert isinstance(result[0], Picture)  # 代码块正常渲染
        assert isinstance(result[1], Text)
        assert result[1].text == "尾注"  # Segment 被清洗

    def test_clean_code_block_on_unprocessed(self, tmp_path):
        """代码块清洗：不处理模式下去除 fence 标记。"""
        from render.chain import build_chain

        segments = [CodeBlock(lang="py", code="x=1")]
        cfg = _render_cfg(code="不处理")
        clean_cfg = _clean_cfg(code=True)
        result = asyncio.run(build_chain(segments, cfg, clean_cfg, str(tmp_path)))
        assert len(result) == 1
        assert isinstance(result[0], Text)
        assert result[0].text == "x=1"

    def test_clean_code_off_unprocessed_preserves_fence(self, tmp_path):
        """默认关：代码块原文保留 fence。"""
        from render.chain import build_chain

        segments = [CodeBlock(lang="py", code="x=1")]
        cfg = _render_cfg(code="不处理")
        clean_cfg = _clean_cfg()  # code=False by default
        result = asyncio.run(build_chain(segments, cfg, clean_cfg, str(tmp_path)))
        assert "```py" in result[0].text

    def test_clean_code_with_keep_original(self, tmp_path):
        """渲染且保留原文 + 清洗：原文去 fence，图片正常。"""
        from render.chain import build_chain

        fake = MagicMock(return_value=b"fake_png")
        segments = [CodeBlock(lang="py", code="x=1")]
        cfg = _render_cfg(code="渲染且保留原文")
        clean_cfg = _clean_cfg(code=True)
        result = asyncio.run(build_chain(segments, cfg, clean_cfg, str(tmp_path), renderers={CodeBlock: fake}))
        assert len(result) == 2
        assert isinstance(result[0], Text)
        assert result[0].text == "x=1"
        assert isinstance(result[1], Picture)

    def test_clean_table_on_unprocessed(self, tmp_path):
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
        cfg = _render_cfg(table="不处理")
        clean_cfg = _clean_cfg(table=True)
        result = asyncio.run(build_chain(segments, cfg, clean_cfg, str(tmp_path)))
        assert len(result) == 1
        assert isinstance(result[0], Text)
        assert "名称 | 版本" in result[0].text
        assert "A | v1" in result[0].text
        assert "|---" not in result[0].text

    def test_clean_expr_on_unprocessed(self, tmp_path):
        """表达式清洗：不处理模式下去除 $ 定界符。"""
        from render.chain import build_chain

        segments = [InlineExpr(expr="E=mc^2")]
        cfg = _render_cfg(expr="不处理")
        clean_cfg = _clean_cfg(expr=True)
        result = asyncio.run(build_chain(segments, cfg, clean_cfg, str(tmp_path)))
        assert len(result) == 1
        assert isinstance(result[0], Text)
        assert result[0].text == "E=mc^2"


class TestGroupSegments:
    def test_single_segment_single_group(self):
        """无切分点时，单个分组。"""
        from render.chain import group_segments

        segments = [Segment(text="只有一段")]
        groups = group_segments(segments, seg_cfg)
        assert len(groups) == 1
        assert groups[0].segments == segments
        assert groups[0].keep_whole is True

    def test_divider_split_when_divider_mode_split(self):
        """分隔线=切分：`---` 处断开，Divider 不进入任何分组。"""
        from render.chain import group_segments

        segments = [Segment(text="上"), Divider(), Segment(text="下")]
        seg_cfg = _segment_cfg(divider_mode="切分")
        groups = group_segments(segments, seg_cfg)
        assert len(groups) == 2
        assert groups[0].segments == [Segment(text="上")]
        assert groups[1].segments == [Segment(text="下")]

    def test_divider_not_split_when_divider_mode_off(self):
        """分隔线=不处理：Divider 保留在同一分组内。"""
        from render.chain import group_segments

        segments = [Segment(text="上"), Divider(), Segment(text="下")]
        seg_cfg = _segment_cfg(divider_mode="不处理")
        groups = group_segments(segments, seg_cfg)
        assert len(groups) == 1
        assert isinstance(groups[0].segments[1], Divider)

    def test_blank_line_split_when_blank_line_mode_split(self):
        """连续换行=切分：相邻纯文本段之间断开。"""
        from render.chain import group_segments

        segments = [Segment(text="第一段"), Segment(text="第二段"), Segment(text="第三段")]
        seg_cfg = _segment_cfg(blank_line_mode="切分")
        groups = group_segments(segments, seg_cfg)
        assert len(groups) == 3
        assert [g.segments[0].text for g in groups] == ["第一段", "第二段", "第三段"]

    def test_block_element_own_group(self):
        """块级元素独立成组，前后纯文本各自成组。"""
        from render.chain import group_segments

        segments = [
            Segment(text="前"),
            CodeBlock(lang="py", code="x=1"),
            Segment(text="后"),
        ]
        seg_cfg = _segment_cfg(blank_line_mode="切分")
        groups = group_segments(segments, seg_cfg)
        assert len(groups) == 3
        assert [g.keep_whole for g in groups] == [True, False, True]
        assert isinstance(groups[1].segments[0], CodeBlock)

    def test_block_types_each_own_group(self):
        """代码块/表格/块级表达式各自独立成组，行内表达式并入文本流。"""
        from render.chain import group_segments

        tbl = Table(headers=[RichCell(spans=[Span(text="A")])], rows=[[RichCell(spans=[Span(text="1")])]])
        segments = [
            Segment(text="文本"),
            CodeBlock(lang="py", code="x=1"),
            InlineExpr(expr="a"),
            tbl,
            BlockExpr(expr="b"),
            Segment(text="尾"),
        ]
        groups = group_segments(segments, seg_cfg)
        assert [g.keep_whole for g in groups] == [True, False, True, False, False, True]
        assert [len(g.segments) for g in groups] == [1, 1, 1, 1, 1, 1]


class TestHasMedia:
    def test_pure_text_false(self):
        """纯文本链 → False。"""
        from render.artifacts import has_media

        assert has_media([Text("a"), Text("b")]) is False

    def test_media_true(self):
        """含图片或文件 → True。"""
        from render.artifacts import has_media

        assert has_media([Text("a"), Picture(png=b"x")]) is True
        assert has_media([SourceFile(path="/tmp/x.md")]) is True


class TestSplitMessages:
    def test_mixed_chain_splits_per_component(self):
        """含媒体产物按件拆成独立消息，保持阅读顺序。"""
        from render.chain import split_messages

        a = Text("A")
        img1 = Picture(png=b"1")
        b = Text("B")
        f = SourceFile(path="/tmp/x.md")
        result = split_messages([a, img1, b, f])
        assert result == [[a], [img1], [b], [f]]

    def test_pure_text_stays_one_message(self):
        """纯文本链保持单条，不拆。"""
        from render.chain import split_messages

        a = Text("A")
        b = Text("B")
        result = split_messages([a, b])
        assert result == [[a, b]]

    def test_consecutive_media_split(self):
        """连续媒体也逐条拆分，不再挤一条。"""
        from render.chain import split_messages

        img1 = Picture(png=b"1")
        img2 = Picture(png=b"2")
        result = split_messages([img1, img2])
        assert result == [[img1], [img2]]

    def test_single_plain_stays_one_message(self):
        """单条纯文本原样返回。"""
        from render.chain import split_messages

        a = Text("A")
        result = split_messages([a])
        assert result == [[a]]


class TestRenderInjection:
    """渲染器注入：build_chain/plan_chain 接受 renderers 覆盖层，未覆盖走注册表里的渲染器。"""

    def test_renderers_override_element_render(self, tmp_path):
        """传 renderers 时被覆盖类型走 fake，产物进消息链。"""
        from unittest.mock import MagicMock

        from render.chain import build_chain

        fake = MagicMock(return_value=b"fake_png")
        segments = [CodeBlock(lang="py", code="x=1")]
        cfg = _render_cfg(code="渲染图像")
        result = asyncio.run(build_chain(segments, cfg, None, str(tmp_path), renderers={CodeBlock: fake}))
        fake.assert_called_once()
        assert len(result) == 1
        assert isinstance(result[0], Picture)

    def test_plan_chain_passes_renderers(self, tmp_path):
        """plan_chain 透传 renderers 到 build_chain。"""
        from unittest.mock import MagicMock

        fake = MagicMock(return_value=b"fake_png")
        cfg = _render_cfg(code="渲染图像")
        result = _collect(
            "```py\nx=1\n```", cfg, seg_cfg, None, str(tmp_path), renderers={CodeBlock: fake}
        )
        fake.assert_called_once()
        assert isinstance(result[0][0], Picture)

    def test_renderer_for_fallback_and_override(self):
        """_renderer_for：覆盖类型取 fake，未覆盖回退注册表里的渲染器，None 走注册表。"""
        from unittest.mock import MagicMock

        from render.chain import _renderer_for
        from render.elements import ELEMENTS

        fake = MagicMock(return_value=b"fake_png")
        code_element = ELEMENTS[CodeBlock]
        table_element = ELEMENTS[Table]
        assert _renderer_for(CodeBlock, code_element, {CodeBlock: fake}) is fake
        assert _renderer_for(Table, table_element, {CodeBlock: fake}) is table_element.render
        assert _renderer_for(CodeBlock, code_element, None) is code_element.render


class TestInlineRunMerging:
    """行内表达式与相邻文本合并成一条消息，块级元素打断内联流。"""

    def test_inline_expr_keeps_own_message(self, tmp_path):
        """「文本 $expr$ 文本」整条合并，行内表达式图片留在文字原位。"""
        fake = MagicMock(return_value=b"fake_png")
        cfg = _render_cfg(expr="渲染图像")
        result = _collect(
            "增长率为 $5\\%$，其余不变", cfg, seg_cfg, None, str(tmp_path),
            renderers={InlineExpr: fake},
        )
        assert len(result) == 1
        assert [type(c) for c in result[0]] == [Text, Picture, Text]
        assert result[0][0].text.strip() == "增长率为"
        assert result[0][2].text.strip() == "，其余不变"

    def test_trailing_text_merged(self, tmp_path):
        """表达式后不换行的文字并入同一条。"""
        fake = MagicMock(return_value=b"fake_png")
        cfg = _render_cfg(expr="渲染图像")
        result = _collect(
            "毛利 $a$，增长 $b$，很好", cfg, seg_cfg, None, str(tmp_path),
            renderers={InlineExpr: fake},
        )
        assert len(result) == 1
        assert len(result[0]) == 5
        assert isinstance(result[0][1], Picture)
        assert isinstance(result[0][3], Picture)

    def test_block_expr_stays_own_message(self, tmp_path):
        """块级表达式不合并，独立一条，前后内联流各自合并。"""
        fake = MagicMock(return_value=b"fake_png")
        cfg = _render_cfg(expr="渲染图像")
        result = _collect(
            "公式 $x$ 且 $$y$$ 且 $z$", cfg, seg_cfg, None, str(tmp_path),
            renderers={InlineExpr: fake, BlockExpr: fake},
        )
        assert len(result) == 3
        assert [type(c) for c in result[0]] == [Text, Picture, Text]
        assert isinstance(result[1][0], Picture)  # 块级表达式独立一条
        assert [type(c) for c in result[2]] == [Text, Picture]

    def test_code_block_splits_inline_run(self, tmp_path):
        """代码块打断内联流：代码块独立一条，前后内联流各自合并。"""
        fake = MagicMock(return_value=b"fake_png")
        cfg = _render_cfg(code="渲染图像", expr="渲染图像")
        md = "注意：$a$ 代码是\n```py\nprint(1)\n```\n末尾 $b$ 了"
        result = _collect(
            md, cfg, seg_cfg, None, str(tmp_path),
            renderers={CodeBlock: fake, InlineExpr: fake},
        )
        assert len(result) == 3
        assert [type(c) for c in result[0]] == [Text, Picture, Text]  # 注意：🖼️(a) 代码是
        assert isinstance(result[1][0], Picture)  # 代码块图独立一条
        assert [type(c) for c in result[2]] == [Text, Picture, Text]  # 末尾 🖼️(b) 了
