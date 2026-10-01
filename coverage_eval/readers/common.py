from pathlib import Path

from coverage_eval.workspace import source_file


def relative_source(filename, context):
    path = Path(filename)
    if not path.is_absolute():
        path = context.cwd / path
    try:
        relative = path.resolve().relative_to(context.repo.resolve()).as_posix()
    except ValueError:
        return None
    return relative if source_file(context.repository, relative, context.suite) else None
