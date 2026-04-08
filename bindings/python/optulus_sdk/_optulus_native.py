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


from html.parser import HTMLParser

INTERACTIVE_TAGS = {"a", "button", "input", "select", "textarea", "label", "option"}
STRUCTURAL_TAGS = {
    "form", "nav", "main", "dialog", "table", "tr", "td", "th", "section", "aside",
}
SKIP_TAGS = {"header", "footer", "script", "style", "head", "noscript", "svg", "meta", "link"}
KEEP_ATTRS = {
    "id", "name", "role", "type", "href", "src", "action", "method",
    "placeholder", "value", "for", "aria-label", "aria-expanded",
    "aria-checked", "aria-disabled", "aria-labelledby",
    "data-testid", "data-pw", "data-id",
}
IDENTITY_ATTRS = {"id", "role", "aria-label", "data-testid"}
TEXT_MAX_CHARS = 100

_VOID_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
}


class _SemanticHTMLReducer(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._lines: list[str] = []
        self._depth = 0
        # Nesting counter while inside a skipped subtree (header, footer, etc.)
        self._skip = 0
        # Index of the most recently emitted element line, for deferred text appending.
        self._last_idx: int | None = None
        # True once any child element line is emitted after _last_idx.
        self._had_child = False
        self._text: list[str] = []

    def _flush(self) -> None:
        """Append collected direct text to the last emitted line, then reset state."""
        if self._last_idx is not None and self._text and not self._had_child:
            combined = " ".join(self._text)[:TEXT_MAX_CHARS]
            self._lines[self._last_idx] += f' "{combined}"'
        self._text = []
        self._last_idx = None
        self._had_child = False

    def _emit(self, tag: str, attrs: dict[str, str]) -> None:
        if self._last_idx is not None:
            self._had_child = True
        self._flush()

        indent = "  " * self._depth
        id_val = attrs.get("id", "")
        tag_part = f"{tag}#{id_val}" if id_val else tag
        attr_str = "".join(
            f"[{k}={v}]"
            for k, v in attrs.items()
            if k in KEEP_ATTRS and k != "id"
        )
        self._last_idx = len(self._lines)
        self._had_child = False
        self._lines.append(f"{indent}{tag_part}{attr_str}")

    def handle_starttag(self, tag: str, attrs_list: list) -> None:
        if self._skip:
            if tag not in _VOID_TAGS:
                self._skip += 1
            return

        if tag in SKIP_TAGS:
            self._skip += 1
            return

        attr_dict = {k.lower(): (v or "") for k, v in attrs_list}
        want = (
            tag in INTERACTIVE_TAGS
            or tag in STRUCTURAL_TAGS
            or bool(attr_dict.keys() & IDENTITY_ATTRS)
        )
        if want:
            self._emit(tag, attr_dict)
            if tag not in _VOID_TAGS:
                self._depth += 1

    def handle_endtag(self, tag: str) -> None:
        if self._skip:
            if tag not in _VOID_TAGS:
                self._skip -= 1
            return

        if tag in INTERACTIVE_TAGS or tag in STRUCTURAL_TAGS:
            self._flush()
            self._depth = max(0, self._depth - 1)

    def handle_startendtag(self, tag: str, attrs_list: list) -> None:
        self.handle_starttag(tag, attrs_list)

    def handle_data(self, data: str) -> None:
        if self._skip:
            return
        stripped = data.strip()
        if stripped:
            self._text.append(stripped)

    def result(self) -> str:
        self._flush()
        return "\n".join(self._lines).strip()


def _reduce_html(value: str) -> str:
    value = re.sub(r"(?is)<script[^>]*>.*?</script>", "", value)
    value = re.sub(r"(?is)<style[^>]*>.*?</style>", "", value)
    reducer = _SemanticHTMLReducer()
    reducer.feed(value)
    return reducer.result()


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
