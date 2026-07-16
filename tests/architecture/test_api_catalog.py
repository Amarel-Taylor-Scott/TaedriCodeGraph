from __future__ import annotations

import unittest

from taedri_codegraph.api import build_openapi, route_catalog


class APICatalogTests(unittest.TestCase):
    def test_catalog_is_unique_and_openapi_is_generated_from_every_route(self) -> None:
        routes = route_catalog()
        keys = {(route.method, route.path) for route in routes}
        self.assertEqual(len(keys), len(routes))
        document = build_openapi()
        for route in routes:
            operation = document["paths"][route.path][route.method.lower()]
            self.assertEqual(operation["operationId"], route.operation_id)
            self.assertEqual(
                operation.get("x-taedri-required-scope"), route.required_scope
            )
        self.assertEqual(
            document["paths"]["/v1/public/plans"]["get"]["security"], []
        )
        self.assertEqual(
            document["paths"]["/v1/portal/subscription"]["get"][
                "x-taedri-required-scope"
            ],
            "billing:read",
        )


if __name__ == "__main__":
    unittest.main()
