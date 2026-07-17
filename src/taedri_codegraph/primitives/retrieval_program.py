"""Versioned, budgeted retrieval programs for body-free primitive metadata.

The program keeps retrieval policy out of one hard-coded query.  Every path declares
its representation family, lifecycle state, cost, and required capabilities.  The
executor uses deterministic reciprocal-rank fusion and emits an immutable receipt that
contains digests rather than the raw request.  Lexical hashes are explicitly
nonsemantic and cannot introduce candidates on their own; a true semantic retriever is
an optional, separately capability-gated supplement.
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from dataclasses import dataclass
from enum import Enum
from typing import Mapping, Protocol, Sequence

from ..canonical import canonical_digest, sha256_digest
from ..contracts import RecordMixin
from ..identity import IdentityRecord

_KEY = re.compile(r"^[a-z][a-z0-9_-]*(?:\.[a-z0-9_-]+)+$")
_VERSION = re.compile(r"^[0-9]+(?:\.[0-9]+){0,2}(?:[-+][A-Za-z0-9.-]+)?$")
_TOKEN = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "each",
        "every",
        "for",
        "from",
        "in",
        "into",
        "is",
        "its",
        "of",
        "on",
        "one",
        "or",
        "so",
        "that",
        "the",
        "their",
        "this",
        "to",
        "use",
        "using",
        "when",
        "while",
        "with",
    }
)


class RetrievalProgramError(ValueError):
    """Raised when a retrieval program or execution request is invalid."""


class RetrievalFamily(str, Enum):
    EXACT = "exact"
    LABEL = "label"
    BM25 = "bm25"
    BLOCKING = "blocking"
    LEXICAL_HASH = "lexical_hash_nonsemantic"
    SEMANTIC = "semantic"


class RepresentationTemperature(str, Enum):
    HOT = "hot"
    WARM = "warm"
    COLD = "cold"
    DERIVED = "derived"
    RETIRED = "retired"


class RetrievalPathStatus(str, Enum):
    EXECUTED = "executed"
    SKIPPED_CAPABILITY = "skipped_capability"
    SKIPPED_BUDGET = "skipped_budget"
    SKIPPED_POLICY = "skipped_policy"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class RetrievalPathDefinition(RecordMixin):
    key: str
    version: str
    family: RetrievalFamily
    representation_keys: tuple[str, ...]
    temperature: RepresentationTemperature
    fusion_weight_microunits: int
    cost_units: int
    candidate_limit: int
    required_capabilities: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not _KEY.fullmatch(self.key) or not _VERSION.fullmatch(self.version):
            raise RetrievalProgramError("retrieval path key or version is invalid")
        if not self.representation_keys or any(
            not _KEY.fullmatch(item) for item in self.representation_keys
        ):
            raise RetrievalProgramError(
                "retrieval path representation keys must be namespaced"
            )
        if (
            isinstance(self.fusion_weight_microunits, bool)
            or not 1 <= self.fusion_weight_microunits <= 100_000_000
        ):
            raise RetrievalProgramError("retrieval path fusion weight is invalid")
        if (
            isinstance(self.cost_units, bool)
            or self.cost_units <= 0
            or isinstance(self.candidate_limit, bool)
            or self.candidate_limit <= 0
        ):
            raise RetrievalProgramError("retrieval path bounds must be positive")
        capabilities = tuple(sorted(set(self.required_capabilities)))
        if any(not _KEY.fullmatch(item) for item in capabilities):
            raise RetrievalProgramError(
                "retrieval path capabilities must be namespaced"
            )
        object.__setattr__(self, "required_capabilities", capabilities)

    @property
    def ref(self) -> str:
        return f"{self.key}@{self.version}"

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict())


@dataclass(frozen=True, slots=True)
class RetrievalProgram(RecordMixin):
    key: str
    version: str
    paths: tuple[RetrievalPathDefinition, ...]
    minimum_candidates: int
    maximum_cost_units: int
    early_stop_margin_microunits: int
    stop_after_unique_exact: bool
    early_stop_path_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        if not _KEY.fullmatch(self.key) or not _VERSION.fullmatch(self.version):
            raise RetrievalProgramError("retrieval program key or version is invalid")
        refs = tuple(path.ref for path in self.paths)
        if not refs or len(set(refs)) != len(refs):
            raise RetrievalProgramError(
                "retrieval program paths must be non-empty and unique"
            )
        if (
            isinstance(self.minimum_candidates, bool)
            or self.minimum_candidates <= 0
            or isinstance(self.maximum_cost_units, bool)
            or self.maximum_cost_units <= 0
            or isinstance(self.early_stop_margin_microunits, bool)
            or self.early_stop_margin_microunits < 0
        ):
            raise RetrievalProgramError("retrieval program bounds are invalid")
        if not isinstance(self.stop_after_unique_exact, bool):
            raise RetrievalProgramError("unique-exact policy must be boolean")
        if len(set(self.early_stop_path_refs)) != len(self.early_stop_path_refs) or not set(
            self.early_stop_path_refs
        ).issubset(refs):
            raise RetrievalProgramError("early-stop paths must belong to the program")

    @property
    def ref(self) -> str:
        return f"{self.key}@{self.version}"

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict())


class RetrievalProgramRegistry:
    """Additive registry that never reinterprets a published program reference."""

    def __init__(self) -> None:
        self._programs: dict[str, RetrievalProgram] = {}

    def register(self, program: RetrievalProgram) -> None:
        existing = self._programs.get(program.ref)
        if existing is not None and existing.digest != program.digest:
            raise RetrievalProgramError(
                f"cannot reinterpret retrieval program {program.ref}"
            )
        self._programs[program.ref] = program

    def resolve(self, reference: str) -> RetrievalProgram:
        try:
            return self._programs[reference]
        except KeyError as exc:
            raise LookupError(f"unknown retrieval program: {reference}") from exc

    def programs(self) -> tuple[RetrievalProgram, ...]:
        return tuple(self._programs[key] for key in sorted(self._programs))


@dataclass(frozen=True, slots=True)
class RetrievalDocument(RecordMixin):
    primitive_id: str
    namespace: str
    name: str
    summary: str
    keywords: tuple[str, ...]
    use_cases: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.primitive_id or not _KEY.fullmatch(self.namespace):
            raise RetrievalProgramError("retrieval document identity is invalid")
        if not re.fullmatch(r"[a-z][a-z0-9.-]{1,127}", self.name):
            raise RetrievalProgramError("retrieval document name is invalid")
        if len(self.summary.strip()) < 10 or not self.keywords or not self.use_cases:
            raise RetrievalProgramError("retrieval document metadata is incomplete")
        if any(not item.strip() for item in self.keywords + self.use_cases):
            raise RetrievalProgramError("retrieval document metadata contains blanks")


class SemanticPrimitiveRetriever(Protocol):
    """Optional true-semantic lane; scores are integer microunits from 1..1M."""

    def __call__(
        self,
        request: str,
        documents: tuple[RetrievalDocument, ...],
        limit: int,
    ) -> Mapping[str, int]: ...


@dataclass(frozen=True, slots=True)
class RetrievalContribution(RecordMixin):
    path_ref: str
    path_rank: int
    path_score_microunits: int
    fusion_score_microunits: int


@dataclass(frozen=True, slots=True)
class RetrievedPrimitive(RecordMixin):
    primitive_id: str
    rank: int
    score_microunits: int
    contributions: tuple[RetrievalContribution, ...]


@dataclass(frozen=True, slots=True)
class RetrievalPathReceipt(RecordMixin):
    sequence: int
    path_ref: str
    definition_digest: str
    family: RetrievalFamily
    temperature: RepresentationTemperature
    status: RetrievalPathStatus
    candidate_count: int
    new_candidate_count: int
    cost_units: int
    result_digest: str | None
    reason_code: str | None


@dataclass(frozen=True, slots=True)
class RetrievalProgramExecution(RecordMixin):
    identity: IdentityRecord
    format_version: str
    program_ref: str
    program_digest: str
    query_digest: str
    catalog_digest: str
    capabilities_digest: str
    candidate_limit: int
    candidates: tuple[RetrievedPrimitive, ...]
    path_receipts: tuple[RetrievalPathReceipt, ...]
    consumed_cost_units: int
    stop_reason: str

    @classmethod
    def create(
        cls,
        *,
        program: RetrievalProgram,
        query_digest: str,
        catalog_digest: str,
        capabilities_digest: str,
        candidate_limit: int,
        candidates: tuple[RetrievedPrimitive, ...],
        path_receipts: tuple[RetrievalPathReceipt, ...],
        consumed_cost_units: int,
        stop_reason: str,
    ) -> "RetrievalProgramExecution":
        key = {
            "format_version": "1.0.0",
            "program_ref": program.ref,
            "program_digest": program.digest,
            "query_digest": query_digest,
            "catalog_digest": catalog_digest,
            "capabilities_digest": capabilities_digest,
            "candidate_limit": candidate_limit,
            "candidates": [item.to_dict() for item in candidates],
            "path_receipts": [item.to_dict() for item in path_receipts],
            "consumed_cost_units": consumed_cost_units,
            "stop_reason": stop_reason,
        }
        return cls(
            IdentityRecord.create("primitive_retrieval_execution", key),
            "1.0.0",
            program.ref,
            program.digest,
            query_digest,
            catalog_digest,
            capabilities_digest,
            candidate_limit,
            candidates,
            path_receipts,
            consumed_cost_units,
            stop_reason,
        )


@dataclass(frozen=True, slots=True)
class _DocumentFeatures:
    name_phrase: str
    exact_phrases: tuple[str, ...]
    label_tokens: tuple[str, ...]
    document_tokens: tuple[str, ...]
    blocking_tokens: tuple[str, ...]
    lexical_hash: Counter[int]


class PrimitiveRetrievalIndex:
    """Immutable metadata index capable of executing versioned retrieval programs."""

    _BM25_SCALE = 1_000_000
    _BM25_K1_MILLI = 1_200
    _BM25_B_MILLI = 750

    def __init__(
        self,
        documents: Sequence[RetrievalDocument],
        *,
        semantic_retriever: SemanticPrimitiveRetriever | None = None,
    ) -> None:
        ordered = tuple(sorted(documents, key=lambda item: item.primitive_id))
        if not ordered or len({item.primitive_id for item in ordered}) != len(ordered):
            raise RetrievalProgramError(
                "retrieval documents must be non-empty and uniquely identified"
            )
        self.documents = ordered
        self.semantic_retriever = semantic_retriever
        self._by_id = {item.primitive_id: item for item in ordered}
        self._features = {
            item.primitive_id: _document_features(item) for item in ordered
        }
        self._document_frequency = Counter(
            token
            for features in self._features.values()
            for token in set(features.document_tokens)
        )
        self._average_length_milli = max(
            1,
            sum(len(item.document_tokens) for item in self._features.values())
            * 1_000
            // len(self._features),
        )
        self.catalog_digest = canonical_digest(
            [item.to_dict() for item in self.documents]
        )

    def execute(
        self,
        request: str,
        program: RetrievalProgram,
        *,
        limit: int,
        capabilities: Sequence[str] = (),
    ) -> RetrievalProgramExecution:
        if not isinstance(request, str) or not request.strip() or len(request) > 2_000:
            raise RetrievalProgramError("retrieval request must be non-empty bounded text")
        if isinstance(limit, bool) or not 1 <= limit <= len(self.documents):
            raise RetrievalProgramError("retrieval candidate limit is outside the catalog")
        available = frozenset(capabilities)
        if any(not _KEY.fullmatch(item) for item in available):
            raise RetrievalProgramError("retrieval capabilities must be namespaced")
        query_digest = sha256_digest(request.encode("utf-8"))
        capabilities_digest = canonical_digest(sorted(available))
        fused: dict[str, int] = {}
        contributions: dict[str, list[RetrievalContribution]] = {}
        receipts: list[RetrievalPathReceipt] = []
        consumed = 0
        stop_reason = "program_complete"
        stop_index: int | None = None
        target_candidates = min(program.minimum_candidates, limit)

        for index, path in enumerate(program.paths, start=1):
            if path.temperature is RepresentationTemperature.RETIRED:
                receipts.append(_skipped_receipt(index, path, "representation_retired"))
                continue
            if not set(path.required_capabilities).issubset(available):
                receipts.append(
                    _skipped_receipt(
                        index,
                        path,
                        "required_capability_unavailable",
                        status=RetrievalPathStatus.SKIPPED_CAPABILITY,
                    )
                )
                continue
            if consumed + path.cost_units > program.maximum_cost_units:
                receipts.append(
                    _skipped_receipt(
                        index,
                        path,
                        "program_cost_budget_exhausted",
                        status=RetrievalPathStatus.SKIPPED_BUDGET,
                    )
                )
                continue
            if path.family is RetrievalFamily.SEMANTIC and _evidence_is_sufficient(
                fused,
                target_candidates=target_candidates,
                margin=program.early_stop_margin_microunits,
            ):
                receipts.append(
                    _skipped_receipt(
                        index, path, "deterministic_evidence_sufficient"
                    )
                )
                continue

            before = set(fused)
            consumed += path.cost_units
            try:
                rows = self._run_path(path, request, frozenset(fused))
            except Exception as exc:  # noqa: BLE001 - isolate optional retrievers
                receipts.append(
                    RetrievalPathReceipt(
                        index,
                        path.ref,
                        path.digest,
                        path.family,
                        path.temperature,
                        RetrievalPathStatus.FAILED,
                        0,
                        0,
                        path.cost_units,
                        None,
                        _failure_code(exc),
                    )
                )
                continue
            for rank, (primitive_id, score) in enumerate(rows, start=1):
                fusion = (
                    path.fusion_weight_microunits * 1_000 // (10 + rank)
                )
                fused[primitive_id] = fused.get(primitive_id, 0) + fusion
                contributions.setdefault(primitive_id, []).append(
                    RetrievalContribution(path.ref, rank, score, fusion)
                )
            result_digest = canonical_digest(
                [
                    {"primitive_id": primitive_id, "score_microunits": score}
                    for primitive_id, score in rows
                ]
            )
            receipts.append(
                RetrievalPathReceipt(
                    index,
                    path.ref,
                    path.digest,
                    path.family,
                    path.temperature,
                    RetrievalPathStatus.EXECUTED,
                    len(rows),
                    len(set(fused) - before),
                    path.cost_units,
                    result_digest,
                    None,
                )
            )
            if (
                program.stop_after_unique_exact
                and path.family is RetrievalFamily.EXACT
                and len(rows) == 1
                and rows[0][1] == 1_000_000
            ):
                stop_reason = "unique_exact_match"
                stop_index = index
                break
            if path.ref in program.early_stop_path_refs and _evidence_is_sufficient(
                fused,
                target_candidates=target_candidates,
                margin=program.early_stop_margin_microunits,
            ):
                stop_reason = "candidate_target_with_margin"
                stop_index = index
                break

        if stop_index is not None:
            for index, path in enumerate(program.paths[stop_index:], start=stop_index + 1):
                receipts.append(_skipped_receipt(index, path, "program_early_stop"))

        candidates = _ranked_candidates(fused, contributions, limit)
        if not candidates and stop_reason == "program_complete":
            stop_reason = "no_grounded_candidates"
        result = RetrievalProgramExecution.create(
            program=program,
            query_digest=query_digest,
            catalog_digest=self.catalog_digest,
            capabilities_digest=capabilities_digest,
            candidate_limit=limit,
            candidates=candidates,
            path_receipts=tuple(receipts),
            consumed_cost_units=consumed,
            stop_reason=stop_reason,
        )
        result.identity.validate()
        return result

    def _run_path(
        self,
        path: RetrievalPathDefinition,
        request: str,
        grounded_ids: frozenset[str],
    ) -> tuple[tuple[str, int], ...]:
        if path.family is RetrievalFamily.EXACT:
            scored = self._exact_scores(request)
        elif path.family is RetrievalFamily.LABEL:
            scored = self._label_scores(request)
        elif path.family is RetrievalFamily.BM25:
            scored = self._bm25_scores(request)
        elif path.family is RetrievalFamily.BLOCKING:
            scored = self._blocking_scores(request)
        elif path.family is RetrievalFamily.LEXICAL_HASH:
            scored = self._lexical_hash_scores(request, grounded_ids)
        elif path.family is RetrievalFamily.SEMANTIC:
            scored = self._semantic_scores(request, path.candidate_limit)
        else:  # pragma: no cover - enum exhaustiveness
            raise RetrievalProgramError("unsupported retrieval family")
        rows = sorted(
            ((primitive_id, score) for primitive_id, score in scored.items() if score > 0),
            key=lambda item: (-item[1], item[0]),
        )
        return tuple(rows[: path.candidate_limit])

    def _exact_scores(self, request: str) -> dict[str, int]:
        phrase = _phrase(request)
        if not phrase:
            return {}
        result: dict[str, int] = {}
        for primitive_id, features in self._features.items():
            if phrase == features.name_phrase:
                result[primitive_id] = 1_000_000
            elif phrase in features.exact_phrases:
                result[primitive_id] = 900_000
            elif len(phrase.split()) >= 2 and any(
                item in phrase for item in features.exact_phrases if len(item.split()) >= 2
            ):
                result[primitive_id] = 750_000
        return result

    def _label_scores(self, request: str) -> dict[str, int]:
        query = tuple(_tokens(request))
        if not query:
            return {}
        query_stems = {_stem(token) for token in query}
        result: dict[str, int] = {}
        for primitive_id, features in self._features.items():
            if not _is_grounded(query, features.blocking_tokens):
                continue
            frequencies = Counter(features.label_tokens)
            exact = sum(frequencies.get(token, 0) for token in set(query))
            document_stems = {_stem(token) for token in features.label_tokens}
            stem_only = len(query_stems & document_stems) - len(
                set(query) & set(features.label_tokens)
            )
            score = exact * 100_000 + max(0, stem_only) * 35_000
            if score:
                result[primitive_id] = score
        return result

    def _bm25_scores(self, request: str) -> dict[str, int]:
        query = Counter(_tokens(request))
        result: dict[str, int] = {}
        for primitive_id, features in self._features.items():
            if not _is_grounded(tuple(query), features.blocking_tokens):
                continue
            frequencies = Counter(features.document_tokens)
            length_norm_milli = (
                1_000
                - self._BM25_B_MILLI
                + self._BM25_B_MILLI
                * len(features.document_tokens)
                * 1_000
                // self._average_length_milli
            )
            score = 0
            for token, query_frequency in query.items():
                frequency = frequencies.get(token, 0)
                if frequency == 0:
                    continue
                denominator_milli = (
                    frequency * 1_000
                    + self._BM25_K1_MILLI * length_norm_milli // 1_000
                )
                term_frequency = (
                    frequency
                    * (self._BM25_K1_MILLI + 1_000)
                    * self._BM25_SCALE
                    // denominator_milli
                )
                inverse_frequency = (
                    (len(self.documents) - self._document_frequency[token] + 1)
                    * self._BM25_SCALE
                    // (self._document_frequency[token] + 1)
                )
                score += (
                    query_frequency
                    * term_frequency
                    * inverse_frequency
                    // self._BM25_SCALE
                )
            if score:
                result[primitive_id] = score
        return result

    def _blocking_scores(self, request: str) -> dict[str, int]:
        query = tuple(dict.fromkeys(_tokens(request)))
        result: dict[str, int] = {}
        for primitive_id, features in self._features.items():
            if not _is_grounded(query, features.blocking_tokens):
                continue
            score = 0
            anchored = False
            for query_token in query:
                best = max(
                    (
                        _token_similarity_microunits(query_token, document_token)
                        for document_token in features.blocking_tokens
                    ),
                    default=0,
                )
                if best >= 500_000:
                    anchored = True
                    score += best
            if anchored:
                result[primitive_id] = score
        return result

    def _lexical_hash_scores(
        self, request: str, grounded_ids: frozenset[str]
    ) -> dict[str, int]:
        query_hash = _lexical_hash(_tokens(request))
        if not query_hash:
            return {}
        return {
            primitive_id: sum(
                count * self._features[primitive_id].lexical_hash.get(bucket, 0)
                for bucket, count in query_hash.items()
            )
            for primitive_id in grounded_ids
        }

    def _semantic_scores(self, request: str, limit: int) -> dict[str, int]:
        if self.semantic_retriever is None:
            raise RetrievalProgramError("semantic retriever is not configured")
        raw = self.semantic_retriever(request, self.documents, limit)
        if not isinstance(raw, Mapping):
            raise RetrievalProgramError("semantic retriever must return a score mapping")
        result: dict[str, int] = {}
        for primitive_id, score in raw.items():
            if primitive_id not in self._by_id:
                raise RetrievalProgramError(
                    "semantic retriever returned an unknown primitive"
                )
            if isinstance(score, bool) or not isinstance(score, int) or not 1 <= score <= 1_000_000:
                raise RetrievalProgramError(
                    "semantic retriever scores must be integer microunits"
                )
            result[primitive_id] = score
        return result


def default_primitive_retrieval_program() -> RetrievalProgram:
    exact = RetrievalPathDefinition(
        "taedri.retrieval.primitive_exact",
        "1.0.0",
        RetrievalFamily.EXACT,
        ("taedri.primitive.namespace", "taedri.primitive.name"),
        RepresentationTemperature.HOT,
        8_000_000,
        1,
        16,
    )
    labels = RetrievalPathDefinition(
        "taedri.retrieval.primitive_labels",
        "1.0.0",
        RetrievalFamily.LABEL,
        ("taedri.primitive.keyword", "taedri.primitive.use_case"),
        RepresentationTemperature.HOT,
        5_000_000,
        1,
        32,
    )
    bm25 = RetrievalPathDefinition(
        "taedri.retrieval.primitive_bm25",
        "1.0.0",
        RetrievalFamily.BM25,
        ("taedri.primitive.body_free_card_text",),
        RepresentationTemperature.WARM,
        3_000_000,
        2,
        64,
    )
    blocking = RetrievalPathDefinition(
        "taedri.retrieval.primitive_token_blocking",
        "1.0.0",
        RetrievalFamily.BLOCKING,
        ("taedri.primitive.token_prefix_block", "taedri.primitive.trigram_block"),
        RepresentationTemperature.WARM,
        2_000_000,
        2,
        64,
    )
    lexical_hash = RetrievalPathDefinition(
        "taedri.retrieval.primitive_lexical_hash",
        "1.0.0",
        RetrievalFamily.LEXICAL_HASH,
        ("uceg.embedding.lexical_hash64",),
        RepresentationTemperature.DERIVED,
        1_000_000,
        1,
        64,
    )
    semantic = RetrievalPathDefinition(
        "taedri.retrieval.primitive_semantic",
        "1.0.0",
        RetrievalFamily.SEMANTIC,
        ("taedri.primitive.semantic_embedding",),
        RepresentationTemperature.COLD,
        2_500_000,
        8,
        32,
        ("taedri.capability.semantic_embeddings",),
    )
    return RetrievalProgram(
        "taedri.retrieval.primitive_cards",
        "1.0.0",
        (exact, labels, bm25, blocking, lexical_hash, semantic),
        4,
        15,
        120_000_000,
        True,
        (bm25.ref, blocking.ref),
    )


def _document_features(document: RetrievalDocument) -> _DocumentFeatures:
    name = _tokens(document.name)
    keywords = _tokens(" ".join(document.keywords))
    use_cases = _tokens(" ".join(document.use_cases))
    summary = _tokens(document.summary)
    namespace = _tokens(document.namespace)
    document_tokens = name * 6 + keywords * 4 + use_cases * 2 + summary + namespace
    label_tokens = name * 6 + keywords * 4 + use_cases * 2
    blocking_tokens = tuple(dict.fromkeys(name + keywords + use_cases + summary))
    phrases = tuple(
        dict.fromkeys(
            item
            for item in (
                _phrase(document.name),
                *(_phrase(value) for value in document.keywords),
                *(_phrase(value) for value in document.use_cases),
            )
            if item
        )
    )
    return _DocumentFeatures(
        _phrase(document.name),
        phrases,
        label_tokens,
        document_tokens,
        blocking_tokens,
        _lexical_hash(document_tokens),
    )


def _tokens(value: str) -> tuple[str, ...]:
    return tuple(
        token for token in _TOKEN.findall(value.casefold()) if token not in _STOPWORDS
    )


def _phrase(value: str) -> str:
    return " ".join(_tokens(value))


def _stem(token: str) -> str:
    if len(token) > 5 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 5 and token.endswith("ing"):
        return token[:-3]
    if len(token) > 4 and token.endswith("ed"):
        return token[:-2]
    if len(token) > 4 and token.endswith("es"):
        return token[:-2]
    if len(token) > 3 and token.endswith("s"):
        return token[:-1]
    return token


def _trigrams(token: str) -> frozenset[str]:
    if len(token) < 3:
        return frozenset((token,))
    padded = "^" + token + "$"
    return frozenset(padded[index : index + 3] for index in range(len(padded) - 2))


def _token_similarity_microunits(left: str, right: str) -> int:
    if left == right or _stem(left) == _stem(right):
        return 1_000_000
    if min(len(left), len(right)) >= 4 and (
        left.startswith(right) or right.startswith(left)
    ):
        return 750_000
    if min(len(left), len(right)) < 4:
        return 0
    left_grams = _trigrams(left)
    right_grams = _trigrams(right)
    return len(left_grams & right_grams) * 1_000_000 // len(left_grams | right_grams)


def _is_grounded(
    query_tokens: Sequence[str], document_tokens: Sequence[str]
) -> bool:
    """Require enough independent lexical anchors for the request's breadth."""

    unique_query = tuple(dict.fromkeys(query_tokens))
    anchor_count = sum(
        any(
            _token_similarity_microunits(query_token, document_token) >= 750_000
            for document_token in document_tokens
        )
        for query_token in unique_query
    )
    required = 1 if len(unique_query) <= 3 else 2 if len(unique_query) <= 5 else 3
    return anchor_count >= required


