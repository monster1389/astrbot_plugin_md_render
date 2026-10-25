"""常驻文档的符号引用测试。

`CLAUDE.md` / `README.md` / `GLOSSARY.md` 描述的是「现在的世界」：里面点名的文件、
函数、类、常量都必须能在现在的仓库里找到。删掉一个符号时，「当时为什么不用它」
属于提交信息或 `docs/adr/`（只追加的历史）；留在常驻文档里就变成读者无从选择的
假话——代码里已经没有那个东西了。

`CHANGELOG.md` 与 `docs/adr/` 不在检查范围：它们本来就该记得已经删掉的东西。
新增一份「描述现状」的文档时，把文件名加进 `_DOCS`。
"""

from __future__ import annotations

import ast
import builtins
import re
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_DOCS = ("CLAUDE.md", "README.md", "GLOSSARY.md")
_SKIP_DIRS = {"data", "__pycache__", ".git"}

# 只查带扩展名的文件路径。目录与运行时路径（`temp/`、`data/plugins/`）不查：
# 它们由容器或 AstrBot 创建，仓库里本来就没有。
_PATH_RE = re.compile(r"^[\w./-]+\.(?:py|md|json|toml|yaml|yml|sh|png|jpg|txt)$")
# 反引号里的名字：允许 @装饰器 与尾随 ()。
_NAME_RE = re.compile(r"^@?([A-Za-z_][A-Za-z0-9_]*)(?:\(\))?$")
_SPAN_RE = re.compile(r"`([^`\n]+)`")
# 正文里的 @装饰器（这类提法常常不套反引号）
_DECORATOR_RE = re.compile(r"@([A-Za-z_][A-Za-z0-9_]*)")
# 文档里的模板占位符：`tests/test_xxx.py`、`<plugin>/skills/…`
_PLACEHOLDER_RE = re.compile(r"[<>]|xxx")

# 文档合法点名、但不由本仓库定义的符号。每条都要写清它属于谁。
_EXTERNAL = {
    "OnDecoratingResultEvent": "AstrBot 的钩子名",
    "ls": "命令行工具",
    "_Avoid_": "GLOSSARY 词条格式约定",
    "description": "SKILL.md frontmatter 字段，AstrBot 读",
    "aligned": "LaTeX/Typst 的环境名",
}

# markdown 语法示意里出现的词，不是项目的符号。
_MARKDOWN_SYNTAX = {
    "item": "README 清洗表「变成什么」列的示意",
    "___": "分隔线的另一种写法",
}


def _sources() -> list[Path]:
    """仓库自己的 Python 文件，跳过运行时数据与缓存。

    Returns:
        `*.py` 路径列表。
    """
    return [
        path
        for path in _ROOT.rglob("*.py")
        if not _SKIP_DIRS & set(path.relative_to(_ROOT).parts)
    ]


def _python_symbols() -> set[str]:
    """收集仓库 Python 里出现过的名字。

    定义、参数、赋值目标、导入别名、属性、关键字参数都算：文档会点名
    `STREAMING_FINISH` 这类跨仓库属性，它在本仓库里只以属性名出现。内建名一并
    放进集合——`ValueError` 不是本仓库的符号，但文档提到它不算错。

    Returns:
        名字集合。
    """
    names = set(dir(builtins))
    for path in _sources():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Name, ast.arg)):
                names.add(node.id if isinstance(node, ast.Name) else node.arg)
            elif isinstance(node, ast.Attribute):
                # 只认读取：`obj.attr = x` 是给别人的桩对象补属性，不证明这个名字还在
                if isinstance(node.ctx, ast.Load):
                    names.add(node.attr)
            elif isinstance(node, ast.keyword):
                if node.arg:
                    names.add(node.arg)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names.add(node.name)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    names.add((alias.asname or alias.name).split(".")[0])
    return names


def _mentions(text: str) -> list[tuple[int, str]]:
    """逐行抽出文档点名的片段候选。

    Args:
        text: 文档全文。

    Returns:
        (行号, 片段) 列表，去重并保持文档顺序。
    """
    found: dict[tuple[int, str], None] = {}
    for lineno, line in enumerate(text.splitlines(), 1):
        for span in _SPAN_RE.findall(line):
            found[(lineno, span.strip())] = None
        for name in _DECORATOR_RE.findall(line):
            found[(lineno, f"@{name}")] = None
    return list(found)


def _unresolved(doc: Path, symbols: set[str]) -> list[str]:
    """列出文档里指向不存在目标的点名。

    Args:
        doc: 文档路径。
        symbols: 仓库里出现过的 Python 名字。

    Returns:
        可直接打印的问题描述列表。
    """
    problems = []
    for lineno, span in _mentions(doc.read_text(encoding="utf-8")):
        name = _NAME_RE.match(span)
        if name:
            ident = name.group(1)
            if ident in symbols or ident in _EXTERNAL or ident in _MARKDOWN_SYNTAX:
                continue
            problems.append(f"{doc.name}:{lineno} `{span}` —— 代码里没有这个名字")
        elif _PATH_RE.match(span) and not _PLACEHOLDER_RE.search(span):
            if not (_ROOT / span).exists():
                problems.append(f"{doc.name}:{lineno} `{span}` —— 文件不存在")
    return problems


@pytest.fixture(scope="module", name="symbols")
def _symbol_fixture() -> set[str]:
    """仓库里出现过的 Python 名字。"""
    return _python_symbols()


@pytest.mark.parametrize("doc", _DOCS)
def test_docs_name_only_existing_symbols(doc: str, symbols: set[str]) -> None:
    """常驻文档点名的文件与符号必须还存在。"""
    problems = _unresolved(_ROOT / doc, symbols)
    assert not problems, (
        f"{doc} 点名的东西在现在的代码里找不到：\n\n"
        + "\n".join(f"  {problem}" for problem in problems)
        + "\n\n删掉那句；「当时为什么不用它」写进提交信息或 docs/adr/。"
    )


def test_exception_list_has_no_sediment(symbols: set[str]) -> None:
    """例外表的每一条都必须仍被文档引用、且没有盖住真实符号。"""
    mentioned = {
        span for doc in _DOCS for _, span in _mentions((_ROOT / doc).read_text(encoding="utf-8"))
    }
    allowed = set(_EXTERNAL) | set(_MARKDOWN_SYNTAX)
    assert not allowed - mentioned, (
        "这些例外已经没被任何文档引用，删掉：\n  "
        + "\n  ".join(sorted(allowed - mentioned))
    )
    shadowed = sorted(allowed & symbols)
    assert not shadowed, (
        "这些例外其实已经在代码里，会挡住真实检查，删掉：\n  " + "\n  ".join(shadowed)
    )
