"""Public format/traceability gates. These are not hidden rubrics or quality scores."""
import hashlib
import re
from pathlib import Path

from graphql import build_schema, parse, validate_schema


class GateError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise GateError(message)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def heading_view(text):
    """Mask fenced code without moving offsets used to slice original prose."""
    result, fence = [], None
    for line in text.splitlines(keepends=True):
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line.rstrip("\r\n"))
        if fence is not None:
            result.append(re.sub(r"[^\r\n]", " ", line))
            if marker and marker[1][0] == fence[0] and len(marker[1]) >= len(fence) and not marker[2].strip():
                fence = None
        elif marker:
            fence = marker[1]
            result.append(re.sub(r"[^\r\n]", " ", line))
        else:
            result.append(line)
    return "".join(result)


def markdown(path, template):
    require(path.is_file() and not path.is_symlink(), f"Missing regular output: {path.name}")
    text = path.read_text()
    require(text.strip(), f"Empty output: {path.name}")
    require(not re.search(r"\{(?:nn|标题|v1|版本号)\}", text), f"Unfilled template: {path.name}")
    headings = re.findall(r"^## .+$", template.read_text(), re.M)
    actual = re.findall(r"^## .+$", heading_view(text), re.M)
    require(actual == headings, f"Expected exact section headings in {path.name}: {headings}")
    for key in ("版本", "责任"):
        require(re.search(rf"^{key}：\S.+$", text, re.M), f"Missing metadata {key}: {path.name}")
    return text


def blocks(text, prefix):
    view = heading_view(text)
    matches = list(re.finditer(rf"^### ({prefix}\d{{2,}}) · (.+)$", view, re.M))
    result = {}
    for i, match in enumerate(matches):
        key = match[1]
        require(key not in result, f"Duplicate ID: {key}")
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        # Stop at any other heading, not only the next same-prefix block.
        boundary = re.search(r"^#{1,3} ", view[match.end():end], re.M)
        if boundary:
            end = match.end() + boundary.start()
        body = text[match.end():end]
        result[key] = body
    return result


def field(body, name):
    match = re.search(rf"^- {re.escape(name)}：[ \t]*(.*)$", body, re.M)
    require(match, f"Missing field: {name}")
    value = match[1].strip()
    if not value:
        # Narrative slots may span paragraphs. Fixed key position does not mean
        # the whole business description has to be squeezed into one line.
        value = re.split(r"^- [^\n：]+：", body[match.end():], maxsplit=1, flags=re.M)[0].strip()
    require(value, f"Empty field: {name}")
    return value


def refs(text, prefix):
    return set(re.findall(rf"\b{prefix}\d{{2,}}\b", text))


def validate_prd(directory, templates):
    text = markdown(directory / "prd.md", templates / "prd.md")
    requirements = blocks(text, "R")
    require(requirements, "PRD must contain at least one Rnn requirement")
    all_ac = set()
    for rid, body in requirements.items():
        for name in ("来源", "需求描述"):
            field(body, name)
        require(field(body, "优先级") in {"P0", "P1", "P2"}, f"Invalid priority: {rid}")
        criteria = re.findall(r"^\s+- (AC-\d{2,}-[1-9]\d*)：(.+)$", body, re.M)
        require(criteria, f"No acceptance criteria: {rid}")
        for acid, statement in criteria:
            require(acid.startswith("AC-" + rid[1:] + "-"), f"AC belongs to wrong requirement: {acid}")
            require(acid not in all_ac, f"Duplicate AC: {acid}")
            all_ac.add(acid)
    return {"requirements": list(requirements), "acceptance_criteria": sorted(all_ac)}