def _lexical_hash(tokens: Sequence[str]) -> Counter[int]:
    result: Counter[int] = Counter()
    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        result[int.from_bytes(digest[:2], "big") % 512] += 1
    return result


def _evidence_is_sufficient(
    fused: Mapping[str, int], *, target_candidates: int, margin: int
) -> bool:
    if len(fused) < target_candidates:
        return False
    ordered = sorted(fused.values(), reverse=True)
    if len(ordered) == 1:
        return True
    return ordered[0] - ordered[1] >= margin


def _ranked_candidates(
    fused: Mapping[str, int],
    contributions: Mapping[str, list[RetrievalContribution]],
    limit: int,
) -> tuple[RetrievedPrimitive, ...]:
    ordered = sorted(fused.items(), key=lambda item: (-item[1], item[0]))[:limit]
    return tuple(
        RetrievedPrimitive(
            primitive_id,
            rank,
            score,
            tuple(contributions[primitive_id]),
        )
        for rank, (primitive_id, score) in enumerate(ordered, start=1)
    )


def _skipped_receipt(
    sequence: int,
    path: RetrievalPathDefinition,
    reason_code: str,
    *,
    status: RetrievalPathStatus = RetrievalPathStatus.SKIPPED_POLICY,
) -> RetrievalPathReceipt:
    return RetrievalPathReceipt(
        sequence,
        path.ref,
        path.digest,
        path.family,
        path.temperature,
        status,
        0,
        0,
        0,
        None,
        reason_code,
    )


def _failure_code(exc: Exception) -> str:
    name = re.sub(r"[^a-z0-9]+", "_", type(exc).__name__.casefold()).strip("_")
    return f"retrieval_path_{name or 'failure'}"


__all__ = (
    "PrimitiveRetrievalIndex",
    "RepresentationTemperature",
    "RetrievalContribution",
    "RetrievalDocument",
    "RetrievalFamily",
    "RetrievalPathDefinition",
    "RetrievalPathReceipt",
    "RetrievalPathStatus",
    "RetrievalProgram",
    "RetrievalProgramError",
    "RetrievalProgramExecution",
    "RetrievalProgramRegistry",
    "RetrievedPrimitive",
    "SemanticPrimitiveRetriever",
    "default_primitive_retrieval_program",
)
