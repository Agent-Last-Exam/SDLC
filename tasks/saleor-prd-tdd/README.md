# Saleor：Instruction → PRD → 技术设计与自审

这个目录是一个完整的任务定义。业务输入、sprint/stage 编排、输入输出、角色、模板和环境配置都归本 task 所有；不依赖全局 spec/。runtime/ 提供执行机制。

## 从哪里改

| 路径 | 职责 |
| --- | --- |
| [instruction.md](instruction.md) | 本次 Saleor 业务目标与交付范围 |
| [workflows/design-delivery.yaml](workflows/design-delivery.yaml) | sprint/stage 顺序、角色、Input/Output 引用、最终产物和停止点 |
| [workflows/single.yaml](workflows/single.yaml)、[flat.yaml](workflows/flat.yaml)、[hierarchical.yaml](workflows/hierarchical.yaml) | 本 task 的三种模式配置；通过 task_root 指回本目录，共用交付契约 |
| [roles/](roles/README.md) | 本 task 的 PM、研发负责人角色 SP，允许包含本 task 的具体路径 |
| [templates/](templates/) | PRD、前后端技术设计、接口契约、目标接口、技术自审模板 |
| [organization-delivery.md](organization-delivery.md) | 供本 task 所有角色读取的共同交付规范 |
| [task.toml](task.toml) | Harbor 运行超时、网络与资源配置；启动器直接冻结并使用 |
| [environment/Dockerfile](environment/Dockerfile) | 本 task 的容器构建定义；workspace/ 由准备器提供 |
| [environment/base-revisions.json](environment/base-revisions.json)、environment/repos/ | 精确 Base 版本和源码 |

## 执行

在 仓库根目录执行：

```bash
/Users/zhihu/.local/share/uv/tools/harbor/bin/python -m runtime \
  --task tasks/saleor-prd-tdd --mode single --use-local-codex-auth
```

将 single 改为 flat 即每阶段新会话。hierarchical 的配置可校验，Lead 后端尚未实现。省略 --task/--mode 时默认本 task 的 single。也可用 --config 指向本 task 的模式 YAML，但不能同时传 --task/--mode。

只生成可运行的 Harbor task、冻结输入与 job.json，不调用模型或启动容器：

```bash
/Users/zhihu/.local/share/uv/tools/harbor/bin/python -m runtime \
  --task tasks/saleor-prd-tdd --mode single --prepare-only
```

必须经过准备入口。environment/Dockerfile 的 COPY workspace/ 指向生成后的构建上下文，不能直接把源码目录作为已准备的 Harbor task 运行。

## 配置如何交接

启动时，运行器冻结公开输入至 `.prepared/<job>/workspace/`；将 task.toml 与 Dockerfile 冻结到 runtime-inputs/，据此组装 task/ 和 job.json。容器中的 instruction.md、organization-delivery.md、roles/、templates/、repos/ 都在 `/workspace` 下。

PM 写入 `/workspace/artifacts/sprint1/prd/prd.md`。技术阶段以 `artifact:sprint1/prd/prd` 引用同一份已封存文件；输出写入 `/workspace/artifacts/sprint1/tech-design/`。目录搬迁不改变容器路径，因此两个优化后的角色 SP 正文无需改写。

organization-delivery.md 是共同阅读的规范，解释 ID 引用、文件格式、交接、自审与 blocked 含义；不直接控制运行。可执行的 stage 输入输出和停止点以 workflows/design-delivery.yaml 为准，强制约束由 Controller、目录权限和结构门禁执行。修改交付契约时同步修改规范、模板及涉及的角色路径。

本 task 目前只有 sprint1 的 PRD 和技术设计两个 stage。sprint 数量和编排归任务配置所有；执行后端目前只支持这两个文档阶段，新增 Code/QA/Deploy 仍需实现对应能力，不能只加 YAML 就运行。

改过角色、模板或业务输入后开新 run；历史 jobs/ 与 .prepared/ 保留当时的版本。结果见 [运行记录说明](../../docs/rollout-records.md)，不会写回 task 的输入目录。
