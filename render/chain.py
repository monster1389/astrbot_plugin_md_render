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
    Segment,
    Table,
    parse,
    table_to_markdown,
    table_to_plain,
)
from render.table import render_table
from render.clean.md_cleaner import clean_markdown
from render.utils import RenderConfig, SegmentConfig, CleanConfig, build_temp_path

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

# 无配置模式的元素（纯文本段 / 分隔线）固定只产纯文本
_TEXT_ONLY = ModeSpec(text=True, image=False, file=False)


@dataclass(frozen=True)
class ElementSpec:
    """元素类型的渲染与文本配方。

    Attributes:
        text: 将 segment 还原为文本：清洗开启时产精简纯文本，否则产 markdown 原文。
        render: 渲染函数，返回 PNG bytes；为 None 表示不渲染（纯文本元素）。
        prefix: 产物文件名前缀。
        supports_file: 是否支持产出 .md 文件。
        mode_key: 该元素对应的 RenderConfig 模式字段名；为 None 表示固定产纯文本。
    """
    text: Callable[[Any, CleanConfig | None], str]
    render: Callable[[Any, str], bytes] | None = None
    prefix: str | None = None
    supports_file: bool = False
    mode_key: str | None = None


_ELEMENT_SPECS: dict[type, ElementSpec] = {
    CodeBlock: ElementSpec(
        text=lambda seg, cc: seg.code if (cc and cc.code) else f"```{seg.lang}\n{seg.code}\n```",
        render=render_code,
        prefix="code",
        supports_file=True,
        mode_key="code_mode",
    ),
    Table: ElementSpec(
        text=lambda seg, cc: table_to_plain(seg) if (cc and cc.table) else table_to_markdown(seg),
        render=render_table,
        prefix="table",
        supports_file=True,
        mode_key="table_mode",
    ),
    InlineExpr: ElementSpec(
        text=lambda seg, cc: seg.expr if (cc and cc.expr) else f"${seg.expr}$",
        render=render_expr,
        prefix="expr",
        mode_key="expr_mode",
    ),
    BlockExpr: ElementSpec(
        text=lambda seg, cc: seg.expr if (cc and cc.expr) else f"$$\n{seg.expr}\n$$",
        render=render_expr,
        prefix="expr",
        mode_key="expr_mode",
    ),
    Segment: ElementSpec(
        text=lambda seg, cc: clean_markdown(seg.text, cc) if cc is not None else seg.text,
    ),
    Divider: ElementSpec(
        text=lambda seg, cc: "\n\n---\n\n" if not (cc and cc.divider) else "\n\n",
    ),
}


def _renderer_for(
    seg_type: type,
    spec: ElementSpec,
    renderers: dict[type, Callable] | None,
) -> Callable[[Any, str], bytes]:
    """按覆盖层解析 segment 类型的渲染器，未覆盖回退 spec.render。

    Args:
        seg_type: segment 类型。
        spec: 元素配方。
        renderers: 渲染器覆盖层，为 None 或未含该类型时回退 spec.render。

    Returns:
        渲染函数。
    """
    if renderers and seg_type in renderers:
        return renderers[seg_type]
    return spec.render


def _recipe_for(spec: ElementSpec, cfg: RenderConfig) -> ModeSpec:
    """读取元素配方对应的产物配方。

    Args:
        spec: 元素配方。
        cfg: 渲染配置。

    Returns:
        该元素本次应填充的产物配方；无模式字段的纯文本元素固定产文本。
    """
    if spec.mode_key is None:
        return _TEXT_ONLY
    return _MODE_SPECS[getattr(cfg, spec.mode_key)]


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
    recipe = _recipe_for(spec, cfg)

    # 渲染失败统一回退为原文
    if recipe.image and result is None:
        chain.append(Plain(spec.text(seg, clean_cfg)))
        return

    if recipe.text:
        chain.append(Plain(spec.text(seg, clean_cfg)))
    if recipe.image:
        _append_image(chain, result, spec.prefix, cfg, data_dir)
    if recipe.file and spec.supports_file:
        _append_file(chain, spec.text(seg, None), spec.prefix, data_dir)


