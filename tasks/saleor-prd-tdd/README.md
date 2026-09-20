# Saleor：Instruction → PRD → 技术设计

这个目录是一个完整的任务定义。业务输入、sprint/stage 编排、输入输出、角色、模板和环境配置都归本 task 所有；不依赖全局 spec/。runtime/ 提供执行机制。

## 从哪里改

| 路径 | 职责 |
| --- | --- |
| [instruction.md](instruction.md) | 本次 Saleor 业务目标与交付范围 |
| [workflows/design-delivery.yaml](workflows/design-delivery.yaml) | sprint/stage 顺序、角色、Input/Output 引用、最终产物和停止点 |
| [workflows/single.yaml](workflows/single.yaml)、[flat.yaml](workflows/flat.yaml)、[hierarchical.yaml](workflows/hierarchical.yaml) | 本 task 的三种模式配置；通过 task_root 指回本目录，共用交付契约 |
| [roles/](roles/README.md) | PM、架构师、QA 测试设计、开发、部署、QA 测试执行的角色与交接定义 |
| [templates/](templates/README.md) | PRD、技术设计、测试用例、提测报告和 QA 结果模板 |
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

启动时，运行器冻结公开输入至 `.prepared/<job>/workspace/`；将 task.toml 与 Dockerfile 冻结到 runtime-inputs/，据此组装 task/ 和 job.json。容器中的 instruction.md、roles/、templates/、repos/ 都在 `/workspace` 下。

PM 写入 `/workspace/artifacts/sprint1/prd/prd.md`。技术阶段以 `artifact:sprint1/prd/prd` 引用同一份已封存文件；输出写入 `/workspace/artifacts/sprint1/tech-design/`。两个角色的 System Prompt 用自然的职业描述说明工作、材料和交付位置。

不再单独提供 organization-delivery.md，也不要求架构师自审或生成 review.md。角色 System Prompt 说明身份、工作、材料与交付位置；模板定义字段和格式。运行器根据 workflows/design-delivery.yaml 执行阶段编排，并附加本次材料与交付文件的路径列表。角色不会收到完整配置 JSON、版本核验任务或控制器说明。Controller、目录权限和结构门禁执行交接约束。修改契约时同步相关角色指令和模板。

当前可执行配置仍只有 sprint1 的 PRD 和技术设计两个 stage。已补齐后续四份角色 Prompt 与产物模板，交接顺序是 QA 先设计用例 → 开发并写提测报告 → 部署并更新同一份提测报告 → QA 执行测试并输出 CSV、报告和 JSON。具体路径和 QA 失败后的返工交接见 [角色说明](roles/README.md)。

这些新增阶段和返工循环尚未接入执行后端。sprint 数量和编排归任务配置所有；运行器还需支持代码修改、提测报告的跨阶段更新、测试环境生命周期和 QA 结果分支，不能只加 YAML 就运行。

改过角色、模板或业务输入后开新 run；历史 jobs/ 与 .prepared/ 保留当时的版本。结果见 [运行记录说明](../../docs/rollout-records.md)，不会写回 task 的输入目录。
