from __future__ import annotations

import json
import time
from collections.abc import Callable
from typing import Any

from . import _optulus_native
from .telemetry import TelemetryRecorder, resolve_telemetry_recorder
from .types import OutputType, PruningResult

MetricsHook = Callable[[dict[str, Any]], None]


class Pruner:
    def __init__(
        self,
        metrics_hook: MetricsHook | None = None,
        telemetry_recorder: TelemetryRecorder | None = None,
    ) -> None:
        self._metrics_hook = metrics_hook
        self._telemetry_recorder = telemetry_recorder

    def prune_output(
        self,
        raw_output: str,
        output_type: str | OutputType,
        token_budget: int,
        previous_output: str | None = None,
    ) -> PruningResult:
        normalized_type = (
            output_type.value if isinstance(output_type, OutputType) else output_type
        )
        started = time.perf_counter()
        native_result = _optulus_native.prune_output(
            raw_output, normalized_type, token_budget, previous_output
        )
        elapsed_ms = (time.perf_counter() - started) * 1000.0

        result = PruningResult(
            pruned_text=native_result.pruned_text,
            tokens_before=native_result.tokens_before,
            tokens_after=native_result.tokens_after,
            rules_applied=list(native_result.rules_applied),
            was_truncated=native_result.was_truncated,
        )

        if self._metrics_hook is not None:
            self._metrics_hook(
                {
                    "tokens_before": result.tokens_before,
                    "tokens_after": result.tokens_after,
                    "latency_ms": elapsed_ms,
                    "rules_applied": result.rules_applied,
                    "was_truncated": result.was_truncated,
                }
            )
        recorder = resolve_telemetry_recorder(self._telemetry_recorder)
        if recorder is not None:
            recorder.record_event(
                "prune",
                {
                    "tokens_before": result.tokens_before,
                    "tokens_after": result.tokens_after,
                    "latency_ms": elapsed_ms,
                    "rules_applied": result.rules_applied,
                    "was_truncated": result.was_truncated,
                    "output_type": normalized_type,
                },
            )

        return result


def prune_output(
    raw_output: str,
    output_type: str | OutputType,
    token_budget: int,
    previous_output: str | None = None,
    metrics_hook: MetricsHook | None = None,
    telemetry_recorder: TelemetryRecorder | None = None,
) -> PruningResult:
    return Pruner(
        metrics_hook=metrics_hook,
        telemetry_recorder=telemetry_recorder,
    ).prune_output(
        raw_output=raw_output,
        output_type=output_type,
        token_budget=token_budget,
        previous_output=previous_output,
    )


def prune_tool_message_content(
    content: Any,
    *,
    output_type: OutputType,
    token_budget: int,
    metrics_hook: MetricsHook | None = None,
    telemetry_recorder: TelemetryRecorder | None = None,
) -> Any:
    """Normalize LangChain / MCP-style tool message ``content`` and prune textual parts.

    Handles:

    - ``str``: passed to :func:`prune_output`; returns ``pruned_text`` (empty string unchanged).
    - ``list``: each element is processed; string items are pruned recursively; dict
      blocks with ``type`` equal to ``"text"`` have their ``text`` field pruned; other
      items are left as-is (e.g. image blocks).
    - Any other value is JSON-serialized (or ``str()``) and then pruned as a single string.

    Returns the same outer structure as the input (``str``, ``list``, or string after
    serialization), with only text segments replaced by pruned strings.
    """
    if isinstance(content, str):
        if not content:
            return content
        result = prune_output(
            content,
            output_type,
            token_budget=token_budget,
            metrics_hook=metrics_hook,
            telemetry_recorder=telemetry_recorder,
        )
        return result.pruned_text

    if isinstance(content, list):
        out: list[Any] = []
        for block in content:
            if isinstance(block, str):
                out.append(
                    prune_tool_message_content(
                        block,
                        output_type=output_type,
                        token_budget=token_budget,
                        metrics_hook=metrics_hook,
                        telemetry_recorder=telemetry_recorder,
                    )
                )
            elif isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text", "")
                if isinstance(text, str) and text:
                    pr = prune_output(
                        text,
                        output_type,
                        token_budget=token_budget,
                        metrics_hook=metrics_hook,
                        telemetry_recorder=telemetry_recorder,
                    )
                    out.append({**block, "text": pr.pruned_text})
                else:
                    out.append(block)
            else:
                out.append(block)
        return out

    try:
        serialized = json.dumps(content, ensure_ascii=False)
    except (TypeError, ValueError):
        serialized = str(content)
    return prune_tool_message_content(
        serialized,
        output_type=output_type,
        token_budget=token_budget,
        metrics_hook=metrics_hook,
        telemetry_recorder=telemetry_recorder,
    )
