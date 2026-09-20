"""Explicit synthetic executor used only by --smoke; never a business deliverable."""
from pathlib import Path
import csv
import json
import shlex
import shutil
import tempfile

from runtime.workflow_agent import HarborBackend

SMOKE_SERVER = '''from http.server import SimpleHTTPRequestHandler, HTTPServer
from multiprocessing import shared_memory
from pathlib import Path
import uuid
token = uuid.uuid4().hex
resources = [Path('/tmp') / token, Path('/var/tmp') / token]
for path in resources:
    path.write_text('service-alive')
shm = shared_memory.SharedMemory(create=True, size=16)
shm.buf[:5] = b'alive'
class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        try:
            assert all(p.read_text() == 'service-alive' for p in resources)
            attached = shared_memory.SharedMemory(name=shm.name)
            assert bytes(attached.buf[:5]) == b'alive'
            attached.close()
        except Exception:
            self.send_error(503, 'Service temporary resources lost')
            return
        super().do_GET()
HTTPServer(('127.0.0.1', 8765), Handler).serve_forever()
'''


def write_fixture(directory, role, workspace):
    directory.mkdir(parents=True, exist_ok=True)
    if role == "pm":
        (directory / "prd.md").write_text("""# PRD：SYNTHETIC SMOKE ONLY
版本：v1
责任：产品
状态：仅用于验证运行器
## 1. 业务背景与目标
这是人工编写的合成样本，不是模型生成的产品需求。
## 2. 用户与场景
运行器测试。
## 3. 需求条目
### R01 · 检查交接
- 来源：合成测试输入
- 优先级：P0
- 需求描述：验证阶段交接。
- 验收条件：
  - AC-01-1：技术设计收到同一 PRD。
## 4. 范围与非目标
仅运行器测试。
## 5. 其他
无业务有效性声明。
""")
        return
    (directory / "frontend-design.md").write_text("""# 前端技术设计：SYNTHETIC SMOKE ONLY
版本：v1
责任：前端技术设计
依据：PRD v1
## 1. 方案概述
合成测试。
## 2. 需求覆盖
| 需求 | 设计单元 |
| --- | --- |
| R01 | FD01 |
## 3. 详细设计
### FD01 · 交接
- 覆盖需求：R01
- 设计说明：合成测试。
## 4. 依赖与联调
I01 由 FD01 消费；仅测试引用闭包。
## 5. 其他
无业务有效性声明。
""")
    (directory / "backend-design.md").write_text("""# 后端技术设计：SYNTHETIC SMOKE ONLY
版本：v1
责任：后端技术设计
依据：PRD v1
## 1. 方案概述
合成测试，完整 schema 直接保留 Base。
## 2. 需求覆盖
R01 由 BD01 覆盖。
## 3. 详细设计
### BD01 · 交接
- 覆盖需求：R01
- 设计说明：合成测试。
## 4. 接口清单
I01 属于 BD01。
## 5. 工程任务与依赖
### BT01 · 验证
- 覆盖设计单元：BD01
- 依赖：无
- 工作与验证：检查运行器。
## 6. 其他
无业务有效性声明。
""")
    (directory / "interface-contract.md").write_text("""# 接口对齐文档：SYNTHETIC SMOKE ONLY
版本：v1
责任：后端技术设计
依据：后端技术设计 v1
## 1. 通用约定
只验证公开结构。
## 2. 接口契约
### I01 · 交接
- 所属设计单元：BD01
- 提供方：Base Saleor
- 调用方：FD01
- 目标定义：target-schema.graphql 的 Query
- 字段说明：沿用 Base。
- 权限：沿用 Base。
- 错误：沿用 Base。
- 完成判定：合成样本，不作业务承诺。
- 变更与兼容：无变化。
## 3. 其他
非正式技术设计。
""")
    shutil.copyfile(workspace / "repos/saleor/saleor/graphql/schema.graphql", directory / "target-schema.graphql")


