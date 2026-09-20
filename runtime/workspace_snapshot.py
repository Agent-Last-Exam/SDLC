"""Content/mode/link inventory and archive of the candidate; also runs in the sandbox."""
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import tarfile


def inventory(root):
    root = Path(root).resolve()
    entries = {}
    for path in sorted(root.rglob('*')):
        info = path.lstat()
        key = str(path.relative_to(root))
        if stat.S_ISLNK(info.st_mode):
            if not path.resolve().is_relative_to(root):
                raise ValueError(f'Candidate symlink escapes repositories: {key}')
            entries[key] = {'link': os.readlink(path)}
        elif stat.S_ISREG(info.st_mode):
            if info.st_nlink != 1:
                raise ValueError(f'Candidate hard link is not supported: {key}')
            entries[key] = {'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'executable': bool(info.st_mode & 0o111)}
        elif stat.S_ISDIR(info.st_mode):
            entries[key] = {'directory': True}
        else:
            raise ValueError(f'Nonregular candidate file: {key}')
    digest = hashlib.sha256(json.dumps(entries, sort_keys=True).encode()).hexdigest()
    return {'sha256': digest, 'files': entries}


if __name__ == '__main__':
    root = Path('/workspace/repos')
    value = inventory(root)
    if len(sys.argv) > 1:
        with tarfile.open(sys.argv[1], 'w') as archive:
            archive.add(root, arcname='repos', recursive=True)
    print(json.dumps(value))
