"""送达模块测试。"""
import asyncio
from unittest.mock import AsyncMock, patch

from astrbot.api.message_components import Plain, Image, File

from render.config import SegmentConfig


def _make_cfg(**overrides):
    """构造测试用 SegmentConfig，支持按需覆盖。"""
    defaults = {
        "divider_mode": "不处理",
        "blank_line_mode": "不处理",
    }
    return SegmentConfig(**(defaults | overrides))


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

    def test_summarize(self):
        """日志摘要：文本截断、图片文件名、文件名称、空文本。"""
        from render.deliver import _summarize

        assert _summarize([Plain("短文本")]) == "文本「短文本」"
        assert _summarize([Plain("x" * 30)]) == "文本「" + "x" * 24 + "…」"
        assert _summarize([Plain("")]) == "空"
        assert _summarize([Plain("   ")]) == "空"
        assert _summarize([Image.fromFileSystem("/tmp/code_123.png")]) == "图片 code_123.png"
        assert _summarize([Image.fromBytes(b"png")]) == "图片"
        assert _summarize([File(name="x.md", file="/tmp/x.md")]) == "文件 x.md"


class TestTempFileLifecycle:
    """临时文件生命周期：发送完成即删，尾条交棒前刷新。"""

    def test_deletes_temp_files_after_send(self):
        """发送完成的条目的临时文件立即删除。"""
        from render.deliver import deliver

        temp_png = "/tmp/test_md_render/temp/code_20260819_114940_123456.png"
        img = Image.fromFileSystem(temp_png)
        send = AsyncMock()
        with patch("render.tempstore.os.remove") as mock_remove, \
                patch("render.tempstore.os.utime") as mock_utime:
            asyncio.run(deliver(send, [[img], [Plain("尾")]], _make_cfg(send_delay=False)))
        mock_remove.assert_called_once_with(temp_png)
        mock_utime.assert_not_called()

    def test_touches_tail_temp_files(self):
        """尾条的临时文件交棒前刷新时间戳、不删除。"""
        from render.deliver import deliver

        temp_md = "/tmp/test_md_render/temp/table_20260819_114940_123456.md"
        md = File(name="table.md", file=temp_md)
        send = AsyncMock()
        with patch("render.tempstore.os.remove") as mock_remove, \
                patch("render.tempstore.os.utime") as mock_utime:
            result = asyncio.run(deliver(send, [[Plain("A")], [md]], _make_cfg(send_delay=False)))
        mock_remove.assert_not_called()
        mock_utime.assert_called_once_with(temp_md, None)
        assert result[0] is md

    def test_single_message_tail_touched_not_sent(self):
        """单条消息全部留尾：不发送、只刷新时间戳。"""
        from render.deliver import deliver

        temp_png = "/tmp/test_md_render/temp/code_20260819_114940_123456.png"
        img = Image.fromFileSystem(temp_png)
        send = AsyncMock()
        with patch("render.tempstore.os.remove") as mock_remove, \
                patch("render.tempstore.os.utime") as mock_utime:
            result = asyncio.run(deliver(send, [[img]], _make_cfg(send_delay=False)))
        send.assert_not_called()
        mock_remove.assert_not_called()
        mock_utime.assert_called_once_with(temp_png, None)
        assert result[0] is img

    def test_ignores_foreign_files(self):
        """非本插件临时文件（用户原始图片等）不被删除或刷新。"""
        from render.deliver import deliver

        foreign = Image.fromFileSystem("/tmp/user_photo.png")
        temp_png = "/tmp/test_md_render/temp/expr_20260819_114940_123456.png"
        send = AsyncMock()
        with patch("render.tempstore.os.remove") as mock_remove, \
                patch("render.tempstore.os.utime") as mock_utime:
            asyncio.run(deliver(
                send,
                [[foreign, Image.fromFileSystem(temp_png)], [Plain("尾")]],
                _make_cfg(send_delay=False),
            ))
        mock_remove.assert_called_once_with(temp_png)
        mock_utime.assert_not_called()
