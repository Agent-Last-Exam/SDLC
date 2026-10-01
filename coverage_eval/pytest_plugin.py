"""Pytest collection inventory and exact node-id selection."""

import json
import os
from pathlib import Path


def pytest_collection_modifyitems(config, items):
    selection = os.environ.get("COVERAGE_SELECTED_NODEIDS")
    if not selection:
        return
    wanted = set(json.loads(Path(selection).read_text()))
    missing = wanted - {item.nodeid for item in items}
    if missing:
        import pytest
        raise pytest.UsageError("selected coverage cases were not collected: " + ", ".join(sorted(missing)))
    selected = [item for item in items if item.nodeid in wanted]
    rejected = [item for item in items if item.nodeid not in wanted]
    items[:] = selected
    config.hook.pytest_deselected(items=rejected)


def pytest_collection_finish(session):
    selection = os.environ.get("COVERAGE_SELECTED_NODEIDS")
    if selection:
        wanted = set(json.loads(Path(selection).read_text()))
        missing = wanted - {item.nodeid for item in session.items}
        if missing:
            import pytest
            raise pytest.UsageError("selected coverage cases were deselected: " + ", ".join(sorted(missing)))
    destination = os.environ.get("COVERAGE_PYTEST_INVENTORY")
    if not destination:
        return
    rows = []
    for item in session.items:
        path, line, _ = item.location
        rows.append({"id": item.nodeid, "path": path, "line": line + 1})
    Path(destination).write_text(json.dumps(rows, indent=2) + "\n")
