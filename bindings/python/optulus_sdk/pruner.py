from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from . import _optulus_native
from .types import OutputType, PruningResult

MetricsHook = Callable[[dict[str, Any]], None]


class Pruner:
    def __init__(self, metrics_hook: MetricsHook | None = None) -> None:
        self._metrics_hook = metrics_hook

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

        return result


def prune_output(
    raw_output: str,
    output_type: str | OutputType,
    token_budget: int,
    previous_output: str | None = None,
    metrics_hook: MetricsHook | None = None,
) -> PruningResult:
    return Pruner(metrics_hook=metrics_hook).prune_output(
        raw_output=raw_output,
        output_type=output_type,
        token_budget=token_budget,
        previous_output=previous_output,
    )
