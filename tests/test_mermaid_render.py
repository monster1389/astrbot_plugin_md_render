"""Mermaid 渲染测试（mermaid.ink，httpx 打桩）。"""
import asyncio
import base64
from unittest.mock import AsyncMock, MagicMock, patch

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


def _client() -> MagicMock:
    """异步 client 打桩：get 是可等待的 AsyncMock。"""
    client = MagicMock()
    client.get = AsyncMock()
    return client


def _render(seg: MermaidBlock) -> bytes:
    return asyncio.run(render_mermaid(seg))


class TestBuildUrl:
    def test_payload_is_urlsafe_base64(self):
        url = build_url("graph LR\n  A-->B")
        payload = url.split("/img/")[1].split("?")[0]
        assert base64.urlsafe_b64decode(payload).decode() == "graph LR\n  A-->B"
        assert "type=png" in url
        assert "theme=dark" in url


class TestRenderMermaid:
    def test_success(self):
        client = _client()
        client.get.return_value = _response(200)
        with patch("render.mermaid_render._client", client):
            assert _render(MermaidBlock(code="graph LR")) == _PNG
        assert client.get.call_count == 1

    @patch("render.mermaid_render.asyncio.sleep", new_callable=AsyncMock)
    def test_retries_on_5xx(self, _sleep):
        client = _client()
        client.get.side_effect = [_response(503, b"busy"), _response(200)]
        with patch("render.mermaid_render._client", client):
            assert _render(MermaidBlock(code="graph LR")) == _PNG
        assert client.get.call_count == 2

    def test_no_retry_on_4xx(self):
        client = _client()
        client.get.return_value = _response(400, b"bad syntax")
        with patch("render.mermaid_render._client", client), pytest.raises(RuntimeError):
            _render(MermaidBlock(code="bad"))
        assert client.get.call_count == 1

    @patch("render.mermaid_render.asyncio.sleep", new_callable=AsyncMock)
    def test_raises_after_two_timeouts(self, _sleep):
        client = _client()
        client.get.side_effect = httpx.ReadTimeout("slow")
        with patch("render.mermaid_render._client", client), pytest.raises(httpx.HTTPError):
            _render(MermaidBlock(code="graph LR"))
        assert client.get.call_count == 2

    def test_non_png_body_is_error(self):
        client = _client()
        client.get.return_value = _response(200, b"<html>oops</html>")
        with patch("render.mermaid_render._client", client), pytest.raises(RuntimeError):
            _render(MermaidBlock(code="graph LR"))
