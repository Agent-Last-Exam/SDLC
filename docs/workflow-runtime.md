# Workflow runtime

当前唯一交付契约是 task 内的 [lifecycle.yaml](../tasks/saleor-prd-tdd/workflows/lifecycle.yaml)，推进规则见 [Single 流程](single-agent-lifecycle.md)。single.yaml 指定同一 Codex 主会话执行；flat.yaml 和 hierarchical.yaml 声明同一契约，但尚无执行后端。旧两阶段契约、入口和 PRD 后续跑机制已删除。

| 模块 | 当前职责 |
| --- | --- |
| runtime/prepare_workflow.py | 校验 11 个阶段、两轮 QA、产物引用和权限；冻结源码、角色、模板及环境配置 |
| runtime/run_workflow.py | 选择 task/mode，创建 Harbor recipe，启动本次容器并生成报告 |
| runtime/workflow_controller.py | 推进阶段、单次执行、复用设计、候选封存、QA 分支及终止 |
| runtime/workflow_agent.py | 阶段 UID 权限、原生会话核验、进程回收、部署源码物化、日志回收 |
| runtime/codex_app_turn.py | App Server 会话延续、developer 注入、当前 turn 完成与失败识别 |
| runtime/workspace_cleanup.py | 按已退出阶段的 UID 清理临时文件，保留服务用户资源 |
| runtime/workspace_snapshot.py | 多仓源码内容、执行位和链接清单，生成候选归档 |
| runtime/local_deployment.py | 全新候选副本、prepare 命令、前台服务、HTTP 就绪检查 |
| runtime/reporting.py | 输出运行报告与证据链接，可读取历史记录 |

Controller 在宿主机持有状态，不把控制数据挂载给 Agent。各阶段有独立输出目录和 UID，开发阶段有源码写权限；接受后产物锁定。阶段结束回收该 UID 的全部进程。服务使用独立 UID，跨 QA 保留，下一轮开发/部署或运行结束时停止。

部署时由 Controller 校验当前源码摘要、清空部署目录并复制源码，再核验副本摘要；部署 Agent 交付的 prepare 命令在该副本上安装、构建和初始化。服务直接从新目录启动，就绪证据保存实际物化候选摘要、阶段、启动声明摘要和 HTTP 状态。准备失败和部署失败都不会进入 QA。

运行器不检查文档内容，也不自动补交。每阶段执行一次，文件收集到 accepted 后封存；日志存入 stages，不生成 attempts 或额外输出快照。封存与服务就绪不替代业务验收。QA 结论来自同一 Agent 的报告，目前没有独立业务 verifier。现有状态目录拒绝重放，不提供断点恢复入口；历史 jobs/ 和 .prepared/ 保留原始记录。
