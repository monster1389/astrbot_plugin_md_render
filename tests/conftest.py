"""测试配置 — 注入项目根目录与 mock 依赖。"""
import sys
import types
from pathlib import Path

# 将项目根目录加入 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Mock astrbot.api — AstrBot 框架运行时依赖，仅在插件宿主中可用
if "astrbot" not in sys.modules:
    _astrbot = types.ModuleType("astrbot")
    _astrbot_api = types.ModuleType("astrbot.api")

    class _MockLogger:
        """静默日志桩，避免测试期间因缺少 logger 而崩溃。"""
        @staticmethod
        def warning(msg: str, *args, **kwargs) -> None:
            pass

    _astrbot_api.logger = _MockLogger()
    _astrbot.api = _astrbot_api
    sys.modules["astrbot"] = _astrbot
    sys.modules["astrbot.api"] = _astrbot_api

# Mock astrbot.api.message_components — 提供 Plain/Image/File 桩类
class MockPlain:
    def __init__(self, text: str = ""):
        self.text = text

MockPlain.__name__ = "Plain"
MockPlain.__qualname__ = "Plain"

class MockImage:
    @staticmethod
    def fromFileSystem(path: str):
        img = MockImage()
        img.file = path
        return img

    @staticmethod
    def fromBytes(data: bytes):
        img = MockImage()
        img.data = data
        return img

class MockFile:
    def __init__(self, name: str = "", file: str = ""):
        self.name = name
        self.file = file

_mock_msg_comp = types.ModuleType("astrbot.api.message_components")
_mock_msg_comp.Plain = MockPlain
_mock_msg_comp.Image = MockImage
_mock_msg_comp.File = MockFile
sys.modules["astrbot.api.message_components"] = _mock_msg_comp
