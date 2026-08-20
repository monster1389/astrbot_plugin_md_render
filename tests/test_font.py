"""render/font.py 字体服务测试。"""
from unittest.mock import MagicMock, patch

from render import font as _font


class TestFindFontPath:
    def setup_method(self):
        _font._font_path = None
        _font._font_cache.clear()

    def test_discovers_wqy(self):
        """init_font 后能发现系统 wqy 字体。"""
        with patch("os.path.exists") as mock_exists:
            mock_exists.side_effect = lambda p: "wqy-microhei.ttc" in p
            _font.init_font(None)
            result = _font.find_font_path()
        assert result is not None
        assert "wqy-microhei.ttc" in result

    def test_returns_none_when_none_found(self):
        """没有可用字体时返回 None。"""
        with patch("os.path.exists", return_value=False):
            _font.init_font(None)
            assert _font.find_font_path() is None

    def test_bundled_font_preferred(self):
        """data_dir 下捆绑的更纱字体优先于系统字体。"""
        with patch("os.path.exists") as mock_exists:
            mock_exists.side_effect = lambda p: "SarasaMonoSC-Regular.ttf" in p
            _font.init_font("/data")
            assert _font.find_font_path() == "/data/fonts/SarasaMonoSC-Regular.ttf"


class TestGetFont:
    def setup_method(self):
        _font._font_path = None
        _font._font_cache.clear()

    @patch("render.font._discover_font_path", return_value="/fake/font.ttf")
    def test_caches_by_size(self, mock_discover):
        """同字号只加载一次字体。"""
        _font.init_font("/data")
        with patch("render.font.ImageFont.truetype") as mock_truetype:
            f1 = _font.get_font(14)
            f2 = _font.get_font(14)
        assert f1 is f2
        mock_truetype.assert_called_once()

    @patch("render.font._discover_font_path", return_value="/fake/font.ttf")
    def test_different_sizes_yield_different_fonts(self, mock_discover):
        """不同字号各自加载。"""
        _font.init_font("/data")
        with patch(
            "render.font.ImageFont.truetype",
            side_effect=lambda path, size: MagicMock(),
        ) as mock_truetype:
            f14 = _font.get_font(14)
            f76 = _font.get_font(76)
        assert f14 is not f76
        assert mock_truetype.call_count == 2

    @patch("render.font._discover_font_path", return_value=None)
    def test_fallback_to_default_when_no_font(self, mock_discover):
        """无字体时回退默认位图字体。"""
        _font.init_font("/data")
        with patch("render.font.ImageFont.load_default") as mock_default:
            _font.get_font(14)
        mock_default.assert_called_once()
