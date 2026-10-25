"""消息链组装。

plan_chain: 解析、分组并提交全部渲染任务，返回按序产出的流水线。
build_chain: 异步并发渲染，按配置模式组装单组产物。
"""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from inspect import iscoroutinefunction
from typing import Any

from astrbot.api import logger

from render.artifacts import Artifact, Message, Picture, SourceFile, Text, has_media
from render.config import CleanConfig, RenderConfig, SegmentConfig
from render.elements import ELEMENTS, Element, recipe_for, text_for, writes_file
from render.parser import Divider, Segment, parse
from render.png import quantize
from render.tempstore import build_temp_path

# 本机渲染器（typst / pytakumi）的保险丝（秒）：只兜住渲染器卡死，正常路径不会触发。
# 自己有超时预算的渲染器（mermaid，走外部 HTTP）不套它，见 Element.budgeted。
_RENDER_TIMEOUT = 15.0


def _renderer_for(
    seg_type: type,
    element: Element,
    renderers: dict[type, Callable] | None,
) -> Callable[[Any], Any]:
    """按覆盖层解析 segment 类型的渲染器，未覆盖回退 element.render。

    Args:
        seg_type: segment 类型。
        element: 元素条目。
        renderers: 渲染器覆盖层，为 None 或未含该类型时回退 element.render。

    Returns:
        渲染函数。
    """
    if renderers and seg_type in renderers:
        return renderers[seg_type]
    return element.render


async def _render_one(renderer: Callable[[Any], Any], seg: Any) -> bytes:
    """执行单个渲染器并统一压缩产物。

    协程渲染器直接 await，同步渲染器转线程池；量化是 CPU 活，同样丢线程池，
    不阻塞事件循环。所有渲染器（含远端 mermaid）都经过这里，产物归一在一处。

    Args:
        renderer: 渲染函数，同步返回 PNG 字节或协程返回 PNG 字节。
        seg: 元素 segment。

    Returns:
        量化后的 PNG 字节。
    """
    if iscoroutinefunction(renderer):
        png = await renderer(seg)
    else:
        png = await asyncio.to_thread(renderer, seg)
    return await asyncio.to_thread(quantize, png)


def _append_image(
    artifacts: list[Artifact],
    png_bytes: bytes,
    prefix: str,
    cfg: RenderConfig,
    data_dir: str,
) -> None:
    """按 temp_ttl 决定图片产物是落盘还是只带字节。

    Args:
        artifacts: 目标产物列表。
        png_bytes: 渲染出的 PNG 字节。
        prefix: 产物文件名前缀。
        cfg: 渲染配置。
        data_dir: 插件数据目录路径。
    """
    if cfg.temp_ttl == 0:
        artifacts.append(Picture(png=png_bytes))
        return
    png_path = build_temp_path(data_dir, prefix, ".png")
    with open(png_path, "wb") as f:
        f.write(png_bytes)
    artifacts.append(Picture(png=png_bytes, path=png_path))


