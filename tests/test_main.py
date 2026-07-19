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
        pass

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

_event.filter = _MockFilter()
_event.AstrMessageEvent = _MockAstrMessageEvent
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
