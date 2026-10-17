"""管道编排测试：消息链 → 渲染流水线 → 待发送消息列表。"""
import asyncio
import time
from unittest.mock import MagicMock, patch

from astrbot.api.message_components import Plain, Image

from render.parser import CodeBlock
from render.config import CleanConfig, RenderConfig, SegmentConfig


def _make_cfg(**overrides):
    """构造测试用 RenderConfig。"""
    defaults = {
        "code_mode": "不处理",
        "table_mode": "不处理",
        "expr_mode": "不处理",
        "temp_ttl": 0,
    }
    return RenderConfig(**(defaults | overrides))


def _make_seg_cfg(**overrides):
    """构造测试用 SegmentConfig。"""
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


class TestPlanChain:
    def test_empty_chain_returns_none(self):
        """空链返回 None。"""
        assert _collect([], _make_cfg(), seg_cfg, None) is None

    def test_blank_text_returns_none(self):
        """纯空白文本返回 None。"""
        assert _collect([Plain("   ")], _make_cfg(), seg_cfg, None) is None

    def test_noop_returns_none(self):
        """无元素、无清洗、无切分 → None（链原样保留）。"""
        assert _collect([Plain("普通文本")], _make_cfg(), seg_cfg, None) is None

    def test_cleaning_produces_messages(self):
        """仅清洗开启：产出清洗后的单条消息。"""
        result = _collect([Plain("**加粗**")], _make_cfg(), seg_cfg, _make_clean_cfg())
        assert [c.text for c in result[0]] == ["加粗"]

    def test_keep_original_splits_text_and_image(self):
        """渲染且保留原文：原文文本前置，图片留末条。"""
        fake = MagicMock(return_value=b"fake_png")
        cfg = _make_cfg(code_mode="渲染且保留原文")
        result = _collect(
            [Plain("```py\nx=1\n```")], cfg, seg_cfg, None, renderers={CodeBlock: fake}
        )
        assert len(result) == 2
        assert "x=1" in result[0][0].text
        assert result[1][0].data == b"fake_png"

    def test_divider_split_returns_groups(self):
        """分隔线=切分：每组一条消息。"""
        seg_cfg = _make_seg_cfg(divider_mode="切分")
        result = _collect(
            [Plain("第一段\n\n---\n\n第二段\n\n---\n\n第三段")], _make_cfg(), seg_cfg, None
        )
        assert len(result) == 3
        assert result[0][0].text.strip() == "第一段"
        assert result[1][0].text.strip() == "第二段"
        assert result[2][0].text.strip() == "第三段"

    def test_blank_line_split_returns_groups(self):
        """连续换行=切分：空行分隔的段落各一条。"""
        seg_cfg = _make_seg_cfg(blank_line_mode="切分")
        result = _collect([Plain("第一段\n\n第二段\n\n第三段")], _make_cfg(), seg_cfg, None)
        assert len(result) == 3
        assert [c.text for c in result[0]] == ["第一段"]
        assert [c.text for c in result[1]] == ["第二段"]
        assert [c.text for c in result[2]] == ["第三段"]

    def test_interleaved_components_in_order(self):
        """交错元素按组件拆条，保持阅读顺序。"""
        fake = MagicMock(side_effect=lambda seg: b"png_" + seg.code.encode())
        cfg = _make_cfg(code_mode="渲染且保留原文")
        result = _collect(
            [Plain("正文第一行\n\n```py\nx=1\n```\n\n```py\ny=2\n```")],
            cfg, seg_cfg, None, renderers={CodeBlock: fake},
        )
        assert len(result) == 5
        assert result[0][0].text.strip() == "正文第一行"
        assert "x=1" in result[1][0].text
        assert result[2][0].data == b"png_x=1"
        assert "y=2" in result[3][0].text
        assert result[4][0].data == b"png_y=2"

    def test_non_plain_prepended_to_first(self):
        """原链非 Plain 组件前置到首条消息。"""
        seg_cfg = _make_seg_cfg(divider_mode="切分")
        img = Image.fromFileSystem("/tmp/a.png")
        result = _collect([img, Plain("第一段\n\n---\n\n第二段")], _make_cfg(), seg_cfg, None)
        assert len(result) == 2
        assert result[0][0] is img
        assert result[0][1].text == "第一段"

    def test_divider_split_with_cleaning(self):
        """分隔线=切分 + 清洗：切分点两侧文本各自成条且清洗干净。"""
        seg_cfg = _make_seg_cfg(divider_mode="切分")
        result = _collect(
            [Plain("好，第一轮回顾 (。-`ω´-)\n\n---\n\n**测试 1：纯闲聊**")],
            _make_cfg(), seg_cfg, _make_clean_cfg(),
        )
        assert len(result) == 2
        assert result[0][0].text == "好，第一轮回顾 (。-`ω´-)"
        assert result[1][0].text == "测试 1：纯闲聊"

    def test_passes_renderers(self):
        """plan_chain 透传 renderers 到 build_chain。"""
        fake = MagicMock(return_value=b"fake_png")
        cfg = _make_cfg(code_mode="渲染图像")
        result = _collect(
            [Plain("```py\nx=1\n```")], cfg, seg_cfg, None, renderers={CodeBlock: fake}
        )
        fake.assert_called_once()
        assert isinstance(result[0][0], Image)


