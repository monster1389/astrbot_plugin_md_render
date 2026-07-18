"""Markdown 格式清洗。

用 markdown-it-py 解析 token 流，按配置开关去除对应格式标记。
"""
from __future__ import annotations

from markdown_it import MarkdownIt
from markdown_it.token import Token

from render.utils import CleanConfig


def clean_markdown(text: str, cfg: CleanConfig) -> str:
    """清洗 markdown 格式标记，按配置开关逐项处理。

    Args:
        text: 待清洗的 markdown 文本。
        cfg: 清洗配置。

    Returns:
        清洗后的纯文本。
    """
    if not text:
        return ""

    flags = vars(cfg)
    if not any(flags.values()):
        return text

    rules: list[str] = []
    if flags["bold"] or flags["italic"]:
        rules.append("emphasis")
    if flags["strikethrough"]:
        rules.append("strikethrough")
    if flags["inline_code"]:
        rules.append("backticks")
    if flags["link"] or flags["image"]:
        rules.append("link")
    if flags["image"]:
        rules.append("image")
    if flags["heading"]:
        rules.append("heading")
    if flags["list_unordered"] or flags["list_ordered"]:
        rules.append("list")
    if flags["blockquote"]:
        rules.append("blockquote")

    md = MarkdownIt("zero").enable(rules)
    md.options["html"] = False
    tokens = md.parse(text)

    return _walk(tokens, cfg, None)


def _walk(tokens: list[Token], cfg: CleanConfig, parent_type: str | None) -> str:
    """递归遍历 token 列表，拼接清洗后文本。"""
    parts: list[str] = []
    link_href: str = ""
    list_counter: int = 0

    i = 0
    while i < len(tokens):
        t = tokens[i]

        if t.type == "inline" and t.children:
            parts.append(_walk_inline(t.children, cfg))
        elif t.type == "text":
            parts.append(t.content)
        elif t.type == "fence":
            parts.append(f"```{t.info}\n{t.content}\n```" if t.info else f"```\n{t.content}\n```")
        elif t.type == "code_block":
            parts.append(t.content)
        elif t.type == "code_inline":
            if cfg.inline_code:
                parts.append(t.content)
            else:
                parts.append(f"`{t.content}`")

        elif t.type in ("heading_open", "heading_close"):
            if not cfg.heading:
                parts.append(t.markup)
        elif t.type == "blockquote_open":
            if not cfg.blockquote:
                parts.append("> ")
        elif t.type == "blockquote_close":
            if not cfg.blockquote:
                parts.append("")

        elif t.type == "bullet_list_open":
            if not cfg.list_unordered:
                parent_type = "bullet_list"
            else:
                parent_type = None
        elif t.type == "bullet_list_close":
            parent_type = None
        elif t.type == "ordered_list_open":
            if not cfg.list_ordered:
                parent_type = "ordered_list"
                list_counter = 0
            else:
                parent_type = None
        elif t.type == "ordered_list_close":
            parent_type = None
        elif t.type == "list_item_open":
            if parent_type == "bullet_list":
                parts.append("- ")
            elif parent_type == "ordered_list":
                list_counter += 1
                parts.append(f"{t.info or str(list_counter)}. ")
        elif t.type == "list_item_close":
            if parent_type is not None and i + 1 < len(tokens) and tokens[i + 1].type == "list_item_open":
                parts.append("\n")

        elif t.type == "paragraph_open":
            pass
        elif t.type == "paragraph_close":
            if i + 1 < len(tokens) and tokens[i + 1].type not in (
                "heading_close", "blockquote_close", "list_item_close",
                "bullet_list_close", "ordered_list_close", "paragraph_close",
            ):
                parts.append("\n\n")
        elif t.type == "hardbreak":
            parts.append("\n")
        elif t.type == "softbreak":
            parts.append("\n")

        elif t.type == "hr":
            parts.append("---")
        elif t.type == "image":
            if cfg.image:
                alt = t.content or ""
                src = t.attrs.get("src", "") if t.attrs else ""
                if alt and src:
                    parts.append(f"{alt} ({src})")
                elif src:
                    parts.append(f"({src})")
                elif alt:
                    parts.append(alt)
            else:
                alt = t.content or ""
                src = t.attrs.get("src", "") if t.attrs else ""
                parts.append(f"![{alt}]({src})")
        elif t.type == "link_open":
            link_href = t.attrs.get("href", "") if t.attrs else ""
        elif t.type == "link_close":
            if cfg.link and link_href:
                parts.append(f" ({link_href})")
            link_href = ""

        elif t.type == "html_block":
            parts.append(t.content)

        i += 1

    return "".join(parts)


def _walk_inline(children: list[Token], cfg: CleanConfig) -> str:
    """处理 inline token 的子节点。"""
    parts: list[str] = []
    link_href: str = ""

    for t in children:
        if t.type == "text":
            parts.append(t.content)
        elif t.type == "strong_open":
            if cfg.bold:
                pass
            else:
                parts.append(t.markup)
        elif t.type == "strong_close":
            if cfg.bold:
                pass
            else:
                parts.append(t.markup)
        elif t.type == "em_open":
            if cfg.italic:
                pass
            else:
                parts.append(t.markup)
        elif t.type == "em_close":
            if cfg.italic:
                pass
            else:
                parts.append(t.markup)
        elif t.type == "s_open":
            if cfg.strikethrough:
                pass
            else:
                parts.append(t.markup)
        elif t.type == "s_close":
            if cfg.strikethrough:
                pass
            else:
                parts.append(t.markup)
        elif t.type == "code_inline":
            if cfg.inline_code:
                parts.append(t.content)
            else:
                parts.append(f"`{t.content}`")
        elif t.type == "link_open":
            link_href = t.attrs.get("href", "") if t.attrs else ""
            if not cfg.link:
                parts.append("[")
        elif t.type == "link_close":
            if cfg.link:
                parts.append(f" ({link_href})")
            else:
                parts.append(f"]({link_href})")
            link_href = ""
        elif t.type == "image":
            alt = t.content or ""
            src = t.attrs.get("src", "") if t.attrs else ""
            if cfg.image:
                if alt and src:
                    parts.append(f"{alt} ({src})")
                elif src:
                    parts.append(f"({src})")
                elif alt:
                    parts.append(alt)
            else:
                parts.append(f"![{alt}]({src})")
        elif t.type == "softbreak":
            parts.append("\n")
        elif t.type == "hardbreak":
            parts.append("\n")
        elif t.type == "html_inline":
            parts.append(t.content)
        else:
            if t.content:
                parts.append(t.content)
            elif hasattr(t, "markup") and t.markup:
                parts.append(t.markup)

    return "".join(parts)
