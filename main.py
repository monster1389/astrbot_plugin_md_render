"""AstrBot Markdown 渲染插件。

在 OnDecoratingResultEvent 阶段拦截消息链，将 markdown 代码块、表格、
数学表达式渲染为图片后替换到消息链中。
"""
from __future__ import annotations

import os
import sys
from typing import Any

from astrbot.api import AstrBotConfig, logger
from astrbot.api.all import MessageChain
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.message_components import Plain, Image, File as AstrFile
from astrbot.api.star import Context, Star, StarTools, register

_plugin_dir = os.path.dirname(os.path.abspath(__file__))
if _plugin_dir not in sys.path:
    sys.path.insert(0, _plugin_dir)

from render.parser import parse, CodeBlock, Table, InlineExpr, BlockExpr, Divider  # noqa: E402
from render.chain import build_chain, split_chain  # noqa: E402
from render.cleaner import start as _start_cleaner, stop as _stop_cleaner  # noqa: E402
from render.utils import load_config  # noqa: E402


@register(
    "astrbot_plugin_md_render",
    "monster1389",
    "Markdown 渲染插件",
    "1.0.0",
)
class MdRenderPlugin(Star):
    """将 QQ 消息中的 markdown 代码块、表格、数学表达式渲染为图片。

    Attributes:
        config: AstrBot 原始配置字典。
    """

    def __init__(self, context: Context, config: AstrBotConfig | None = None):
        super().__init__(context)
        self.config: dict[str, Any] = config or {}

    async def initialize(self):
        """插件初始化。"""
        data_dir = StarTools.get_data_dir("astrbot_plugin_md_render")
        temp_dir = os.path.join(data_dir, "temp")
        os.makedirs(temp_dir, exist_ok=True)
        cfg = load_config(self.config)
        _start_cleaner(str(data_dir), cfg.temp_ttl)
        logger.info("Markdown 渲染插件已启动")

    @filter.on_decorating_result(priority=1000)
    async def on_decorating_result(self, event: AstrMessageEvent):
        """装饰结果事件：解析 Plain 文本，渲染 markdown 元素并替换到 chain。

        Args:
            event: AstrBot 消息事件。
        """
        result = event.get_result()
        chain = result.chain
        if not chain:
            return

        data_dir = StarTools.get_data_dir("astrbot_plugin_md_render")

        # 收集所有 Plain 文本，拼接后统一解析
        text_parts: list[str] = []
        for comp in chain:
            if hasattr(comp, "text") and type(comp).__name__ == "Plain":
                text_parts.append(comp.text or "")
            elif hasattr(comp, "type") and comp.type == "Plain":
                text_parts.append(comp.text or "")

        full_text = "".join(text_parts)
        if not full_text.strip():
            return

        # 解析 → 组装 chain
        segments = parse(full_text)

        # 检查是否需要处理
        has_elements = any(
            isinstance(s, (CodeBlock, Table, InlineExpr, BlockExpr, Divider))
            for s in segments
        )
        if not has_elements:
            return

        cfg = load_config(self.config)
        built = build_chain(segments, cfg, data_dir)

        # 汇总日志（0 则静默）
        image_count = sum(1 for item in built if item["type"] == "Image")
        file_count = sum(1 for item in built if item["type"] == "File")
        total = image_count + file_count
        if total > 0:
            parts: list[str] = []
            if cfg.code_mode != "不处理":
                parts.append(f"代码块({cfg.code_mode})")
            if cfg.table_mode != "不处理":
                parts.append(f"表格({cfg.table_mode})")
            if cfg.expr_mode != "不处理":
                parts.append(f"表达式({cfg.expr_mode})")
            logger.info("已渲染 %d 项 (%s)", total, " ".join(parts))

        front_segments, last_segment = split_chain(built)

        # 前置段逐段发送
        for seg_group in front_segments:
            comps = self._to_comp_list(seg_group)
            if comps:
                await event.send(MessageChain(comps))

        # 末段放回 chain 交给 RespondStage
        result.chain = self._to_comp_list(last_segment)

    def _to_comp_list(self, seg_group: list[dict[str, Any]]) -> list:
        """将内部 chain 结构转换为 AstrBot Component 列表。

        Args:
            seg_group: build_chain 输出的消息段。

        Returns:
            AstrBot Component 对象列表。
        """
        comps: list[Any] = []
        for item in seg_group:
            if item["type"] == "Plain":
                comps.append(Plain(item["text"]))
            elif item["type"] == "Image":
                comps.append(Image.fromFileSystem(item["path"]))
            elif item["type"] == "File":
                comps.append(AstrFile(
                    name=os.path.basename(item["path"]),
                    file=item["path"],
                ))
        return comps

    async def terminate(self):
        """插件销毁。"""
        await _stop_cleaner()
        logger.info("Markdown 渲染插件已卸载")