class SmokeBackend(HarborBackend):
    synthetic = True

    def __init__(self, real, scenario="repair"):
        super().__init__(real.agent, real.environment, real.context, real.workspace)
        self.scenario = scenario

    async def execute(self, stage, prompt, instruction, resume_session, stage_dir):
        # Upload fixture only in explicitly synthetic trials. The real backend
        # never copies these examples into the Agent environment.
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp)
            write_stage_fixture(source, stage, self.workspace, self.scenario)
            for path in source.iterdir():
                await self.environment.upload_file(path, stage["writable_directory"] + "/" + path.name)
        if stage["role"] == "developer":
            result = await self.environment.exec(
                "python3 -c " + shlex.quote("from pathlib import Path; Path('/workspace/repos/smoke-version.txt').write_text(" + repr(str(stage["round"])) + "); Path('/workspace/repos/smoke-server.py').write_text(" + repr(SMOKE_SERVER) + ")"),
                user=self.user)
            if result.return_code:
                raise RuntimeError("Development cannot write candidate")
        if stage["role"] == "deployer":
            await self.root("chmod 600 " + shlex.quote(stage["writable_directory"] + "/deployment.json"))
            result = await self.environment.exec("touch /tmp/sdlc-retired-stage /dev/shm/sdlc-retired-stage", user=self.user)
            if result.return_code:
                raise RuntimeError("Cannot create retired stage resources")
        if stage["role"] == "qa":
            result = await self.environment.exec("curl --fail --silent http://127.0.0.1:8765/smoke-built-version.txt", user=self.user)
            if result.return_code or result.stdout.strip() != str(stage["round"]):
                raise RuntimeError("QA did not reach the current deployed candidate across the stage boundary")
            await self.root("test ! -e /tmp/sdlc-retired-stage; test ! -e /dev/shm/sdlc-retired-stage")
            (stage_dir / "smoke-service-evidence.json").write_text(json.dumps({"round": stage["round"], "observed_version": result.stdout.strip(), "service_temp_and_shm_survived": True, "retired_stage_temp_removed": True, "synthetic": True}))
        # Start a leftover process; quiesce must remove it at the boundary.
        result = await self.environment.exec("nohup sleep 300 >/dev/null 2>&1 &", user=self.user)
        if result.return_code:
            raise RuntimeError("Could not start smoke boundary probe")
        return resume_session or f"synthetic-session-{self.stage_index}"


def write_stage_fixture(directory, stage, workspace, scenario="repair"):
    """Synthetic branch fixtures; real workflow never exposes these to the Agent."""
    role, number = stage["role"], stage.get("round", 1)
    if role in {"pm", "architect"}:
        return write_fixture(directory, role, workspace)
    CASE_COLUMNS = ['用例编号', '一级模块', '二级模块', '用例标题', '覆盖', '优先级', '前置条件', '操作步骤', '预期结果']
    RESULT_COLUMNS = ['用例编号', '结果', '实际结果', '证据', '缺陷编号']
    directory.mkdir(parents=True, exist_ok=True)
    def csv_file(name, columns, rows):
        with (directory / name).open('w', newline='') as stream:
            writer = csv.writer(stream)
            writer.writerow(columns)
            writer.writerows(rows)
    if role == "qa-design":
        csv_file(f"test-cases.v{number}.csv", CASE_COLUMNS,
                 [["TC001", "运行器测试", "R01 · 检查交接", "SYNTHETIC 交接", "AC-01-1", "P0", "本地环境", "1. 请求版本", "1. 返回本轮版本"]])
    elif role in {"developer", "deployer"}:
        (directory / "test-handoff.md").write_text(f"""# 提测报告：SYNTHETIC
版本：v{number}
轮次：{number}
## 1. 提测版本
合成版本 {number}，repos/smoke-version.txt。
## 2. 已完成功能
R01 · 检查交接
## 3. 未完成项与已知问题
无业务有效性声明。
## 4. 测试环境与验证方式
- 部署状态：{'待部署' if role == 'developer' else '已部署'}
- 部署版本：synthetic-{number}
- 环境入口：http://127.0.0.1:8765/smoke-version.txt
- 访问方式：本容器
- 验证方式：HTTP GET
- 环境限制：SYNTHETIC
""")
        if role == "deployer":
            (directory / "deployment.json").write_text(json.dumps({"prepare": [{"argv": ["cp", "smoke-version.txt", "smoke-built-version.txt"], "cwd": "/workspace/deployment/repos"}], "services": [{"name": "smoke", "argv": ["python3", "smoke-server.py"], "cwd": "/workspace/deployment/repos"}], "healthchecks": ["http://127.0.0.1:8765/smoke-built-version.txt"]}))
    elif role == "triage":
        changed = scenario != "repair-reuse"
        (directory / "repair-plan.json").write_text(json.dumps({"round": 2, "design_changed": changed,
                                                               "defects": ["D01"], "summary": "SYNTHETIC 修复计划"}))
    elif role == "qa":
        verdict = "pass" if scenario == "pass" or (number == 2 and scenario != "fail") else "fail"
        csv_file(f"test-results.{number}.csv", RESULT_COLUMNS,
                 [["TC001", "通过" if verdict == "pass" else "失败", "SYNTHETIC 执行结果", "合成测试证据", "" if verdict == "pass" else "D01"]])
        (directory / f"test-report.{number}.md").write_text(f"""# 测试报告：SYNTHETIC
版本：v{number}
轮次：{number}
## 1. 结论
结论：{verdict}
TC001 合成结论。
## 2. 需求验收情况
R01 / TC001
## 3. 缺陷
""" + ("无\n" if verdict == "pass" else "### D01 · 合成缺陷\nTC001 / R01 / AC-01-1：仅验证失败分支。\n") + "## 4. 其他\n非真实业务测试。\n")
        (directory / "test-verify.json").write_text(json.dumps({"round": number, "verdict": verdict}))
