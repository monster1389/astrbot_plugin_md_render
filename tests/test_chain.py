"""消息链组装与分段测试。"""
import asyncio
from unittest.mock import MagicMock, patch

from astrbot.api.message_components import Plain, Image, File as AstrFile

from render.parser import BlockExpr, CodeBlock, Divider, HtmlDoc, InlineExpr, MermaidBlock, Segment
from render.table_domain import RichCell, Span, Table
from render.config import RenderConfig, SegmentConfig, CleanConfig


def _make_cfg(**overrides):
    """构造测试用 RenderConfig，支持按需覆盖。"""
    defaults = {
        "code_mode": "不处理",
        "table_mode": "不处理",
        "expr_mode": "不处理",
        "temp_ttl": 5,
    }
    return RenderConfig(**(defaults | overrides))


def _make_seg_cfg(**overrides):
    """构造测试用 SegmentConfig，支持按需覆盖。"""
    defaults = {
        "divider_mode": "不处理",
        "blank_line_mode": "不处理",
        "send_delay": False,
    }
    return SegmentConfig(**(defaults | overrides))


# 默认分段配置：不切分、无延时。需定制的用例在方法内局部覆盖。
seg_cfg = _make_seg_cfg()


def _make_clean_cfg(**overrides):
    """构造测试用 CleanConfig，经典字段默认 True，code/table/expr 默认 False。"""
    defaults = vars(CleanConfig()).copy()
    for k in defaults:
        if k not in ("code", "table", "expr"):
            defaults[k] = True
    defaults.update(overrides)
    return CleanConfig(**defaults)


