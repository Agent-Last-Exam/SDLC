# 执行代码

面向使用者的入口是仓库根目录执行 `python -m runtime`。这里只放实现，不放业务 prompt、实验结果或历史报告。

Single/Flat 默认允许 Agent 自行决定是否调用子 Agent，不强制调用。
`--document-only` 只限制交付阶段为 PRD、技术设计和测试设计，保留模式配置的子 Agent 策略。
开发续跑使用新准备包中的子 Agent 策略。修改仅影响后续启动的运行；已有 job 的冻结输入与运行配置不变。

`--resume-from <trial目录>` 从已接受的文档阶段边界续跑。启动前校验模式、原始业务输入、
Base、模型、思考强度、阶段契约与封存文件哈希。Single 恢复同一原生主会话；Flat 只恢复
封存文件，新阶段使用新会话。两者都使用新环境，不恢复失败开发代码。
目前支持只读文档阶段构成的连续前缀，不支持从已接受的开发或部署阶段恢复。
`--stop-after-stage` 可以限制续跑的结束位置；新运行按当前配置决定子 Agent 策略。

Single/Flat 开发失败或超时会尽力回收 `workflow/partial-candidates/` 快照，标为未验收，
证据回收失败不会覆盖原始执行错误。旧实验专用恢复器已删除，不再作为运行入口。
工作区准备时统一物化镜像硬链接，严格源码快照仍拒绝开发过程中引入的硬链接。

Single/Flat 每个 Stage 的 Agent 执行默认最多 4 小时（`--stage-timeout-sec 14400`），
进入下一阶段重新计时。Harbor 外层总时限按所选阶段数累加，并预留部署、证据回收和快照时间，
不再使用整个流程 3 小时的默认上限。显式传入 `--max-runtime-sec` 时仍保留用户指定的总时限，
与单阶段时限取先到者；超时报告区分单阶段和总预算耗尽。Hierarchical 的时间策略不变。

模型由 `--model` 或 `CLAUDE_MODEL` 指定；思考强度由 `--reasoning-effort` 或
`CLAUDE_REASONING_EFFORT` 指定，支持 low / medium / high / xhigh / max，默认 high。
客户端由 `--client-version` 固定精确版本，安装后验证公共路径可供阶段用户使用。
`--request-audit` 通过本地中继记录模型、effort、用量等元数据，保持请求体原样；
`--request-profile` 显式启用模型/思考强度/缓存断点改写，并同时审计。中继不记录凭据、
提示词、消息或思考内容，也不负责终止模型进程。`request_usage.summarize` 汇总流式用量。
实际可用强度和协议兼容性仍由 Claude Code 与模型网关决定。凭证放在本机忽略提交的
`.env` 或进程环境中，不写入任务和公开报告。

| 文件 | 职责 |
| --- | --- |
| run_workflow.py | 解析参数、冻结输入、创建 Harbor job、回收结果并生成 report.md |
| prepare_workflow.py | 解析 task 配置、校验依赖与 Base SHA、生成 Agent workspace |
| prepare_sources.py | 按 `--task` 精确获取并校验 Base；不复制工作树改动 |
| workflow_controller.py | 阶段游标、Single/Flat 主会话策略、单次执行、封存、QA 分支与终止 |
| hierarchical_controller.py | 持续 Lead 循环、结构化动作执行和并发成员调度 |
| team_protocol.py / team_broker.py | 动作协议、团队状态、写域、不可变 revision、stale 与闭包规则 |
| team_workspace.py | Hierarchical 独立代码副本的内容 diff、冲突检查和受控集成 |
| workflow_checkpoint.py | 校验与恢复 Single/Flat 已接受文档检查点 |
| workflow_agent.py | Harbor/Claude Code 适配、固定身份与会话隔离、日志回收 |
| reporting.py | 从主机证据生成每个 job 的 report.md 和 jobs/README.md |
| trajectory.py | 导出 Single、Flat 或 Lead+成员嵌套 ATIF，供 Harbor Viewer 读取 |
| workflow_smoke.py | 明确标记 SYNTHETIC 的无模型容器联调 |
| agents.py | Claude Code system prompt 注入适配器 |
| environment.py | 按字面量读取本机 .env，不执行 shell |
| agent_cost.py | 从 Agent result 事件读取已花费成本，供费用报告使用 |
| defaults/ | 角色、模板与唯一的交付契约 |

`prepare_workflow.HERE` 指向 仓库根目录，不依赖 shell 当前目录推算资源位置；用户传入的相对路径仍相对调用目录。角色、模板与交付契约位于 [defaults/](defaults/README.md)，业务输入与源码位于 tasks/<task>/，执行记录位于 jobs/。

Controller 数据在 trial/workflow 下，不挂载给 Agent。Agent 只拥有本阶段产物和 scratch 等目录的写权限；已接受文件归 root 只读，源码仅开发阶段可写。详见 [当前设计](../docs/workflow-runtime.md)。

运行器改动后执行 [tests/](tests/README.md)；涉及 Docker、包导入或上传路径时再跑 `python -m runtime --smoke`。升级 Claude Code 原生接口时，用 `--role-probe` 做两个真实模型回合验证。

`--mode` 选择 [defaults/workflows/](defaults/README.md) 下对应的运行配置，`--task` 指定 task 包；配置只存在于 runtime，包里不放也不被查找。三个模式都累加 Agent 上报的 `total_cost_usd` 用于费用报告，不按费用终止运行；Hierarchical 保留六个 `max_*` 执行上限。Single/Flat 单向推进，QA 轮数由 `lifecycle.yaml` 的 `stages:` 决定。task 包声明 `docker_image` 时，Harbor 任务定义由运行器生成，仓库来自镜像既有位置并迁移到 `/workspace/repos/`；包自带 `environment/Dockerfile` 时改用该文件与宿主快照。契约中 `defaults:` 引用默认集，`task:` 与 `derive:` 相对 task 根解析，后者声明该输入由指定的包内文件推导而非复制。Single 完整阶段见 [生命周期说明](../docs/single-agent-lifecycle.md)。Flat 固定顺序推进；Hierarchical 的 Lead 根据共享交付契约动态创建成员、派工、返修和接受 revision。Hierarchical 不适用固定阶段 smoke/role-probe，需真实模型 rollout。

Single/Flat 的每个实际 Stage 只执行一次；Hierarchical 可由 Lead 创建返工 assignment 和新 revision。运行器不检查文档内容，不自动补交。Controller 仅读取流程分支字段；`local_deployment.py` 管理容器内服务启动与健康检查；`workspace_snapshot.py` 保存开发候选的多仓归档和摘要。

已归档提示词的 Viewer 展示适配器见 `viewer_context.py`：校验归档后生成独立、仅供查看的 Harbor 目录，将带来源和继承标记的阶段快照显示为补充 system 卡片。使用方式与展示边界见 [运行记录说明](../docs/rollout-records.md#在-harbor-viewer-中显示已归档的阶段提示词)。
