import unittest

from runtime.request_usage import summarize


class UsageTests(unittest.TestCase):
    def test_stream_snapshots_are_merged_and_inclusive_native_prompt_is_preserved(self):
        rows = [
            {"kind": "request", "id": "one"},
            {"kind": "usage", "id": "one", "usage": {"input_tokens": 100, "cache_read_input_tokens": 50, "output_tokens": 1}},
            {"kind": "usage", "id": "one", "usage": {"input_tokens": 100, "cache_read_input_tokens": 50, "output_tokens": 9,
             "billing_usage": {"semantic": "openai", "openai_usage": {"prompt_tokens": 100, "completion_tokens": 9, "cost": .01}}}},
        ]
        result = summarize(rows)
        self.assertEqual(result["cache_read_input_tokens"], 50)
        self.assertEqual(result["input_tokens_including_cache"], 100)
        self.assertEqual(result["output_tokens"], 9)
        self.assertTrue(result["gateway_cost_complete"])

    def test_anthropic_input_is_exclusive_and_missing_cost_stays_unknown(self):
        result = summarize([{"kind": "request", "id": "one"},
                            {"kind": "usage", "id": "one", "usage": {
                                "input_tokens": 2, "cache_creation_input_tokens": 10, "cache_read_input_tokens": 20, "output_tokens": 3}}])
        self.assertEqual(result["input_tokens_including_cache"], 32)
        self.assertIsNone(result["gateway_reported_cost_usd"])
        self.assertFalse(result["gateway_cost_complete"])


if __name__ == "__main__":
    unittest.main()
