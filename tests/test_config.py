"""render/config.py 测试。"""
from __future__ import annotations

from dataclasses import FrozenInstanceError

from render.config import (
    RenderConfig,
    load_config,
)


class TestLoadConfig:
    def test_defaults(self):
        raw = {}
        render_cfg, seg_cfg, clean_cfg = load_config(raw)
        assert render_cfg.code_mode == "渲染且md文件"
        assert render_cfg.table_mode == "渲染图像"
        assert render_cfg.expr_mode == "渲染图像"
        assert render_cfg.temp_ttl == 3
        assert seg_cfg.divider_mode == "切分"
        assert seg_cfg.blank_line_mode == "切分"
        assert seg_cfg.send_delay is True
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
        assert clean_cfg.divider is True
        assert clean_cfg.blank_line is True
        assert clean_cfg.code is False

    def test_custom_values(self):
        raw = {
            "渲染": {
                "代码块": "渲染图像",
                "表格": "渲染且保留原文",
                "表达式": "渲染图像",
                "临时文件存活": 10,
            },
            "分段": {
                "分隔线": "不处理",
                "连续换行": "切分",
                "发送延时": False,
            },
            "清洗": {
                "加粗": False,
                "斜体": True,
            },
        }
        render_cfg, seg_cfg, clean_cfg = load_config(raw)
        assert render_cfg.code_mode == "渲染图像"
        assert render_cfg.table_mode == "渲染且保留原文"
        assert render_cfg.expr_mode == "渲染图像"
        assert render_cfg.temp_ttl == 10
        assert seg_cfg.divider_mode == "不处理"
        assert seg_cfg.blank_line_mode == "切分"
        assert seg_cfg.send_delay is False
        assert clean_cfg.bold is False
        assert clean_cfg.italic is True

    def test_clean_config_partial(self):
        """清洗配置部分覆盖。"""
        raw = {
            "清洗": {
                "加粗": False,
                "图片": False,
            },
        }
        _, _, clean_cfg = load_config(raw)
        assert clean_cfg.bold is False
        assert clean_cfg.image is False
        assert clean_cfg.italic is True  # 未指定，默认


class TestRenderConfig:
    def test_frozen(self):
        cfg = RenderConfig(
            code_mode="渲染且txt",
            table_mode="渲染图像",
            expr_mode="渲染图像",
            temp_ttl=5,
        )
        try:
            cfg.code_mode = "xxx"
            assert False, "should have raised FrozenInstanceError"
        except FrozenInstanceError:
            pass


