from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

from taedri_codegraph.analyzers import PythonSyntaxAnalyzer
from taedri_codegraph.storage import GraphStore


MCP_AVAILABLE = importlib.util.find_spec("mcp") is not None


@unittest.skipUnless(MCP_AVAILABLE, "install taedri-codegraph[agents] for MCP protocol test")
class MCPProtocolIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        source = root / "source"
        source.mkdir()
        (source / "address.py").write_text(
            "def normalize_address(value: str) -> str:\n"
            "    return ' '.join(value.lower().split())\n",
            "utf-8",
        )
        analyzer = PythonSyntaxAnalyzer()
        bundle = analyzer.analyze(source, package_name="fixture", release="1.0")
        self.store = root / "graph"
        graph = GraphStore(self.store)
        epoch = graph.write_candidate(bundle, analyzer.registry)
        graph.publish_epoch(epoch)

    async def asyncTearDown(self) -> None:
        self.temporary.cleanup()

    async def test_stdio_initialize_list_and_search_tool_round_trip(self) -> None:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        parameters = StdioServerParameters(
            command=sys.executable,
            args=[
                "-m",
                "taedri_codegraph",
                "mcp",
                "--store",
                str(self.store),
            ],
        )
        async with stdio_client(parameters) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                initialized = await session.initialize()
                self.assertEqual(initialized.serverInfo.name, "Taedri CodeGraph")
                listed = await session.list_tools()
                names = {tool.name for tool in listed.tools}
                self.assertTrue(
                    {
                        "search_code",
                        "search_primitives",
                        "get_code_context",
                        "get_entity",
                        "get_neighbors",
                        "list_representations",
                        "find_structural_candidates",
                        "search_metadata",
                    }.issubset(names)
                )
                result = await session.call_tool(
                    "search_code", {"query": "normalize address", "limit": 5}
                )
                self.assertFalse(result.isError)
                self.assertIsInstance(result.structuredContent, dict)
                assert result.structuredContent is not None
                payload = result.structuredContent["result"]
                self.assertEqual(payload[0]["native_name"], "normalize_address")
                adaptive = await session.call_tool(
                    "search_primitives",
                    {
                        "query": "normalize address",
                        "strategy": "auto",
                        "limit": 5,
                        "minimum_candidates": 2,
                    },
                )
                self.assertFalse(adaptive.isError)
                assert adaptive.structuredContent is not None
                adaptive_payload = adaptive.structuredContent.get(
                    "result", adaptive.structuredContent
                )
                self.assertEqual(adaptive_payload["strategy"], "auto")
                self.assertEqual(
                    [item["stage"] for item in adaptive_payload["stages"]],
                    ["exact", "sparse", "semantic", "structural"],
                )


if __name__ == "__main__":
    unittest.main()
