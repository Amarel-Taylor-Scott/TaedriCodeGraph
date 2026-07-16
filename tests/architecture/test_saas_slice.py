from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class SaaSVerticalSliceArchitectureTests(unittest.TestCase):
    def test_saas_schemas_are_versioned_and_do_not_persist_plaintext_keys(self) -> None:
        for name in (
            "tenant.v1.schema.json",
            "job-submission.v1.schema.json",
            "primitive-stage.v1.schema.json",
            "usage-limit-revision.v1.schema.json",
            "usage-receipt.v1.schema.json",
            "mechanism-waterfall-run.v1.schema.json",
            "pipeline-definition.v1.schema.json",
            "search-trigger-signal.v1.schema.json",
            "subscription-revision.v1.schema.json",
        ):
            schema = json.loads((ROOT / "schemas" / name).read_text("utf-8"))
            self.assertEqual(
                schema["$schema"], "https://json-schema.org/draft/2020-12/schema"
            )
            self.assertIn("v1.schema.json", schema["$id"])
        combined = "\n".join(
            path.read_text("utf-8")
            for path in (
                ROOT / "schemas" / "tenant.v1.schema.json",
                ROOT / "deploy" / "postgres" / "001_control_plane.sql",
            )
        ).lower()
        self.assertNotIn("plaintext_token", combined)
        self.assertIn("verifier", combined)

    def test_postgres_contract_covers_tenants_audit_payloads_and_worker_leases(self) -> None:
        migration = (ROOT / "deploy" / "postgres" / "001_control_plane.sql").read_text(
            "utf-8"
        )
        for table in (
            "tenant",
            "api_key",
            "graph_mount",
            "audit_event",
            "job_payload",
            "worker_job",
            "worker_lease",
            "worker_event",
            "primitive_handle",
            "primitive_blob",
            "primitive_tree",
            "primitive_revision",
            "primitive_ref",
            "primitive_ref_update",
            "primitive_release",
            "primitive_release_revocation",
            "candidate_submission",
            "candidate_state_event",
            "prompt_session",
            "prompt_session_event",
            "usage_limit_revision",
            "usage_event",
        ):
            self.assertIn(f"taedri.{table}", migration)
        self.assertIn("FOR UPDATE SKIP LOCKED", migration)

        ledger = (
            ROOT / "deploy" / "postgres" / "002_representation_ledger.sql"
        ).read_text("utf-8")
        for table in (
            "graph_subject",
            "descriptor_definition",
            "representation_content",
            "generation_run",
            "representation_assertion",
            "evidence_link",
            "lineage_assertion",
            "relation_assertion",
            "representation_combination",
            "preferred_view_revision",
            "projection_epoch",
            "lexical_projection",
            "scalar_projection",
            "blocking_projection",
            "embedding_projection",
            "graph_projection",
        ):
            self.assertIn(f"taedri.{table}", ledger)
        self.assertIn("serving projections are never authoritative", ledger.lower())

    def test_container_manifests_drop_privileges_and_commit_no_credentials(self) -> None:
        backend = (ROOT / "Dockerfile").read_text("utf-8")
        frontend = (ROOT / "apps" / "explorer" / "Dockerfile").read_text("utf-8")
        portal = (ROOT / "apps" / "portal" / "Dockerfile").read_text("utf-8")
        compose = (ROOT / "compose.yaml").read_text("utf-8")
        for dockerfile in (backend, frontend):
            self.assertRegex(dockerfile, r"(?m)^USER 10001(?::10001)?$")
        self.assertRegex(portal, r"(?m)^USER 10002(?::10002)?$")
        self.assertIn("cap_drop: [ALL]", compose)
        self.assertIn("no-new-privileges:true", compose)
        self.assertNotRegex(
            "\n".join((backend, frontend, portal, compose)),
            r"tcg_[a-f0-9]{24}_[A-Za-z0-9_-]{32,}",
        )

    def test_fly_volume_manifest_is_explicitly_single_machine_poc(self) -> None:
        manifest = (
            ROOT / "deploy" / "fly" / "single-node-poc.fly.toml"
        ).read_text("utf-8")
        guide = (ROOT / "deploy" / "fly" / "README.md").read_text("utf-8")
        self.assertIn("single-Machine proof", manifest)
        self.assertIn('auto_stop_machines = "off"', manifest)
        self.assertNotRegex(manifest, r"(?m)^app\s*=")
        self.assertIn("PostgreSQL", guide)
        self.assertIn("S3/Tigris", guide)

    def test_live_explorer_is_self_contained_and_calls_authenticated_api(self) -> None:
        page = (ROOT / "apps" / "explorer" / "index.html").read_text("utf-8")
        self.assertIn("/v1/search", page)
        self.assertIn("/v1/jobs", page)
        self.assertIn("/v1/candidates", page)
        self.assertIn("/v1/usage", page)
        self.assertIn("/v1/metrics", page)
        self.assertIn("/v1/limits", page)
        self.assertIn("/cancel", page)
        self.assertIn("generate_primitive_candidates", page)
        self.assertIn('type="password"', page)
        self.assertNotIn("localStorage", page)
        self.assertIsNone(re.search(r'<(?:script|link)[^>]+(?:src|href)="https?://', page))

    def test_public_portal_uses_live_plan_and_entitlement_contracts(self) -> None:
        page = (ROOT / "apps" / "portal" / "index.html").read_text("utf-8")
        self.assertIn("/v1/public/plans", page)
        self.assertIn("/v1/portal/subscription", page)
        self.assertIn("/v1/portal/checkout", page)
        self.assertIn("/v1/portal/billing-session", page)
        self.assertIn('type="password"', page)
        self.assertIn("No invented pricing", page)
        self.assertNotIn("localStorage", page)
        self.assertIsNone(re.search(r'<(?:script|link)[^>]+(?:src|href)="https?://', page))

    def test_ci_runs_tests_postgres_ddl_and_container_builds_without_write_token(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text("utf-8")
        self.assertIn("python -m unittest discover -s tests -v", workflow)
        self.assertIn("python tools/smoke_production_server.py", workflow)
        self.assertIn("001_control_plane.sql", workflow)
        self.assertIn("002_representation_ledger.sql", workflow)
        self.assertIn("docker/build-push-action@v7", workflow)
        self.assertIn("permissions:\n  contents: read", workflow)
        self.assertIn("persist-credentials: false", workflow)
        pyproject = (ROOT / "pyproject.toml").read_text("utf-8")
        backend = (ROOT / "Dockerfile").read_text("utf-8")
        self.assertIn('server = ["gunicorn>=26,<27"]', pyproject)
        self.assertIn("--production", backend)


if __name__ == "__main__":
    unittest.main()
