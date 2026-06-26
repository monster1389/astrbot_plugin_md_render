"""消息链组装。

build_chain: 异步并发渲染，按配置模式组装消息链。
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from astrbot.api.message_components import Plain, Image, File as AstrFile

from render.code import render_code
from render.expr import render_block_expr, render_inline_expr
from render.parser import (
    BlockExpr,
    CodeBlock,
    InlineExpr,
    RichCell,
    Segment,
    Table,
)
from render.table import render_table
from render.utils import RenderConfig, build_temp_path

logger = logging.getLogger(__name__)


def _make_render_fn(seg: Any, cfg: RenderConfig, data_dir: str):
    """构造无参渲染函数，供 asyncio.to_thread 调用。

    Args:
        seg: 待渲染的 segment。
        cfg: 渲染配置。
        data_dir: 插件数据目录路径。

    Returns:
        无参可调用对象，返回 bytes 或 (bytes, str)。
    """
    if isinstance(seg, CodeBlock):
        def _fn():
            return render_code(seg, cfg, data_dir)
        return _fn
    elif isinstance(seg, Table):
        def _fn():
            return render_table(seg, cfg, data_dir)
        return _fn
    elif isinstance(seg, InlineExpr):
        def _fn():
            return render_inline_expr(seg, cfg, data_dir)
        return _fn
    elif isinstance(seg, BlockExpr):
        def _fn():
            return render_block_expr(seg, cfg, data_dir)
        return _fn
    raise ValueError(f"Unknown segment type: {type(seg)}")


def _dispatch_code(
    chain: list,
    raw_text: str,
    mode: str,
    cfg: RenderConfig,
    data_dir: str,
    result: object,
) -> None:
    """代码块分发（支持 md 文件模式）。

    Args:
        chain: 目标消息链列表。
        raw_text: 原始 markdown 文本。
        mode: 配置渲染模式。
        cfg: 渲染配置。
        data_dir: 插件数据目录路径。
        result: 渲染结果 — (bytes, str) 或 None（失败）。
    """
    if mode == "不处理":
        chain.append(Plain(raw_text))
        return
    if mode == "仅md文件":
        md_path = build_temp_path(data_dir, "code", ".md")
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(raw_text)
        chain.append(AstrFile(name=os.path.basename(md_path), file=md_path))
        return
    if result is None:
        chain.append(Plain(raw_text))
        return
    png_bytes, md_text = result if isinstance(result, tuple) else (result, None)
    if "保留原文" in mode:
        chain.append(Plain(raw_text))
    if cfg.temp_ttl == 0:
        chain.append(Image.fromBytes(png_bytes))
    else:
        png_path = build_temp_path(data_dir, "code", ".png")
        with open(png_path, "wb") as f:
            f.write(png_bytes)
        chain.append(Image.fromFileSystem(png_path))
    if mode == "渲染且md文件":
        md_path = build_temp_path(data_dir, "code", ".md")
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(md_text if md_text else raw_text)
        chain.append(AstrFile(name=os.path.basename(md_path), file=md_path))


def _dispatch_generic(
    chain: list,
    raw_text: str,
    mode: str,
    cfg: RenderConfig,
    data_dir: str,
    prefix: str,
    result: object,
    has_file_mode: bool,
) -> None:
    """表格/表达式分发。

    Args:
        chain: 目标消息链列表。
        raw_text: 原始 markdown 文本。
        mode: 配置渲染模式。
        cfg: 渲染配置。
        data_dir: 插件数据目录路径。
        prefix: 产物文件名前缀。
        result: 渲染结果 — bytes 或 None（失败）。
        has_file_mode: 是否支持 md 文件模式。
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
    if result is None:
        chain.append(Plain(raw_text))
        return
    png_bytes = result
    if "保留原文" in mode:
        chain.append(Plain(raw_text))
    if cfg.temp_ttl == 0:
        chain.append(Image.fromBytes(png_bytes))
    else:
        png_path = build_temp_path(data_dir, prefix, ".png")
        with open(png_path, "wb") as f:
            f.write(png_bytes)
        chain.append(Image.fromFileSystem(png_path))
    if has_file_mode and mode == "渲染且md文件":
        md_path = build_temp_path(data_dir, prefix, ".md")
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(raw_text)
        chain.append(AstrFile(name=os.path.basename(md_path), file=md_path))


def _dispatch_result(
    chain: list,
    seg: Any,
    result: object,
    cfg: RenderConfig,
    data_dir: str,
) -> None:
    """接收已完成（或失败）的渲染结果，按 mode 组装组件。

    Args:
        chain: 目标消息链列表。
        seg: 原始 segment。
        result: 渲染结果 — bytes / (bytes, str) / None（失败）。
        cfg: 渲染配置。
        data_dir: 插件数据目录路径。
    """
    if isinstance(seg, CodeBlock):
        raw_text = f"```{seg.lang}\n{seg.code}\n```"
        _dispatch_code(chain, raw_text, cfg.code_mode, cfg, data_dir, result)
    elif isinstance(seg, Table):
        raw_text = _table_to_text(seg)
        _dispatch_generic(chain, raw_text, cfg.table_mode, cfg, data_dir, "table", result, has_file_mode=True)
    elif isinstance(seg, InlineExpr):
        raw_text = f"${seg.expr}$"
        _dispatch_generic(chain, raw_text, cfg.expr_mode, cfg, data_dir, "expr", result, has_file_mode=False)
    elif isinstance(seg, BlockExpr):
        raw_text = f"$$\n{seg.expr}\n$$"
        _dispatch_generic(chain, raw_text, cfg.expr_mode, cfg, data_dir, "expr", result, has_file_mode=False)


async def build_chain(
    segments: list[Any],
    cfg: RenderConfig,
    data_dir: str,
) -> list[Plain | Image | AstrFile]:
    """将解析后的 Segment 列表转换为 AstrBot Component 列表。

    并发提交渲染任务到线程池，全部完成后按原顺序组装。

    Args:
        segments: parser.parse() 输出的 Segment 列表。
        cfg: 渲染配置。
        data_dir: 插件数据目录路径。

    Returns:
        AstrBot Component 对象列表。
    """
    # 第一遍：收集可渲染的 segment 索引和协程
    indices: list[int] = []
    coros: list[asyncio.Future] = []
    for i, seg in enumerate(segments):
        if isinstance(seg, (CodeBlock, Table, InlineExpr, BlockExpr)):
            fn = _make_render_fn(seg, cfg, data_dir)
            indices.append(i)
            coros.append(asyncio.to_thread(fn))

    # 并发执行
    if coros:
        results_list = await asyncio.gather(*coros, return_exceptions=True)
    else:
        results_list = []

    # 分离成功 / 失败
    results: dict[int, object] = {}
    for i, result in zip(indices, results_list):
        if isinstance(result, BaseException):
            logger.warning("渲染失败，回退为原文", exc_info=result)
            results[i] = None
        else:
            results[i] = result

    # 第二遍：按原顺序组装
    chain: list[Plain | Image | AstrFile] = []
    for i, seg in enumerate(segments):
        if i in results:
            _dispatch_result(chain, seg, results[i], cfg, data_dir)
        elif isinstance(seg, Segment):
            chain.append(Plain(seg.text))

    return chain


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
