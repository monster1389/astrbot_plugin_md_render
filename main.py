"""AstrBot Markdown 渲染插件。

在 OnDecoratingResultEvent 阶段拦截消息链，将 markdown 代码块、表格、
数学表达式渲染为图片后替换到消息链中。
"""
from __future__ import annotations

import os
import sys
from typing import Any

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import (
    AstrMessageEvent,
    MessageChain,
    ResultContentType,
    filter,
)
from astrbot.api.star import Context, Star, StarTools

_plugin_dir = os.path.dirname(os.path.abspath(__file__))
if _plugin_dir not in sys.path:
    sys.path.insert(0, _plugin_dir)

from render.chain import Pipeline, plan_chain  # noqa: E402
from render.config import load_config  # noqa: E402
from render.deliver import deliver  # noqa: E402
from render.font import init_font  # noqa: E402
from render.html_render import init_html  # noqa: E402
from render.tempstore import start as _start_cleaner  # noqa: E402
from render.tempstore import stop as _stop_cleaner  # noqa: E402


class MdRenderPlugin(Star):
    """将 QQ 消息中的 markdown 代码块、HTML 文档、Mermaid 图表、表格、数学表达式渲染为图片。

    Attributes:
        config: AstrBot 原始配置字典。
    """

    def __init__(self, context: Context, config: AstrBotConfig | None = None):
        super().__init__(context)
        self.config: dict[str, Any] = config or {}
        self.cfg = None
        self.seg_cfg = None
        self.clean_cfg = None

    async def initialize(self):
        """插件初始化。"""
        data_dir = StarTools.get_data_dir("astrbot_plugin_md_render")
        temp_dir = os.path.join(data_dir, "temp")
        os.makedirs(temp_dir, exist_ok=True)
        init_font(str(data_dir))
        self.cfg, self.seg_cfg, self.clean_cfg = load_config(self.config)
        init_html(self.cfg.html_width)
        _start_cleaner(str(data_dir), self.cfg.temp_ttl)
        logger.info("Markdown 渲染插件已启动")

    @filter.on_decorating_result(priority=1000)
    async def on_decorating_result(self, event: AstrMessageEvent):
        """装饰结果事件：解析 Plain 文本，渲染 markdown 元素并按切分配置分条发送。

        Args:
            event: AstrBot 消息事件。
        """
        result = event.get_result()
        if result.result_content_type is ResultContentType.STREAMING_FINISH:
            # 流式阶段已把原文发给用户，RespondStage 不会再发这条结果。
            # 实时分段回复下继续渲染还会经 deliver 重复发送一遍内容。
            logger.debug("跳过流式结束通知")
            return
        if self.cfg.model_only and not result.is_model_result():
            logger.debug("跳过非模型回复（仅处理模型回复已开启）")
            return
        data_dir = StarTools.get_data_dir("astrbot_plugin_md_render")

        pipeline = await plan_chain(
            result.chain, self.cfg, self.seg_cfg, self.clean_cfg, data_dir
        )
        if pipeline is None:
            return

        async def _send(comps: list) -> None:
            mc = MessageChain()
            mc.chain = comps
            await self.context.send_message(event.unified_msg_origin, mc)

        try:
            result.chain = await deliver(_send, pipeline, self.seg_cfg)
        finally:
            pipeline.cancel()

        self._log_render_summary(pipeline)

    def _log_render_summary(self, pipeline: Pipeline) -> None:
        """汇总渲染产物数量日志，0 则静默。

        Args:
            pipeline: 已消费完的渲染流水线。
        """
        total = pipeline.image_count + pipeline.file_count
        if total > 0:
            parts: list[str] = []
            if self.cfg.code_mode != "不处理":
                parts.append(f"代码块({self.cfg.code_mode})")
            if self.cfg.table_mode != "不处理":
                parts.append(f"表格({self.cfg.table_mode})")
            if self.cfg.expr_mode != "不处理":
                parts.append(f"表达式({self.cfg.expr_mode})")
            if self.cfg.html_mode != "不处理":
                parts.append(f"HTML({self.cfg.html_mode})")
            if self.cfg.mermaid_mode != "不处理":
                parts.append(f"Mermaid({self.cfg.mermaid_mode})")
            logger.info("已渲染 %d 项 (%s)", total, " ".join(parts))

    async def terminate(self):
        """插件销毁。"""
        await _stop_cleaner()
        logger.info("Markdown 渲染插件已卸载")
