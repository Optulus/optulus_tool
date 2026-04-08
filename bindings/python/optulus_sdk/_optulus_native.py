from __future__ import annotations

from dataclasses import dataclass
import json
import re


@dataclass(slots=True)
class PyPruningResult:
    pruned_text: str
    tokens_before: int
    tokens_after: int
    rules_applied: list[str]
    was_truncated: bool


def _token_count(value: str) -> int:
    return len(value.split())


def _reduce_html(value: str) -> str:
    value = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", value)
    value = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", value)
    value = re.sub(r"(?is)<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _reduce_json(current: str, previous: str | None) -> str:
    try:
        current_json = json.loads(current)
    except json.JSONDecodeError:
        return current

    if previous is None:
        return json.dumps(current_json, indent=2, sort_keys=True)

    try:
        previous_json = json.loads(previous)
    except json.JSONDecodeError:
        return json.dumps(current_json, indent=2, sort_keys=True)

    def diff(prev, curr):
        if prev == curr:
            return None
        if isinstance(prev, dict) and isinstance(curr, dict):
            out = {}
            for key, value in curr.items():
                if key in prev:
                    nested = diff(prev[key], value)
                    if nested is not None:
                        out[key] = nested
                else:
                    out[key] = value
            return out or None
        return curr

    delta = diff(previous_json, current_json)
    return json.dumps(delta if delta is not None else None, indent=2, sort_keys=True)


def prune_output(
    raw_output: str,
    output_type: str,
    token_budget: int,
    previous_output: str | None = None,
) -> PyPruningResult:
    output_type = output_type.lower()
    if output_type not in {"html", "json", "log", "text"}:
        raise ValueError(f"invalid prune request: invalid output_type: {output_type}")

    text = raw_output.replace("\r\n", "\n").replace(chr(0), "").strip()
    rules_applied: list[str] = []

    if text != raw_output:
        rules_applied.append("normalize_input")

    before_type = text
    if output_type == "html":
        text = _reduce_html(text)
    elif output_type == "json":
        text = _reduce_json(text, previous_output)
    elif output_type == "log":
        text = "\n".join(
            line.rstrip()
            for line in text.splitlines()
            if "DEBUG" not in line and "TRACE" not in line
        ).strip()
    if text != before_type:
        rules_applied.append("type_specific_reducer")

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    deduped = []
    seen = set()
    for line in lines:
        if line not in seen:
            seen.add(line)
            deduped.append(line)
    if deduped:
        candidate = "\n".join(deduped)
        if candidate != text:
            rules_applied.append("duplicate_collapse")
            text = candidate

    tokens = text.split()
    was_truncated = False
    if len(tokens) > token_budget:
        was_truncated = True
        if token_budget == 0:
            text = "..."
        else:
            kept = tokens[:token_budget]
            kept[-1] = "..."
            text = " ".join(kept)
        rules_applied.append("token_budget")

    return PyPruningResult(
        pruned_text=text,
        tokens_before=_token_count(raw_output),
        tokens_after=_token_count(text),
        rules_applied=rules_applied,
        was_truncated=was_truncated,
    )