def _append_file(
    artifacts: list[Artifact],
    text: str,
    prefix: str,
    data_dir: str,
) -> None:
    """将 markdown 文本写入 .md 文件并加入产物列表。

    Args:
        artifacts: 目标产物列表。
        text: markdown 原始文本。
        prefix: 产物文件名前缀。
        data_dir: 插件数据目录路径。
    """
    md_path = build_temp_path(data_dir, prefix, ".md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(text)
    artifacts.append(SourceFile(path=md_path))


def _dispatch(
    artifacts: list[Artifact],
    seg: Any,
    result: object,
    cfg: RenderConfig,
    clean_cfg: CleanConfig | None,
    data_dir: str,
) -> None:
    """按 (元素, 模式) 配方组装产物到列表。

    Args:
        artifacts: 目标产物列表。
        seg: 元素 segment。
        result: 渲染结果 — bytes 或 None（失败）。
        cfg: 渲染配置。
        clean_cfg: 清洗配置，为 None 时不清洗。
        data_dir: 插件数据目录路径。
    """
    element = ELEMENTS[type(seg)]
    recipe = recipe_for(element, cfg.modes)
    can_file = writes_file(element)

    # 渲染失败：没有原文可看就出 .md（文件是渲染不出来时的保底形态）
    if recipe.image and result is None:
        if not recipe.text and can_file:
            _append_file(artifacts, element.text.to_markdown(seg), element.prefix, data_dir)
        else:
            artifacts.append(Text(text=text_for(element, seg, clean_cfg)))
        return

    if recipe.text:
        artifacts.append(Text(text=text_for(element, seg, clean_cfg)))
    if recipe.image:
        _append_image(artifacts, result, element.prefix, cfg, data_dir)
    if recipe.file and can_file:
        _append_file(artifacts, element.text.to_markdown(seg), element.prefix, data_dir)


async def build_chain(
    segments: list[Any],
    cfg: RenderConfig,
    clean_cfg: CleanConfig | None,
    data_dir: str,
    renderers: dict[type, Callable] | None = None,
) -> list[Artifact]:
    """将解析后的 Segment 列表转换为产物列表。

    并发提交渲染任务到线程池，全部完成后按原顺序组装；每个元素加通用保险丝，
    自带超时预算的渲染器（budgeted）不套。

    Args:
        segments: parser.parse() 输出的 Segment 列表。
        cfg: 渲染配置。
        clean_cfg: 清洗配置，为 None 时跳过清洗。
        data_dir: 插件数据目录路径。
        renderers: 渲染器覆盖层，为 None 或未覆盖时用元素注册表里的渲染器。

    Returns:
        产物列表。
    """
    # 第一遍：收集需要渲染的 segment 索引和协程（仅配方含图片插槽的模式）
    indices: list[int] = []
    coros: list[asyncio.Future] = []
    for i, seg in enumerate(segments):
        element = ELEMENTS[type(seg)]
        if element.render is None:
            continue
        if recipe_for(element, cfg.modes).image:
            indices.append(i)
            coro = _render_one(_renderer_for(type(seg), element, renderers), seg)
            coros.append(coro if element.budgeted else asyncio.wait_for(coro, _RENDER_TIMEOUT))

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
    artifacts: list[Artifact] = []
    for i, seg in enumerate(segments):
        _dispatch(artifacts, seg, results.get(i), cfg, clean_cfg, data_dir)
    return artifacts


# 块级元素自身独立成组，前后的纯文本与行内表达式各并成一组（keep_whole）。
# 哪些元素算块级由元素注册表的 Element.block 决定。


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
      - 块级元素（代码块/表格/块级表达式/HTML 文档/Mermaid 图表，即注册表里 block=True 的元素）：
        自身独立一组，前后的纯文本与行内表达式各并成一组。

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
        if ELEMENTS[type(seg)].block:
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


def split_messages(artifacts: list[Artifact]) -> list[list[Artifact]]:
    """组内含媒体时逐组件拆成独立消息；纯文本组保持单条。

    拆分保持阅读顺序：代码原文、渲染图、表格原文、表格图……各自独立一条，
    相邻文本或相邻媒体不再合并。

    Args:
        artifacts: build_chain 构建的扁平产物列表。

    Returns:
        一条或多条消息产物列表。
    """
    if not has_media(artifacts):
        return [artifacts]
    return [[artifact] for artifact in artifacts]


@dataclass
class Pipeline:
    """渲染流水线：渲染任务已全部提交，按序逐条产出待发送消息。

    严格保序：某组渲染慢时，它后面的消息一律等它，不越过。

    Attributes:
        groups: 分组列表，与 tasks 一一对应。
        tasks: 各组的 build_chain 任务，plan_chain 中已全部提交。
        image_count: 已产出的图片数。
        file_count: 已产出的文件数。
    """

    groups: list[SegmentGroup]
    tasks: list[asyncio.Task]
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
        last_group = len(self.groups) - 1
        for index, (group, task) in enumerate(zip(self.groups, self.tasks)):
            built = await task
            messages = [built] if group.keep_whole else split_messages(built)
            for position, artifacts in enumerate(messages):
                self._count(artifacts)
                is_tail = index == last_group and position == len(messages) - 1
                yield Message(artifacts, is_tail)

    def _count(self, artifacts: list[Artifact]) -> None:
        """累计产物数量，供汇总日志使用。

        Args:
            artifacts: 一条消息的产物列表。
        """
        for artifact in artifacts:
            if isinstance(artifact, SourceFile):
                self.file_count += 1
            elif isinstance(artifact, Picture):
                self.image_count += 1

    def cancel(self) -> None:
        """取消尚未完成的渲染任务。"""
        for task in self.tasks:
            task.cancel()


async def plan_chain(
    text: str,
    cfg: RenderConfig,
    seg_cfg: SegmentConfig,
    clean_cfg: CleanConfig | None,
    data_dir: str,
    renderers: dict[type, Callable] | None = None,
) -> Pipeline | None:
    """解析、分组并提交全部渲染任务，返回可逐条产出的流水线。

    文本为空或纯空白，或无需任何处理（无元素、无需清洗、无需切分）
    时返回 None，调用方原样保留消息链。

    Args:
        text: 原链的纯文本（由 render.bridge 拼接）。
        cfg: 渲染配置。
        seg_cfg: 分段配置。
        clean_cfg: 清洗配置，为 None 时跳过清洗。
        data_dir: 插件数据目录路径。
        renderers: 渲染器覆盖层，透传给 build_chain。

    Returns:
        待消费的渲染流水线；无事可做时返回 None。
    """
    if not text.strip():
        return None

    segments = parse(text, split_blank_lines=(seg_cfg.blank_line_mode == "切分"))

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

    # 立刻提交全部渲染任务：并发度与整批渲染时一致，慢的组不挡住别的组开工
    tasks = [
        asyncio.create_task(build_chain(g.segments, cfg, clean_cfg, data_dir, renderers))
        for g in groups
    ]
    return Pipeline(groups, tasks)
