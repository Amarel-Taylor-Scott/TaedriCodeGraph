"""Replaceable SQLite exact, lexical, and adjacency serving projection."""

from __future__ import annotations

import json
import math
import re
import sqlite3
from pathlib import Path
from typing import Any, Iterable, Mapping

from .canonical import canonical_json_bytes
from .contracts import GraphBundle, RelationAssertion
from .fingerprints import lsh_key_profile
from .representations import (
    RepresentationRegistry,
    core_representation_registry,
    identifier_blocking_keys,
    lexical_hash_vector,
)

INDEX_SCHEMA_VERSION = "2.0.0"
_TERM = re.compile(r"[\w.:-]+", re.UNICODE)
_STOPWORDS = frozenset(
    {"a", "an", "and", "as", "at", "by", "for", "from", "in", "into", "of", "on", "or", "the", "to", "with"}
)


def _record_json(record: Any) -> str:
    return canonical_json_bytes(record).decode("utf-8")


def _fts_query(text: str) -> str:
    terms = _TERM.findall(text)
    return " AND ".join('"' + term.replace('"', '""') + '"' for term in terms)


def _fts_query_any(text: str) -> str:
    terms = [term for term in _TERM.findall(text) if term.casefold() not in _STOPWORDS]
    clauses = []
    for term in terms:
        escaped = term.replace('"', '""')
        clauses.append(f'"{escaped}"*' if len(term) >= 4 and term.isalnum() else f'"{escaped}"')
    return " OR ".join(clauses)


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


def _flatten_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, bool | int):
        return str(value)
    if isinstance(value, list | tuple):
        return " ".join(_flatten_text(item) for item in value)
    if isinstance(value, dict):
        return " ".join(
            f"{key} {_flatten_text(item)}" for key, item in sorted(value.items())
        )
    return ""


def _cosine(left: Iterable[int], right: Iterable[int]) -> float:
    pairs = list(zip(left, right, strict=True))
    dot = sum(a * b for a, b in pairs)
    left_norm = math.sqrt(sum(a * a for a, _ in pairs))
    right_norm = math.sqrt(sum(b * b for _, b in pairs))
    if not left_norm or not right_norm:
        return 0.0
    return dot / (left_norm * right_norm)


