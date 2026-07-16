from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from taedri_codegraph.cli import main
from taedri_codegraph.primitive_repository import SQLitePrimitiveRepository
from taedri_codegraph.saas import SQLiteControlPlane, Tenant
from tests.primitive_fixtures import copy_runtime_native_primitive


ROOT = Path(__file__).resolve().parents[2]


class PrimitiveCLIIntegrationTests(unittest.TestCase):
    def test_validate_is_complete_and_does_not_execute_code(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            result = main(
                [
                    "primitive",
                    "validate",
                    str(ROOT / "examples/primitives/casefold-text"),
                ]
            )
        self.assertEqual(result, 0)
        record = json.loads(output.getvalue())
        self.assertEqual(record["status"], "release-grade")
        self.assertFalse(record["code_executed"])
        self.assertEqual(record["required_role_count"], 12)
        self.assertEqual(record["artifacts"]["interface_edge_count"], 6)

    def test_release_local_processes_exactly_one_complete_primitive(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            temporary_path = Path(temporary)
            primitive_path = copy_runtime_native_primitive(
                ROOT / "examples/primitives/casefold-text",
                temporary_path / "casefold-text",
            )
            control_path = temporary_path / "control.sqlite"
            control = SQLiteControlPlane(control_path)
            tenant = control.create_tenant(
                Tenant.create(
                    slug="primitive-cli",
                    display_name="Primitive CLI",
                    created_at="2026-07-16T23:20:00Z",
                )
            )
            output = io.StringIO()
            with redirect_stdout(output):
                result = main(
                    [
                        "primitive",
                        "release-local",
                        str(primitive_path),
                        "--control",
                        str(control_path),
                        "--tenant",
                        "primitive-cli",
                        "--authorizer-id",
                        "taedri.release-manager.cli-test-v1",
                        "--allow-trusted-code-execution",
                    ]
                )
            self.assertEqual(result, 0)
            record = json.loads(output.getvalue())
            self.assertEqual(record["status"], "released")
            self.assertEqual(record["executed_case_count"], 6)
            self.assertEqual(record["search_result_count"], 1)
            self.assertEqual(record["interface_edges"], 6)
            repository = SQLitePrimitiveRepository(SQLiteControlPlane(control_path))
            self.assertEqual(len(repository.list(tenant.identity.id)), 1)


if __name__ == "__main__":
    unittest.main()
