"""Body-free primitive interception with executable, independent verification.

The model sees only a natural-language request and released ``PrimitiveCard``
metadata.  It never sees capsule bodies or hidden verifier cases.  A selected pack
is resolved through a catalog-scoped handle, digest checked, and executed by the
existing deterministic one-stage pipeline executor before the selection is accepted.
"""

from __future__ import annotations

import json
import platform
import re
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping, Sequence

from .canonical import canonical_json_bytes, sha256_digest
from .contracts import RecordMixin
from .identity import IdentityRecord
from .model_providers import ChatMessage, ChatProvider, ModelUsageReceipt
from .primitive_capsules import decode_primitive_pack
from .primitives.edges import PrimitiveInterface, validate_primitive_graph
from .primitives.wiring import (
    ExactPrimitiveWirePlanner,
    LocalDeterministicPythonPipelineExecutor,
)

_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_TASK_ID = re.compile(r"^[a-z][a-z0-9_.-]{2,127}$")
_NAME = re.compile(r"^[a-z][a-z0-9.-]{1,127}$")
_TOKEN = re.compile(r"[a-z0-9]+")
_ERROR_TOKEN = re.compile(r"[^a-z0-9]+")
_IDENTITY_PREFIX = "uceg:v1:"
_CAMPAIGN_FORMAT_VERSION = "2.0.0"
_LEGACY_CAMPAIGN_FORMAT_VERSION = "1.0.0"
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


class PromptInterceptionError(ValueError):
    """Raised when checked interception evidence is malformed or unavailable."""


class RetrievalArm(str, Enum):
    FULL_CATALOG = "full_catalog"
    DETERMINISTIC_SHORTLIST = "deterministic_shortlist"


@dataclass(frozen=True, slots=True)
class ScopedArtifactHandle(RecordMixin):
    """Non-filesystem authority handed from selection to the checked resolver."""

    scope: str
    location: str
    pack_id: str
    digest: str
    size_bytes: int

    def __post_init__(self) -> None:
        if self.scope != "checked_primitive_catalog":
            raise PromptInterceptionError("primitive pack handle has an invalid scope")
        if not self.location.startswith("cohort:") or "\\" in self.location:
            raise PromptInterceptionError("primitive pack handle location is invalid")
        relative = self.location.removeprefix("cohort:")
        pure = PurePosixPath(relative)
        if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
            raise PromptInterceptionError("primitive pack handle location is unsafe")
        _require_uceg_id(self.pack_id, "primitive_pack")
        _require_digest(self.digest, "primitive pack")
        if isinstance(self.size_bytes, bool) or self.size_bytes <= 0:
            raise PromptInterceptionError("primitive pack size must be positive")


@dataclass(frozen=True, slots=True)
class PrimitiveCard(RecordMixin):
    """Released, body-free metadata safe to place in a teacher prompt."""

    primitive_id: str
    release_id: str
    revision_id: str
    pack_id: str
    namespace: str
    name: str
    summary: str
    keywords: tuple[str, ...]
    use_cases: tuple[str, ...]
    pack_digest: str
    pack_location: str
    artifact_handle: ScopedArtifactHandle

    def __post_init__(self) -> None:
        _require_uceg_id(self.primitive_id, "primitive")
        _require_uceg_id(self.release_id, "primitive_release")
        _require_uceg_id(self.revision_id, "primitive_revision")
        _require_uceg_id(self.pack_id, "primitive_pack")
        if not _NAME.fullmatch(self.namespace) or not _NAME.fullmatch(self.name):
            raise PromptInterceptionError("primitive namespace or name is invalid")
        if len(self.summary.strip()) < 10 or len(self.summary) > 500:
            raise PromptInterceptionError("primitive card summary is invalid")
        if not self.keywords or not self.use_cases or any(
            not isinstance(item, str) or not item.strip()
            for item in self.keywords + self.use_cases
        ):
            raise PromptInterceptionError("primitive card descriptor fields are invalid")
        _require_digest(self.pack_digest, "primitive pack")
        if (
            self.pack_id != self.artifact_handle.pack_id
            or self.pack_digest != self.artifact_handle.digest
            or self.pack_location != self.artifact_handle.location
        ):
            raise PromptInterceptionError("primitive card does not bind its pack handle")

    def teacher_value(self, route_handle: str) -> dict[str, Any]:
        """Return compact capability metadata, never padded registry identifiers."""

        return {
            "route_handle": route_handle,
            "name": self.name,
            "summary": self.summary,
            "keywords": list(self.keywords),
            "use_cases": list(self.use_cases),
        }


@dataclass(frozen=True, slots=True)
class _ReleasedPrimitiveAsset:
    card: PrimitiveCard
    path: Path
    interface: PrimitiveInterface


class ReleasedPrimitiveCatalog:
    """Immutable view over checked cohort packs and their released identifiers."""

    def __init__(self, assets: Iterable[_ReleasedPrimitiveAsset]) -> None:
        ordered = tuple(sorted(assets, key=lambda item: item.card.primitive_id))
        if not ordered:
            raise PromptInterceptionError("released primitive catalog cannot be empty")
        by_pack = {item.card.pack_id: item for item in ordered}
        by_primitive = {item.card.primitive_id: item for item in ordered}
        if len(by_pack) != len(ordered) or len(by_primitive) != len(ordered):
            raise PromptInterceptionError("released primitive catalog identities must be unique")
        self._assets = ordered
        self._by_pack = by_pack
        self._by_primitive = by_primitive
        self.cards = tuple(item.card for item in ordered)
        self.digest = sha256_digest(
            canonical_json_bytes([item.to_dict() for item in self.cards])
        )

    @classmethod
    def load_checked_cohort(cls, cohort_root: str | Path) -> "ReleasedPrimitiveCatalog":
        root = Path(cohort_root).expanduser().resolve()
        run_path = root / "run.json"
        try:
            run = json.loads(run_path.read_bytes())
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise PromptInterceptionError("checked cohort run.json is unavailable") from exc
        if not isinstance(run, Mapping) or run.get("status") != "passed":
            raise PromptInterceptionError("primitive cohort is not a passed release run")
        records = run.get("records")
        if not isinstance(records, list) or not records:
            raise PromptInterceptionError("primitive cohort has no release records")
        assets = tuple(_load_released_asset(root, value) for value in records)
        if run.get("pack_count") != len(assets):
            raise PromptInterceptionError("primitive cohort pack count does not validate")
        return cls(assets)

    def card(self, primitive_id: str) -> PrimitiveCard:
        try:
            return self._by_primitive[primitive_id].card
        except KeyError as exc:
            raise PromptInterceptionError(
                "selected primitive is outside the checked catalog"
            ) from exc

    def resolve(
        self, handle: ScopedArtifactHandle
    ) -> tuple[bytes, PrimitiveInterface]:
        """Resolve only an exact catalog-issued handle and recheck the pack digest."""

        try:
            asset = self._by_pack[handle.pack_id]
        except KeyError as exc:
            raise PromptInterceptionError("artifact handle is outside the checked catalog") from exc
        if handle != asset.card.artifact_handle:
            raise PromptInterceptionError("artifact handle does not match the catalog record")
        try:
            encoded = asset.path.read_bytes()
        except OSError as exc:
            raise PromptInterceptionError("checked primitive pack is unavailable") from exc
        if len(encoded) != handle.size_bytes or sha256_digest(encoded) != handle.digest:
            raise PromptInterceptionError("checked primitive pack digest does not validate")
        return encoded, asset.interface


def _load_released_asset(root: Path, raw: object) -> _ReleasedPrimitiveAsset:
    if not isinstance(raw, Mapping):
        raise PromptInterceptionError("primitive release record must be an object")
    namespace = _required_string(raw, "namespace")
    name = _required_string(raw, "name")
    if not _NAME.fullmatch(namespace) or not _NAME.fullmatch(name):
        raise PromptInterceptionError("primitive release namespace or name is invalid")
    filename = f"{namespace}--{name}.tcgpack"
    path = root / "packs" / filename
    try:
        encoded = path.read_bytes()
    except OSError as exc:
        raise PromptInterceptionError("checked primitive pack is missing") from exc
    digest = sha256_digest(encoded)
    if raw.get("pack_digest") != digest or raw.get("pack_bytes") != len(encoded):
        raise PromptInterceptionError("cohort release record does not match its pack bytes")
    manifest, payloads = decode_primitive_pack(encoded)
    identity = manifest.get("identity")
    if not isinstance(identity, Mapping) or identity.get("id") != raw.get("pack_id"):
        raise PromptInterceptionError("primitive pack identity does not match its release record")
    entries = manifest.get("entries")
    if not isinstance(entries, list) or not entries:
        raise PromptInterceptionError("primitive pack entry manifest is invalid")
    revision_ids = {
        item.get("revision_id") for item in entries if isinstance(item, Mapping)
    }
    tree_ids = {item.get("tree_id") for item in entries if isinstance(item, Mapping)}
    if revision_ids != {raw.get("revision_id")} or tree_ids != {raw.get("tree_id")}:
        raise PromptInterceptionError("primitive pack release binding does not validate")
    by_path, by_role = _pack_payload_index(entries, payloads)
    contract_path, contract = _one_pack_json(by_role, "contract")
    _, descriptor = _one_pack_json(by_role, "descriptor")
    _, runtime = _one_pack_json(by_role, "runtime")
    _, graph = _one_pack_json(by_role, "graph_delta")
    interface = validate_primitive_graph(
        graph,
        capsule_paths=by_path,
        contract=contract,
        contract_path=contract_path,
        language=_required_string(runtime, "language"),
        runtime_version=_required_string(runtime, "runtime_version"),
        entrypoint_path=_required_string(runtime, "entrypoint_path"),
        entrypoint=_required_string(runtime, "entrypoint"),
    )
    summary = _required_string(descriptor, "summary")
    keywords = _required_string_tuple(descriptor, "keywords")
    use_cases = _required_string_tuple(descriptor, "use_cases")
    location = f"cohort:{root.name}/packs/{filename}"
    handle = ScopedArtifactHandle(
        "checked_primitive_catalog",
        location,
        _required_string(raw, "pack_id"),
        digest,
        len(encoded),
    )
    card = PrimitiveCard(
        _required_string(raw, "primitive_id"),
        _required_string(raw, "release_id"),
        _required_string(raw, "revision_id"),
        handle.pack_id,
        namespace,
        name,
        summary,
        keywords,
        use_cases,
        digest,
        location,
        handle,
    )
    return _ReleasedPrimitiveAsset(card, path, interface)


def _pack_payload_index(
    entries: Sequence[object], payloads: Mapping[str, bytes]
) -> tuple[dict[str, tuple[bytes, str]], dict[str, list[tuple[str, bytes]]]]:
    by_path: dict[str, tuple[bytes, str]] = {}
    by_role: dict[str, list[tuple[str, bytes]]] = {}
    for raw in entries:
        if not isinstance(raw, Mapping):
            raise PromptInterceptionError("primitive pack entry must be an object")
        path = _required_string(raw, "path")
        role = _required_string(raw, "role")
        blob = raw.get("blob")
        if not isinstance(blob, Mapping):
            raise PromptInterceptionError("primitive pack entry blob is invalid")
        digest = _required_string(blob, "digest")
        if path in by_path or digest not in payloads:
            raise PromptInterceptionError("primitive pack entry payload is missing or duplicated")
        content = payloads[digest]
        if sha256_digest(content) != digest:
            raise PromptInterceptionError("primitive pack payload digest does not validate")
        by_path[path] = (content, digest)
        by_role.setdefault(role, []).append((path, content))
    return by_path, by_role


def _one_pack_json(
    by_role: Mapping[str, list[tuple[str, bytes]]], role: str
) -> tuple[str, Mapping[str, Any]]:
    matches = by_role.get(role, [])
    if len(matches) != 1:
        raise PromptInterceptionError(f"primitive pack requires one {role} record")
    path, encoded = matches[0]
    try:
        value = json.loads(encoded)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PromptInterceptionError(f"primitive pack {role} record is invalid JSON") from exc
    if not isinstance(value, Mapping):
        raise PromptInterceptionError(f"primitive pack {role} record must be an object")
    return path, value


@dataclass(frozen=True, slots=True)
class RankedCandidate(RecordMixin):
    route_handle: str
    primitive_id: str
    rank: int
    score_microunits: int | None


class DeterministicBM25Shortlister:
    """Integer-only BM25-like local retrieval over body-free card metadata."""

    _SCALE = 1_000_000
    _K1_MILLI = 1_200
    _B_MILLI = 750

    def __init__(self, cards: Sequence[PrimitiveCard]) -> None:
        self.cards = tuple(sorted(cards, key=lambda item: item.primitive_id))
        if not self.cards:
            raise PromptInterceptionError("shortlister requires primitive cards")
        self._documents = {card.primitive_id: _weighted_card_tokens(card) for card in self.cards}
        self._document_frequency = Counter(
            token for terms in self._documents.values() for token in set(terms)
        )
        self._average_length_milli = max(
            1,
            sum(len(value) for value in self._documents.values())
            * 1_000
            // len(self._documents),
        )

    def full_catalog(self) -> tuple[RankedCandidate, ...]:
        return tuple(
            RankedCandidate(f"c{index:03d}", card.primitive_id, index, None)
            for index, card in enumerate(self.cards, start=1)
        )

    def shortlist(self, request: str, limit: int) -> tuple[RankedCandidate, ...]:
        if isinstance(limit, bool) or not 1 <= limit <= len(self.cards):
            raise PromptInterceptionError("shortlist limit is outside the catalog")
        query = Counter(_tokens(request))
        scored = [
            (self._score(query, self._documents[card.primitive_id]), card.primitive_id)
            for card in self.cards
        ]
        scored = [item for item in scored if item[0] > 0]
        scored.sort(key=lambda item: (-item[0], item[1]))
        return tuple(
            RankedCandidate(f"c{rank:03d}", primitive_id, rank, score)
            for rank, (score, primitive_id) in enumerate(scored[:limit], start=1)
        )

    def _score(self, query: Counter[str], document: tuple[str, ...]) -> int:
        frequencies = Counter(document)
        length_norm_milli = (
            1_000
            - self._B_MILLI
            + self._B_MILLI * len(document) * 1_000 // self._average_length_milli
        )
        result = 0
        count = len(self.cards)
        for token, query_frequency in query.items():
            frequency = frequencies.get(token, 0)
            if frequency == 0:
                continue
            denominator_milli = (
                frequency * 1_000
                + self._K1_MILLI * length_norm_milli // 1_000
            )
            term_frequency = (
                frequency
                * (self._K1_MILLI + 1_000)
                * self._SCALE
                // denominator_milli
            )
            inverse_frequency = (
                (count - self._document_frequency[token] + 1)
                * self._SCALE
                // (self._document_frequency[token] + 1)
            )
            result += (
                query_frequency * term_frequency * inverse_frequency // self._SCALE
            )
        return result


@dataclass(frozen=True, slots=True)
class CandidateRejection(RecordMixin):
    primitive_id: str
    reason_code: str


