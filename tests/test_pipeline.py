"""管道编排测试：消息链 → 渲染流水线 → 待发送消息列表。"""
import asyncio
import time
from unittest.mock import MagicMock, patch

import pytest

from factories import clean_cfg as _clean_cfg
from factories import collect as _collect
from factories import render_cfg as _render_cfg
from factories import segment_cfg as _segment_cfg
from render.artifacts import Picture, SourceFile, Text
from render.parser import CodeBlock

# 这些用例测链组装与顺序，fake 渲染器返回假字节，量化由 test_png.py 覆盖
pytestmark = pytest.mark.usefixtures("no_quantize")

# 默认分段配置：不切分、无延时。需定制的用例在方法内局部覆盖。
seg_cfg = _segment_cfg()


class TestPlanChain:
    def test_empty_chain_returns_none(self, tmp_path):
        """空链返回 None。"""
        assert _collect("", _render_cfg(), seg_cfg, None, str(tmp_path)) is None

    def test_blank_text_returns_none(self, tmp_path):
        """纯空白文本返回 None。"""
        assert _collect("   ", _render_cfg(), seg_cfg, None, str(tmp_path)) is None

    def test_noop_returns_none(self, tmp_path):
        """无元素、无清洗、无切分 → None（链原样保留）。"""
        assert _collect("普通文本", _render_cfg(), seg_cfg, None, str(tmp_path)) is None

    def test_cleaning_produces_messages(self, tmp_path):
        """仅清洗开启：产出清洗后的单条消息。"""
        result = _collect(
            "**加粗**", _render_cfg(), seg_cfg, _clean_cfg(), str(tmp_path)
        )
        assert [c.text for c in result[0]] == ["加粗"]

    def test_keep_original_splits_text_and_image(self, tmp_path):
        """渲染且保留原文：原文文本前置，图片留末条。"""
        fake = MagicMock(return_value=b"fake_png")
        cfg = _render_cfg(code="渲染且保留原文")
        result = _collect(
            "```py\nx=1\n```", cfg, seg_cfg, None, str(tmp_path), renderers={CodeBlock: fake}
        )
        assert len(result) == 2
        assert "x=1" in result[0][0].text
        assert result[1][0].png == b"fake_png"

    def test_divider_split_returns_groups(self, tmp_path):
        """分隔线=切分：每组一条消息。"""
        seg_cfg = _segment_cfg(divider_mode="切分")
        result = _collect(
            "第一段\n\n---\n\n第二段\n\n---\n\n第三段", _render_cfg(), seg_cfg, None,
            str(tmp_path),
        )
        assert len(result) == 3
        assert result[0][0].text.strip() == "第一段"
        assert result[1][0].text.strip() == "第二段"
        assert result[2][0].text.strip() == "第三段"

    def test_blank_line_split_returns_groups(self, tmp_path):
        """连续换行=切分：空行分隔的段落各一条。"""
        seg_cfg = _segment_cfg(blank_line_mode="切分")
        result = _collect(
            "第一段\n\n第二段\n\n第三段", _render_cfg(), seg_cfg, None, str(tmp_path)
        )
        assert len(result) == 3
        assert [c.text for c in result[0]] == ["第一段"]
        assert [c.text for c in result[1]] == ["第二段"]
        assert [c.text for c in result[2]] == ["第三段"]

    def test_interleaved_components_in_order(self, tmp_path):
        """交错元素按组件拆条，保持阅读顺序。"""
        fake = MagicMock(side_effect=lambda seg: b"png_" + seg.code.encode())
        cfg = _render_cfg(code="渲染且保留原文")
        result = _collect(
            "正文第一行\n\n```py\nx=1\n```\n\n```py\ny=2\n```",
            cfg, seg_cfg, None, str(tmp_path), renderers={CodeBlock: fake},
        )
        assert len(result) == 5
        assert result[0][0].text.strip() == "正文第一行"
        assert "x=1" in result[1][0].text
        assert result[2][0].png == b"png_x=1"
        assert "y=2" in result[3][0].text
        assert result[4][0].png == b"png_y=2"

    def test_divider_split_with_cleaning(self, tmp_path):
        """分隔线=切分 + 清洗：切分点两侧文本各自成条且清洗干净。"""
        seg_cfg = _segment_cfg(divider_mode="切分")
        result = _collect(
            "好，第一轮回顾 (。-`ω´-)\n\n---\n\n**测试 1：纯闲聊**",
            _render_cfg(), seg_cfg, _clean_cfg(), str(tmp_path),
        )
        assert len(result) == 2
        assert result[0][0].text == "好，第一轮回顾 (。-`ω´-)"
        assert result[1][0].text == "测试 1：纯闲聊"

    def test_passes_renderers(self, tmp_path):
        """plan_chain 透传 renderers 到 build_chain。"""
        fake = MagicMock(return_value=b"fake_png")
        cfg = _render_cfg(code="渲染图像")
        result = _collect(
            "```py\nx=1\n```", cfg, seg_cfg, None, str(tmp_path), renderers={CodeBlock: fake}
        )
        fake.assert_called_once()
        assert isinstance(result[0][0], Picture)


