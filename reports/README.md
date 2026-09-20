# 报告与验收证据

**本次真实产物：** [single-real-baseline-20260920](../jobs/single-real-baseline-20260920/operator-stop.md)，PRD、技术设计和测试用例已接受，按要求在开发前停止。

0920 的 jobs 仅保留本次真实运行；无模型测试目录及对应准备目录已清理，基线验证结果仅保留摘要。

**历史真实文档交付（旧契约）：** [workflow-single-20260918-b/report.md](../jobs/workflow-single-20260918-b/report.md)。

**所有 rollout：** [jobs/README.md](../jobs/README.md)，包括失败记录、角色切换探针、无模型 smoke 和 Codex / Claude Code 安装检查。每个 job 自带 report.md，原始记录保存在相邻 trial 目录，不在此处复制第二份。

| 证据 | 含义 |
| --- | --- |
| [checks/single-agent-real-docs-verification.json](checks/single-agent-real-docs-verification.json) | 真实 gpt-6-astra：前三个文档阶段通过，130 条用例覆盖 96 条 AC，基线封存；按用户要求在开发前停止 |
| [checks/single-agent-baseline-verification.json](checks/single-agent-baseline-verification.json) | 当前版本：PRD/用例基线锁定，57 项单元测试及 11 阶段无模型修复链通过 |
| [checks/verification.json](checks/verification.json) | 2026-09-17 旧入口安装检查与4项适配器测试；不是模型交付 |
| [checks/workflow-preparation-verification.json](checks/workflow-preparation-verification.json) | 2026-09-18 输入准备与三模式配置检查；不是执行结果 |
| [checks/workflow-runtime-verification.json](checks/workflow-runtime-verification.json) | 2026-09-18 真实 Single 交付、同会话角色证据、哈希和 blocked 结论 |
| [checks/layout-verification.json](checks/layout-verification.json) | 本次目录迁移、报告生成及无模型联调验证 |
| [checks/task-ownership-verification.json](checks/task-ownership-verification.json) | 任务配置闭环、用户优化 SP 原样保留、37项测试和新无模型联调 |

各份 JSON 保留生成时的含义；其中 jobs/、.prepared/ 等相对路径均以 仓库根目录为基准。它们记录当时的测试数量，不随后续新增测试改写成新的历史结论。
