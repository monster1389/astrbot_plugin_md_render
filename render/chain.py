"""消息链组装。

build_chain: 根据配置模式将解析结果+渲染产物组装为统一的消息链。
"""
from __future__ import annotations

import logging
import os
from typing import Any

from astrbot.api.message_components import Plain, Image, File as AstrFile

from render.code import render_code
from render.expr import render_block_expr, render_inline_expr
from render.parser import (
    BlockExpr,
    CodeBlock,
    Divider,
    InlineExpr,
    RichCell,
    Segment,
    Table,
)
from render.table import render_table
from render.utils import RenderConfig, build_temp_path

logger = logging.getLogger(__name__)


def build_chain(
    segments: list[Any],
    cfg: RenderConfig,
    data_dir: str,
) -> list[Plain | Image | AstrFile]:
    """将解析后的 Segment 列表转换为 AstrBot Component 列表。

    Args:
        segments: parser.parse() 输出的 Segment 列表。
        cfg: 渲染配置。
        data_dir: 插件数据目录路径，用于存放渲染产物。

    Returns:
        AstrBot Component 对象列表。
    """
    chain: list[Plain | Image | AstrFile] = []

    for seg in segments:
        if isinstance(seg, CodeBlock):
            _dispatch(
                chain,
                raw_text=f"```{seg.lang}\n{seg.code}\n```",
                mode=cfg.code_mode,
                data_dir=data_dir,
                prefix="code",
                render_fn=lambda: render_code(seg, cfg, data_dir),
                has_file_mode=True,
            )
        elif isinstance(seg, Table):
            _dispatch(
                chain,
                raw_text=_table_to_text(seg),
                mode=cfg.table_mode,
                data_dir=data_dir,
                prefix="table",
                render_fn=lambda: render_table(seg, cfg, data_dir),
                has_file_mode=True,
            )
        elif isinstance(seg, InlineExpr):
            _dispatch(
                chain,
                raw_text=f"${seg.expr}$",
                mode=cfg.expr_mode,
                data_dir=data_dir,
                prefix="expr",
                render_fn=lambda: render_inline_expr(seg, cfg, data_dir),
                has_file_mode=False,
            )
        elif isinstance(seg, BlockExpr):
            _dispatch(
                chain,
                raw_text=f"$$\n{seg.expr}\n$$",
                mode=cfg.expr_mode,
                data_dir=data_dir,
                prefix="expr",
                render_fn=lambda: render_block_expr(seg, cfg, data_dir),
                has_file_mode=False,
            )
        elif isinstance(seg, Divider):
            if cfg.divider_mode == "切分":
                pass  # splitter plugin integration
        elif isinstance(seg, Segment):
            chain.append(Plain(seg.text))

    return chain


def _dispatch(
    chain: list,
    raw_text: str,
    mode: str,
    data_dir: str,
    prefix: str,
    render_fn,
    has_file_mode: bool,
) -> None:
    """统一分发：按 mode 决定渲染/文件/原文策略。

    Args:
        chain: 目标消息链列表。
        raw_text: 原始 markdown 文本（用于不处理/保留原文/回退）。
        mode: 配置渲染模式。
        data_dir: 插件数据目录路径。
        prefix: 产物文件名前缀（code/table/expr）。
        render_fn: 无参渲染函数，返回 png_path 或 (png_path, md_path)。
        has_file_mode: 是否支持"仅md文件"/"渲染且md文件"模式。
    """
    if mode == "不处理":
        chain.append(Plain(raw_text))
        return

    if has_file_mode and mode == "仅md文件":
        md_path = build_temp_path(data_dir, prefix, ".md")
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(raw_text)
        chain.append(AstrFile(name=os.path.basename(md_path), file=md_path))
        return

    try:
        result = render_fn()
    except Exception:
        logger.warning("%s 渲染失败，已回退为原文", prefix, exc_info=True)
        chain.append(Plain(raw_text))
        return

    png_path, md_path = result if isinstance(result, tuple) else (result, None)

    if "保留原文" in mode:
        chain.append(Plain(raw_text))
    chain.append(Image.fromFileSystem(png_path))

    if mode == "渲染且md文件":
        if md_path is None:
            md_path = build_temp_path(data_dir, prefix, ".md")
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(raw_text)
        chain.append(AstrFile(name=os.path.basename(md_path), file=md_path))


def _table_to_text(table: Table) -> str:
    """将 Table 还原为原始 markdown 文本。

    Args:
        table: Table 实例。

    Returns:
        markdown 表格文本。
    """
    def _cell_text(cell: RichCell) -> str:
        parts: list[str] = []
        for span in cell.spans:
            s = span.text
            if span.code:
                s = f"`{s}`"
            if span.strike:
                s = f"~~{s}~~"
            if span.italic:
                s = f"*{s}*"
            if span.bold:
                s = f"**{s}**"
            if span.link_url:
                s = f"[{s}]({span.link_url})"
            parts.append(s)
        return "".join(parts)

    lines: list[str] = []
    lines.append("| " + " | ".join(_cell_text(h) for h in table.headers) + " |")
    lines.append("|" + "|".join(["---" for _ in table.headers]) + "|")
    for row in table.rows:
        lines.append("| " + " | ".join(_cell_text(c) for c in row) + " |")
    return "\n".join(lines)
