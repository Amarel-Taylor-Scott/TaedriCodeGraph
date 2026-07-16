"""Generate OpenAPI from the route catalog instead of a second handwritten inventory."""

from __future__ import annotations

import re
from typing import Any

from .routes import route_catalog


def build_openapi() -> dict[str, Any]:
    paths: dict[str, dict[str, Any]] = {}
    for route in route_catalog():
        operation: dict[str, Any] = {
            "operationId": route.operation_id,
            "summary": route.summary,
            "tags": list(route.tags),
            "responses": {
                str(route.success_status): {"description": "Successful response"}
            },
        }
        if route.authenticated:
            operation["security"] = [{"bearerAuth": []}]
        else:
            operation["security"] = []
        if route.required_scope:
            operation["x-taedri-required-scope"] = route.required_scope
            operation["responses"].update(
                {
                    "401": {"description": "Authentication required"},
                    "403": {"description": "Required scope missing"},
                }
            )
        parameters = [
            {
                "name": name,
                "in": "path",
                "required": True,
                "schema": {"type": "string"},
            }
            for name in re.findall(r"\{([a-zA-Z0-9_]+)\}", route.path)
        ]
        if parameters:
            operation["parameters"] = parameters
        if route.request_schema:
            operation["requestBody"] = {
                "required": True,
                "content": {
                    "application/json": {
                        "schema": {
                            "$ref": "https://schemas.taedri.dev/codegraph/"
                            + route.request_schema
                        }
                    }
                },
            }
        paths.setdefault(route.path, {})[route.method.lower()] = operation
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "Taedri CodeGraph API",
            "version": "0.1.0-alpha",
            "description": (
                "Tenant-scoped retrieval, primitive registry, worker, session, usage, "
                "and provider-neutral SaaS portal API."
            ),
        },
        "paths": paths,
        "components": {
            "securitySchemes": {
                "bearerAuth": {"type": "http", "scheme": "bearer"}
            }
        },
    }
