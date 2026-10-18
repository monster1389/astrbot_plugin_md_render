"""数学表达式渲染。

用 Typst 渲染 LaTeX：先用 tylax 把 LaTeX 转成 Typst 语法，再编译成 PNG。
Typst 有完整排版引擎，``aligned`` 的 ``&`` 对齐、矩阵、``\\text{中文}``
都由引擎处理，不再靠替换表把命令改成 Unicode 字符。转换层已知的少量缺口
（``\\hbar``、``\\oint`` 粘词、``\\&``、``\\_``、``\\mathscr``）在转换前
后补齐；仍然转换或编译失败的直接抛给上层回退原文，不做静默替换。
"""
from __future__ import annotations

import re
from io import BytesIO

import tylax
import typst
from PIL import Image

from astrbot.api import logger
from render.font import find_font_spec, font_family, font_search_dir

# VS Code dark theme 配色
_FONT_COLOR = "#9CDCFE"
_BG_COLOR = "#1E1E1E"

# 独立公式图的留白；表格内嵌公式不留白，由表格排版加间距
_PAD = 10

# 旧接口的基准字号（像素），Typst 按 ppi 换算成 pt
_BASE_FONT_SIZE = 50
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

    Returns:
        (font_paths, 字体族列表)。系统字体不需要额外目录。
    """
    spec = find_font_spec()
    family = font_family(spec)
    search_dir = font_search_dir(spec)
    font_paths = [search_dir] if search_dir else []
    families = [family, _MATH_FONT] if family else [_MATH_FONT]
    if family is None:
        _warn_missing_font()
    return font_paths, families


def _document(body: str, color: str, size: int, families: list[str]) -> bytes:
    """拼出单条公式的 Typst 文档。

    Args:
        body: Typst 数学源码。
        color: 文字颜色，如 ``#9CDCFE``。
        size: 字号（像素），按 ppi 换算成 pt。
        families: 字体族回退列表。

    Returns:
        UTF-8 编码的 Typst 源文档。
    """
    font_list = ", ".join(f'"{name}"' for name in families)
    size_pt = size * 72 / _PPI
    # align* 等环境转换出来本身就是完整方程块，不能再包一层 $
    content = body if body.startswith("#math.equation") else f"$ {body} $"
    source = (
        "#set page(width: auto, height: auto, margin: 0pt, fill: none)\n"
        f'#set text(fill: rgb("{color}"), size: {size_pt:.2f}pt, font: ({font_list}))\n'
        f"{content}\n"
    )
    return source.encode()


def _compile(latex: str, *, color: str, size: int) -> bytes:
    """把 LaTeX 渲染成透明底 PNG 字节。

    Args:
        latex: 原始 LaTeX 源码（不含 $ 分隔符）。
        color: 文字颜色。
        size: 字号（像素）。

    Returns:
        PNG 字节串。

    Raises:
        RuntimeError: 转换或编译失败，交由上层降级为原文。
    """
    body = _to_typst(latex)
    font_paths, families = _font_setup()
    source = _document(body, color, size, families)
    try:
        return typst.compile(source, format="png", ppi=_PPI, font_paths=font_paths)
    except Exception as exc:
        raise RuntimeError(f"LaTeX 渲染失败：{latex[:120]}") from exc


def render_expr_image(src: str, *, color: str, size: int = _BASE_FONT_SIZE) -> Image.Image:
    """渲染 LaTeX 源码为指定文字颜色的透明底图像。

    Args:
        src: LaTeX 源码（不含 $ 分隔符）。
        color: 文字颜色，如 ``#9CDCFE``。
        size: 字号（像素）。

    Returns:
        RGBA 图像，背景透明。
    """
    png = _compile(src, color=color, size=size)
    with Image.open(BytesIO(png)) as image:
        return image.convert("RGBA")


def render_expr(expr: object) -> bytes:
    """渲染数学表达式为 PNG。

    公式以透明底生成，这里合成到配置的背景色上，确保 QQ 可正常显示。

    Args:
        expr: InlineExpr/BlockExpr 实例，含 expr 属性（不含 $ 分隔符）。

    Returns:
        渲染产物 PNG 字节串。
    """
    latex_src = getattr(expr, "expr", "")
    image = render_expr_image(latex_src, color=_FONT_COLOR)

    w, h = image.size
    result = Image.new("RGB", (w + _PAD * 2, h + _PAD * 2), _BG_COLOR)
    result.paste(image, (_PAD, _PAD), image)

    buf = BytesIO()
    result.save(buf, "PNG", optimize=True)
    return buf.getvalue()
