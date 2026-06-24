"""render/utils.py 测试。"""
from __future__ import annotations

from dataclasses import FrozenInstanceError
from unittest.mock import patch

from render.utils import (
    RenderConfig,
    load_config,
    parse_color,
    find_font_path,
    build_temp_path,
)


class TestParseColor:
    def test_with_hint(self):
        assert parse_color("#9CDCFE (浅蓝)") == "#9CDCFE"

    def test_pure_hex(self):
        assert parse_color("#1E1E1E") == "#1E1E1E"

    def test_lowercase(self):
        assert parse_color("#aabbcc") == "#aabbcc"


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
        cfg = load_config(raw)
        assert cfg.code_mode == "渲染且txt"
        assert cfg.table_mode == "渲染图像"
        assert cfg.expr_mode == "渲染图像"
        assert cfg.divider_mode == "不处理"
        assert cfg.font_color == "#9CDCFE"
        assert cfg.bg_color == "#1E1E1E"
        assert cfg.glyph_mapping == {}
        assert cfg.temp_ttl == 5

    def test_custom_values(self):
        raw = {
            "代码块": "渲染图像",
            "表格": "渲染且保留原文",
            "表达式": "渲染图像",
            "分隔线": "渲染图像",
            "字体颜色": "#FF0000 (红)",
            "背景颜色": "#000000 (黑)",
            "临时文件存活": 10,
        }
        cfg = load_config(raw)
        assert cfg.code_mode == "渲染图像"
        assert cfg.table_mode == "渲染且保留原文"
        assert cfg.expr_mode == "渲染图像"
        assert cfg.divider_mode == "渲染图像"
        assert cfg.font_color == "#FF0000"
        assert cfg.bg_color == "#000000"
        assert cfg.temp_ttl == 10


class TestRenderConfig:
    def test_frozen(self):
        cfg = RenderConfig(
            code_mode="渲染且txt",
            table_mode="渲染图像",
            expr_mode="渲染图像",
            divider_mode="不处理",
            font_color="#000",
            bg_color="#FFF",
            glyph_mapping={},
            temp_ttl=5,
        )
        try:
            cfg.code_mode = "xxx"
            assert False, "should have raised FrozenInstanceError"
        except FrozenInstanceError:
            pass
