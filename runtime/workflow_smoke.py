"""Explicit synthetic executor used only by --smoke; never a business deliverable."""
from pathlib import Path
import shutil
import tempfile

from runtime.workflow_agent import HarborBackend


def write_fixture(directory, role, workspace, outcome="pass"):
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
    (directory / "review.md").write_text(f"""# 技术评审：SYNTHETIC SMOKE ONLY
版本：v1
责任：架构师自审
评审方式：合成执行器，无模型
结论：{outcome}
依据：PRD v1；前端 v1；后端 v1；接口 v1
## 1. 评审对象
全部合成产物。
## 2. 需求与设计覆盖
R01 由 FD01、BD01、I01 覆盖。
## 3. 接口与工程一致性
仅用于验证运行器门禁。
## 4. 问题与处置
{'没有合成阻塞问题。' if outcome == 'pass' else '测试 blocked 停止，不允许进入后续阶段。'}
## 5. 结论与交接
这不是实际 PRD/TDD，不证明模型或业务质量。
""")
    shutil.copyfile(workspace / "repos/saleor/saleor/graphql/schema.graphql", directory / "target-schema.graphql")


class SmokeBackend(HarborBackend):
    synthetic = True

    def __init__(self, real):
        super().__init__(real.agent, real.environment, real.context, real.workspace)

    async def execute(self, stage, prompt, instruction, resume_session, attempt_dir):
        # Upload fixture only in explicitly synthetic trials. The real backend
        # never copies these examples into the Agent environment.
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp)
            write_fixture(source, stage["role"], self.workspace)
            for path in source.iterdir():
                await self.environment.upload_file(path, stage["writable_directory"] + "/" + path.name)
        # Start a leftover process; quiesce must remove it at the boundary.
        result = await self.environment.exec("nohup sleep 300 >/dev/null 2>&1 &", user=self.user)
        if result.return_code:
            raise RuntimeError("Could not start smoke boundary probe")
        return resume_session or f"synthetic-session-{self.stage_index}"
