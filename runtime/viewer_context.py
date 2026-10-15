"""Build display-only Harbor jobs from archived trajectories and prompt snapshots."""
import argparse
import copy
import gzip
import hashlib
import json
from pathlib import Path
import re
import shutil
import tempfile
from uuid import NAMESPACE_URL, uuid5


MARKER = "sdlc-archive-context-view-v1"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def contained(root, name):
    path = (root / name).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError(f"Archive path escapes its root: {name}")
    return path


def fenced(text):
    fence = "`" * max(3, max((len(s) + 1 for s in re.findall(r"`+", text)), default=3))
    return f"{fence}\n{text}\n{fence}"


def display_trajectory(manifest_path):
    """Return a derived ATIF document; never write to the original archive."""
    manifest_path = Path(manifest_path)
    bundle = manifest_path.parent
    archive = bundle.parent
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("schema_version") != 1:
        raise ValueError("Unsupported prompt snapshot manifest version")
    source = contained(archive, manifest["trajectory"]["path"])
    raw = source.read_bytes()
    if digest(raw) != manifest["trajectory"]["sha256"]:
        raise ValueError(f"Trajectory hash mismatch: {source}")
    original = json.loads(gzip.decompress(raw) if source.suffix == ".gz" else raw)
    if not original.get("steps"):
        raise ValueError("Archive trajectory has no steps")
    if (original.get("extra") or {}).get("archive_context_view"):
        raise ValueError("Refusing to enrich an already enriched display copy")
    result = copy.deepcopy(original)
    cards = []

    def card(message, **metadata):
        cards.append({
            "step_id": len(cards) + 1, "source": "system", "message": message,
            "extra": {"display_only": True, "kind": "archived_prompt_context", **metadata},
        })

    card(
        "# 归档补充上下文 · 非原始对话事件\n\n"
        f"归档：{manifest['archive']}\n\n"
        "这是查看副本，不是新 rollout；Viewer 显示的配置生成日期不是原运行时间。"
        "费用字段沿用历史导出值，不等于已核实账单。\n\n"
        "以下卡片来自保存的阶段提示词快照，按原始 job / trial / stage 分组；"
        "卡片顺序不是运行时间线，不能据此推断消息发送时点。"
        "原始对话从“原始轨迹开始”之后显示。\n\n"
        "role.md 是运行器保存的阶段职责提示词，不包含 CLI 内置 system prompt，"
        "也不是完整供应商请求。未记录的 AGENTS.md、输入版本或子会话不会被补造。\n\n"
        f"原始对话步数：{len(original['steps'])}；原始计费和 token 指标保持不变，"
        "补充卡片不代表模型调用。\n\n"
        f"轨迹 SHA-256：{digest(raw)}"
    )
    for run in manifest["rollouts"]:
        job, trial = run["source_job"], run["source_trial"]
        recovery = run.get("recovery_source")
        for stage in run["stages"]:
            stage_id = stage["stage_id"]
            inherited = stage.get("identical_snapshot_in_recovery_source", False)
            missing = stage.get("missing_snapshot_files", [])
            source_run = f"{recovery['job']} / {recovery['trial']}" if recovery else "无直接恢复来源"
            present = stage.get("session_present_in_published_trajectory_metadata")
            presence = {True: "是（仅核对会话身份，不证明全部消息已导出）", False: "否", None: "无法确认"}[present]
            message = (
                f"# 阶段快照 · {job} / {trial}\n\n"
                f"阶段：{stage_id}；角色：{stage.get('role')}；记录状态：{stage.get('recorded_status')}\n\n"
                f"继承快照：{'是，不能计作本次重新执行' if inherited else '未匹配到直接恢复来源中的相同完整快照'}\n\n"
                f"恢复来源：{source_run}\n\n"
                f"原生会话：{stage.get('session_id') or '未记录'}\n\n"
                f"会话出现在此归档的轨迹元数据中：{presence}\n\n"
                f"提示词注入方式：{stage.get('system_prompt_transport') or '缺少原生证据，无法确认'}\n\n"
                f"缺失快照文件：{', '.join(missing) if missing else '无'}\n\n"
            )
            file_records = []
            for entry in stage["files"]:
                path = contained(bundle, entry["path"])
                data = path.read_bytes()
                if digest(data) != entry["export_sha256"]:
                    raise ValueError(f"Snapshot hash mismatch: {path}")
                if path.name not in {"role.md", "instruction.md", "native-evidence.json"}:
                    raise ValueError(f"Unexpected snapshot file: {path.name}")
                message += (
                    f"## {path.name}\n\n"
                    f"来源：{entry['path']}\n\n"
                    f"原件 SHA-256：{entry['source_sha256']}\n\n"
                    f"归档 SHA-256：{entry['export_sha256']}\n\n"
                    f"{fenced(data.decode('utf-8'))}\n\n"
                )
                file_records.append(copy.deepcopy(entry))
            card(message, source_job=job, source_trial=trial, stage_id=stage_id,
                 inherited_snapshot=inherited, recovery_source=recovery,
                 missing_snapshot_files=missing, snapshot_files=file_records)
    card("# 原始轨迹开始\n\n以下为归档中的原始对话与工具记录。仅顺延展示编号；"
         "原始编号保存在每步 extra.archive_original_step_id，时间戳、消息、工具返回、"
         "子会话标记及用量指标不变。前面的补充卡片不表示实际发送顺序。")
    offset = len(cards)
    for step in result["steps"]:
        original_id = step["step_id"]
        step["step_id"] = original_id + offset
        step["extra"] = {**(step.get("extra") or {}), "archive_original_step_id": original_id}
    result["steps"] = cards + result["steps"]
    result["notes"] = (result.get("notes") or "") + (
        "\nDisplay-only archived prompt context has been prepended. "
        "These supplemental system cards are not original conversation events. "
        "Original metrics exclude supplemental cards."
    )
    result["extra"] = {
        **(result.get("extra") or {}),
        "archive_context_view": {
            "format": MARKER, "archive": manifest["archive"],
            "source_sha256": digest(raw), "manifest_sha256": digest(manifest_path.read_bytes()),
            "supplemental_steps": offset, "original_steps": len(original["steps"]),
            "display_steps": len(result["steps"]),
        },
    }
    return result, manifest


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def prepare(jobs, output):
    jobs, output = Path(jobs).resolve(), Path(output).resolve()
    if output.is_relative_to(jobs) or jobs.is_relative_to(output):
        raise ValueError("Display output must be separate from the source jobs tree")
    if output.exists():
        raise ValueError(f"Output already exists; choose a fresh directory: {output}")
    manifests = sorted(jobs.glob("**/prompt-snapshots/manifest.json"))
    if not manifests:
        raise ValueError(f"No archived prompt manifests found under {jobs}")
    # Verify all source bytes before creating any output directory.
    documents = [(m, *display_trajectory(m)) for m in manifests]
    output.parent.mkdir(parents=True, exist_ok=True)
    index = []
    with tempfile.TemporaryDirectory(prefix=".viewer-context-", dir=output.parent) as temporary:
        staging = Path(temporary) / "jobs"
        staging.mkdir()
        for manifest_path, trajectory, manifest in documents:
            archive_id = manifest["archive"]
            suffix = hashlib.sha256(archive_id.encode()).hexdigest()[:8]
            slug = re.sub(r"[^a-zA-Z0-9_-]+", "--", archive_id)
            name = f"context--{slug}--{suffix}"
            trial_name = "archive-view"
            folder = staging / name
            task = {"path": f"archive-context/{slug}", "source": "display-only-archive"}
            agent = {"name": "claude-code", "model_name": trajectory["agent"].get("model_name")}
            job_id = str(uuid5(NAMESPACE_URL, "sdlc-context:" + archive_id))
            write_json(folder / "config.json", {
                "job_name": name, "tasks": [task], "agents": [agent],
            })
            write_json(folder / trial_name / "config.json", {
                "trial_name": trial_name, "task": task, "agent": agent, "job_id": job_id,
            })
            write_json(folder / trial_name / "agent/trajectory.json", trajectory)
            write_json(folder / trial_name / "context-source.json", manifest)
            (folder / "README.md").write_text(
                "# 归档展示副本 · 未执行新 rollout\n\n"
                f"来源归档：{archive_id}\n\n"
                "此目录只供 Harbor Viewer 读取，不代表新的运行或评测。"
                "config.json 是用于发现归档的展示配置，不是历史执行配置。"
                "没有生成 result.json，不伪造成功、奖励或计费。"
                "界面若显示 pending/running，仅表示该展示目录没有执行结果，不代表任务在运行。\n"
            )
            index.append({"archive": archive_id, "viewer_job": name,
                          "viewer_trial": trial_name,
                          "rollouts": [{"job": r["source_job"], "trial": r["source_trial"]}
                                       for r in manifest["rollouts"]],
                          **trajectory["extra"]["archive_context_view"]})
        write_json(staging / "context-views.json", {"format": MARKER, "views": index})
        (staging / "README.md").write_text(
            "# Harbor 归档上下文展示\n\n"
            "这是查看用副本，不是新 rollout。原始归档和轨迹未改写。\n\n"
            "在解压后的目录运行 `harbor view . --host 127.0.0.1`，"
            "选择 context-- 开头的归档和 archive-view，再进入 Trajectory。"
            "先显示标明来源与继承关系的补充 system 卡片，再显示原始对话。\n\n"
            "这些卡片不是当时发送消息的事件记录，也不包含未保存的 CLI 内置提示词、"
            "AGENTS.md 或全部子会话。没有生成运行结果；界面 pending/running 不表示新任务正在执行。\n"
        )
        shutil.move(str(staging), str(output))
    return index


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs", type=Path, default=Path("jobs"))
    parser.add_argument("--output", type=Path, required=True,
                        help="New display-only jobs directory; must not already exist")
    args = parser.parse_args()
    try:
        index = prepare(args.jobs, args.output)
    except (ValueError, OSError, KeyError) as error:
        parser.exit(1, f"Cannot prepare viewer context: {error}\n")
    print(f"Prepared {len(index)} archive views at {args.output}")
    print(f"harbor view {args.output} --host 127.0.0.1")


if __name__ == "__main__":
    main()
