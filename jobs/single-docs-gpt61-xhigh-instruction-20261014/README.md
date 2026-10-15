# GPT 6.1 Sol xhigh：新版题目文档交付

运行：`single-docs-gpt61-xhigh-instruction-20261014 / task__Fq5bK83`。Single 同会话完成 PRD、技术设计和测试设计，约 131.69 分钟，260 条测试用例。

- `artifacts/`：13 份正式文档，包括 PRD、前后端设计、接口协议、完整 GraphQL SDL 和测试用例 CSV。
- `agent/trajectory.json.gz`：结构化对话与工具轨迹；提示词另见下方快照，子会话覆盖以导出记录为准。
- 新版题目见仓库 `tasks/saleor-3.23-pruned/instruction.md` 和 `business-conversations.md`；本目录不重复提交输入与配置快照。

产物已封存；流程接受不代表独立内容评分或业务验收通过。后续 coding 和独立 F2P/P2P 结果见相邻 `single-coding-gpt61-xhigh-continuation-20261014/`。旧五模型题目不同，不直接混排成绩。

验证结论与历史执行环境限制见 PR 描述。辅助日志、请求审计与配置保留在本地原始记录，未纳入精简归档。

## 当次阶段提示词

当时保存的职责、用户阶段指令及原生注入证据见 [prompt-snapshots/](prompt-snapshots/README.md)，按原始 job、trial、阶段区分，并标记继承快照。该补充不代表完整供应商请求或全部子会话日志。
