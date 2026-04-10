from __future__ import annotations

from dataclasses import dataclass
import contextvars
import uuid


@dataclass(frozen=True, slots=True)
class ObservabilityContext:
    session_id: str | None
    trace_id: str | None
    step_index: int | None


_session_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "optulus_session_id",
    default=None,
)
_trace_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "optulus_trace_id",
    default=None,
)
_step_index_var: contextvars.ContextVar[int] = contextvars.ContextVar(
    "optulus_step_index",
    default=0,
)


def start_session(
    *,
    session_id: str | None = None,
    trace_id: str | None = None,
) -> ObservabilityContext:
    resolved_session_id = session_id or f"sess_{uuid.uuid4().hex}"
    resolved_trace_id = trace_id or f"trace_{uuid.uuid4().hex}"
    _session_id_var.set(resolved_session_id)
    _trace_id_var.set(resolved_trace_id)
    _step_index_var.set(0)
    return ObservabilityContext(
        session_id=resolved_session_id,
        trace_id=resolved_trace_id,
        step_index=0,
    )


def end_session() -> None:
    _session_id_var.set(None)
    _trace_id_var.set(None)
    _step_index_var.set(0)


def set_trace_id(trace_id: str | None) -> None:
    _trace_id_var.set(trace_id)


def set_step_index(step_index: int) -> None:
    if step_index < 0:
        raise ValueError("step_index must be >= 0")
    _step_index_var.set(step_index)


def next_step_index() -> int:
    next_index = _step_index_var.get() + 1
    _step_index_var.set(next_index)
    return next_index


def get_observability_context() -> ObservabilityContext:
    session_id = _session_id_var.get()
    trace_id = _trace_id_var.get()
    if session_id is None and trace_id is None:
        return ObservabilityContext(session_id=None, trace_id=None, step_index=None)
    return ObservabilityContext(
        session_id=session_id,
        trace_id=trace_id,
        step_index=_step_index_var.get(),
    )


def ensure_observability_session() -> ObservabilityContext:
    """Start a process-local session with UUID ids if none is active (used by telemetry)."""
    ctx = get_observability_context()
    if ctx.session_id is None:
        return start_session()
    return ctx
