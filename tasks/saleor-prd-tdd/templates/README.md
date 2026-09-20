# 产物模板

角色 Prompt 说明身份、工作和文件位置，模板定义字段与格式。

| 产物 | 模板 | 文件形式 |
| --- | --- | --- |
| PRD | [prd.md](prd.md) | Markdown |
| 前端技术设计 | [frontend-design.md](frontend-design.md) | Markdown |
| 后端技术设计 | [backend-design.md](backend-design.md) | Markdown |
| 接口契约 | [interface-contract.md](interface-contract.md) | Markdown |
| 完整目标接口 | [target-interface.md](target-interface.md) | GraphQL SDL，其他协议按需补充 |
| 测试用例 | [test-cases.md](test-cases.md) | CSV，首版 test-cases.v1.csv |
| 提测报告 | [test-handoff.md](test-handoff.md) | Markdown，开发创建、部署更新同一份 |
| 测试执行记录 | [test-results.md](test-results.md) | CSV，test-results.{round}.csv |
| 测试报告 | [test-report.md](test-report.md) | Markdown，test-report.{round}.md |
| QA 结果 JSON | [test-verify.schema.json](test-verify.schema.json) | JSON，test-verify.json |

QA 模板依据用户指定的[「QA阶段的Schema」章节](https://rcnmkynuc7as.feishu.cn/wiki/GsuKwp9JJiTLPckayTwctTjxnic#share-IpFadrqBroFShyxKzC5clszanch)，2026-09-20 读取正文 revision 1366，以及内嵌产物总览表 revision 222。保留测试用例和执行记录的列、TC/AC/D 引用规则、报告的四个章节，以及 JSON 的原始 Schema。

原章节的总览表将 JSON 称为 `test-verdict.json`，详细章节标题为 `test-verify.json`，Schema title 为 `test-verdict`。这里统一交付文件名为 `test-verify.json`，Schema title 保留原文；交付的 JSON 是符合 Schema 的数据，不是 Schema 本身。

本 task 将执行记录和报告的文件后缀统一为测试轮次，使同一 sprint 内的返工复测保留历史。报告增加轮次、被测版本和测试环境，以关联本轮实际测试对象。测试用例跨轮次延续，不随每次执行重编号；修订用例时使用新版本并延续 TC 编号。

提测报告按本次用户要求新增；角色顺序、共享报告的更新和返工交接见 [角色说明](../roles/README.md)。新阶段目前为角色及产物定义，尚未接通自动执行。
