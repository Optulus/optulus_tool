from dataclasses import dataclass
from enum import Enum


class OutputType(str, Enum):
    HTML = "html"
    JSON = "json"
    LOG = "log"
    TEXT = "text"


@dataclass(slots=True)
class PruningResult:
    pruned_text: str
    tokens_before: int
    tokens_after: int
    rules_applied: list[str]
    was_truncated: bool
