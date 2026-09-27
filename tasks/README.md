# 任务定义与环境

[saleor-prd-tdd/environment/base-revisions.json](saleor-prd-tdd/environment/base-revisions.json) 固定三仓 Base：

| 仓库 | Commit |
| --- | --- |
| saleor 3.22.0 | 6cfb77430ddbc53f48dfd3462fbefaad4e8c3d45 |
| saleor-dashboard 3.22.2 | 59e600df5fa8bc9cc875bb7beaeca43a2549d2d5 |
| saleor-platform | 8330f42e5673fe0c4fd4a445d6789bd257cc9265 |

## 已冻结的 Harbor 任务

- [standard/](standard/README.md)：2026-09-20 的历史 Saleor 3.23 标准任务。
- [saleor-3.23-pruned/](saleor-3.23-pruned/README.md)：剪枝后的正式 Golden Harbor，release ID 为 `saleor-3.23-pruned-20260927-01`；Base 使用 architecture-upgraded environment 与最终 test patch，Target 在同一测试树上增加最终 code patch，冻结选择为 F2P 5,365、P2P 15,013。

源码在 environment/repos/，由 `python3 -m runtime.prepare_sources --task tasks/<task>` 精确获取。目录中的 Base Git 仓库保持干净，不放 Agent 输出。新 workflow 用 git archive 创建无历史的独立源码快照，放进每个 job 的冻结 workspace。

已有 Harbor task 可以智能复制现有 Single workflow；业务 instruction、原 task.toml 和原 Dockerfile 不会被覆盖：

```bash
python3 -m runtime.scaffold_workflow tasks/<task> --update-manifest
```

复制器会复用角色、模板和两轮 lifecycle；若目标是带预构建镜像的冻结评测包，则在 task 内生成独立的 `workflow-runtime/`，避免改变原 empty/gold/verifier 入口。若目标没有 `base-revisions.json`，复制器会尝试从标准测试配置推导 Base 仓库和 SHA。

[saleor-prd-tdd/](saleor-prd-tdd/README.md) 自包含业务 Instruction、阶段 Input/Output、sprint/stage 编排、三种运行模式、角色 SP、模板、共同交付规范、task.toml 与 Dockerfile。没有全局 Saleor spec。

新入口用 `--task tasks/saleor-prd-tdd --mode single` 选择任务及模式。新增任务时在 tasks/ 下建立同级目录；任务配置不需要放进公共 runtime。运行器当前能力限于 PRD → 技术设计/自审，其他阶段后端尚未实现。

此处只准备代码分析环境，未安装完整 Saleor 业务依赖，也未启动 API、Dashboard、数据库或 Worker。Agent 可见路径为 `/workspace/repos/<repo>`。
