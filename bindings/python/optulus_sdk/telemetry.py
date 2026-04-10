from __future__ import annotations

from dataclasses import dataclass
import atexit
import json
import os
import queue
import threading
import time
from typing import Any, Callable, Literal, Protocol
import uuid

from ._telemetry_endpoint import DEFAULT_TELEMETRY_ENDPOINT
from .context import ensure_observability_session, get_observability_context

EventType = Literal[
    "prune",
    "tool_selection",
    "tool_call",
    "tool_result",
    "llm_request",
    "llm_response",
    "session_start",
    "session_end",
]


@dataclass(frozen=True, slots=True)
class AgentEvent:
    event_id: str
    event_type: EventType
    timestamp_ms: int
    payload: dict[str, Any]
    session_id: str | None = None
    trace_id: str | None = None
    step_index: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "timestamp_ms": self.timestamp_ms,
            "session_id": self.session_id,
            "trace_id": self.trace_id,
            "step_index": self.step_index,
            "payload": self.payload,
        }


@dataclass(frozen=True, slots=True)
class TelemetryConfig:
    enabled: bool = False
    endpoint: str = DEFAULT_TELEMETRY_ENDPOINT
    api_key: str | None = None
    queue_size: int = 10_000
    flush_interval_ms: int = 500
    max_batch_size: int = 100
    timeout_ms: int = 2_000
    max_retries: int = 3
    redact_content: bool = True


@dataclass(frozen=True, slots=True)
class ExportResult:
    success: bool
    attempts: int
    status_code: int | None = None
    error: str | None = None


class TelemetryExporter(Protocol):
    def export(self, events: list[AgentEvent]) -> ExportResult:
        raise NotImplementedError


@dataclass(slots=True)
class TelemetryStats:
    dropped_events: int = 0
    exported_events: int = 0
    export_errors: int = 0
    last_error: str | None = None


def new_event(
    event_type: EventType,
    payload: dict[str, Any],
    *,
    session_id: str | None = None,
    trace_id: str | None = None,
    step_index: int | None = None,
    timestamp_ms: int | None = None,
) -> AgentEvent:
    context = get_observability_context()
    return AgentEvent(
        event_id=f"evt_{uuid.uuid4().hex}",
        event_type=event_type,
        timestamp_ms=timestamp_ms or int(time.time() * 1000),
        payload=payload,
        session_id=session_id if session_id is not None else context.session_id,
        trace_id=trace_id if trace_id is not None else context.trace_id,
        step_index=step_index if step_index is not None else context.step_index,
    )


class TelemetryRecorder:
    def __init__(
        self,
        exporter: TelemetryExporter,
        *,
        config: TelemetryConfig | None = None,
        sdk_version: str = "0.1.0",
    ) -> None:
        self._config = config or TelemetryConfig(enabled=False)
        self._exporter = exporter
        self._sdk_version = sdk_version
        self._queue: queue.Queue[AgentEvent] = queue.Queue(maxsize=self._config.queue_size)
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._stats = TelemetryStats()
        self._lock = threading.Lock()

        if self._config.queue_size <= 0:
            raise ValueError("queue_size must be positive")
        if self._config.flush_interval_ms <= 0:
            raise ValueError("flush_interval_ms must be positive")
        if self._config.max_batch_size <= 0:
            raise ValueError("max_batch_size must be positive")

    @property
    def enabled(self) -> bool:
        return self._config.enabled

    def start(self) -> None:
        if not self._config.enabled:
            return
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="optulus-telemetry", daemon=True)
        self._thread.start()

    def stop(self, *, flush: bool = True) -> None:
        if self._thread is None:
            return
        self._stop_event.set()
        self._thread.join(timeout=max(1.0, self._config.timeout_ms / 1000.0))
        if flush and not self._queue.empty():
            self._flush_once()
        self._thread = None

    def record(self, event: AgentEvent) -> None:
        if not self._config.enabled:
            return
        try:
            self._queue.put_nowait(event)
        except queue.Full:
            with self._lock:
                self._stats.dropped_events += 1

    def record_event(
        self,
        event_type: EventType,
        payload: dict[str, Any],
        *,
        session_id: str | None = None,
        trace_id: str | None = None,
        step_index: int | None = None,
    ) -> None:
        if not self._config.enabled:
            return
        ensure_observability_session()
        event = new_event(
            event_type,
            payload,
            session_id=session_id,
            trace_id=trace_id,
            step_index=step_index,
        )
        self.record(event)

    def stats(self) -> TelemetryStats:
        with self._lock:
            return TelemetryStats(
                dropped_events=self._stats.dropped_events,
                exported_events=self._stats.exported_events,
                export_errors=self._stats.export_errors,
                last_error=self._stats.last_error,
            )

    def _run(self) -> None:
        interval_s = self._config.flush_interval_ms / 1000.0
        while not self._stop_event.is_set():
            self._flush_once(wait_timeout_s=interval_s)
        while not self._queue.empty():
            self._flush_once(wait_timeout_s=0.0)

    def _flush_once(self, *, wait_timeout_s: float = 0.0) -> None:
        batch: list[AgentEvent] = []
        if wait_timeout_s > 0.0 and self._queue.empty():
            try:
                first = self._queue.get(timeout=wait_timeout_s)
                batch.append(first)
            except queue.Empty:
                return

        while len(batch) < self._config.max_batch_size:
            try:
                batch.append(self._queue.get_nowait())
            except queue.Empty:
                break

        if not batch:
            return

        export_result = self._exporter.export(batch)
        with self._lock:
            if export_result.success:
                self._stats.exported_events += len(batch)
            else:
                self._stats.export_errors += 1
                self._stats.last_error = export_result.error or f"status={export_result.status_code}"

    def observe_tool_call(
        self,
        tool_name: str,
        invoke: Callable[[], Any],
    ) -> Any:
        started = time.perf_counter()
        self.record_event("tool_call", {"tool_name": tool_name})
        try:
            result = invoke()
            latency_ms = (time.perf_counter() - started) * 1000.0
            self.record_event(
                "tool_result",
                {"tool_name": tool_name, "success": True, "latency_ms": latency_ms},
            )
            return result
        except Exception as exc:
            latency_ms = (time.perf_counter() - started) * 1000.0
            self.record_event(
                "tool_result",
                {
                    "tool_name": tool_name,
                    "success": False,
                    "latency_ms": latency_ms,
                    "error": exc.__class__.__name__,
                },
            )
            raise

    def observe_llm_call(
        self,
        model: str,
        invoke: Callable[[], Any],
        *,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
    ) -> Any:
        started = time.perf_counter()
        self.record_event(
            "llm_request",
            {"model": model, "input_tokens": input_tokens},
        )
        try:
            result = invoke()
            latency_ms = (time.perf_counter() - started) * 1000.0
            self.record_event(
                "llm_response",
                {
                    "model": model,
                    "success": True,
                    "latency_ms": latency_ms,
                    "output_tokens": output_tokens,
                },
            )
            return result
        except Exception as exc:
            latency_ms = (time.perf_counter() - started) * 1000.0
            self.record_event(
                "llm_response",
                {
                    "model": model,
                    "success": False,
                    "latency_ms": latency_ms,
                    "error": exc.__class__.__name__,
                },
            )
            raise


