"""Mermaid 渲染测试（mermaid.ink，httpx 打桩）。"""
import asyncio
import base64
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from render import mermaid_render
from render.parser import MermaidBlock

_PNG = b"\x89PNG\r\n\x1a\nfake"


def _response(status: int, content: bytes = _PNG) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status
    resp.content = content
    return resp


def _client_double() -> MagicMock:
    """异步 client 打桩：get 是可等待的 AsyncMock。"""
    client = MagicMock()
    client.get = AsyncMock()
    return client


def _render(seg: MermaidBlock) -> bytes:
    return asyncio.run(mermaid_render.render_mermaid(seg))


class TestBuildUrl:
    def test_payload_is_urlsafe_base64(self):
        url = mermaid_render.build_url("graph LR\n  A-->B")
        payload = url.split("/img/")[1].split("?")[0]
        assert base64.urlsafe_b64decode(payload).decode() == "graph LR\n  A-->B"
        assert "type=png" in url
        assert "theme=dark" in url


class TestRenderMermaid:
    def test_success(self):
        client = _client_double()
        client.get.return_value = _response(200)
        with patch("render.mermaid_render._client", client):
            assert _render(MermaidBlock(code="graph LR")) == _PNG
        assert client.get.call_count == 1

    @patch("render.mermaid_render.asyncio.sleep", new_callable=AsyncMock)
    def test_retries_on_5xx(self, _sleep):
        client = _client_double()
        client.get.side_effect = [_response(503, b"busy"), _response(200)]
        with patch("render.mermaid_render._client", client):
            assert _render(MermaidBlock(code="graph LR")) == _PNG
        assert client.get.call_count == 2

    def test_no_retry_on_4xx(self):
        client = _client_double()
        client.get.return_value = _response(400, b"bad syntax")
        with patch("render.mermaid_render._client", client), pytest.raises(RuntimeError):
            _render(MermaidBlock(code="bad"))
        assert client.get.call_count == 1

    @patch("render.mermaid_render.asyncio.sleep", new_callable=AsyncMock)
    def test_raises_after_two_timeouts(self, _sleep):
        client = _client_double()
        client.get.side_effect = httpx.ReadTimeout("slow")
        with patch("render.mermaid_render._client", client), pytest.raises(httpx.HTTPError):
            _render(MermaidBlock(code="graph LR"))
        assert client.get.call_count == 2

    @patch("render.mermaid_render.asyncio.sleep", new_callable=AsyncMock)
    def test_raises_after_two_5xx(self, _sleep):
        client = _client_double()
        client.get.return_value = _response(503, b"busy")
        with patch("render.mermaid_render._client", client), pytest.raises(RuntimeError):
            _render(MermaidBlock(code="graph LR"))
        assert client.get.call_count == 2

    def test_non_png_200_is_not_retried(self):
        client = _client_double()
        client.get.return_value = _response(200, b"<html>oops</html>")
        with patch("render.mermaid_render._client", client), pytest.raises(RuntimeError):
            _render(MermaidBlock(code="graph LR"))
        assert client.get.call_count == 1

    def test_timeout_budget_is_ten_seconds(self):
        assert mermaid_render._TIMEOUT == 10.0
        assert mermaid_render._client.timeout.connect == 10.0


class TestChannel:
    def test_requests_are_serialized(self):
        """并发提交时进程内只允许一个请求在飞（mermaid.ink 拒并发）。"""
        peak = 0
        in_flight = 0

        async def get(_url):
            nonlocal peak, in_flight
            in_flight += 1
            peak = max(peak, in_flight)
            await asyncio.sleep(0.01)
            in_flight -= 1
            return _response(200)

        client = MagicMock()
        client.get = get
        segs = [MermaidBlock(code=f"graph LR\n  A{i}-->B") for i in range(3)]

        async def run_all():
            return await asyncio.gather(*(mermaid_render.render_mermaid(s) for s in segs))

        with patch("render.mermaid_render._client", client):
            results = asyncio.run(run_all())
        assert results == [_PNG] * 3
        assert peak == 1

    def test_channel_rebuilds_when_loop_changes(self):
        """每个 asyncio.run 都是新事件循环，通道锁必须跟着重建。"""
        client = _client_double()
        client.get.return_value = _response(200)
        with patch("render.mermaid_render._client", client):
            assert _render(MermaidBlock(code="graph LR")) == _PNG
            assert _render(MermaidBlock(code="graph LR")) == _PNG
        assert client.get.call_count == 2
