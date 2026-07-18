"""render/utils.py 测试。"""
from __future__ import annotations

from dataclasses import FrozenInstanceError
from unittest.mock import MagicMock, patch

from render.utils import (
    RenderConfig,
    load_config,
    find_font_path,
    build_temp_path,
)


class TestFindFontPath:
    def test_wqy_exists(self):
        with patch("os.path.exists") as mock_exists:
            mock_exists.side_effect = lambda p: "wqy-microhei.ttc" in p
            result = find_font_path()
            assert result is not None
            assert "wqy-microhei.ttc" in result

    def test_returns_none_when_none_found(self):
        with patch("os.path.exists", return_value=False):
            assert find_font_path() is None


class TestBuildTempPath:
    @patch("render.utils.os.makedirs")
    def test_creates_dir_and_returns_path(self, mock_makedirs):
        path = build_temp_path("/data", "table", ".png")
        assert path.startswith("/data/temp/table_")
        assert path.endswith(".png")
        mock_makedirs.assert_called_once()


class TestLoadConfig:
    def test_defaults(self):
        raw = {}
        render_cfg, clean_cfg = load_config(raw)
        assert render_cfg.code_mode == "渲染且md文件"
        assert render_cfg.table_mode == "渲染图像"
        assert render_cfg.expr_mode == "渲染图像"
        assert render_cfg.divider_mode == "不处理"
        assert render_cfg.temp_ttl == 0
        assert clean_cfg.bold is True
        assert clean_cfg.italic is True
        assert clean_cfg.strikethrough is True
        assert clean_cfg.inline_code is True
        assert clean_cfg.link is True
        assert clean_cfg.heading is True
        assert clean_cfg.list_unordered is True
        assert clean_cfg.list_ordered is True
        assert clean_cfg.blockquote is True
        assert clean_cfg.image is True

    def test_custom_values(self):
        raw = {
            "渲染": {
                "代码块": "渲染图像",
                "表格": "渲染且保留原文",
                "表达式": "渲染图像",
                "分隔线": "渲染图像",
                "临时文件存活": 10,
            },
            "清洗": {
                "加粗": False,
                "斜体": True,
            },
        }
        render_cfg, clean_cfg = load_config(raw)
        assert render_cfg.code_mode == "渲染图像"
        assert render_cfg.table_mode == "渲染且保留原文"
        assert render_cfg.expr_mode == "渲染图像"
        assert render_cfg.divider_mode == "渲染图像"
        assert render_cfg.temp_ttl == 10
        assert clean_cfg.bold is False
        assert clean_cfg.italic is True

    def test_backward_compat_flat_config(self):
        """旧版平铺配置向后兼容。"""
        raw = {
            "代码块": "渲染图像",
            "表格": "不处理",
            "表达式": "不处理",
            "分隔线": "不处理",
            "临时文件存活": -1,
        }
        render_cfg, clean_cfg = load_config(raw)
        assert render_cfg.code_mode == "渲染图像"

    def test_clean_config_partial(self):
        """清洗配置部分覆盖。"""
        raw = {
            "清洗": {
                "加粗": False,
                "图片": False,
            },
        }
        _, clean_cfg = load_config(raw)
        assert clean_cfg.bold is False
        assert clean_cfg.image is False
        assert clean_cfg.italic is True  # 未指定，默认


class TestRenderConfig:
    def test_frozen(self):
        cfg = RenderConfig(
            code_mode="渲染且txt",
            table_mode="渲染图像",
            expr_mode="渲染图像",
            divider_mode="不处理",
            temp_ttl=5,
        )
        try:
            cfg.code_mode = "xxx"
            assert False, "should have raised FrozenInstanceError"
        except FrozenInstanceError:
            pass


class TestGetFont:
    def setup_method(self):
        import render.utils as _ru
        _ru._font_cache.clear()
        _ru._font_path = None

    @patch("render.utils.find_font_path", return_value="/fake/font.ttf")
    @patch("render.utils.ImageFont.truetype")
    def test_caches_by_size(self, mock_truetype, mock_find):
        from render.utils import get_font
        f1 = get_font("/data", 14)
        f2 = get_font("/data", 14)
        assert f1 is f2
        mock_truetype.assert_called_once()

    @patch("render.utils.find_font_path", return_value="/fake/font.ttf")
    @patch("render.utils.ImageFont.truetype")
    def test_different_sizes_yield_different_fonts(self, mock_truetype, mock_find):
        mock_truetype.side_effect = lambda path, size: MagicMock()
        from render.utils import get_font
        f14 = get_font("/data", 14)
        f76 = get_font("/data", 76)
        assert f14 is not f76
        assert mock_truetype.call_count == 2

    @patch("render.utils.find_font_path", return_value=None)
    @patch("render.utils.ImageFont.load_default")
    def test_fallback_to_default_when_no_font(self, mock_default, mock_find):
        from render.utils import get_font
        get_font("/data", 14)
        mock_default.assert_called_once()
