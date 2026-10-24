"""render/font.py 字体服务测试。"""
from unittest.mock import MagicMock, patch

import pytest

from render import font as _font
from render.font import (
    FontSpec,
    body_family,
    body_spec,
    font_family,
    font_files,
    font_search_dir,
    measure_font,
)

NOTO = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
WQY = "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"
SARASA = "/data/fonts/SarasaMonoSC-Regular.ttf"


def _only(*existing: str):
    """生成只认指定路径的 os.path.exists 替身。"""
    return lambda path: path in existing


class TestFindFontSpec:
    def setup_method(self):
        _font._font_spec = None
        _font._measure_cache.clear()

    def test_discovers_noto_mono_face(self):
        """系统只有 Noto 时取第 7 个 face（Noto Sans Mono CJK SC）。"""
        with patch("os.path.exists", side_effect=_only(NOTO)):
            _font.init_font(None)
            assert _font.find_font_spec() == FontSpec(NOTO, 7)

    def test_discovers_wqy_mono_face(self):
        """没有 Noto 时取文泉驿等宽，即第 1 个 face。"""
        with patch("os.path.exists", side_effect=_only(WQY)):
            _font.init_font(None)
            assert _font.find_font_spec() == FontSpec(WQY, 1)

    def test_returns_none_when_none_found(self):
        """没有可用字体时返回 None。"""
        with patch("os.path.exists", return_value=False):
            _font.init_font(None)
            assert _font.find_font_spec() is None

    def test_bundled_font_preferred(self):
        """data_dir 下手动放置的字体优先于系统字体。"""
        with patch("os.path.exists", side_effect=_only(SARASA, NOTO)):
            _font.init_font("/data")
            assert _font.find_font_spec() == FontSpec(SARASA)


class TestBodySpec:
    def test_noto_proportional_face(self):
        """正文取 Noto 的第 2 个 face（比例体 Noto Sans CJK SC）。"""
        with patch("os.path.exists", side_effect=_only(NOTO)):
            _font.init_font(None)
            assert body_spec() == FontSpec(NOTO, 2)

    def test_wqy_proportional_face(self):
        """没有 Noto 时取文泉驿比例体，即第 0 个 face。"""
        with patch("os.path.exists", side_effect=_only(WQY)):
            _font.init_font(None)
            assert body_spec() == FontSpec(WQY, 0)

    def test_manual_mono_font_is_not_body_candidate(self):
        """手动字体是等宽的，没系统字体时正文退回到它，而不是凭空缺席。"""
        with patch("os.path.exists", side_effect=_only(SARASA)):
            _font.init_font("/data")
            assert body_spec() == FontSpec(SARASA)

    def test_none_without_any_font(self):
        with patch("os.path.exists", return_value=False):
            _font.init_font(None)
            assert body_spec() is None


class TestFontFamily:
    def test_system_noto_mono(self):
        """系统 Noto 等宽 face 用等宽 CJK 族名。"""
        assert font_family(FontSpec(NOTO, 7)) == "Noto Sans Mono CJK SC"

    def test_system_noto_proportional(self):
        """系统 Noto 比例 face 用比例 CJK 族名。"""
        assert font_family(FontSpec(NOTO, 2)) == "Noto Sans CJK SC"

    def test_manual_sarasa(self):
        """手动放置的 Sarasa 按文件名推断族名。"""
        assert font_family(FontSpec(SARASA)) == "Sarasa Mono SC"

    def test_unknown_font(self):
        """未知字体返回 None。"""
        assert font_family(FontSpec("/fake/font.ttf")) is None
        assert font_family(None) is None

    def test_body_family_follows_body_spec(self):
        with patch("os.path.exists", side_effect=_only(NOTO)):
            _font.init_font(None)
            assert body_family() == "Noto Sans CJK SC"

    def test_search_dir_only_for_manual(self):
        """系统字体不需要额外注册目录，手动字体要。"""
        assert font_search_dir(FontSpec(NOTO, 7)) is None
        assert font_search_dir(FontSpec(SARASA)) == "/data/fonts"
        assert font_search_dir(None) is None


class TestFontFiles:
    def test_single_ttc_registered_once(self):
        """一个 ttc 同时担正文与等宽，只注册一次。"""
        with patch("os.path.exists", side_effect=_only(NOTO)):
            _font.init_font(None)
            assert font_files() == [NOTO]

    def test_manual_font_and_system_font(self):
        """手动等宽体与系统比例体并存，返回两个文件。"""
        with patch("os.path.exists", side_effect=_only(SARASA, NOTO)):
            _font.init_font("/data")
            assert font_files() == [SARASA, NOTO]

    def test_empty_without_fonts(self):
        with patch("os.path.exists", return_value=False):
            _font.init_font(None)
            assert font_files() == []


class TestMeasureFont:
    def setup_method(self):
        _font._measure_spec = None
        _font._measure_cache.clear()

    @patch("render.font.body_spec", return_value=FontSpec(NOTO, 2))
    def test_caches_by_size(self, mock_spec):
        """同字号只加载一次字体。"""
        with patch("render.font.ImageFont.truetype") as mock_truetype:
            first = measure_font(34)
            second = measure_font(34)
        assert first is second
        mock_truetype.assert_called_once()

    @patch("render.font.body_spec", return_value=FontSpec(NOTO, 2))
    def test_passes_face_index(self, mock_spec):
        """加载 ttc 时把 face 序号传给 Pillow。"""
        with patch("render.font.ImageFont.truetype") as mock_truetype:
            measure_font(34)
        mock_truetype.assert_called_once_with(NOTO, 34, index=2)

    @patch("render.font.body_spec", return_value=FontSpec(NOTO, 2))
    def test_different_sizes_yield_different_fonts(self, mock_spec):
        """不同字号各自加载。"""
        with patch(
            "render.font.ImageFont.truetype",
            side_effect=lambda path, size, index: MagicMock(),
        ) as mock_truetype:
            small = measure_font(14)
            large = measure_font(76)
        assert small is not large
        assert mock_truetype.call_count == 2

    @patch("render.font.body_spec", return_value=None)
    def test_raises_without_font(self, mock_spec):
        """没有任何可用字体时明确报错，交由上层降级。"""
        with pytest.raises(RuntimeError, match="字体"):
            measure_font(34)

    @patch("render.font.body_spec", return_value=FontSpec(NOTO, 2))
    def test_cache_cleared_when_spec_changes(self, mock_spec):
        """字体规格变化后清空缓存，重新加载。"""
        with patch("render.font.ImageFont.truetype", side_effect=lambda *a, **k: MagicMock()):
            first = measure_font(34)
        with patch(
            "render.font.body_spec",
            return_value=FontSpec("/fake/other.ttf", 0),
        ), patch("render.font.ImageFont.truetype", side_effect=lambda *a, **k: MagicMock()):
            second = measure_font(34)
        assert first is not second
