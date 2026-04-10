from __future__ import annotations

from optulus_sdk.embeddings import HashedEmbeddingProvider
from optulus_sdk.filtering import filter_tools
from optulus_sdk.pruner import prune_output
from optulus_sdk.telemetry import AgentEvent, ExportResult, TelemetryConfig, TelemetryRecorder
from optulus_sdk.types import OutputType


class FakeExporter:
    def __init__(self) -> None:
        self.events: list[AgentEvent] = []

    def export(self, events: list[AgentEvent]) -> ExportResult:
        self.events.extend(events)
        return ExportResult(success=True, attempts=1, status_code=200)


def test_pruner_emits_prune_event() -> None:
    exporter = FakeExporter()
    recorder = TelemetryRecorder(
        exporter,
        config=TelemetryConfig(enabled=True, flush_interval_ms=10),
    )
    recorder.start()
    try:
        prune_output(
            "word " * 100,
            OutputType.TEXT,
            token_budget=10,
            telemetry_recorder=recorder,
        )
    finally:
        recorder.stop(flush=True)

    assert any(event.event_type == "prune" for event in exporter.events)


def test_filter_tools_emits_tool_selection_event(tmp_path) -> None:
    exporter = FakeExporter()
    recorder = TelemetryRecorder(
        exporter,
        config=TelemetryConfig(enabled=True, flush_interval_ms=10),
    )
    provider = HashedEmbeddingProvider(dimensions=64)
    tools = [
        {"name": "weather_lookup", "description": "Weather forecast", "input_schema": {"type": "object"}},
        {"name": "stock_quote", "description": "Stock quote", "input_schema": {"type": "object"}},
    ]

    recorder.start()
    try:
        filter_tools(
            tools,
            context="weather in Paris",
            max_tools=1,
            budget_tokens=1000,
            db_path=tmp_path / "registry.db",
            embedding_provider=provider,
            telemetry_recorder=recorder,
        )
    finally:
        recorder.stop(flush=True)

    assert any(event.event_type == "tool_selection" for event in exporter.events)
