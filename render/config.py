"""配置 dataclass 与读取。

导出: RenderConfig, SegmentConfig, CleanConfig, load_config
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RenderConfig:
    """渲染配置。

    Attributes:
        code_mode: 代码块处理模式。
        table_mode: 表格处理模式。
        expr_mode: 数学表达式处理模式。
        temp_ttl: 临时文件存活分钟数（0=发送完成后立即删除）。
    """
    code_mode: str
    table_mode: str
    expr_mode: str
    temp_ttl: int


@dataclass(frozen=True)
class SegmentConfig:
    """分段配置。

    Attributes:
        divider_mode: 水平分割线处理模式（不处理/切分）。
        blank_line_mode: 连续换行（空行）处理模式（不处理/切分）。
        send_delay: 切分后多条消息间是否随机延时（1~3 秒）防风控。
    """
    divider_mode: str
    blank_line_mode: str
    send_delay: bool = True


@dataclass(frozen=True)
class CleanConfig:
    """Markdown 格式清洗配置。

    Attributes:
        bold: 去除 ** 加粗标记。
        italic: 去除 * 斜体标记。
        strikethrough: 去除 ~~ 删除线标记。
        inline_code: 去除 ` 行内代码标记。
        link: 去除 [文字](url) 转为 文字 (url)。
        heading: 去除行首 # 标题标记。
        list_unordered: 去除 - 无序列表标记。
        list_ordered: 去除 1. 有序列表标记。
        blockquote: 去除 > 引用标记。
        image: 去除 ![alt](url) 转为 alt (url)。
        divider: 去除独立 --- 分隔线标记，保留段落分隔。
        blank_line: 将连续空行压为单个换行。
        code: 去除 ``` 围栏标记，保留代码文本。
        table: 去除表头分隔行及首尾 |，保留列分隔符。
        expr: 去除 $ 和 $$ 定界符，保留公式文本。
    """
    bold: bool = True
    italic: bool = True
    strikethrough: bool = True
    inline_code: bool = True
    link: bool = True
    heading: bool = True
    list_unordered: bool = True
    list_ordered: bool = True
    blockquote: bool = True
    image: bool = True
    divider: bool = True
    blank_line: bool = True
    code: bool = False
    table: bool = False
    expr: bool = False


def load_config(raw: dict) -> tuple[RenderConfig, SegmentConfig, CleanConfig]:
    """从 AstrBot 原始配置字典构造 RenderConfig、SegmentConfig 和 CleanConfig。

    适配三块嵌套配置结构：raw["渲染"]、raw["分段"]、raw["清洗"]。

    Args:
        raw: AstrBot 配置字典。

    Returns:
        (RenderConfig, SegmentConfig, CleanConfig) 元组。
    """
    render_raw = raw.get("渲染", {})
    segment_raw = raw.get("分段", {})
    clean_raw = raw.get("清洗", {})

    render_cfg = RenderConfig(
        code_mode=render_raw.get("代码块", "渲染且md文件"),
        table_mode=render_raw.get("表格", "渲染图像"),
        expr_mode=render_raw.get("表达式", "渲染图像"),
        temp_ttl=int(render_raw.get("临时文件存活", 3)),
    )

    segment_cfg = SegmentConfig(
        divider_mode=segment_raw.get("分隔线", "切分"),
        blank_line_mode=segment_raw.get("连续换行", "切分"),
        send_delay=bool(segment_raw.get("发送延时", True)),
    )

    clean_cfg = CleanConfig(
        bold=bool(clean_raw.get("加粗", True)),
        italic=bool(clean_raw.get("斜体", True)),
        strikethrough=bool(clean_raw.get("删除线", True)),
        inline_code=bool(clean_raw.get("行内代码", True)),
        link=bool(clean_raw.get("链接", True)),
        heading=bool(clean_raw.get("标题", True)),
        list_unordered=bool(clean_raw.get("列表标记（无序）", True)),
        list_ordered=bool(clean_raw.get("列表标记（有序）", True)),
        blockquote=bool(clean_raw.get("引用", True)),
        image=bool(clean_raw.get("图片", True)),
        divider=bool(clean_raw.get("分隔线", True)),
        blank_line=bool(clean_raw.get("连续换行", True)),
        code=bool(clean_raw.get("代码块", False)),
        table=bool(clean_raw.get("表格", False)),
        expr=bool(clean_raw.get("表达式", False)),
    )

    return render_cfg, segment_cfg, clean_cfg
