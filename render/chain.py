"""消息链组装。

plan_chain: 解析、分组并提交全部渲染任务，返回按序产出的流水线。
build_chain: 异步并发渲染，按配置模式组装单组消息链。
"""
from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import Any

from astrbot.api.message_components import File as AstrFile
from astrbot.api.message_components import Image, Plain
from render.code_render import render_code
from render.config import CleanConfig, RenderConfig, SegmentConfig
from render.expr_render import render_expr
from render.html_render import render_html
from render.md_cleaner import clean_markdown
from render.mermaid_render import render_mermaid
from render.parser import (
    BlockExpr,
    CodeBlock,
    Divider,
    HtmlDoc,
    InlineExpr,
    MermaidBlock,
    Segment,
    codeblock_to_markdown,
    codeblock_to_plain,
    expr_to_markdown,
    expr_to_plain,
    parse,
)
from render.table_domain import Table, table_to_markdown, table_to_plain
from render.table_render import render_table
from render.tempstore import build_temp_path

logger = logging.getLogger(__name__)

# 单个元素的渲染保险丝（秒）：只兜住渲染器卡死，正常路径不会触发——
# mermaid.ink 自己 5s×2 次 + 0.5s 重试延迟 ≈ 10.5s 就会放弃。
_RENDER_TIMEOUT = 15.0


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
    render: Callable[[Any], bytes] | None = None
    prefix: str | None = None
    supports_file: bool = False
    mode_key: str | None = None


