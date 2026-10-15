# DeepSeek V4.1 Flash high · 新版业务输入文档 rollout

本归档对应 `single-coding-deepseek41-high-instruction-20261014` / `task__DkkX3ja`，使用新版 `instruction.md` 与 `business-conversations.md`，Single 模式，允许阶段内子 Agent。运行于 2026-10-14 17:13 UTC 结束；PRD、技术设计和 QA 测试用例全部封存。

## 内容

- `artifacts/`：7 份封存产物，包括 PRD、前后端设计、接口契约、OIDC 补充协议、GraphQL SDL 和测试用例 CSV。
- `agent/trajectory.json.gz`：614 步 ATIF 主会话轨迹，截至测试设计阶段。主轨迹不单独合并子会话历史。
- `workflow/stages/`：三个阶段的角色指令、用户指令、原生角色证据及压缩事件日志。
- `workflow/`：原始状态、事件、基线与请求用量记录；保留历史停止原因。
- `configuration/inputs/`：实际运行时冻结的业务题目和基线版本；`run.json` 记录模型、模式、输入哈希及成本口径。
- `checksums.sha256`：归档文件 SHA-256；先解压 `.gz` 可查看对应 JSON/JSONL。

## 状态与成本

三个阶段均为 `accepted`，表示产物已封存，不代表通过独立业务验收。运行因 CLI 费用估算触发上限而标记 `budget_exhausted`，保留该事实，不将它改写成成功停止。

CLI 累计估算 `$115.150053` 的 `costBasis` 为 `unknown`，不等于 DeepSeek 实际账单。此前已按网关 342 条消费记录核实 PRD 实际扣费 `$0.343702`；整轮实际总额未完整核算。后续 coding 续跑及其中断记录不在本次归档范围内。

封存文件导出前已逐项与原状态的 SHA-256 核对。导出对凭证字符串及本地操作员路径做脱敏，因此归档文件哈希可能与原封存哈希不同，原历史哈希仍保留用于溯源。未包含 `.env`、认证文件、私有 Golden 或 prepared 源码仓库副本。

## 验证

在本目录运行 `sha256sum -c checksums.sha256`。所有 JSON/JSONL 与 gzip 流已验证可读。只归档运行证据，没有重新调用模型，也没有执行代码或部署验收。
