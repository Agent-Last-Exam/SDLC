"""Materialize image-provided hard links before taking a strict Base inventory."""
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile


def materialize_hardlinks(root):
    root = Path(root).resolve()
    count = 0
    for path in root.rglob("*"):
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink == 1:
            continue
        fd, temporary = tempfile.mkstemp(prefix=".materialize-", dir=path.parent)
        os.close(fd)
        try:
            shutil.copy2(path, temporary)
            os.replace(temporary, path)
            count += 1
        finally:
            Path(temporary).unlink(missing_ok=True)
    return count


if __name__ == "__main__":
    print(json.dumps({"materialized_files": materialize_hardlinks(sys.argv[1])}))
