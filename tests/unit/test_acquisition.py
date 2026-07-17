from __future__ import annotations

import base64
import hashlib
import io
import tempfile
import unittest
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Mapping

from taedri_codegraph.acquisition import (
    AcquisitionError,
    DownloadedArtifact,
    GitHubArchiveAcquirer,
    HTTPDocument,
    NetworkAcquisitionPolicy,
    PyPIAcquirer,
    _AllowlistedRedirectHandler,
    attach_acquisition_receipt,
    extract_github_archive,
)
from taedri_codegraph.analyzers import PythonSyntaxAnalyzer
from taedri_codegraph.artifacts import analyze_wheel
from taedri_codegraph.canonical import canonical_json_bytes, sha256_digest
from taedri_codegraph.representations import core_representation_registry


COMMIT = "a" * 40
TREE = "b" * 40


def _record_hash(content: bytes) -> str:
    digest = hashlib.sha256(content).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def valid_wheel_bytes() -> bytes:
    source = (
        b"from pathlib import Path\n"
        b"def normalize(value: str) -> str:\n"
        b"    Path('must-not-exist').write_text('executed')\n"
        b"    return value.strip().lower()\n"
    )
    metadata = b"Metadata-Version: 2.4\nName: demo-pkg\nVersion: 1.0\nLicense-Expression: MIT\n"
    record_path = "demo_pkg-1.0.dist-info/RECORD"
    record = (
        f"demo_pkg.py,sha256={_record_hash(source)},{len(source)}\n"
        f"demo_pkg-1.0.dist-info/METADATA,sha256={_record_hash(metadata)},{len(metadata)}\n"
        f"{record_path},,\n"
    ).encode("utf-8")
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("demo_pkg.py", source)
        archive.writestr("demo_pkg-1.0.dist-info/METADATA", metadata)
        archive.writestr(record_path, record)
    return output.getvalue()


def github_archive_bytes(*, poison: bool = False) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        name = "../escape.py" if poison else "demo-repo/main.py"
        archive.writestr(name, "def parse(value: str) -> str:\n    return value.strip()\n")
    return output.getvalue()


class FakeTransport:
    def __init__(self, wheel: bytes, github: bytes):
        self.wheel = wheel
        self.github = github
        self.requests: list[tuple[str, Mapping[str, str] | None]] = []

    def get_json(self, url: str, *, headers=None) -> HTTPDocument:
        self.requests.append((url, headers))
        if "pypi.org" in url:
            digest = hashlib.sha256(self.wheel).hexdigest()
            value: dict[str, Any] = {
                "info": {"name": "demo-pkg", "version": "1.0"},
                "urls": [
                    {
                        "packagetype": "bdist_wheel",
                        "filename": "demo_pkg-1.0-py3-none-any.whl",
                        "url": "https://files.pythonhosted.org/packages/demo_pkg-1.0-py3-none-any.whl",
                        "digests": {"sha256": digest},
                        "size": len(self.wheel),
                        "yanked": False,
                    }
                ],
            }
        else:
            value = {"sha": COMMIT, "tree": {"sha": TREE}}
        content = canonical_json_bytes(value)
        return HTTPDocument(value, url, sha256_digest(content), len(content))

    def download(
        self,
        url: str,
        destination: Path,
        *,
        headers=None,
        expected_digest: str | None = None,
        expected_size: int | None = None,
    ) -> DownloadedArtifact:
        self.requests.append((url, headers))
        content = self.wheel if "pythonhosted" in url else self.github
        digest = sha256_digest(content)
        if expected_digest is not None:
            expected = expected_digest if expected_digest.startswith("sha256:") else f"sha256:{expected_digest}"
            if digest != expected:
                raise AcquisitionError("fixture digest mismatch")
        if expected_size is not None and len(content) != expected_size:
            raise AcquisitionError("fixture size mismatch")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        return DownloadedArtifact(
            destination,
            url,
            digest,
            len(content),
            "application/zip",
        )


