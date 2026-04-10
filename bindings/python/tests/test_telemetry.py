from __future__ import annotations

import time

from optulus_sdk.context import end_session, next_step_index, start_session
from optulus_sdk.telemetry import AgentEvent, ExportResult, TelemetryConfig, TelemetryRecorder


class FakeExporter:
    def __init__(self) -> None:
        self.batches: list[list[AgentEvent]] = []

    def export(self, events: list[AgentEvent]) -> ExportResult:
        self.batches.append(events)
        return ExportResult(success=True, attempts=1, status_code=200)


def test_telemetry_recorder_drops_when_queue_full() -> None:
    exporter = FakeExporter()
    recorder = TelemetryRecorder(
        exporter,
        config=TelemetryConfig(enabled=True, queue_size=1, flush_interval_ms=1_000, max_batch_size=1),
    )

    recorder.record_event("tool_call", {"tool_name": "a"})
    recorder.record_event("tool_call", {"tool_name": "b"})

    stats = recorder.stats()
    assert stats.dropped_events == 1
    assert stats.exported_events == 0


def test_telemetry_recorder_flushes_in_background() -> None:
    exporter = FakeExporter()
    recorder = TelemetryRecorder(
        exporter,
        config=TelemetryConfig(enabled=True, queue_size=10, flush_interval_ms=10, max_batch_size=5),
    )
    recorder.start()
    try:
        recorder.record_event("tool_call", {"tool_name": "weather"})
        deadline = time.time() + 0.5
        while not exporter.batches and time.time() < deadline:
            time.sleep(0.01)
    finally:
        recorder.stop(flush=True)

    assert exporter.batches
    assert exporter.batches[0][0].event_type == "tool_call"


def test_context_propagates_session_and_step() -> None:
    exporter = FakeExporter()
    recorder = TelemetryRecorder(exporter, config=TelemetryConfig(enabled=True))
    context = start_session()
    step = next_step_index()
    recorder.record_event("llm_request", {"model": "test"})
    recorder.start()
    try:
        recorder.stop(flush=True)
    finally:
        end_session()

    event = exporter.batches[0][0]
    assert event.session_id == context.session_id
    assert event.trace_id == context.trace_id
    assert event.step_index == step
