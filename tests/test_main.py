"""on_decorating_result 事件处理测试。"""
import asyncio
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

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


# 符合 main.py 中 type(comp).__name__ == "Plain" 检查的 Plain 桩
Plain = type('Plain', (), {
    '__init__': lambda self, text="": setattr(self, 'text', text or ""),
})


def _make_event(chain: list):
    """构造 mock AstrMessageEvent，携带指定 chain。"""
    result = MagicMock()
    result.chain = chain
    event = MagicMock()
    event.get_result.return_value = result
    return event


class TestOnDecoratingResultWithoutRenderableElements:
    """无代码块/表格/表达式时，仍应对纯文本执行清洗。"""

    def test_cleans_markdown_when_no_renderable_elements(self):
        """**加粗** 和 > 引用应在清洗后去除，即使没有任何渲染元素。"""
        from main import MdRenderPlugin
        from render.utils import load_config

        chain = [Plain("**先让...所有人**\n\n> 1%\n\n**立刻回滚**")]
        event = _make_event(chain)

        config = {
            "渲染": {"代码块": "不处理", "表格": "不处理", "表达式": "不处理", "分隔线": "不处理", "临时文件存活": 0},
            "清洗": {"加粗": True, "引用": True},
        }

        with patch('main.StarTools') as mock_tools:
            mock_tools.get_data_dir.return_value = "/tmp/test_md_render"
            plugin = MdRenderPlugin(context=MagicMock(), config=config)
            plugin.cfg, plugin.clean_cfg = load_config(config)

            asyncio.run(plugin.on_decorating_result(event))

            updated = event.get_result.return_value.chain
            text = "".join(c.text for c in updated)
            assert "**" not in text, f"加粗标记应被去除: {text}"
            assert "> " not in text, f"引用标记应被去除: {text}"

    def test_skips_when_no_renderable_and_cleaning_disabled(self):
        """无渲染元素且清洗全关时，应跳过（原文不变）。"""
        from main import MdRenderPlugin
        from render.utils import load_config

        chain = [Plain("**原文保留**")]
        event = _make_event(chain)

        config = {
            "渲染": {"代码块": "不处理", "表格": "不处理", "表达式": "不处理", "分隔线": "不处理", "临时文件存活": 0},
            "清洗": {"加粗": False, "斜体": False, "删除线": False, "行内代码": False, "链接": False, "标题": False, "列表标记（无序）": False, "列表标记（有序）": False, "引用": False, "图片": False},
        }

        with patch('main.StarTools') as mock_tools:
            mock_tools.get_data_dir.return_value = "/tmp/test_md_render"
            plugin = MdRenderPlugin(context=MagicMock(), config=config)
            plugin.cfg, plugin.clean_cfg = load_config(config)

            asyncio.run(plugin.on_decorating_result(event))

            updated = event.get_result.return_value.chain
            text = "".join(c.text for c in updated)
            assert "**" in text, "清洗全关时原文应保留不变"


