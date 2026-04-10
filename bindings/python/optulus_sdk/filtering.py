from __future__ import annotations

"""Local SDK-only tool registration and filtering helpers.

Example with MCP-style dict tools:
    tools = [{"name": "weather_lookup", "description": "Get forecast", "input_schema": {}}]
    selected = filter_tools(tools, context="weather in Tokyo")

Example with Python callables:
    def search_docs(query: str) -> str:
        "Search product docs."
        ...
    selected = filter_tools([search_docs], context="find API auth docs")

Example with LangChain ``@tool`` / ``BaseTool`` (requires ``langchain-core`` installed):
    from langchain_core.tools import tool

    @tool
    def search_docs(query: str) -> str:
        \"\"\"Search product docs.\"\"\"
        ...
    selected = filter_tools([search_docs], context="find API auth docs")
"""

from pathlib import Path
import logging
from typing import Iterable, Protocol, Any

from .embeddings import EmbeddingProvider
from .telemetry import TelemetryRecorder, resolve_telemetry_recorder
from .tool_registry import ToolRegistry
from .tool_types import ToolLike

logger = logging.getLogger(__name__)


class SupportsBindTools(Protocol):
    def bind_tools(self, tools: list[Any]) -> Any:
        ...


def register_tools(
    tools: list[ToolLike],
    *,
    db_path: str | Path = "~/.optulus/registry.db",
    embedding_provider: EmbeddingProvider | None = None,
) -> None:
    registry = ToolRegistry(db_path=db_path, embedding_provider=embedding_provider)
    try:
        registry.register(tools)
    finally:
        registry.close()


def filter_tools(
    tools: list[ToolLike],
    *,
    context: str,
    max_tools: int = 10,
    budget_tokens: int = 2000,
    pinned: Iterable[str] | None = None,
    db_path: str | Path = "~/.optulus/registry.db",
    embedding_provider: EmbeddingProvider | None = None,
    logging_enabled: bool = False,
    telemetry_recorder: TelemetryRecorder | None = None,
) -> list[ToolLike]:
    if max_tools <= 0:
        raise ValueError("max_tools must be positive")
    if budget_tokens < 0:
        raise ValueError("budget_tokens must be non-negative")

    pinned_set = set(pinned or [])
    registry = ToolRegistry(db_path=db_path, embedding_provider=embedding_provider)
    try:
        records = registry.register(tools)
        ranked = registry.rank(context=context, candidate_records=records)
        selected = _apply_limits(
            ranked=ranked,
            max_tools=max_tools,
            budget_tokens=budget_tokens,
            pinned=pinned_set,
        )
        event = _build_tool_selection_event(
            candidate_records=records,
            selected_records=selected,
            max_tools=max_tools,
            budget_tokens=budget_tokens,
            pinned_count=len(pinned_set),
        )
        if logging_enabled:
            logger.info(
                "Tool selection: %s/%s kept, estimated token savings=%s",
                event["selected_count"],
                event["candidate_count"],
                event["tokens_saved_est"],
            )
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug("Tool selection event: %s", event)
        recorder = resolve_telemetry_recorder(telemetry_recorder)
        if recorder is not None:
            recorder.record_event("tool_selection", event)
        if logging_enabled and recorder is not None:
            logger.info("TELEMETRY tool_selection %s", event)
        registry.record_selection(selected)
        return [record.original_tool for record in selected]
    finally:
        registry.close()


def bind_tools(
    llm: SupportsBindTools,
    tools: list[ToolLike],
    *,
    context: str,
    max_tools: int = 10,
    budget_tokens: int = 2000,
    pinned: Iterable[str] | None = None,
    db_path: str | Path = "~/.optulus/registry.db",
    embedding_provider: EmbeddingProvider | None = None,
    logging_enabled: bool = False,
    telemetry_recorder: TelemetryRecorder | None = None,
) -> Any:
    """Filter tools for context and bind them to an LLM in one call."""
    selected = filter_tools(
        tools,
        context=context,
        max_tools=max_tools,
        budget_tokens=budget_tokens,
        pinned=pinned,
        db_path=db_path,
        embedding_provider=embedding_provider,
        logging_enabled=logging_enabled,
        telemetry_recorder=telemetry_recorder,
    )
    return llm.bind_tools(selected)


def _build_tool_selection_event(
    *,
    candidate_records,
    selected_records,
    max_tools: int,
    budget_tokens: int,
    pinned_count: int,
) -> dict[str, Any]:
    candidate_tokens_est = sum(record.token_cost_estimate for record in candidate_records)
    selected_tokens_est = sum(record.token_cost_estimate for record in selected_records)
    selected_names = [record.name for record in selected_records]
    return {
        "event": "tool_selection",
        "candidate_count": len(candidate_records),
        "selected_count": len(selected_records),
        "tools_pruned_count": len(candidate_records) - len(selected_records),
        "candidate_tokens_est": candidate_tokens_est,
        "selected_tokens_est": selected_tokens_est,
        "tokens_saved_est": candidate_tokens_est - selected_tokens_est,
        "max_tools": max_tools,
        "budget_tokens": budget_tokens,
        "pinned_count": pinned_count,
        "selected_tool_names": selected_names,
    }


def _apply_limits(
    *,
    ranked,
    max_tools: int,
    budget_tokens: int,
    pinned: set[str],
):
    selected = []
    selected_ids = set()
    running_cost = 0

    for ranked_item in ranked:
        record = ranked_item.record
        if record.tool_id in selected_ids:
            continue

        is_pinned = record.name in pinned
        within_slot_limit = len(selected) < max_tools
        within_budget = running_cost + record.token_cost_estimate <= budget_tokens

        if is_pinned or (within_slot_limit and within_budget):
            selected.append(record)
            selected_ids.add(record.tool_id)
            if not is_pinned:
                running_cost += record.token_cost_estimate

    for ranked_item in ranked:
        record = ranked_item.record
        if record.name in pinned and record.tool_id not in selected_ids:
            selected.append(record)
            selected_ids.add(record.tool_id)

    return selected
