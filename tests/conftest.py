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