def build_index(
    bundle: GraphBundle,
    path: Path,
    representation_registry: RepresentationRegistry | None = None,
) -> dict[str, Any]:
    """Build a disposable projection from a validated in-memory fact bundle."""

    if path.exists():
        path.unlink()
    representation_registry = representation_registry or core_representation_registry()
    descriptions = _projection_texts(bundle)
    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            """
            PRAGMA journal_mode=OFF;
            PRAGMA synchronous=OFF;
            PRAGMA temp_store=MEMORY;
            CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL) WITHOUT ROWID;
            CREATE TABLE source_file(
                source_file_id TEXT PRIMARY KEY,
                relative_path TEXT NOT NULL,
                content_digest TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                record_json TEXT NOT NULL
            ) WITHOUT ROWID;
            CREATE TABLE occurrence_ref(
                occurrence_id TEXT PRIMARY KEY,
                entity_id TEXT,
                source_file_id TEXT NOT NULL,
                byte_start INTEGER NOT NULL,
                byte_end INTEGER NOT NULL,
                line_range_json TEXT NOT NULL
            ) WITHOUT ROWID;
            CREATE INDEX occurrence_entity ON occurrence_ref(entity_id);
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
            CREATE TABLE representation_content(
                content_id TEXT PRIMARY KEY,
                family_key TEXT NOT NULL,
                representation_key TEXT NOT NULL,
                schema_version TEXT NOT NULL,
                value_kind TEXT NOT NULL,
                value_json TEXT NOT NULL
            ) WITHOUT ROWID;
            CREATE INDEX representation_content_key
                ON representation_content(representation_key, value_kind);
            CREATE TABLE representation_assertion(
                assertion_id TEXT PRIMARY KEY,
                subject_kind TEXT NOT NULL,
                subject_id TEXT NOT NULL,
                content_id TEXT NOT NULL,
                generation_run_id TEXT NOT NULL,
                modality TEXT NOT NULL,
                polarity TEXT NOT NULL,
                confidence_ppm INTEGER,
                lifecycle TEXT NOT NULL
            ) WITHOUT ROWID;
            CREATE INDEX representation_subject
                ON representation_assertion(subject_kind, subject_id, content_id);
            CREATE TABLE generation_run(
                generation_run_id TEXT PRIMARY KEY,
                attempt_key TEXT NOT NULL,
                producer_id TEXT NOT NULL,
                producer_version TEXT NOT NULL,
                status TEXT NOT NULL
            ) WITHOUT ROWID;
            CREATE TABLE lineage(
                lineage_id TEXT PRIMARY KEY,
                predicate_key TEXT NOT NULL,
                source_kind TEXT NOT NULL,
                source_id TEXT NOT NULL,
                target_kind TEXT NOT NULL,
                target_id TEXT NOT NULL,
                role_key TEXT,
                ordinal INTEGER
            ) WITHOUT ROWID;
            CREATE INDEX lineage_source ON lineage(source_kind, source_id, predicate_key);
            CREATE INDEX lineage_target ON lineage(target_kind, target_id, predicate_key);
            CREATE TABLE search_document(
                ordinal INTEGER PRIMARY KEY,
                entity_id TEXT NOT NULL UNIQUE,
                text_value TEXT NOT NULL
            );
            CREATE VIRTUAL TABLE search_fts USING fts5(
                text_value,
                tokenize='unicode61'
            );
            CREATE TABLE facet(
                entity_id TEXT NOT NULL,
                representation_key TEXT NOT NULL,
                value TEXT NOT NULL,
                assertion_id TEXT NOT NULL,
                PRIMARY KEY(entity_id, representation_key, value, assertion_id)
            ) WITHOUT ROWID;
            CREATE INDEX facet_lookup ON facet(representation_key, value, entity_id);
            CREATE TABLE scalar(
                entity_id TEXT NOT NULL,
                representation_key TEXT NOT NULL,
                integer_value INTEGER,
                decimal_value TEXT,
                assertion_id TEXT NOT NULL,
                PRIMARY KEY(entity_id, representation_key, assertion_id)
            ) WITHOUT ROWID;
            CREATE INDEX scalar_integer ON scalar(representation_key, integer_value, entity_id);
            CREATE TABLE blocking(
                block_key TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                assertion_id TEXT NOT NULL,
                PRIMARY KEY(block_key, entity_id, assertion_id)
            ) WITHOUT ROWID;
            CREATE INDEX blocking_entity ON blocking(entity_id, block_key);
            CREATE TABLE vector(
                entity_id TEXT NOT NULL,
                representation_key TEXT NOT NULL,
                dimensions INTEGER NOT NULL,
                values_json TEXT NOT NULL,
                assertion_id TEXT NOT NULL,
                PRIMARY KEY(entity_id, representation_key, assertion_id)
            ) WITHOUT ROWID;
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
        for record in sorted(bundle.files.values(), key=lambda item: item.identity.id):
            connection.execute(
                "INSERT INTO source_file VALUES (?, ?, ?, ?, ?)",
                (
                    record.identity.id,
                    record.relative_path,
                    record.content_digest,
                    record.size_bytes,
                    _record_json(record),
                ),
            )
        for occurrence in sorted(bundle.occurrences.values(), key=lambda item: item.identity.id):
            connection.execute(
                "INSERT INTO occurrence_ref VALUES (?, ?, ?, ?, ?, ?)",
                (
                    occurrence.identity.id,
                    occurrence.entity_id,
                    occurrence.source_file_id,
                    occurrence.byte_range[0],
                    occurrence.byte_range[1],
                    json.dumps(occurrence.line_column_range, separators=(",", ":")),
                ),
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
        search_texts: dict[str, list[str]] = {
            entity_id: [
                entity.qualified_name,
                entity.native_name,
                entity.entity_kind_key,
                entity.module_name,
                *descriptions.get(entity_id, ()),
            ]
            for entity_id, entity in bundle.entities.items()
        }
        for content in sorted(
            bundle.representation_contents.values(), key=lambda item: item.identity.id
        ):
            connection.execute(
                "INSERT INTO representation_content VALUES (?, ?, ?, ?, ?, ?)",
                (
                    content.identity.id,
                    content.family_key,
                    content.representation_key,
                    content.schema_version,
                    content.typed_value.kind.value,
                    json.dumps(content.typed_value.value, ensure_ascii=False, separators=(",", ":")),
                ),
            )
        for run in sorted(bundle.generation_runs.values(), key=lambda item: item.identity.id):
            connection.execute(
                "INSERT INTO generation_run VALUES (?, ?, ?, ?, ?)",
                (
                    run.identity.id,
                    run.attempt_key,
                    run.producer.id,
                    run.producer.version,
                    run.status,
                ),
            )
        for item in sorted(bundle.lineage.values(), key=lambda item: item.identity.id):
            connection.execute(
                "INSERT INTO lineage VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    item.identity.id,
                    item.predicate_key,
                    item.source.subject_kind,
                    item.source.id,
                    item.target.subject_kind,
                    item.target.id,
                    item.role_key,
                    item.ordinal,
                ),
            )
        for assertion in sorted(
            bundle.representation_assertions.values(), key=lambda item: item.identity.id
        ):
            content = bundle.representation_contents[assertion.content_id]
            connection.execute(
                "INSERT INTO representation_assertion VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    assertion.identity.id,
                    assertion.subject.subject_kind,
                    assertion.subject.id,
                    assertion.content_id,
                    assertion.generation_run_id,
                    assertion.modality.value,
                    assertion.polarity.value,
                    assertion.confidence_ppm,
                    assertion.lifecycle.value,
                ),
            )
            if assertion.subject.subject_kind != "entity" or assertion.polarity.value != "positive":
                continue
            try:
                descriptor = representation_registry.resolve(
                    content.representation_key, content.schema_version
                )
            except KeyError:
                continue
            value = content.typed_value.value
            lanes = set(descriptor.index_lanes)
            if "lexical" in lanes:
                search_texts.setdefault(assertion.subject.id, []).append(_flatten_text(value))
            if "facet" in lanes:
                values = value if isinstance(value, list) else [value]
                for facet_value in values:
                    if isinstance(facet_value, str | bool | int):
                        connection.execute(
                            "INSERT OR IGNORE INTO facet VALUES (?, ?, ?, ?)",
                            (
                                assertion.subject.id,
                                content.representation_key,
                                str(facet_value),
                                assertion.identity.id,
                            ),
                        )
            if "scalar" in lanes:
                integer_value = value if isinstance(value, int) and not isinstance(value, bool) else None
                decimal_value = value if isinstance(value, str) else None
                connection.execute(
                    "INSERT OR IGNORE INTO scalar VALUES (?, ?, ?, ?, ?)",
                    (
                        assertion.subject.id,
                        content.representation_key,
                        integer_value,
                        decimal_value,
                        assertion.identity.id,
                    ),
                )
            if "blocking" in lanes:
                if isinstance(value, dict):
                    block_values = value.get("values", [])
                else:
                    block_values = value if isinstance(value, list) else [value]
                for block_value in block_values:
                    if isinstance(block_value, str):
                        connection.execute(
                            "INSERT OR IGNORE INTO blocking VALUES (?, ?, ?)",
                            (block_value, assertion.subject.id, assertion.identity.id),
                        )
            if "vector" in lanes and isinstance(value, dict):
                values = value.get("values")
                dimensions = value.get("dimensions")
                if isinstance(values, list) and isinstance(dimensions, int):
                    connection.execute(
                        "INSERT OR IGNORE INTO vector VALUES (?, ?, ?, ?, ?)",
                        (
                            assertion.subject.id,
                            content.representation_key,
                            dimensions,
                            json.dumps(values, separators=(",", ":")),
                            assertion.identity.id,
                        ),
                    )
        for ordinal, entity in enumerate(
            sorted(bundle.entities.values(), key=lambda item: item.identity.id), start=1
        ):
            text_value = "\n".join(
                item for item in search_texts.get(entity.identity.id, ()) if item
            )
            connection.execute(
                "INSERT INTO search_document VALUES (?, ?, ?)",
                (ordinal, entity.identity.id, text_value),
            )
            connection.execute(
                "INSERT INTO search_fts(rowid, text_value) VALUES (?, ?)",
                (ordinal, text_value),
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
        "provider": "sqlite-typed-hybrid-adjacency",
        "schema_version": INDEX_SCHEMA_VERSION,
        "sqlite_version": sqlite3.sqlite_version,
        "entity_count": len(bundle.entities),
        "relation_count": len(bundle.relations),
        "representation_content_count": len(bundle.representation_contents),
        "representation_assertion_count": len(bundle.representation_assertions),
        "generation_run_count": len(bundle.generation_runs),
        "lineage_count": len(bundle.lineage),
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

    def metadata(self) -> dict[str, str]:
        with self._connect() as connection:
            rows = connection.execute("SELECT key, value FROM metadata ORDER BY key").fetchall()
        return {str(row["key"]): str(row["value"]) for row in rows}

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

    @staticmethod
    def _facet_filter_ids(
        connection: sqlite3.Connection, facets: Mapping[str, str] | None
    ) -> set[str] | None:
        if not facets:
            return None
        allowed: set[str] | None = None
        for key, value in sorted(facets.items()):
            rows = connection.execute(
                "SELECT DISTINCT entity_id FROM facet WHERE representation_key=? AND value=?",
                (key, value),
            ).fetchall()
            current = {str(row["entity_id"]) for row in rows}
            allowed = current if allowed is None else allowed & current
        return allowed or set()

    def hybrid_search(
        self,
        text: str,
        *,
        entity_kind: str | None = None,
        facets: Mapping[str, str] | None = None,
        lanes: Iterable[str] = ("exact", "lexical", "blocking", "vector"),
        limit: int = 20,
        explain: bool = True,
    ) -> list[dict[str, Any]]:
        """Fuse exact, FTS5, blocking, and bounded vector candidates with RRF."""

        if not 1 <= limit <= 1000:
            raise ValueError("entity result limit must be between 1 and 1000")
        requested = tuple(dict.fromkeys(lanes))
        unknown = set(requested) - {"exact", "lexical", "blocking", "vector"}
        if unknown:
            raise ValueError(f"unknown hybrid lane(s): {', '.join(sorted(unknown))}")
        lane_rows: dict[str, list[tuple[str, float | None]]] = {}
        with self._connect() as connection:
            allowed = self._facet_filter_ids(connection, facets)
            kind_ids: set[str] | None = None
            if entity_kind:
                kind_ids = {
                    str(row["entity_id"])
                    for row in connection.execute(
                        "SELECT entity_id FROM entity WHERE entity_kind=?", (entity_kind,)
                    )
                }

            def accepted(entity_id: str) -> bool:
                return (allowed is None or entity_id in allowed) and (
                    kind_ids is None or entity_id in kind_ids
                )

            if "exact" in requested:
                rows = connection.execute(
                    "SELECT entity_id FROM entity WHERE qualified_name=? OR native_name=? "
                    "ORDER BY CASE WHEN qualified_name=? THEN 0 ELSE 1 END, qualified_name LIMIT ?",
                    (text, text, text, max(limit * 5, 100)),
                ).fetchall()
                lane_rows["exact"] = [
                    (str(row["entity_id"]), None)
                    for row in rows
                    if accepted(str(row["entity_id"]))
                ]

            fts = _fts_query_any(text)
            if "lexical" in requested and fts:
                rows = connection.execute(
                    "SELECT d.entity_id, bm25(search_fts) AS rank FROM search_fts "
                    "JOIN search_document d ON d.ordinal=search_fts.rowid "
                    "WHERE search_fts MATCH ? ORDER BY rank, d.entity_id LIMIT ?",
                    (fts, max(limit * 50, 1000)),
                ).fetchall()
                lane_rows["lexical"] = [
                    (str(row["entity_id"]), float(row["rank"]))
                    for row in rows
                    if accepted(str(row["entity_id"]))
                ]

            if "blocking" in requested:
                keys = identifier_blocking_keys(text, text)
                placeholders = ",".join("?" for _ in keys)
                rows = connection.execute(
                    f"SELECT entity_id, COUNT(DISTINCT block_key) AS matches FROM blocking "
                    f"WHERE block_key IN ({placeholders}) GROUP BY entity_id "
                    "ORDER BY matches DESC, entity_id LIMIT ?",
                    (*keys, max(limit * 50, 1000)),
                ).fetchall()
                lane_rows["blocking"] = [
                    (str(row["entity_id"]), float(row["matches"]))
                    for row in rows
                    if accepted(str(row["entity_id"]))
                ]

            if "vector" in requested:
                candidate_ids = {
                    entity_id for rows in lane_rows.values() for entity_id, _ in rows
                }
                total_vectors = int(
                    connection.execute(
                        "SELECT COUNT(*) FROM vector WHERE representation_key=?",
                        ("uceg.embedding.lexical_hash64",),
                    ).fetchone()[0]
                )
                vector_rows: list[sqlite3.Row]
                if candidate_ids:
                    bounded = sorted(candidate_ids)[:5000]
                    placeholders = ",".join("?" for _ in bounded)
                    vector_rows = connection.execute(
                        f"SELECT entity_id, values_json FROM vector WHERE representation_key=? "
                        f"AND entity_id IN ({placeholders})",
                        ("uceg.embedding.lexical_hash64", *bounded),
                    ).fetchall()
                elif total_vectors <= 50_000:
                    vector_rows = connection.execute(
                        "SELECT entity_id, values_json FROM vector WHERE representation_key=?",
                        ("uceg.embedding.lexical_hash64",),
                    ).fetchall()
                else:
                    vector_rows = []
                query_vector = lexical_hash_vector(text)
                scored = sorted(
                    (
                        (str(row["entity_id"]), _cosine(query_vector, json.loads(row["values_json"])))
                        for row in vector_rows
                        if accepted(str(row["entity_id"]))
                    ),
                    key=lambda item: (-item[1], item[0]),
                )
                lane_rows["vector"] = [item for item in scored if item[1] > 0][
                    : max(limit * 50, 1000)
                ]

            entity_ids = {entity_id for rows in lane_rows.values() for entity_id, _ in rows}
            records: dict[str, dict[str, Any]] = {}
            if entity_ids:
                bounded_ids = sorted(entity_ids)
                placeholders = ",".join("?" for _ in bounded_ids)
                rows = connection.execute(
                    "SELECT entity_id, qualified_name, native_name, entity_kind, module_name, "
                    f"lifecycle, description FROM entity WHERE entity_id IN ({placeholders})",
                    bounded_ids,
                ).fetchall()
                records = {str(row["entity_id"]): dict(row) for row in rows}

        weights = {"exact": 4.0, "lexical": 2.0, "blocking": 1.0, "vector": 1.25}
        fused: dict[str, dict[str, Any]] = {}
        for lane, rows in lane_rows.items():
            for rank, (entity_id, raw_score) in enumerate(rows, start=1):
                item = fused.setdefault(
                    entity_id,
                    {"score": 0.0, "lane_ranks": {}, "raw_lane_scores": {}},
                )
                item["score"] += weights[lane] / (60 + rank)
                item["lane_ranks"][lane] = rank
                if raw_score is not None:
                    item["raw_lane_scores"][lane] = raw_score
        kind_prior = {
            "uceg.entity.python.function": 0.008,
            "uceg.entity.python.method": 0.008,
            "uceg.entity.python.class": 0.008,
            "uceg.entity.python.module": 0.003,
            "uceg.entity.python.parameter": -0.008,
            "uceg.entity.python.variable": -0.007,
            "uceg.entity.python.instance_field": -0.006,
            "uceg.entity.external_symbol": -0.009,
            "uceg.entity.file": -0.004,
        }
        for entity_id, receipt in fused.items():
            record = records.get(entity_id, {})
            prior = kind_prior.get(record.get("entity_kind"), 0.0)
            native_name = str(record.get("native_name", ""))
            if native_name.startswith("_") and not native_name.startswith("__"):
                prior -= 0.001
            depth_penalty = min(str(record.get("qualified_name", "")).count("."), 12) * 0.00015
            receipt["structural_prior"] = prior - depth_penalty
            receipt["score"] += receipt["structural_prior"]
        ordered = sorted(
            fused.items(),
            key=lambda item: (-item[1]["score"], records.get(item[0], {}).get("qualified_name", item[0])),
        )[:limit]
        output: list[dict[str, Any]] = []
        for entity_id, receipt in ordered:
            result = dict(records[entity_id])
            result["score"] = round(receipt["score"], 8)
            result["lane_ranks"] = receipt["lane_ranks"]
            if explain:
                result["query_receipt"] = {
                    "fusion": "weighted_reciprocal_rank@60",
                    "requested_lanes": list(requested),
                    "contributing_lanes": list(receipt["lane_ranks"]),
                    "raw_lane_scores": receipt["raw_lane_scores"],
                    "structural_prior": round(receipt["structural_prior"], 8),
                    "facet_filters": dict(facets or {}),
                    "vector_policy": "candidate-bounded-or-exhaustive-at-most-50000",
                }
            output.append(result)
        return output

    def representations(
        self, subject_kind: str, subject_id: str, *, limit: int = 100
    ) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT a.assertion_id, c.family_key, c.representation_key, c.schema_version, "
                "c.value_kind, c.value_json, a.modality, a.polarity, a.confidence_ppm, "
                "a.lifecycle, a.generation_run_id, r.attempt_key, r.producer_id, "
                "r.producer_version FROM representation_assertion a "
                "JOIN representation_content c ON c.content_id=a.content_id "
                "JOIN generation_run r ON r.generation_run_id=a.generation_run_id "
                "WHERE a.subject_kind=? AND a.subject_id=? "
                "ORDER BY c.family_key, c.representation_key, a.assertion_id LIMIT ?",
                (subject_kind, subject_id, limit),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["value"] = json.loads(item.pop("value_json"))
            result.append(item)
        return result

    def search_representations(
        self,
        *,
        representation_key: str | None = None,
        text: str | None = None,
        subject_kind: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        if not 1 <= limit <= 1000:
            raise ValueError("representation result limit must be between 1 and 1000")
        clauses: list[str] = []
        params: list[Any] = []
        if representation_key:
            clauses.append("c.representation_key=?")
            params.append(representation_key)
        if subject_kind:
            clauses.append("a.subject_kind=?")
            params.append(subject_kind)
        if text:
            clauses.append("c.value_json LIKE ? ESCAPE '\\'")
            escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            params.append(f"%{escaped}%")
        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        params.append(limit)
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT a.assertion_id, a.subject_kind, a.subject_id, c.family_key, "
                "c.representation_key, c.schema_version, c.value_kind, c.value_json, "
                "a.modality, a.polarity, a.confidence_ppm, a.lifecycle, "
                "a.generation_run_id, r.attempt_key, r.producer_id, r.producer_version "
                "FROM representation_assertion a "
                "JOIN representation_content c ON c.content_id=a.content_id "
                "JOIN generation_run r ON r.generation_run_id=a.generation_run_id "
                f"{where} ORDER BY c.representation_key, a.subject_kind, a.subject_id, "
                "a.assertion_id LIMIT ?",
                params,
            ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["value"] = json.loads(item.pop("value_json"))
            result.append(item)
        return result

    def source_for_entity(
        self, entity_id: str, *, include_text: bool = False, max_bytes: int = 12_000
    ) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT f.relative_path, f.content_digest, f.size_bytes, o.byte_start, "
                "o.byte_end, o.line_range_json FROM entity e "
                "JOIN occurrence_ref o ON o.occurrence_id=json_extract(e.record_json, "
                "'$.defining_occurrence_id') JOIN source_file f ON f.source_file_id=o.source_file_id "
                "WHERE e.entity_id=?",
                (entity_id,),
            ).fetchone()
        if row is None:
            return None
        result = {
            "relative_path": row["relative_path"],
            "content_digest": row["content_digest"],
            "size_bytes": row["size_bytes"],
            "byte_range": [row["byte_start"], row["byte_end"]],
            "line_column_range": json.loads(row["line_range_json"]),
        }
        if include_text:
            digest = str(row["content_digest"]).removeprefix("sha256:")
            cas_path = self.path.parents[3] / "cas" / "sha256" / digest[:2] / digest[2:]
            if cas_path.is_file():
                start, end = int(row["byte_start"]), int(row["byte_end"])
                content = cas_path.read_bytes()[start:end]
                truncated = len(content) > max_bytes
                result["source_text"] = content[:max_bytes].decode("utf-8", errors="replace")
                result["source_truncated"] = truncated
        return result

    def context(
        self,
        query: str,
        *,
        limit: int = 5,
        include_source: bool = False,
        facets: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        matches = self.hybrid_search(query, facets=facets, limit=limit, explain=True)
        items: list[dict[str, Any]] = []
        for match in matches:
            entity_id = match["entity_id"]
            representations = self.representations("entity", entity_id, limit=200)
            useful_keys = {
                "uceg.description.source.docstring",
                "uceg.description.deterministic.synopsis",
                "uceg.aspect.python.signature",
                "uceg.aspect.python.annotation",
                "uceg.label.entity_kind",
                "uceg.label.language",
            }
            items.append(
                {
                    "match": match,
                    "representations": [
                        item for item in representations if item["representation_key"] in useful_keys
                    ],
                    "source": self.source_for_entity(entity_id, include_text=include_source),
                    "neighbors": self.neighbors(entity_id, direction="both", limit=12),
                }
            )
        return {
            "query": query,
            "disclosure_level": "implementation" if include_source else "selection",
            "result_count": len(items),
            "items": items,
        }

    def structurally_similar(
        self, identifier: str, *, limit: int = 50
    ) -> list[dict[str, Any]]:
        """Generate bounded structural candidates from indexed MinHash/SimHash bands."""

        entity = self.resolve_entity(identifier)
        if entity is None:
            raise LookupError(f"entity not found: {identifier}")
        entity_id = entity["identity"]["id"]
        with self._connect() as connection:
            keys = [
                str(row["block_key"])
                for row in connection.execute(
                    "SELECT DISTINCT block_key FROM blocking WHERE entity_id=? "
                    "AND (block_key LIKE 'lsh:v1:%' OR block_key LIKE 'minhash4:%' "
                    "OR block_key LIKE 'simhash16:%')",
                    (entity_id,),
                )
            ]
            if not keys:
                return []
            placeholders = ",".join("?" for _ in keys)
            rows = connection.execute(
                "SELECT b.entity_id, e.qualified_name, e.entity_kind, "
                "COUNT(DISTINCT b.block_key) AS matching_bands, "
                "GROUP_CONCAT(DISTINCT b.block_key) AS matched_keys FROM blocking b "
                "JOIN entity e ON e.entity_id=b.entity_id "
                f"WHERE b.block_key IN ({placeholders}) AND b.entity_id<>? "
                "GROUP BY b.entity_id, e.qualified_name, e.entity_kind "
                "ORDER BY matching_bands DESC, e.qualified_name LIMIT ?",
                (*keys, entity_id, limit),
            ).fetchall()
        searched_profiles = sorted(
            {profile for profile in map(lsh_key_profile, keys) if profile is not None}
        )
        results: list[dict[str, Any]] = []
        for row in rows:
            result = dict(row)
            matched_keys = str(result.get("matched_keys", "")).split(",")
            matched_profiles = sorted(
                {
                    profile
                    for profile in map(lsh_key_profile, matched_keys)
                    if profile is not None
                }
            )
            result["matching_profiles"] = [
                {"algorithm": algorithm, "profile": profile}
                for algorithm, profile in matched_profiles
            ]
            result["candidate_only"] = True
            result["receipt"] = {
                "method": "indexed_multiresolution_lsh_bands",
                "source_entity_id": entity_id,
                "searched_band_count": len(keys),
                "searched_profiles": [
                    {"algorithm": algorithm, "profile": profile}
                    for algorithm, profile in searched_profiles
                ],
                "warning": "fingerprint collision nominates; it does not prove equivalence",
            }
            results.append(result)
        return results

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
