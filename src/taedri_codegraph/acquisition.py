"""Bounded, allowlisted acquisition of immutable PyPI and GitHub artifacts."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
import urllib.error
import urllib.request
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Protocol
from urllib.parse import quote, urlsplit, urlunsplit

from .canonical import canonical_digest, canonical_json_bytes, sha256_digest, to_primitive
from .contracts import (
    EvidenceRecord,
    GraphBundle,
    ProducerRef,
    RecordMixin,
    SubjectRef,
    TypedValue,
    ValueKind,
)
from .identity import IdentityRecord
from .representations import RepresentationSeed, materialize_seeds


_PROJECT = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]{0,126}[A-Za-z0-9])?$")
_REPOSITORY = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9_.-]{0,99})/[A-Za-z0-9](?:[A-Za-z0-9_.-]{0,99})$"
)
_COMMIT = re.compile(r"^[0-9a-fA-F]{40}$")
_SHA256_HEX = re.compile(r"^[0-9a-fA-F]{64}$")


class AcquisitionError(ValueError):
    """Raised for a non-retryable acquisition policy or integrity failure."""


class RetryableAcquisitionError(AcquisitionError):
    """Raised when a bounded network failure may safely be retried."""


@dataclass(frozen=True, slots=True)
class NetworkAcquisitionPolicy:
    allowed_hosts: tuple[str, ...] = (
        "api.github.com",
        "codeload.github.com",
        "files.pythonhosted.org",
        "pypi.org",
    )
    metadata_max_bytes: int = 5 * 1024 * 1024
    artifact_max_bytes: int = 512 * 1024 * 1024
    timeout_seconds: float = 30.0
    max_archive_members: int = 200_000
    max_archive_member_bytes: int = 128 * 1024 * 1024
    max_archive_uncompressed_bytes: int = 2 * 1024 * 1024 * 1024
    user_agent: str = "TaedriCodeGraph/0.1 (+https://github.com/Amarel-Taylor-Scott/TaedriCodeGraph)"

    def __post_init__(self) -> None:
        normalized = tuple(sorted(set(host.casefold() for host in self.allowed_hosts)))
        if not normalized or any(not host or ":" in host or "/" in host for host in normalized):
            raise AcquisitionError("acquisition hosts must be exact DNS names")
        if min(
            self.metadata_max_bytes,
            self.artifact_max_bytes,
            self.max_archive_members,
            self.max_archive_member_bytes,
            self.max_archive_uncompressed_bytes,
        ) <= 0:
            raise AcquisitionError("acquisition limits must be positive")
        if not 0.1 <= self.timeout_seconds <= 300:
            raise AcquisitionError("acquisition timeout must be between 0.1 and 300 seconds")
        object.__setattr__(self, "allowed_hosts", normalized)

    def validate_url(self, url: str) -> str:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").casefold()
        if parsed.scheme != "https" or host not in self.allowed_hosts:
            raise AcquisitionError("acquisition URL is outside the exact HTTPS host allowlist")
        if parsed.username is not None or parsed.password is not None:
            raise AcquisitionError("acquisition URLs cannot contain credentials")
        if parsed.port not in {None, 443} or parsed.fragment:
            raise AcquisitionError("acquisition URL contains a forbidden port or fragment")
        return url

    @property
    def digest(self) -> str:
        return canonical_digest(
            {
                "allowed_hosts": self.allowed_hosts,
                "metadata_max_bytes": self.metadata_max_bytes,
                "artifact_max_bytes": self.artifact_max_bytes,
                "timeout_seconds_millis": round(self.timeout_seconds * 1000),
                "max_archive_members": self.max_archive_members,
                "max_archive_member_bytes": self.max_archive_member_bytes,
                "max_archive_uncompressed_bytes": self.max_archive_uncompressed_bytes,
            }
        )


@dataclass(frozen=True, slots=True)
class HTTPDocument:
    value: Mapping[str, Any]
    final_url: str
    content_digest: str
    size_bytes: int


@dataclass(frozen=True, slots=True)
class DownloadedArtifact:
    path: Path
    final_url: str
    content_digest: str
    size_bytes: int
    media_type: str


class AcquisitionTransport(Protocol):
    def get_json(
        self, url: str, *, headers: Mapping[str, str] | None = None
    ) -> HTTPDocument: ...

    def download(
        self,
        url: str,
        destination: Path,
        *,
        headers: Mapping[str, str] | None = None,
        expected_digest: str | None = None,
        expected_size: int | None = None,
    ) -> DownloadedArtifact: ...


class _AllowlistedRedirectHandler(urllib.request.HTTPRedirectHandler):
    def __init__(self, policy: NetworkAcquisitionPolicy):
        self.policy = policy
        super().__init__()

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        self.policy.validate_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class BoundedHTTPTransport:
    """Standard-library HTTPS transport with redirect, byte, and digest enforcement."""

    def __init__(self, policy: NetworkAcquisitionPolicy | None = None):
        self.policy = policy or NetworkAcquisitionPolicy()
        self._opener = urllib.request.build_opener(_AllowlistedRedirectHandler(self.policy))

    def get_json(
        self, url: str, *, headers: Mapping[str, str] | None = None
    ) -> HTTPDocument:
        response = self._open(url, headers=headers, accept="application/json")
        with response:
            declared = _content_length(response.headers)
            if declared is not None and declared > self.policy.metadata_max_bytes:
                raise AcquisitionError("metadata response exceeds the configured byte limit")
            content = response.read(self.policy.metadata_max_bytes + 1)
            if len(content) > self.policy.metadata_max_bytes:
                raise AcquisitionError("metadata response exceeds the configured byte limit")
            final_url = self.policy.validate_url(response.geturl())
        try:
            value = json.loads(content)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise AcquisitionError("acquisition metadata is not valid JSON") from exc
        if not isinstance(value, Mapping):
            raise AcquisitionError("acquisition metadata must be a JSON object")
        return HTTPDocument(value, final_url, sha256_digest(content), len(content))

    def download(
        self,
        url: str,
        destination: Path,
        *,
        headers: Mapping[str, str] | None = None,
        expected_digest: str | None = None,
        expected_size: int | None = None,
    ) -> DownloadedArtifact:
        destination.parent.mkdir(parents=True, exist_ok=True)
        response = self._open(url, headers=headers, accept="application/octet-stream")
        temporary = destination.with_name(f".{destination.name}.tmp-{uuid.uuid4().hex}")
        digest = hashlib.sha256()
        size = 0
        try:
            with response, temporary.open("xb") as output:
                declared = _content_length(response.headers)
                if declared is not None and declared > self.policy.artifact_max_bytes:
                    raise AcquisitionError("artifact exceeds the configured byte limit")
                while True:
                    chunk = response.read(min(1024 * 1024, self.policy.artifact_max_bytes + 1 - size))
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > self.policy.artifact_max_bytes:
                        raise AcquisitionError("artifact exceeds the configured byte limit")
                    digest.update(chunk)
                    output.write(chunk)
                output.flush()
                os.fsync(output.fileno())
                final_url = self.policy.validate_url(response.geturl())
                media_type = str(response.headers.get("Content-Type") or "application/octet-stream").split(";", 1)[0]
            actual = f"sha256:{digest.hexdigest()}"
            if expected_digest is not None and actual != _digest(expected_digest):
                raise AcquisitionError("downloaded artifact digest does not match registry metadata")
            if expected_size is not None and size != expected_size:
                raise AcquisitionError("downloaded artifact size does not match registry metadata")
            os.replace(temporary, destination)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
        return DownloadedArtifact(destination, final_url, actual, size, media_type)

    def _open(
        self,
        url: str,
        *,
        headers: Mapping[str, str] | None,
        accept: str,
    ):
        self.policy.validate_url(url)
        request_headers = {
            "Accept": accept,
            "User-Agent": self.policy.user_agent,
        }
        for key, value in (headers or {}).items():
            if key.casefold() not in {"authorization", "if-none-match"}:
                raise AcquisitionError(f"acquisition header is not allowed: {key}")
            if "\r" in value or "\n" in value:
                raise AcquisitionError("acquisition header contains a newline")
            request_headers[key] = value
        request = urllib.request.Request(url, headers=request_headers, method="GET")
        try:
            response = self._opener.open(request, timeout=self.policy.timeout_seconds)
        except urllib.error.HTTPError as exc:
            if exc.code == 429 or 500 <= exc.code <= 599:
                raise RetryableAcquisitionError(f"remote acquisition returned HTTP {exc.code}") from exc
            raise AcquisitionError(f"remote acquisition returned HTTP {exc.code}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise RetryableAcquisitionError("remote acquisition transport failed") from exc
        self.policy.validate_url(response.geturl())
        return response


@dataclass(frozen=True, slots=True)
class AcquisitionReceipt(RecordMixin):
    identity: IdentityRecord
    format_version: str
    source_kind: str
    requested_subject: str
    request_uri: str
    resolved_uri: str
    artifact_digest: str
    artifact_size_bytes: int
    media_type: str
    acquired_at: str
    policy_digest: str
    metadata: Mapping[str, Any]

    @classmethod
    def create(
        cls,
        *,
        source_kind: str,
        requested_subject: str,
        request_uri: str,
        resolved_uri: str,
        artifact_digest: str,
        artifact_size_bytes: int,
        media_type: str,
        acquired_at: str,
        policy_digest: str,
        metadata: Mapping[str, Any],
    ) -> "AcquisitionReceipt":
        if not all(
            (
                source_kind,
                requested_subject,
                request_uri,
                resolved_uri,
                artifact_digest,
                media_type,
                acquired_at,
                policy_digest,
            )
        ):
            raise AcquisitionError("acquisition receipt fields are required")
        _digest(artifact_digest)
        _digest(policy_digest)
        if artifact_size_bytes < 0:
            raise AcquisitionError("artifact size cannot be negative")
        primitive = to_primitive(dict(metadata))
        if not isinstance(primitive, dict):
            raise AcquisitionError("acquisition metadata must be an object")
        key = {
            "format_version": "1.0.0",
            "source_kind": source_kind,
            "requested_subject": requested_subject,
            "request_uri": _public_uri(request_uri),
            "resolved_uri": _public_uri(resolved_uri),
            "artifact_digest": _digest(artifact_digest),
            "artifact_size_bytes": artifact_size_bytes,
            "media_type": media_type,
            "acquired_at": acquired_at,
            "policy_digest": _digest(policy_digest),
            "metadata": primitive,
        }
        return cls(
            IdentityRecord.create("acquisition_receipt", key),
            "1.0.0",
            source_kind,
            requested_subject,
            key["request_uri"],
            key["resolved_uri"],
            key["artifact_digest"],
            artifact_size_bytes,
            media_type,
            acquired_at,
            key["policy_digest"],
            primitive,
        )


class PyPIAcquirer:
    def __init__(
        self,
        transport: AcquisitionTransport,
        policy: NetworkAcquisitionPolicy | None = None,
    ):
        self.transport = transport
        self.policy = policy or NetworkAcquisitionPolicy()

    def acquire_wheel(
        self,
        package: str,
        version: str,
        destination: Path,
        *,
        acquired_at: str,
        filename: str | None = None,
        allow_yanked: bool = False,
    ) -> tuple[DownloadedArtifact, AcquisitionReceipt]:
        normalized = normalize_project_name(package)
        _version(version)
        endpoint = f"https://pypi.org/pypi/{quote(package, safe='')}/{quote(version, safe='')}/json"
        metadata = self.transport.get_json(endpoint)
        self.policy.validate_url(metadata.final_url)
        info = metadata.value.get("info")
        urls = metadata.value.get("urls")
        if not isinstance(info, Mapping) or not isinstance(urls, list):
            raise AcquisitionError("PyPI response lacks info or release files")
        if normalize_project_name(str(info.get("name", ""))) != normalized:
            raise AcquisitionError("PyPI metadata project does not match the request")
        if str(info.get("version", "")) != version:
            raise AcquisitionError("PyPI metadata version does not match the request")
        wheels: list[Mapping[str, Any]] = []
        for item in urls:
            if not isinstance(item, Mapping) or item.get("packagetype") != "bdist_wheel":
                continue
            candidate_name = str(item.get("filename", ""))
            if filename is not None and candidate_name != filename:
                continue
            if not allow_yanked and bool(item.get("yanked")):
                continue
            if _safe_filename(candidate_name, suffix=".whl"):
                wheels.append(item)
        if not wheels:
            raise AcquisitionError("PyPI release has no acceptable wheel artifact")
        selected = min(
            wheels,
            key=lambda item: (
                0 if str(item["filename"]).endswith("py3-none-any.whl") else 1,
                str(item["filename"]),
            ),
        )
        selected_name = str(selected["filename"])
        selected_url = str(selected.get("url", ""))
        self.policy.validate_url(selected_url)
        digests = selected.get("digests")
        if not isinstance(digests, Mapping) or not _SHA256_HEX.fullmatch(
            str(digests.get("sha256", ""))
        ):
            raise AcquisitionError("PyPI wheel lacks a valid SHA-256 digest")
        expected_size = selected.get("size")
        if not isinstance(expected_size, int) or expected_size <= 0:
            raise AcquisitionError("PyPI wheel lacks a valid declared size")
        artifact = self.transport.download(
            selected_url,
            destination / selected_name,
            expected_digest=str(digests["sha256"]),
            expected_size=expected_size,
        )
        self.policy.validate_url(artifact.final_url)
        receipt = AcquisitionReceipt.create(
            source_kind="pypi_wheel",
            requested_subject=f"{normalized}=={version}",
            request_uri=endpoint,
            resolved_uri=artifact.final_url,
            artifact_digest=artifact.content_digest,
            artifact_size_bytes=artifact.size_bytes,
            media_type=artifact.media_type,
            acquired_at=acquired_at,
            policy_digest=self.policy.digest,
            metadata={
                "package": normalized,
                "version": version,
                "filename": selected_name,
                "pypi_metadata_digest": metadata.content_digest,
                "pypi_metadata_size_bytes": metadata.size_bytes,
                "registry_sha256_verified": True,
                "registry_size_verified": True,
                "yanked": bool(selected.get("yanked")),
            },
        )
        return artifact, receipt


class GitHubArchiveAcquirer:
    def __init__(
        self,
        transport: AcquisitionTransport,
        policy: NetworkAcquisitionPolicy | None = None,
        *,
        token: str | None = None,
    ):
        self.transport = transport
        self.policy = policy or NetworkAcquisitionPolicy()
        self.token = token

    def acquire_commit(
        self,
        repository: str,
        commit_sha: str,
        destination: Path,
        *,
        acquired_at: str,
    ) -> tuple[DownloadedArtifact, AcquisitionReceipt]:
        if not _REPOSITORY.fullmatch(repository):
            raise AcquisitionError("GitHub repository must use owner/name syntax")
        if not _COMMIT.fullmatch(commit_sha):
            raise AcquisitionError("GitHub acquisition requires an immutable 40-hex commit SHA")
        normalized_commit = commit_sha.casefold()
        api_url = f"https://api.github.com/repos/{repository}/git/commits/{normalized_commit}"
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else None
        metadata = self.transport.get_json(api_url, headers=headers)
        self.policy.validate_url(metadata.final_url)
        resolved_commit = str(metadata.value.get("sha", "")).casefold()
        tree = metadata.value.get("tree")
        tree_sha = str(tree.get("sha", "")).casefold() if isinstance(tree, Mapping) else ""
        if resolved_commit != normalized_commit or not _COMMIT.fullmatch(tree_sha):
            raise AcquisitionError("GitHub did not resolve the requested immutable commit")
        archive_url = f"https://codeload.github.com/{repository}/zip/{resolved_commit}"
        archive_name = f"{repository.replace('/', '-')}-{resolved_commit}.zip"
        artifact = self.transport.download(
            archive_url,
            destination / archive_name,
            # The API credential is deliberately not forwarded to codeload. This
            # adapter supports public archives; private-repository acquisition gets a
            # separate scoped transport rather than broadening credential exposure.
            headers=None,
        )
        self.policy.validate_url(artifact.final_url)
        receipt = AcquisitionReceipt.create(
            source_kind="github_commit_archive",
            requested_subject=f"{repository}@{resolved_commit}",
            request_uri=api_url,
            resolved_uri=artifact.final_url,
            artifact_digest=artifact.content_digest,
            artifact_size_bytes=artifact.size_bytes,
            media_type=artifact.media_type,
            acquired_at=acquired_at,
            policy_digest=self.policy.digest,
            metadata={
                "repository": repository,
                "commit_sha": resolved_commit,
                "tree_sha": tree_sha,
                "github_metadata_digest": metadata.content_digest,
                "github_metadata_size_bytes": metadata.size_bytes,
                "commit_api_verified": True,
            },
        )
        return artifact, receipt

    def extract_commit_archive(self, artifact: Path, destination: Path) -> Path:
        return extract_github_archive(artifact, destination, policy=self.policy)


def extract_github_archive(
    artifact: Path,
    destination: Path,
    *,
    policy: NetworkAcquisitionPolicy | None = None,
) -> Path:
    """Safely extract one GitHub zip archive and strip its single root directory."""

    effective = policy or NetworkAcquisitionPolicy()
    archive = artifact.resolve(strict=True)
    if destination.exists():
        if not destination.is_dir() or any(destination.iterdir()):
            raise AcquisitionError("GitHub extraction destination must be absent or empty")
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
    stage = destination.with_name(f".{destination.name}.extracting-{uuid.uuid4().hex}")
    stage.mkdir()
    try:
        with zipfile.ZipFile(archive) as handle:
            infos = handle.infolist()
            if not infos or len(infos) > effective.max_archive_members:
                raise AcquisitionError("GitHub archive has an invalid member count")
            total = 0
            roots: set[str] = set()
            prepared: list[tuple[zipfile.ZipInfo, PurePosixPath]] = []
            for info in infos:
                member = _safe_archive_member(info.filename)
                roots.add(member.parts[0])
                if _zip_symlink(info):
                    raise AcquisitionError(f"GitHub archive symlink is refused: {info.filename}")
                if info.file_size > effective.max_archive_member_bytes:
                    raise AcquisitionError("GitHub archive member exceeds the configured byte limit")
                total += info.file_size
                if total > effective.max_archive_uncompressed_bytes:
                    raise AcquisitionError("GitHub archive exceeds the uncompressed byte limit")
                if len(member.parts) > 1:
                    prepared.append((info, PurePosixPath(*member.parts[1:])))
            if len(roots) != 1:
                raise AcquisitionError("GitHub archive must have exactly one top-level directory")
            for info, relative in prepared:
                output = stage.joinpath(*relative.parts)
                if info.is_dir():
                    output.mkdir(parents=True, exist_ok=True)
                    continue
                output.parent.mkdir(parents=True, exist_ok=True)
                with handle.open(info) as source, output.open("xb") as target:
                    copied = shutil.copyfileobj(source, target, length=1024 * 1024)
                    del copied
            if not any(path.is_file() for path in stage.rglob("*")):
                raise AcquisitionError("GitHub archive contains no regular files")
        if destination.exists():
            destination.rmdir()
        os.replace(stage, destination)
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    return destination


def attach_acquisition_receipt(
    bundle: GraphBundle,
    receipt: AcquisitionReceipt,
    artifact: Path,
) -> None:
    """Attach acquisition provenance and the immutable archive to a graph snapshot."""

    content = artifact.read_bytes()
    if sha256_digest(content) != receipt.artifact_digest or len(content) != receipt.artifact_size_bytes:
        raise AcquisitionError("acquired artifact changed before graph publication")
    bundle.source_blobs[receipt.artifact_digest] = content
    producer = ProducerRef("taedri.network-acquisition", "0.1.0", receipt.policy_digest)
    evidence = EvidenceRecord.create(
        snapshot_id=bundle.snapshot.identity.id,
        evidence_type_key=f"uceg.evidence.acquisition.{receipt.source_kind}",
        uri=receipt.resolved_uri,
        content_digest=receipt.artifact_digest,
        producer=producer,
    )
    bundle.evidence[evidence.identity.id] = evidence
    subject = SubjectRef("snapshot", bundle.snapshot.identity.id)
    input_ref = SubjectRef("evidence", evidence.identity.id)
    seeds = [
        RepresentationSeed(
            subject,
            "uceg.family.artifact",
            "uceg.artifact.source_uri",
            TypedValue(ValueKind.TEXT, receipt.resolved_uri),
            (evidence.identity.id,),
            input_ref,
        ),
        RepresentationSeed(
            subject,
            "uceg.family.artifact",
            "uceg.artifact.acquisition_receipt",
            TypedValue(ValueKind.JSON, receipt.to_dict()),
            (evidence.identity.id,),
            input_ref,
        ),
    ]
    if receipt.source_kind == "pypi_wheel":
        seeds.append(
            RepresentationSeed(
                subject,
                "uceg.family.artifact",
                "uceg.artifact.pypi.metadata_digest",
                TypedValue(ValueKind.DIGEST, str(receipt.metadata["pypi_metadata_digest"])),
                (evidence.identity.id,),
                input_ref,
            )
        )
    if receipt.source_kind == "github_commit_archive":
        for key, representation in (
            ("repository", "uceg.artifact.git.repository"),
            ("commit_sha", "uceg.artifact.git.commit"),
            ("tree_sha", "uceg.artifact.git.tree"),
        ):
            seeds.append(
                RepresentationSeed(
                    subject,
                    "uceg.family.artifact",
                    representation,
                    TypedValue(ValueKind.KEYWORD, str(receipt.metadata[key])),
                    (evidence.identity.id,),
                    input_ref,
                )
            )
    materialize_seeds(
        bundle,
        seeds,
        producer=producer,
        attempt_key=f"acquisition:{receipt.identity.id}",
        environment={"network_allowed": True, "execution_allowed": False},
    )


def normalize_project_name(value: str) -> str:
    if not _PROJECT.fullmatch(value):
        raise AcquisitionError("invalid PyPI project name")
    return re.sub(r"[-_.]+", "-", value).casefold()


def _version(value: str) -> str:
    if not value or len(value) > 128 or value.strip() != value or any(
        character in value for character in "/\\\x00"
    ):
        raise AcquisitionError("invalid immutable package version")
    return value


def _safe_filename(value: str, *, suffix: str) -> bool:
    path = PurePosixPath(value)
    return bool(
        value
        and len(value) <= 255
        and path.name == value
        and "\\" not in value
        and "\x00" not in value
        and value.endswith(suffix)
    )


def _safe_archive_member(value: str) -> PurePosixPath:
    if not value or "\\" in value or "\x00" in value:
        raise AcquisitionError(f"unsafe archive member: {value!r}")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise AcquisitionError(f"unsafe archive member: {value!r}")
    return path


def _zip_symlink(info: zipfile.ZipInfo) -> bool:
    return stat.S_IFMT(info.external_attr >> 16) == stat.S_IFLNK


def _digest(value: str) -> str:
    normalized = value.casefold()
    if _SHA256_HEX.fullmatch(normalized):
        normalized = f"sha256:{normalized}"
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", normalized):
        raise AcquisitionError("expected a SHA-256 digest")
    return normalized


def _public_uri(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.username is not None or parsed.password is not None:
        raise AcquisitionError("receipt URI cannot contain credentials")
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, parsed.query, ""))


def _content_length(headers: Mapping[str, Any]) -> int | None:
    value = headers.get("Content-Length")
    if value is None:
        return None
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise AcquisitionError("remote Content-Length is invalid") from exc
    if result < 0:
        raise AcquisitionError("remote Content-Length is invalid")
    return result
