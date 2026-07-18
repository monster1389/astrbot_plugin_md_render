"""md_cleaner 测试。"""
from __future__ import annotations

from render.clean.md_cleaner import clean_markdown
from render.utils import CleanConfig


def _cfg(**overrides) -> CleanConfig:
    defaults = {k: True for k in vars(CleanConfig())}
    defaults.update(overrides)
    return CleanConfig(**defaults)


class TestCleanAllOn:
    def test_clean_bold(self):
        assert clean_markdown("**加粗**", _cfg()) == "加粗"

    def test_clean_italic(self):
        assert clean_markdown("*斜体*", _cfg()) == "斜体"

    def test_clean_underscore_italic(self):
        assert clean_markdown("_斜体_", _cfg()) == "斜体"

    def test_clean_strikethrough(self):
        assert clean_markdown("~~删除~~", _cfg()) == "删除"

    def test_clean_inline_code(self):
        assert clean_markdown("`code`", _cfg()) == "code"

    def test_clean_link(self):
        assert clean_markdown("[文档](https://x.com)", _cfg()) == "文档 (https://x.com)"

    def test_clean_image_with_alt(self):
        assert clean_markdown("![logo](https://x.com/img.png)", _cfg()) == "logo (https://x.com/img.png)"

    def test_clean_image_no_alt(self):
        assert clean_markdown("![](https://x.com/img.png)", _cfg()) == "(https://x.com/img.png)"

    def test_clean_heading_h1(self):
        assert clean_markdown("# 标题", _cfg()) == "标题"

    def test_clean_heading_h2(self):
        assert clean_markdown("## 二级标题", _cfg()) == "二级标题"

    def test_clean_heading_h3(self):
        assert clean_markdown("### 三级标题", _cfg()) == "三级标题"

    def test_clean_unordered_list(self):
        assert clean_markdown("- 项目", _cfg()) == "项目"

    def test_clean_ordered_list(self):
        assert clean_markdown("1. 第一", _cfg()) == "第一"

    def test_clean_blockquote(self):
        assert clean_markdown("> 引用", _cfg()) == "引用"

    def test_clean_mixed_format(self):
        text = "**粗体** 和 *斜体* 和 ~~删除~~ 和 `代码`"
        result = clean_markdown(text, _cfg())
        assert result == "粗体 和 斜体 和 删除 和 代码"

    def test_plain_text_passthrough(self):
        assert clean_markdown("普通文本", _cfg()) == "普通文本"

    def test_empty_text(self):
        assert clean_markdown("", _cfg()) == ""


class TestKaomojiSafe:
    def test_kaomoji_with_star_not_stripped(self):
        result = clean_markdown("**粗体**(￣▽￣*)", _cfg())
        assert result == "粗体(￣▽￣*)"

    def test_kaomoji_with_underscore(self):
        result = clean_markdown("(｀・ω・´)b", _cfg())
        assert result == "(｀・ω・´)b"

    def test_kaomoji_with_tilde(self):
        result = clean_markdown("(。-´ω´-)", _cfg())
        assert result == "(。-´ω´-)"


class TestPartialClean:
    def test_bold_off_keeps_markup(self):
        result = clean_markdown("**加粗** *斜体*", _cfg(bold=False))
        assert result == "**加粗** 斜体"

    def test_italic_off_keeps_markup(self):
        result = clean_markdown("**加粗** *斜体*", _cfg(italic=False))
        assert result == "加粗 *斜体*"

    def test_unordered_off_ordered_on(self):
        result = clean_markdown("- 无序\n1. 有序", _cfg(list_unordered=False, list_ordered=True))
        assert "- 无序" in result
        assert "有序" in result
        assert "1." not in result

    def test_ordered_off_unordered_on(self):
        result = clean_markdown("- 无序\n1. 有序", _cfg(list_unordered=True, list_ordered=False))
        assert "无序" in result
        assert "- " not in result
        assert "1. 有序" in result

    def test_all_off_returns_original(self):
        text = "**粗体** *斜体* ~~删除~~ `代码` [链接](x)"
        assert clean_markdown(text, _cfg(
            bold=False, italic=False, strikethrough=False,
            inline_code=False, link=False,
        )) == text


class TestEdgeCases:
    def test_unclosed_marker_preserved(self):
        result = clean_markdown("**没闭合", _cfg())
        assert result == "**没闭合"

    def test_nested_format(self):
        result = clean_markdown("**粗体*斜体*混排**", _cfg())
        assert result == "粗体斜体混排"

    def test_multiline(self):
        text = "# 标题\n\n**粗体** 内容\n\n- 列表1\n- 列表2"
        result = clean_markdown(text, _cfg())
        assert "标题" in result
        assert "粗体" in result
        assert "列表1" in result
        assert "#" not in result
        assert "**" not in result
