"""Read reported spend from Claude Code result events; no Harbor dependency.

Both the host-side controllers (to enforce a budget mid-run) and the trajectory
exporter (to report totals afterwards) read cost from the same streams, so the
parsing lives here rather than in either consumer.
"""
import json


def stream_cost(paths):
    """Total the last reported ``total_cost_usd`` per stream.

    Returns ``None`` when no stream reports a cost, which callers must treat as
    "unknown" rather than zero: a missing or truncated stream must not look like
    a free Stage.
    """
    total = 0.0
    found = False
    for path in paths:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        results = []
        for line in lines:
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if event.get("type") == "result" and event.get("total_cost_usd") is not None:
                results.append(float(event["total_cost_usd"]))
        if results:
            total += results[-1]
            found = True
    return total if found else None
