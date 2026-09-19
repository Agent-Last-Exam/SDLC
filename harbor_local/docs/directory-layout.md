# 目录整理记录：2026-09-18

以下记录历次目录变更；当前入口与目录以 task README 为准。对既有业务产物、原生会话、trial 状态、冻结输入不做修改。

| 原路径（相对 harbor_local） | 新路径 |
| --- | --- |
| run_workflow.py、prepare_workflow.py、prepare_sources.py、workflow_*.py、codex_app_turn.py、agents.py | runtime/ 下同名文件 |
| test_*.py | runtime/tests/ 下同名文件 |
| workflows/ | spec/workflows/ |
| prompts/pm.system.md、architect.system.md | spec/roles/ |
| templates/、inputs/、organization-delivery.md | spec/ 下同名路径 |
| design/ | docs/ |
| run.py、configs/、prompts/system.md | legacy/run.py、legacy/configs/、legacy/system.md |
| *verification.json | reports/checks/ 下同名文件 |
| requirements-workflow.txt | requirements.txt |
| .prepared/、jobs/、tasks/ | 保持原位 |

新入口为 `python -m harbor_local`。内部模块使用 `harbor_local.runtime.*`；测试使用 `harbor_local.runtime.tests.*`；当时保留的旧单轮入口现已删除。

旧命令 `python -m harbor_local.run_workflow` 和旧 Python import 路径不再作为当前入口。历史 recipe / traceback / 冻结文档中的旧路径保留为历史事实，不批量重写。新入口生成的新 recipe 使用新的 import_path。

所有公开资源位置经运行器显式解析；Agent 容器内的 `/workspace` 路径、输入输出契约不变。README 和可执行 YAML 引用已更新。

验收：完整单元测试、三个模式配置解析、旧入口的无执行参数检查、新目录下 Single 无模型容器联调、自动 report 和文档本地链接检查。具体结果见 [目录整理验收](../reports/checks/layout-verification.json)。

## 后续修正：按 task 闭环

上表记录首次迁移；之后已将全局 spec/ 撤销，所有 Saleor 任务定义归到 tasks/saleor-prd-tdd/：

| 原路径 | 当前路径 |
| --- | --- |
| spec/inputs/saleor-instruction.md | tasks/saleor-prd-tdd/instruction.md |
| spec/workflows/、roles/、templates/、organization-delivery.md | tasks/saleor-prd-tdd/ 下同名路径 |
| 原任务 instruction.md、task.toml、environment/Dockerfile、check_environment.py | tasks/saleor-prd-tdd/legacy/ 下同名文件 |
| runtime 内嵌的 task.toml 与 Dockerfile | tasks/saleor-prd-tdd/task.toml 与 environment/Dockerfile |

现在由 --task/--mode 选择任务；任务配置和 Dockerfile 也冻结后使用。旧 jobs/ 与 .prepared/ 不改写。两个用户优化后的角色 SP 按字节保留，容器路径不变。入口与配置导航见 [task README](../tasks/saleor-prd-tdd/README.md)。

本次 task 归属修正验证见 [task-ownership-verification.json](../reports/checks/task-ownership-verification.json)：37 项测试、三模式解析、迁移 task 独立准备、SP 原文与冻结字节核对、旧入口参数检查及 Single 无模型容器联调通过。

## 删除旧单轮入口

已删除 harbor_local/legacy/ 和 tasks/saleor-prd-tdd/legacy/，包括旧启动器、配置、联合 prompt、旧 task.toml、Instruction、Dockerfile 和健康检查。当前唯一启动入口为 `python -m harbor_local`。上文迁移表及旧验收记录描述当时状态，不代表旧入口仍可使用。

历史 jobs/、.prepared/ 与 reports/checks/ 作为运行证据保留；当前工作流不依赖被删除的文件。
