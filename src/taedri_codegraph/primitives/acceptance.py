"""Executable acceptance worker for complete Python primitive capsules.

The bootstrap verifier is intentionally narrow and real: an exact match to the local
Python major/minor, JSON-vector examples/tests, a pinned dependency lock, no declared
network, bounded subprocess time, pack download, safe materialization, and exact
output/error checks. Other language and runtime verifiers register alongside it; they
do not weaken the release contract.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol

from ..canonical import canonical_json_bytes, sha256_digest
from ..contracts import RecordMixin
from ..primitive_capsules import CapsuleRole, RefKind
from ..primitive_repository import ReleasedPrimitive, SQLitePrimitiveRepository
from .digestion import DigestionPolicy, DigestionReceipt, PrimitiveDigester
from .release import (
    AssuranceLevel,
    PrimitiveAcceptanceReceipt,
    PrimitiveReleaseAuthorization,
    PrimitiveReleaseError,
    REQUIRED_ACCEPTANCE_PROOFS,
    inspect_release_artifacts,
)


_RUNNER = r'''
import asyncio
import contextlib
import hashlib
import importlib.util
import inspect
import io
import json
import pathlib
import sys

request = json.loads(sys.stdin.read())
root = pathlib.Path(request["root"]).resolve()
source = (root / request["entrypoint_path"]).resolve()
if root not in source.parents:
    raise SystemExit("entrypoint escaped materialized root")

def audit(event, args):
    if event.startswith("socket.") or event in {"subprocess.Popen", "os.system", "os.posix_spawn"}:
        raise PermissionError("primitive execution policy denied " + event)

sys.addaudithook(audit)
sys.path.insert(0, str(root))
captured = io.StringIO()
with contextlib.redirect_stdout(captured), contextlib.redirect_stderr(captured):
    spec = importlib.util.spec_from_file_location("taedri_verified_primitive", source)
    if spec is None or spec.loader is None:
        raise SystemExit("entrypoint module could not be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    target = getattr(module, request["entrypoint_symbol"])
    observations = []
    for case in request["cases"]:
        try:
            value = target(*case.get("args", []), **case.get("kwargs", {}))
            if inspect.isawaitable(value):
                value = asyncio.run(value)
        except BaseException as exc:
            expected = case.get("expected_error")
            if expected != type(exc).__name__:
                raise AssertionError(
                    "expected error %r but received %s" % (expected, type(exc).__name__)
                ) from exc
            observations.append({"error": type(exc).__name__})
        else:
            if "expected_error" in case:
                raise AssertionError("expected error %r but call succeeded" % case["expected_error"])
            if value != case.get("expected"):
                raise AssertionError("primitive result did not match the exact oracle")
            observations.append({"result": value})
payload = json.dumps(observations, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
print(json.dumps({
    "status": "passed",
    "executed_case_count": len(observations),
    "observation_digest": "sha256:" + hashlib.sha256(payload).hexdigest(),
    "captured_output_digest": "sha256:" + hashlib.sha256(captured.getvalue().encode()).hexdigest(),
}, sort_keys=True, separators=(",", ":")))
'''

_PYTHON_SYMBOL = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True, slots=True)
class PrimitiveAcceptanceResult(RecordMixin):
    released: ReleasedPrimitive
    acceptance: PrimitiveAcceptanceReceipt
    acceptance_receipt_ref: str
    digestion: DigestionReceipt
    executed_case_count: int


class PrimitiveVerifier(Protocol):
    """Executable language verifier registered by exact runtime language."""

    language: str

    def verify_and_release(
        self,
        tenant_id: str,
        revision_id: str,
        *,
        ref_kind: RefKind,
        ref_name: str,
        authorizer_id: str,
        policy_decision_id: str,
        verified_at: str,
        assurance_level: AssuranceLevel = AssuranceLevel.BOOTSTRAP,
    ) -> PrimitiveAcceptanceResult: ...


class PrimitiveVerifierRegistry:
    """Fail-closed dispatch port for independently implemented runtime verifiers."""

    def __init__(self, repository: SQLitePrimitiveRepository) -> None:
        self.repository = repository
        self._verifiers: dict[str, PrimitiveVerifier] = {}

    def register(self, verifier: PrimitiveVerifier) -> None:
        language = verifier.language.strip().lower()
        if not language or language in self._verifiers:
            raise PrimitiveReleaseError(
                f"primitive verifier language is empty or already registered: {language!r}"
            )
        self._verifiers[language] = verifier

    @property
    def languages(self) -> tuple[str, ...]:
        return tuple(sorted(self._verifiers))

    def verify_and_release(
        self,
        tenant_id: str,
        revision_id: str,
        *,
        ref_kind: RefKind,
        ref_name: str,
        authorizer_id: str,
        policy_decision_id: str,
        verified_at: str,
        assurance_level: AssuranceLevel = AssuranceLevel.BOOTSTRAP,
    ) -> PrimitiveAcceptanceResult:
        content = self.repository.staged_revision(tenant_id, revision_id)
        artifacts = inspect_release_artifacts(content.tree, content.blobs)
        try:
            verifier = self._verifiers[artifacts.language.lower()]
        except KeyError as exc:
            raise PrimitiveReleaseError(
                f"no executable verifier is registered for language {artifacts.language!r}"
            ) from exc
        return verifier.verify_and_release(
            tenant_id,
            revision_id,
            ref_kind=ref_kind,
            ref_name=ref_name,
            authorizer_id=authorizer_id,
            policy_decision_id=policy_decision_id,
            verified_at=verified_at,
            assurance_level=assurance_level,
        )


class LocalPythonPrimitiveVerifier:
    """Verify and release complete trusted-source Python primitive revisions."""

    language = "python"

    def __init__(
        self,
        repository: SQLitePrimitiveRepository,
        *,
        verifier_id: str = "taedri.verifier.local-python-v1",
        timeout_seconds: float = 10.0,
    ) -> None:
        if not verifier_id or not 0.1 <= timeout_seconds <= 120:
            raise ValueError("verifier ID and a bounded timeout are required")
        self.repository = repository
        self.verifier_id = verifier_id
        self.timeout_seconds = timeout_seconds

    def verify_and_release(
        self,
        tenant_id: str,
        revision_id: str,
        *,
        ref_kind: RefKind,
        ref_name: str,
        authorizer_id: str,
        policy_decision_id: str,
        verified_at: str,
        assurance_level: AssuranceLevel = AssuranceLevel.BOOTSTRAP,
    ) -> PrimitiveAcceptanceResult:
        content = self.repository.staged_revision(tenant_id, revision_id)
        artifacts = inspect_release_artifacts(content.tree, content.blobs)
        if artifacts.language != self.language:
            raise PrimitiveReleaseError(
                f"Python verifier cannot execute {artifacts.language!r} primitives"
            )
        if not artifacts.entrypoint_path.endswith(".py") or not _PYTHON_SYMBOL.fullmatch(
            artifacts.entrypoint
        ):
            raise PrimitiveReleaseError(
                "Python v1 entrypoint requires a .py source path and simple symbol name"
            )
        expected_runtime = f"{sys.version_info.major}.{sys.version_info.minor}"
        if artifacts.runtime_version != expected_runtime:
            raise PrimitiveReleaseError(
                f"primitive pins Python {artifacts.runtime_version}; verifier runs {expected_runtime}"
            )
        pack, encoded = self.repository.pack_revision(tenant_id, revision_id)
        with tempfile.TemporaryDirectory(prefix="taedri-primitive-acceptance-") as temporary:
            root = Path(temporary) / "materialized"
            digestion = PrimitiveDigester(
                DigestionPolicy(allowed_roles=tuple(CapsuleRole))
            ).materialize(encoded, root)
            examples = _role_json(content.tree, content.blobs, CapsuleRole.EXAMPLE)[
                "examples"
            ]
            tests = _role_json(content.tree, content.blobs, CapsuleRole.TEST)["cases"]
            cases = [*examples, *tests]
            request = {
                "root": root.as_posix(),
                "entrypoint_path": artifacts.entrypoint_path,
                "entrypoint_symbol": artifacts.entrypoint,
                "cases": cases,
            }
            completed = subprocess.run(
                (sys.executable, "-I", "-c", _RUNNER),
                input=canonical_json_bytes(request),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=root,
                env={"PYTHONHASHSEED": "0", "PYTHONIOENCODING": "utf-8"},
                timeout=self.timeout_seconds,
                check=False,
            )
        if completed.returncode != 0:
            detail = completed.stderr.decode("utf-8", "replace")[-2000:]
            raise PrimitiveReleaseError(
                "primitive executable acceptance failed: " + detail
            )
        if len(completed.stdout) > 64 * 1024:
            raise PrimitiveReleaseError("primitive verifier output exceeded its bound")
        try:
            execution = json.loads(completed.stdout)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise PrimitiveReleaseError("primitive verifier returned invalid JSON") from exc
        if not isinstance(execution, Mapping) or execution.get("status") != "passed":
            raise PrimitiveReleaseError("primitive verifier did not return passed status")
        executed = int(execution.get("executed_case_count", 0))
        output_digest = sha256_digest(
            canonical_json_bytes(
                {
                    "pack_id": pack.identity.id,
                    "pack_digest": digestion.pack_digest,
                    "materialization": {
                        "files": [item.to_dict() for item in digestion.files],
                        "omitted_roles": digestion.omitted_roles,
                        "materialized_bytes": digestion.materialized_bytes,
                        "cache_hits": digestion.cache_hits,
                        "executable_bits_removed": digestion.executable_bits_removed,
                    },
                    "execution": dict(execution),
                }
            )
        )
        acceptance = PrimitiveAcceptanceReceipt.create(
            revision_id=revision_id,
            tree_id=content.tree.identity.id,
            source_digest=artifacts.source_digest,
            verifier_id=self.verifier_id,
            implementation_producer_id=artifacts.implementation_producer_id,
            oracle_producer_id=artifacts.oracle_producer_id,
            verified_at=verified_at,
            proofs=tuple(REQUIRED_ACCEPTANCE_PROOFS),
            executed_case_count=executed,
            language=artifacts.language,
            runtime_version=artifacts.runtime_version,
            output_digest=output_digest,
        )
        receipt_ref = self.repository.control.put_job_payload(
            tenant_id, acceptance.to_dict(), created_at=verified_at
        )
        released = self.repository.release(
            tenant_id,
            revision_id=revision_id,
            ref_kind=ref_kind,
            ref_name=ref_name,
            acceptance_receipt_ref=receipt_ref,
            authorization=PrimitiveReleaseAuthorization(
                authorizer_id,
                policy_decision_id,
                verified_at,
                assurance_level,
            ),
        )
        return PrimitiveAcceptanceResult(
            released,
            acceptance,
            receipt_ref,
            digestion,
            executed,
        )


def _role_json(tree, blobs: Mapping[str, bytes], role: CapsuleRole) -> Mapping[str, Any]:
    entries = [entry for entry in tree.entries if entry.role is role]
    if len(entries) != 1:
        raise PrimitiveReleaseError(f"expected one {role.value} role record")
    try:
        value = json.loads(blobs[entries[0].blob.digest])
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PrimitiveReleaseError(f"{role.value} record is invalid JSON") from exc
    if not isinstance(value, Mapping):
        raise PrimitiveReleaseError(f"{role.value} record must be an object")
    return value
