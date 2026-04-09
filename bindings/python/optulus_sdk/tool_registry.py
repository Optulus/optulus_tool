from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import sqlite3
import time

from .embeddings import (
    EmbeddingProvider,
    SentenceTransformerEmbeddingProvider,
    cosine_similarity,
)
from .tool_types import ToolLike, ToolRecord, normalize_tools


@dataclass(slots=True)
class RankedTool:
    record: ToolRecord
    score: float


class ToolRegistry:
    def __init__(
        self,
        db_path: str | Path = "~/.optulus/registry.db",
        embedding_provider: EmbeddingProvider | None = None,
    ) -> None:
        self._db_path = Path(db_path).expanduser()
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._db_path)
        self._conn.row_factory = sqlite3.Row
        self._embedding_provider = (
            embedding_provider or SentenceTransformerEmbeddingProvider()
        )
        self._init_schema()

    def _init_schema(self) -> None:
        cursor = self._conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS tools (
                tool_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT NOT NULL,
                schema_text TEXT NOT NULL,
                token_cost_estimate INTEGER NOT NULL,
                source_kind TEXT NOT NULL,
                fingerprint TEXT NOT NULL UNIQUE,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS tool_embeddings (
                tool_id TEXT PRIMARY KEY,
                vector_json TEXT NOT NULL,
                dimension INTEGER NOT NULL,
                updated_at REAL NOT NULL,
                FOREIGN KEY(tool_id) REFERENCES tools(tool_id)
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS tool_usage_stats (
                tool_id TEXT PRIMARY KEY,
                selected_count INTEGER NOT NULL DEFAULT 0,
                last_selected_at REAL,
                FOREIGN KEY(tool_id) REFERENCES tools(tool_id)
            )
            """
        )
        self._conn.commit()

    def register(self, tools: list[ToolLike]) -> list[ToolRecord]:
        records = normalize_tools(tools)
        if not records:
            return records

        vectors = self._embedding_provider.embed_many(
            [self._embedding_text(record) for record in records]
        )
        now = time.time()
        cursor = self._conn.cursor()

        for record, vector in zip(records, vectors):
            cursor.execute(
                """
                INSERT INTO tools (
                    tool_id, name, description, schema_text, token_cost_estimate,
                    source_kind, fingerprint, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(tool_id) DO UPDATE SET
                    name = excluded.name,
                    description = excluded.description,
                    schema_text = excluded.schema_text,
                    token_cost_estimate = excluded.token_cost_estimate,
                    source_kind = excluded.source_kind,
                    fingerprint = excluded.fingerprint,
                    updated_at = excluded.updated_at
                """,
                (
                    record.tool_id,
                    record.name,
                    record.description,
                    record.schema_text,
                    record.token_cost_estimate,
                    record.source_kind,
                    record.fingerprint,
                    now,
                    now,
                ),
            )
            cursor.execute(
                """
                INSERT INTO tool_embeddings (tool_id, vector_json, dimension, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(tool_id) DO UPDATE SET
                    vector_json = excluded.vector_json,
                    dimension = excluded.dimension,
                    updated_at = excluded.updated_at
                """,
                (record.tool_id, json.dumps(vector), len(vector), now),
            )
            cursor.execute(
                """
                INSERT INTO tool_usage_stats (tool_id, selected_count, last_selected_at)
                VALUES (?, 0, NULL)
                ON CONFLICT(tool_id) DO NOTHING
                """,
                (record.tool_id,),
            )

        self._conn.commit()
        return records

    def rank(
        self,
        context: str,
        candidate_records: list[ToolRecord],
    ) -> list[RankedTool]:
        if not candidate_records:
            return []

        query_vector = self._embedding_provider.embed_text(context)
        embeddings = self._load_embeddings([record.tool_id for record in candidate_records])

        ranked: list[RankedTool] = []
        for record in candidate_records:
            vector = embeddings.get(record.tool_id)
            score = cosine_similarity(query_vector, vector) if vector is not None else 0.0
            ranked.append(RankedTool(record=record, score=score))

        ranked.sort(
            key=lambda item: (
                -item.score,
                item.record.input_index,
                item.record.name,
            )
        )
        return ranked

    def record_selection(self, selected_records: list[ToolRecord]) -> None:
        if not selected_records:
            return
        now = time.time()
        cursor = self._conn.cursor()
        for record in selected_records:
            cursor.execute(
                """
                UPDATE tool_usage_stats
                SET selected_count = selected_count + 1,
                    last_selected_at = ?
                WHERE tool_id = ?
                """,
                (now, record.tool_id),
            )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def _embedding_text(self, record: ToolRecord) -> str:
        return f"{record.name}\n{record.description}\n{record.schema_text}"

    def _load_embeddings(self, tool_ids: list[str]) -> dict[str, list[float]]:
        if not tool_ids:
            return {}
        placeholders = ", ".join("?" for _ in tool_ids)
        cursor = self._conn.cursor()
        rows = cursor.execute(
            f"""
            SELECT tool_id, vector_json
            FROM tool_embeddings
            WHERE tool_id IN ({placeholders})
            """,
            tuple(tool_ids),
        ).fetchall()
        return {row["tool_id"]: json.loads(row["vector_json"]) for row in rows}
