from __future__ import annotations

import sqlite3

from optulus_sdk.embeddings import HashedEmbeddingProvider
from optulus_sdk.tool_registry import ToolRegistry
from optulus_sdk.tool_types import normalize_tools


def _search_docs(query: str, limit: int = 5) -> str:
    """Search docs by keyword."""
    return f"{query}:{limit}"


def test_normalize_tools_supports_dict_and_callable() -> None:
    tools = [
        {
            "name": "web_search",
            "description": "Search the web for recent information",
            "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}},
        },
        _search_docs,
    ]

    records = normalize_tools(tools)
    assert len(records) == 2
    assert records[0].source_kind == "dict"
    assert records[1].source_kind == "callable"
    assert records[1].name == "_search_docs"


def test_registry_register_upsert_does_not_duplicate(tmp_path) -> None:
    db_path = tmp_path / "registry.db"
    provider = HashedEmbeddingProvider(dimensions=64)
    registry = ToolRegistry(db_path=db_path, embedding_provider=provider)
    try:
        tools = [
            {
                "name": "calendar_lookup",
                "description": "Read calendar events",
                "input_schema": {"type": "object"},
            }
        ]
        registry.register(tools)
        registry.register(tools)
    finally:
        registry.close()

    conn = sqlite3.connect(db_path)
    try:
        tool_count = conn.execute("SELECT COUNT(*) FROM tools").fetchone()[0]
        embedding_count = conn.execute("SELECT COUNT(*) FROM tool_embeddings").fetchone()[0]
        assert tool_count == 1
        assert embedding_count == 1
    finally:
        conn.close()


def test_registry_rank_prefers_semantic_match(tmp_path) -> None:
    db_path = tmp_path / "registry.db"
    provider = HashedEmbeddingProvider(dimensions=128)
    registry = ToolRegistry(db_path=db_path, embedding_provider=provider)
    try:
        tools = [
            {
                "name": "weather_lookup",
                "description": "Get weather forecast and temperature",
                "input_schema": {"type": "object"},
            },
            {
                "name": "stock_quote",
                "description": "Get stock market prices",
                "input_schema": {"type": "object"},
            },
        ]
        records = registry.register(tools)
        ranked = registry.rank("weather for tomorrow", candidate_records=records)
        assert ranked[0].record.name == "weather_lookup"
    finally:
        registry.close()
