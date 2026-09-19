# 任务定义与环境

[saleor-prd-tdd/environment/base-revisions.json](saleor-prd-tdd/environment/base-revisions.json) 固定三仓 Base：

| 仓库 | Commit |
| --- | --- |
| saleor 3.22.0 | 6cfb77430ddbc53f48dfd3462fbefaad4e8c3d45 |
| saleor-dashboard 3.22.2 | 59e600df5fa8bc9cc875bb7beaeca43a2549d2d5 |
| saleor-platform | 8330f42e5673fe0c4fd4a445d6789bd257cc9265 |

源码在 environment/repos/，由 `python3 -m harbor_local.runtime.prepare_sources` 精确获取。目录中的 Base Git 仓库保持干净，不放 Agent 输出。新 workflow 用 git archive 创建无历史的独立源码快照，放进每个 job 的冻结 workspace。

[saleor-prd-tdd/](saleor-prd-tdd/README.md) 自包含业务 Instruction、阶段 Input/Output、sprint/stage 编排、三种运行模式、角色 SP、模板、共同交付规范、task.toml 与 Dockerfile。没有全局 Saleor spec。

新入口用 `--task harbor_local/tasks/saleor-prd-tdd --mode single` 选择任务及模式。新增任务时在 tasks/ 下建立同级目录；任务配置不需要放进公共 runtime。运行器当前能力限于 PRD → 技术设计/自审，其他阶段后端尚未实现。

此处只准备代码分析环境，未安装完整 Saleor 业务依赖，也未启动 API、Dashboard、数据库或 Worker。Agent 可见路径为 `/workspace/repos/<repo>`。