@dataclass(frozen=True, slots=True)
class PromptInterceptionReceipt(RecordMixin):
    identity: IdentityRecord
    format_version: str
    trajectory_id: str
    task_id: str
    step_index: int
    request_digest: str
    catalog_digest: str
    retrieval_arm: RetrievalArm
    shortlist_limit: int | None
    candidates: tuple[RankedCandidate, ...]
    rejections: tuple[CandidateRejection, ...]
    selected_primitive_id: str | None
    selected_release_id: str | None
    selected_pack_id: str | None
    artifact_handle: ScopedArtifactHandle | None
    status: str
    error_code: str | None
    model_usage: ModelUsageReceipt

    @classmethod
    def create(
        cls,
        *,
        trajectory_id: str,
        task_id: str,
        step_index: int,
        request_digest: str,
        catalog_digest: str,
        retrieval_arm: RetrievalArm,
        shortlist_limit: int | None,
        candidates: tuple[RankedCandidate, ...],
        rejections: tuple[CandidateRejection, ...],
        selection: PrimitiveCard | None,
        status: str,
        error_code: str | None,
        model_usage: ModelUsageReceipt,
    ) -> "PromptInterceptionReceipt":
        if status not in {"selected", "teacher_rejected"}:
            raise PromptInterceptionError("interception receipt status is invalid")
        if (status == "selected") != (selection is not None):
            raise PromptInterceptionError("interception selection and status disagree")
        if (status == "teacher_rejected") != (error_code is not None):
            raise PromptInterceptionError("interception error evidence is incomplete")
        model_usage.identity.validate()
        key = {
            "format_version": "1.0.0",
            "trajectory_id": trajectory_id,
            "task_id": task_id,
            "step_index": step_index,
            "request_digest": request_digest,
            "catalog_digest": catalog_digest,
            "retrieval_arm": retrieval_arm.value,
            "shortlist_limit": shortlist_limit,
            "candidates": [item.to_dict() for item in candidates],
            "rejections": [item.to_dict() for item in rejections],
            "selected_primitive_id": selection.primitive_id if selection else None,
            "selected_release_id": selection.release_id if selection else None,
            "selected_pack_id": selection.pack_id if selection else None,
            "artifact_handle": selection.artifact_handle.to_dict() if selection else None,
            "status": status,
            "error_code": error_code,
            "model_usage": model_usage.to_dict(),
        }
        return cls(
            IdentityRecord.create("prompt_interception_receipt", key),
            "1.0.0",
            trajectory_id,
            task_id,
            step_index,
            request_digest,
            catalog_digest,
            retrieval_arm,
            shortlist_limit,
            candidates,
            rejections,
            selection.primitive_id if selection else None,
            selection.release_id if selection else None,
            selection.pack_id if selection else None,
            selection.artifact_handle if selection else None,
            status,
            error_code,
            model_usage,
        )


class PromptInterceptor:
    """Ask a bounded teacher to select from body-free released cards."""

    def __init__(
        self,
        catalog: ReleasedPrimitiveCatalog,
        provider: ChatProvider,
        *,
        shortlist_limit: int = 4,
    ) -> None:
        if isinstance(shortlist_limit, bool) or not 1 <= shortlist_limit < len(catalog.cards):
            raise PromptInterceptionError(
                "shortlist must be positive and smaller than the full catalog"
            )
        self.catalog = catalog
        self.provider = provider
        self.shortlist_limit = shortlist_limit
        self.shortlister = DeterministicBM25Shortlister(catalog.cards)

    def messages(
        self, task: "NaturalPrimitiveTask", retrieval_arm: RetrievalArm
    ) -> tuple[tuple[ChatMessage, ...], tuple[RankedCandidate, ...]]:
        if retrieval_arm is RetrievalArm.FULL_CATALOG:
            ranking = self.shortlister.full_catalog()
        else:
            ranking = self.shortlister.shortlist(task.request, self.shortlist_limit)
        cards = [
            self.catalog.card(item.primitive_id).teacher_value(item.route_handle)
            for item in ranking
        ]
        user_value = {
            "schema_version": "1.0.0",
            "task_request": task.request,
            "primitive_cards": cards,
        }
        messages = (
            ChatMessage(
                "system",
                "Select at most one released primitive whose stated capability best "
                "satisfies the task. Route handles are opaque and primitive cards are "
                "metadata only. Reply with one JSON object, no markdown or extra keys. "
                "Select using "
                '{"selected_route_handle":"<candidate route_handle>",'
                '"reason_code":"capability_match"}, or abstain using '
                '{"selected_route_handle":null,'
                '"reason_code":"no_suitable_candidate"}.',
            ),
            ChatMessage("user", canonical_json_bytes(user_value).decode("utf-8")),
        )
        return messages, ranking

    def intercept(
        self,
        task: "NaturalPrimitiveTask",
        retrieval_arm: RetrievalArm,
        *,
        model: str,
        seed: int,
        max_completion_tokens: int,
    ) -> PromptInterceptionReceipt:
        messages, ranking = self.messages(task, retrieval_arm)
        try:
            result = self.provider.chat(
                model,
                messages,
                seed=seed,
                temperature="0",
                max_completion_tokens=max_completion_tokens,
            )
        except Exception as exc:  # noqa: BLE001 - normalize structural providers
            raise _TeacherProviderFailure(_exception_code("provider", exc)) from exc
        candidate_ids = {item.primitive_id for item in ranking}
        routes = {item.route_handle: item.primitive_id for item in ranking}
        excluded = sorted(
            set(card.primitive_id for card in self.catalog.cards) - candidate_ids
        )
        try:
            selected_route = _parse_teacher_selection(result.content, set(routes))
            if selected_route is None:
                raise _TeacherOutputError("teacher_abstained_no_suitable_candidate")
            selected_id = routes[selected_route]
        except _TeacherOutputError as exc:
            rejections = tuple(
                CandidateRejection(item, "deterministic_shortlist_excluded")
                for item in excluded
            ) + tuple(
                CandidateRejection(item.primitive_id, exc.code) for item in ranking
            )
            return PromptInterceptionReceipt.create(
                trajectory_id=task.trajectory_id,
                task_id=task.task_id,
                step_index=task.step_index,
                request_digest=task.request_digest,
                catalog_digest=self.catalog.digest,
                retrieval_arm=retrieval_arm,
                shortlist_limit=(
                    None
                    if retrieval_arm is RetrievalArm.FULL_CATALOG
                    else self.shortlist_limit
                ),
                candidates=ranking,
                rejections=rejections,
                selection=None,
                status="teacher_rejected",
                error_code=exc.code,
                model_usage=result.receipt,
            )
        selection = self.catalog.card(selected_id)
        rejections = tuple(
            CandidateRejection(item, "deterministic_shortlist_excluded")
            for item in excluded
        ) + tuple(
            CandidateRejection(item.primitive_id, "teacher_not_selected")
            for item in ranking
            if item.primitive_id != selected_id
        )
        return PromptInterceptionReceipt.create(
            trajectory_id=task.trajectory_id,
            task_id=task.task_id,
            step_index=task.step_index,
            request_digest=task.request_digest,
            catalog_digest=self.catalog.digest,
            retrieval_arm=retrieval_arm,
            shortlist_limit=(
                None
                if retrieval_arm is RetrievalArm.FULL_CATALOG
                else self.shortlist_limit
            ),
            candidates=ranking,
            rejections=rejections,
            selection=selection,
            status="selected",
            error_code=None,
            model_usage=result.receipt,
        )