class TestPipelineStreaming:
    """流水线语义：提交即开工、严格保序、超时降级、产物计数、取消。"""

    def test_first_message_ready_before_slow_render_finishes(self):
        """首条纯文本不必等后面的慢渲染——流水线不向前多看一条。"""
        from render.chain import plan_chain

        finished: list[str] = []

        def slow(seg):
            time.sleep(0.2)
            finished.append("done")
            return b"png"

        async def _run():
            pipeline = await plan_chain(
                [Plain("正文\n\n```py\nx=1\n```")], _make_cfg(code_mode="渲染图像"), seg_cfg,
                None, "/tmp", {CodeBlock: slow},
            )
            iterator = pipeline.__aiter__()
            first = await iterator.__anext__()
            pending = list(finished)
            rest = [m.chain async for m in iterator]
            return first, pending, rest

        first, pending, rest = asyncio.run(_run())
        assert first.chain[0].text.strip() == "正文"
        assert pending == []  # 首条产出时慢渲染还没跑完
        assert rest[0][0].data == b"png"

    def test_strict_order_with_slow_first(self):
        """第 1 组渲染慢：第 2 组即便先好也必须等它，产出顺序不变。"""
        from render.chain import plan_chain

        def dispatch(seg):
            if seg.code.strip() == "slow":
                time.sleep(0.1)
                return b"slow"
            return b"fast"

        async def _run():
            pipeline = await plan_chain(
                [Plain("```py\nslow\n```\n\n```py\nfast\n```")],
                _make_cfg(code_mode="渲染图像"), seg_cfg, None, "/tmp", {CodeBlock: dispatch},
            )
            return [m.chain[0].data async for m in pipeline]

        assert asyncio.run(_run()) == [b"slow", b"fast"]

    def test_render_timeout_degrades(self):
        """渲染超过保险丝：按失败降级为原文，不抛异常。"""
        def hang(seg):
            time.sleep(0.3)
            return b"never"

        cfg = _make_cfg(code_mode="渲染图像")
        with patch("render.chain._RENDER_TIMEOUT", 0.01):
            result = _collect(
                [Plain("```py\nx=1\n```")], cfg, seg_cfg, None, renderers={CodeBlock: hang}
            )
        assert len(result) == 1
        assert isinstance(result[0][0], Plain)
        assert "x=1" in result[0][0].text

    def test_timeout_with_file_mode_keeps_md(self, tmp_path):
        """超时 + 渲染且md文件：仍写 .md 文件，不丢弃。"""
        def hang(seg):
            time.sleep(0.3)
            return b"never"

        cfg = _make_cfg(code_mode="渲染且md文件")
        with patch("render.chain._RENDER_TIMEOUT", 0.01):
            result = _collect(
                [Plain("```py\nx=1\n```")], cfg, seg_cfg, None,
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
                [Plain("```py\nx=1\n```")], _make_cfg(code_mode="渲染且md文件"), seg_cfg, None,
                str(tmp_path), {CodeBlock: fake},
            )
            [m async for m in pipeline]
            return pipeline.image_count, pipeline.file_count

        assert asyncio.run(_run()) == (1, 1)

    def test_cancel_stops_pending_tasks(self):
        """cancel 取消未完成的渲染任务。"""
        from render.chain import plan_chain

        def hang(seg):
            time.sleep(0.05)
            return b"never"

        async def _run():
            pipeline = await plan_chain(
                [Plain("```py\nx=1\n```")], _make_cfg(code_mode="渲染图像"), seg_cfg, None,
                "/tmp", {CodeBlock: hang},
            )
            pipeline.cancel()
            await asyncio.sleep(0)  # 让取消生效
            return [task.cancelled() for task in pipeline.tasks]

        assert asyncio.run(_run()) == [True]
