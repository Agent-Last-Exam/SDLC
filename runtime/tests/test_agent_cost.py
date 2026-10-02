"""Spend accounting from Agent result events; no Agent, Docker or model calls."""

import json
from pathlib import Path
import tempfile
import unittest

from runtime.agent_cost import stream_cost


class StreamCostTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def stream(self, name, *events):
        path = self.root / name
        path.write_text("".join(json.dumps(event) + "\n" for event in events))
        return path

    def test_last_result_per_stream_is_totalled(self):
        # Claude Code reports a cumulative total per session; the last one wins.
        a = self.stream("a.jsonl",
                        {"type": "result", "total_cost_usd": 0.5},
                        {"type": "result", "total_cost_usd": 1.25})
        b = self.stream("b.jsonl", {"type": "result", "total_cost_usd": 2.0})
        self.assertEqual(stream_cost([a]), 1.25)
        self.assertEqual(stream_cost([a, b]), 3.25)

    def test_missing_or_silent_streams_are_unknown_not_zero(self):
        absent = self.root / "absent.jsonl"
        silent = self.stream("silent.jsonl", {"type": "assistant"})
        no_cost = self.stream("no-cost.jsonl", {"type": "result"})
        for paths in ([], [absent], [silent], [no_cost], [absent, silent]):
            with self.subTest(paths=paths):
                self.assertIsNone(stream_cost(paths))

    def test_malformed_lines_are_skipped(self):
        path = self.root / "mixed.jsonl"
        path.write_text(
            "not json\n"
            + json.dumps({"type": "result", "total_cost_usd": 0.75}) + "\n"
            + "{truncated\n"
        )
        self.assertEqual(stream_cost([path]), 0.75)

    def test_known_cost_survives_an_unknown_sibling(self):
        known = self.stream("known.jsonl", {"type": "result", "total_cost_usd": 1.5})
        self.assertEqual(stream_cost([known, self.root / "absent.jsonl"]), 1.5)


if __name__ == "__main__":
    unittest.main()
