from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from taedri_codegraph.cli import build_parser
from taedri_codegraph.production_server import (
    ProductionServerError,
    gunicorn_options,
    run_production_server,
)


class ProductionServerTests(unittest.TestCase):
    def test_gunicorn_contract_is_bounded_and_recycles_workers(self) -> None:
        options = gunicorn_options(
            host="0.0.0.0",
            port=8000,
            workers=3,
            threads=8,
            timeout_seconds=120,
        )
        self.assertEqual(options["bind"], "0.0.0.0:8000")
        self.assertEqual(options["worker_class"], "gthread")
        self.assertEqual(options["max_requests"], 10_000)
        self.assertGreater(options["max_requests_jitter"], 0)
        self.assertTrue(options["control_socket_disable"])
        with self.assertRaises(ValueError):
            gunicorn_options(
                host="0.0.0.0",
                port=8000,
                workers=0,
                threads=8,
                timeout_seconds=120,
            )

    def test_cli_production_settings_are_explicit(self) -> None:
        args = build_parser().parse_args(
            [
                "serve",
                "--production",
                "--workers",
                "3",
                "--threads",
                "7",
                "--timeout-seconds",
                "90",
            ]
        )
        self.assertTrue(args.production)
        self.assertEqual((args.workers, args.threads, args.timeout_seconds), (3, 7, 90))

    def test_missing_optional_dependency_has_an_actionable_failure(self) -> None:
        try:
            import gunicorn  # noqa: F401
        except ImportError:
            with tempfile.TemporaryDirectory() as temporary:
                with self.assertRaisesRegex(ProductionServerError, r"\[server\]"):
                    run_production_server(
                        control_db=Path(temporary) / "control.sqlite",
                        host="127.0.0.1",
                        port=8000,
                    )


if __name__ == "__main__":
    unittest.main()
