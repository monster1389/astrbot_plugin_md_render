"""Mermaid 渲染测试（mermaid.ink，httpx 打桩）。"""
import base64
from unittest.mock import MagicMock, patch

import httpx
import pytest

from render.mermaid_render import build_url, render_mermaid
from render.parser import MermaidBlock

_PNG = b"\x89PNG\r\n\x1a\nfake"


def _response(status: int, content: bytes = _PNG) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status
    resp.content = content
    return resp


class TestBuildUrl:
    def test_payload_is_urlsafe_base64(self):
        url = build_url("graph LR\n  A-->B")
        payload = url.split("/img/")[1].split("?")[0]
        assert base64.urlsafe_b64decode(payload).decode() == "graph LR\n  A-->B"
        assert "type=png" in url
        assert "theme=dark" in url


class TestRenderMermaid:
    @patch("render.mermaid_render._client")
    def test_success(self, client):
        client.get.return_value = _response(200)
        png = render_mermaid(MermaidBlock(code="graph LR"))
        assert png == _PNG
        assert client.get.call_count == 1

    @patch("render.mermaid_render.time.sleep")
    @patch("render.mermaid_render._client")
    def test_retries_on_5xx(self, client, _sleep):
        client.get.side_effect = [_response(503, b"busy"), _response(200)]
        assert render_mermaid(MermaidBlock(code="graph LR")) == _PNG
        assert client.get.call_count == 2

    @patch("render.mermaid_render._client")
    def test_no_retry_on_4xx(self, client):
        client.get.return_value = _response(400, b"bad syntax")
        with pytest.raises(RuntimeError):
            render_mermaid(MermaidBlock(code="bad"))
        assert client.get.call_count == 1

    @patch("render.mermaid_render.time.sleep")
    @patch("render.mermaid_render._client")
    def test_raises_after_two_timeouts(self, client, _sleep):
        client.get.side_effect = httpx.ReadTimeout("slow")
        with pytest.raises(httpx.HTTPError):
            render_mermaid(MermaidBlock(code="graph LR"))
        assert client.get.call_count == 2

    @patch("render.mermaid_render._client")
    def test_non_png_body_is_error(self, client):
        client.get.return_value = _response(200, b"<html>oops</html>")
        with pytest.raises(RuntimeError):
            render_mermaid(MermaidBlock(code="graph LR"))
