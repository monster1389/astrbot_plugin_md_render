"""配置读取、颜色解析、字体发现、临时路径构建。"""
from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass
from datetime import datetime

from PIL import ImageFont

logger = logging.getLogger(__name__)


_font_cache: dict[int, ImageFont.FreeTypeFont] = {}
_font_path: str | None = None
_lock = threading.Lock()


def get_font(data_dir: str, size: int) -> ImageFont.FreeTypeFont:
    """获取缓存的字体，按字号缓存，路径变更时全清。线程安全。

    Args:
        data_dir: 插件数据目录路径。
        size: 字号（像素）。

    Returns:
        PIL 字体对象。字体不可用时回退为默认位图字体。
    """
    global _font_cache, _font_path
    path = find_font_path(data_dir)
    with _lock:
        if path != _font_path:
            _font_cache.clear()
            _font_path = path
        if size not in _font_cache:
            if path is None:
                logger.warning("未找到中文字体，将使用默认位图字体，中文将显示为豆腐块")
                _font_cache[size] = ImageFont.load_default()
            else:
                _font_cache[size] = ImageFont.truetype(path, size)
        return _font_cache[size]


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
        temp_ttl: 临时文件存活分钟数。
    """
    code_mode: str
    table_mode: str
    expr_mode: str
    divider_mode: str
    font_color: str
    bg_color: str
    temp_ttl: int


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


def load_config(raw: dict) -> RenderConfig:
    """从 AstrBot 原始配置字典构造 RenderConfig。

    Args:
        raw: AstrBot 配置字典。

    Returns:
        RenderConfig 实例。
    """
    return RenderConfig(
        code_mode=raw.get("代码块", "渲染且md文件"),
        table_mode=raw.get("表格", "渲染图像"),
        expr_mode=raw.get("表达式", "渲染图像"),
        divider_mode=raw.get("分隔线", "不处理"),
        font_color=parse_color(raw.get("字体颜色", "#9CDCFE (浅蓝)")),
        bg_color=parse_color(raw.get("背景颜色", "#1E1E1E (VS Code 深色)")),
        temp_ttl=int(raw.get("临时文件存活", 0)),
    )


def parse_color(value: str) -> str:
    """从颜色配置值中提取纯 hex 颜色。

    Args:
        value: 颜色值，如 '#9CDCFE (浅蓝)' 或 '#1E1E1E'。

    Returns:
        纯 hex 颜色字符串。
    """
    return value.split(" ")[0]


def find_font_path(data_dir: str | None = None) -> str | None:
    """发现可用中文字体。

    优先使用捆绑的更纱等宽黑体（中英 2:1 等宽），
    不存在时 fallback 到系统字体。

    Args:
        data_dir: 插件数据目录路径，为 None 时只搜系统字体。

    Returns:
        第一个存在的字体路径，都没找到返回 None。
    """
    candidates: list[str] = []
    if data_dir:
        candidates.append(os.path.join(data_dir, "fonts", "SarasaMonoSC-Regular.ttf"))
    candidates += [
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
        ext: 文件扩展名（如 '.png'、'.md'）。

    Returns:
        完整文件路径。
    """
    temp_dir = os.path.join(data_dir, "temp")
    os.makedirs(temp_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    return os.path.join(temp_dir, f"{prefix}_{ts}{ext}")
