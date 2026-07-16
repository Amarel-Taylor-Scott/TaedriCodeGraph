#!/usr/bin/env python3
"""Boot the optional production server and verify live health over a real socket."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


def available_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def fetch_json(url: str) -> dict[str, object]:
    with urlopen(url, timeout=1) as response:  # noqa: S310 - loopback smoke only
        value = json.load(response)
    if not isinstance(value, dict):
        raise RuntimeError("health endpoint did not return an object")
    return value


def main() -> int:
    port = available_port()
    with tempfile.TemporaryDirectory(prefix="taedri-production-smoke-") as temporary:
        control = Path(temporary) / "control.sqlite"
        command = [
            sys.executable,
            "-m",
            "taedri_codegraph",
            "serve",
            "--production",
            "--control",
            str(control),
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--workers",
            "1",
            "--threads",
            "2",
            "--timeout-seconds",
            "30",
        ]
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=dict(os.environ),
        )
        try:
            deadline = time.monotonic() + 15
            health: dict[str, object] | None = None
            while time.monotonic() < deadline and process.poll() is None:
                try:
                    health = fetch_json(f"http://127.0.0.1:{port}/healthz")
                    break
                except (URLError, TimeoutError, ConnectionError):
                    time.sleep(0.05)
            if health is None:
                process.terminate()
                output, _ = process.communicate(timeout=5)
                output = output[:16_384]
                raise RuntimeError("production server did not become healthy: " + output)
            ready = fetch_json(f"http://127.0.0.1:{port}/readyz")
            if health.get("status") != "ok" or ready.get("status") != "ready":
                raise RuntimeError("production health contract failed")
            print(
                json.dumps(
                    {
                        "format_version": "1.0.0",
                        "server": "gunicorn",
                        "health": health,
                        "ready": ready,
                        "socket_round_trip": True,
                    },
                    sort_keys=True,
                )
            )
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
