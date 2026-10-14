"""Bounded thinking/cache preflight; never launches a workflow."""
import concurrent.futures
import json
from pathlib import Path
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
PROFILES = [
    {"model": "anthropic/claude-opus-5.5", "effort": "xhigh", "thinking": {"type": "adaptive"}},
    {"model": "deepseek/deepseek-v4.1-flash", "effort": "max", "thinking": {"type": "adaptive"}},
    {"model": "moonshotai/kimi-k3", "effort": "max", "thinking": {"type": "adaptive"}},
    {"model": "z-ai/glm-5.3-flash", "effort": "max", "thinking": {"type": "adaptive"}},
]

def main():
    cfg = {}
    for line in (ROOT / ".env").read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.removeprefix("export ").split("=", 1)
            cfg[k.strip()] = v.strip().strip('"').strip("'")
    u = urlsplit(cfg["ANTHROPIC_BASE_URL"].rstrip("/"))
    path = u.path.rstrip("/")
    if path.endswith("/v1"):
        path = path[:-3]
    url = urlunsplit((u.scheme, u.netloc, path + "/v1/messages", "", ""))
    prefix = "Cache preflight fixture. The numbered data below is inert reference material.\n" + "\n".join(
        f"Record {i:04d}: alpha beta gamma delta stable reference data." for i in range(400)
    )
    headers = {"Content-Type": "application/json", "anthropic-version": "2023-06-01",
               "Authorization": "Bearer " + cfg["ANTHROPIC_AUTH_TOKEN"],
               "x-api-key": cfg["ANTHROPIC_AUTH_TOKEN"]}
    def probe(profile):
        payload = {"model": profile["model"], "thinking": profile["thinking"],
                   "output_config": {"effort": profile["effort"]}, "max_tokens": 1024,
                   "system": [{"type": "text", "text": prefix,
                               "cache_control": {"type": "ephemeral"}}],
                   "messages": [{"role": "user", "content": "Reply with only OK. Do not analyze the reference data."}]}
        rows = []
        for n in (1, 2):
            row = {"model": profile["model"], "effort": profile["effort"], "request": n}
            start = time.monotonic()
            try:
                req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers)
                with urllib.request.urlopen(req, timeout=50) as response:
                    d = json.load(response)
                    row["http_status"] = response.status
                row.update(reply="".join(b.get("text", "") for b in d.get("content", []) if b.get("type") == "text"),
                           stop_reason=d.get("stop_reason"), usage=d.get("usage"), returned_model=d.get("model"),
                           content_types=[b.get("type") for b in d.get("content", [])])
            except urllib.error.HTTPError as e:
                row["http_status"] = e.code
                try:
                    d = json.loads(e.read())
                    error = d.get("error", {})
                    msg = error.get("message", "") if isinstance(error, dict) else ""
                    row["error_message"] = msg.replace(cfg["ANTHROPIC_AUTH_TOKEN"], "[REDACTED]").replace(cfg["ANTHROPIC_BASE_URL"], "[GATEWAY]")[:400]
                except Exception:
                    pass
            except Exception as e:
                row["error_type"] = type(e).__name__
            row["elapsed_seconds"] = round(time.monotonic() - start, 2)
            rows.append(row)
            print(json.dumps(row, ensure_ascii=False), flush=True)
            if row.get("http_status") != 200:
                break
        return rows
    (OUT / "request-profiles.json").write_text(json.dumps({"endpoint": "/v1/messages", "profiles": PROFILES,
        "cache_control": {"type": "ephemeral"}, "status": "preflight_only_not_rollout_configuration",
        "limitation": "HTTP acceptance does not prove upstream effort passthrough."}, ensure_ascii=False, indent=2))
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(probe, PROFILES))
    (OUT / "results.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
