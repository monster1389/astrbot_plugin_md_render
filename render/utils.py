"""配置读取、颜色解析、字体发现、临时路径构建。"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime

from render.glyph import load_glyph_mapping


@dataclass(frozen=True)
class RenderConfig:
    """渲染配置。

    Attributes:
        code_mode: 代码块处理模式。
        table_mode: 表格处理模式。
        expr_mode: 数学表达式处理模式。
        divider_mode: 水平分割线处理模式。
        font_color: 字体颜色（纯 hex）。
        bg_color: 背景颜色（纯 hex）。
        glyph_mapping: 字形映射表。
        temp_ttl: 临时文件存活分钟数。
    """
    code_mode: str
    table_mode: str
    expr_mode: str
    divider_mode: str
    font_color: str
    bg_color: str
    glyph_mapping: dict
    temp_ttl: int


def load_config(raw: dict) -> RenderConfig:
    """从 AstrBot 原始配置字典构造 RenderConfig。

    Args:
        raw: AstrBot 配置字典。

    Returns:
        RenderConfig 实例。
    """
    return RenderConfig(
        code_mode=raw.get("代码块", "渲染且txt"),
        table_mode=raw.get("表格", "渲染图像"),
        expr_mode=raw.get("表达式", "渲染图像"),
        divider_mode=raw.get("分隔线", "不处理"),
        font_color=parse_color(raw.get("字体颜色", "#9CDCFE (浅蓝)")),
        bg_color=parse_color(raw.get("背景颜色", "#1E1E1E (VS Code 深色)")),
        glyph_mapping=load_glyph_mapping(raw.get("字形映射", "{}")),
        temp_ttl=int(raw.get("临时文件存活", 5)),
    )


def parse_color(value: str) -> str:
    """从颜色配置值中提取纯 hex 颜色。

    Args:
        value: 颜色值，如 '#9CDCFE (浅蓝)' 或 '#1E1E1E'。

    Returns:
        纯 hex 颜色字符串。
    """
    return value.split(" ")[0]


def find_font_path() -> str | None:
    """发现可用中文字体。

    Returns:
        第一个存在的字体路径，都没找到返回 None。
    """
    candidates = [
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


def build_temp_path(data_dir: str, prefix: str, ext: str) -> str:
    """在 data_dir/temp/ 下建带时间戳的文件路径。

    Args:
        data_dir: 插件数据目录路径。
        prefix: 文件名前缀（如 'code'、'table'、'expr'）。
        ext: 文件扩展名（如 '.png'、'.txt'）。

    Returns:
        完整文件路径。
    """
    temp_dir = os.path.join(data_dir, "temp")
    os.makedirs(temp_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return os.path.join(temp_dir, f"{prefix}_{ts}{ext}")