class _TeacherOutputError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class _TeacherProviderFailure(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _parse_teacher_selection(content: str, route_handles: set[str]) -> str | None:
    if len(content.encode("utf-8")) > 4_096:
        raise _TeacherOutputError("teacher_output_too_large")

    def strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise _TeacherOutputError("teacher_duplicate_json_key")
            result[key] = value
        return result

    try:
        value = json.loads(content, object_pairs_hook=strict_object)
    except _TeacherOutputError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _TeacherOutputError("teacher_invalid_json") from exc
    if not isinstance(value, Mapping) or set(value) != {
        "selected_route_handle",
        "reason_code",
    }:
        raise _TeacherOutputError("teacher_schema_mismatch")
    reason = value.get("reason_code")
    selected = value.get("selected_route_handle")
    if selected is None and reason == "no_suitable_candidate":
        return None
    if reason != "capability_match":
        raise _TeacherOutputError("teacher_reason_code_invalid")
    if not isinstance(selected, str) or selected not in route_handles:
        raise _TeacherOutputError("teacher_selection_outside_candidates")
    return selected


@dataclass(frozen=True, slots=True)
class HiddenVerificationCase(RecordMixin):
    case_id: str
    input_value: Any
    expected_output: Any

    def __post_init__(self) -> None:
        if not _TASK_ID.fullmatch(self.case_id):
            raise PromptInterceptionError("hidden verification case id is invalid")
        canonical_json_bytes(self.input_value)
        canonical_json_bytes(self.expected_output)

    @property
    def input_digest(self) -> str:
        return sha256_digest(canonical_json_bytes(self.input_value))

    @property
    def expected_digest(self) -> str:
        return sha256_digest(canonical_json_bytes(self.expected_output))


@dataclass(frozen=True, slots=True)
class NaturalPrimitiveTask(RecordMixin):
    task_id: str
    trajectory_id: str
    step_index: int
    domain: str
    request: str
    hidden_cases: tuple[HiddenVerificationCase, ...]

    def __post_init__(self) -> None:
        if not _TASK_ID.fullmatch(self.task_id) or not _TASK_ID.fullmatch(
            self.trajectory_id
        ):
            raise PromptInterceptionError("task or trajectory id is invalid")
        if isinstance(self.step_index, bool) or self.step_index < 0:
            raise PromptInterceptionError("task step index must be non-negative")
        if self.domain not in {"data_cleaning", "data_engineering", "data_science"}:
            raise PromptInterceptionError("natural task domain is invalid")
        if len(self.request.strip()) < 20 or len(self.request) > 2_000:
            raise PromptInterceptionError("natural task request is invalid")
        if len(self.hidden_cases) < 2:
            raise PromptInterceptionError("natural task requires at least two hidden cases")
        if len({item.case_id for item in self.hidden_cases}) != len(self.hidden_cases):
            raise PromptInterceptionError("hidden verification case ids must be unique")

    @property
    def request_digest(self) -> str:
        return sha256_digest(self.request.encode("utf-8"))

    @property
    def hidden_case_set_digest(self) -> str:
        return sha256_digest(
            canonical_json_bytes(
                [
                    {
                        "case_id": item.case_id,
                        "input_digest": item.input_digest,
                        "expected_digest": item.expected_digest,
                    }
                    for item in self.hidden_cases
                ]
            )
        )


@dataclass(frozen=True, slots=True)
class CampaignTaskManifestEntry(RecordMixin):
    """Public, digest-only description of one task step expected in a campaign."""

    trajectory_id: str
    task_id: str
    step_index: int
    request_digest: str
    hidden_case_set_digest: str

    @classmethod
    def from_task(cls, task: NaturalPrimitiveTask) -> "CampaignTaskManifestEntry":
        return cls(
            task.trajectory_id,
            task.task_id,
            task.step_index,
            task.request_digest,
            task.hidden_case_set_digest,
        )

    def __post_init__(self) -> None:
        if not _TASK_ID.fullmatch(self.task_id) or not _TASK_ID.fullmatch(
            self.trajectory_id
        ):
            raise PromptInterceptionError("campaign manifest task context is invalid")
        if isinstance(self.step_index, bool) or self.step_index < 0:
            raise PromptInterceptionError("campaign manifest step index is invalid")
        _require_digest(self.request_digest, "campaign manifest request")
        _require_digest(
            self.hidden_case_set_digest, "campaign manifest hidden case set"
        )


@dataclass(frozen=True, slots=True)
class CampaignExpectedCounts(RecordMixin):
    """Expected Cartesian-product cardinalities bound into the campaign identity."""

    task_count: int
    seed_count: int
    task_seed_count: int
    retrieval_conditions_per_task_seed: int
    arm_count: int
    matched_pair_count: int

    @classmethod
    def create(
        cls, *, task_count: int, seed_count: int
    ) -> "CampaignExpectedCounts":
        task_seed_count = task_count * seed_count
        return cls(
            task_count,
            seed_count,
            task_seed_count,
            2,
            task_seed_count * 2,
            task_seed_count,
        )

    def __post_init__(self) -> None:
        values = (
            self.task_count,
            self.seed_count,
            self.task_seed_count,
            self.retrieval_conditions_per_task_seed,
            self.arm_count,
            self.matched_pair_count,
        )
        if any(isinstance(value, bool) or value <= 0 for value in values):
            raise PromptInterceptionError("campaign expected counts must be positive")
        if self.retrieval_conditions_per_task_seed != 2:
            raise PromptInterceptionError(
                "campaign must declare exactly two retrieval conditions"
            )
        if self.task_seed_count != self.task_count * self.seed_count:
            raise PromptInterceptionError("campaign task/seed count is inconsistent")
        if self.arm_count != self.task_seed_count * 2:
            raise PromptInterceptionError("campaign arm count is inconsistent")
        if self.matched_pair_count != self.task_seed_count:
            raise PromptInterceptionError("campaign pair count is inconsistent")


@dataclass(frozen=True, slots=True)
class CampaignExecutionPolicy(RecordMixin):
    """Frozen disclosure, provider-boundary, and verifier execution policy."""

    prompt_template_version: str
    campaign_harness_version: str
    shortlister_version: str
    verifier_version: str
    executor_version: str
    python_runtime_version: str
    temperature: str
    request_timeout_ms: int
    max_response_bytes: int
    provider_endpoint_policy: str
    prompt_harness_digest: str
    verifier_runtime_digest: str
    provider_policy_digest: str

    @classmethod
    def create(
        cls,
        *,
        request_timeout_ms: int,
        max_response_bytes: int,
    ) -> "CampaignExecutionPolicy":
        prompt_template_version = "prompt-interception-teacher-v1"
        campaign_harness_version = "prompt-interception-campaign-v2"
        shortlister_version = "deterministic-integer-bm25-v1"
        verifier_version = "independent-pack-verifier-v2"
        executor_version = "local-deterministic-python-exact-wire-v1"
        python_runtime_version = platform.python_version()
        temperature = "0"
        provider_endpoint_policy = "https-or-loopback-http-no-redirects-v1"
        prompt_harness_digest = sha256_digest(
            canonical_json_bytes(
                {
                    "prompt_template_version": prompt_template_version,
                    "campaign_harness_version": campaign_harness_version,
                    "shortlister_version": shortlister_version,
                    "temperature": temperature,
                }
            )
        )
        verifier_runtime_digest = sha256_digest(
            canonical_json_bytes(
                {
                    "verifier_version": verifier_version,
                    "executor_version": executor_version,
                    "python_runtime_version": python_runtime_version,
                }
            )
        )
        provider_policy_digest = sha256_digest(
            canonical_json_bytes(
                {
                    "temperature": temperature,
                    "request_timeout_ms": request_timeout_ms,
                    "max_response_bytes": max_response_bytes,
                    "provider_endpoint_policy": provider_endpoint_policy,
                }
            )
        )
        return cls(
            prompt_template_version,
            campaign_harness_version,
            shortlister_version,
            verifier_version,
            executor_version,
            python_runtime_version,
            temperature,
            request_timeout_ms,
            max_response_bytes,
            provider_endpoint_policy,
            prompt_harness_digest,
            verifier_runtime_digest,
            provider_policy_digest,
        )

    def __post_init__(self) -> None:
        text_fields = (
            self.prompt_template_version,
            self.campaign_harness_version,
            self.shortlister_version,
            self.verifier_version,
            self.executor_version,
            self.python_runtime_version,
            self.temperature,
            self.provider_endpoint_policy,
            self.prompt_harness_digest,
            self.verifier_runtime_digest,
            self.provider_policy_digest,
        )
        if any(not value for value in text_fields):
            raise PromptInterceptionError("campaign execution policy is incomplete")
        if self.temperature != "0":
            raise PromptInterceptionError("campaign teacher temperature must be zero")
        if (
            isinstance(self.request_timeout_ms, bool)
            or self.request_timeout_ms <= 0
            or isinstance(self.max_response_bytes, bool)
            or self.max_response_bytes <= 0
        ):
            raise PromptInterceptionError("campaign provider bounds must be positive")
        for value in (
            self.prompt_harness_digest,
            self.verifier_runtime_digest,
            self.provider_policy_digest,
        ):
            _require_digest(value, "campaign component policy")

    @property
    def digest(self) -> str:
        return sha256_digest(canonical_json_bytes(self.to_dict()))


def load_natural_primitive_tasks(path: str | Path) -> tuple[NaturalPrimitiveTask, ...]:
    try:
        value = json.loads(Path(path).expanduser().read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PromptInterceptionError("natural primitive task fixture is unavailable") from exc
    if not isinstance(value, Mapping) or value.get("schema_version") != "1.0.0":
        raise PromptInterceptionError("natural primitive task fixture version is invalid")
    raw_tasks = value.get("tasks")
    if not isinstance(raw_tasks, list) or not raw_tasks:
        raise PromptInterceptionError("natural primitive task fixture has no tasks")
    tasks: list[NaturalPrimitiveTask] = []
    for raw in raw_tasks:
        if not isinstance(raw, Mapping):
            raise PromptInterceptionError("natural primitive task must be an object")
        raw_cases = raw.get("hidden_cases")
        if not isinstance(raw_cases, list):
            raise PromptInterceptionError("natural primitive task hidden cases are invalid")
        cases = tuple(
            HiddenVerificationCase(
                _required_string(item, "case_id"),
                item.get("input"),
                item.get("expected"),
            )
            for item in raw_cases
            if isinstance(item, Mapping)
        )
        if len(cases) != len(raw_cases):
            raise PromptInterceptionError("natural primitive hidden case must be an object")
        tasks.append(
            NaturalPrimitiveTask(
                _required_string(raw, "task_id"),
                _required_string(raw, "trajectory_id"),
                _required_integer(raw, "step_index"),
                _required_string(raw, "domain"),
                _required_string(raw, "request"),
                cases,
            )
        )
    if len({item.task_id for item in tasks}) != len(tasks):
        raise PromptInterceptionError("natural primitive task ids must be unique")
    return tuple(tasks)


@dataclass(frozen=True, slots=True)
class VerificationCaseObservation(RecordMixin):
    case_id: str
    input_digest: str
    expected_digest: str
    output_digest: str | None
    pipeline_receipt_id: str | None
    passed: bool
    error_code: str | None


@dataclass(frozen=True, slots=True)
class VerificationOccurrenceReceipt(RecordMixin):
    """Arm-specific, replay-stable authority for one verifier execution.

    The run identifier is the occurrence identity itself.  It is derived from the
    frozen campaign arm and exact interception receipt rather than randomness, so
    deterministic replay is possible while the two A/B executions cannot collapse.
    """

    identity: IdentityRecord
    format_version: str
    verification_run_id: str
    interception_receipt_id: str
    trajectory_id: str
    task_id: str
    step_index: int
    request_digest: str
    hidden_case_set_digest: str
    retrieval_arm: RetrievalArm
    attempt_index: int
    pair_order: int
    provider_id: str
    model_requested: str
    seed: int
    max_completion_tokens: int
    execution_policy_digest: str

    @classmethod
    def create(
        cls,
        *,
        task: NaturalPrimitiveTask,
        interception: PromptInterceptionReceipt,
        retrieval_arm: RetrievalArm,
        attempt_index: int,
        pair_order: int,
        provider_id: str,
        model_requested: str,
        seed: int,
        max_completion_tokens: int,
        execution_policy_digest: str,
    ) -> "VerificationOccurrenceReceipt":
        if (
            interception.task_id != task.task_id
            or interception.trajectory_id != task.trajectory_id
            or interception.step_index != task.step_index
            or interception.request_digest != task.request_digest
            or interception.retrieval_arm is not retrieval_arm
        ):
            raise PromptInterceptionError(
                "verification occurrence does not match its interception"
            )
        if interception.status != "selected":
            raise PromptInterceptionError(
                "verification occurrence requires a selected interception"
            )
        if pair_order not in {1, 2}:
            raise PromptInterceptionError("verification pair order must be one or two")
        if isinstance(attempt_index, bool) or attempt_index < 1:
            raise PromptInterceptionError("verification attempt index must start at one")
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise PromptInterceptionError("verification seed must be an integer")
        if (
            isinstance(max_completion_tokens, bool)
            or max_completion_tokens <= 0
        ):
            raise PromptInterceptionError(
                "verification completion token limit must be positive"
            )
        if (
            interception.model_usage.provider_id != provider_id
            or interception.model_usage.model_requested != model_requested
        ):
            raise PromptInterceptionError(
                "verification occurrence provider context differs"
            )
        _require_digest(
            execution_policy_digest, "verification occurrence execution policy"
        )
        key = {
            "format_version": _CAMPAIGN_FORMAT_VERSION,
            "interception_receipt_id": interception.identity.id,
            "trajectory_id": task.trajectory_id,
            "task_id": task.task_id,
            "step_index": task.step_index,
            "request_digest": task.request_digest,
            "hidden_case_set_digest": task.hidden_case_set_digest,
            "retrieval_arm": retrieval_arm.value,
            "attempt_index": attempt_index,
            "pair_order": pair_order,
            "provider_id": provider_id,
            "model_requested": model_requested,
            "seed": seed,
            "max_completion_tokens": max_completion_tokens,
            "execution_policy_digest": execution_policy_digest,
        }
        identity = IdentityRecord.create("independent_verification_occurrence", key)
        return cls(
            identity,
            _CAMPAIGN_FORMAT_VERSION,
            identity.id,
            interception.identity.id,
            task.trajectory_id,
            task.task_id,
            task.step_index,
            task.request_digest,
            task.hidden_case_set_digest,
            retrieval_arm,
            attempt_index,
            pair_order,
            provider_id,
            model_requested,
            seed,
            max_completion_tokens,
            execution_policy_digest,
        )


@dataclass(frozen=True, slots=True)
class IndependentVerificationReceipt(RecordMixin):
    identity: IdentityRecord
    format_version: str
    trajectory_id: str
    task_id: str
    step_index: int
    request_digest: str
    hidden_case_set_digest: str
    primitive_id: str
    release_id: str
    pack_id: str
    pack_digest: str
    artifact_handle: ScopedArtifactHandle
    occurrence: VerificationOccurrenceReceipt
    cases: tuple[VerificationCaseObservation, ...]
    executed_case_count: int
    passed_case_count: int
    accepted: bool

    @classmethod
    def create(
        cls,
        *,
        task: NaturalPrimitiveTask,
        card: PrimitiveCard,
        interception: PromptInterceptionReceipt,
        occurrence: VerificationOccurrenceReceipt,
        cases: tuple[VerificationCaseObservation, ...],
    ) -> "IndependentVerificationReceipt":
        if occurrence.interception_receipt_id != interception.identity.id:
            raise PromptInterceptionError(
                "verification receipt occurrence does not bind the interception"
            )
        if (
            occurrence.task_id != task.task_id
            or occurrence.trajectory_id != task.trajectory_id
            or occurrence.step_index != task.step_index
            or occurrence.request_digest != task.request_digest
            or occurrence.hidden_case_set_digest != task.hidden_case_set_digest
        ):
            raise PromptInterceptionError(
                "verification receipt occurrence does not bind the task"
            )
        if (
            interception.selected_primitive_id != card.primitive_id
            or interception.selected_release_id != card.release_id
            or interception.selected_pack_id != card.pack_id
            or interception.artifact_handle != card.artifact_handle
        ):
            raise PromptInterceptionError(
                "verification receipt pack does not bind the interception"
            )
        expected_cases = tuple(item.case_id for item in task.hidden_cases)
        if tuple(item.case_id for item in cases) != expected_cases:
            raise PromptInterceptionError(
                "verification receipt cases do not exactly cover the task"
            )
        for expected, observed in zip(task.hidden_cases, cases, strict=True):
            if (
                observed.input_digest != expected.input_digest
                or observed.expected_digest != expected.expected_digest
            ):
                raise PromptInterceptionError(
                    "verification receipt case digest differs from the task"
                )
        accepted = bool(cases) and all(item.passed for item in cases)
        passed = sum(item.passed for item in cases)
        key = {
            "format_version": _CAMPAIGN_FORMAT_VERSION,
            "trajectory_id": task.trajectory_id,
            "task_id": task.task_id,
            "step_index": task.step_index,
            "request_digest": task.request_digest,
            "hidden_case_set_digest": task.hidden_case_set_digest,
            "primitive_id": card.primitive_id,
            "release_id": card.release_id,
            "pack_id": card.pack_id,
            "pack_digest": card.pack_digest,
            "artifact_handle": card.artifact_handle.to_dict(),
            "occurrence": occurrence.to_dict(),
            "cases": [item.to_dict() for item in cases],
            "executed_case_count": len(cases),
            "passed_case_count": passed,
            "accepted": accepted,
        }
        return cls(
            IdentityRecord.create("independent_primitive_verification_receipt", key),
            _CAMPAIGN_FORMAT_VERSION,
            task.trajectory_id,
            task.task_id,
            task.step_index,
            task.request_digest,
            task.hidden_case_set_digest,
            card.primitive_id,
            card.release_id,
            card.pack_id,
            card.pack_digest,
            card.artifact_handle,
            occurrence,
            cases,
            len(cases),
            passed,
            accepted,
        )


class IndependentPackVerifier:
    """Execute a selected checked pack against cases withheld from the teacher."""

    def __init__(
        self,
        catalog: ReleasedPrimitiveCatalog,
        *,
        executor: LocalDeterministicPythonPipelineExecutor | None = None,
    ) -> None:
        self.catalog = catalog
        self.executor = executor or LocalDeterministicPythonPipelineExecutor()
        self.planner = ExactPrimitiveWirePlanner()

    def verify(
        self,
        task: NaturalPrimitiveTask,
        interception: PromptInterceptionReceipt,
        occurrence: VerificationOccurrenceReceipt,
    ) -> IndependentVerificationReceipt:
        if interception.status != "selected" or interception.artifact_handle is None:
            raise PromptInterceptionError("only a selected interception can be verified")
        if (
            interception.task_id != task.task_id
            or interception.trajectory_id != task.trajectory_id
            or interception.step_index != task.step_index
            or interception.request_digest != task.request_digest
        ):
            raise PromptInterceptionError("interception receipt does not match the task step")
        card = self.catalog.card(str(interception.selected_primitive_id))
        if interception.artifact_handle != card.artifact_handle:
            raise PromptInterceptionError("interception selected an unbound artifact handle")
        if occurrence.interception_receipt_id != interception.identity.id:
            raise PromptInterceptionError(
                "verification occurrence does not bind the interception receipt"
            )
        encoded, interface = self.catalog.resolve(card.artifact_handle)
        plan = self.planner.pipeline((interface,))
        observations: list[VerificationCaseObservation] = []
        for case in task.hidden_cases:
            try:
                result = self.executor.execute(plan, (encoded,), case.input_value)
                output_digest = sha256_digest(canonical_json_bytes(result.output))
                passed = canonical_json_bytes(result.output) == canonical_json_bytes(
                    case.expected_output
                )
                observations.append(
                    VerificationCaseObservation(
                        case.case_id,
                        case.input_digest,
                        case.expected_digest,
                        output_digest,
                        result.receipt.identity.id,
                        passed,
                        None if passed else "output_mismatch",
                    )
                )
            except Exception as exc:  # noqa: BLE001 - failures are retained as evidence
                observations.append(
                    VerificationCaseObservation(
                        case.case_id,
                        case.input_digest,
                        case.expected_digest,
                        None,
                        None,
                        False,
                        _exception_code("execution", exc),
                    )
                )
        return IndependentVerificationReceipt.create(
            task=task,
            card=card,
            interception=interception,
            occurrence=occurrence,
            cases=tuple(observations),
        )


@dataclass(frozen=True, slots=True)
class CampaignArmReceipt(RecordMixin):
    identity: IdentityRecord
    format_version: str
    trajectory_id: str
    task_id: str
    step_index: int
    attempt_index: int
    pair_order: int
    request_digest: str
    hidden_case_set_digest: str
    retrieval_arm: RetrievalArm
    provider_id: str
    model_requested: str
    seed: int
    max_completion_tokens: int
    execution_policy_digest: str
    started_at: str
    completed_at: str
    wall_ms: int
    status: str
    error_code: str | None
    interception: PromptInterceptionReceipt | None
    verification: IndependentVerificationReceipt | None

    @classmethod
    def create(
        cls,
        *,
        task: NaturalPrimitiveTask,
        attempt_index: int,
        pair_order: int,
        retrieval_arm: RetrievalArm,
        provider_id: str,
        model_requested: str,
        seed: int,
        max_completion_tokens: int,
        execution_policy_digest: str,
        started_at: str,
        completed_at: str,
        wall_ms: int,
        status: str,
        error_code: str | None,
        interception: PromptInterceptionReceipt | None,
        verification: IndependentVerificationReceipt | None,
    ) -> "CampaignArmReceipt":
        if status not in {
            "accepted",
            "verification_failed",
            "teacher_rejected",
            "provider_failed",
            "interceptor_failed",
            "verifier_failed",
        }:
            raise PromptInterceptionError("campaign arm status is invalid")
        if pair_order not in {1, 2}:
            raise PromptInterceptionError("campaign arm pair order must be one or two")
        if isinstance(attempt_index, bool) or attempt_index < 1:
            raise PromptInterceptionError("campaign attempt index must start at one")
        _require_digest(execution_policy_digest, "campaign arm execution policy")
        if not started_at or not completed_at:
            raise PromptInterceptionError("campaign arm timing is incomplete")
        if isinstance(wall_ms, bool) or wall_ms < 0:
            raise PromptInterceptionError("campaign arm duration is invalid")
        if status == "accepted" and (verification is None or not verification.accepted):
            raise PromptInterceptionError("accepted campaign arm lacks verifier evidence")
        if status == "verification_failed" and (
            verification is None or verification.accepted
        ):
            raise PromptInterceptionError(
                "failed verification arm lacks rejecting verifier evidence"
            )
        if status not in {"accepted", "verification_failed"} and verification is not None:
            raise PromptInterceptionError(
                "non-verification campaign arm unexpectedly has verifier evidence"
            )
        if status != "accepted" and error_code is None:
            raise PromptInterceptionError("failed campaign arm lacks an error code")
        if status == "accepted" and error_code is not None:
            raise PromptInterceptionError("accepted campaign arm has an error code")
        if interception is not None and (
            interception.model_usage.provider_id != provider_id
            or interception.model_usage.model_requested != model_requested
        ):
            raise PromptInterceptionError(
                "campaign arm provider usage does not match its frozen context"
            )
        if interception is not None and (
            interception.trajectory_id != task.trajectory_id
            or interception.task_id != task.task_id
            or interception.step_index != task.step_index
            or interception.request_digest != task.request_digest
            or interception.retrieval_arm is not retrieval_arm
        ):
            raise PromptInterceptionError(
                "campaign arm interception does not match its frozen context"
            )
        if (
            status
            in {
                "accepted",
                "verification_failed",
                "teacher_rejected",
                "verifier_failed",
            }
            and interception is None
        ):
            raise PromptInterceptionError(
                "campaign arm status requires an interception receipt"
            )
        if (
            status == "teacher_rejected"
            and interception is not None
            and interception.status != "teacher_rejected"
        ):
            raise PromptInterceptionError(
                "teacher-rejected arm does not contain a teacher rejection"
            )
        if (
            status in {"accepted", "verification_failed", "verifier_failed"}
            and interception is not None
            and interception.status != "selected"
        ):
            raise PromptInterceptionError(
                "campaign arm verifier status requires a selected interception"
            )
        if verification is not None:
            occurrence = verification.occurrence
            expected_occurrence = (
                interception is not None
                and occurrence.interception_receipt_id == interception.identity.id
                and occurrence.trajectory_id == task.trajectory_id
                and occurrence.task_id == task.task_id
                and occurrence.step_index == task.step_index
                and occurrence.request_digest == task.request_digest
                and occurrence.hidden_case_set_digest == task.hidden_case_set_digest
                and occurrence.retrieval_arm is retrieval_arm
                and occurrence.attempt_index == attempt_index
                and occurrence.pair_order == pair_order
                and occurrence.provider_id == provider_id
                and occurrence.model_requested == model_requested
                and occurrence.seed == seed
                and occurrence.max_completion_tokens == max_completion_tokens
                and occurrence.execution_policy_digest == execution_policy_digest
            )
            if not expected_occurrence:
                raise PromptInterceptionError(
                    "campaign arm verifier occurrence does not match its frozen context"
                )
        key = {
            "format_version": _CAMPAIGN_FORMAT_VERSION,
            "trajectory_id": task.trajectory_id,
            "task_id": task.task_id,
            "step_index": task.step_index,
            "attempt_index": attempt_index,
            "pair_order": pair_order,
            "request_digest": task.request_digest,
            "hidden_case_set_digest": task.hidden_case_set_digest,
            "retrieval_arm": retrieval_arm.value,
            "provider_id": provider_id,
            "model_requested": model_requested,
            "seed": seed,
            "max_completion_tokens": max_completion_tokens,
            "execution_policy_digest": execution_policy_digest,
            "started_at": started_at,
            "completed_at": completed_at,
            "wall_ms": wall_ms,
            "status": status,
            "error_code": error_code,
            "interception": interception.to_dict() if interception else None,
            "verification": verification.to_dict() if verification else None,
        }
        return cls(
            IdentityRecord.create("prompt_interception_campaign_arm_receipt", key),
            _CAMPAIGN_FORMAT_VERSION,
            task.trajectory_id,
            task.task_id,
            task.step_index,
            attempt_index,
            pair_order,
            task.request_digest,
            task.hidden_case_set_digest,
            retrieval_arm,
            provider_id,
            model_requested,
            seed,
            max_completion_tokens,
            execution_policy_digest,
            started_at,
            completed_at,
            wall_ms,
            status,
            error_code,
            interception,
            verification,
        )


@dataclass(frozen=True, slots=True)
class MatchedCampaignPair(RecordMixin):
    identity: IdentityRecord
    format_version: str
    trajectory_id: str
    task_id: str
    step_index: int
    attempt_index: int
    request_digest: str
    hidden_case_set_digest: str
    provider_id: str
    model_requested: str
    seed: int
    max_completion_tokens: int
    execution_policy_digest: str
    full_catalog_arm_id: str
    shortlist_arm_id: str
    full_catalog_usage: ModelUsageReceipt | None
    shortlist_usage: ModelUsageReceipt | None
    provider_deployment_digest: str | None
    full_catalog_verifier_id: str | None
    shortlist_verifier_id: str | None
    full_catalog_verification_occurrence_id: str | None
    shortlist_verification_occurrence_id: str | None
    full_catalog_accepted: bool
    shortlist_accepted: bool

    @classmethod
    def create(
        cls, full: CampaignArmReceipt, shortlist: CampaignArmReceipt
    ) -> "MatchedCampaignPair":
        compared = (
            "trajectory_id",
            "task_id",
            "step_index",
            "attempt_index",
            "request_digest",
            "hidden_case_set_digest",
            "provider_id",
            "model_requested",
            "seed",
            "max_completion_tokens",
            "execution_policy_digest",
        )
        if (
            full.retrieval_arm is not RetrievalArm.FULL_CATALOG
            or shortlist.retrieval_arm
            is not RetrievalArm.DETERMINISTIC_SHORTLIST
        ):
            raise PromptInterceptionError("matched campaign pair arms are reversed")
        if any(getattr(full, field) != getattr(shortlist, field) for field in compared):
            raise PromptInterceptionError("matched campaign pair context differs")
        full_usage = full.interception.model_usage if full.interception else None
        shortlist_usage = (
            shortlist.interception.model_usage if shortlist.interception else None
        )
        deployment_digest: str | None = None
        if full_usage is not None and shortlist_usage is not None:
            full_deployment = {
                "provider_id": full_usage.provider_id,
                "provider_api": full_usage.provider_api,
                "endpoint_origin": full_usage.endpoint_origin,
                "model_reported": full_usage.model_reported,
            }
            shortlist_deployment = {
                "provider_id": shortlist_usage.provider_id,
                "provider_api": shortlist_usage.provider_api,
                "endpoint_origin": shortlist_usage.endpoint_origin,
                "model_reported": shortlist_usage.model_reported,
            }
            if full_deployment != shortlist_deployment:
                raise PromptInterceptionError(
                    "matched campaign pair concrete provider deployment differs"
                )
            if full_usage.identity.id == shortlist_usage.identity.id:
                raise PromptInterceptionError(
                    "matched campaign pair reuses a provider receipt"
                )
            deployment_digest = sha256_digest(
                canonical_json_bytes(full_deployment)
            )
        full_verifier = full.verification.identity.id if full.verification else None
        shortlist_verifier = (
            shortlist.verification.identity.id if shortlist.verification else None
        )
        full_occurrence = (
            full.verification.occurrence.identity.id if full.verification else None
        )
        shortlist_occurrence = (
            shortlist.verification.occurrence.identity.id
            if shortlist.verification
            else None
        )
        if (
            full_occurrence is not None
            and shortlist_occurrence is not None
            and full_occurrence == shortlist_occurrence
        ):
            raise PromptInterceptionError(
                "matched campaign pair reuses a verifier occurrence"
            )
        if (
            full_verifier is not None
            and shortlist_verifier is not None
            and full_verifier == shortlist_verifier
        ):
            raise PromptInterceptionError(
                "matched campaign pair reuses a verifier receipt"
            )
        key = {
            "format_version": _CAMPAIGN_FORMAT_VERSION,
            "trajectory_id": full.trajectory_id,
            "task_id": full.task_id,
            "step_index": full.step_index,
            "attempt_index": full.attempt_index,
            "request_digest": full.request_digest,
            "hidden_case_set_digest": full.hidden_case_set_digest,
            "provider_id": full.provider_id,
            "model_requested": full.model_requested,
            "seed": full.seed,
            "max_completion_tokens": full.max_completion_tokens,
            "execution_policy_digest": full.execution_policy_digest,
            "full_catalog_arm_id": full.identity.id,
            "shortlist_arm_id": shortlist.identity.id,
            "full_catalog_usage": full_usage.to_dict() if full_usage else None,
            "shortlist_usage": shortlist_usage.to_dict() if shortlist_usage else None,
            "provider_deployment_digest": deployment_digest,
            "full_catalog_verifier_id": full_verifier,
            "shortlist_verifier_id": shortlist_verifier,
            "full_catalog_verification_occurrence_id": full_occurrence,
            "shortlist_verification_occurrence_id": shortlist_occurrence,
            "full_catalog_accepted": bool(full.verification and full.verification.accepted),
            "shortlist_accepted": bool(
                shortlist.verification and shortlist.verification.accepted
            ),
        }
        return cls(
            IdentityRecord.create("matched_prompt_interception_pair", key),
            _CAMPAIGN_FORMAT_VERSION,
            full.trajectory_id,
            full.task_id,
            full.step_index,
            full.attempt_index,
            full.request_digest,
            full.hidden_case_set_digest,
            full.provider_id,
            full.model_requested,
            full.seed,
            full.max_completion_tokens,
            full.execution_policy_digest,
            full.identity.id,
            shortlist.identity.id,
            full_usage,
            shortlist_usage,
            deployment_digest,
            full_verifier,
            shortlist_verifier,
            full_occurrence,
            shortlist_occurrence,
            bool(full.verification and full.verification.accepted),
            bool(shortlist.verification and shortlist.verification.accepted),
        )


@dataclass(frozen=True, slots=True)
class PromptInterceptionCampaignReceipt(RecordMixin):
    identity: IdentityRecord
    format_version: str
    claim_scope: str
    catalog_digest: str
    task_set_digest: str
    task_manifest: tuple[CampaignTaskManifestEntry, ...]
    expected_counts: CampaignExpectedCounts
    retrieval_conditions: tuple[RetrievalArm, ...]
    execution_policy: CampaignExecutionPolicy
    execution_policy_digest: str
    provider_id: str
    model_requested: str
    seeds: tuple[int, ...]
    max_completion_tokens: int
    shortlist_limit: int
    arms: tuple[CampaignArmReceipt, ...]
    matched_pairs: tuple[MatchedCampaignPair, ...]

    @classmethod
    def create(
        cls,
        *,
        catalog_digest: str,
        task_manifest: tuple[CampaignTaskManifestEntry, ...],
        expected_counts: CampaignExpectedCounts,
        execution_policy: CampaignExecutionPolicy,
        provider_id: str,
        model_requested: str,
        seeds: tuple[int, ...],
        max_completion_tokens: int,
        shortlist_limit: int,
        arms: tuple[CampaignArmReceipt, ...],
        matched_pairs: tuple[MatchedCampaignPair, ...],
    ) -> "PromptInterceptionCampaignReceipt":
        retrieval_conditions = (
            RetrievalArm.FULL_CATALOG,
            RetrievalArm.DETERMINISTIC_SHORTLIST,
        )
        if not task_manifest or len(
            {
                (item.trajectory_id, item.task_id, item.step_index)
                for item in task_manifest
            }
        ) != len(task_manifest):
            raise PromptInterceptionError(
                "campaign task manifest contexts must be non-empty and unique"
            )
        if len({item.task_id for item in task_manifest}) != len(task_manifest):
            raise PromptInterceptionError("campaign task manifest ids must be unique")
        if len(seeds) != len(set(seeds)):
            raise PromptInterceptionError("campaign seeds must be unique")
        if expected_counts != CampaignExpectedCounts.create(
            task_count=len(task_manifest), seed_count=len(seeds)
        ):
            raise PromptInterceptionError("campaign expected counts are inconsistent")
        if len(arms) != expected_counts.arm_count or len(
            matched_pairs
        ) != expected_counts.matched_pair_count:
            raise PromptInterceptionError(
                "campaign records do not meet their declared expected counts"
            )
        task_set_key = {
            "format_version": _CAMPAIGN_FORMAT_VERSION,
            "task_manifest": [item.to_dict() for item in task_manifest],
            "seeds": list(seeds),
            "retrieval_conditions": [item.value for item in retrieval_conditions],
            "expected_counts": expected_counts.to_dict(),
        }
        task_set_digest = sha256_digest(canonical_json_bytes(task_set_key))
        execution_policy_digest = execution_policy.digest
        if any(
            item.execution_policy_digest != execution_policy_digest for item in arms
        ) or any(
            item.execution_policy_digest != execution_policy_digest
            for item in matched_pairs
        ):
            raise PromptInterceptionError(
                "campaign records do not bind the execution policy"
            )
        claim_scope = (
            "provider-native token counts and independently executed hidden-case outcomes; "
            "causal savings require separate token_savings integrity evaluation"
        )
        key = {
            "format_version": _CAMPAIGN_FORMAT_VERSION,
            "claim_scope": claim_scope,
            "catalog_digest": catalog_digest,
            "task_set_digest": task_set_digest,
            "task_manifest": [item.to_dict() for item in task_manifest],
            "expected_counts": expected_counts.to_dict(),
            "retrieval_conditions": [item.value for item in retrieval_conditions],
            "execution_policy": execution_policy.to_dict(),
            "execution_policy_digest": execution_policy_digest,
            "provider_id": provider_id,
            "model_requested": model_requested,
            "seeds": list(seeds),
            "max_completion_tokens": max_completion_tokens,
            "shortlist_limit": shortlist_limit,
            "arm_ids": [item.identity.id for item in arms],
            "matched_pair_ids": [item.identity.id for item in matched_pairs],
        }
        result = cls(
            IdentityRecord.create("prompt_interception_campaign_receipt", key),
            _CAMPAIGN_FORMAT_VERSION,
            claim_scope,
            catalog_digest,
            task_set_digest,
            task_manifest,
            expected_counts,
            retrieval_conditions,
            execution_policy,
            execution_policy_digest,
            provider_id,
            model_requested,
            seeds,
            max_completion_tokens,
            shortlist_limit,
            arms,
            matched_pairs,
        )
        validate_prompt_interception_campaign_document(
            result.to_dict(), allow_legacy=False
        )
        return result


def run_prompt_interception_campaign(
    *,
    catalog: ReleasedPrimitiveCatalog,
    tasks: Sequence[NaturalPrimitiveTask],
    provider: ChatProvider,
    provider_id: str,
    model: str,
    seeds: Sequence[int],
    max_completion_tokens: int,
    shortlist_limit: int = 4,
    request_timeout_ms: int = 60_000,
    max_response_bytes: int = 1_048_576,
) -> PromptInterceptionCampaignReceipt:
    """Compare all descriptions with locally selected descriptions; retain failures."""

    prepared_tasks = tuple(tasks)
    prepared_seeds = tuple(seeds)
    if not prepared_tasks or not prepared_seeds:
        raise PromptInterceptionError("campaign requires tasks and seeds")
    if not provider_id or not model:
        raise PromptInterceptionError("campaign provider and model are required")
    if any(isinstance(seed, bool) or not isinstance(seed, int) for seed in prepared_seeds):
        raise PromptInterceptionError("campaign seeds must be integers")
    if len(set(prepared_seeds)) != len(prepared_seeds):
        raise PromptInterceptionError("campaign seeds must be unique")
    task_contexts = tuple(
        (task.trajectory_id, task.task_id, task.step_index) for task in prepared_tasks
    )
    if len(set(task_contexts)) != len(task_contexts) or len(
        {task.task_id for task in prepared_tasks}
    ) != len(prepared_tasks):
        raise PromptInterceptionError("campaign tasks must be unique")
    if isinstance(max_completion_tokens, bool) or max_completion_tokens <= 0:
        raise PromptInterceptionError("campaign completion token limit must be positive")
    execution_policy = CampaignExecutionPolicy.create(
        request_timeout_ms=request_timeout_ms,
        max_response_bytes=max_response_bytes,
    )
    # A checked campaign is evidence, not a best-effort portability exercise.
    # Validate the exact runtime contract before constructing an interceptor or
    # spending a provider call; an unsupported host must fail without side effects.
    _validate_execution_policy(execution_policy.to_dict())
    interceptor = PromptInterceptor(
        catalog, provider, shortlist_limit=shortlist_limit
    )
    verifier = IndependentPackVerifier(catalog)
    arms: list[CampaignArmReceipt] = []
    pairs: list[MatchedCampaignPair] = []
    for task in prepared_tasks:
        for attempt_index, seed in enumerate(prepared_seeds, start=1):
            execution_order = (
                (RetrievalArm.FULL_CATALOG, RetrievalArm.DETERMINISTIC_SHORTLIST)
                if (attempt_index + task.step_index) % 2 == 0
                else (RetrievalArm.DETERMINISTIC_SHORTLIST, RetrievalArm.FULL_CATALOG)
            )
            completed: dict[RetrievalArm, CampaignArmReceipt] = {}
            for pair_order, retrieval_arm in enumerate(execution_order, start=1):
                completed[retrieval_arm] = _run_campaign_arm(
                    task=task,
                    attempt_index=attempt_index,
                    pair_order=pair_order,
                    retrieval_arm=retrieval_arm,
                    interceptor=interceptor,
                    verifier=verifier,
                    provider_id=provider_id,
                    model=model,
                    seed=seed,
                    max_completion_tokens=max_completion_tokens,
                    execution_policy_digest=execution_policy.digest,
                )
            full = completed[RetrievalArm.FULL_CATALOG]
            shortlist = completed[RetrievalArm.DETERMINISTIC_SHORTLIST]
            arms.extend(completed[item] for item in execution_order)
            pairs.append(MatchedCampaignPair.create(full, shortlist))
    task_manifest = tuple(
        CampaignTaskManifestEntry.from_task(item) for item in prepared_tasks
    )
    expected_counts = CampaignExpectedCounts.create(
        task_count=len(task_manifest), seed_count=len(prepared_seeds)
    )
    return PromptInterceptionCampaignReceipt.create(
        catalog_digest=catalog.digest,
        task_manifest=task_manifest,
        expected_counts=expected_counts,
        execution_policy=execution_policy,
        provider_id=provider_id,
        model_requested=model,
        seeds=prepared_seeds,
        max_completion_tokens=max_completion_tokens,
        shortlist_limit=shortlist_limit,
        arms=tuple(arms),
        matched_pairs=tuple(pairs),
    )


def _run_campaign_arm(
    *,
    task: NaturalPrimitiveTask,
    attempt_index: int,
    pair_order: int,
    retrieval_arm: RetrievalArm,
    interceptor: PromptInterceptor,
    verifier: IndependentPackVerifier,
    provider_id: str,
    model: str,
    seed: int,
    max_completion_tokens: int,
    execution_policy_digest: str,
) -> CampaignArmReceipt:
    started_at = _utc_now()
    started_ns = time.monotonic_ns()

    def finish(
        *,
        status: str,
        error_code: str | None,
        interception: PromptInterceptionReceipt | None,
        verification: IndependentVerificationReceipt | None,
    ) -> CampaignArmReceipt:
        return CampaignArmReceipt.create(
            task=task,
            attempt_index=attempt_index,
            pair_order=pair_order,
            retrieval_arm=retrieval_arm,
            provider_id=provider_id,
            model_requested=model,
            seed=seed,
            max_completion_tokens=max_completion_tokens,
            execution_policy_digest=execution_policy_digest,
            started_at=started_at,
            completed_at=_utc_now(),
            wall_ms=max(0, (time.monotonic_ns() - started_ns) // 1_000_000),
            status=status,
            error_code=error_code,
            interception=interception,
            verification=verification,
        )

    try:
        interception = interceptor.intercept(
            task,
            retrieval_arm,
            model=model,
            seed=seed,
            max_completion_tokens=max_completion_tokens,
        )
    except _TeacherProviderFailure as exc:
        return finish(
            status="provider_failed",
            error_code=exc.code,
            interception=None,
            verification=None,
        )
    except Exception as exc:  # noqa: BLE001 - interception failures are evidence
        return finish(
            status="interceptor_failed",
            error_code=_exception_code("interceptor", exc),
            interception=None,
            verification=None,
        )
    if interception.status != "selected":
        return finish(
            status="teacher_rejected",
            error_code=interception.error_code,
            interception=interception,
            verification=None,
        )
    occurrence = VerificationOccurrenceReceipt.create(
        task=task,
        interception=interception,
        retrieval_arm=retrieval_arm,
        attempt_index=attempt_index,
        pair_order=pair_order,
        provider_id=provider_id,
        model_requested=model,
        seed=seed,
        max_completion_tokens=max_completion_tokens,
        execution_policy_digest=execution_policy_digest,
    )
    try:
        verification = verifier.verify(task, interception, occurrence)
    except Exception as exc:  # noqa: BLE001 - verifier infrastructure failures are retained
        return finish(
            status="verifier_failed",
            error_code=_exception_code("verifier", exc),
            interception=interception,
            verification=None,
        )
    accepted = verification.accepted
    return finish(
        status="accepted" if accepted else "verification_failed",
        error_code=None if accepted else "hidden_cases_failed",
        interception=interception,
        verification=verification,
    )


@dataclass(frozen=True, slots=True)
class PromptInterceptionCampaignValidation(RecordMixin):
    """Result of strict, non-executing serialized-campaign validation."""

    campaign_id: str
    format_version: str
    legacy: bool
    identity_chain_valid: bool
    manifest_complete: bool
    arm_matrix_complete: bool
    pair_matrix_complete: bool
    verification_occurrences_bound: bool
    provider_receipts_unique: bool
    concrete_deployment_bound: bool
    claimable_independent_execution: bool
    task_count: int
    arm_count: int
    matched_pair_count: int
    limitations: tuple[str, ...]


def validate_prompt_interception_campaign_document(
    raw: Mapping[str, Any], *, allow_legacy: bool = True
) -> PromptInterceptionCampaignValidation:
    """Strictly validate a serialized campaign before any counters are derived.

    Version 2 validates the declared task/seed/condition Cartesian product and
    arm-specific verifier occurrences.  Version 1 remains readable as a legacy,
    nonclaimable observation, but its missing manifest and occurrence bindings are
    reported rather than inferred away.
    """

    campaign = _strict_mapping(raw, "campaign")
    version = _strict_text(campaign.get("format_version"), "campaign.format_version")
    if version == _CAMPAIGN_FORMAT_VERSION:
        return _validate_v2_campaign(campaign)
    if version == _LEGACY_CAMPAIGN_FORMAT_VERSION and allow_legacy:
        return _validate_legacy_campaign(campaign)
    raise PromptInterceptionError(
        f"campaign format_version {version!r} is unsupported"
    )


def _validate_v2_campaign(
    campaign: Mapping[str, Any],
) -> PromptInterceptionCampaignValidation:
    _exact_fields(
        campaign,
        {
            "identity",
            "format_version",
            "claim_scope",
            "catalog_digest",
            "task_set_digest",
            "task_manifest",
            "expected_counts",
            "retrieval_conditions",
            "execution_policy",
            "execution_policy_digest",
            "provider_id",
            "model_requested",
            "seeds",
            "max_completion_tokens",
            "shortlist_limit",
            "arms",
            "matched_pairs",
        },
        "campaign",
    )
    _strict_text(campaign["claim_scope"], "campaign.claim_scope")
    catalog_digest = _strict_digest(campaign["catalog_digest"], "campaign.catalog_digest")
    provider_id = _strict_text(campaign["provider_id"], "campaign.provider_id")
    model_requested = _strict_text(
        campaign["model_requested"], "campaign.model_requested"
    )
    max_completion_tokens = _positive_int(
        campaign["max_completion_tokens"], "campaign.max_completion_tokens"
    )
    shortlist_limit = _positive_int(
        campaign["shortlist_limit"], "campaign.shortlist_limit"
    )
    seeds = _integer_list(campaign["seeds"], "campaign.seeds")
    if not seeds or len(seeds) != len(set(seeds)):
        raise PromptInterceptionError("campaign.seeds must be non-empty and unique")
    retrieval_conditions = _strict_list(
        campaign["retrieval_conditions"], "campaign.retrieval_conditions"
    )
    expected_conditions = [
        RetrievalArm.FULL_CATALOG.value,
        RetrievalArm.DETERMINISTIC_SHORTLIST.value,
    ]
    if retrieval_conditions != expected_conditions:
        raise PromptInterceptionError(
            "campaign retrieval conditions must be the frozen A/B conditions"
        )

    manifest_raw = _strict_list(campaign["task_manifest"], "campaign.task_manifest")
    if not manifest_raw:
        raise PromptInterceptionError("campaign task manifest cannot be empty")
    manifest: list[dict[str, Any]] = []
    manifest_by_context: dict[tuple[str, str, int], dict[str, Any]] = {}
    task_ids: set[str] = set()
    for index, item in enumerate(manifest_raw):
        entry = _strict_mapping(item, f"campaign.task_manifest[{index}]")
        _exact_fields(
            entry,
            {
                "trajectory_id",
                "task_id",
                "step_index",
                "request_digest",
                "hidden_case_set_digest",
            },
            f"campaign.task_manifest[{index}]",
        )
        prepared = {
            "trajectory_id": _strict_text(
                entry["trajectory_id"], f"campaign.task_manifest[{index}].trajectory_id"
            ),
            "task_id": _strict_text(
                entry["task_id"], f"campaign.task_manifest[{index}].task_id"
            ),
            "step_index": _nonnegative_int(
                entry["step_index"], f"campaign.task_manifest[{index}].step_index"
            ),
            "request_digest": _strict_digest(
                entry["request_digest"],
                f"campaign.task_manifest[{index}].request_digest",
            ),
            "hidden_case_set_digest": _strict_digest(
                entry["hidden_case_set_digest"],
                f"campaign.task_manifest[{index}].hidden_case_set_digest",
            ),
        }
        context = (
            prepared["trajectory_id"],
            prepared["task_id"],
            prepared["step_index"],
        )
        if context in manifest_by_context or prepared["task_id"] in task_ids:
            raise PromptInterceptionError("campaign task manifest contains duplicates")
        manifest.append(prepared)
        manifest_by_context[context] = prepared
        task_ids.add(prepared["task_id"])

    expected_counts = _validate_expected_counts(
        campaign["expected_counts"], len(manifest), len(seeds)
    )
    policy = _validate_execution_policy(campaign["execution_policy"])
    policy_digest = _strict_digest(
        campaign["execution_policy_digest"], "campaign.execution_policy_digest"
    )
    if policy_digest != sha256_digest(canonical_json_bytes(policy)):
        raise PromptInterceptionError("campaign execution policy digest differs")
    task_set_key = {
        "format_version": _CAMPAIGN_FORMAT_VERSION,
        "task_manifest": manifest,
        "seeds": seeds,
        "retrieval_conditions": expected_conditions,
        "expected_counts": expected_counts,
    }
    task_set_digest = _strict_digest(
        campaign["task_set_digest"], "campaign.task_set_digest"
    )
    if task_set_digest != sha256_digest(canonical_json_bytes(task_set_key)):
        raise PromptInterceptionError("campaign task_set_digest differs from its manifest")

    arms_raw = _strict_list(campaign["arms"], "campaign.arms")
    pairs_raw = _strict_list(campaign["matched_pairs"], "campaign.matched_pairs")
    if len(arms_raw) != expected_counts["arm_count"]:
        raise PromptInterceptionError("campaign arm matrix is incomplete")
    if len(pairs_raw) != expected_counts["matched_pair_count"]:
        raise PromptInterceptionError("campaign matched-pair matrix is incomplete")

    arm_by_condition: dict[tuple[Any, ...], dict[str, Any]] = {}
    arm_by_id: dict[str, dict[str, Any]] = {}
    usage_ids: list[str] = []
    verifier_ids: list[str] = []
    occurrence_ids: list[str] = []
    for index, item in enumerate(arms_raw):
        arm = _validate_campaign_arm(
            item,
            label=f"campaign.arms[{index}]",
            version=_CAMPAIGN_FORMAT_VERSION,
            catalog_digest=catalog_digest,
            provider_id=provider_id,
            model_requested=model_requested,
            max_completion_tokens=max_completion_tokens,
            shortlist_limit=shortlist_limit,
            execution_policy_digest=policy_digest,
            manifest_by_context=manifest_by_context,
        )
        key = _arm_condition_key(arm)
        if key in arm_by_condition or arm["identity_id"] in arm_by_id:
            raise PromptInterceptionError("campaign contains duplicate arm evidence")
        arm_by_condition[key] = arm
        arm_by_id[arm["identity_id"]] = arm
        if arm["usage_id"] is not None:
            usage_ids.append(arm["usage_id"])
        if arm["verifier_id"] is not None:
            verifier_ids.append(arm["verifier_id"])
        if arm["occurrence_id"] is not None:
            occurrence_ids.append(arm["occurrence_id"])

    expected_arm_keys: set[tuple[Any, ...]] = set()
    for entry in manifest:
        for attempt_index, seed in enumerate(seeds, start=1):
            for retrieval_arm in expected_conditions:
                expected_arm_keys.add(
                    (
                        entry["trajectory_id"],
                        entry["task_id"],
                        entry["step_index"],
                        entry["request_digest"],
                        entry["hidden_case_set_digest"],
                        attempt_index,
                        seed,
                        retrieval_arm,
                    )
                )
    if set(arm_by_condition) != expected_arm_keys:
        raise PromptInterceptionError(
            "campaign arms do not exactly cover task x seed x condition"
        )
    if len(usage_ids) != len(set(usage_ids)):
        raise PromptInterceptionError("campaign reuses a provider source receipt")
    if len(verifier_ids) != len(set(verifier_ids)):
        raise PromptInterceptionError("campaign reuses a verifier receipt")
    if len(occurrence_ids) != len(set(occurrence_ids)):
        raise PromptInterceptionError("campaign reuses a verifier occurrence")

    pair_by_context: dict[tuple[Any, ...], dict[str, Any]] = {}
    referenced_arm_ids: list[str] = []
    concrete_deployment_bound = True
    for index, item in enumerate(pairs_raw):
        pair = _validate_campaign_pair(
            item,
            label=f"campaign.matched_pairs[{index}]",
            version=_CAMPAIGN_FORMAT_VERSION,
            arm_by_id=arm_by_id,
            execution_policy_digest=policy_digest,
        )
        key = _pair_context_key(pair)
        if key in pair_by_context:
            raise PromptInterceptionError("campaign contains duplicate matched pairs")
        pair_by_context[key] = pair
        referenced_arm_ids.extend(
            (pair["full_catalog_arm_id"], pair["shortlist_arm_id"])
        )
        concrete_deployment_bound &= pair["deployment_bound"]
    expected_pair_keys = {
        (
            entry["trajectory_id"],
            entry["task_id"],
            entry["step_index"],
            entry["request_digest"],
            entry["hidden_case_set_digest"],
            attempt_index,
            seed,
        )
        for entry in manifest
        for attempt_index, seed in enumerate(seeds, start=1)
    }
    if set(pair_by_context) != expected_pair_keys:
        raise PromptInterceptionError(
            "campaign pairs do not exactly cover task x seed"
        )
    if len(referenced_arm_ids) != len(set(referenced_arm_ids)) or set(
        referenced_arm_ids
    ) != set(arm_by_id):
        raise PromptInterceptionError(
            "campaign pairs do not reference every arm exactly once"
        )

    campaign_key = {
        "format_version": _CAMPAIGN_FORMAT_VERSION,
        "claim_scope": campaign["claim_scope"],
        "catalog_digest": catalog_digest,
        "task_set_digest": task_set_digest,
        "task_manifest": manifest,
        "expected_counts": expected_counts,
        "retrieval_conditions": expected_conditions,
        "execution_policy": policy,
        "execution_policy_digest": policy_digest,
        "provider_id": provider_id,
        "model_requested": model_requested,
        "seeds": seeds,
        "max_completion_tokens": max_completion_tokens,
        "shortlist_limit": shortlist_limit,
        "arm_ids": [arm_by_id_value["identity_id"] for arm_by_id_value in [
            _validated_arm_for_raw(item, arm_by_id) for item in arms_raw
        ]],
        "matched_pair_ids": [
            _identity_id_from_record(_strict_mapping(item, "campaign.matched_pairs[]"))
            for item in pairs_raw
        ],
    }
    campaign_id = _validate_record_identity(
        campaign["identity"],
        "prompt_interception_campaign_receipt",
        campaign_key,
        "campaign.identity",
    )
    limitations: list[str] = []
    if not concrete_deployment_bound:
        limitations.append(
            "one or more pairs lack two provider receipts, so a concrete "
            "deployment comparison is unavailable"
        )
    if not occurrence_ids:
        limitations.append(
            "campaign contains no completed verifier occurrence"
        )
    claimable_independent_execution = bool(occurrence_ids) and concrete_deployment_bound
    return PromptInterceptionCampaignValidation(
        campaign_id,
        _CAMPAIGN_FORMAT_VERSION,
        False,
        True,
        True,
        True,
        True,
        True,
        True,
        concrete_deployment_bound,
        claimable_independent_execution,
        len(manifest),
        len(arms_raw),
        len(pairs_raw),
        tuple(limitations),
    )


def _validate_legacy_campaign(
    campaign: Mapping[str, Any],
) -> PromptInterceptionCampaignValidation:
    _exact_fields(
        campaign,
        {
            "identity",
            "format_version",
            "claim_scope",
            "catalog_digest",
            "task_set_digest",
            "provider_id",
            "model_requested",
            "seeds",
            "max_completion_tokens",
            "shortlist_limit",
            "arms",
            "matched_pairs",
        },
        "campaign",
    )
    catalog_digest = _strict_digest(campaign["catalog_digest"], "campaign.catalog_digest")
    task_set_digest = _strict_digest(campaign["task_set_digest"], "campaign.task_set_digest")
    provider_id = _strict_text(campaign["provider_id"], "campaign.provider_id")
    model_requested = _strict_text(
        campaign["model_requested"], "campaign.model_requested"
    )
    max_completion_tokens = _positive_int(
        campaign["max_completion_tokens"], "campaign.max_completion_tokens"
    )
    shortlist_limit = _positive_int(
        campaign["shortlist_limit"], "campaign.shortlist_limit"
    )
    seeds = _integer_list(campaign["seeds"], "campaign.seeds")
    if not seeds or len(seeds) != len(set(seeds)):
        raise PromptInterceptionError("legacy campaign seeds must be non-empty and unique")
    arms_raw = _strict_list(campaign["arms"], "campaign.arms")
    pairs_raw = _strict_list(campaign["matched_pairs"], "campaign.matched_pairs")
    if not arms_raw or not pairs_raw:
        raise PromptInterceptionError("legacy campaign has no arm or pair evidence")
    arm_by_id: dict[str, dict[str, Any]] = {}
    arm_by_condition: dict[tuple[Any, ...], dict[str, Any]] = {}
    usage_ids: list[str] = []
    for index, item in enumerate(arms_raw):
        arm = _validate_campaign_arm(
            item,
            label=f"campaign.arms[{index}]",
            version=_LEGACY_CAMPAIGN_FORMAT_VERSION,
            catalog_digest=catalog_digest,
            provider_id=provider_id,
            model_requested=model_requested,
            max_completion_tokens=max_completion_tokens,
            shortlist_limit=shortlist_limit,
            execution_policy_digest=None,
            manifest_by_context=None,
        )
        key = _legacy_arm_condition_key(arm)
        if key in arm_by_condition or arm["identity_id"] in arm_by_id:
            raise PromptInterceptionError("legacy campaign contains duplicate arms")
        arm_by_condition[key] = arm
        arm_by_id[arm["identity_id"]] = arm
        if arm["usage_id"] is not None:
            usage_ids.append(arm["usage_id"])
    if len(usage_ids) != len(set(usage_ids)):
        raise PromptInterceptionError("legacy campaign reuses a provider source receipt")
    observed_task_contexts = {
        (arm["trajectory_id"], arm["task_id"], arm["step_index"], arm["request_digest"])
        for arm in arm_by_id.values()
    }
    expected_arm_keys = {
        (*task_context, attempt_index, seed, retrieval_arm)
        for task_context in observed_task_contexts
        for attempt_index, seed in enumerate(seeds, start=1)
        for retrieval_arm in (
            RetrievalArm.FULL_CATALOG.value,
            RetrievalArm.DETERMINISTIC_SHORTLIST.value,
        )
    }
    if set(arm_by_condition) != expected_arm_keys:
        raise PromptInterceptionError(
            "legacy campaign is incomplete for its observed task contexts"
        )
    pair_ids: list[str] = []
    referenced_arm_ids: list[str] = []
    pair_contexts: set[tuple[Any, ...]] = set()
    for index, item in enumerate(pairs_raw):
        pair = _validate_campaign_pair(
            item,
            label=f"campaign.matched_pairs[{index}]",
            version=_LEGACY_CAMPAIGN_FORMAT_VERSION,
            arm_by_id=arm_by_id,
            execution_policy_digest=None,
        )
        context = _legacy_pair_context_key(pair)
        if context in pair_contexts:
            raise PromptInterceptionError("legacy campaign contains duplicate pairs")
        pair_contexts.add(context)
        pair_ids.append(pair["identity_id"])
        referenced_arm_ids.extend(
            (pair["full_catalog_arm_id"], pair["shortlist_arm_id"])
        )
    expected_pair_contexts = {
        (*task_context, attempt_index, seed)
        for task_context in observed_task_contexts
        for attempt_index, seed in enumerate(seeds, start=1)
    }
    if pair_contexts != expected_pair_contexts:
        raise PromptInterceptionError(
            "legacy campaign pairs are incomplete for observed tasks"
        )
    if len(referenced_arm_ids) != len(set(referenced_arm_ids)) or set(
        referenced_arm_ids
    ) != set(arm_by_id):
        raise PromptInterceptionError(
            "legacy campaign pairs do not reference every arm exactly once"
        )
    campaign_key = {
        "format_version": _LEGACY_CAMPAIGN_FORMAT_VERSION,
        "claim_scope": _strict_text(campaign["claim_scope"], "campaign.claim_scope"),
        "catalog_digest": catalog_digest,
        "task_set_digest": task_set_digest,
        "provider_id": provider_id,
        "model_requested": model_requested,
        "seeds": seeds,
        "max_completion_tokens": max_completion_tokens,
        "shortlist_limit": shortlist_limit,
        "arm_ids": [
            _identity_id_from_record(_strict_mapping(item, "campaign.arms[]"))
            for item in arms_raw
        ],
        "matched_pair_ids": pair_ids,
    }
    campaign_id = _validate_record_identity(
        campaign["identity"],
        "prompt_interception_campaign_receipt",
        campaign_key,
        "campaign.identity",
    )
    limitations = (
        "legacy format has no declared task manifest, so omitted whole tasks cannot be detected",
        "legacy verifier receipts do not bind interception, A/B arm, attempt, or occurrence",
        "duplicate legacy verifier IDs are deterministic content matches, not "
        "independent-execution evidence",
        "legacy campaign context does not bind harness, disclosure, "
        "provider-boundary, or executor policy versions",
    )
    return PromptInterceptionCampaignValidation(
        campaign_id,
        _LEGACY_CAMPAIGN_FORMAT_VERSION,
        True,
        True,
        False,
        True,
        True,
        False,
        True,
        False,
        False,
        len(observed_task_contexts),
        len(arms_raw),
        len(pairs_raw),
        limitations,
    )


def _validate_campaign_arm(
    raw: object,
    *,
    label: str,
    version: str,
    catalog_digest: str,
    provider_id: str,
    model_requested: str,
    max_completion_tokens: int,
    shortlist_limit: int,
    execution_policy_digest: str | None,
    manifest_by_context: Mapping[tuple[str, str, int], Mapping[str, Any]] | None,
) -> dict[str, Any]:
    arm = _strict_mapping(raw, label)
    fields = {
        "identity",
        "format_version",
        "trajectory_id",
        "task_id",
        "step_index",
        "attempt_index",
        "pair_order",
        "request_digest",
        "retrieval_arm",
        "provider_id",
        "model_requested",
        "seed",
        "max_completion_tokens",
        "status",
        "error_code",
        "interception",
        "verification",
    }
    if version == _CAMPAIGN_FORMAT_VERSION:
        fields |= {
            "hidden_case_set_digest",
            "execution_policy_digest",
            "started_at",
            "completed_at",
            "wall_ms",
        }
    _exact_fields(arm, fields, label)
    if arm["format_version"] != version:
        raise PromptInterceptionError(f"{label}.format_version differs")
    trajectory_id = _strict_text(arm["trajectory_id"], f"{label}.trajectory_id")
    task_id = _strict_text(arm["task_id"], f"{label}.task_id")
    step_index = _nonnegative_int(arm["step_index"], f"{label}.step_index")
    attempt_index = _positive_int(arm["attempt_index"], f"{label}.attempt_index")
    pair_order = _positive_int(arm["pair_order"], f"{label}.pair_order")
    if pair_order not in {1, 2}:
        raise PromptInterceptionError(f"{label}.pair_order is invalid")
    request_digest = _strict_digest(arm["request_digest"], f"{label}.request_digest")
    retrieval_arm = _strict_text(arm["retrieval_arm"], f"{label}.retrieval_arm")
    if retrieval_arm not in {item.value for item in RetrievalArm}:
        raise PromptInterceptionError(f"{label}.retrieval_arm is invalid")
    if arm["provider_id"] != provider_id or arm["model_requested"] != model_requested:
        raise PromptInterceptionError(f"{label} provider/model context differs")
    seed = _strict_integer(arm["seed"], f"{label}.seed")
    if arm["max_completion_tokens"] != max_completion_tokens:
        raise PromptInterceptionError(f"{label} completion limit differs")
    hidden_case_set_digest: str | None = None
    if version == _CAMPAIGN_FORMAT_VERSION:
        hidden_case_set_digest = _strict_digest(
            arm["hidden_case_set_digest"], f"{label}.hidden_case_set_digest"
        )
        if arm["execution_policy_digest"] != execution_policy_digest:
            raise PromptInterceptionError(f"{label} execution policy differs")
        _strict_text(arm["started_at"], f"{label}.started_at")
        _strict_text(arm["completed_at"], f"{label}.completed_at")
        _nonnegative_int(arm["wall_ms"], f"{label}.wall_ms")
        assert manifest_by_context is not None
        manifest = manifest_by_context.get((trajectory_id, task_id, step_index))
        if manifest is None or (
            manifest["request_digest"] != request_digest
            or manifest["hidden_case_set_digest"] != hidden_case_set_digest
        ):
            raise PromptInterceptionError(f"{label} does not bind a manifest task")
        expected_first = (
            RetrievalArm.FULL_CATALOG.value
            if (attempt_index + step_index) % 2 == 0
            else RetrievalArm.DETERMINISTIC_SHORTLIST.value
        )
        expected_order = 1 if retrieval_arm == expected_first else 2
        if pair_order != expected_order:
            raise PromptInterceptionError(f"{label} pair order is not counterbalanced")

    interception: Mapping[str, Any] | None = None
    usage_id: str | None = None
    if arm["interception"] is not None:
        interception, usage_id = _validate_interception(
            arm["interception"],
            label=f"{label}.interception",
            trajectory_id=trajectory_id,
            task_id=task_id,
            step_index=step_index,
            request_digest=request_digest,
            retrieval_arm=retrieval_arm,
            catalog_digest=catalog_digest,
            provider_id=provider_id,
            model_requested=model_requested,
            shortlist_limit=shortlist_limit,
        )
    verification: Mapping[str, Any] | None = None
    verifier_id: str | None = None
    occurrence_id: str | None = None
    if arm["verification"] is not None:
        if interception is None:
            raise PromptInterceptionError(f"{label} verification lacks interception")
        verification, verifier_id, occurrence_id = _validate_verification(
            arm["verification"],
            label=f"{label}.verification",
            version=version,
            arm=arm,
            interception=interception,
            hidden_case_set_digest=hidden_case_set_digest,
            execution_policy_digest=execution_policy_digest,
        )
    status = _strict_text(arm["status"], f"{label}.status")
    error_code = arm["error_code"]
    if error_code is not None:
        _strict_text(error_code, f"{label}.error_code")
    accepted = bool(verification and verification["accepted"] is True)
    valid_state = {
        "accepted": interception is not None and accepted and error_code is None,
        "verification_failed": interception is not None
        and verification is not None
        and not accepted
        and error_code is not None,
        "teacher_rejected": interception is not None
        and interception["status"] == "teacher_rejected"
        and verification is None
        and error_code is not None,
        "provider_failed": interception is None
        and verification is None
        and error_code is not None,
        "interceptor_failed": interception is None
        and verification is None
        and error_code is not None,
        "verifier_failed": interception is not None
        and interception["status"] == "selected"
        and verification is None
        and error_code is not None,
    }
    if status not in valid_state or not valid_state[status]:
        raise PromptInterceptionError(f"{label} status/evidence state is inconsistent")
    identity_id = _validate_body_identity(
        arm, "prompt_interception_campaign_arm_receipt", label
    )
    return {
        **{key: arm[key] for key in arm if key != "identity"},
        "identity_id": identity_id,
        "usage_id": usage_id,
        "verifier_id": verifier_id,
        "occurrence_id": occurrence_id,
        "hidden_case_set_digest": hidden_case_set_digest,
    }


def _validate_interception(
    raw: object,
    *,
    label: str,
    trajectory_id: str,
    task_id: str,
    step_index: int,
    request_digest: str,
    retrieval_arm: str,
    catalog_digest: str,
    provider_id: str,
    model_requested: str,
    shortlist_limit: int,
) -> tuple[Mapping[str, Any], str]:
    receipt = _strict_mapping(raw, label)
    _exact_fields(
        receipt,
        {
            "identity",
            "format_version",
            "trajectory_id",
            "task_id",
            "step_index",
            "request_digest",
            "catalog_digest",
            "retrieval_arm",
            "shortlist_limit",
            "candidates",
            "rejections",
            "selected_primitive_id",
            "selected_release_id",
            "selected_pack_id",
            "artifact_handle",
            "status",
            "error_code",
            "model_usage",
        },
        label,
    )
    if receipt["format_version"] != _LEGACY_CAMPAIGN_FORMAT_VERSION:
        raise PromptInterceptionError(f"{label}.format_version is unsupported")
    expected_context = (
        receipt["trajectory_id"] == trajectory_id
        and receipt["task_id"] == task_id
        and receipt["step_index"] == step_index
        and receipt["request_digest"] == request_digest
        and receipt["catalog_digest"] == catalog_digest
        and receipt["retrieval_arm"] == retrieval_arm
    )
    if not expected_context:
        raise PromptInterceptionError(f"{label} differs from its arm context")
    expected_limit = (
        None if retrieval_arm == RetrievalArm.FULL_CATALOG.value else shortlist_limit
    )
    if receipt["shortlist_limit"] != expected_limit:
        raise PromptInterceptionError(f"{label}.shortlist_limit differs")
    candidates = _strict_list(receipt["candidates"], f"{label}.candidates")
    routes: set[str] = set()
    primitive_ids: set[str] = set()
    for index, item in enumerate(candidates):
        candidate = _strict_mapping(item, f"{label}.candidates[{index}]")
        _exact_fields(
            candidate,
            {"route_handle", "primitive_id", "rank", "score_microunits"},
            f"{label}.candidates[{index}]",
        )
        route = _strict_text(
            candidate["route_handle"], f"{label}.candidates[{index}].route_handle"
        )
        primitive = _strict_text(
            candidate["primitive_id"], f"{label}.candidates[{index}].primitive_id"
        )
        if route in routes or primitive in primitive_ids:
            raise PromptInterceptionError(f"{label} candidates are not unique")
        routes.add(route)
        primitive_ids.add(primitive)
        if candidate["rank"] != index + 1:
            raise PromptInterceptionError(f"{label} candidate ranks are not contiguous")
        score = candidate["score_microunits"]
        if score is not None:
            _nonnegative_int(score, f"{label}.candidates[{index}].score_microunits")
    rejections = _strict_list(receipt["rejections"], f"{label}.rejections")
    for index, item in enumerate(rejections):
        rejection = _strict_mapping(item, f"{label}.rejections[{index}]")
        _exact_fields(
            rejection,
            {"primitive_id", "reason_code"},
            f"{label}.rejections[{index}]",
        )
        _strict_text(rejection["primitive_id"], f"{label}.rejections[{index}].primitive_id")
        _strict_text(rejection["reason_code"], f"{label}.rejections[{index}].reason_code")
    status = _strict_text(receipt["status"], f"{label}.status")
    selected_values = (
        receipt["selected_primitive_id"],
        receipt["selected_release_id"],
        receipt["selected_pack_id"],
        receipt["artifact_handle"],
    )
    if status == "selected":
        if any(value is None for value in selected_values) or receipt["error_code"] is not None:
            raise PromptInterceptionError(f"{label} selected evidence is incomplete")
        if receipt["selected_primitive_id"] not in primitive_ids:
            raise PromptInterceptionError(f"{label} selected primitive is not a candidate")
        handle = _validate_artifact_handle(receipt["artifact_handle"], f"{label}.artifact_handle")
        if handle["pack_id"] != receipt["selected_pack_id"]:
            raise PromptInterceptionError(f"{label} selected pack differs from handle")
    elif status == "teacher_rejected":
        if any(value is not None for value in selected_values):
            raise PromptInterceptionError(f"{label} rejection contains a selection")
        _strict_text(receipt["error_code"], f"{label}.error_code")
    else:
        raise PromptInterceptionError(f"{label}.status is invalid")
    usage_id = _validate_model_usage(
        receipt["model_usage"],
        f"{label}.model_usage",
        provider_id=provider_id,
        model_requested=model_requested,
    )
    _validate_body_identity(receipt, "prompt_interception_receipt", label)
    return receipt, usage_id


def _validate_verification(
    raw: object,
    *,
    label: str,
    version: str,
    arm: Mapping[str, Any],
    interception: Mapping[str, Any],
    hidden_case_set_digest: str | None,
    execution_policy_digest: str | None,
) -> tuple[Mapping[str, Any], str, str | None]:
    receipt = _strict_mapping(raw, label)
    fields = {
        "identity",
        "format_version",
        "trajectory_id",
        "task_id",
        "step_index",
        "request_digest",
        "hidden_case_set_digest",
        "primitive_id",
        "release_id",
        "pack_id",
        "pack_digest",
        "artifact_handle",
        "cases",
        "executed_case_count",
        "passed_case_count",
        "accepted",
    }
    if version == _CAMPAIGN_FORMAT_VERSION:
        fields.add("occurrence")
    _exact_fields(receipt, fields, label)
    if receipt["format_version"] != version:
        raise PromptInterceptionError(f"{label}.format_version differs")
    for field in ("trajectory_id", "task_id", "step_index", "request_digest"):
        if receipt[field] != arm[field]:
            raise PromptInterceptionError(f"{label}.{field} differs from its arm")
    if (
        hidden_case_set_digest is not None
        and receipt["hidden_case_set_digest"] != hidden_case_set_digest
    ):
        raise PromptInterceptionError(f"{label} hidden case set differs from manifest")
    if (
        receipt["primitive_id"] != interception["selected_primitive_id"]
        or receipt["release_id"] != interception["selected_release_id"]
        or receipt["pack_id"] != interception["selected_pack_id"]
        or receipt["artifact_handle"] != interception["artifact_handle"]
    ):
        raise PromptInterceptionError(f"{label} selected primitive/pack binding differs")
    handle = _validate_artifact_handle(receipt["artifact_handle"], f"{label}.artifact_handle")
    if handle["pack_id"] != receipt["pack_id"] or handle["digest"] != receipt["pack_digest"]:
        raise PromptInterceptionError(f"{label} artifact handle binding differs")
    cases = _strict_list(receipt["cases"], f"{label}.cases")
    case_ids: set[str] = set()
    passed_count = 0
    case_set_values: list[dict[str, str]] = []
    for index, item in enumerate(cases):
        case = _strict_mapping(item, f"{label}.cases[{index}]")
        _exact_fields(
            case,
            {
                "case_id",
                "input_digest",
                "expected_digest",
                "output_digest",
                "pipeline_receipt_id",
                "passed",
                "error_code",
            },
            f"{label}.cases[{index}]",
        )
        case_id = _strict_text(case["case_id"], f"{label}.cases[{index}].case_id")
        if case_id in case_ids:
            raise PromptInterceptionError(f"{label} case ids are not unique")
        case_ids.add(case_id)
        input_digest = _strict_digest(
            case["input_digest"], f"{label}.cases[{index}].input_digest"
        )
        expected_digest = _strict_digest(
            case["expected_digest"], f"{label}.cases[{index}].expected_digest"
        )
        if not isinstance(case["passed"], bool):
            raise PromptInterceptionError(f"{label}.cases[{index}].passed must be boolean")
        if case["output_digest"] is not None:
            _strict_digest(case["output_digest"], f"{label}.cases[{index}].output_digest")
        if case["pipeline_receipt_id"] is not None:
            _strict_text(
                case["pipeline_receipt_id"],
                f"{label}.cases[{index}].pipeline_receipt_id",
            )
        if case["passed"]:
            passed_count += 1
            if (
                case["output_digest"] is None
                or case["pipeline_receipt_id"] is None
                or case["error_code"] is not None
            ):
                raise PromptInterceptionError(f"{label} passed case evidence is incomplete")
        else:
            _strict_text(case["error_code"], f"{label}.cases[{index}].error_code")
        case_set_values.append(
            {
                "case_id": case_id,
                "input_digest": input_digest,
                "expected_digest": expected_digest,
            }
        )
    if receipt["executed_case_count"] != len(cases):
        raise PromptInterceptionError(f"{label} executed case count differs")
    if receipt["passed_case_count"] != passed_count:
        raise PromptInterceptionError(f"{label} passed case count differs")
    accepted = bool(cases) and passed_count == len(cases)
    if receipt["accepted"] is not accepted:
        raise PromptInterceptionError(f"{label} accepted flag differs from cases")
    expected_case_set_digest = sha256_digest(canonical_json_bytes(case_set_values))
    if receipt["hidden_case_set_digest"] != expected_case_set_digest:
        raise PromptInterceptionError(f"{label} hidden case-set digest differs from cases")
    occurrence_id: str | None = None
    if version == _CAMPAIGN_FORMAT_VERSION:
        occurrence_id = _validate_occurrence(
            receipt["occurrence"],
            f"{label}.occurrence",
            arm=arm,
            interception=interception,
            execution_policy_digest=str(execution_policy_digest),
        )
    verifier_id = _validate_body_identity(
        receipt, "independent_primitive_verification_receipt", label
    )
    return receipt, verifier_id, occurrence_id


def _validate_occurrence(
    raw: object,
    label: str,
    *,
    arm: Mapping[str, Any],
    interception: Mapping[str, Any],
    execution_policy_digest: str,
) -> str:
    occurrence = _strict_mapping(raw, label)
    _exact_fields(
        occurrence,
        {
            "identity",
            "format_version",
            "verification_run_id",
            "interception_receipt_id",
            "trajectory_id",
            "task_id",
            "step_index",
            "request_digest",
            "hidden_case_set_digest",
            "retrieval_arm",
            "attempt_index",
            "pair_order",
            "provider_id",
            "model_requested",
            "seed",
            "max_completion_tokens",
            "execution_policy_digest",
        },
        label,
    )
    expected = {
        "format_version": _CAMPAIGN_FORMAT_VERSION,
        "interception_receipt_id": _identity_id_from_record(interception),
        "trajectory_id": arm["trajectory_id"],
        "task_id": arm["task_id"],
        "step_index": arm["step_index"],
        "request_digest": arm["request_digest"],
        "hidden_case_set_digest": arm["hidden_case_set_digest"],
        "retrieval_arm": arm["retrieval_arm"],
        "attempt_index": arm["attempt_index"],
        "pair_order": arm["pair_order"],
        "provider_id": arm["provider_id"],
        "model_requested": arm["model_requested"],
        "seed": arm["seed"],
        "max_completion_tokens": arm["max_completion_tokens"],
        "execution_policy_digest": execution_policy_digest,
    }
    for field, value in expected.items():
        if occurrence[field] != value:
            raise PromptInterceptionError(f"{label}.{field} differs from its arm")
    occurrence_id = _validate_record_identity(
        occurrence["identity"],
        "independent_verification_occurrence",
        expected,
        f"{label}.identity",
    )
    if occurrence["verification_run_id"] != occurrence_id:
        raise PromptInterceptionError(f"{label}.verification_run_id differs")
    return occurrence_id


def _validate_campaign_pair(
    raw: object,
    *,
    label: str,
    version: str,
    arm_by_id: Mapping[str, Mapping[str, Any]],
    execution_policy_digest: str | None,
) -> dict[str, Any]:
    pair = _strict_mapping(raw, label)
    fields = {
        "identity",
        "format_version",
        "trajectory_id",
        "task_id",
        "step_index",
        "attempt_index",
        "request_digest",
        "provider_id",
        "model_requested",
        "seed",
        "max_completion_tokens",
        "full_catalog_arm_id",
        "shortlist_arm_id",
        "full_catalog_usage",
        "shortlist_usage",
        "full_catalog_verifier_id",
        "shortlist_verifier_id",
        "full_catalog_accepted",
        "shortlist_accepted",
    }
    if version == _CAMPAIGN_FORMAT_VERSION:
        fields |= {
            "hidden_case_set_digest",
            "execution_policy_digest",
            "provider_deployment_digest",
            "full_catalog_verification_occurrence_id",
            "shortlist_verification_occurrence_id",
        }
    _exact_fields(pair, fields, label)
    if pair["format_version"] != version:
        raise PromptInterceptionError(f"{label}.format_version differs")
    full_id = _strict_text(pair["full_catalog_arm_id"], f"{label}.full_catalog_arm_id")
    shortlist_id = _strict_text(pair["shortlist_arm_id"], f"{label}.shortlist_arm_id")
    if full_id == shortlist_id:
        raise PromptInterceptionError(f"{label} reuses an arm")
    full = arm_by_id.get(full_id)
    shortlist = arm_by_id.get(shortlist_id)
    if full is None or shortlist is None:
        raise PromptInterceptionError(f"{label} references an unknown arm")
    if (
        full["retrieval_arm"] != RetrievalArm.FULL_CATALOG.value
        or shortlist["retrieval_arm"] != RetrievalArm.DETERMINISTIC_SHORTLIST.value
    ):
        raise PromptInterceptionError(f"{label} arm references are reversed")
    compared = [
        "trajectory_id",
        "task_id",
        "step_index",
        "attempt_index",
        "request_digest",
        "provider_id",
        "model_requested",
        "seed",
        "max_completion_tokens",
    ]
    if version == _CAMPAIGN_FORMAT_VERSION:
        compared += ["hidden_case_set_digest", "execution_policy_digest"]
    for field in compared:
        if full[field] != shortlist[field] or pair[field] != full[field]:
            raise PromptInterceptionError(f"{label}.{field} differs from its arms")
    expected_full_usage = (
        full["interception"]["model_usage"] if full["interception"] else None
    )
    expected_shortlist_usage = (
        shortlist["interception"]["model_usage"]
        if shortlist["interception"]
        else None
    )
    if pair["full_catalog_usage"] != expected_full_usage or pair[
        "shortlist_usage"
    ] != expected_shortlist_usage:
        raise PromptInterceptionError(f"{label} usage copies differ from arms")
    deployment_bound = False
    if expected_full_usage is not None and expected_shortlist_usage is not None:
        full_deployment = _provider_deployment(expected_full_usage)
        shortlist_deployment = _provider_deployment(expected_shortlist_usage)
        if full_deployment != shortlist_deployment:
            raise PromptInterceptionError(
                f"{label} concrete provider deployment/model differs"
            )
        if _identity_id_from_record(expected_full_usage) == _identity_id_from_record(
            expected_shortlist_usage
        ):
            raise PromptInterceptionError(f"{label} reuses a provider receipt")
        deployment_bound = True
        if version == _CAMPAIGN_FORMAT_VERSION:
            expected_deployment_digest = sha256_digest(
                canonical_json_bytes(full_deployment)
            )
            if pair["provider_deployment_digest"] != expected_deployment_digest:
                raise PromptInterceptionError(f"{label} deployment digest differs")
    elif version == _CAMPAIGN_FORMAT_VERSION and pair["provider_deployment_digest"] is not None:
        raise PromptInterceptionError(f"{label} has an ungrounded deployment digest")
    expected_full_verifier = full["verifier_id"]
    expected_shortlist_verifier = shortlist["verifier_id"]
    if (
        pair["full_catalog_verifier_id"] != expected_full_verifier
        or pair["shortlist_verifier_id"] != expected_shortlist_verifier
    ):
        raise PromptInterceptionError(f"{label} verifier references differ from arms")
    if version == _CAMPAIGN_FORMAT_VERSION:
        full_occurrence = full["occurrence_id"]
        shortlist_occurrence = shortlist["occurrence_id"]
        if (
            pair["full_catalog_verification_occurrence_id"] != full_occurrence
            or pair["shortlist_verification_occurrence_id"] != shortlist_occurrence
        ):
            raise PromptInterceptionError(f"{label} occurrence references differ from arms")
        if full_occurrence is not None and full_occurrence == shortlist_occurrence:
            raise PromptInterceptionError(f"{label} clones a verifier occurrence")
        if (
            expected_full_verifier is not None
            and expected_full_verifier == expected_shortlist_verifier
        ):
            raise PromptInterceptionError(f"{label} clones a verifier receipt")
        if pair["execution_policy_digest"] != execution_policy_digest:
            raise PromptInterceptionError(f"{label} execution policy differs")
    if pair["full_catalog_accepted"] is not bool(
        full["verification"] and full["verification"]["accepted"]
    ) or pair["shortlist_accepted"] is not bool(
        shortlist["verification"] and shortlist["verification"]["accepted"]
    ):
        raise PromptInterceptionError(f"{label} acceptance flags differ from arms")
    identity_id = _validate_body_identity(pair, "matched_prompt_interception_pair", label)
    return {
        **{key: pair[key] for key in pair if key != "identity"},
        "identity_id": identity_id,
        "deployment_bound": deployment_bound,
    }


def _validate_model_usage(
    raw: object,
    label: str,
    *,
    provider_id: str,
    model_requested: str,
) -> str:
    usage = _strict_mapping(raw, label)
    fields = {
        "identity",
        "format_version",
        "provider_id",
        "provider_api",
        "endpoint_origin",
        "model_requested",
        "model_reported",
        "request_digest",
        "response_digest",
        "content_digest",
        "started_at",
        "completed_at",
        "wall_ms",
        "prompt_tokens",
        "completion_tokens",
        "total_duration_ns",
        "load_duration_ns",
        "prompt_eval_duration_ns",
        "eval_duration_ns",
        "finish_reason",
        "usage_source",
    }
    _exact_fields(usage, fields, label)
    if usage["format_version"] != _LEGACY_CAMPAIGN_FORMAT_VERSION:
        raise PromptInterceptionError(f"{label}.format_version is unsupported")
    if usage["provider_id"] != provider_id or usage["model_requested"] != model_requested:
        raise PromptInterceptionError(f"{label} provider/model context differs")
    for field in (
        "provider_api",
        "endpoint_origin",
        "model_reported",
        "started_at",
        "completed_at",
        "usage_source",
    ):
        _strict_text(usage[field], f"{label}.{field}")
    for field in ("request_digest", "response_digest", "content_digest"):
        _strict_digest(usage[field], f"{label}.{field}")
    for field in ("wall_ms", "prompt_tokens", "completion_tokens"):
        _nonnegative_int(usage[field], f"{label}.{field}")
    for field in (
        "total_duration_ns",
        "load_duration_ns",
        "prompt_eval_duration_ns",
        "eval_duration_ns",
    ):
        if usage[field] is not None:
            _nonnegative_int(usage[field], f"{label}.{field}")
    if usage["finish_reason"] is not None:
        _strict_text(usage["finish_reason"], f"{label}.finish_reason")
    return _validate_body_identity(usage, "model_usage_receipt", label)


def _validate_artifact_handle(raw: object, label: str) -> Mapping[str, Any]:
    handle = _strict_mapping(raw, label)
    _exact_fields(
        handle,
        {"scope", "location", "pack_id", "digest", "size_bytes"},
        label,
    )
    try:
        ScopedArtifactHandle(
            _strict_text(handle["scope"], f"{label}.scope"),
            _strict_text(handle["location"], f"{label}.location"),
            _strict_text(handle["pack_id"], f"{label}.pack_id"),
            _strict_digest(handle["digest"], f"{label}.digest"),
            _positive_int(handle["size_bytes"], f"{label}.size_bytes"),
        )
    except PromptInterceptionError:
        raise
    return handle


def _validate_expected_counts(
    raw: object, task_count: int, seed_count: int
) -> dict[str, int]:
    value = _strict_mapping(raw, "campaign.expected_counts")
    fields = {
        "task_count",
        "seed_count",
        "task_seed_count",
        "retrieval_conditions_per_task_seed",
        "arm_count",
        "matched_pair_count",
    }
    _exact_fields(value, fields, "campaign.expected_counts")
    result = {
        field: _positive_int(value[field], f"campaign.expected_counts.{field}")
        for field in fields
    }
    expected = CampaignExpectedCounts.create(
        task_count=task_count, seed_count=seed_count
    ).to_dict()
    if result != expected:
        raise PromptInterceptionError("campaign expected counts are inconsistent")
    return result


def _validate_execution_policy(raw: object) -> dict[str, Any]:
    value = _strict_mapping(raw, "campaign.execution_policy")
    fields = {
        "prompt_template_version",
        "campaign_harness_version",
        "shortlister_version",
        "verifier_version",
        "executor_version",
        "python_runtime_version",
        "temperature",
        "request_timeout_ms",
        "max_response_bytes",
        "provider_endpoint_policy",
        "prompt_harness_digest",
        "verifier_runtime_digest",
        "provider_policy_digest",
    }
    _exact_fields(value, fields, "campaign.execution_policy")
    for field in fields - {"request_timeout_ms", "max_response_bytes"}:
        _strict_text(value[field], f"campaign.execution_policy.{field}")
    _positive_int(
        value["request_timeout_ms"], "campaign.execution_policy.request_timeout_ms"
    )
    _positive_int(
        value["max_response_bytes"], "campaign.execution_policy.max_response_bytes"
    )
    if value["temperature"] != "0":
        raise PromptInterceptionError("campaign execution policy temperature differs")
    supported = {
        "prompt_template_version": "prompt-interception-teacher-v1",
        "campaign_harness_version": "prompt-interception-campaign-v2",
        "shortlister_version": "deterministic-integer-bm25-v1",
        "verifier_version": "independent-pack-verifier-v2",
        "executor_version": "local-deterministic-python-exact-wire-v1",
        "provider_endpoint_policy": (
            "https-or-loopback-http-no-redirects-v1"
        ),
    }
    if any(value[field] != expected for field, expected in supported.items()):
        raise PromptInterceptionError(
            "campaign execution policy contains an unsupported component version"
        )
    if not str(value["python_runtime_version"]).startswith("3.12."):
        raise PromptInterceptionError(
            "campaign execution policy requires a Python 3.12 runtime"
        )
    component_values = {
        "prompt_harness_digest": {
            "prompt_template_version": value["prompt_template_version"],
            "campaign_harness_version": value["campaign_harness_version"],
            "shortlister_version": value["shortlister_version"],
            "temperature": value["temperature"],
        },
        "verifier_runtime_digest": {
            "verifier_version": value["verifier_version"],
            "executor_version": value["executor_version"],
            "python_runtime_version": value["python_runtime_version"],
        },
        "provider_policy_digest": {
            "temperature": value["temperature"],
            "request_timeout_ms": value["request_timeout_ms"],
            "max_response_bytes": value["max_response_bytes"],
            "provider_endpoint_policy": value["provider_endpoint_policy"],
        },
    }
    for field, component in component_values.items():
        _strict_digest(value[field], f"campaign.execution_policy.{field}")
        if value[field] != sha256_digest(canonical_json_bytes(component)):
            raise PromptInterceptionError(
                f"campaign execution policy {field} differs from its component"
            )
    return dict(value)


def _provider_deployment(usage: Mapping[str, Any]) -> dict[str, str]:
    return {
        "provider_id": str(usage["provider_id"]),
        "provider_api": str(usage["provider_api"]),
        "endpoint_origin": str(usage["endpoint_origin"]),
        "model_reported": str(usage["model_reported"]),
    }


def _arm_condition_key(arm: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        arm["trajectory_id"],
        arm["task_id"],
        arm["step_index"],
        arm["request_digest"],
        arm["hidden_case_set_digest"],
        arm["attempt_index"],
        arm["seed"],
        arm["retrieval_arm"],
    )


def _legacy_arm_condition_key(arm: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        arm["trajectory_id"],
        arm["task_id"],
        arm["step_index"],
        arm["request_digest"],
        arm["attempt_index"],
        arm["seed"],
        arm["retrieval_arm"],
    )


def _pair_context_key(pair: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        pair["trajectory_id"],
        pair["task_id"],
        pair["step_index"],
        pair["request_digest"],
        pair["hidden_case_set_digest"],
        pair["attempt_index"],
        pair["seed"],
    )


def _legacy_pair_context_key(pair: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        pair["trajectory_id"],
        pair["task_id"],
        pair["step_index"],
        pair["request_digest"],
        pair["attempt_index"],
        pair["seed"],
    )


def _validated_arm_for_raw(
    raw: object, arm_by_id: Mapping[str, Mapping[str, Any]]
) -> Mapping[str, Any]:
    identity_id = _identity_id_from_record(_strict_mapping(raw, "campaign.arms[]"))
    return arm_by_id[identity_id]


def _validate_body_identity(
    record: Mapping[str, Any], kind: str, label: str
) -> str:
    key = {name: value for name, value in record.items() if name != "identity"}
    return _validate_record_identity(
        record.get("identity"), kind, key, f"{label}.identity"
    )


def _validate_record_identity(
    raw: object, kind: str, canonical_key: Mapping[str, Any], label: str
) -> str:
    identity = _strict_mapping(raw, label)
    _exact_fields(identity, {"id", "kind", "canonical_key"}, label)
    expected = IdentityRecord.create(kind, canonical_key).to_dict()
    if dict(identity) != expected:
        raise PromptInterceptionError(f"{label} does not match its exact record body")
    return str(expected["id"])


def _identity_id_from_record(record: Mapping[str, Any]) -> str:
    identity = _strict_mapping(record.get("identity"), "record.identity")
    return _strict_text(identity.get("id"), "record.identity.id")


def _strict_mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise PromptInterceptionError(f"{label} must be an object")
    return value


def _strict_list(value: object, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise PromptInterceptionError(f"{label} must be an array")
    return value


def _exact_fields(value: Mapping[str, Any], fields: set[str], label: str) -> None:
    if set(value) != fields:
        raise PromptInterceptionError(f"{label} fields differ from the format")


def _strict_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise PromptInterceptionError(f"{label} must be a non-empty string")
    return value


def _strict_digest(value: object, label: str) -> str:
    text = _strict_text(value, label)
    if not _DIGEST.fullmatch(text):
        raise PromptInterceptionError(f"{label} must be a SHA-256 digest")
    return text


def _strict_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise PromptInterceptionError(f"{label} must be an integer")
    return value


def _nonnegative_int(value: object, label: str) -> int:
    result = _strict_integer(value, label)
    if result < 0:
        raise PromptInterceptionError(f"{label} must be non-negative")
    return result


def _positive_int(value: object, label: str) -> int:
    result = _strict_integer(value, label)
    if result <= 0:
        raise PromptInterceptionError(f"{label} must be positive")
    return result


def _integer_list(value: object, label: str) -> list[int]:
    return [
        _strict_integer(item, f"{label}[{index}]")
        for index, item in enumerate(_strict_list(value, label))
    ]


def _utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def _tokens(value: str) -> tuple[str, ...]:
    return tuple(
        token
        for token in _TOKEN.findall(value.casefold())
        if token not in _STOPWORDS
    )


def _weighted_card_tokens(card: PrimitiveCard) -> tuple[str, ...]:
    """Apply generic field weights without consulting task labels or oracle data."""

    name = _tokens(card.name)
    keywords = _tokens(" ".join(card.keywords))
    use_cases = _tokens(" ".join(card.use_cases))
    summary = _tokens(card.summary)
    namespace = _tokens(card.namespace)
    return name * 6 + keywords * 4 + use_cases * 2 + summary + namespace


def _required_string(value: Mapping[str, Any], field: str) -> str:
    result = value.get(field)
    if not isinstance(result, str) or not result.strip():
        raise PromptInterceptionError(f"{field} must be a non-empty string")
    return result.strip()


def _required_integer(value: Mapping[str, Any], field: str) -> int:
    result = value.get(field)
    if isinstance(result, bool) or not isinstance(result, int):
        raise PromptInterceptionError(f"{field} must be an integer")
    return result


def _required_string_tuple(value: Mapping[str, Any], field: str) -> tuple[str, ...]:
    result = value.get(field)
    if not isinstance(result, list) or not result or not all(
        isinstance(item, str) and item.strip() for item in result
    ):
        raise PromptInterceptionError(f"{field} must be a non-empty string list")
    prepared = tuple(item.strip() for item in result)
    if len(set(prepared)) != len(prepared):
        raise PromptInterceptionError(f"{field} cannot contain duplicates")
    return prepared


def _require_digest(value: str, subject: str) -> None:
    if not _DIGEST.fullmatch(value):
        raise PromptInterceptionError(f"{subject} digest is invalid")


def _require_uceg_id(value: str, kind: str) -> None:
    prefix = f"{_IDENTITY_PREFIX}{kind}:"
    if not value.startswith(prefix) or len(value) <= len(prefix):
        raise PromptInterceptionError(f"{kind} identity is invalid")


def _exception_code(scope: str, exc: Exception) -> str:
    name = _ERROR_TOKEN.sub("_", type(exc).__name__.casefold()).strip("_")
    return f"{scope}_{name or 'error'}"
