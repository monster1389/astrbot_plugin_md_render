"""测试配置工厂 —— 三块配置的默认值与流水线收集器。

默认值从真实来源派生：元素族的清洗开关来自元素注册表（有 ``clean`` 字段的元素
默认关，其余字段默认开）；元素族清单来自 ``FAMILIES``。测试只写自己关心的那几个
参数，不再各造一份默认值。
"""
from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from render.artifacts import Artifact
from render.config import CleanConfig, RenderConfig, SegmentConfig
from render.elements import ELEMENTS, FAMILIES

# 由元素注册表派生：这些清洗开关管的是元素，默认关
_ELEMENT_SWITCHES = frozenset(
    element.clean for element in ELEMENTS.values() if element.clean is not None
)


def render_cfg(temp_ttl: int = 0, **modes: str) -> RenderConfig:
    """构造测试用 RenderConfig；modes 用元素族键（code/table/expr/html/mermaid）。

    Args:
        temp_ttl: 临时文件存活分钟数，默认 0（图片只带字节，不落盘）。
        **modes: 元素族键 → 模式字符串，未指定的族一律「不处理」。

    Returns:
        渲染配置。
    """
    return RenderConfig(
        modes=dict.fromkeys(FAMILIES, "不处理") | modes,
        temp_ttl=temp_ttl,
    )


def segment_cfg(**overrides: Any) -> SegmentConfig:
    """构造测试用 SegmentConfig：默认不切分、无发送延时。

    Args:
        **overrides: 需要覆盖的字段。

    Returns:
        分段配置。
    """
    defaults: dict[str, Any] = {
        "divider_mode": "不处理",
        "blank_line_mode": "不处理",
        "send_delay": False,
    }
    return SegmentConfig(**(defaults | overrides))


def clean_cfg(**overrides: bool) -> CleanConfig:
    """构造测试用 CleanConfig：元素开关默认关，其余格式开关默认开。

    Args:
        **overrides: 需要覆盖的开关。

    Returns:
        清洗配置。
    """
    defaults = {
        name: name not in _ELEMENT_SWITCHES for name in vars(CleanConfig())
    }
    defaults.update(overrides)
    return CleanConfig(**defaults)


def collect(
    text: str,
    cfg: RenderConfig,
    seg_cfg: SegmentConfig,
    clean_cfg: CleanConfig | None,
    data_dir: str,
    renderers: dict[type, Callable] | None = None,
) -> list[list[Artifact]] | None:
    """建流水线并收集全部产出消息。

    Args:
        text: 待处理 markdown 文本。
        cfg: 渲染配置。
        seg_cfg: 分段配置。
        clean_cfg: 清洗配置，None 表示不清洗。
        data_dir: 插件数据目录路径（测试里用 tmp_path）。
        renderers: 渲染器覆盖层。

    Returns:
        每条消息的产物列表；plan_chain 判定无事可做时返回 None。
    """
    from render.chain import plan_chain

    async def _run() -> list[list[Artifact]] | None:
        pipeline = await plan_chain(
            text, cfg, seg_cfg, clean_cfg, data_dir, renderers
        )
        if pipeline is None:
            return None
        return [message.artifacts async for message in pipeline]

    return asyncio.run(_run())