async def build_chain(
    segments: list[Any],
    cfg: RenderConfig,
    clean_cfg: CleanConfig | None,
    data_dir: str,
    renderers: dict[type, Callable] | None = None,
) -> list[Plain | Image | AstrFile]:
    """将解析后的 Segment 列表转换为 AstrBot Component 列表。

    并发提交渲染任务到线程池，全部完成后按原顺序组装。

    Args:
        segments: parser.parse() 输出的 Segment 列表。
        cfg: 渲染配置。
        clean_cfg: 清洗配置，为 None 时跳过清洗。
        data_dir: 插件数据目录路径。
        renderers: 渲染器覆盖层，为 None 或未覆盖时用元素配方默认渲染器。

    Returns:
        AstrBot Component 对象列表。
    """
    # 第一遍：收集需要渲染的 segment 索引和协程（仅配方含图片插槽的模式）
    indices: list[int] = []
    coros: list[asyncio.Future] = []
    for i, seg in enumerate(segments):
        spec = _ELEMENT_SPECS.get(type(seg))
        if spec is None or spec.render is None:
            continue
        if _recipe_for(spec, cfg).image:
            indices.append(i)
            coros.append(asyncio.to_thread(_renderer_for(type(seg), spec, renderers), seg, data_dir))

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
        _dispatch(chain, seg, results.get(i), cfg, clean_cfg, data_dir)
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


def group_segments(
    segments: list[Any],
    seg_cfg: SegmentConfig,
) -> list[list[Any]]:
    """按切分配置将 segments 分组为多条独立消息。

    切分点有两类：
      - 分隔线（分隔线=切分）：`---` 作为断点，本身不进入消息。
      - 空行（连续换行=切分）：相邻纯文本段之间断开。

    Args:
        segments: parser.parse() 输出的片段列表。
        seg_cfg: 分段配置。

    Returns:
        消息分组列表，每组为一段待独立发送的片段列表。
    """
    groups: list[list[Any]] = []
    current: list[Any] = []
    for seg in segments:
        if isinstance(seg, Divider):
            if seg_cfg.divider_mode == "切分":
                if current:
                    groups.append(current)
                    current = []
                continue
            current.append(seg)
            continue
        if (
            seg_cfg.blank_line_mode == "切分"
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
    seg_cfg: SegmentConfig,
    clean_cfg: CleanConfig | None,
    data_dir: str,
    renderers: dict[type, Callable] | None = None,
) -> list[list[Any]] | None:
    """完整管道：解析、渲染、清洗、切分，产出待发送消息列表。

    空链、纯空白文本、或无需任何处理（无元素、无需清洗、无需切分）
    时返回 None，调用方原样保留消息链。

    Args:
        chain: 原始消息链组件列表。
        cfg: 渲染配置。
        seg_cfg: 分段配置。
        clean_cfg: 清洗配置，为 None 时跳过清洗。
        data_dir: 插件数据目录路径。
        renderers: 渲染器覆盖层，透传给 build_chain。

    Returns:
        待发送消息列表，末条留作 result.chain；无事可做时返回 None。
    """
    if not chain:
        return None

    text_parts = [c.text or "" for c in chain if _is_plain(c)]
    full_text = "\n".join(text_parts)
    if not full_text.strip():
        return None

    segments = parse(full_text, split_blank_lines=(seg_cfg.blank_line_mode == "切分"))

    # 结构性元素（纯文本段以外的类型）才值得走渲染管线；
    # 纯文本段无清洗、无切分时短路，原样保留消息链。
    has_elements = any(not isinstance(s, Segment) for s in segments)
    needs_cleaning = clean_cfg is not None and any(vars(clean_cfg).values())
    needs_split = (
        (seg_cfg.blank_line_mode == "切分" or seg_cfg.divider_mode == "切分")
        and len(segments) > 1
    )
    if not has_elements and not needs_cleaning and not needs_split:
        return None

    groups = group_segments(segments, seg_cfg)
    non_plain = [c for c in chain if not _is_plain(c)]

    built_groups = list(await asyncio.gather(
        *(build_chain(g, cfg, clean_cfg, data_dir, renderers) for g in groups)
    ))

    return assemble_messages(built_groups, non_plain)
