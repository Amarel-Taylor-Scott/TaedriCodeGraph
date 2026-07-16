"""Replaceable SQLite exact, lexical, and adjacency serving projection."""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any, Iterable

from .canonical import canonical_json_bytes
from .contracts import GraphBundle, RelationAssertion

INDEX_SCHEMA_VERSION = "1.0.0"
_TERM = re.compile(r"[\w.:-]+", re.UNICODE)


def _record_json(record: Any) -> str:
    return canonical_json_bytes(record).decode("utf-8")


def _fts_query(text: str) -> str:
    terms = _TERM.findall(text)
    return " AND ".join('"' + term.replace('"', '""') + '"' for term in terms)


def _projection_texts(bundle: GraphBundle) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for projection in bundle.projections.values():
        if projection.subject.subject_kind != "entity":
            continue
        if not projection.projection_key.startswith("uceg.description."):
            continue
        payload = projection.payload
        if isinstance(payload, dict) and isinstance(payload.get("text"), str):
            result.setdefault(projection.subject.id, []).append(payload["text"])
    return result


def _entity_participants(relation: RelationAssertion) -> list[tuple[str, str]]:
    return [
        (participant.role_key, participant.subject.id)
        for participant in relation.participants
        if participant.subject.subject_kind == "entity"
    ]


