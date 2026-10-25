"""送达模块测试。"""
import asyncio
import time
from unittest.mock import AsyncMock, patch

from factories import segment_cfg as _make_cfg

from render.artifacts import Message, Picture, SourceFile, Text


class _FakePipeline:
    """deliver 只依赖异步可迭代，用消息列表或异步生成器伪装流水线。"""

    def __init__(self, source):
        self._source = source

    def __aiter__(self):
        if hasattr(self._source, "__aiter__"):
            return self._source.__aiter__()
        return self._list_iter(list(self._source))

    async def _list_iter(self, messages):
        last = len(messages) - 1
        for index, artifacts in enumerate(messages):
            yield Message(artifacts, is_tail=index == last)


class TestDeliver:
    def test_single_message_kept_as_tail(self):
        """只有一条消息时全部留尾，不发送。"""
        from render.deliver import deliver

        send = AsyncMock()
        result = asyncio.run(deliver(send, _FakePipeline([[Text("唯一")]]), _make_cfg(send_delay=False)))
        assert [c.text for c in result] == ["唯一"]
        send.assert_not_called()

    def test_returns_last_message_as_tail(self):
        """末条消息作为留尾返回，不发送。"""
        from render.deliver import deliver

        send = AsyncMock()
        result = asyncio.run(
            deliver(send, _FakePipeline([[Text("A")], [Text("B")]]), _make_cfg(send_delay=False))
        )
        assert [c.text for c in result] == ["B"]
        send.assert_awaited_once()
        assert send.await_args.args[0][0].text == "A"

    def test_sends_all_but_last_in_order(self):
        """除末条外全部按序发送。"""
        from render.deliver import deliver

        send = AsyncMock()
        messages = [[Text("1")], [Text("2")], [Text("3")], [Text("4")]]
        asyncio.run(deliver(send, _FakePipeline(messages), _make_cfg(send_delay=False)))
        assert send.await_count == 3
        assert [c.args[0][0].text for c in send.await_args_list] == ["1", "2", "3"]

    def test_skips_whitespace_only_messages(self):
        """纯空白消息跳过，不发送。"""
        from render.deliver import deliver

        send = AsyncMock()
        messages = [[Text("   ")], [Text("正文")], [Text("尾")]]
        asyncio.run(deliver(send, _FakePipeline(messages), _make_cfg(send_delay=False)))
        send.assert_awaited_once()
        assert send.await_args.args[0][0].text == "正文"

    def test_two_tier_delay_ranges(self):
        """间隔按待发消息的类型取区间：文本 0.3~1s，媒体 1~3s。"""
        from render.deliver import deliver

        send = AsyncMock()
        messages = [
            [Picture(png=b"png")],
            [Text("文本")],
            [Picture(png=b"png")],
            [Text("尾")],
        ]
        ranges: list[tuple] = []

        def _uniform(a, b):
            ranges.append((a, b))
            return 1.0

        with patch("render.deliver.random.uniform", side_effect=_uniform), \
                patch("render.deliver.asyncio.sleep", new=AsyncMock()):
            asyncio.run(deliver(send, _FakePipeline(messages), _make_cfg(send_delay=True)))

        # 首条发送前没有间隔；其后两条各自按自身类型取区间
        assert ranges == [(0.3, 1.0), (1.0, 3.0)]

    def test_no_delay_when_disabled(self):
        """send_delay 关时不延时。"""
        from render.deliver import deliver

        send = AsyncMock()
        messages = [[Text("A")], [Text("B")]]
        with patch("render.deliver.random.uniform") as mock_uniform, \
                patch("render.deliver.asyncio.sleep", new=AsyncMock()) as mock_sleep:
            asyncio.run(deliver(send, _FakePipeline(messages), _make_cfg(send_delay=False)))
        mock_uniform.assert_not_called()
        mock_sleep.assert_not_called()

    def test_first_send_has_no_delay(self):
        """首条发送没有前一条可比，不计延时（空消息跳过也不补）。"""
        from render.deliver import deliver

        send = AsyncMock()
        messages = [[Text("   ")], [Text("正文")], [Text("尾")]]
        with patch("render.deliver.random.uniform") as mock_uniform, \
                patch("render.deliver.asyncio.sleep", new=AsyncMock()):
            asyncio.run(deliver(send, _FakePipeline(messages), _make_cfg(send_delay=True)))
        send.assert_awaited_once()
        mock_uniform.assert_not_called()

    def test_delay_overlaps_with_render_wait(self):
        """渲染耗时计入间隔：等渲染 0.12s 后只补足到下限，不叠加。"""
        from render.deliver import deliver

        sleeps: list[float] = []

        async def fake_sleep(sec):
            sleeps.append(sec)

        async def slow_pipeline():
            yield Message([Picture(png=b"1")], is_tail=False)
            # 模拟第 2 条渲染耗时：要真的推进时钟，而 asyncio.sleep 已被替身接管
            time.sleep(0.12)  # noqa: ASYNC251
            yield Message([Picture(png=b"2")], is_tail=False)
            yield Message([Text("尾")], is_tail=True)

        with patch("render.deliver._DELAY_RANGES", {True: (0.3, 0.3), False: (0.3, 0.3)}), \
                patch("render.deliver.asyncio.sleep", new=fake_sleep):
            asyncio.run(
                deliver(AsyncMock(), _FakePipeline(slow_pipeline()), _make_cfg(send_delay=True))
            )

        assert len(sleeps) == 1
        assert 0.05 < sleeps[0] < 0.25  # ≈ 0.3 - 0.12：渲染已消耗的间隔不再叠加

    def test_no_delay_when_render_wait_exceeds_gap(self):
        """渲染耗时已超过下限：完全不补延时。"""
        from render.deliver import deliver

        sleeps: list[float] = []

        async def fake_sleep(sec):
            sleeps.append(sec)

        async def slow_pipeline():
            yield Message([Picture(png=b"1")], is_tail=False)
            time.sleep(0.4)  # noqa: ASYNC251 —— 同上，要真实耗时超过 0.3s 下限
            yield Message([Picture(png=b"2")], is_tail=False)
            yield Message([Text("尾")], is_tail=True)

        with patch("render.deliver._DELAY_RANGES", {True: (0.3, 0.3), False: (0.3, 0.3)}), \
                patch("render.deliver.asyncio.sleep", new=fake_sleep):
            asyncio.run(
                deliver(AsyncMock(), _FakePipeline(slow_pipeline()), _make_cfg(send_delay=True))
            )

        assert sleeps == []  # 渲染 0.4s 已超过 0.3s 下限，完全不补

    def test_summarize(self):
        """日志摘要：文本截断、图片文件名、文件名称、空文本。"""
        from render.deliver import _summarize

        assert _summarize([Text("短文本")]) == "文本「短文本」"
        assert _summarize([Text("x" * 30)]) == "文本「" + "x" * 24 + "…」"
        assert _summarize([Text("")]) == "空"
        assert _summarize([Text("   ")]) == "空"
        assert _summarize([Picture(png=b"", path="/tmp/code_123.png")]) == "图片 code_123.png"
        assert _summarize([Picture(png=b"png")]) == "图片"
        assert _summarize([SourceFile(path="/tmp/x.md")]) == "文件 x.md"


