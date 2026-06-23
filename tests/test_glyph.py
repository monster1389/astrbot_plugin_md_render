"""字形回退映射的测试。"""
import pytest
from PIL import ImageFont
from render.glyph import fallback, fallback_text, load_glyph_mapping


def test_fallback_char_available():
    """字符字形存在时返回原字符。"""
    # 任何基本 ASCII 字符字形必然存在
    assert fallback("A", {}) == "A"
    assert fallback("1", {"1": "?"}) == "1"


def test_fallback_char_available_with_mapping():
    """字符字形存在时忽略映射返回原字符。"""
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


def test_load_glyph_mapping_non_dict():
    """非字典 JSON 返回空字典。"""
    assert load_glyph_mapping("[1, 2, 3]") == {}


def test_load_glyph_mapping_invalid_json():
    """无效 JSON 返回空字典。"""
    assert load_glyph_mapping("{bad}") == {}


def test_load_glyph_mapping_whitespace_only():
    """仅空白字符串返回空字典。"""
    assert load_glyph_mapping("   ") == {}


def test_fallback_with_font_and_missing_glyph():
    """字形缺失且有映射时返回映射值。"""
    try:
        font = ImageFont.truetype("DejaVuSansMono", 14)
    except (OSError, IOError):
        pytest.skip("DejaVuSansMono not available")
    # 选择字体中极可能不存在的 unicode 字符
    result = fallback("​", {"​": "?"}, font)
    assert result == "?"
