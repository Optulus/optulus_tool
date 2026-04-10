from __future__ import annotations

from dataclasses import dataclass
import hashlib
import inspect
import json
from typing import Any, Callable, Mapping

try:
    from langchain_core.tools import BaseTool as _LangChainBaseTool
except ImportError:  # pragma: no cover - optional integration
    _LangChainBaseTool = None  # type: ignore[misc, assignment]

ToolLike = Mapping[str, Any] | Callable[..., Any]


@dataclass(slots=True)
class ToolRecord:
    tool_id: str
    name: str
    description: str
    schema_text: str
    token_cost_estimate: int
    source_kind: str
    fingerprint: str
    original_tool: ToolLike
    input_index: int


def _estimate_token_cost(value: str) -> int:
    return len(value.split())


def _fingerprint_payload(payload: dict[str, str]) -> str:
    stable = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(stable.encode("utf-8")).hexdigest()


def _normalize_dict_tool(tool: Mapping[str, Any], input_index: int) -> ToolRecord:
    name = str(tool.get("name", "")).strip()
    if not name:
        raise ValueError("dict tool is missing required key 'name'")

    description = str(tool.get("description", "")).strip()
    input_schema = tool.get("input_schema", tool.get("parameters", {}))
    try:
        schema_text = json.dumps(input_schema, sort_keys=True, separators=(",", ":"))
    except TypeError:
        schema_text = str(input_schema)

    payload = {
        "source_kind": "dict",
        "name": name,
        "description": description,
        "schema_text": schema_text,
    }
    fingerprint = _fingerprint_payload(payload)

    return ToolRecord(
        tool_id=fingerprint,
        name=name,
        description=description,
        schema_text=schema_text,
        token_cost_estimate=max(1, _estimate_token_cost(f"{name} {description} {schema_text}")),
        source_kind="dict",
        fingerprint=fingerprint,
        original_tool=tool,
        input_index=input_index,
    )


def _normalize_langchain_tool(tool: Any, input_index: int) -> ToolRecord:
    name = str(getattr(tool, "name", "") or "").strip()
    if not name:
        raise ValueError("langchain tool is missing required attribute 'name'")

    description = str(getattr(tool, "description", "") or "").strip()
    get_json_schema = getattr(tool, "get_input_jsonschema", None)
    if callable(get_json_schema):
        try:
            input_schema = get_json_schema()
        except Exception:  # pragma: no cover - defensive
            input_schema = getattr(tool, "args_schema", {})
    else:
        input_schema = getattr(tool, "args_schema", {})

    try:
        schema_text = json.dumps(input_schema, sort_keys=True, separators=(",", ":"))
    except TypeError:
        schema_text = str(input_schema)

    payload = {
        "source_kind": "langchain",
        "name": name,
        "description": description,
        "schema_text": schema_text,
    }
    fingerprint = _fingerprint_payload(payload)

    return ToolRecord(
        tool_id=fingerprint,
        name=name,
        description=description,
        schema_text=schema_text,
        token_cost_estimate=max(1, _estimate_token_cost(f"{name} {description} {schema_text}")),
        source_kind="langchain",
        fingerprint=fingerprint,
        original_tool=tool,
        input_index=input_index,
    )


def _normalize_callable_tool(tool: Callable[..., Any], input_index: int) -> ToolRecord:
    name = tool.__name__
    doc = inspect.getdoc(tool) or ""
    try:
        signature = str(inspect.signature(tool))
    except (TypeError, ValueError):
        signature = "()"

    schema_text = f"{name}{signature}"
    payload = {
        "source_kind": "callable",
        "name": name,
        "description": doc,
        "schema_text": schema_text,
    }
    fingerprint = _fingerprint_payload(payload)

    return ToolRecord(
        tool_id=fingerprint,
        name=name,
        description=doc,
        schema_text=schema_text,
        token_cost_estimate=max(1, _estimate_token_cost(f"{name} {doc} {schema_text}")),
        source_kind="callable",
        fingerprint=fingerprint,
        original_tool=tool,
        input_index=input_index,
    )


def normalize_tools(tools: list[ToolLike]) -> list[ToolRecord]:
    records: list[ToolRecord] = []
    for index, tool in enumerate(tools):
        if _LangChainBaseTool is not None and isinstance(tool, _LangChainBaseTool):
            records.append(_normalize_langchain_tool(tool, input_index=index))
            continue
        if callable(tool):
            records.append(_normalize_callable_tool(tool, input_index=index))
            continue
        if isinstance(tool, Mapping):
            records.append(_normalize_dict_tool(tool, input_index=index))
            continue
        raise TypeError(
            "unsupported tool type; expected mapping-style MCP tool, callable, "
            "or langchain_core.tools.BaseTool, "
            f"got {type(tool)!r}"
        )
    return records
