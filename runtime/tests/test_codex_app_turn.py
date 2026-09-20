"""Native RPC ordering checks with a fake stdio server, without calling Codex."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from runtime import codex_app_turn
from runtime.workflow_agent import native_role_evidence


class Process:
    def __init__(self, events):
        self.stdin = io.StringIO()
        self.stdout = io.StringIO('\n'.join(json.dumps(e) for e in events) + '\n')

    def wait(self, timeout):
        return 0


class AppTurnTests(unittest.TestCase):
    def invoke(self, events):
        with tempfile.TemporaryDirectory() as temp:
            request = Path(temp) / 'request.json'
            request.write_text(json.dumps({'allow_subagents': False, 'model': 'test', 'session_id': 'same', 'prompt': 'role', 'instruction': 'task'}))
            with patch('sys.argv', ['app_turn', str(request)]), patch.object(codex_app_turn.subprocess, 'Popen', return_value=Process(events)), contextlib.redirect_stdout(io.StringIO()):
                codex_app_turn.main()

    def events(self, status):
        def completed(turn, state):
            return {'method': 'turn/completed', 'params': {'threadId': 'same', 'turn': {'id': turn, 'status': state}}}
        return [
            {'id': 1, 'result': {}},
            completed('previous', 'completed'),
            {'id': 2, 'result': {'thread': {'id': 'same'}}},
            {'id': 3, 'result': {}},
            completed('current', status),  # Completion can arrive before the turn/start reply.
            {'id': 4, 'result': {'turn': {'id': 'current'}}},
        ]

    def test_current_completion_before_start_reply_is_accepted(self):
        self.invoke(self.events('completed'))

    def test_old_completion_cannot_hide_current_failure(self):
        with self.assertRaisesRegex(RuntimeError, 'Codex turn failed'):
            self.invoke(self.events('failed'))

    def test_old_completion_cannot_hide_missing_current_completion(self):
        events = [e for e in self.events('completed') if e.get('params', {}).get('turn', {}).get('id') != 'current']
        with self.assertRaisesRegex(RuntimeError, 'closed before'):
            self.invoke(events)

    def test_same_role_from_prior_sprint_is_not_current_activation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            rows = [{'type': 'session_meta', 'payload': {'id': 'same'}},
                    {'type': 'response_item', 'payload': {'role': 'developer', 'content': 'SDLC_STAGE_ROLE: qa\nSDLC_STAGE_ID: sprint1/qa'}}]
            (root / 'session.jsonl').write_text('\n'.join(json.dumps(r) for r in rows))
            with self.assertRaisesRegex(RuntimeError, 'stale stage'):
                native_role_evidence(root, 'same', 'qa', 'sprint2/qa')


if __name__ == '__main__':
    unittest.main()
