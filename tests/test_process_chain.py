"""管道编排测试：消息链 → 待发送消息列表。"""
import asyncio
from unittest.mock import MagicMock

from astrbot.api.message_components import Plain, Image

from render.parser import CodeBlock
from render.utils import CleanConfig, RenderConfig, SegmentConfig


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


class TestProcessChain:
    def test_empty_chain_returns_none(self):
        """空链返回 None。"""
        from render.chain import process_chain

        result = asyncio.run(process_chain([], _make_cfg(), seg_cfg, None, "/tmp"))
        assert result is None

    def test_blank_text_returns_none(self):
        """纯空白文本返回 None。"""
        from render.chain import process_chain

        result = asyncio.run(process_chain([Plain("   ")], _make_cfg(), seg_cfg, None, "/tmp"))
        assert result is None

    def test_noop_returns_none(self):
        """无元素、无清洗、无切分 → None（链原样保留）。"""
        from render.chain import process_chain

        result = asyncio.run(
            process_chain([Plain("普通文本")], _make_cfg(), seg_cfg, None, "/tmp")
        )
        assert result is None

    def test_cleaning_produces_messages(self):
        """仅清洗开启：产出清洗后的单条消息。"""
        from render.chain import process_chain

        result = asyncio.run(
            process_chain([Plain("**加粗**")], _make_cfg(), seg_cfg, _make_clean_cfg(), "/tmp")
        )
        assert result is not None
        assert [c.text for c in result[0]] == ["加粗"]

    def test_keep_original_splits_text_and_image(self):
        """渲染且保留原文：原文文本前置，图片留末条。"""
        from render.chain import process_chain

        fake = MagicMock(return_value=b"fake_png")
        cfg = _make_cfg(code_mode="渲染且保留原文")
        result = asyncio.run(
            process_chain([Plain("```py\nx=1\n```")], cfg, seg_cfg, None, "/tmp", renderers={CodeBlock: fake})
        )
        assert result is not None
        assert len(result) == 2
        assert "x=1" in result[0][0].text
        assert result[1][0].data == b"fake_png"

    def test_divider_split_returns_groups(self):
        """分隔线=切分：每组一条消息。"""
        from render.chain import process_chain

        cfg = _make_cfg()
        seg_cfg = _make_seg_cfg(divider_mode="切分")
        result = asyncio.run(
            process_chain([Plain("第一段\n\n---\n\n第二段\n\n---\n\n第三段")], cfg, seg_cfg, None, "/tmp")
        )
        assert result is not None
        assert len(result) == 3
        assert result[0][0].text.strip() == "第一段"
        assert result[1][0].text.strip() == "第二段"
        assert result[2][0].text.strip() == "第三段"

    def test_blank_line_split_returns_groups(self):
        """连续换行=切分：空行分隔的段落各一条。"""
        from render.chain import process_chain

        cfg = _make_cfg()
        seg_cfg = _make_seg_cfg(blank_line_mode="切分")
        result = asyncio.run(
            process_chain([Plain("第一段\n\n第二段\n\n第三段")], cfg, seg_cfg, None, "/tmp")
        )
        assert result is not None
        assert len(result) == 3
        assert [c.text for c in result[0]] == ["第一段"]
        assert [c.text for c in result[1]] == ["第二段"]
        assert [c.text for c in result[2]] == ["第三段"]

    def test_interleaved_components_in_order(self):
        """交错元素按组件拆条，保持阅读顺序。"""
        from render.chain import process_chain

        fake = MagicMock(side_effect=lambda seg, data_dir: b"png_" + seg.code.encode())
        cfg = _make_cfg(code_mode="渲染且保留原文")
        result = asyncio.run(
            process_chain([Plain("正文第一行\n\n```py\nx=1\n```\n\n```py\ny=2\n```")], cfg, seg_cfg, None, "/tmp", renderers={CodeBlock: fake})
        )
        assert result is not None
        assert len(result) == 5
        assert result[0][0].text.strip() == "正文第一行"
        assert "x=1" in result[1][0].text
        assert result[2][0].data == b"png_x=1"
        assert "y=2" in result[3][0].text
        assert result[4][0].data == b"png_y=2"

    def test_non_plain_prepended_to_first(self):
        """原链非 Plain 组件前置到首条消息。"""
        from render.chain import process_chain

        cfg = _make_cfg()
        seg_cfg = _make_seg_cfg(divider_mode="切分")
        img = Image.fromFileSystem("/tmp/a.png")
        result = asyncio.run(
            process_chain([img, Plain("第一段\n\n---\n\n第二段")], cfg, seg_cfg, None, "/tmp")
        )
        assert result is not None
        assert len(result) == 2
        assert result[0][0] is img
        assert result[0][1].text == "第一段"
