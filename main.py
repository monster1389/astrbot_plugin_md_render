"""AstrBot Markdown 渲染插件。

在 OnDecoratingResultEvent 阶段拦截消息链，将 markdown 代码块、表格、
数学表达式渲染为图片后替换到消息链中。
"""
from __future__ import annotations

import asyncio
import io
import os
import shutil
import sys
import tempfile
import urllib.request
from typing import Any

import py7zr

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, MessageChain, filter
from astrbot.api.message_components import Image, File as AstrFile
from astrbot.api.star import Context, Star, StarTools, register

_plugin_dir = os.path.dirname(os.path.abspath(__file__))
if _plugin_dir not in sys.path:
    sys.path.insert(0, _plugin_dir)

from render.parser import parse, CodeBlock, Table, InlineExpr, BlockExpr, Divider  # noqa: E402
from render.chain import build_chain, group_segments, merge_chain, _is_plain  # noqa: E402
from render.cleaner import start as _start_cleaner, stop as _stop_cleaner  # noqa: E402
from render.utils import load_config  # noqa: E402

_FONT_URLS = [
    "https://github.com/be5invis/Sarasa-Gothic/releases/download/v1.0.27/SarasaMonoSC-TTF-1.0.27.7z",
]


def _download_sarasa_font(fonts_dir: str) -> bool:
    """尝试下载更纱等宽黑体，成功返回 True，失败返回 False。

    用 py7zr 从 7z 压缩包中提取 SarasaMonoSC-Regular.ttf。

    Args:
        fonts_dir: 字体存放目录路径。
    """
    for url in _FONT_URLS:
        try:
            logger.info("正在下载更纱字体: %s", url)
            req = urllib.request.Request(url, headers={"User-Agent": "astrbot-md-render"})
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = resp.read()
            with py7zr.SevenZipFile(io.BytesIO(data)) as archive:
                with tempfile.TemporaryDirectory() as tmpdir:
                    archive.extract(path=tmpdir, targets=["SarasaMonoSC-Regular.ttf"])
                    src = os.path.join(tmpdir, "SarasaMonoSC-Regular.ttf")
                    if os.path.exists(src):
                        dst = os.path.join(fonts_dir, "SarasaMonoSC-Regular.ttf")
                        shutil.move(src, dst)
                    else:
                        raise FileNotFoundError("SarasaMonoSC-Regular.ttf 未在压缩包中找到")
            logger.info("更纱字体下载成功，已保存至 %s", os.path.join(fonts_dir, "SarasaMonoSC-Regular.ttf"))
            return True
        except Exception:
            logger.warning("从 %s 下载更纱字体失败", url, exc_info=True)
    return False


@register(
    "astrbot_plugin_md_render",
    "monster1389",
    "Markdown 渲染插件",
    "1.1.0",
)
class MdRenderPlugin(Star):
    """将 QQ 消息中的 markdown 代码块、表格、数学表达式渲染为图片。

    Attributes:
        config: AstrBot 原始配置字典。
    """

    def __init__(self, context: Context, config: AstrBotConfig | None = None):
        super().__init__(context)
        self.config: dict[str, Any] = config or {}
        self.cfg = None
        self.clean_cfg = None

    async def initialize(self):
        """插件初始化。"""
        data_dir = StarTools.get_data_dir("astrbot_plugin_md_render")
        temp_dir = os.path.join(data_dir, "temp")
        os.makedirs(temp_dir, exist_ok=True)
        fonts_dir = os.path.join(data_dir, "fonts")
        os.makedirs(fonts_dir, exist_ok=True)
        font_path = os.path.join(fonts_dir, "SarasaMonoSC-Regular.ttf")
        if not os.path.exists(font_path):
            asyncio.get_running_loop().run_in_executor(None, _download_sarasa_font, fonts_dir)
        self.cfg, self.clean_cfg = load_config(self.config)
        _start_cleaner(str(data_dir), self.cfg.temp_ttl)
        logger.info("Markdown 渲染插件已启动")

    @filter.on_decorating_result(priority=1000)
    async def on_decorating_result(self, event: AstrMessageEvent):
        """装饰结果事件：解析 Plain 文本，渲染 markdown 元素并按切分配置分条发送。

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
            if _is_plain(comp):
                text_parts.append(comp.text or "")

        full_text = "\n".join(text_parts)
        if not full_text.strip():
            return

        # 解析 → 按切分配置分组
        segments = parse(full_text, split_blank_lines=(self.cfg.blank_line_mode == "切分"))

        has_elements = any(
            isinstance(s, (CodeBlock, Table, InlineExpr, BlockExpr, Divider))
            for s in segments
        )
        needs_cleaning = self.clean_cfg is not None and any(vars(self.clean_cfg).values())
        needs_split = (
            (self.cfg.blank_line_mode == "切分" or self.cfg.divider_mode == "切分")
            and len(segments) > 1
        )
        if not has_elements and not needs_cleaning and not needs_split:
            return

        groups = group_segments(segments, self.cfg)
        non_plain = [c for c in chain if not _is_plain(c)]

        if len(groups) == 1:
            built = await build_chain(segments, self.cfg, self.clean_cfg, data_dir)
            self._log_render_summary([built])
            result.chain = merge_chain(chain, built)
            return

        built_groups = list(await asyncio.gather(
            *(build_chain(g, self.cfg, self.clean_cfg, data_dir) for g in groups)
        ))
        self._log_render_summary(built_groups)

        if non_plain:
            built_groups[0] = non_plain + built_groups[0]

        for group_chain in built_groups[:-1]:
            if self._has_content(group_chain):
                await self._send_chain(event, group_chain)
                await asyncio.sleep(0.2)

        result.chain = built_groups[-1]

    async def _send_chain(self, event: AstrMessageEvent, comps: list) -> None:
        """将组件列表作为一条独立消息发送。

        Args:
            event: AstrBot 消息事件。
            comps: 组件列表。
        """
        mc = MessageChain()
        mc.chain = comps
        await self.context.send_message(event.unified_msg_origin, mc)

    def _log_render_summary(self, chains: list[list]) -> None:
        """汇总渲染产物数量日志，0 则静默。

        Args:
            chains: 各消息的组件列表。
        """
        image_count = sum(1 for c in chains for item in c if isinstance(item, Image))
        file_count = sum(1 for c in chains for item in c if isinstance(item, AstrFile))
        total = image_count + file_count
        if total > 0:
            parts: list[str] = []
            if self.cfg.code_mode != "不处理":
                parts.append(f"代码块({self.cfg.code_mode})")
            if self.cfg.table_mode != "不处理":
                parts.append(f"表格({self.cfg.table_mode})")
            if self.cfg.expr_mode != "不处理":
                parts.append(f"表达式({self.cfg.expr_mode})")
            logger.info("已渲染 %d 项 (%s)", total, " ".join(parts))

    @staticmethod
    def _has_content(comps: list) -> bool:
        """判断组件列表是否含实质内容（有非 Plain，或 Plain 文本非空白）。"""
        for c in comps:
            if not _is_plain(c):
                return True
            if (c.text or "").strip():
                return True
        return False

    async def terminate(self):
        """插件销毁。"""
        await _stop_cleaner()
        logger.info("Markdown 渲染插件已卸载")
