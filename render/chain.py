"""消息链组装。

build_chain: 异步并发渲染，按配置模式组装消息链。
"""
from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from typing import Any, Callable

from astrbot.api.message_components import Plain, Image, File as AstrFile

from render.code import render_code
from render.expr import render_expr
from render.parser import (
    BlockExpr,
    CodeBlock,
    Divider,
    InlineExpr,
    RichCell,
    Segment,
    Table,
    parse,
)
from render.table import render_table
from render.clean.md_cleaner import clean_markdown, clean_code_block, clean_table, clean_expr
from render.utils import RenderConfig, CleanConfig, build_temp_path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ModeSpec:
    """模式 → 产物配方：text/image/file 三个插槽是否填充。

    Attributes:
        text: 是否产出原文 Plain。
        image: 是否产出渲染 PNG。
        file: 是否产出 .md 文件。
    """
    text: bool
    image: bool
    file: bool


# 联合能力表：模式字符串 → 产物配方。配置边界（_conf_schema.json）保持中文字符串，
# 此表即这些字符串唯一的解释处。各元素类型的可达模式是其子集（表达式无 md 文件模式）。
_MODE_SPECS: dict[str, ModeSpec] = {
    "不处理":           ModeSpec(text=True,  image=False, file=False),
    "渲染图像":         ModeSpec(text=False, image=True,  file=False),
    "渲染且保留原文":     ModeSpec(text=True,  image=True,  file=False),
    "渲染且md文件":      ModeSpec(text=False, image=True,  file=True),
    "仅md文件":         ModeSpec(text=False, image=False, file=True),
}


@dataclass(frozen=True)
class ElementSpec:
    """元素类型的渲染能力描述。

    Attributes:
        render: 渲染函数，返回 PNG bytes。
        to_text: 将 segment 还原为原始 markdown 文本。
        clean_key: 清洗配置字段与清洗函数键（code/table/expr）。
        prefix: 产物文件名前缀。
        supports_file: 是否支持产出 .md 文件。
    """
    render: Callable[[Any, RenderConfig, str], bytes]
    to_text: Callable[[Any], str]
    clean_key: str
    prefix: str
    supports_file: bool


_ELEMENT_SPECS: dict[type, ElementSpec] = {
    CodeBlock: ElementSpec(
        render=lambda seg, dd: render_code(seg, dd),
        to_text=lambda s: f"```{s.lang}\n{s.code}\n```",
        clean_key="code",
        prefix="code",
        supports_file=True,
    ),
    Table: ElementSpec(
        render=lambda seg, dd: render_table(seg, dd),
        to_text=lambda s: _table_to_text(s),
        clean_key="table",
        prefix="table",
        supports_file=True,
    ),
    InlineExpr: ElementSpec(
        render=lambda seg, dd: render_expr(seg),
        to_text=lambda s: f"${s.expr}$",
        clean_key="expr",
        prefix="expr",
        supports_file=False,
    ),
    BlockExpr: ElementSpec(
        render=lambda seg, dd: render_expr(seg),
        to_text=lambda s: f"$$\n{s.expr}\n$$",
        clean_key="expr",
        prefix="expr",
        supports_file=False,
    ),
}


def _mode_for(seg: Any, cfg: RenderConfig) -> str:
    """读取 segment 对应的渲染模式。"""
    if isinstance(seg, CodeBlock):
        return cfg.code_mode
    if isinstance(seg, Table):
        return cfg.table_mode
    return cfg.expr_mode  # InlineExpr / BlockExpr


_CLEAN_FLAGS: dict[str, Callable[[CleanConfig], bool]] = {
    "code": lambda cc: cc.code,
    "table": lambda cc: cc.table,
    "expr": lambda cc: cc.expr,
}
_CLEAN_FNS: dict[str, Callable[[str], str]] = {
    "code": lambda t: clean_code_block(t),
    "table": lambda t: clean_table(t),
    "expr": lambda t: clean_expr(t),
}


def _maybe_clean(raw_text: str, clean_cfg: CleanConfig | None, key: str) -> str:
    """按元素类型清洗 markdown 标记，未启用或 clean_cfg 为 None 时原样返回。

    Args:
        raw_text: 原始 markdown 文本。
        clean_cfg: 清洗配置，为 None 时不清洗。
        key: 元素类型键（code/table/expr）。

    Returns:
        清洗后或原始文本。
    """
    if clean_cfg is None or not _CLEAN_FLAGS[key](clean_cfg):
        return raw_text
    return _CLEAN_FNS[key](raw_text)


