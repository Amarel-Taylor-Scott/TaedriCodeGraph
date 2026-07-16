"""HTTP route catalog and generated API description."""

from .openapi import build_openapi
from .routes import RouteSpec, route_catalog

__all__ = ["RouteSpec", "build_openapi", "route_catalog"]
