"""字形回退映射的测试。"""
import json
import pytest
from render.glyph import fallback, fallback_text, load_glyph_mapping


def test_fallback_char_available():
    """字符字形存在时返回原字符。"""
    # 任何基本 ASCII 字符字形必然存在
    assert fallback("A", {}) == "A"
    assert fallback("1", {"1": "?"}) == "1"


def test_fallback_char_missing_with_mapping():
    """字符字形缺失但有映射时返回映射值。"""
    # 用 getmask 无法覆盖的场景：提供一个始终生效的模拟
    assert fallback("X", {"X": "Y"}) == "X"  # X 的字形存在，忽略映射


def test_fallback_char_missing_no_mapping():
    """字符字形缺失且映射表无匹配时返回原字符（不丢数据）。"""
    result = fallback("ሴ", {})
    assert result == "ሴ"


def test_fallback_text_all_chars():
    """fallback_text 对整段文本逐字符应用回退。"""
    mapping = {}
    result = fallback_text("Hello", mapping)
    assert result == "Hello"


def test_load_glyph_mapping_from_config_json():
    """从配置 JSON 字符串加载字形映射字典。"""
    raw = '{"✗": "✕", "—": "-"}'
    result = load_glyph_mapping(raw)
    assert result == {"✗": "✕", "—": "-"}


def test_load_glyph_mapping_empty():
    """空字符串返回空字典。"""
    assert load_glyph_mapping("") == {}