def _collect(chain, cfg, seg_cfg, clean_cfg, data_dir="/tmp", renderers=None):
    """建流水线并收集全部产出消息；plan_chain 返回 None 时同样返回 None。"""
    from render.chain import plan_chain

    async def _run():
        pipeline = await plan_chain(chain, cfg, seg_cfg, clean_cfg, data_dir, renderers)
        if pipeline is None:
            return None
        return [message.chain async for message in pipeline]

    return asyncio.run(_run())


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

    def test_code_render_image(self):
        """代码块渲染图像模式：只有 Image 没有 File 也没有原文。"""
        from render.chain import build_chain

        fake = MagicMock(return_value=b"fake_png_data")
        segments = [CodeBlock(lang="py", code="x=1")]
        cfg = _make_cfg(code_mode="渲染图像")
        result = asyncio.run(build_chain(segments, cfg, None, "/tmp", renderers={CodeBlock: fake}))
        assert len(result) == 1
        assert isinstance(result[0], Image)

    def test_async_renderer_is_awaited(self):
        """协程渲染器直接 await，不丢进线程池。"""
        from render.chain import build_chain

        async def fake(seg):
            return b"fake_png_data"

        cfg = _make_cfg(code_mode="渲染图像")
        result = asyncio.run(
            build_chain([CodeBlock(lang="py", code="x=1")], cfg, None, "/tmp", renderers={CodeBlock: fake})
        )
        assert len(result) == 1
        assert isinstance(result[0], Image)

    def test_html_render_image(self):
        """HTML 文档渲染图像模式。"""
        from render.chain import build_chain

        fake = MagicMock(return_value=b"fake_png_data")
        cfg = _make_cfg(html_mode="渲染图像")
        result = asyncio.run(
            build_chain([HtmlDoc(code="<html></html>")], cfg, None, "/tmp", renderers={HtmlDoc: fake})
        )
        assert len(result) == 1
        assert isinstance(result[0], Image)

    def test_html_noop_keeps_fence(self):
        """HTML 文档不处理：还原为 ```html 围栏原文。"""
        from render.chain import build_chain

        cfg = _make_cfg(html_mode="不处理")
        result = asyncio.run(build_chain([HtmlDoc(code="<html></html>")], cfg, None, "/tmp"))
        assert len(result) == 1
        assert isinstance(result[0], Plain)
        assert "```html" in result[0].text

    def test_html_keep_original(self):
        """HTML 渲染且保留原文：Plain + Image。"""
        from render.chain import build_chain

        fake = MagicMock(return_value=b"fake_png_data")
        cfg = _make_cfg(html_mode="渲染且保留原文")
        result = asyncio.run(
            build_chain([HtmlDoc(code="<html></html>")], cfg, None, "/tmp", renderers={HtmlDoc: fake})
        )
        assert len(result) == 2
        assert isinstance(result[0], Plain)
        assert isinstance(result[1], Image)

    def test_mermaid_render_and_md(self):
        """Mermaid 渲染且md文件：Image + File。"""
        from render.chain import build_chain

        fake = MagicMock(return_value=b"fake_png_data")
        cfg = _make_cfg(mermaid_mode="渲染且md文件")
        result = asyncio.run(
            build_chain([MermaidBlock(code="graph LR")], cfg, None, "/tmp", renderers={MermaidBlock: fake})
        )
        assert len(result) == 2
        assert isinstance(result[0], Image)
        assert isinstance(result[1], AstrFile)

    def test_mermaid_render_image(self):
        """Mermaid 图表渲染图像模式。"""
        from render.chain import build_chain

        fake = MagicMock(return_value=b"fake_png_data")
        cfg = _make_cfg(mermaid_mode="渲染图像")
        result = asyncio.run(
            build_chain([MermaidBlock(code="graph LR")], cfg, None, "/tmp", renderers={MermaidBlock: fake})
        )
        assert len(result) == 1
        assert isinstance(result[0], Image)

    def test_render_failure_falls_back_to_text(self):
        """渲染异常时回退为原文。"""
        from render.chain import build_chain

        def boom(_seg):
            raise RuntimeError("boom")

        cfg = _make_cfg(mermaid_mode="渲染图像")
        result = asyncio.run(
            build_chain([MermaidBlock(code="graph LR")], cfg, None, "/tmp", renderers={MermaidBlock: boom})
        )
        assert isinstance(result[0], Plain)
        assert "```mermaid" in result[0].text

    def test_render_failure_with_md_mode_still_writes_file(self):
        """图渲染失败但配置了 md 文件：仍写 .md，不回退原文。"""
        from render.chain import build_chain

        def boom(_seg):
            raise RuntimeError("boom")

        cfg = _make_cfg(mermaid_mode="渲染且md文件")
        result = asyncio.run(
            build_chain([MermaidBlock(code="graph LR")], cfg, None, "/tmp", renderers={MermaidBlock: boom})
        )
        assert len(result) == 1
        assert isinstance(result[0], AstrFile)
        with open(result[0].file, encoding="utf-8") as f:
            assert "```mermaid" in f.read()

    def test_mermaid_md_only(self):
        """仅md文件模式：只有 File 没有 Image，不调渲染。"""
        from render.chain import build_chain

        fake = MagicMock(return_value=b"fake_png_data")
        cfg = _make_cfg(mermaid_mode="仅md文件")
        result = asyncio.run(
            build_chain([MermaidBlock(code="graph LR")], cfg, None, "/tmp", renderers={MermaidBlock: fake})
        )
        assert len(result) == 1
        assert isinstance(result[0], AstrFile)
        fake.assert_not_called()

    def test_code_render_with_md(self):
        """渲染且md文件：Image + File。"""
        from render.chain import build_chain

        fake = MagicMock(return_value=b"fake_png_data")
        segments = [CodeBlock(lang="py", code="x=1")]
        cfg = _make_cfg(code_mode="渲染且md文件")
        result = asyncio.run(build_chain(segments, cfg, None, "/tmp", renderers={CodeBlock: fake}))
        assert isinstance(result[0], Image)
        assert isinstance(result[1], AstrFile)

    def test_code_keep_original(self):
        """渲染且保留原文：原文 Plain + Image，无 File。"""
        from render.chain import build_chain

        fake = MagicMock(return_value=b"fake_png_data")
        segments = [CodeBlock(lang="py", code="x=1")]
        cfg = _make_cfg(code_mode="渲染且保留原文")
        result = asyncio.run(build_chain(segments, cfg, None, "/tmp", renderers={CodeBlock: fake}))
        assert len(result) == 2
        assert isinstance(result[0], Plain)
        assert "x=1" in result[0].text
        assert isinstance(result[1], Image)

    def test_table_render_image(self):
        """表格渲染图像模式。"""
        from render.chain import build_chain

        fake = MagicMock(return_value=b"fake_png_data")
        segments = [Table(headers=[RichCell(spans=[Span(text="A")])], rows=[[RichCell(spans=[Span(text="1")])]])]
        cfg = _make_cfg(table_mode="渲染图像")
        result = asyncio.run(build_chain(segments, cfg, None, "/tmp", renderers={Table: fake}))
        assert isinstance(result[0], Image)

    def test_divider_noop_outputs_text(self):
        """分隔线不处理模式：输出 --- 文本，保留段落分隔。"""
        from render.chain import build_chain

        segments = [Segment(text="上"), Divider(), Segment(text="下")]
        cfg = _make_cfg()
        result = asyncio.run(build_chain(segments, cfg, None, "/tmp"))
        assert len(result) == 3
        assert isinstance(result[1], Plain)
        assert "---" in result[1].text

    def test_divider_noop_with_cleaning_removes_mark(self):
        """分隔线不处理 + 清洗分隔线开：去掉 --- 标记，保留段落分隔。"""
        from render.chain import build_chain

        segments = [Segment(text="前面\n\n"), Divider(), Segment(text="**后面**")]
        cfg = _make_cfg()
        clean_cfg = _make_clean_cfg()
        result = asyncio.run(build_chain(segments, cfg, clean_cfg, "/tmp"))
        full = "".join(c.text for c in result)
        assert "---" not in full
        assert "前面\n\n后面" in full

    def test_divider_noop_without_cleaning_keeps_mark(self):
        """分隔线不处理 + 清洗分隔线关：保留 --- 标记。"""
        from render.chain import build_chain

        segments = [Segment(text="上"), Divider(), Segment(text="下")]
        cfg = _make_cfg()
        clean_cfg = _make_clean_cfg(divider=False)
        result = asyncio.run(build_chain(segments, cfg, clean_cfg, "/tmp"))
        assert "---" in "".join(c.text for c in result)

    def test_inline_expr_render_image(self):
        """行内表达式渲染图像模式。"""
        from render.chain import build_chain

        fake = MagicMock(return_value=b"fake_png_data")
        segments = [InlineExpr(expr="E=mc^2")]
        cfg = _make_cfg(expr_mode="渲染图像")
        result = asyncio.run(build_chain(segments, cfg, None, "/tmp", renderers={InlineExpr: fake}))
        assert len(result) == 1
        assert isinstance(result[0], Image)

    @patch("render.expr_render.typst.compile")
    def test_inline_expr_real_renderer_contract(self, mock_compile):
        """真实 render_expr 经 build_chain 统一契约调用，不抛参数不匹配。"""
        from io import BytesIO

        from PIL import Image as PILImage

        from render.chain import build_chain
        from render.expr_render import render_expr

        buf = BytesIO()
        PILImage.new("RGBA", (100, 20), (0, 0, 0, 255)).save(buf, "PNG")
        mock_compile.return_value = buf.getvalue()

        segments = [InlineExpr(expr="E=mc^2")]
        cfg = _make_cfg(expr_mode="渲染图像")
        result = asyncio.run(build_chain(segments, cfg, None, "/tmp", renderers={InlineExpr: render_expr}))

        assert len(result) == 1
        assert isinstance(result[0], Image)

    def test_block_expr_noop(self):
        """块级表达式不处理：还原为 markdown 原文，不调渲染。"""
        from render.chain import build_chain

        fake = MagicMock(return_value=b"fake_png_data")
        segments = [BlockExpr(expr="\\int x dx")]
        cfg = _make_cfg(expr_mode="不处理")
        result = asyncio.run(build_chain(segments, cfg, None, "/tmp", renderers={BlockExpr: fake}))
        assert len(result) == 1
        assert isinstance(result[0], Plain)
        assert "$$" in result[0].text
        fake.assert_not_called()

    def test_code_render_failure_fallback(self):
        """代码块渲染失败时回退为 Plain 原文，不影响后续段落。"""
        from render.chain import build_chain
        from render.config import RenderConfig

        fake = MagicMock(side_effect=RuntimeError("Pygments crashed"))
        cfg = RenderConfig(
            code_mode="渲染图像", table_mode="不处理",
            expr_mode="不处理", temp_ttl=5,
        )
        segments = [CodeBlock(lang="py", code="x=1"), Segment(text="后续文本")]
        result = asyncio.run(build_chain(segments, cfg, None, "/tmp", renderers={CodeBlock: fake}))
        assert isinstance(result[0], Plain)
        assert "```py" in result[0].text
        assert isinstance(result[1], Plain)
        assert result[1].text == "后续文本"

    def test_code_render_failure_keep_original_mode(self):
        """渲染且保留原文模式下渲染失败，只回退为原文（不重复）。"""
        from render.chain import build_chain
        from render.config import RenderConfig

        fake = MagicMock(side_effect=RuntimeError("Pygments crashed"))
        cfg = RenderConfig(
            code_mode="渲染且保留原文", table_mode="不处理",
            expr_mode="不处理", temp_ttl=5,
        )
        segments = [CodeBlock(lang="py", code="x=1")]
        result = asyncio.run(build_chain(segments, cfg, None, "/tmp", renderers={CodeBlock: fake}))
        assert len(result) == 1
        assert isinstance(result[0], Plain)

    def test_code_md_only(self):
        """仅md文件模式：只有 File 没有 Image，不调渲染。"""
        from render.chain import build_chain

        fake = MagicMock(return_value=b"fake_png_data")
        segments = [CodeBlock(lang="py", code="x=1")]
        cfg = _make_cfg(code_mode="仅md文件")
        result = asyncio.run(build_chain(segments, cfg, None, "/tmp", renderers={CodeBlock: fake}))
        assert len(result) == 1
        assert isinstance(result[0], AstrFile)
        fake.assert_not_called()

    def test_table_md_only(self):
        """仅md文件模式：只有 File 没有 Image，不调渲染。"""
        from render.chain import build_chain

        fake = MagicMock(return_value=b"fake_png_data")
        segments = [Table(headers=[RichCell(spans=[Span(text="A")])], rows=[[RichCell(spans=[Span(text="1")])]])]
        cfg = _make_cfg(table_mode="仅md文件")
        result = asyncio.run(build_chain(segments, cfg, None, "/tmp", renderers={Table: fake}))
        assert len(result) == 1
        assert isinstance(result[0], AstrFile)
        fake.assert_not_called()

    def test_table_render_and_md(self):
        """渲染且md文件模式：Image + File，无 Plain 原文。"""
        from render.chain import build_chain

        fake = MagicMock(return_value=b"fake_png_data")
        segments = [Table(headers=[RichCell(spans=[Span(text="A")])], rows=[[RichCell(spans=[Span(text="1")])]])]
        cfg = _make_cfg(table_mode="渲染且md文件")
        result = asyncio.run(build_chain(segments, cfg, None, "/tmp", renderers={Table: fake}))
        assert len(result) == 2
        assert isinstance(result[0], Image)
        assert isinstance(result[1], AstrFile)

    def test_code_zero_ttl_uses_frombytes(self):
        """temp_ttl=0 时代码块用 Image.fromBytes，不走文件落盘。"""
        from render.chain import build_chain

        fake = MagicMock(return_value=b"fake_png_data")
        segments = [CodeBlock(lang="py", code="x=1")]
        cfg = _make_cfg(code_mode="渲染图像", temp_ttl=0)
        result = asyncio.run(build_chain(segments, cfg, None, "/tmp", renderers={CodeBlock: fake}))
        assert len(result) == 1
        img = result[0]
        assert isinstance(img, Image)
        assert hasattr(img, "data") and img.data == b"fake_png_data"
        assert not hasattr(img, "file")

    def test_table_zero_ttl_uses_frombytes(self):
        """temp_ttl=0 时表格用 Image.fromBytes，不走文件落盘。"""
        from render.chain import build_chain

        fake = MagicMock(return_value=b"fake_png_data")
        segments = [Table(headers=[RichCell(spans=[Span(text="A")])], rows=[[RichCell(spans=[Span(text="1")])]])]
        cfg = _make_cfg(table_mode="渲染图像", temp_ttl=0)
        result = asyncio.run(build_chain(segments, cfg, None, "/tmp", renderers={Table: fake}))
        assert len(result) == 1
        img = result[0]
        assert isinstance(img, Image)
        assert hasattr(img, "data") and img.data == b"fake_png_data"
        assert not hasattr(img, "file")

    def test_expr_zero_ttl_uses_frombytes(self):
        """temp_ttl=0 时表达式用 Image.fromBytes，不走文件落盘。"""
        from render.chain import build_chain

        fake = MagicMock(return_value=b"fake_png_data")
        segments = [InlineExpr(expr="E=mc^2")]
        cfg = _make_cfg(expr_mode="渲染图像", temp_ttl=0)
        result = asyncio.run(build_chain(segments, cfg, None, "/tmp", renderers={InlineExpr: fake}))
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

    def test_code_render_unaffected_by_cleaning(self):
        """代码块渲染不受清洗影响，只有 Segment 被清洗。"""
        from render.chain import build_chain

        fake = MagicMock(return_value=b"fake_png")
        segments = [CodeBlock(lang="py", code="x=1"), Segment(text="**尾注**")]
        cfg = _make_cfg(code_mode="渲染图像")
        clean_cfg = _make_clean_cfg()
        result = asyncio.run(build_chain(segments, cfg, clean_cfg, "/tmp", renderers={CodeBlock: fake}))
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

    def test_clean_code_with_keep_original(self):
        """渲染且保留原文 + 清洗：原文去 fence，图片正常。"""
        from render.chain import build_chain

        fake = MagicMock(return_value=b"fake_png")
        segments = [CodeBlock(lang="py", code="x=1")]
        cfg = _make_cfg(code_mode="渲染且保留原文")
        clean_cfg = _make_clean_cfg(code=True)
        result = asyncio.run(build_chain(segments, cfg, clean_cfg, "/tmp", renderers={CodeBlock: fake}))
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


