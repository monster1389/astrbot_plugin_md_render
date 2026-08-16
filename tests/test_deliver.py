"""送达模块测试。"""
import asyncio
from unittest.mock import AsyncMock, patch

from astrbot.api.message_components import Plain, Image

from render.utils import RenderConfig


def _make_cfg(**overrides):
    """构造测试用 RenderConfig，支持按需覆盖。"""
    defaults = {
        "code_mode": "不处理",
        "table_mode": "不处理",
        "expr_mode": "不处理",
        "divider_mode": "不处理",
        "blank_line_mode": "不处理",
        "temp_ttl": 5,
    }
    return RenderConfig(**(defaults | overrides))


class TestDeliver:
    def test_single_message_kept_as_tail(self):
        """只有一条消息时全部留尾，不发送。"""
        from render.deliver import deliver

        send = AsyncMock()
        result = asyncio.run(deliver(send, [[Plain("唯一")]], _make_cfg(send_delay=False)))
        assert [c.text for c in result] == ["唯一"]
        send.assert_not_called()

    def test_returns_last_message_as_tail(self):
        """末条消息作为留尾返回，不发送。"""
        from render.deliver import deliver

        send = AsyncMock()
        result = asyncio.run(
            deliver(send, [[Plain("A")], [Plain("B")]], _make_cfg(send_delay=False))
        )
        assert [c.text for c in result] == ["B"]
        send.assert_awaited_once()
        assert send.await_args.args[0][0].text == "A"

    def test_sends_all_but_last_in_order(self):
        """除末条外全部按序发送。"""
        from render.deliver import deliver

        send = AsyncMock()
        messages = [[Plain("1")], [Plain("2")], [Plain("3")], [Plain("4")]]
        asyncio.run(deliver(send, messages, _make_cfg(send_delay=False)))
        assert send.await_count == 3
        assert [c.args[0][0].text for c in send.await_args_list] == ["1", "2", "3"]

    def test_skips_whitespace_only_messages(self):
        """纯空白消息跳过，不发送。"""
        from render.deliver import deliver

        send = AsyncMock()
        messages = [[Plain("   ")], [Plain("正文")], [Plain("尾")]]
        asyncio.run(deliver(send, messages, _make_cfg(send_delay=False)))
        send.assert_awaited_once()
        assert send.await_args.args[0][0].text == "正文"

    def test_two_tier_delay_ranges(self):
        """文本消息 0.3~1s，媒体消息 1~3s。"""
        from render.deliver import deliver

        send = AsyncMock()
        text_msg = [Plain("文本")]
        media_msg = [Image.fromBytes(b"png")]
        messages = [text_msg, media_msg, [Plain("尾")]]
        ranges: list[tuple] = []

        def _uniform(a, b):
            ranges.append((a, b))
            return 1.0

        with patch("render.deliver.random.uniform", side_effect=_uniform), \
                patch("render.deliver.asyncio.sleep", new=AsyncMock()):
            asyncio.run(deliver(send, messages, _make_cfg(send_delay=True)))

        assert ranges == [(0.3, 1.0), (1.0, 3.0)]

    def test_no_delay_when_disabled(self):
        """send_delay 关时不延时。"""
        from render.deliver import deliver

        send = AsyncMock()
        messages = [[Plain("A")], [Plain("B")]]
        with patch("render.deliver.random.uniform") as mock_uniform, \
                patch("render.deliver.asyncio.sleep", new=AsyncMock()) as mock_sleep:
            asyncio.run(deliver(send, messages, _make_cfg(send_delay=False)))
        mock_uniform.assert_not_called()
        mock_sleep.assert_not_called()

    def test_no_delay_after_skipped_empty(self):
        """空消息跳过时不触发延时。"""
        from render.deliver import deliver

        send = AsyncMock()
        messages = [[Plain("   ")], [Plain("正文")], [Plain("尾")]]
        with patch("render.deliver.random.uniform") as mock_uniform, \
                patch("render.deliver.asyncio.sleep", new=AsyncMock()):
            asyncio.run(deliver(send, messages, _make_cfg(send_delay=True)))
        send.assert_awaited_once()
        mock_uniform.assert_called_once()
