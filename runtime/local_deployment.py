"""Local-only deployment contract and sandbox service supervisor (no model calls)."""
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from urllib.parse import urlsplit


def validate_manifest(value):
    # Import-free of Harbor so the same validation runs inside the container.
    def require(ok, message):
        if not ok:
            raise ValueError(message)
    require(isinstance(value, dict) and set(value) == {'prepare', 'services', 'healthchecks'}, 'Invalid deployment fields')
    require(isinstance(value['prepare'], list) and len(value['prepare']) <= 12, 'Declare 0..12 preparation commands')
    for command in value['prepare']:
        require(isinstance(command, dict) and set(command) == {'argv', 'cwd'}, 'Invalid preparation fields')
    services, checks = value['services'], value['healthchecks']
    require(isinstance(services, list) and 0 < len(services) <= 12, 'Declare 1..12 local services')
    names = set()
    for service in services:
        require(isinstance(service, dict) and set(service) == {'name', 'argv', 'cwd'}, 'Invalid service fields')
        name, argv, cwd = service['name'], service['argv'], service['cwd']
        require(isinstance(name, str) and re.fullmatch(r'[a-z][a-z0-9_-]{0,40}', name) and name not in names, 'Invalid/duplicate service name')
        names.add(name)
    for command in [*value['prepare'], *services]:
        argv, cwd = command['argv'], command['cwd']
        require(isinstance(argv, list) and argv and all(isinstance(a, str) and a and '\0' not in a for a in argv), 'Command argv must be nonempty strings')
        require(isinstance(cwd, str) and (cwd == '/workspace/deployment' or cwd.startswith('/workspace/deployment/'))
                and '..' not in PurePosixPath(cwd).parts, 'Service cwd must be under /workspace/deployment')
    require(isinstance(checks, list) and 0 < len(checks) <= 24, 'Declare 1..24 health checks')
    for url in checks:
        require(isinstance(url, str), 'Health URL must be a string')
        p = urlsplit(url)
        require(p.scheme == 'http' and p.hostname == '127.0.0.1' and p.port and not p.username and not p.password and not p.fragment,
                'Health checks must use http://127.0.0.1:<port>/path')
    return value


def materialize(source, destination, expected_sha256):
    """Controller-only: discard prior releases and verify the fresh candidate copy."""
    if __package__:
        from .workspace_snapshot import inventory
    else:
        from workspace_snapshot import inventory
    source, destination = Path(source), Path(destination)
    if inventory(source)['sha256'] != expected_sha256:
        raise ValueError('Deployment source does not match the accepted candidate')
    if destination.is_symlink():
        destination.unlink()
    elif destination.exists():
        shutil.rmtree(destination)
    destination.mkdir()
    shutil.copytree(source, destination / 'repos', symlinks=True)
    copied = inventory(destination / 'repos')['sha256']
    if copied != expected_sha256:
        raise ValueError('Materialized release does not match the accepted candidate')
    return {'candidate_sha256': copied, 'source_verified': True, 'fresh_release': True}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def launch(manifest, evidence_path, timeout=60):
    """Runs as the dedicated unprivileged service UID; children survive this helper."""
    validate_manifest(manifest)
    processes, logs = [], []
    started = time.time()
    root = Path('/workspace/deployment').resolve()
    logdir = root / '.runtime-logs'
    logdir.mkdir(exist_ok=True)
    try:
        for index, command in enumerate(manifest['prepare']):
            cwd = Path(command['cwd']).resolve()
            if not cwd.is_relative_to(root):
                raise ValueError('Preparation cwd escapes deployment via a symlink')
            with (logdir / f'prepare-{index}.log').open('wb') as log:
                subprocess.run(command['argv'], cwd=cwd, stdin=subprocess.DEVNULL,
                               stdout=log, stderr=subprocess.STDOUT, check=True, timeout=600)
        for service in manifest['services']:
            cwd = Path(service['cwd']).resolve()
            if not cwd.is_relative_to(root):
                raise ValueError('Service cwd escapes deployment via a symlink')
            log = (logdir / (service['name'] + '.log')).open('ab')
            logs.append(log)
            process = subprocess.Popen(service['argv'], cwd=cwd, stdin=subprocess.DEVNULL,
                                       stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            processes.append(process)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        deadline, results = time.monotonic() + timeout, {}
        while time.monotonic() < deadline:
            if any(p.poll() is not None for p in processes):
                raise RuntimeError('A declared foreground service exited before readiness')
            results = {}
            for url in manifest['healthchecks']:
                try:
                    with opener.open(url, timeout=2) as response:
                        if 200 <= response.status < 300:
                            results[url] = {'status': response.status, 'checked_at': time.time()}
                except (OSError, ValueError):
                    pass
            if len(results) == len(set(manifest['healthchecks'])):
                break
            time.sleep(.25)
        else:
            raise RuntimeError('Local deployment health checks timed out')
        evidence = {'started_at': started, 'ready_at': time.time(), 'services': manifest['services'],
                    'pids': [p.pid for p in processes], 'healthchecks': results}
        Path(evidence_path).write_text(json.dumps(evidence, indent=2) + '\n')
    except BaseException:
        for process in processes:
            if process.poll() is None:
                process.kill()
        raise
    finally:
        for log in logs:
            log.close()


if __name__ == '__main__':
    launch(json.loads(Path(sys.argv[1]).read_text()), sys.argv[2])
