# 执行代码

面向使用者的入口是仓库根目录执行 `python -m runtime`。这里只放实现，不放业务 prompt、实验结果或历史报告。

| 文件 | 职责 |
| --- | --- |
| run_workflow.py | 解析参数、冻结输入、创建 Harbor job、回收结果并生成 report.md |
| prepare_workflow.py | 解析 task 配置、校验依赖与 Base SHA、生成 Agent workspace |
| prepare_sources.py | 按 `--task` 精确获取并校验 Base；不复制工作树改动 |
| workflow_controller.py | 阶段游标、Single/Flat 主会话策略、单次执行、封存、QA 分支与终止 |
| hierarchical_controller.py | 持续 Lead 循环、结构化动作执行和并发成员调度 |
| team_protocol.py / team_broker.py | 动作协议、团队状态、写域、不可变 revision、stale 与闭包规则 |
| team_workspace.py | Hierarchical 独立代码副本的内容 diff、冲突检查和受控集成 |
| workflow_agent.py | Harbor/Claude Code 适配、固定身份与会话隔离、日志回收 |
| reporting.py | 从主机证据生成每个 job 的 report.md 和 jobs/README.md |
| trajectory.py | 导出 Single、Flat 或 Lead+成员嵌套 ATIF，供 Harbor Viewer 读取 |
| workflow_smoke.py | 明确标记 SYNTHETIC 的无模型容器联调 |
| agents.py | Claude Code system prompt 注入适配器 |
| environment.py | 按字面量读取本机 .env，不执行 shell |
| agent_cost.py | 从 Agent result 事件读取已花费成本，供执行中预算检查与事后报告共用 |
| defaults/ | 角色、模板与唯一的交付契约 |

`prepare_workflow.HERE` 指向 仓库根目录，不依赖 shell 当前目录推算资源位置；用户传入的相对路径仍相对调用目录。角色、模板与交付契约位于 [defaults/](defaults/README.md)，业务输入与源码位于 tasks/<task>/，执行记录位于 jobs/。

Controller 数据在 trial/workflow 下，不挂载给 Agent。Agent 只拥有本阶段产物和 scratch 等目录的写权限；已接受文件归 root 只读，源码仅开发阶段可写。详见 [当前设计](../docs/workflow-runtime.md)。

运行器改动后执行 [tests/](tests/README.md)；涉及 Docker、包导入或上传路径时再跑 `python -m runtime --smoke`。升级 Claude Code 原生接口时，用 `--role-probe` 做两个真实模型回合验证。

`--mode` 选择 [defaults/workflows/](defaults/README.md) 下对应的运行配置，`--task` 指定 task 包；配置只存在于 runtime，包里不放也不被查找。三个模式都声明 `max_cost_usd` 成本上限，由 Controller 和 TeamBroker 在执行中累加 Agent 上报的 `total_cost_usd` 并在超限时终止；Hierarchical 另有六个 `max_*` 执行上限。Single/Flat 单向推进，QA 轮数由 `lifecycle.yaml` 的 `stages:` 决定。task 包声明 `docker_image` 时，Harbor 任务定义由运行器生成，仓库来自镜像既有位置并迁移到 `/workspace/repos/`；包自带 `environment/Dockerfile` 时改用该文件与宿主快照。契约中 `defaults:` 引用默认集，`task:` 与 `derive:` 相对 task 根解析，后者声明该输入由指定的包内文件推导而非复制。Single 完整阶段见 [生命周期说明](../docs/single-agent-lifecycle.md)。Flat 固定顺序推进；Hierarchical 的 Lead 根据共享交付契约动态创建成员、派工、返修和接受 revision。Hierarchical 不适用固定阶段 smoke/role-probe，需真实模型 rollout。

Single/Flat 的每个实际 Stage 只执行一次；Hierarchical 可由 Lead 创建返工 assignment 和新 revision。运行器不检查文档内容，不自动补交。Controller 仅读取流程分支字段；`local_deployment.py` 管理容器内服务启动与健康检查；`workspace_snapshot.py` 保存开发候选的多仓归档和摘要。
