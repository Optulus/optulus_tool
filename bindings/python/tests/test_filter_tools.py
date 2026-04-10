from __future__ import annotations

import pytest

from optulus_sdk.embeddings import HashedEmbeddingProvider
from optulus_sdk.filtering import bind_tools, filter_tools
from optulus_sdk.telemetry import ExportResult, TelemetryConfig, TelemetryRecorder


def weather_tool(city: str) -> str:
    """Get weather forecast for a city."""
    return city


def stocks_tool(symbol: str) -> str:
    """Get latest stock price quote."""
    return symbol


class DummyLLM:
    def __init__(self) -> None:
        self.bound_tools = None

    def bind_tools(self, tools):
        self.bound_tools = tools
        return {"bound_tools": tools}


def test_filter_tools_returns_original_objects(tmp_path) -> None:
    db_path = tmp_path / "registry.db"
    provider = HashedEmbeddingProvider(dimensions=128)
    dict_tool = {
        "name": "calendar_events",
        "description": "Read a user's calendar events",
        "input_schema": {"type": "object"},
    }
    tools = [dict_tool, weather_tool, stocks_tool]

    selected = filter_tools(
        tools,
        context="need weather update for tomorrow",
        max_tools=2,
        budget_tokens=2000,
        db_path=db_path,
        embedding_provider=provider,
    )

    assert len(selected) == 2
    assert weather_tool in selected
    assert any(tool is weather_tool for tool in selected)


def test_filter_tools_respects_budget(tmp_path) -> None:
    db_path = tmp_path / "registry.db"
    provider = HashedEmbeddingProvider(dimensions=128)
    tools = [
        {
            "name": "heavy_tool",
            "description": " ".join(["large"] * 400),
            "input_schema": {"type": "object"},
        },
        {
            "name": "light_tool",
            "description": "small",
            "input_schema": {"type": "object"},
        },
    ]

    selected = filter_tools(
        tools,
        context="small task",
        max_tools=2,
        budget_tokens=10,
        db_path=db_path,
        embedding_provider=provider,
    )

    assert len(selected) == 1
    assert selected[0]["name"] == "light_tool"


def test_filter_tools_always_includes_pinned(tmp_path) -> None:
    db_path = tmp_path / "registry.db"
    provider = HashedEmbeddingProvider(dimensions=128)
    tools = [
        {
            "name": "debug_logs",
            "description": "very verbose diagnostics collector",
            "input_schema": {"type": "object"},
        },
        {
            "name": "weather_lookup",
            "description": "forecast and temperature for a city",
            "input_schema": {"type": "object"},
        },
    ]

    selected = filter_tools(
        tools,
        context="what is weather tomorrow",
        max_tools=1,
        budget_tokens=1,
        pinned=["debug_logs"],
        db_path=db_path,
        embedding_provider=provider,
    )

    names = [tool["name"] for tool in selected]
    assert "debug_logs" in names


def test_filter_tools_is_deterministic_for_ties(tmp_path) -> None:
    db_path = tmp_path / "registry.db"
    provider = HashedEmbeddingProvider(dimensions=1)
    tools = [
        {"name": "tool_a", "description": "same", "input_schema": {"type": "object"}},
        {"name": "tool_b", "description": "same", "input_schema": {"type": "object"}},
        {"name": "tool_c", "description": "same", "input_schema": {"type": "object"}},
    ]

    first = filter_tools(
        tools,
        context="same",
        max_tools=2,
        budget_tokens=1000,
        db_path=db_path,
        embedding_provider=provider,
    )
    second = filter_tools(
        tools,
        context="same",
        max_tools=2,
        budget_tokens=1000,
        db_path=db_path,
        embedding_provider=provider,
    )
    assert [tool["name"] for tool in first] == [tool["name"] for tool in second]


def test_bind_tools_filters_and_binds(tmp_path) -> None:
    db_path = tmp_path / "registry.db"
    provider = HashedEmbeddingProvider(dimensions=128)
    llm = DummyLLM()
    tools = [
        {
            "name": "weather_lookup",
            "description": "Get weather forecast",
            "input_schema": {"type": "object"},
        },
        {
            "name": "heavy_debug_tool",
            "description": " ".join(["debug"] * 300),
            "input_schema": {"type": "object"},
        },
    ]

    result = bind_tools(
        llm,
        tools,
        context="weather tomorrow",
        max_tools=1,
        budget_tokens=20,
        db_path=db_path,
        embedding_provider=provider,
    )

    assert llm.bound_tools is not None
    assert len(llm.bound_tools) == 1
    assert llm.bound_tools[0]["name"] == "weather_lookup"
    assert result["bound_tools"][0]["name"] == "weather_lookup"


def test_bind_tools_emits_selection_metrics(tmp_path) -> None:
    db_path = tmp_path / "registry.db"
    provider = HashedEmbeddingProvider(dimensions=128)
    llm = DummyLLM()
    tools = [
        {
            "name": "weather_lookup",
            "description": "Get weather forecast",
            "input_schema": {"type": "object"},
        },
        {
            "name": "heavy_debug_tool",
            "description": " ".join(["debug"] * 300),
            "input_schema": {"type": "object"},
        },
    ]
    result = bind_tools(
        llm,
        tools,
        context="weather tomorrow",
        max_tools=1,
        budget_tokens=20,
        db_path=db_path,
        embedding_provider=provider,
    )
    assert result["bound_tools"][0]["name"] == "weather_lookup"


class _NoopTelemetryExporter:
    def export(self, events):
        return ExportResult(success=True, attempts=1, status_code=200)


def test_bind_tools_logs_selection_when_enabled(tmp_path, caplog) -> None:
    db_path = tmp_path / "registry.db"
    provider = HashedEmbeddingProvider(dimensions=128)
    llm = DummyLLM()
    tools = [
        {
            "name": "weather_lookup",
            "description": "Get weather forecast",
            "input_schema": {"type": "object"},
        },
        {
            "name": "heavy_debug_tool",
            "description": " ".join(["debug"] * 300),
            "input_schema": {"type": "object"},
        },
    ]

    recorder = TelemetryRecorder(
        _NoopTelemetryExporter(),
        config=TelemetryConfig(enabled=True, flush_interval_ms=10_000, max_batch_size=100),
    )
    recorder.start()
    try:
        with caplog.at_level("INFO"):
            bind_tools(
                llm,
                tools,
                context="weather tomorrow",
                max_tools=1,
                budget_tokens=20,
                db_path=db_path,
                embedding_provider=provider,
                logging_enabled=True,
                telemetry_recorder=recorder,
            )
    finally:
        recorder.stop(flush=True)

    logs = "\n".join(caplog.messages)
    assert "Tool selection:" in logs
    assert "TELEMETRY tool_selection" in logs


def test_filter_tools_accepts_langchain_structured_tool(tmp_path) -> None:
    pytest.importorskip("langchain_core.tools")
    from langchain_core.tools import tool

    @tool
    def lc_weather(city: str) -> str:
        """Forecast for a city."""
        return city

    db_path = tmp_path / "registry.db"
    provider = HashedEmbeddingProvider(dimensions=128)
    tools = [lc_weather, weather_tool]

    selected = filter_tools(
        tools,
        context="weather in Paris tomorrow",
        max_tools=2,
        budget_tokens=2000,
        db_path=db_path,
        embedding_provider=provider,
    )

    assert len(selected) == 2
    assert lc_weather in selected
