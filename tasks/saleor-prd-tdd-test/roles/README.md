# Role Blueprint 与阶段交接

角色提示词说明职业职责，模板说明字段和格式，运行器注入当前阶段、轮次、材料路径、输出路径和可写范围。默认 Single 使用 [lifecycle.yaml](../workflows/lifecycle.yaml)。

| 阶段 | 角色 | 交付 |
| --- | --- | --- |
| PRD | [PM](pm.system.md) | sprint1/prd/prd.md |
| 技术设计 | [Tech Owner](architect.system.md) | sprintN/tech-design/ 下四份技术产物，按需附 interfaces/ |
| 测试设计 | [QA](qa-design.system.md) | sprintN/test-design/test-cases.vN.csv |
| 开发 | [Tech Owner](developer.system.md) | 当前代码及 sprintN/development/test-handoff.md |
| 部署 | [部署职责](deployer.system.md) | sprintN/deploy/test-handoff.md、deployment.json；本地可测试环境 |
| QA | [QA 执行](qa.system.md) | sprintN/qa/test-results.N.csv、test-report.N.md、test-verify.json |
| 修复研判 | [Tech Owner](triage.system.md) | sprint2/triage/repair-plan.json |

路径相对 `/workspace/artifacts`；源码在 `/workspace/repos`。PRD 保持首轮版本。开发报告和部署报告分别封存，部署读取开发报告并交付更新版本，QA 明确读取部署版本。

Sprint 1 按表前六步推进。首轮 QA pass 即结束；fail 进入 Sprint 2：研判报告 → 按需更新技术设计 → 修复开发 → 重新部署 → QA 复测。无需修改的设计由运行器复用，保留来源。测试用例固定使用第一轮版本，不更新。第二轮 QA fail 以 qa_failed 停止，不继续第三轮。各阶段只执行一次，运行器不做文档内容检查或自动补交；模板仍作为 Agent 的编写指引。

每次进入阶段时明确声明上一阶段已结束。旧 developer 消息保留历史，但本阶段任务、路径和权限以新消息与当前环境为准。同一原生主会话贯穿执行。

执行机制、部署服务生命周期、验证结果及尚未验证的真实业务边界见 [Single 流程说明](../../../docs/single-agent-lifecycle.md)。
