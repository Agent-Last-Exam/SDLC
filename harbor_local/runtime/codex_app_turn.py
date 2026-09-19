#!/usr/bin/env python3
"""One native Codex app-server turn over stdio; runs inside the stage sandbox.

The pinned CLI retains old developer instructions on resume. App-server's
thread/inject_items adds the current developer-role message to native history.
No HTTP client or credential handling is implemented here: Codex owns both.
"""
import json
from pathlib import Path
import subprocess
import sys


def app_server_command(allow_subagents):
    return ["codex", "app-server", "--stdio", "-c", "features.multi_agent=" + str(allow_subagents).lower()]


def main():
    request = json.loads(Path(sys.argv[1]).read_text())
    proc = subprocess.Popen(app_server_command(request["allow_subagents"]), stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=sys.stderr, text=True, bufsize=1)
    early_completions = []
    def send(value):
        proc.stdin.write(json.dumps(value, ensure_ascii=False) + "\n")
        proc.stdin.flush()
    def receive():
        line = proc.stdout.readline()
        if not line:
            raise RuntimeError("Codex app-server closed before the turn completed")
        value = json.loads(line)
        if "method" in value and "id" in value:
            # No hidden approval/input loop in an unattended stage.
            send({"id": value["id"], "error": {"code": -32601, "message": "Interactive requests unavailable in this workflow"}})
        elif value.get("method") in {"item/completed", "turn/completed", "error", "thread/tokenUsage/updated"}:
            print(json.dumps(value, ensure_ascii=False), flush=True)
        return value
    def rpc(ident, method, params):
        send({"id": ident, "method": method, "params": params})
        while True:
            value = receive()
            if value.get("method") == "turn/completed":
                early_completions.append(value)
            if value.get("id") == ident and "method" not in value:
                if "error" in value:
                    raise RuntimeError(f"{method}: {value['error']}")
                return value["result"]
    try:
        rpc(1, "initialize", {"clientInfo": {"name": "sdlc_harbor", "title": "SDLC Harbor", "version": "1"},
                              "capabilities": {"experimentalApi": True}})
        send({"method": "initialized", "params": {}})
        params = {"model": request["model"], "cwd": "/workspace", "approvalPolicy": "never",
                  "sandbox": "danger-full-access",
                  "config": {"web_search": "disabled", "model_reasoning_effort": "high"}}
        session = request.get("session_id")
        if session:
            params["threadId"] = session
        result = rpc(2, "thread/resume" if session else "thread/start", params)
        thread = result["thread"]
        thread_id = thread["id"]
        session_id = thread.get("sessionId") or thread_id
        if session and session_id != session:
            raise RuntimeError("App-server resumed a different native session")
        print(json.dumps({"type": "thread.started", "thread_id": session_id, "transport": "app-server"}), flush=True)
        rpc(3, "thread/inject_items", {"threadId": thread_id, "items": [
            {"type": "message", "role": "developer", "content": [{"type": "input_text", "text": request["prompt"]}]}
        ]})
        rpc(4, "turn/start", {"threadId": thread_id, "input": [{"type": "text", "text": request["instruction"]}], "effort": "high"})
        while True:
            event = early_completions.pop(0) if early_completions else receive()
            if event.get("method") == "turn/completed" and event["params"].get("threadId") == thread_id:
                turn = event["params"]["turn"]
                if turn["status"] != "completed":
                    raise RuntimeError(f"Codex turn {turn['status']}: {turn.get('error')}")
                break
    finally:
        proc.stdin.close()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.terminate()
            proc.wait(timeout=5)


if __name__ == "__main__":
    main()
