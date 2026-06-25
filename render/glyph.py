"""字形回退映射。

渲染文本前，逐字符检测目标字体是否覆盖该字形。
若缺失，按配置的映射表替换为替代字符；无映射则保留原字符。
提供 fallback_text（纯文本）和 fallback_spans（富文本 Span）两个入口。
"""

import json
from typing import TYPE_CHECKING, Any

from astrbot.api import logger
from PIL import ImageFont

if TYPE_CHECKING:
    from render.parser import RichCell  # noqa: F401


def load_glyph_mapping(raw: str) -> dict[str, str]:
    """从配置 JSON 字符串解析字形映射表。

    Args:
        raw: JSON 字符串，形如 '{"✗": "✕", "—": "-"}'。

    Returns:
        字符到替代字符的映射字典。解析失败或空串返回 {}。
    """
    if not raw or not raw.strip():
        return {}
    try:
        mapping: Any = json.loads(raw)
        if not isinstance(mapping, dict):
            logger.warning(f"字形映射配置不是 JSON 对象，已忽略: {type(mapping).__name__}")
            return {}
        return {str(k): str(v) for k, v in mapping.items()}
    except json.JSONDecodeError as exc:
        logger.warning(f"字形映射 JSON 解析失败: {exc}")
        return {}


def fallback(char: str, mapping: dict[str, str], font: ImageFont.FreeTypeFont | None = None) -> str:
    """对单个字符执行字形回退检测。

    Args:
        char: 待检测字符。
        mapping: 字形缺失时的替代映射表。
        font: PIL 字体对象，为 None 时跳过检测直接返回原字符。

    Returns:
        若字形存在则返回原字符，否则返回映射表中的替代字符，
        映射表无匹配则返回原字符。
    """
    if font is None:
        return char
    try:
        glyph_index = font.font.get_char_index(ord(char))
        if glyph_index != 0:
            return char
    except (ValueError, OSError, AttributeError):
        pass
    except Exception as exc:
        logger.warning(f"Unexpected error during glyph detection for '{char}': {exc}")
    return mapping.get(char, char)


def fallback_text(text: str, mapping: dict[str, str], font: ImageFont.FreeTypeFont | None = None) -> str:
    """对整段文本逐字符应用字形回退。

    Args:
        text: 原始文本。
        mapping: 字形缺失时的替代映射表。
        font: PIL 字体对象，为 None 时跳过检测直接返回原文。

    Returns:
        回退处理后的文本。
    """
    if font is None:
        return text
    return "".join(fallback(ch, mapping, font) for ch in text)


def fallback_spans(
    cells: list[list[RichCell]],
    mapping: dict[str, str],
    font: "ImageFont.FreeTypeFont | None" = None,
) -> None:
    """对 RichCell 中的 Span 文本逐字符应用字形回退（原地修改）。

    Args:
        cells: [[RichCell]] — [表头行, 数据行...]。
        mapping: 字形缺失时的替代映射表。
        font: PIL 字体对象，为 None 时跳过。
    """
    if font is None:
        return
    for row in cells:
        for cell in row:
            for span in cell.spans:
                span.text = fallback_text(span.text, mapping, font)
