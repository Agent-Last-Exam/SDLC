# 阶段性验收证据与运行入口

`reports/` 保存阶段性验收摘要；`jobs/` 保存每次运行的配置、状态、日志、轨迹、产物及自动生成的 `report.md`。模型的单次运行（包括 DeepSeek）统一放在 `jobs/`。

## 单次运行报告

**运行入口：** [jobs/README.md](../jobs/README.md)。本机运行器会根据已有 jobs 生成报告索引；仓库中还保留部分运行的脱敏归档。GitHub 上的清单只反映已提交的记录，不等于本机全部运行。

**DeepSeek 已提交归档：** [single-coding-deepseek41-high-instruction-20261014](../jobs/single-coding-deepseek41-high-instruction-20261014/README.md)，包含三个文档阶段的产物及压缩轨迹。虽然名称含 `coding`，这份归档截至测试设计阶段，不包含后续 coding 续跑。

DeepSeek 本机原始报告路径（需在保留对应 jobs 的机器上查看）：

- 文档阶段：`jobs/single-docs-deepseek41-high-20261013/report.md`。
- 新版题目文档阶段：`jobs/single-coding-deepseek41-high-instruction-20261014/report.md`。
- 后续 continuation、Flat 模式和 restart 运行，可在本机生成的 jobs 索引中查找名称含 `deepseek41` 的条目。

此处只提供阅读入口，不另行维护完整运行清单或状态副本。原始运行详情以对应 `report.md` 和 trial 的 `workflow/state.json` 为准；提交归档的范围以其 README 为准。`accepted` 表示文件封存，不表示业务验收通过；任务名中的日期也不一定等于实际开始日期。

## 历史验收摘要

以下是 2026-09-17 至 2026-09-20 的验收记录，只说明当时检查过的版本与范围，不代表当前代码或后续模型运行已通过相同验收。

2026-09-20 的 `single-real-baseline-20260920` 曾封存 PRD、技术设计和测试用例，并按要求在开发前停止；当前本机已无该 job 目录，查看下表的真实文档验收摘要。同期无模型测试原始目录也已清理，仅保留摘要。

2026-09-18 的旧契约真实文档运行 `workflow-single-20260918-b` 当前本机也已无对应目录；其历史结论见下表的 workflow runtime 验收摘要。摘要内的原始路径保留历史含义，不保证本机仍可访问。

| 证据 | 含义 |
| --- | --- |
| [checks/single-agent-real-docs-verification.json](checks/single-agent-real-docs-verification.json) | 真实 gpt-6-astra：前三个文档阶段通过，130 条用例覆盖 96 条 AC，基线封存；按用户要求在开发前停止 |
| [checks/single-agent-baseline-verification.json](checks/single-agent-baseline-verification.json) | 2026-09-20：PRD/用例基线锁定，57 项单元测试及 11 阶段无模型修复链通过 |
| [checks/verification.json](checks/verification.json) | 2026-09-17 旧入口安装检查与4项适配器测试；不是模型交付 |
| [checks/workflow-preparation-verification.json](checks/workflow-preparation-verification.json) | 2026-09-18 输入准备与三模式配置检查；不是执行结果 |
| [checks/workflow-runtime-verification.json](checks/workflow-runtime-verification.json) | 2026-09-18 真实 Single 交付、同会话角色证据、哈希和 blocked 结论 |
| [checks/layout-verification.json](checks/layout-verification.json) | 2026-09-18：目录迁移、报告生成及无模型联调验证 |
| [checks/task-ownership-verification.json](checks/task-ownership-verification.json) | 任务配置闭环、用户优化 SP 原样保留、37项测试和新无模型联调 |

各份 JSON 保留生成时的含义；其中 jobs/、.prepared/ 等相对路径均以 仓库根目录为基准。它们记录当时的测试数量，不随后续新增测试改写成新的历史结论。