def build_index(bundle: GraphBundle, path: Path) -> dict[str, Any]:
    """Build a disposable projection from a validated in-memory fact bundle."""

    if path.exists():
        path.unlink()
    descriptions = _projection_texts(bundle)
    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            """
            PRAGMA journal_mode=OFF;
            PRAGMA synchronous=OFF;
            PRAGMA temp_store=MEMORY;
            CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL) WITHOUT ROWID;
            CREATE TABLE entity(
                ordinal INTEGER PRIMARY KEY,
                entity_id TEXT NOT NULL UNIQUE,
                qualified_name TEXT NOT NULL,
                native_name TEXT NOT NULL,
                entity_kind TEXT NOT NULL,
                module_name TEXT NOT NULL,
                lifecycle TEXT NOT NULL,
                description TEXT NOT NULL,
                record_json TEXT NOT NULL
            );
            CREATE INDEX entity_native ON entity(native_name);
            CREATE INDEX entity_qualified ON entity(qualified_name);
            CREATE INDEX entity_kind ON entity(entity_kind);
            CREATE INDEX entity_module ON entity(module_name);
            CREATE VIRTUAL TABLE entity_fts USING fts5(
                qualified_name, native_name, entity_kind, module_name, description,
                tokenize='unicode61'
            );
            CREATE TABLE relation(
                ordinal INTEGER PRIMARY KEY,
                assertion_id TEXT NOT NULL UNIQUE,
                relation_key_id TEXT NOT NULL,
                predicate_key TEXT NOT NULL,
                modality TEXT NOT NULL,
                polarity TEXT NOT NULL,
                quantifier TEXT NOT NULL,
                source_entity_id TEXT,
                target_entity_id TEXT,
                endpoint_text TEXT NOT NULL,
                record_json TEXT NOT NULL
            );
            CREATE INDEX relation_key ON relation(relation_key_id);
            CREATE INDEX relation_predicate ON relation(predicate_key);
            CREATE INDEX relation_source ON relation(source_entity_id, predicate_key);
            CREATE INDEX relation_target ON relation(target_entity_id, predicate_key);
            CREATE VIRTUAL TABLE relation_fts USING fts5(
                predicate_key, endpoint_text,
                tokenize='unicode61'
            );
            CREATE TABLE participant(
                assertion_id TEXT NOT NULL,
                ordinal INTEGER NOT NULL,
                role_key TEXT NOT NULL,
                subject_kind TEXT NOT NULL,
                subject_id TEXT NOT NULL,
                PRIMARY KEY(assertion_id, ordinal)
            ) WITHOUT ROWID;
            CREATE INDEX participant_subject ON participant(subject_kind, subject_id, role_key);
            CREATE TABLE adjacency(
                entity_id TEXT NOT NULL,
                direction TEXT NOT NULL,
                predicate_key TEXT NOT NULL,
                other_entity_id TEXT NOT NULL,
                assertion_id TEXT NOT NULL,
                source_role TEXT NOT NULL,
                target_role TEXT NOT NULL,
                PRIMARY KEY(entity_id, direction, predicate_key, other_entity_id, assertion_id)
            ) WITHOUT ROWID;
            CREATE INDEX adjacency_walk ON adjacency(entity_id, direction, predicate_key);
            """
        )
        metadata = {
            "index_schema_version": INDEX_SCHEMA_VERSION,
            "snapshot_id": bundle.snapshot.identity.id,
            "analysis_manifest_id": bundle.analysis.identity.id,
        }
        connection.executemany(
            "INSERT INTO metadata(key, value) VALUES (?, ?)", sorted(metadata.items())
        )
        entity_names = {
            entity.identity.id: entity.qualified_name
            for entity in bundle.entities.values()
        }
        for ordinal, entity in enumerate(
            sorted(bundle.entities.values(), key=lambda item: item.identity.id), start=1
        ):
            description = "\n".join(sorted(descriptions.get(entity.identity.id, ())))
            row = (
                ordinal,
                entity.identity.id,
                entity.qualified_name,
                entity.native_name,
                entity.entity_kind_key,
                entity.module_name,
                entity.lifecycle.value,
                description,
                _record_json(entity),
            )
            connection.execute(
                "INSERT INTO entity VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", row
            )
            connection.execute(
                "INSERT INTO entity_fts(rowid, qualified_name, native_name, entity_kind, "
                "module_name, description) VALUES (?, ?, ?, ?, ?, ?)",
                (ordinal, entity.qualified_name, entity.native_name, entity.entity_kind_key,
                 entity.module_name, description),
            )
        for ordinal, relation in enumerate(
            sorted(bundle.relations.values(), key=lambda item: item.edge_assertion_id),
            start=1,
        ):
            entity_participants = _entity_participants(relation)
            source_id = entity_participants[0][1] if entity_participants else None
            target_id = entity_participants[1][1] if len(entity_participants) > 1 else None
            endpoint_text = " ".join(
                f"{role} {entity_names.get(entity_id, entity_id)}"
                for role, entity_id in entity_participants
            )
            connection.execute(
                "INSERT INTO relation VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    ordinal,
                    relation.edge_assertion_id,
                    relation.relation_key_id,
                    relation.predicate_key,
                    relation.modality.value,
                    relation.polarity.value,
                    relation.quantifier.value,
                    source_id,
                    target_id,
                    endpoint_text,
                    _record_json(relation),
                ),
            )
            connection.execute(
                "INSERT INTO relation_fts(rowid, predicate_key, endpoint_text) VALUES (?, ?, ?)",
                (ordinal, relation.predicate_key, endpoint_text),
            )
            for participant_ordinal, participant in enumerate(relation.participants):
                connection.execute(
                    "INSERT INTO participant VALUES (?, ?, ?, ?, ?)",
                    (
                        relation.edge_assertion_id,
                        participant_ordinal,
                        participant.role_key,
                        participant.subject.subject_kind,
                        participant.subject.id,
                    ),
                )
            if len(entity_participants) >= 2:
                source_role, source_id = entity_participants[0]
                for target_role, target_id in entity_participants[1:]:
                    connection.execute(
                        "INSERT OR IGNORE INTO adjacency VALUES (?, 'out', ?, ?, ?, ?, ?)",
                        (
                            source_id,
                            relation.predicate_key,
                            target_id,
                            relation.edge_assertion_id,
                            source_role,
                            target_role,
                        ),
                    )
                    connection.execute(
                        "INSERT OR IGNORE INTO adjacency VALUES (?, 'in', ?, ?, ?, ?, ?)",
                        (
                            target_id,
                            relation.predicate_key,
                            source_id,
                            relation.edge_assertion_id,
                            target_role,
                            source_role,
                        ),
                    )
        connection.commit()
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise RuntimeError(f"SQLite index integrity check failed: {integrity}")
    finally:
        connection.close()
    return {
        "provider": "sqlite-fts5-adjacency",
        "schema_version": INDEX_SCHEMA_VERSION,
        "sqlite_version": sqlite3.sqlite_version,
        "entity_count": len(bundle.entities),
        "relation_count": len(bundle.relations),
        "input_snapshot_id": bundle.snapshot.identity.id,
    }


