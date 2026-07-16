"""Gunicorn process manager boundary for hosted WSGI deployments."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from .http_api import ApiConfig, TaedriAPI


class ProductionServerError(RuntimeError):
    """Raised when the optional production server dependency is unavailable."""


def gunicorn_options(
    *,
    host: str,
    port: int,
    workers: int,
    threads: int,
    timeout_seconds: int,
) -> dict[str, Any]:
    if not host or not 1 <= port <= 65_535:
        raise ValueError("production bind host and port are invalid")
    if not 1 <= workers <= 64 or not 1 <= threads <= 256:
        raise ValueError("production workers must be 1..64 and threads 1..256")
    if not 5 <= timeout_seconds <= 3600:
        raise ValueError("production timeout must be between 5 and 3600 seconds")
    return {
        "bind": f"{host}:{port}",
        "workers": workers,
        "threads": threads,
        "worker_class": "gthread",
        "timeout": timeout_seconds,
        "graceful_timeout": min(timeout_seconds, 30),
        "keepalive": 5,
        "max_requests": 10_000,
        "max_requests_jitter": 1_000,
        "accesslog": "-",
        "errorlog": "-",
        "capture_output": False,
        # Gunicorn 26 enables a local control socket by default. Hosted containers
        # are read-only and managed by their orchestrator, so no writable control
        # socket or second administrative plane is exposed.
        "control_socket_disable": True,
    }


def run_production_server(
    *,
    control_db: str | Path,
    host: str,
    port: int,
    cors_origins: Iterable[str] = (),
    workers: int = 2,
    threads: int = 4,
    timeout_seconds: int = 120,
    api_request_limit_per_minute: int = 600,
) -> None:
    """Run Taedri under Gunicorn; import remains optional for local library users."""

    try:
        from gunicorn.app.base import BaseApplication
    except ImportError as exc:  # pragma: no cover - optional deployment dependency
        raise ProductionServerError(
            "install taedri-codegraph[server] to use --production"
        ) from exc

    application = TaedriAPI(
        ApiConfig(
            control_db=Path(control_db),
            cors_origins=tuple(sorted(set(cors_origins))),
            api_request_limit_per_minute=api_request_limit_per_minute,
        )
    )
    options = gunicorn_options(
        host=host,
        port=port,
        workers=workers,
        threads=threads,
        timeout_seconds=timeout_seconds,
    )

    class TaedriGunicornApplication(BaseApplication):  # type: ignore[misc]
        def load_config(self) -> None:
            for key, value in options.items():
                if key in self.cfg.settings and value is not None:
                    self.cfg.set(key.lower(), value)

        def load(self) -> TaedriAPI:
            return application

    TaedriGunicornApplication().run()
