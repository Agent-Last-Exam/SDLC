"""Local HTTP integration: audit transport must preserve requests and omit secrets."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.request


class RelayTests(unittest.TestCase):
    def test_audit_is_transparent_and_profile_changes_are_explicit(self):
        received = []

        class Upstream(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_POST(self):
                received.append((self.path, self.rfile.read(int(self.headers["Content-Length"])),
                                 self.headers.get("Authorization")))
                data = json.dumps({"usage": {"input_tokens": 7, "output_tokens": 2}}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        server = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            for enforce in (False, True):
                with self.subTest(enforce=enforce), tempfile.TemporaryDirectory() as temp:
                    with socket.socket() as reservation:
                        reservation.bind(("127.0.0.1", 0))
                        port = reservation.getsockname()[1]
                    evidence = Path(temp) / "evidence.jsonl"
                    command = [sys.executable, "-m", "runtime.request_relay", "--upstream",
                               f"http://127.0.0.1:{server.server_port}/gateway/v1", "--model", "selected",
                               "--effort", "high", "--port", str(port), "--evidence", str(evidence)]
                    if enforce:
                        command.append("--enforce-profile")
                    process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
                    try:
                        endpoint = f"http://127.0.0.1:{port}"
                        deadline = time.monotonic() + 5
                        while True:
                            try:
                                with urllib.request.urlopen(endpoint + "/health", timeout=.2):
                                    break
                            except OSError:
                                if process.poll() is not None or time.monotonic() > deadline:
                                    self.fail("Relay failed to start")
                                time.sleep(.02)
                        raw = b'{ "model": "original", "system": "private-prompt", "messages": [], "thinking": {"type": "disabled"} }'
                        request = urllib.request.Request(endpoint + "/v1/messages", data=raw,
                                                         headers={"Authorization": "Bearer private-token"})
                        with urllib.request.urlopen(request, timeout=3) as response:
                            self.assertEqual(json.load(response)["usage"]["output_tokens"], 2)
                        path, forwarded, auth = received[-1]
                        self.assertEqual(path, "/gateway/v1/messages")
                        self.assertEqual(auth, "Bearer private-token")
                        if enforce:
                            self.assertEqual(json.loads(forwarded)["model"], "selected")
                        else:
                            self.assertEqual(forwarded, raw)
                        text = evidence.read_text()
                        self.assertNotIn("private-token", text)
                        self.assertNotIn("private-prompt", text)
                        rows = [json.loads(line) for line in text.splitlines()]
                        self.assertEqual(rows[0]["profile_enforced"], enforce)
                        self.assertTrue(any(r["kind"] == "usage" for r in rows))
                    finally:
                        process.terminate()
                        process.communicate(timeout=5)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
