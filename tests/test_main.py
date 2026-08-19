"""on_decorating_result 事件处理测试：管线接入的薄接线测试。"""
import asyncio
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# conftest.py 已 mock astrbot / astrbot.api / astrbot.api.message_components
# 补上 main.py 额外需要的 astrbot.api.star 和 astrbot.api.event mock

_star = types.ModuleType("astrbot.api.star")


class _MockContext:
    pass


class _MockStar:
    def __init__(self, context=None):
        self.context = context


class _MockStarTools:
    @staticmethod
    def get_data_dir(name: str) -> str:
        return "/tmp/test_md_render"


def _register(*args, **kwargs):
    def decorator(cls):
        return cls
    return decorator


_star.Context = _MockContext
_star.Star = _MockStar
_star.StarTools = _MockStarTools
_star.register = _register
sys.modules["astrbot.api.star"] = _star

_event = types.ModuleType("astrbot.api.event")


class _MockFilter:
    @staticmethod
    def on_decorating_result(priority=1000):
        def decorator(fn):
            return fn
        return decorator


class _MockAstrMessageEvent:
    pass


class _MockMessageChain:
    def __init__(self):
        self.chain = []


_event.filter = _MockFilter()
_event.AstrMessageEvent = _MockAstrMessageEvent
_event.MessageChain = _MockMessageChain
sys.modules["astrbot.api.event"] = _event

# AstrBotConfig — main.py 用其做类型标注
import astrbot.api  # noqa: E402
astrbot.api.AstrBotConfig = dict

from astrbot.api.message_components import Plain  # noqa: E402


def _make_event(chain: list):
    """构造 mock AstrMessageEvent，携带指定 chain。"""
    result = MagicMock()
    result.chain = chain
    event = MagicMock()
    event.get_result.return_value = result
    return event


def _make_plugin(context: MagicMock):
    """构造插件实例，cfg 用 MagicMock、clean_cfg 置 None。"""
    from main import MdRenderPlugin

    plugin = MdRenderPlugin(context=context, config={})
    plugin.cfg = MagicMock()
    plugin.seg_cfg = MagicMock()
    plugin.clean_cfg = None
    return plugin


class TestProcessChainWiring:
    """on_decorating_result 只负责接线：process_chain 与 deliver 两处 seam。"""

    def test_returns_early_when_process_chain_none(self):
        """process_chain 返回 None → 原样保留，不交付、不发送。"""
        chain = [Plain("**加粗**")]
        event = _make_event(chain)
        event.unified_msg_origin = "napcat:FriendMessage:1"
        context = MagicMock()
        context.send_message = AsyncMock()

        with patch("main.process_chain", AsyncMock(return_value=None)) as mock_pc, \
                patch("main.deliver", AsyncMock()) as mock_deliver, \
                patch("main.StarTools") as mock_tools:
            mock_tools.get_data_dir.return_value = "/tmp/test_md_render"
            plugin = _make_plugin(context)
            asyncio.run(plugin.on_decorating_result(event))

        assert mock_pc.await_count == 1
        mock_deliver.assert_not_awaited()
        context.send_message.assert_not_awaited()
        assert event.get_result.return_value.chain is chain

    def test_delivers_with_process_chain_messages(self):
        """process_chain 返回消息 → deliver 收尾，result.chain 取其返回。"""
        messages = [[Plain("前置")], [Plain("尾条")]]
        tail = [Plain("尾条")]
        original_chain = [Plain("原文")]
        event = _make_event(original_chain)
        event.unified_msg_origin = "napcat:FriendMessage:1"
        context = MagicMock()
        context.send_message = AsyncMock()

        cfg = MagicMock()
        seg_cfg = MagicMock()

        with patch("main.process_chain", AsyncMock(return_value=messages)) as mock_pc, \
                patch("main.deliver", AsyncMock(return_value=tail)) as mock_deliver, \
                patch("main.StarTools") as mock_tools:
            mock_tools.get_data_dir.return_value = "/tmp/test_md_render"
            plugin = _make_plugin(context)
            plugin.cfg = cfg
            plugin.seg_cfg = seg_cfg
            asyncio.run(plugin.on_decorating_result(event))

        mock_pc.assert_awaited_once_with(
            original_chain, cfg, seg_cfg, None, "/tmp/test_md_render"
        )
        assert mock_deliver.await_count == 1
        assert mock_deliver.await_args[0][1] is messages
        assert mock_deliver.await_args[0][2] is seg_cfg
        assert event.get_result.return_value.chain is tail

    def test_send_callback_routes_to_context(self):
        """deliver 收到的 send 回调经 context.send_message 发送。"""
        event = _make_event([Plain("原文")])
        event.unified_msg_origin = "napcat:FriendMessage:1"
        context = MagicMock()
        context.send_message = AsyncMock()

        with patch("main.process_chain", AsyncMock(return_value=[[Plain("a")]])), \
                patch("main.deliver", AsyncMock(return_value=[Plain("a")])) as mock_deliver, \
                patch("main.StarTools") as mock_tools:
            mock_tools.get_data_dir.return_value = "/tmp/test_md_render"
            plugin = _make_plugin(context)
            asyncio.run(plugin.on_decorating_result(event))

            send_fn = mock_deliver.await_args[0][0]
            asyncio.run(send_fn([Plain("发送")]))

        origin, mc = context.send_message.await_args.args
        assert origin == "napcat:FriendMessage:1"
        assert mc.chain[0].text == "发送"