class TestElementTextRecipe:
    """元素文本配方：ElementSpec.text(seg, cc) 一键产出纯文本或 markdown 原文。"""

    @staticmethod
    def _table() -> Table:
        return Table(
            headers=[
                RichCell(spans=[Span(text="名称")]),
                RichCell(spans=[Span(text="版本")]),
            ],
            rows=[[
                RichCell(spans=[Span(text="A")]),
                RichCell(spans=[Span(text="v1")]),
            ]],
        )

    def test_code_recipe(self):
        """代码块：清洗开→裸代码，关闭/None→markdown 围栏原文。"""
        from render.chain import _ELEMENT_SPECS
        from render.config import CleanConfig

        seg = CodeBlock(lang="py", code="x=1")
        spec = _ELEMENT_SPECS[type(seg)]
        assert spec.text(seg, CleanConfig(code=True)) == "x=1"
        assert spec.text(seg, CleanConfig(code=False)) == "```py\nx=1\n```"
        assert spec.text(seg, None) == "```py\nx=1\n```"

    def test_table_recipe(self):
        """表格：清洗开→无外管无分隔行，关闭/None→markdown 表格原文。"""
        from render.chain import _ELEMENT_SPECS
        from render.config import CleanConfig

        seg = self._table()
        spec = _ELEMENT_SPECS[type(seg)]
        assert spec.text(seg, CleanConfig(table=True)) == "名称 | 版本\nA | v1"
        assert spec.text(seg, CleanConfig(table=False)) == "| 名称 | 版本 |\n|---|---|\n| A | v1 |"
        assert spec.text(seg, None) == "| 名称 | 版本 |\n|---|---|\n| A | v1 |"

    def test_inline_expr_recipe(self):
        """行内表达式：清洗开→裸公式，关闭/None→$ 包裹原文。"""
        from render.chain import _ELEMENT_SPECS
        from render.config import CleanConfig

        seg = InlineExpr(expr="x")
        spec = _ELEMENT_SPECS[type(seg)]
        assert spec.text(seg, CleanConfig(expr=True)) == "x"
        assert spec.text(seg, CleanConfig(expr=False)) == "$x$"
        assert spec.text(seg, None) == "$x$"

    def test_block_expr_recipe(self):
        """块级表达式：清洗开→裸公式，关闭/None→$$ 包裹原文。"""
        from render.chain import _ELEMENT_SPECS
        from render.config import CleanConfig

        seg = BlockExpr(expr="x")
        spec = _ELEMENT_SPECS[type(seg)]
        assert spec.text(seg, CleanConfig(expr=True)) == "x"
        assert spec.text(seg, CleanConfig(expr=False)) == "$$\nx\n$$"
        assert spec.text(seg, None) == "$$\nx\n$$"

    def test_segment_recipe(self):
        """纯文本段：清洗开→clean_markdown 清洗，None→原文。"""
        from render.chain import _ELEMENT_SPECS
        from render.md_cleaner import clean_markdown

        seg = Segment(text="**加粗**")
        spec = _ELEMENT_SPECS[type(seg)]
        cc = _make_clean_cfg()
        assert spec.text(seg, cc) == clean_markdown(seg.text, cc)
        assert spec.text(seg, None) == seg.text

    def test_divider_recipe(self):
        """分隔线：分隔线清洗开→空行，关闭/None→--- 标记。"""
        from render.chain import _ELEMENT_SPECS

        seg = Divider()
        spec = _ELEMENT_SPECS[type(seg)]
        assert spec.text(seg, _make_clean_cfg(divider=True)) == "\n\n"
        assert spec.text(seg, _make_clean_cfg(divider=False)) == "\n\n---\n\n"
        assert spec.text(seg, None) == "\n\n---\n\n"


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
        seg_cfg = _make_seg_cfg(divider_mode="切分")
        groups = group_segments(segments, seg_cfg)
        assert len(groups) == 2
        assert groups[0].segments == [Segment(text="上")]
        assert groups[1].segments == [Segment(text="下")]

    def test_divider_not_split_when_divider_mode_off(self):
        """分隔线=不处理：Divider 保留在同一分组内。"""
        from render.chain import group_segments

        segments = [Segment(text="上"), Divider(), Segment(text="下")]
        seg_cfg = _make_seg_cfg(divider_mode="不处理")
        groups = group_segments(segments, seg_cfg)
        assert len(groups) == 1
        assert isinstance(groups[0].segments[1], Divider)

    def test_blank_line_split_when_blank_line_mode_split(self):
        """连续换行=切分：相邻纯文本段之间断开。"""
        from render.chain import group_segments

        segments = [Segment(text="第一段"), Segment(text="第二段"), Segment(text="第三段")]
        seg_cfg = _make_seg_cfg(blank_line_mode="切分")
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
        seg_cfg = _make_seg_cfg(blank_line_mode="切分")
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
        from render.chain import has_media

        assert has_media([Plain("a"), Plain("b")]) is False

    def test_media_true(self):
        """含图片或文件 → True。"""
        from render.chain import has_media

        assert has_media([Plain("a"), Image.fromBytes(b"x")]) is True
        assert has_media([AstrFile(name="x.md", file="/tmp/x.md")]) is True


