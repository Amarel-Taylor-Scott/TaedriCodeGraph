"""Atomic primitive write waterfall over immutable capsule repository contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Protocol

from ..canonical import canonical_json_bytes, sha256_digest
from ..contracts import RecordMixin
from ..mechanisms import (
    FailurePolicy,
    MechanismDefinition,
    MechanismMode,
    MechanismRegistry,
    MechanismResult,
    StageDefinition,
    WaterfallExecutor,
    WaterfallPlan,
    WaterfallRun,
)
from ..primitive_capsules import CapsuleRole, RefKind
from ..primitive_repository import (
    PrimitiveFileInput,
    StagedPrimitive,
    SQLitePrimitiveRepository,
)


class PrimitiveStorageProjection(Protocol):
    """Optional candidate projection hook run after immutable staging."""

    @property
    def definition(self) -> MechanismDefinition: ...

    def project(
        self, request: "PrimitiveWriteRequest", staged: StagedPrimitive
    ) -> MechanismResult: ...


@dataclass(frozen=True, slots=True)
class PrimitiveWriteRequest(RecordMixin):
    tenant_id: str
    namespace: str
    name: str
    files: tuple[PrimitiveFileInput, ...]
    contract_path: str
    ref_kind: RefKind
    ref_name: str
    expected_revision_id: str | None
    actor: str
    created_at: str
    message: str
    graph_epoch_id: str | None = None
    parent_revision_ids: tuple[str, ...] | None = None
    generation_run_id: str | None = None
    evidence_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.tenant_id or not self.namespace or not self.name:
            raise ValueError("tenant, namespace, and primitive name are required")
        if not self.files:
            raise ValueError("primitive write requires at least one file")
        paths = tuple(item.path for item in self.files)
        if len(paths) != len(set(paths)):
            raise ValueError("primitive file paths must be unique")
        contracts = tuple(
            item for item in self.files if item.path == self.contract_path
        )
        if len(contracts) != 1 or contracts[0].role is not CapsuleRole.CONTRACT:
            raise ValueError("contract_path must select exactly one contract-role file")
        if not any(item.role is CapsuleRole.SOURCE for item in self.files):
            raise ValueError("primitive write requires source-role content")
        if not self.actor or not self.created_at or not self.message:
            raise ValueError("primitive author, creation time, and message are required")
        object.__setattr__(self, "evidence_ids", tuple(sorted(set(self.evidence_ids))))
        if self.parent_revision_ids is not None:
            parents = tuple(self.parent_revision_ids)
            if len(parents) != len(set(parents)):
                raise ValueError("parent revision IDs must be unique")
            object.__setattr__(self, "parent_revision_ids", parents)

    def receipt_input(self) -> dict[str, object]:
        """Return identity-safe metadata; raw primitive bytes never enter run receipts."""

        return {
            "tenant_id": self.tenant_id,
            "namespace": self.namespace,
            "name": self.name,
            "files": [
                {
                    "path": item.path,
                    "role": item.role.value,
                    "media_type": item.media_type,
                    "mode": item.mode,
                    "digest": sha256_digest(item.content),
                    "size_bytes": len(item.content),
                }
                for item in sorted(self.files, key=lambda value: value.path)
            ],
            "contract_path": self.contract_path,
            "ref_kind": self.ref_kind.value,
            "ref_name": self.ref_name,
            "expected_revision_id": self.expected_revision_id,
            "graph_epoch_id": self.graph_epoch_id,
            "parent_revision_ids": self.parent_revision_ids,
            "generation_run_id": self.generation_run_id,
            "evidence_ids": self.evidence_ids,
        }


@dataclass(frozen=True, slots=True)
class PrimitiveStorageReceipt(RecordMixin):
    staged: StagedPrimitive
    waterfall: WaterfallRun
    content_manifest_digest: str
    projection_refs: tuple[str, ...]


class PrimitiveStorageService:
    """Coordinates immutable staging; only acceptance workers may release revisions."""

    VALIDATE = "taedri.storage.validate"
    PERSIST = "taedri.storage.persist"
    PROJECT = "taedri.storage.project"

    def __init__(
        self,
        repository: SQLitePrimitiveRepository,
        *,
        projections: Iterable[PrimitiveStorageProjection] = (),
    ) -> None:
        self.repository = repository
        self.projections = tuple(projections)
        references = [projection.definition.ref for projection in self.projections]
        if len(references) != len(set(references)):
            raise ValueError("primitive storage projection mechanisms must be unique")
        for projection in self.projections:
            if projection.definition.phase != self.PROJECT:
                raise ValueError("primitive projection mechanism has the wrong phase")

    def stage(self, request: PrimitiveWriteRequest) -> PrimitiveStorageReceipt:
        registry = MechanismRegistry()
        state: dict[str, StagedPrimitive] = {}
        validate_definition = MechanismDefinition(
            "taedri.primitive.validate_capsule",
            "1.0.0",
            self.VALIDATE,
            True,
            output_facets=("validation",),
        )
        persist_definition = MechanismDefinition(
            "taedri.primitive.persist_revision",
            "1.0.0",
            self.PERSIST,
            True,
            cost_units=4,
            output_facets=("handle", "tree", "revision", "ref"),
        )
        registry.register(
            validate_definition,
            lambda _invocation: MechanismResult(
                {
                    "valid": True,
                    "file_count": len(request.files),
                    "content_bytes": sum(len(item.content) for item in request.files),
                },
                1_000_000,
            ),
        )

        def persist(_invocation: object) -> MechanismResult:
            staged = self.repository.stage(
                request.tenant_id,
                namespace=request.namespace,
                name=request.name,
                files=request.files,
                contract_path=request.contract_path,
                ref_kind=request.ref_kind,
                ref_name=request.ref_name,
                expected_revision_id=request.expected_revision_id,
                actor=request.actor,
                created_at=request.created_at,
                message=request.message,
                graph_epoch_id=request.graph_epoch_id,
                parent_revision_ids=request.parent_revision_ids,
                generation_run_id=request.generation_run_id,
                evidence_ids=request.evidence_ids,
            )
            state["staged"] = staged
            return MechanismResult(
                {
                    "primitive_id": staged.handle.identity.id,
                    "tree_id": staged.tree.identity.id,
                    "revision_id": staged.revision.identity.id,
                    "ref_update_id": staged.ref_update.identity.id,
                },
                1_000_000,
                (staged.revision.identity.id,),
            )

        registry.register(persist_definition, persist)
        for projection in self.projections:
            registry.register(
                projection.definition,
                lambda _invocation, item=projection: item.project(
                    request, state["staged"]
                ),
            )
        stages = [
            StageDefinition(
                self.VALIDATE,
                (validate_definition.ref,),
                MechanismMode.ALL,
                FailurePolicy.FAIL_CLOSED,
            ),
            StageDefinition(
                self.PERSIST,
                (persist_definition.ref,),
                MechanismMode.ALL,
                FailurePolicy.FAIL_CLOSED,
            ),
        ]
        if self.projections:
            stages.append(
                StageDefinition(
                    self.PROJECT,
                    tuple(item.definition.ref for item in self.projections),
                    MechanismMode.ALL,
                    FailurePolicy.CONTINUE,
                    minimum_successes=0,
                )
            )
        plan = WaterfallPlan(
            "taedri.plan.primitive_storage", "1.0.0", tuple(stages)
        )
        waterfall = WaterfallExecutor(registry).execute(
            plan,
            request.receipt_input(),
            correlation_id=f"{request.tenant_id}:{request.namespace}/{request.name}",
        )
        staged = state.get("staged")
        if staged is None:
            raise RuntimeError(f"primitive storage failed: {waterfall.stop_reason}")
        manifest_digest = sha256_digest(
            canonical_json_bytes(request.receipt_input()["files"])
        )
        return PrimitiveStorageReceipt(
            staged,
            waterfall,
            manifest_digest,
            tuple(item.definition.ref for item in self.projections),
        )