_telemetry_override: bool | None = None
_default_recorder_lock = threading.Lock()
_default_recorder: TelemetryRecorder | None = None
_atexit_registered = False


def _env_truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def get_telemetry_enabled() -> bool:
    """Return whether outbound telemetry is enabled (API or ``OPTULUS_TELEMETRY_ENABLED``)."""
    if _telemetry_override is not None:
        return _telemetry_override
    return _env_truthy(os.environ.get("OPTULUS_TELEMETRY_ENABLED", ""))


def set_telemetry_enabled(enabled: bool) -> None:
    """Enable or disable SDK telemetry. When disabled, the default recorder is stopped."""
    global _telemetry_override
    _telemetry_override = enabled
    if not enabled:
        reset_default_telemetry_recorder()


def reset_default_telemetry_recorder() -> None:
    """Stop and drop the process-wide default recorder (mainly for tests)."""
    global _default_recorder
    with _default_recorder_lock:
        if _default_recorder is not None:
            _default_recorder.stop(flush=True)
            _default_recorder = None


def reset_telemetry_state() -> None:
    """Reset telemetry globals (for tests)."""
    global _telemetry_override
    _telemetry_override = None
    reset_default_telemetry_recorder()


def _register_atexit_once() -> None:
    global _atexit_registered
    if not _atexit_registered:
        atexit.register(_atexit_flush_default_recorder)
        _atexit_registered = True


def _atexit_flush_default_recorder() -> None:
    with _default_recorder_lock:
        if _default_recorder is not None:
            _default_recorder.stop(flush=True)


def get_default_telemetry_recorder() -> TelemetryRecorder | None:
    """Lazily create the default HTTP-backed recorder when telemetry is enabled."""
    if not get_telemetry_enabled():
        return None
    global _default_recorder
    with _default_recorder_lock:
        if _default_recorder is None:
            from .exporters import HttpTelemetryExporter

            api_key = os.environ.get("OPTULUS_API_KEY")
            config = TelemetryConfig(enabled=True, api_key=api_key)
            exporter = HttpTelemetryExporter(api_key=api_key, endpoint=config.endpoint)
            _default_recorder = TelemetryRecorder(exporter, config=config)
            _default_recorder.start()
            _register_atexit_once()
        return _default_recorder


def resolve_telemetry_recorder(explicit: TelemetryRecorder | None) -> TelemetryRecorder | None:
    """Use an explicit recorder if provided; otherwise the default when telemetry is enabled."""
    if explicit is not None:
        return explicit
    return get_default_telemetry_recorder()


def serialize_event_batch(events: list[AgentEvent], *, sdk_version: str) -> bytes:
    body = {
        "sdk_version": sdk_version,
        "sent_at_ms": int(time.time() * 1000),
        "events": [event.to_dict() for event in events],
    }
    return json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