class TestSplitIntoMessages:
    def _make_plugin(self, config, context):
        from main import MdRenderPlugin
        from render.utils import load_config

        plugin = MdRenderPlugin(context=context, config=config)
        plugin.cfg, plugin.clean_cfg = load_config(config)
        return plugin

    def test_divider_split_sends_front_segments(self):
        """分隔线=切分：前置段逐条 send，末段留在 result.chain。"""
        from unittest.mock import AsyncMock, MagicMock

        chain = [Plain("第一段\n\n---\n\n第二段\n\n---\n\n第三段")]
        event = _make_event(chain)
        event.unified_msg_origin = "napcat:FriendMessage:1"

        config = {
            "渲染": {"代码块": "不处理", "表格": "不处理", "表达式": "不处理", "分隔线": "切分", "连续换行": "不处理", "发送延时": False, "临时文件存活": 0},
            "清洗": {"加粗": False, "斜体": False, "删除线": False, "行内代码": False, "链接": False, "标题": False, "列表标记（无序）": False, "列表标记（有序）": False, "引用": False, "图片": False},
        }
        context = MagicMock()
        context.send_message = AsyncMock()

        with patch('main.StarTools') as mock_tools:
            mock_tools.get_data_dir.return_value = "/tmp/test_md_render"
            plugin = self._make_plugin(config, context)
            asyncio.run(plugin.on_decorating_result(event))

        assert context.send_message.await_count == 2
        updated = event.get_result.return_value.chain
        text = "".join(c.text for c in updated)
        assert text.strip() == "第三段"

    def test_blank_line_split_sends_front_segments(self):
        """连续换行=切分：空行分隔的段落逐条 send，末段留在 result.chain。"""
        from unittest.mock import AsyncMock, MagicMock

        chain = [Plain("第一段\n\n第二段\n\n第三段")]
        event = _make_event(chain)
        event.unified_msg_origin = "napcat:FriendMessage:1"

        config = {
            "渲染": {"代码块": "不处理", "表格": "不处理", "表达式": "不处理", "分隔线": "不处理", "连续换行": "切分", "发送延时": False, "临时文件存活": 0},
            "清洗": {"加粗": False, "斜体": False, "删除线": False, "行内代码": False, "链接": False, "标题": False, "列表标记（无序）": False, "列表标记（有序）": False, "引用": False, "图片": False},
        }
        context = MagicMock()
        context.send_message = AsyncMock()

        with patch('main.StarTools') as mock_tools:
            mock_tools.get_data_dir.return_value = "/tmp/test_md_render"
            plugin = self._make_plugin(config, context)
            asyncio.run(plugin.on_decorating_result(event))

        assert context.send_message.await_count == 2
        updated = event.get_result.return_value.chain
        text = "".join(c.text for c in updated)
        assert text.strip() == "第三段"

    def test_split_delay_applied_when_enabled(self):
        """发送延时=开时，前置消息之间应随机延时。"""
        from unittest.mock import AsyncMock, MagicMock, patch

        chain = [Plain("第一段\n\n---\n\n第二段\n\n---\n\n第三段")]
        event = _make_event(chain)
        event.unified_msg_origin = "napcat:FriendMessage:1"

        config = {
            "渲染": {"代码块": "不处理", "表格": "不处理", "表达式": "不处理", "分隔线": "切分", "连续换行": "不处理", "发送延时": True, "临时文件存活": 0},
            "清洗": {"加粗": False, "斜体": False, "删除线": False, "行内代码": False, "链接": False, "标题": False, "列表标记（无序）": False, "列表标记（有序）": False, "引用": False, "图片": False},
        }
        context = MagicMock()
        context.send_message = AsyncMock()

        with patch('main.StarTools') as mock_tools, \
                patch('main.asyncio.sleep', new=AsyncMock()) as mock_sleep, \
                patch('main.random.uniform', return_value=1.5):
            mock_tools.get_data_dir.return_value = "/tmp/test_md_render"
            plugin = self._make_plugin(config, context)
            asyncio.run(plugin.on_decorating_result(event))

        assert context.send_message.await_count == 2
        assert mock_sleep.await_count == 2
        mock_sleep.assert_awaited_with(1.5)


class TestKeepOriginalSplit:
    def test_keep_original_splits_text_and_image(self):
        """渲染且保留原文：原文切分为前置文本消息，图片留在末段。"""
        from unittest.mock import AsyncMock, MagicMock
        from main import MdRenderPlugin
        from render.utils import load_config

        chain = [Plain("```py\nx=1\n```")]
        event = _make_event(chain)
        event.unified_msg_origin = "napcat:FriendMessage:1"

        config = {
            "渲染": {"代码块": "渲染且保留原文", "表格": "不处理", "表达式": "不处理", "分隔线": "不处理", "连续换行": "不处理", "发送延时": False, "临时文件存活": 0},
            "清洗": {"加粗": False, "斜体": False, "删除线": False, "行内代码": False, "链接": False, "标题": False, "列表标记（无序）": False, "列表标记（有序）": False, "引用": False, "图片": False},
        }
        context = MagicMock()
        context.send_message = AsyncMock()

        with patch('main.StarTools') as mock_tools, \
                patch('render.chain.render_code', return_value=b"fake_png"):
            mock_tools.get_data_dir.return_value = "/tmp/test_md_render"
            plugin = MdRenderPlugin(context=context, config=config)
            plugin.cfg, plugin.clean_cfg = load_config(config)
            asyncio.run(plugin.on_decorating_result(event))

        # 前置文本消息已独立发送，末段为图片
        assert context.send_message.await_count == 1
        sent_chain = context.send_message.call_args[0][1].chain
        assert len(sent_chain) == 1
        assert "x=1" in sent_chain[0].text

        updated = event.get_result.return_value.chain
        assert len(updated) == 1
        assert updated[0].data == b"fake_png"