class GraphIndex:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        return connection

    def resolve_entity(self, identifier: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT record_json FROM entity WHERE entity_id=? OR qualified_name=? "
                "ORDER BY CASE WHEN entity_id=? THEN 0 ELSE 1 END, ordinal LIMIT 1",
                (identifier, identifier, identifier),
            ).fetchone()
        return json.loads(row["record_json"]) if row else None

    def search_entities(
        self,
        text: str,
        *,
        entity_kind: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        if not 1 <= limit <= 1000:
            raise ValueError("entity result limit must be between 1 and 1000")
        fts = _fts_query(text)
        with self._connect() as connection:
            exact_params: list[Any] = [text, text]
            exact_where = "(qualified_name=? OR native_name=?)"
            if entity_kind:
                exact_where += " AND entity_kind=?"
                exact_params.append(entity_kind)
            exact_rows = connection.execute(
                f"SELECT entity_id, qualified_name, native_name, entity_kind, module_name, "
                f"lifecycle, description, 0.0 AS rank, 'exact' AS lane FROM entity WHERE {exact_where} "
                "ORDER BY qualified_name LIMIT ?",
                (*exact_params, limit),
            ).fetchall()
            results = [dict(row) for row in exact_rows]
            seen = {row["entity_id"] for row in results}
            if fts and len(results) < limit:
                params: list[Any] = [fts]
                kind_clause = ""
                if entity_kind:
                    kind_clause = " AND e.entity_kind=?"
                    params.append(entity_kind)
                params.append(limit - len(results))
                rows = connection.execute(
                    "SELECT e.entity_id, e.qualified_name, e.native_name, e.entity_kind, "
                    "e.module_name, e.lifecycle, e.description, "
                    "bm25(entity_fts, 4.0, 3.0, 1.0, 1.5, 2.0) "
                    "AS rank, 'fts5' AS lane FROM entity_fts "
                    "JOIN entity e ON e.ordinal=entity_fts.rowid "
                    f"WHERE entity_fts MATCH ?{kind_clause} ORDER BY rank, e.qualified_name LIMIT ?",
                    params,
                ).fetchall()
                results.extend(dict(row) for row in rows if row["entity_id"] not in seen)
        return results[:limit]

    def search_edges(
        self,
        *,
        predicate: str | None = None,
        text: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        if not 1 <= limit <= 1000:
            raise ValueError("edge result limit must be between 1 and 1000")
        with self._connect() as connection:
            if text and _fts_query(text):
                params: list[Any] = [_fts_query(text)]
                clause = ""
                if predicate:
                    clause = " AND r.predicate_key=?"
                    params.append(predicate)
                params.append(limit)
                rows = connection.execute(
                    "SELECT r.assertion_id, r.relation_key_id, r.predicate_key, r.modality, "
                    "r.polarity, r.quantifier, r.source_entity_id, r.target_entity_id, "
                    "r.endpoint_text, bm25(relation_fts) AS rank FROM relation_fts "
                    "JOIN relation r ON r.ordinal=relation_fts.rowid "
                    f"WHERE relation_fts MATCH ?{clause} ORDER BY rank, r.assertion_id LIMIT ?",
                    params,
                ).fetchall()
            else:
                clause = "WHERE predicate_key=?" if predicate else ""
                params = [predicate, limit] if predicate else [limit]
                rows = connection.execute(
                    "SELECT assertion_id, relation_key_id, predicate_key, modality, polarity, "
                    "quantifier, source_entity_id, target_entity_id, endpoint_text, 0.0 AS rank "
                    f"FROM relation {clause} ORDER BY assertion_id LIMIT ?",
                    params,
                ).fetchall()
        return [dict(row) for row in rows]

    def neighbors(
        self,
        entity_id: str,
        *,
        direction: str = "both",
        predicate: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        if direction not in {"in", "out", "both"}:
            raise ValueError("direction must be in, out, or both")
        if not 1 <= limit <= 1000:
            raise ValueError("neighbor limit must be between 1 and 1000")
        clauses = ["a.entity_id=?"]
        params: list[Any] = [entity_id]
        if direction != "both":
            clauses.append("a.direction=?")
            params.append(direction)
        if predicate:
            clauses.append("a.predicate_key=?")
            params.append(predicate)
        params.append(limit)
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT a.direction, a.predicate_key, a.other_entity_id, "
                "e.qualified_name AS other_qualified_name, e.entity_kind AS other_entity_kind, "
                "a.assertion_id, a.source_role, a.target_role FROM adjacency a "
                "JOIN entity e ON e.entity_id=a.other_entity_id WHERE "
                + " AND ".join(clauses)
                + " ORDER BY a.predicate_key, e.qualified_name, a.assertion_id LIMIT ?",
                params,
            ).fetchall()
        return [dict(row) for row in rows]

    def edge_record(self, assertion_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT record_json FROM relation WHERE assertion_id=?", (assertion_id,)
            ).fetchone()
        return json.loads(row["record_json"]) if row else None

    def integrity_check(self) -> str:
        with self._connect() as connection:
            return str(connection.execute("PRAGMA integrity_check").fetchone()[0])