class AcquisitionTests(unittest.TestCase):
    def test_url_policy_is_exact_host_https_only(self) -> None:
        policy = NetworkAcquisitionPolicy()
        self.assertEqual(policy.validate_url("https://pypi.org/pypi/demo/json"), "https://pypi.org/pypi/demo/json")
        for value in (
            "http://pypi.org/pypi/demo/json",
            "https://pypi.org.evil.example/pypi/demo/json",
            "https://user:secret@pypi.org/pypi/demo/json",
            "https://pypi.org:444/pypi/demo/json",
        ):
            with self.subTest(value=value), self.assertRaises(AcquisitionError):
                policy.validate_url(value)

    def test_authenticated_acquisition_request_never_follows_redirect(self) -> None:
        handler = _AllowlistedRedirectHandler(NetworkAcquisitionPolicy())
        authenticated = urllib.request.Request(
            "https://api.github.com/repos/owner/repo",
            headers={"Authorization": "Bearer fixture-secret"},
        )
        self.assertIsNone(
            handler.redirect_request(
                authenticated,
                None,
                302,
                "Found",
                {},
                "https://codeload.github.com/owner/repo/zip/commit",
            )
        )

        unauthenticated = urllib.request.Request(
            "https://pypi.org/pypi/demo/json"
        )
        redirected = handler.redirect_request(
            unauthenticated,
            None,
            302,
            "Found",
            {},
            "https://files.pythonhosted.org/packages/demo.whl",
        )
        self.assertIsNotNone(redirected)
        assert redirected is not None
        self.assertFalse(redirected.has_header("Authorization"))

    def test_real_wheel_bytes_are_acquired_verified_and_never_executed(self) -> None:
        wheel = valid_wheel_bytes()
        transport = FakeTransport(wheel, github_archive_bytes())
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact, receipt = PyPIAcquirer(transport).acquire_wheel(
                "Demo_Pkg", "1.0", root, acquired_at="2026-07-16T12:00:00Z"
            )
            bundle, inspection = analyze_wheel(artifact.path)
            attach_acquisition_receipt(bundle, receipt, artifact.path)
            bundle.validate(
                PythonSyntaxAnalyzer().registry.resolve,
                core_representation_registry().resolve,
            )
            self.assertEqual(inspection.distribution_name, "demo-pkg")
            self.assertFalse((root / "must-not-exist").exists())
            keys = {
                content.representation_key
                for content in bundle.representation_contents.values()
            }
            self.assertIn("uceg.artifact.acquisition_receipt", keys)
            self.assertIn(receipt.artifact_digest, bundle.source_blobs)

    def test_github_requires_a_commit_and_safe_archive_then_retains_lineage(self) -> None:
        transport = FakeTransport(valid_wheel_bytes(), github_archive_bytes())
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            acquirer = GitHubArchiveAcquirer(transport, token="fixture-token")
            artifact, receipt = acquirer.acquire_commit(
                "owner/demo", COMMIT, root / "artifacts", acquired_at="2026-07-16T12:00:00Z"
            )
            source = acquirer.extract_commit_archive(artifact.path, root / "source")
            bundle = PythonSyntaxAnalyzer().analyze(
                source,
                package_name="demo",
                release=COMMIT,
                source_kind="github_commit_archive",
                source_uri=f"github:owner/demo@{COMMIT}",
            )
            attach_acquisition_receipt(bundle, receipt, artifact.path)
            bundle.validate(
                PythonSyntaxAnalyzer().registry.resolve,
                core_representation_registry().resolve,
            )
            self.assertEqual(receipt.metadata["tree_sha"], TREE)
            self.assertNotIn("fixture-token", canonical_json_bytes(receipt).decode("utf-8"))
            keys = {
                content.representation_key
                for content in bundle.representation_contents.values()
            }
            self.assertIn("uceg.artifact.git.commit", keys)
            self.assertTrue((source / "main.py").is_file())

    def test_github_archive_traversal_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "poison.zip"
            archive.write_bytes(github_archive_bytes(poison=True))
            with self.assertRaisesRegex(AcquisitionError, "unsafe archive member"):
                extract_github_archive(archive, root / "source")


if __name__ == "__main__":
    unittest.main()
