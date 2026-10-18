"""render/font.py 字体服务测试。"""
from unittest.mock import MagicMock, patch

from render import font as _font
from render.font import FontSpec, font_family, font_search_dir

NOTO = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
WQY = "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"
SARASA = "/data/fonts/SarasaMonoSC-Regular.ttf"


def _only(*existing: str):
    """生成只认指定路径的 os.path.exists 替身。"""
    return lambda path: path in existing


class TestFindFontSpec:
    def setup_method(self):
        _font._font_spec = None
        _font._font_cache.clear()

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


class TestFontFamily:
    def test_system_noto(self):
        """系统 Noto 用等宽 CJK 族名。"""
        assert font_family(FontSpec(NOTO, 7)) == "Noto Sans Mono CJK SC"

    def test_manual_sarasa(self):
        """手动放置的 Sarasa 按文件名推断族名。"""
        assert font_family(FontSpec(SARASA)) == "Sarasa Mono SC"

    def test_unknown_font(self):
        """未知字体返回 None。"""
        assert font_family(FontSpec("/fake/font.ttf")) is None
        assert font_family(None) is None

    def test_search_dir_only_for_manual(self):
        """系统字体不需要额外注册目录，手动字体要。"""
        assert font_search_dir(FontSpec(NOTO, 7)) is None
        assert font_search_dir(FontSpec(SARASA)) == "/data/fonts"
        assert font_search_dir(None) is None


class TestGetFont:
    def setup_method(self):
        _font._font_spec = None
        _font._font_cache.clear()

    @patch("render.font._discover_font_spec", return_value=FontSpec("/fake/font.ttc", 7))
    def test_caches_by_size(self, mock_discover):
        """同字号只加载一次字体。"""
        _font.init_font("/data")
        with patch("render.font.ImageFont.truetype") as mock_truetype:
            f1 = _font.get_font(14)
            f2 = _font.get_font(14)
        assert f1 is f2
        mock_truetype.assert_called_once()

    @patch("render.font._discover_font_spec", return_value=FontSpec("/fake/font.ttc", 7))
    def test_passes_face_index(self, mock_discover):
        """加载 ttc 时把 face 序号传给 Pillow。"""
        _font.init_font("/data")
        with patch("render.font.ImageFont.truetype") as mock_truetype:
            _font.get_font(14)
        mock_truetype.assert_called_once_with("/fake/font.ttc", 14, index=7)

    @patch("render.font._discover_font_spec", return_value=FontSpec("/fake/font.ttf", 0))
    def test_different_sizes_yield_different_fonts(self, mock_discover):
        """不同字号各自加载。"""
        _font.init_font("/data")
        with patch(
            "render.font.ImageFont.truetype",
            side_effect=lambda path, size, index: MagicMock(),
        ) as mock_truetype:
            f14 = _font.get_font(14)
            f76 = _font.get_font(76)
        assert f14 is not f76
        assert mock_truetype.call_count == 2

    @patch("render.font._discover_font_spec", return_value=None)
    def test_fallback_to_default_when_no_font(self, mock_discover):
        """无字体时回退默认位图字体。"""
        _font.init_font("/data")
        with patch("render.font.ImageFont.load_default") as mock_default:
            _font.get_font(14)
        mock_default.assert_called_once()

    @patch("render.font._discover_font_spec", return_value=FontSpec("/fake/font.ttc", 7))
    def test_cache_cleared_when_spec_changes(self, mock_discover):
        """字体规格变化后清空缓存，重新加载。"""
        _font.init_font("/data")
        with patch("render.font.ImageFont.truetype", side_effect=lambda *a, **k: MagicMock()):
            first = _font.get_font(14)
            with patch(
                "render.font._discover_font_spec",
                return_value=FontSpec("/fake/other.ttf", 0),
            ):
                second = _font.get_font(14)
        assert first is not second
