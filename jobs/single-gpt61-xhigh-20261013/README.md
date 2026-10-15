# Single Agent rollout — 2026-10-13

真实 gpt-6.1-sol / xhigh，Single 同会话角色切换，官方 verifier 关闭。最终状态 failed；QA 写出报告后，运行器封存阶段触发 Docker 参数长度限制。没有执行 sprint2/triage 或修复。详细结论见 [report.md](report.md)。

## 记录

- `agent/trajectory.json.gz`：脱敏的标准 ATIF 轨迹，1165 个步骤，包括可见消息、工具调用与返回；不是服务端全部内部思考。解压：`gzip -dc agent/trajectory.json.gz > trajectory.json`。
- `workflow/state.json`、`workflow/events.jsonl`：状态与阶段事件。
- `artifacts/sprint1/`：各阶段主要交付及 QA CSV、报告、判定；大体积 target-schema.graphql 以 gzip 保存。
- `trial-result.json`、`result.json`：原始失败结果的脱敏副本；其中 cost 为 CLI 估算，不是供应商账单。
- `manifest.json`：本次公开副本的文件大小及 SHA-256。

## 边界与脱敏

本 PR 只增加运行记录，不修改运行器或任务。QA 自检 52 通过、7 失败、74 阻塞、12 未执行，未经过独立评分。`artifacts` 中的 QA 文件已下载保存，但运行器封存校验失败，不能把文件存在视为阶段 accepted。

本机已知密钥、常见 token/Bearer/JWT、字符串形式密码、邮件地址及主机用户名已脱敏。源文件保留在本机；发布副本不是原始字节归档，脱敏会影响部分命令的直接重放。没有提交 .env、Claude 认证配置、会话配置、原生会话重复副本、QA 截图/详细证据目录或完整工作区归档。按需可另行整理更多脱敏证据。

## Coding 产物

[coding/README.md](coding/README.md) 提供 Core、Dashboard 的原样代码补丁、固定基线和重建校验，供后续代码评测。随后已执行独立代码评测，结果见下方。

## 后续代码评测

[coding-evaluation/README.md](coding-evaluation/README.md)：本次候选 F2P 95/5182、P2P 15009/15012、reward=0；含参考 Oracle 对照及逐项 CSV。原 rollout 的 verifier 关闭与原始失败记录保持不变。

## 当次阶段提示词

当时保存的职责、用户阶段指令及原生注入证据见 [prompt-snapshots/](prompt-snapshots/README.md)，按原始 job、trial、阶段区分，并标记继承快照。该补充不代表完整供应商请求或全部子会话日志。
