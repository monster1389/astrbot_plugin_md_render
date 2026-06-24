"""消息链组装与自然分段。

build_chain: 根据配置模式将解析结果+渲染产物组装为统一的消息链。
split_chain: 以 Plain 为锚点自然分段，末段留给 RespondStage。
"""
from __future__ import annotations

import logging
from typing import Any

from render.code import render_code
from render.expr import render_block_expr, render_inline_expr
from render.parser import (
    BlockExpr,
    CodeBlock,
    Divider,
    InlineExpr,
    Segment,
    Table,
)
from render.table import render_table
from render.utils import RenderConfig

logger = logging.getLogger(__name__)


def build_chain(
    segments: list[Any],
    cfg: RenderConfig,
    data_dir: str,
) -> list[dict[str, Any]]:
    """将解析后的 Segment 列表转换为统一的消息链结构。

    每个元素为 dict，type 为 Plain/Image/File/divider。
    渲染产物路径写入对应字段。

    Args:
        segments: parser.parse() 输出的 Segment 列表。
        cfg: 渲染配置。
        data_dir: 插件数据目录路径，用于存放渲染产物。

    Returns:
        消息链结构列表。
    """
    chain: list[dict[str, Any]] = []

    for seg in segments:
        if isinstance(seg, CodeBlock):
            _append_code(chain, seg, cfg, data_dir)
        elif isinstance(seg, Table):
            _append_table(chain, seg, cfg, data_dir)
        elif isinstance(seg, InlineExpr):
            _append_inline_expr(chain, seg, cfg, data_dir)
        elif isinstance(seg, BlockExpr):
            _append_block_expr(chain, seg, cfg, data_dir)
        elif isinstance(seg, Divider):
            if cfg.divider_mode == "切分":
                chain.append({"type": "divider"})
        elif isinstance(seg, Segment):
            chain.append({"type": "Plain", "text": seg.text})

    return chain


def _append_code(
    chain: list[dict[str, Any]],
    seg: CodeBlock,
    cfg: RenderConfig,
    data_dir: str,
) -> None:
    """按代码块处理模式将渲染结果追加到 chain。

    Args:
        chain: 目标消息链列表。
        seg: CodeBlock 实例。
        cfg: 渲染配置。
        data_dir: 插件数据目录路径。
    """
    mode = cfg.code_mode
    if mode == "不处理":
        chain.append({"type": "Plain", "text": f"```{seg.lang}\n{seg.code}\n```"})
        return

    try:
        png_path, txt_path = render_code(seg, cfg, data_dir)
    except Exception:
        logger.warning(
            "代码块渲染失败，已回退为原文: %s", seg.lang,
            exc_info=True,
        )
        chain.append({"type": "Plain", "text": f"```{seg.lang}\n{seg.code}\n```"})
        return

    if mode == "渲染且保留原文":
        chain.append({"type": "Plain", "text": f"```{seg.lang}\n{seg.code}\n```"})
    chain.append({"type": "Image", "path": png_path})
    if mode == "渲染且txt":
        chain.append({"type": "File", "path": txt_path})


def _append_table(
    chain: list[dict[str, Any]],
    seg: Table,
    cfg: RenderConfig,
    data_dir: str,
) -> None:
    """按表格处理模式将渲染结果追加到 chain。

    Args:
        chain: 目标消息链列表。
        seg: Table 实例。
        cfg: 渲染配置。
        data_dir: 插件数据目录路径。
    """
    if cfg.table_mode == "不处理":
        text = _table_to_text(seg)
        chain.append({"type": "Plain", "text": text})
        return

    try:
        png_path = render_table(seg, cfg, data_dir)
    except Exception:
        logger.warning("表格渲染失败，已回退为原文", exc_info=True)
        chain.append({"type": "Plain", "text": _table_to_text(seg)})
        return

    if cfg.table_mode == "渲染且保留原文":
        chain.append({"type": "Plain", "text": _table_to_text(seg)})
    chain.append({"type": "Image", "path": png_path})


def _append_inline_expr(
    chain: list[dict[str, Any]],
    seg: InlineExpr,
    cfg: RenderConfig,
    data_dir: str,
) -> None:
    """按表达式处理模式将行内表达式渲染结果追加到 chain。

    Args:
        chain: 目标消息链列表。
        seg: InlineExpr 实例。
        cfg: 渲染配置。
        data_dir: 插件数据目录路径。
    """
    if cfg.expr_mode == "不处理":
        chain.append({"type": "Plain", "text": f"${seg.expr}$"})
        return

    try:
        png_path = render_inline_expr(seg, cfg, data_dir)
    except Exception:
        logger.warning(
            "行内表达式渲染失败，已回退为原文: %s", seg.expr[:30],
            exc_info=True,
        )
        chain.append({"type": "Plain", "text": f"${seg.expr}$"})
        return

    if cfg.expr_mode == "渲染且保留原文":
        chain.append({"type": "Plain", "text": f"${seg.expr}$"})
    chain.append({"type": "Image", "path": png_path})


def _append_block_expr(
    chain: list[dict[str, Any]],
    seg: BlockExpr,
    cfg: RenderConfig,
    data_dir: str,
) -> None:
    """按表达式处理模式将块级表达式渲染结果追加到 chain。

    Args:
        chain: 目标消息链列表。
        seg: BlockExpr 实例。
        cfg: 渲染配置。
        data_dir: 插件数据目录路径。
    """
    if cfg.expr_mode == "不处理":
        chain.append({"type": "Plain", "text": f"$$\n{seg.expr}\n$$"})
        return

    try:
        png_path = render_block_expr(seg, cfg, data_dir)
    except Exception:
        logger.warning(
            "块级表达式渲染失败，已回退为原文: %s", seg.expr[:30],
            exc_info=True,
        )
        chain.append({"type": "Plain", "text": f"$$\n{seg.expr}\n$$"})
        return

    if cfg.expr_mode == "渲染且保留原文":
        chain.append({"type": "Plain", "text": f"$$\n{seg.expr}\n$$"})
    chain.append({"type": "Image", "path": png_path})


def _table_to_text(table: Table) -> str:
    """将 Table 还原为原始 markdown 文本。

    Args:
        table: Table 实例。

    Returns:
        markdown 表格文本。
    """
    lines: list[str] = []
    lines.append("| " + " | ".join(table.headers) + " |")
    lines.append("|" + "|".join(["---" for _ in table.headers]) + "|")
    for row in table.rows:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def split_chain(
    chain: list[dict[str, Any]],
) -> tuple[list[list[dict[str, Any]]], list[dict[str, Any]]]:
    """将消息链按 Plain 锚点自然分段。

    规则:
      - 以 Plain 起始，其后紧跟的 Image/File 归入同段。
      - 遇到 divider 时断开。
      - 最后一段留在末段返回，其余段为前置发送段。

    Args:
        chain: build_chain() 输出的消息链结构列表。

    Returns:
        (front_segments, last_segment) — 前置发送段列表和末段。
    """
    if not chain:
        return [], []

    groups: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []

    for item in chain:
        if item["type"] == "divider":
            if current:
                groups.append(current)
                current = []
            continue
        if item["type"] == "Plain":
            if current:
                groups.append(current)
            current = [item]
        else:
            current.append(item)

    if current:
        groups.append(current)

    if not groups:
        return [], []

    if len(groups) == 1:
        return [], groups[0]

    return groups[:-1], groups[-1]
