"""行内格式状态机测试。"""
from markdown_it.token import Token

from render.inline_format import FormatState, advance


def _token(type: str, attrs: dict | None = None) -> Token:
    tok = Token(type, type, 0)
    tok.attrs = attrs
    return tok


class TestAdvance:
    def test_strong_toggle(self):
        state = advance(FormatState(), _token("strong_open"))
        assert state.bold is True
        state = advance(state, _token("strong_close"))
        assert state.bold is False

    def test_em_toggle(self):
        state = advance(FormatState(), _token("em_open"))
        assert state.italic is True
        state = advance(state, _token("em_close"))
        assert state.italic is False

    def test_s_toggle(self):
        state = advance(FormatState(), _token("s_open"))
        assert state.strike is True
        state = advance(state, _token("s_close"))
        assert state.strike is False

    def test_link_open_sets_href(self):
        state = advance(FormatState(), _token("link_open", {"href": "https://x.com"}))
        assert state.link_url == "https://x.com"

    def test_link_open_without_attrs(self):
        state = advance(FormatState(), _token("link_open"))
        assert state.link_url == ""

    def test_link_close_clears_href(self):
        state = advance(FormatState(), _token("link_open", {"href": "u"}))
        state = advance(state, _token("link_close"))
        assert state.link_url == ""

    def test_unrelated_token_unchanged(self):
        state = FormatState(bold=True, italic=True, strike=True, link_url="u")
        assert advance(state, _token("text")) is state
        assert advance(state, _token("code_inline")) is state


class TestAdvanceAtBottom:
    """约定：调用方在循环体末尾 advance，处理 token 时 state 反映该 token 之前的格式态。"""

    def _walk(self, tokens: list[Token]) -> list[tuple[str, FormatState]]:
        state = FormatState()
        seen: list[tuple[str, FormatState]] = []
        for t in tokens:
            seen.append((t.type, state))
            state = advance(state, t)
        return seen

    def test_bold_visible_before_close(self):
        seen = self._walk([_token("strong_open"), _token("text"), _token("strong_close")])
        assert seen[0][1].bold is False
        assert seen[1][1].bold is True
        assert seen[2][1].bold is True

    def test_link_href_readable_at_close(self):
        tokens = [_token("link_open", {"href": "https://x.com"}), _token("text"), _token("link_close")]
        seen = self._walk(tokens)
        assert seen[0][1].link_url == ""
        assert seen[1][1].link_url == "https://x.com"
        assert seen[2][1].link_url == "https://x.com"

    def test_link_url_cleared_after_close(self):
        tokens = [
            _token("link_open", {"href": "u"}),
            _token("text"),
            _token("link_close"),
            _token("text"),
        ]
        seen = self._walk(tokens)
        assert seen[-1][1].link_url == ""
