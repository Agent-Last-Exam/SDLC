"""Pure line-set arithmetic, shared by all projects and report formats."""

def measured(lines, changes, *, changed_eligible=None):
    all_lines = sum(len(executable) for executable, _ in lines.values())
    hit_lines = sum(len(covered) for _, covered in lines.values())
    changed_all, changed_hit = 0, 0
    changed_uncomparable = []
    for path, (executable, covered) in lines.items():
        changed = changes.get(path, set())
        if changed_eligible is not None and path not in changed_eligible:
            if changed & executable:
                changed_uncomparable.append(path)
            continue
        changed_all += len(executable & changed)
        changed_hit += len(covered & changed)
    return {
        "covered_lines": hit_lines,
        "executable_lines": all_lines,
        "line_percent": round(100 * hit_lines / all_lines, 2) if all_lines else None,
        "changed_covered_lines": changed_hit,
        "changed_executable_lines": changed_all,
        "changed_line_percent": round(100 * changed_hit / changed_all, 2)
        if changed_all else None,
        "changed_uncomparable_files": sorted(changed_uncomparable),
    }


def normalize_pair(official, agent, official_hashes, agent_hashes):
    """Use one denominator for identical source, including omitted Jest files."""
    names = set(official) | set(agent)
    comparable = {name for name in names
                  if official_hashes.get(name) is not None
                  and official_hashes.get(name) == agent_hashes.get(name)}
    old = dict(official)
    new = dict(agent)
    for name in comparable:
        executable = (official.get(name, (set(), set()))[0]
                      | agent.get(name, (set(), set()))[0])
        old[name] = (executable, official.get(name, (set(), set()))[1] & executable)
        new[name] = (executable, agent.get(name, (set(), set()))[1] & executable)
    return old, new, comparable, sorted(names - comparable)


def comparison(official, agent, official_hashes, agent_hashes):
    official, agent, comparable, diverged = normalize_pair(
        official, agent, official_hashes, agent_hashes)
    shared = agent_extra = combined = denominator = 0
    for name in comparable:
        executable = official[name][0]
        old = official[name][1]
        new = agent[name][1]
        denominator += len(executable)
        shared += len(old & new)
        agent_extra += len(new - old)
        combined += len(old | new)
    return {
        "comparable_files": len(comparable),
        "uncomparable_files": diverged,
        "comparison_executable_lines": denominator,
        "covered_by_both": shared,
        "agent_only_covered_lines": agent_extra,
        "combined_covered_lines": combined,
        "combined_line_percent": round(100 * combined / denominator, 2)
        if denominator else None,
    }



def merge_lines(reports):
    result = {}
    for lines in reports:
        for path, (executable, covered) in lines.items():
            previous = result.get(path, (set(), set()))
            result[path] = (previous[0] | executable, previous[1] | covered)
    return result