class TestSplitMessages:
    def test_mixed_chain_splits_per_component(self):
        """含媒体链按组件拆成独立消息，保持阅读顺序。"""
        from render.chain import split_messages

        a = Plain("A")
        img1 = Image.fromBytes(b"1")
        b = Plain("B")
        f = AstrFile(name="x.md", file="/tmp/x.md")
        result = split_messages([a, img1, b, f])
        assert result == [[a], [img1], [b], [f]]

    def test_pure_text_stays_one_message(self):
        """纯文本链保持单条，不拆。"""
        from render.chain import split_messages

        a = Plain("A")
        b = Plain("B")
        result = split_messages([a, b])
        assert result == [[a, b]]

    def test_consecutive_media_split(self):
        """连续媒体也逐条拆分，不再挤一条。"""
        from render.chain import split_messages

        img1 = Image.fromBytes(b"1")
        img2 = Image.fromBytes(b"2")
        result = split_messages([img1, img2])
        assert result == [[img1], [img2]]

    def test_single_plain_stays_one_message(self):
        """单条纯文本原样返回。"""
        from render.chain import split_messages

        a = Plain("A")
        result = split_messages([a])
        assert result == [[a]]


class TestRenderInjection:
    """渲染器注入：build_chain/plan_chain 接受 renderers 覆盖层，未覆盖走默认配方。"""

    def test_renderers_override_spec_render(self):
        """传 renderers 时被覆盖类型走 fake，产物进消息链。"""
        from unittest.mock import MagicMock

        from render.chain import build_chain

        fake = MagicMock(return_value=b"fake_png")
        segments = [CodeBlock(lang="py", code="x=1")]
        cfg = _make_cfg(code_mode="渲染图像")
        result = asyncio.run(build_chain(segments, cfg, None, "/tmp", renderers={CodeBlock: fake}))
        fake.assert_called_once()
        assert len(result) == 1
        assert isinstance(result[0], Image)

    def test_plan_chain_passes_renderers(self):
        """plan_chain 透传 renderers 到 build_chain。"""
        from unittest.mock import MagicMock

        fake = MagicMock(return_value=b"fake_png")
        cfg = _make_cfg(code_mode="渲染图像")
        result = _collect(
            [Plain("```py\nx=1\n```")], cfg, seg_cfg, None, "/tmp", renderers={CodeBlock: fake}
        )
        fake.assert_called_once()
        assert isinstance(result[0][0], Image)

    def test_renderer_for_fallback_and_override(self):
        """_renderer_for：覆盖类型取 fake，未覆盖回退 spec.render，None 走默认。"""
        from unittest.mock import MagicMock

        from render.chain import _ELEMENT_SPECS, _renderer_for

        fake = MagicMock(return_value=b"fake_png")
        code_spec = _ELEMENT_SPECS[CodeBlock]
        table_spec = _ELEMENT_SPECS[Table]
        assert _renderer_for(CodeBlock, code_spec, {CodeBlock: fake}) is fake
        assert _renderer_for(Table, table_spec, {CodeBlock: fake}) is table_spec.render
        assert _renderer_for(CodeBlock, code_spec, None) is code_spec.render


