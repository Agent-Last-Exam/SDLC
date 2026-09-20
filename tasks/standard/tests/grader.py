"""Grade one post execution using the release's calibrated ID normalization."""
import json
import os
from pathlib import Path

from reports import core, jest, playwright


def grade(tests_dir, output):
    config = json.loads((tests_dir / 'config.json').read_text())
    rows = []
    for suite in ('core-unit', 'core-e2e'):
        tests, _ = core(output / 'post' / suite / 'results.xml', suite)
        rows.extend(tests)
    tests, _, _ = jest(output / 'post/dash-unit/results.json', {})
    rows.extend(tests)
    tests, _ = playwright(output / 'post/dash-e2e/results.json')
    rows.extend(tests)
    ids = [row['id'] for row in rows]
    assert len(ids) == len(set(ids)), 'report ID collision'
    states = {row['id']: row['status'] for row in rows}
    result = {}
    selected = []
    for kind in ('f2p', 'p2p'):
        nodes = config[kind + '_node_ids']
        assert len(nodes) == len(set(nodes)), 'duplicate scoring ID'
        result[kind + '_total'] = len(nodes)
        result[kind + '_passed'] = sum(states.get(node) == 'passed' for node in nodes)
        selected.extend({'name': '[' + kind + '] ' + node,
                         'status': 'passed' if states.get(node) == 'passed' else 'failed'}
                        for node in nodes)
    result['reward'] = int(bool(result['f2p_total']) and all(
        result[k + '_total'] == result[k + '_passed'] for k in ('f2p', 'p2p')))
    (output / 'reward.json').write_text(json.dumps(result, indent=2) + '\n')
    (output / 'reward.txt').write_text(str(result['reward']) + '\n')
    passed = sum(row['status'] == 'passed' for row in selected)
    (output / 'ctrf.json').write_text(json.dumps({'reportFormat': 'CTRF', 'specVersion': '1.0.0',
        'results': {'tool': {'name': 'saleor-post'}, 'summary': {'tests': len(selected),
        'passed': passed, 'failed': len(selected)-passed, 'skipped': 0, 'pending': 0,
        'other': 0}, 'tests': selected}}, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    grade(Path(os.environ.get('TESTS_DIR', '/tests')),
          Path(os.environ.get('VERIFIER_DIR', '/logs/verifier')))
