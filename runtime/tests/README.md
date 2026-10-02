# 运行器的无模型测试

本目录测试 Harbor 运行器的行为，与 runtime 实现放在一起。具体任务的业务验收测试应归属 `tasks/<task>/tests/`，需要时再建立。

在 仓库根目录执行：

```bash
<harbor-python> -m unittest discover -s runtime/tests -t . -v
```

| 文件 | 验证内容 |
| --- | --- |
| test_prompt_adapters.py | Claude Code prompt 注入、参数引用、字面量环境配置 |
| test_document_judge_runner.py | Claude Code 独立 Judge 的 restricted 与结构化输出参数 |
| test_workflow_preparation.py | YAML、模式策略、输入输出引用、准备约束 |
| test_workflow_runtime.py | 原生角色证据与子 Agent 配置 |
| test_reporting.py | 报告状态、正式文件哈希、探针区分、异常信息处理和手写报告保护 |
| test_team_protocol.py / test_team_broker.py | Lead/成员 JSON 协议、并行写域、成员会话、不可变 revision、stale 和闭包 |
| test_hierarchical_controller.py | 持续 Lead、同 Stage 多成员并行与预算终止 |
| test_agent_cost.py | 从 Agent result 事件读取成本：累计、未知与畸形行的处理 |
| test_team_workspace.py | 独立代码副本 diff、冲突拒绝、受控集成和链接防护 |
| test_trajectory.py | Single、Flat 与 Hierarchical Lead/成员嵌套 ATIF 导出 |

这些测试不调用模型。Single/Flat 的真实 Docker 隔离与模块上传路径由 `python -m runtime --smoke` 验证；Hierarchical 无固定阶段 smoke，需要真实模型 rollout。合成业务文件不能充当真实 PRD/TDD。

`test_lifecycle.py` 覆盖两轮 QA 分支、可选设计复用、两轮固定用例、Single/Flat 会话策略、分支读取、缺失输出停止、部署准入与候选快照边界；`test_workflow_runtime.py` 验证 Claude Code 精确续会话与原生角色证据。完整容器联调用 `--smoke --smoke-scenario repair`，其他分支用 pass / repair-reuse / fail。

`test_deployment_boundary.py` 验证部署重建、候选摘要不匹配拒绝、旧链接隔离，以及清理阶段资源时保留服务文件。容器 smoke 还会实际执行 prepare、跨 QA 访问服务临时文件并重新挂接共享内存。

`test_lifecycle.py` 同时验证 PRD/用例基线绑定、跨轮次摘要一致，以及文件被修改、删除、替换为链接或基线清单被修改时终止；工具异常也不能绕过基线检查。
