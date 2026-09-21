# Saleor：Single Agent SDLC

这个目录是一个完整的任务定义。业务输入、sprint/stage 编排、输入输出、角色、模板和环境配置都归本 task 所有；不依赖全局 spec/。runtime/ 提供执行机制。

## 从哪里改

| 路径 | 职责 |
| --- | --- |
| [instruction.md](instruction.md) | 本次 Saleor 业务目标与交付范围 |
| [workflows/lifecycle.yaml](workflows/lifecycle.yaml) | Single 首次交付和有界修复 Sprint |
| [workflows/single.yaml](workflows/single.yaml)、[flat.yaml](workflows/flat.yaml)、[hierarchical.yaml](workflows/hierarchical.yaml) | 模式配置，通过 task_root 指回本目录；都引用 lifecycle.yaml；Single 可执行，Flat/Hierarchical 仅声明 |
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

Flat/Hierarchical 的新契约配置可校验，执行后端尚未实现，启动器明确拒绝。省略 --task/--mode 时默认本 task 的 single。也可用 --config 指向本 task 的模式 YAML，但不能同时传 --task/--mode。

只生成可运行的 Harbor task、冻结输入与 job.json，不调用模型或启动容器：

```bash
/Users/zhihu/.local/share/uv/tools/harbor/bin/python -m runtime \
  --task tasks/saleor-prd-tdd --mode single --prepare-only
```

必须经过准备入口。environment/Dockerfile 的 COPY workspace/ 指向生成后的构建上下文，不能直接把源码目录作为已准备的 Harbor task 运行。

## 配置如何交接

启动时，运行器冻结公开输入至 `.prepared/<job>/workspace/`；将 task.toml 与 Dockerfile 冻结到 runtime-inputs/，据此组装 task/ 和 job.json。容器中的 instruction.md、roles/、templates/、repos/ 都在 `/workspace` 下。

PM 写入 `/workspace/artifacts/sprint1/prd/prd.md`。技术阶段以 `artifact:sprint1/prd/prd` 引用同一份已封存文件；输出写入 `/workspace/artifacts/sprint1/tech-design/`。两个角色的 System Prompt 用自然的职业描述说明工作、材料和交付位置。

不再单独提供 organization-delivery.md，也不要求架构师自审或生成 review.md。角色 System Prompt 说明身份、工作、材料与交付位置；模板定义字段和格式。运行器根据所选 workflow 契约 执行阶段编排，并附加本次材料与交付文件的路径列表。角色不会收到完整配置 JSON、版本核验任务或控制器说明。Controller 和目录权限保证顺序推进及产物封存；不对文档内容设置门禁，也不自动补交。修改契约时同步相关角色指令和模板。

默认 `single.yaml` 使用 `lifecycle.yaml`：首次六阶段交付，QA 失败后进入研判、按需更新设计、修复、部署和复测；测试用例沿用第一轮。第二轮失败停止。完整行为见 [Single 流程](../../docs/single-agent-lifecycle.md)。

改过角色、模板或业务输入后开新 run；历史 jobs/ 与 .prepared/ 保留当时的版本。结果见 [运行记录说明](../../docs/rollout-records.md)，不会写回 task 的输入目录。
