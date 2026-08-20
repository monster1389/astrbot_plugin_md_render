"""行内格式状态机 —— markdown-it inline children 的格式态跟踪。

表格解析（table_domain）与格式清洗（md_cleaner）都在遍历 inline 子节点时
维护「当前加粗/斜体/删除线/链接」状态，本模块是这份切换逻辑的唯一出处。

约定：调用方在循环体**末尾**调用 advance(state, t)。这样处理每个 token 时
state 反映的是该 token 之前的格式态；link_close 需要读到 href，而 href 由
link_open 的 advance 设置，若在循环开头推进则已被清空。
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from markdown_it.token import Token


@dataclass(frozen=True)
class FormatState:
    """当前行内格式态。

    Attributes:
        bold: 是否处于加粗。
        italic: 是否处于斜体。
        strike: 是否处于删除线。
        link_url: 当前链接 href，空串表示不在链接内。
    """
    bold: bool = False
    italic: bool = False
    strike: bool = False
    link_url: str = ""


def advance(state: FormatState, token: Token) -> FormatState:
    """按 token 类型推进格式态：strong/em/s/link 的开与关。

    Args:
        state: 当前格式态。
        token: 当前遍历到的 inline 子节点。

    Returns:
        推进后的格式态；非格式切换 token 原样返回。
    """
    if token.type == "strong_open":
        return replace(state, bold=True)
    if token.type == "strong_close":
        return replace(state, bold=False)
    if token.type == "em_open":
        return replace(state, italic=True)
    if token.type == "em_close":
        return replace(state, italic=False)
    if token.type == "s_open":
        return replace(state, strike=True)
    if token.type == "s_close":
        return replace(state, strike=False)
    if token.type == "link_open":
        return replace(state, link_url=(token.attrs or {}).get("href", ""))
    if token.type == "link_close":
        return replace(state, link_url="")
    return state