class TestInterleavedSplit:
    def test_interleaved_components_split_in_order(self):
        """多个交错元素按组件逐条拆发，保持阅读顺序。"""
        from unittest.mock import AsyncMock, MagicMock
        from main import MdRenderPlugin
        from render.utils import load_config

        chain = [Plain("正文第一行\n\n```py\nx=1\n```\n\n```py\ny=2\n```")]
        event = _make_event(chain)
        event.unified_msg_origin = "napcat:FriendMessage:1"

        config = {
            "渲染": {"代码块": "渲染且保留原文", "表格": "不处理", "表达式": "不处理", "分隔线": "不处理", "连续换行": "不处理", "发送延时": False, "临时文件存活": 0},
            "清洗": {"加粗": False, "斜体": False, "删除线": False, "行内代码": False, "链接": False, "标题": False, "列表标记（无序）": False, "列表标记（有序）": False, "引用": False, "图片": False},
        }
        context = MagicMock()
        context.send_message = AsyncMock()

        def _fake_render(seg, cfg, data_dir):
            return b"png_" + seg.code.encode()

        with patch('main.StarTools') as mock_tools, \
                patch('render.chain.render_code', side_effect=_fake_render):
            mock_tools.get_data_dir.return_value = "/tmp/test_md_render"
            plugin = MdRenderPlugin(context=context, config=config)
            plugin.cfg, plugin.clean_cfg = load_config(config)
            asyncio.run(plugin.on_decorating_result(event))

        # 4 条前置独立发送：正文 / 代码1原文 / 图1 / 代码2原文；末段为图2
        assert context.send_message.await_count == 4
        sent = [c.args[1].chain for c in context.send_message.await_args_list]
        assert sent[0][0].text.strip() == "正文第一行"
        assert "x=1" in sent[1][0].text
        assert sent[2][0].data == b"png_x=1"
        assert "y=2" in sent[3][0].text

        updated = event.get_result.return_value.chain
        assert len(updated) == 1
        assert updated[0].data == b"png_y=2"

    def test_two_tier_delay(self):
        """发送延时=开：文本消息 0.3~1s，含媒体消息 1~3s。"""
        from unittest.mock import AsyncMock, MagicMock
        from main import MdRenderPlugin
        from render.utils import load_config

        chain = [Plain("```py\nx=1\n```\n\n尾段文本")]
        event = _make_event(chain)
        event.unified_msg_origin = "napcat:FriendMessage:1"

        config = {
            "渲染": {"代码块": "渲染且保留原文", "表格": "不处理", "表达式": "不处理", "分隔线": "不处理", "连续换行": "不处理", "发送延时": True, "临时文件存活": 0},
            "清洗": {"加粗": False, "斜体": False, "删除线": False, "行内代码": False, "链接": False, "标题": False, "列表标记（无序）": False, "列表标记（有序）": False, "引用": False, "图片": False},
        }
        context = MagicMock()
        context.send_message = AsyncMock()

        ranges: list[tuple] = []

        def _uniform(a, b):
            ranges.append((a, b))
            return 1.0

        def _fake_render(seg, cfg, data_dir):
            return b"png"

        with patch('main.StarTools') as mock_tools, \
                patch('render.chain.render_code', side_effect=_fake_render), \
                patch('main.random.uniform', side_effect=_uniform), \
                patch('main.asyncio.sleep', new=AsyncMock()):
            mock_tools.get_data_dir.return_value = "/tmp/test_md_render"
            plugin = MdRenderPlugin(context=context, config=config)
            plugin.cfg, plugin.clean_cfg = load_config(config)
            asyncio.run(plugin.on_decorating_result(event))

        # 前置两条：代码原文(文本) → 0.3~1s；渲染图(媒体) → 1~3s；末段尾段文本
        assert ranges == [(0.3, 1.0), (1.0, 3.0)]
