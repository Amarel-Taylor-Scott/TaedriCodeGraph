from __future__ import annotations

import unittest

from taedri_codegraph.pagination import CursorError, decode_cursor, encode_cursor


class PaginationCursorTests(unittest.TestCase):
    def test_cursor_is_deterministic_tamper_evident_and_scope_bound(self) -> None:
        scope = {
            "route": "search",
            "query": "normalize address",
            "epoch": "uceg:v1:graph_epoch:fixture",
        }
        cursor = encode_cursor(scope, 20)
        self.assertEqual(cursor, encode_cursor(dict(reversed(tuple(scope.items()))), 20))
        self.assertEqual(decode_cursor(cursor, scope), 20)
        replacement = "A" if cursor[-1] != "A" else "B"
        with self.assertRaises(CursorError):
            decode_cursor(cursor[:-1] + replacement, scope)
        with self.assertRaisesRegex(CursorError, "does not belong"):
            decode_cursor(cursor, {**scope, "query": "different"})

    def test_cursor_depth_is_bounded(self) -> None:
        with self.assertRaises(CursorError):
            encode_cursor({"route": "search"}, 1001)


if __name__ == "__main__":
    unittest.main()