class TestPipelineStreaming:
    """流水线语义：提交即开工、严格保序、超时降级、产物计数、取消。"""

    def test_first_message_ready_before_slow_render_finishes(self, tmp_path):
        """首条纯文本不必等后面的慢渲染——流水线不向前多看一条。"""
        from render.chain import plan_chain

        finished: list[str] = []

        def slow(seg):
            time.sleep(0.2)
            finished.append("done")
            return b"png"

        async def _run():
            pipeline = await plan_chain(
                "正文\n\n```py\nx=1\n```", _render_cfg(code="渲染图像"), seg_cfg,
                None, str(tmp_path), {CodeBlock: slow},
            )
            iterator = pipeline.__aiter__()
            first = await iterator.__anext__()
            pending = list(finished)
            rest = [m.artifacts async for m in iterator]
            return first, pending, rest

        first, pending, rest = asyncio.run(_run())
        assert first.artifacts[0].text.strip() == "正文"
        assert pending == []  # 首条产出时慢渲染还没跑完
        assert rest[0][0].png == b"png"

    def test_strict_order_with_slow_first(self, tmp_path):
        """第 1 组渲染慢：第 2 组即便先好也必须等它，产出顺序不变。"""
        from render.chain import plan_chain

        def dispatch(seg):
            if seg.code.strip() == "slow":
                time.sleep(0.1)
                return b"slow"
            return b"fast"

        async def _run():
            pipeline = await plan_chain(
                "```py\nslow\n```\n\n```py\nfast\n```",
                _render_cfg(code="渲染图像"), seg_cfg, None, str(tmp_path), {CodeBlock: dispatch},
            )
            return [m.artifacts[0].png async for m in pipeline]

        assert asyncio.run(_run()) == [b"slow", b"fast"]

    def test_render_timeout_degrades(self, tmp_path):
        """渲染超过保险丝：按失败降级为 .md 文件，不抛异常。"""
        def hang(seg):
            time.sleep(0.3)
            return b"never"

        cfg = _render_cfg(code="渲染图像")
        with patch("render.chain._RENDER_TIMEOUT", 0.01):
            result = _collect(
                "```py\nx=1\n```", cfg, seg_cfg, None, str(tmp_path),
                renderers={CodeBlock: hang},
            )
        assert len(result) == 1
        assert result[0][0].name.endswith(".md")
        with open(result[0][0].path, encoding="utf-8") as f:
            assert "x=1" in f.read()

    def test_timeout_with_file_mode_keeps_md(self, tmp_path):
        """超时 + 渲染且md文件：仍写 .md 文件，不丢弃。"""
        def hang(seg):
            time.sleep(0.3)
            return b"never"

        cfg = _render_cfg(code="渲染且md文件")
        with patch("render.chain._RENDER_TIMEOUT", 0.01):
            result = _collect(
                "```py\nx=1\n```", cfg, seg_cfg, None,
                data_dir=str(tmp_path), renderers={CodeBlock: hang},
            )
        assert len(result) == 1
        assert result[0][0].name.startswith("code_")
        assert result[0][0].name.endswith(".md")

    def test_counts_images_and_files(self, tmp_path):
        """产出过程中累计图片与文件数量。"""
        from render.chain import plan_chain

        fake = MagicMock(return_value=b"png")

        async def _run():
            pipeline = await plan_chain(
                "```py\nx=1\n```", _render_cfg(code="渲染且md文件"), seg_cfg, None,
                str(tmp_path), {CodeBlock: fake},
            )
            [m async for m in pipeline]
            return pipeline.image_count, pipeline.file_count

        assert asyncio.run(_run()) == (1, 1)

    def test_cancel_stops_pending_tasks(self, tmp_path):
        """cancel 取消未完成的渲染任务。"""
        from render.chain import plan_chain

        def hang(seg):
            time.sleep(0.05)
            return b"never"

        async def _run():
            pipeline = await plan_chain(
                "```py\nx=1\n```", _render_cfg(code="渲染图像"), seg_cfg, None,
                str(tmp_path), {CodeBlock: hang},
            )
            pipeline.cancel()
            await asyncio.sleep(0)  # 让取消生效
            return [task.cancelled() for task in pipeline.tasks]

        assert asyncio.run(_run()) == [True]