def validate_design(directory, templates, prd_path, base_schema):
    names = ("frontend-design", "backend-design", "interface-contract")
    texts = {name: markdown(directory / f"{name}.md", templates / f"{name}.md") for name in names}
    requirements = set(blocks(prd_path.read_text(), "R"))
    front = blocks(texts["frontend-design"], "FD")
    back = blocks(texts["backend-design"], "BD")
    tasks = blocks(texts["backend-design"], "BT")
    interfaces = blocks(texts["interface-contract"], "I")
    require(front and back and interfaces and tasks, "Saleor needs FD, BD, BT and I blocks")
    covered = set()
    for key, body in {**front, **back}.items():
        covered_here = refs(field(body, "覆盖需求"), "R")
        require(covered_here and covered_here <= requirements, f"Invalid requirement reference: {key}")
        covered |= covered_here
    for iid, body in interfaces.items():
        require(refs(field(body, "所属设计单元"), "BD") <= set(back), f"Unknown BD: {iid}")
        require(refs(field(body, "所属设计单元"), "BD"), f"Missing BD: {iid}")
        for key in ("提供方", "调用方", "目标定义", "字段说明", "权限", "错误", "完成判定", "变更与兼容"):
            field(body, key)
    graph = {}
    for tid, body in tasks.items():
        owners = refs(field(body, "覆盖设计单元"), "BD")
        require(owners and owners <= set(back), f"Unknown or missing task owner: {tid}")
        graph[tid] = refs(field(body, "依赖"), "BT")
        require(graph[tid] <= set(tasks), f"Unknown dependency: {tid}")
    visiting, visited = set(), set()
    def visit(tid):
        require(tid not in visiting, f"Task dependency cycle: {tid}")
        if tid in visited:
            return
        visiting.add(tid)
        for dep in graph[tid]:
            visit(dep)
        visiting.remove(tid)
        visited.add(tid)
    for tid in graph:
        visit(tid)
    for prefix, known in (("R", requirements), ("FD", set(front)), ("BD", set(back)), ("I", set(interfaces)), ("BT", set(tasks))):
        used = refs("\n".join(texts.values()), prefix)
        require(used <= known, f"Dangling {prefix} references: {sorted(used - known)}")
    schema_path = directory / "target-schema.graphql"
    require(schema_path.is_file() and not schema_path.is_symlink(), "Missing target-schema.graphql")
    try:
        target = schema_path.read_text()
        schema = build_schema(target)
        errors = validate_schema(schema)
        require(not errors, "Invalid target schema: " + "; ".join(str(e) for e in errors[:5]))
        base_names = {d.name.value for d in parse(base_schema.read_text()).definitions if getattr(d, "name", None)}
        target_names = {d.name.value for d in parse(target).definitions if getattr(d, "name", None)}
        # A complete schema can remove retired definitions, but must account for
        # each removal in the design. Do not mistake a valid SDL excerpt for a full schema.
        removed = base_names - target_names
        all_design = "\n".join(texts.values())
        unaccounted = [name for name in removed if not re.search(r"\b" + re.escape(name) + r"\b", all_design)]
        require(not unaccounted, f"SDL may be a fragment; removed definitions absent from design: {sorted(unaccounted)[:20]}")
    except GateError:
        raise
    except Exception as exc:
        raise GateError(f"GraphQL SDL cannot be built: {exc}") from exc
    return {"requirements": sorted(requirements),
            "covered_requirements": sorted(covered), "design_units": sorted(set(front) | set(back)),
            "interfaces": sorted(interfaces), "schema_definitions": len(target_names),
            "removed_schema_definitions": sorted(removed),
            "limits": "Public structural checks only; not semantic approval"}


def validate_stage(stage, directory, workspace, accepted_prd=None):
    expected = {Path(path).name for path in stage["outputs"].values()}
    for p in directory.rglob("*"):
        require(not p.is_symlink(), f"Symlink output is not accepted: {p.name}")
        require(p.is_dir() or p.is_file(), f"Nonregular output: {p.name}")
        if p.is_file():
            relative = p.relative_to(directory)
            allowed = str(relative) in expected or (stage["role"] == "architect" and relative.parts[0] == "interfaces")
            require(allowed, f"Undeclared output {relative}; keep investigation notes in scratch")
    require(all((directory / name).is_file() for name in expected), f"Missing outputs: {sorted(expected)}")
    if stage["role"] == "pm":
        return validate_prd(directory, workspace / "templates")
    require(accepted_prd is not None, "No accepted PRD input")
    return validate_design(directory, workspace / "templates", accepted_prd,
                           workspace / "repos/saleor/saleor/graphql/schema.graphql")