class TestInlineRunMerging:
    """行内表达式与相邻文本合并成一条消息，块级元素打断内联流。"""

    def test_inline_expr_keeps_own_message(self):
        """「文本 $expr$ 文本」整条合并，行内表达式图片留在文字原位。"""
        fake = MagicMock(return_value=b"fake_png")
        cfg = _make_cfg(expr_mode="渲染图像")
        result = _collect(
            [Plain("增长率为 $5\\%$，其余不变")], cfg, seg_cfg, None, "/tmp",
            renderers={InlineExpr: fake},
        )
        assert len(result) == 1
        assert [type(c) for c in result[0]] == [Plain, Image, Plain]
        assert result[0][0].text.strip() == "增长率为"
        assert result[0][2].text.strip() == "，其余不变"

    def test_trailing_text_merged(self):
        """表达式后不换行的文字并入同一条。"""
        fake = MagicMock(return_value=b"fake_png")
        cfg = _make_cfg(expr_mode="渲染图像")
        result = _collect(
            [Plain("毛利 $a$，增长 $b$，很好")], cfg, seg_cfg, None, "/tmp",
            renderers={InlineExpr: fake},
        )
        assert len(result) == 1
        assert len(result[0]) == 5
        assert isinstance(result[0][1], Image)
        assert isinstance(result[0][3], Image)

    def test_block_expr_stays_own_message(self):
        """块级表达式不合并，独立一条，前后内联流各自合并。"""
        fake = MagicMock(return_value=b"fake_png")
        cfg = _make_cfg(expr_mode="渲染图像")
        result = _collect(
            [Plain("公式 $x$ 且 $$y$$ 且 $z$")], cfg, seg_cfg, None, "/tmp",
            renderers={InlineExpr: fake, BlockExpr: fake},
        )
        assert len(result) == 3
        assert [type(c) for c in result[0]] == [Plain, Image, Plain]
        assert isinstance(result[1][0], Image)  # 块级表达式独立一条
        assert [type(c) for c in result[2]] == [Plain, Image]

    def test_code_block_splits_inline_run(self):
        """代码块打断内联流：代码块独立一条，前后内联流各自合并。"""
        fake = MagicMock(return_value=b"fake_png")
        cfg = _make_cfg(code_mode="渲染图像", expr_mode="渲染图像")
        md = "注意：$a$ 代码是\n```py\nprint(1)\n```\n末尾 $b$ 了"
        result = _collect(
            [Plain(md)], cfg, seg_cfg, None, "/tmp",
            renderers={CodeBlock: fake, InlineExpr: fake},
        )
        assert len(result) == 3
        assert [type(c) for c in result[0]] == [Plain, Image, Plain]  # 注意：🖼️(a) 代码是
        assert isinstance(result[1][0], Image)  # 代码块图独立一条
        assert [type(c) for c in result[2]] == [Plain, Image, Plain]  # 末尾 🖼️(b) 了