class TestTempFileLifecycle:
    """临时文件生命周期：发送完成即删，尾条交棒前刷新。"""

    def test_deletes_temp_files_after_send(self):
        """发送完成的条目的临时文件立即删除。"""
        from render.deliver import deliver

        temp_png = "/tmp/test_md_render/temp/code_20260819_114940_123456.png"
        img = Picture(png=b"", path=temp_png)
        send = AsyncMock()
        with patch("render.tempstore.os.remove") as mock_remove, \
                patch("render.tempstore.os.utime") as mock_utime:
            asyncio.run(
                deliver(send, _FakePipeline([[img], [Text("尾")]]), _make_cfg(send_delay=False))
            )
        mock_remove.assert_called_once_with(temp_png)
        mock_utime.assert_not_called()

    def test_touches_tail_temp_files(self):
        """尾条的临时文件交棒前刷新时间戳、不删除。"""
        from render.deliver import deliver

        temp_md = "/tmp/test_md_render/temp/table_20260819_114940_123456.md"
        md = SourceFile(path=temp_md)
        send = AsyncMock()
        with patch("render.tempstore.os.remove") as mock_remove, \
                patch("render.tempstore.os.utime") as mock_utime:
            result = asyncio.run(
                deliver(send, _FakePipeline([[Text("A")], [md]]), _make_cfg(send_delay=False))
            )
        mock_remove.assert_not_called()
        mock_utime.assert_called_once_with(temp_md, None)
        assert result[0] == md

    def test_single_message_tail_touched_not_sent(self):
        """单条消息全部留尾：不发送、只刷新时间戳。"""
        from render.deliver import deliver

        temp_png = "/tmp/test_md_render/temp/code_20260819_114940_123456.png"
        img = Picture(png=b"", path=temp_png)
        send = AsyncMock()
        with patch("render.tempstore.os.remove") as mock_remove, \
                patch("render.tempstore.os.utime") as mock_utime:
            result = asyncio.run(
                deliver(send, _FakePipeline([[img]]), _make_cfg(send_delay=False))
            )
        send.assert_not_called()
        mock_remove.assert_not_called()
        mock_utime.assert_called_once_with(temp_png, None)
        assert result[0] == img