_ELEMENT_SPECS: dict[type, ElementSpec] = {
    CodeBlock: ElementSpec(
        text=lambda seg, cc: codeblock_to_plain(seg) if (cc and cc.code) else codeblock_to_markdown(seg),
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
    HtmlDoc: ElementSpec(
        text=lambda seg, cc: codeblock_to_plain(seg) if (cc and cc.code) else codeblock_to_markdown(seg),
        render=render_html,
        prefix="html",
        mode_key="html_mode",
    ),
    MermaidBlock: ElementSpec(
        text=lambda seg, cc: codeblock_to_plain(seg) if (cc and cc.code) else codeblock_to_markdown(seg),
        render=render_mermaid,
        prefix="mermaid",
        supports_file=True,
        mode_key="mermaid_mode",
    ),
    InlineExpr: ElementSpec(
        text=lambda seg, cc: expr_to_plain(seg) if (cc and cc.expr) else expr_to_markdown(seg),
        render=render_expr,
        prefix="expr",
        mode_key="expr_mode",
    ),
    BlockExpr: ElementSpec(
        text=lambda seg, cc: expr_to_plain(seg) if (cc and cc.expr) else expr_to_markdown(seg),
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
) -> Callable[[Any], bytes]:
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

    # 渲染失败：能出文件的模式仍写 .md（文件本就是渲染不出来时的保底形态），否则回退原文
    if recipe.image and result is None:
        if recipe.file and spec.supports_file and spec.prefix:
            _append_file(chain, spec.text(seg, None), spec.prefix, data_dir)
        else:
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

    并发提交渲染任务到线程池，全部完成后按原顺序组装；每个元素带渲染超时。

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
            coros.append(asyncio.wait_for(
                asyncio.to_thread(_renderer_for(type(seg), spec, renderers), seg),
                _RENDER_TIMEOUT,
            ))

    # 并发执行
    if coros:
        results_list = await asyncio.gather(*coros, return_exceptions=True)
    else:
        results_list = []

    # 分离成功 / 失败
    results: dict[int, object] = {}
    for i, result in zip(indices, results_list):
        if isinstance(result, BaseException):
            logger.warning("渲染失败，改用降级产物", exc_info=result)
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


# 块级元素：代码块、HTML 文档、Mermaid 图表、表格、块级表达式。自身独立成组，
# 前后的纯文本与行内表达式各并成一组（keep_whole）。
_BLOCK_TYPES: tuple[type, ...] = (CodeBlock, Table, BlockExpr, HtmlDoc, MermaidBlock)


@dataclass(frozen=True)
class SegmentGroup:
    """一次分组的片段列表与其发送方式。

    Attributes:
        segments: 该组的 segment 列表。
        keep_whole: True 表示整组合并成一条消息（纯文本段 + 行内表达式）；
            False 表示含块级元素，逐组件拆条保持阅读顺序。
    """
    segments: list[Any]
    keep_whole: bool


def group_segments(
    segments: list[Any],
    seg_cfg: SegmentConfig,
) -> list[SegmentGroup]:
    """按切分配置将 segments 分组为多条独立消息。

    切分点有三类：
      - 分隔线（分隔线=切分）：`---` 作为断点，本身不进入消息。
      - 空行（连续换行=切分）：相邻纯文本段之间断开。
      - 块级元素（代码块/表格/块级表达式/HTML 文档/Mermaid 图表）：自身独立一组，前后的纯文本
        与行内表达式各并成一组。

    keep_whole=True 的组（纯文本段 + 行内表达式）整组合并成一条消息，
    行内表达式图片与相邻文字同条展示；keep_whole=False 的块级组逐组件
    拆条，保持阅读顺序。

    Args:
        segments: parser.parse() 输出的片段列表。
        seg_cfg: 分段配置。

    Returns:
        消息分组列表，每组带 keep_whole 标记。
    """
    groups: list[SegmentGroup] = []
    current: list[Any] = []
    for seg in segments:
        if isinstance(seg, Divider):
            if seg_cfg.divider_mode == "切分":
                if current:
                    groups.append(SegmentGroup(current, keep_whole=True))
                    current = []
                continue
            current.append(seg)
            continue
        if isinstance(seg, _BLOCK_TYPES):
            if current:
                groups.append(SegmentGroup(current, keep_whole=True))
                current = []
            groups.append(SegmentGroup([seg], keep_whole=False))
            continue
        if (
            seg_cfg.blank_line_mode == "切分"
            and current
            and isinstance(current[-1], Segment)
            and isinstance(seg, Segment)
        ):
            groups.append(SegmentGroup(current, keep_whole=True))
            current = []
        current.append(seg)
    if current:
        groups.append(SegmentGroup(current, keep_whole=True))
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


@dataclass(frozen=True)
class Message:
    """流水线产出的一条待发送消息。

    Attributes:
        chain: 该条消息的组件列表。
        is_tail: 是否末条——末条不由 deliver 发送，留作 result.chain。
    """
    chain: list[Any]
    is_tail: bool


@dataclass
class Pipeline:
    """渲染流水线：渲染任务已全部提交，按序逐条产出待发送消息。

    严格保序：某组渲染慢时，它后面的消息一律等它，不越过。

    Attributes:
        groups: 分组列表，与 tasks 一一对应。
        tasks: 各组的 build_chain 任务，plan_chain 中已全部提交。
        non_plain: 原链非 Plain 组件，前置到首条产出的消息。
        image_count: 已产出的图片数。
        file_count: 已产出的文件数。
    """

    groups: list[SegmentGroup]
    tasks: list[asyncio.Task]
    non_plain: list[Any]
    image_count: int = 0
    file_count: int = 0

    def __aiter__(self) -> AsyncIterator[Message]:
        """按序产出消息。"""
        return self._iterate()

    async def _iterate(self) -> AsyncIterator[Message]:
        """逐组等待渲染结果，组装为一条或多条消息后产出。

        末条由 is_tail 标记：调用方不必向前多取一条就能知道该留尾。

        Yields:
            带留尾标记的消息。
        """
        prefixed = False
        last_group = len(self.groups) - 1
        for index, (group, task) in enumerate(zip(self.groups, self.tasks)):
            built = await task
            messages = [built] if group.keep_whole else split_messages(built)
            if not prefixed:
                if self.non_plain:
                    messages[0] = self.non_plain + messages[0]
                prefixed = True
            for position, chain in enumerate(messages):
                self._count(chain)
                is_tail = index == last_group and position == len(messages) - 1
                yield Message(chain, is_tail)

    def _count(self, chain: list[Any]) -> None:
        """累计产物数量，供汇总日志使用。

        Args:
            chain: 一条消息的组件列表。
        """
        for comp in chain:
            if isinstance(comp, AstrFile):
                self.file_count += 1
            elif isinstance(comp, Image):
                self.image_count += 1

    def cancel(self) -> None:
        """取消尚未完成的渲染任务。"""
        for task in self.tasks:
            task.cancel()


async def plan_chain(
    chain: list[Any],
    cfg: RenderConfig,
    seg_cfg: SegmentConfig,
    clean_cfg: CleanConfig | None,
    data_dir: str,
    renderers: dict[type, Callable] | None = None,
) -> Pipeline | None:
    """解析、分组并提交全部渲染任务，返回可逐条产出的流水线。

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
        待消费的渲染流水线；无事可做时返回 None。
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

    # 立刻提交全部渲染任务：并发度与整批渲染时一致，慢的组不挡住别的组开工
    tasks = [
        asyncio.create_task(build_chain(g.segments, cfg, clean_cfg, data_dir, renderers))
        for g in groups
    ]
    return Pipeline(groups, tasks, non_plain)
