"""表达式渲染测试。"""
from io import BytesIO
from unittest.mock import patch

import pytest
from PIL import Image

from render import canvas
from render.expr_render import (
    Formula,
    _formula_cached,
    _to_typst,
    formula_image,
    render_expr,
    render_formula,
)
from render.parser import BlockExpr, InlineExpr


def _image(png: bytes) -> Image.Image:
    """把公式 PNG 解成 RGBA 图像，供像素断言用。"""
    return Image.open(BytesIO(png)).convert("RGBA")


def _has_ink(image: Image.Image) -> bool:
    """判断图像是否有可见像素。"""
    return image.getchannel("A").getbbox() is not None


def _png(width: int = 1, height: int = 1) -> bytes:
    """造一张最小 PNG，供不解码的用例使用。"""
    buf = BytesIO()
    Image.new("RGBA", (width, height), (0, 0, 0, 255)).save(buf, "PNG")
    return buf.getvalue()


@pytest.fixture(autouse=True)
def _clear_formula_cache():
    """公式图按 (源码, 角色, 颜色) 缓存，用例之间互不影响。"""
    _formula_cached.cache_clear()
    yield
    _formula_cached.cache_clear()


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


class TestRenderFormula:
    """真实调用 Typst 渲染。"""

    def test_returns_transparent_png_with_ink(self):
        """返回有可见像素的透明底 PNG；解码与合成都不在这里做。"""
        png = render_formula(r"E = mc^2", color="#112233", size=canvas.EXPR_SIZE, pad=0)

        assert png.startswith(b"\x89PNG")
        image = _image(png)
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
        png = render_formula(latex, color="#112233", size=canvas.EXPR_SIZE, pad=0)
        assert _has_ink(_image(png))

    def test_pad_grows_the_image(self):
        """留白由 Typst 的 page margin 给：独立公式比格内公式大一圈。"""
        tight = _image(
            render_formula("E=mc^2", color="#112233", size=canvas.EXPR_SIZE, pad=0)
        ).size
        padded = _image(
            render_formula("E=mc^2", color="#112233", size=canvas.EXPR_SIZE, pad=10)
        ).size
        assert padded[0] > tight[0]
        assert padded[1] > tight[1]

    def test_failure_propagates(self):
        """编译失败包装成 RuntimeError，交给上层回退原文。"""
        with patch("render.expr_render.typst.compile", side_effect=ValueError("boom")):
            with pytest.raises(RuntimeError, match="LaTeX 渲染失败"):
                render_formula(r"E = mc^2", color="#112233", size=canvas.EXPR_SIZE, pad=0)


class TestRenderExpr:
    @patch("render.expr_render.formula_image")
    def test_inline_expr(self, mock_formula):
        """行内表达式是 body 角色的薄包装，原样返回 PNG 字节。"""
        mock_formula.return_value = Formula(png=b"\x89PNG fake", width=10, height=5)

        png_bytes = render_expr(InlineExpr(expr="E=mc^2"))

        assert png_bytes == b"\x89PNG fake"
        mock_formula.assert_called_once_with("E=mc^2")

    @patch("render.expr_render.formula_image")
    def test_block_expr(self, mock_formula):
        """块级表达式同样只有一条出口。"""
        mock_formula.return_value = Formula(png=b"\x89PNG fake", width=10, height=5)

        png_bytes = render_expr(BlockExpr(expr="\\int_0^\\infty e^{-x} dx = 1"))

        assert png_bytes == b"\x89PNG fake"
        mock_formula.assert_called_once_with("\\int_0^\\infty e^{-x} dx = 1")


class TestFormulaImage:
    """角色定形：字号、默认色、留白与缓存。"""

    def _spy(self, monkeypatch) -> dict:
        seen: dict = {}

        def fake(src, **kw):
            seen.update(kw)
            return _png()

        monkeypatch.setattr("render.expr_render.render_formula", fake)
        return seen

    def test_body_role_is_the_default(self, monkeypatch):
        seen = self._spy(monkeypatch)
        formula_image("x")
        assert seen["size"] == canvas.EXPR_SIZE
        assert seen["color"] == canvas.EXPR_COLOR
        assert seen["pad"] > 0

    def test_table_role_is_tight_and_small(self, monkeypatch):
        seen = self._spy(monkeypatch)
        formula_image("x", role="table")
        assert seen["size"] == canvas.TABLE_SIZE
        assert seen["color"] == canvas.TEXT
        assert seen["pad"] == 0

    def test_header_role_uses_header_color(self, monkeypatch):
        seen = self._spy(monkeypatch)
        formula_image("x", role="table_header")
        assert seen["color"] == canvas.BOLD

    def test_color_override_wins(self, monkeypatch):
        seen = self._spy(monkeypatch)
        formula_image("x", role="table", color=canvas.ITALIC)
        assert seen["color"] == canvas.ITALIC

    def test_same_source_and_role_reuses_cache(self, monkeypatch):
        calls: list[str] = []

        def fake(src, **kw):
            calls.append(src)
            return _png()

        monkeypatch.setattr("render.expr_render.render_formula", fake)
        formula_image("x", role="table")
        formula_image("x", role="table")
        formula_image("x", role="table_header")
        assert calls == ["x", "x"]

    def test_failure_is_not_cached(self, monkeypatch):
        calls: list[str] = []

        def boom(src, **kw):
            calls.append(src)
            raise RuntimeError("boom")

        monkeypatch.setattr("render.expr_render.render_formula", boom)
        for _ in range(2):
            with pytest.raises(RuntimeError):
                formula_image("x")
        assert calls == ["x", "x"]
