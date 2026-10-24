"""数学表达式渲染。

用 Typst 渲染 LaTeX：先用 tylax 把 LaTeX 转成 Typst 语法，再编译成 PNG。
Typst 有完整排版引擎，``aligned`` 的 ``&`` 对齐、矩阵、``\\text{中文}``
都由引擎处理，不再靠替换表把命令改成 Unicode 字符。转换层已知的少量缺口
（``\\hbar``、``\\oint`` 粘词、``\\&``、``\\_``、``\\mathscr``）在转换前
后补齐；仍然转换或编译失败的直接抛给上层回退原文，不做静默替换。

表格格内公式与独立出现的公式走同一条排版路径（``formula_image``，角色决定
字号与默认色）；链上的 ``render_expr`` 只是 body 角色的一层包装。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

import tylax
import typst

from astrbot.api import logger
from render import canvas, font
from render.png import header_size

# 独立公式图的留白（像素）；表格内嵌公式不留白，由表格排版加间距
_PAD = 10

# Typst 按 ppi 换算成 pt
_PPI = 200

# Typst 内置数学字体；中文按 font.py 发现的字体族回退
_MATH_FONT = "New Computer Modern"

# Typst 里 & 是对齐点、_ 是下标，LaTeX 的转义字符必须走文本模式
_TEXT_ESCAPES: tuple[tuple[str, str], ...] = (
    ("\\&", "\\text{\\&}"),
    ("\\_", "\\text{\\_}"),
)

# LaTeX 的否定关系在 Typst 里没有同名符号，换成 \not<rel>
_NEGATED_RELATIONS: dict[str, str] = {
    "nleq": r"\not\leq",
}

# Typst 没有对应名字的符号，直接换成 Unicode 字符
_UNICODE_COMMANDS: dict[str, str] = {
    "wp": "℘",
    "Finv": "Ⅎ",
}

# 数学花体：Typst 有 scr，但转换器不认识 \mathscr，先用 \mathcal 近似
_MATHSCR_RE = re.compile(r"\\mathscr(?![A-Za-z])")

# 只提醒一次，避免每条公式刷屏
_warned_missing_font = False


def _pre_fix(latex: str) -> str:
    """修补转换器已知的 LaTeX 缺口。

    Args:
        latex: 原始 LaTeX 源码（不含 $ 分隔符）。

    Returns:
        修补后的 LaTeX 源码。
    """
    # \frac{1}{\rho}\oint 这类写法会被粘成 rhointegral，先补一个空格
    text = re.sub(r"}(?=\\)", "} ", latex)
    for source, target in _TEXT_ESCAPES:
        text = text.replace(source, target)
    for name, target in _NEGATED_RELATIONS.items():
        text = re.sub(
            r"\\" + name + r"(?![A-Za-z])",
            lambda _m, replacement=target: replacement,
            text,
        )
    for name, char in _UNICODE_COMMANDS.items():
        text = re.sub(
            r"\\" + name + r"(?![A-Za-z])",
            lambda _m, replacement=char: replacement,
            text,
        )
    return _MATHSCR_RE.sub(r"\\mathcal", text)


def _post_fix(body: str) -> str:
    """修补转换产物里 Typst 已改名的符号。

    Args:
        body: tylax 输出的 Typst 源码。

    Returns:
        修补后的 Typst 源码。
    """
    return body.replace("planck.reduce", "planck")


def _to_typst(latex: str) -> str:
    """把 LaTeX 转成 Typst 数学源码。

    Args:
        latex: 原始 LaTeX 源码（不含 $ 分隔符）。

    Returns:
        可直接交给 Typst 的数学源码。

    Raises:
        ValueError: 转换后没有可渲染内容。
    """
    body = _post_fix(tylax.latex_to_typst(_pre_fix(latex))).strip()
    if not body:
        raise ValueError(f"表达式无可渲染内容：{latex!r}")
    return body


def _warn_missing_font() -> None:
    """提示一次缺少中文字体。"""
    global _warned_missing_font
    if not _warned_missing_font:
        logger.warning("未找到中文字体，公式里的中文将显示为方块")
        _warned_missing_font = True


def _font_setup() -> tuple[list[str], list[str]]:
    """构造 Typst 的字体目录与字体族列表。

    系统字体那一半来自 ``render.font``；数学字体是 Typst 自己的事，拼在末尾。

    Returns:
        (font_paths, 字体族列表)。系统字体不需要额外目录。
    """
    font_paths, families = font.typst_fonts()
    if not families:
        _warn_missing_font()
    return font_paths, families + [_MATH_FONT]


def _document(
    body: str,
    color: str,
    size: int,
    families: list[str],
    pad: int,
) -> bytes:
    """拼出单条公式的 Typst 文档。

    Args:
        body: Typst 数学源码。
        color: 文字颜色，如 ``#9CDCFE``。
        size: 字号（像素），按 ppi 换算成 pt。
        families: 字体族回退列表。
        pad: 四周留白（像素），按 ppi 换算成 pt。

    Returns:
        UTF-8 编码的 Typst 源文档。
    """
    font_list = ", ".join(f'"{name}"' for name in families)
    size_pt = size * 72 / _PPI
    pad_pt = pad * 72 / _PPI
    # align* 等环境转换出来本身就是完整方程块，不能再包一层 $
    content = body if body.startswith("#math.equation") else f"$ {body} $"
    source = (
        f"#set page(width: auto, height: auto, margin: {pad_pt:.2f}pt, fill: none)\n"
        f'#set text(fill: rgb("{color}"), size: {size_pt:.2f}pt, font: ({font_list}))\n'
        f"{content}\n"
    )
    return source.encode()


def render_formula(src: str, *, color: str, size: int, pad: int) -> bytes:
    """把 LaTeX 源码排成透明底 PNG。

    透明底与留白都由 Typst 的 page 设置给出；扁平化与量化统一在链出口做，
    这里不解码也不重编码。

    Args:
        src: LaTeX 源码（不含 $ 分隔符）。
        color: 文字颜色。
        size: 字号（像素）。
        pad: 四周留白（像素）。

    Returns:
        PNG 字节串，背景透明。

    Raises:
        RuntimeError: 转换或编译失败，交由上层降级为原文。
    """
    body = _to_typst(src)
    font_paths, families = _font_setup()
    source = _document(body, color, size, families, pad)
    try:
        return typst.compile(source, format="png", ppi=_PPI, font_paths=font_paths)
    except Exception as exc:
        raise RuntimeError(f"LaTeX 渲染失败：{src[:120]}") from exc


Role = Literal["body", "table", "table_header"]

# 角色 → (字号, 默认文字色, 留白)。表格格内不留白，独立公式留一圈。
_ROLE_SPECS: dict[str, tuple[int, str, int]] = {
    "body": (canvas.EXPR_SIZE, canvas.EXPR_COLOR, _PAD),
    "table": (canvas.TABLE_SIZE, canvas.TEXT, 0),
    "table_header": (canvas.TABLE_SIZE, canvas.BOLD, 0),
}

_CACHE_SIZE = 128


@dataclass(frozen=True)
class Formula:
    """一张公式图与它的尺寸。

    Attributes:
        png: 透明底 PNG 字节。
        width: 宽（像素）。
        height: 高（像素）。
    """

    png: bytes
    width: int
    height: int


@lru_cache(maxsize=_CACHE_SIZE)
def _formula_cached(src: str, role: str, color: str) -> Formula:
    """按 (源码, 角色, 颜色) 缓存地排一张公式图。

    Args:
        src: LaTeX 源码（不含 $ 分隔符）。
        role: 角色键，决定字号与留白。
        color: 已解析的文字颜色。

    Returns:
        公式图与尺寸。

    Raises:
        RuntimeError: 转换或编译失败；失败不入缓存。
    """
    size, _, pad = _ROLE_SPECS[role]
    png = render_formula(src, color=color, size=size, pad=pad)
    width, height = header_size(png)
    return Formula(png=png, width=width, height=height)


def formula_image(
    src: str,
    *,
    role: Role = "body",
    color: str | None = None,
) -> Formula:
    """公式图的唯一入口：源码 + 角色 → 图与尺寸。

    独立公式（role=body）与表格格内公式（role=table / table_header）走同一条
    排版路径，只差字号与默认颜色；缓存按 (源码, 角色, 颜色) 跨消息复用，
    失败不入缓存。字体在启动时注册，换字体要重启插件。

    Args:
        src: LaTeX 源码（不含 $ 分隔符）。
        role: 出现位置，决定字号、留白与默认颜色。
        color: 覆盖默认颜色（格内带格式的片段用）。

    Returns:
        公式图与尺寸。

    Raises:
        RuntimeError: 转换或编译失败，交由调用方降级为原文。
    """
    return _formula_cached(src, role, color or _ROLE_SPECS[role][1])


def render_expr(expr: object) -> bytes:
    """渲染数学表达式为透明底 PNG。

    底色不在这里合成：链出口的量化会把它铺到主题底色上，与其它产物同一条路。

    Args:
        expr: InlineExpr/BlockExpr 实例，含 expr 属性（不含 $ 分隔符）。

    Returns:
        渲染产物 PNG 字节串。
    """
    return formula_image(getattr(expr, "expr", "")).png
