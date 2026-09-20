"""Remove retired stage-owned temporary entries without unlinking service resources."""
from pathlib import Path
import stat
import sys


def cleanup_owned(roots, uids):
    uids = set(uids)

    def visit(path):
        try:
            info = path.lstat()
        except FileNotFoundError:
            return
        if stat.S_ISDIR(info.st_mode):
            if info.st_uid not in uids and info.st_uid != 0:
                return  # Live service/private directories are not ours to scan.
            for child in path.iterdir():
                visit(child)
            # A stage-owned parent may contain service-owned resources. Keep it
            # until empty; never recursively delete another identity's files.
            if info.st_uid in uids and not any(path.iterdir()):
                path.rmdir()
        elif info.st_uid in uids:
            path.unlink()  # Do not follow symlinks, even those pointing outside.

    for root in roots:
        for child in Path(root).iterdir():
            visit(child)


if __name__ == '__main__':
    cleanup_owned(['/tmp', '/var/tmp', '/dev/shm'], map(int, sys.argv[1:]))
