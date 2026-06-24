"""消息链组装。

build_chain: 根据配置模式将解析结果+渲染产物组装为统一的消息链。
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
from render.utils import RenderConfig, build_temp_path

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

    if mode == "仅txt":
        md_text = f"```{seg.lang}\n{seg.code}\n```"
        txt_path = build_temp_path(data_dir, "code", ".txt")
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(md_text)
        chain.append({"type": "File", "path": txt_path})
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
    md_text = _table_to_text(seg)

    if cfg.table_mode == "不处理":
        chain.append({"type": "Plain", "text": md_text})
        return

    if cfg.table_mode == "仅md文件":
        md_path = build_temp_path(data_dir, "table", ".md")
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(md_text)
        chain.append({"type": "File", "path": md_path})
        return

    try:
        png_path = render_table(seg, cfg, data_dir)
    except Exception:
        logger.warning("表格渲染失败，已回退为原文", exc_info=True)
        chain.append({"type": "Plain", "text": md_text})
        return

    if cfg.table_mode == "渲染且保留原文":
        chain.append({"type": "Plain", "text": md_text})
    chain.append({"type": "Image", "path": png_path})
    if cfg.table_mode == "渲染且md文件":
        md_path = build_temp_path(data_dir, "table", ".md")
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(md_text)
        chain.append({"type": "File", "path": md_path})


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