def _append_image(chain: list, png_bytes: bytes, prefix: str, cfg: RenderConfig, data_dir: str) -> None:
    """按 temp_ttl 将 PNG 以 fromBytes 或落盘文件形式加入消息链。

    Args:
        chain: 目标消息链列表。
        png_bytes: 渲染出的 PNG 字节。
        prefix: 产物文件名前缀。
        cfg: 渲染配置。
        data_dir: 插件数据目录路径。
    """
    if cfg.temp_ttl == 0:
        chain.append(Image.fromBytes(png_bytes))
    else:
        png_path = build_temp_path(data_dir, prefix, ".png")
        with open(png_path, "wb") as f:
            f.write(png_bytes)
        chain.append(Image.fromFileSystem(png_path))


def _append_file(chain: list, text: str, prefix: str, data_dir: str) -> None:
    """将 markdown 文本写入 .md 文件并加入消息链。

    Args:
        chain: 目标消息链列表。
        text: markdown 原始文本。
        prefix: 产物文件名前缀。
        data_dir: 插件数据目录路径。
    """
    md_path = build_temp_path(data_dir, prefix, ".md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(text)
    chain.append(AstrFile(name=os.path.basename(md_path), file=md_path))


def _dispatch(
    chain: list,
    seg: Any,
    result: object,
    cfg: RenderConfig,
    clean_cfg: CleanConfig | None,
    data_dir: str,
) -> None:
    """按 (元素类型, 模式) 配方组装组件到消息链。

    Args:
        chain: 目标消息链列表。
        seg: 元素 segment。
        result: 渲染结果 — bytes 或 None（失败）。
        cfg: 渲染配置。
        clean_cfg: 清洗配置，为 None 时不清洗。
        data_dir: 插件数据目录路径。
    """
    spec = _ELEMENT_SPECS[type(seg)]
    recipe = _MODE_SPECS[_mode_for(seg, cfg)]
    raw_text = spec.to_text(seg)

    # 渲染失败统一回退为原文
    if recipe.image and result is None:
        chain.append(Plain(_maybe_clean(raw_text, clean_cfg, spec.clean_key)))
        return

    if recipe.text:
        chain.append(Plain(_maybe_clean(raw_text, clean_cfg, spec.clean_key)))
    if recipe.image:
        _append_image(chain, result, spec.prefix, cfg, data_dir)
    if recipe.file and spec.supports_file:
        _append_file(chain, raw_text, spec.prefix, data_dir)


async def build_chain(
    segments: list[Any],
    cfg: RenderConfig,
    clean_cfg: CleanConfig | None,
    data_dir: str,
) -> list[Plain | Image | AstrFile]:
    """将解析后的 Segment 列表转换为 AstrBot Component 列表。

    并发提交渲染任务到线程池，全部完成后按原顺序组装。

    Args:
        segments: parser.parse() 输出的 Segment 列表。
        cfg: 渲染配置。
        clean_cfg: 清洗配置，为 None 时跳过清洗。
        data_dir: 插件数据目录路径。

    Returns:
        AstrBot Component 对象列表。
    """
    # 第一遍：收集需要渲染的 segment 索引和协程（仅配方含图片插槽的模式）
    indices: list[int] = []
    coros: list[asyncio.Future] = []
    for i, seg in enumerate(segments):
        if type(seg) not in _ELEMENT_SPECS:
            continue
        if _MODE_SPECS[_mode_for(seg, cfg)].image:
            indices.append(i)
            coros.append(asyncio.to_thread(_ELEMENT_SPECS[type(seg)].render, seg, data_dir))

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
            _dispatch(chain, seg, results[i], cfg, clean_cfg, data_dir)
        elif type(seg) in _ELEMENT_SPECS:
            _dispatch(chain, seg, None, cfg, clean_cfg, data_dir)
        elif isinstance(seg, Divider):
            if cfg.divider_mode == "不处理":
                chain.append(Plain("\n\n---\n\n"))
        elif isinstance(seg, Segment):
            text = seg.text
            if clean_cfg is not None:
                text = clean_markdown(text, clean_cfg)
            chain.append(Plain(text))

    return chain


def _is_plain(comp: Any) -> bool:
    """判断组件是否为 Plain 文本。

    Args:
        comp: AstrBot 消息链组件。

    Returns:
        True 表示该组件为 Plain 文本。
    """
    return (
        (hasattr(comp, "text") and type(comp).__name__ == "Plain")
        or (hasattr(comp, "type") and comp.type == "Plain")
    )


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


def group_segments(
    segments: list[Any],
    cfg: RenderConfig,
) -> list[list[Any]]:
    """按切分配置将 segments 分组为多条独立消息。

    切分点有两类：
      - 分隔线（分隔线=切分）：`---` 作为断点，本身不进入消息。
      - 空行（连续换行=切分）：相邻纯文本段之间断开。

    Args:
        segments: parser.parse() 输出的片段列表。
        cfg: 渲染配置。

    Returns:
        消息分组列表，每组为一段待独立发送的片段列表。
    """
    groups: list[list[Any]] = []
    current: list[Any] = []
    for seg in segments:
        if isinstance(seg, Divider):
            if cfg.divider_mode == "切分":
                if current:
                    groups.append(current)
                    current = []
                continue
            current.append(seg)
            continue
        if (
            cfg.blank_line_mode == "切分"
            and current
            and isinstance(current[-1], Segment)
            and isinstance(seg, Segment)
        ):
            groups.append(current)
            current = []
        current.append(seg)
    if current:
        groups.append(current)
    return groups


def has_media(chain: list[Any]) -> bool:
    """判断组件列表是否含媒体（Image/File）。

    Args:
        chain: build_chain 构建的扁平组件列表。

    Returns:
        True 表示含媒体组件。
    """
    return any(not _is_plain(c) for c in chain)


def split_messages(chain: list[Any]) -> list[list[Any]]:
    """组内含媒体时逐组件拆成独立消息；纯文本组保持单条。

    拆分保持阅读顺序：代码原文、渲染图、表格原文、表格图……各自独立一条，
    相邻文本或相邻媒体不再合并。

    Args:
        chain: build_chain 构建的扁平组件列表。

    Returns:
        一条或多条消息组件列表。
    """
    if not has_media(chain):
        return [chain]
    return [[c] for c in chain]


def assemble_messages(
    built_groups: list[list[Any]],
    non_plain: list[Any],
) -> list[list[Any]]:
    """将各组的构建链拆条后拼接为待发送消息列表。

    含媒体的组逐组件拆成独立消息；原链的非 Plain 组件前置到首条消息。

    Args:
        built_groups: build_chain 对各组的结果列表。
        non_plain: 原始链中的非 Plain 组件，为空则不做前置。

    Returns:
        待发送消息列表，末条留作 result.chain。
    """
    messages = [m for built in built_groups for m in split_messages(built)]
    if non_plain:
        messages[0] = non_plain + messages[0]
    return messages


async def process_chain(
    chain: list[Any],
    cfg: RenderConfig,
    clean_cfg: CleanConfig | None,
    data_dir: str,
) -> list[list[Any]] | None:
    """完整管道：解析、渲染、清洗、切分，产出待发送消息列表。

    空链、纯空白文本、或无需任何处理（无元素、无需清洗、无需切分）
    时返回 None，调用方原样保留消息链。

    Args:
        chain: 原始消息链组件列表。
        cfg: 渲染配置。
        clean_cfg: 清洗配置，为 None 时跳过清洗。
        data_dir: 插件数据目录路径。

    Returns:
        待发送消息列表，末条留作 result.chain；无事可做时返回 None。
    """
    if not chain:
        return None

    text_parts = [c.text or "" for c in chain if _is_plain(c)]
    full_text = "\n".join(text_parts)
    if not full_text.strip():
        return None

    segments = parse(full_text, split_blank_lines=(cfg.blank_line_mode == "切分"))

    has_elements = any(
        type(s) in _ELEMENT_SPECS or isinstance(s, Divider) for s in segments
    )
    needs_cleaning = clean_cfg is not None and any(vars(clean_cfg).values())
    needs_split = (
        (cfg.blank_line_mode == "切分" or cfg.divider_mode == "切分")
        and len(segments) > 1
    )
    if not has_elements and not needs_cleaning and not needs_split:
        return None

    groups = group_segments(segments, cfg)
    non_plain = [c for c in chain if not _is_plain(c)]

    built_groups = list(await asyncio.gather(
        *(build_chain(g, cfg, clean_cfg, data_dir) for g in groups)
    ))

    return assemble_messages(built_groups, non_plain)
