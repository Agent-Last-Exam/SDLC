"""Normalize per-request SSE usage without double-counting stream snapshots."""
from decimal import Decimal


def summarize(rows):
    requests = {r["id"]: r for r in rows if r.get("kind") == "request"}
    latest = {}
    for row in rows:
        if row.get("kind") == "usage":
            latest.setdefault(row["id"], {}).update(row["usage"])
    totals = {"requests": len(requests), "requests_with_usage": len(latest),
              "input_tokens_including_cache": 0, "output_tokens": 0,
              "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0,
              "gateway_reported_cost_usd": None, "requests_with_gateway_cost": 0}
    cost = Decimal(0)
    for usage in latest.values():
        read = usage.get("cache_read_input_tokens", 0) or 0
        write = usage.get("cache_creation_input_tokens", 0) or 0
        billing = usage.get("billing_usage", {})
        native = billing.get("openai_usage", {}) if billing.get("semantic") == "openai" else {}
        # Some translated providers retain OpenAI's inclusive prompt count in
        # Anthropic input_tokens. Prefer explicitly tagged native billing usage.
        prompt = native.get("prompt_tokens")
        if prompt is None:
            prompt = (usage.get("input_tokens", 0) or 0) + read + write
        totals["input_tokens_including_cache"] += prompt
        totals["output_tokens"] += native.get("completion_tokens", usage.get("output_tokens", 0)) or 0
        totals["cache_read_input_tokens"] += read
        totals["cache_creation_input_tokens"] += write
        if native.get("cost") is not None:
            cost += Decimal(str(native["cost"]))
            totals["requests_with_gateway_cost"] += 1
    if totals["requests_with_gateway_cost"]:
        totals["gateway_reported_cost_usd"] = float(cost)
    totals["gateway_cost_complete"] = bool(requests) and totals["requests_with_gateway_cost"] == len(requests)
    return totals
