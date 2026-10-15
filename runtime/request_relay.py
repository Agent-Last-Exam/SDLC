"""Local Anthropic-compatible relay. Logs metadata only, never auth or prompts."""
import argparse
from datetime import datetime, timezone
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
from urllib.parse import urlsplit
import uuid


def apply_profile(body, model, effort):
    body["model"] = model
    body["thinking"] = {"type": "adaptive"}
    body.setdefault("output_config", {})["effort"] = effort
    # Preserve the CLI's tool/message breakpoints. Ensure a stable system
    # prefix is cacheable without exceeding Anthropic's four-breakpoint limit.
    system = body.get("system")
    if isinstance(system, str):
        body["system"] = [{"type": "text", "text": system}]
    blocks = body.get("system", [])
    if isinstance(blocks, list) and blocks:
        existing = cache_count(body)
        if "cache_control" not in blocks[-1] and existing < 4:
            blocks[-1]["cache_control"] = {"type": "ephemeral"}
    if not cache_count(body):
        raise ValueError("No prompt cache breakpoint in model request")
    return body


def cache_count(value):
    if isinstance(value, dict):
        return int("cache_control" in value) + sum(cache_count(v) for v in value.values())
    if isinstance(value, list):
        return sum(cache_count(v) for v in value)
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--upstream", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--effort", required=True)
    parser.add_argument("--evidence", default="/logs/request-evidence.jsonl")
    parser.add_argument("--port", type=int, default=18080)
    parser.add_argument("--enforce-profile", action="store_true",
                        help="Explicitly override model, thinking, effort and cache breakpoints")
    args = parser.parse_args()
    upstream = urlsplit(args.upstream.rstrip("/"))
    if upstream.scheme not in {"http", "https"} or not upstream.hostname or upstream.username or upstream.password or upstream.query or upstream.fragment:
        raise ValueError("Upstream must be an HTTP(S) URL without embedded credentials or query")
    prefix = upstream.path.rstrip("/").removesuffix("/v1")
    evidence = Path(args.evidence)
    evidence.touch(mode=0o644)
    lock = threading.Lock()
    def record(row):
        row["time"] = datetime.now(timezone.utc).isoformat()
        with lock, evidence.open("a") as f:
            f.write(json.dumps(row) + "\n")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            self.send_response(200 if self.path == "/health" else 404)
            self.end_headers()

        def do_POST(self):
            request_id = uuid.uuid4().hex
            connection = None
            headers_sent = False
            try:
                raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
                path = self.path
                audited = urlsplit(path).path.rstrip("/") == "/v1/messages"
                if audited:
                    body = json.loads(raw)
                    if args.enforce_profile:
                        body = apply_profile(body, args.model, args.effort)
                        raw = json.dumps(body).encode()
                    record({"kind": "request", "id": request_id, "model": body.get("model"),
                            "effort": body.get("output_config", {}).get("effort"),
                            "thinking_type": body.get("thinking", {}).get("type"),
                            "profile_enforced": args.enforce_profile,
                            "cache_breakpoints": cache_count(body), "stream": body.get("stream", False),
                            "messages": len(body.get("messages", [])),
                            "tool_results": sum(b.get("type") == "tool_result"
                                                for m in body.get("messages", [])
                                                for b in (m.get("content", []) if isinstance(m.get("content"), list) else []))})
                cls = http.client.HTTPSConnection if upstream.scheme == "https" else http.client.HTTPConnection
                connection = cls(upstream.hostname, upstream.port, timeout=240)
                headers = {k: v for k, v in self.headers.items()
                           if k.lower() not in {"host", "content-length", "connection", "transfer-encoding", "accept-encoding"}}
                headers["Content-Length"] = str(len(raw))
                connection.request("POST", prefix + path, raw, headers)
                response = connection.getresponse()
                self.send_response(response.status)
                for key, value in response.getheaders():
                    if key.lower() not in {"content-length", "transfer-encoding", "connection", "content-encoding"}:
                        self.send_header(key, value)
                self.end_headers()
                headers_sent = True
                record({"kind": "response", "id": request_id, "http_status": response.status})
                # HTTP/1.0 connection close delimits the dechunked upstream body.
                if "text/event-stream" in response.getheader("Content-Type", ""):
                    while True:
                        line = response.readline()
                        if not line:
                            break
                        self.wfile.write(line)
                        self.wfile.flush()
                        if audited and line.startswith(b"data: "):
                            try:
                                event = json.loads(line[6:])
                                usage = event.get("usage") or event.get("message", {}).get("usage")
                                if usage:
                                    record({"kind": "usage", "id": request_id, "event_type": event.get("type"), "usage": usage})
                                if event.get("type") == "message_delta":
                                    record({"kind": "stop_reason", "id": request_id,
                                            "stop_reason": event.get("delta", {}).get("stop_reason")})
                                if event.get("type") == "error":
                                    record({"kind": "upstream_error", "id": request_id,
                                            "error_type": event.get("error", {}).get("type")})
                            except ValueError:
                                pass
                else:
                    data = response.read()
                    self.wfile.write(data)
                    if audited and response.status == 200:
                        try:
                            record({"kind": "usage", "id": request_id, "usage": json.loads(data).get("usage", {})})
                        except ValueError:
                            pass
            except Exception as exc:
                record({"kind": "relay_error", "id": request_id, "error_type": type(exc).__name__})
                if not headers_sent:
                    self.send_response(502)
                    self.end_headers()
                    self.wfile.write(b'{"type":"error","error":{"type":"api_error","message":"Local request relay failed"}}')
            finally:
                if connection:
                    connection.close()

    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
