"""Framework-independent test ownership based on inventories and patch lines."""

from dataclasses import asdict


def select_cases(cases, changes, base_files, baseline, renamed):
    selected, uncertain = [], []
    baseline_ids = {case.id for case in baseline.cases} if baseline.exit_code == 0 else None
    for case in cases:
        if case.path not in changes:
            continue
        reason = case.uncertainty
        if not reason:
            new_file = case.path not in base_files and case.path not in renamed
            new_id = baseline_ids is not None and case.path not in renamed and case.id not in baseline_ids
            if new_file or new_id:
                selected.append(case)
                continue
            if case.start is None or case.end is None:
                reason = "test source range unavailable"
            elif changes[case.path].intersection(range(case.start, case.end + 1)):
                selected.append(case)
                continue
        if reason:
            uncertain.append({**asdict(case), "reason": reason})
    return selected, uncertain


def support_changes(changes, cases, test_paths):
    """Record changed helpers/fixtures without assigning every affected case."""
    spans = {}
    for case in cases:
        if case.start is not None and case.end is not None:
            spans.setdefault(case.path, set()).update(range(case.start, case.end + 1))
    return {path: sorted(lines - spans.get(path, set())) for path, lines in changes.items()
            if path in test_paths and lines - spans.get(path, set())}
