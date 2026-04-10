from __future__ import annotations

from urllib import error

from optulus_sdk.exporters import HttpTelemetryExporter
from optulus_sdk.telemetry import new_event


class _Response:
    def __init__(self, status: int) -> None:
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_http_exporter_sets_auth_and_succeeds(monkeypatch) -> None:
    captured = {}

    def _fake_urlopen(req, timeout):
        captured["authorization"] = req.get_header("Authorization")
        captured["timeout"] = timeout
        return _Response(202)

    monkeypatch.setattr("optulus_sdk.exporters.request.urlopen", _fake_urlopen)
    exporter = HttpTelemetryExporter(
        api_key="secret",
        timeout_ms=1500,
        max_retries=0,
    )

    result = exporter.export([new_event("tool_call", {"tool_name": "weather"})])
    assert result.success is True
    assert captured["authorization"] == "Bearer secret"
    assert captured["timeout"] == 1.5


def test_http_exporter_retries_transient_errors(monkeypatch) -> None:
    calls = {"count": 0}

    def _fake_urlopen(req, timeout):
        calls["count"] += 1
        if calls["count"] < 3:
            raise error.HTTPError(req.full_url, 429, "rate limited", hdrs=None, fp=None)
        return _Response(200)

    monkeypatch.setattr("optulus_sdk.exporters.request.urlopen", _fake_urlopen)
    exporter = HttpTelemetryExporter(
        max_retries=3,
        backoff_base_ms=1,
    )

    result = exporter.export([new_event("tool_call", {"tool_name": "weather"})])
    assert result.success is True
    assert calls["count"] == 3
