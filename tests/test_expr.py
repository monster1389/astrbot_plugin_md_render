"""表达式渲染测试。"""
from unittest.mock import patch

import pytest
from PIL import Image

from render.expr_render import _to_typst, render_expr, render_expr_image
from render.parser import BlockExpr, InlineExpr


def _has_ink(image: Image.Image) -> bool:
    """判断图像是否有可见像素。"""
    return image.getchannel("A").getbbox() is not None


class TestToTypst:
    """转换层要补的已知缺口。"""

    def test_hbar(self):
        """\\hbar 换成 Typst 认识的 planck。"""
        body = _to_typst(r"\hbar")
        assert "planck" in body
        assert "planck.reduce" not in body

    def test_oint_after_brace(self):
        """\\frac{1}{\\rho}\\oint 不能被粘成 rhointegral。"""
        body = _to_typst(r"\frac{1}{\rho}\oint_{\partial\Omega}")
        assert "rhointegral" not in body

    def test_literal_ampersand(self):
        """\\& 走文本模式，不能变成 Typst 的对齐点。"""
        assert _to_typst(r"\&") == r"#text[\&]"

    def test_literal_underscore(self):
        """\\_ 走文本模式，不能变成下标。"""
        assert r"#text[\_]" in _to_typst(r"a\_b")

    def test_mathscr(self):
        """\\mathscr 退成 \\mathcal，保留花体。"""
        assert "cal(" in _to_typst(r"\mathscr{H}")

    def test_chinese_text(self):
        """\\text{中文} 原样交给 Typst 文本模式。"""
        assert _to_typst(r"\text{中文}") == "#text[中文]"

    def test_empty_source_raises(self):
        """转换后无内容时直接报错，让上层走降级。"""
        with pytest.raises(ValueError):
            _to_typst(r"\displaystyle")


class TestRenderExprImage:
    """真实调用 Typst 渲染。"""

    def test_returns_rgba_with_ink(self):
        """返回有可见像素的 RGBA 透明底图像。"""
        image = render_expr_image(r"E = mc^2", color="#112233")

        assert image.mode == "RGBA"
        assert image.width > 0
        assert image.height > 0
        assert _has_ink(image)

    @pytest.mark.parametrize(
        "latex",
        [
            r"\hbar",
            r"\frac{1}{\rho}\oint_{\partial\Omega}",
            r"\&",
            r"x \nleq y",
            r"\begin{aligned} a &= b \\ c &= d \end{aligned}",
            r"\begin{pmatrix} a & b \\ c & d \end{pmatrix}",
            r"a\phantom{x}b",
            r"\aleph\ \beth\ \hbar\ \ell\ \wp\ \Im\ \Re\ \mho\ \Finv",
        ],
    )
    def test_known_cases_render(self, latex):
        """转换层的回归用例都能画出内容。"""
        assert _has_ink(render_expr_image(latex, color="#112233"))

    def test_failure_propagates(self):
        """编译失败包装成 RuntimeError，交给上层回退原文。"""
        with patch("render.expr_render.typst.compile", side_effect=ValueError("boom")):
            with pytest.raises(RuntimeError, match="LaTeX 渲染失败"):
                render_expr_image(r"E = mc^2", color="#112233")


class TestRenderExpr:
    @patch("render.expr_render.render_expr_image")
    def test_inline_expr(self, mock_render_image):
        """行内表达式渲染返回 PNG 字节串。"""
        mock_render_image.return_value = Image.new("RGBA", (100, 20), (0, 0, 0, 255))

        png_bytes = render_expr(InlineExpr(expr="E=mc^2"))

        assert isinstance(png_bytes, bytes)
        assert len(png_bytes) > 0
        mock_render_image.assert_called_once_with("E=mc^2", color="#9CDCFE")

    @patch("render.expr_render.render_expr_image")
    def test_block_expr(self, mock_render_image):
        """块级表达式渲染返回 PNG 字节串。"""
        mock_render_image.return_value = Image.new("RGBA", (200, 30), (0, 0, 0, 255))

        png_bytes = render_expr(BlockExpr(expr="\\int_0^\\infty e^{-x} dx = 1"))

        assert isinstance(png_bytes, bytes)
        assert len(png_bytes) > 0
        mock_render_image.assert_called_once_with(
            "\\int_0^\\infty e^{-x} dx = 1", color="#9CDCFE"
        )
