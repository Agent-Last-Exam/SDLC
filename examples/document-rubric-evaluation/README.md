# Document Rubric Evaluation Example

这是一次真实 Harbor 文档评测的可审计示例，覆盖 PRD、Tech Design 和 Test Design。候选文档不是 Golden 或参考答案；它们是 Runner 的实际交付，最终文档验收未通过。

## 内容

| 路径 | 内容 |
| --- | --- |
| `candidate/` | source trial 封存的 PRD、技术设计和测试设计 |
| `rubrics/document-rubrics.v2.json` | 三阶段分组的冻结 P/F Rubric；Tech Design 含 12 项 |
| `rubrics/document-rubrics.v3.json` | direct LLM 文档 Judge 的 22 条原子化 Rubric；排除 GraphQL、Base 与模板结构检查 |
| `rubrics/document-rubrics.v4.json` | 当前 Rubric；明确禁止以目标 SDL 未进入证据包作为 TDD4 失败依据 |
| `source-result-v4/` | regrade12 的原始 Harbor 结果，保留历史 `tdd_schema` / `tdd_quality` 分组 |
| `merged-result-v5/` | 保持逐项最终判定不变、合并为 `tech_design` 后的确定性重聚合结果 |
| `direct-result-v6/` | v3 范围校准运行；保留“SDL 缺失被间接扣分”的审计证据 |
| `direct-result-v7/` | v4 范围一致的正式 VKE regrade 结果与完整验证清单 |
| `merged-tech-design-report.html` | 面向人工查看的问题报告 |
| `direct-v3-report.html` | v3 正式结果的自包含 HTML 验收报告 |
| `direct-v4-report.html` | 当前 v4 正式结果的自包含 HTML 验收报告 |
| `build_merged_result.py` | 从原始结果重建合并结果；不调用模型或 Harbor |
| `build_direct_report.py` | 从正式 v4 JSON 重建 HTML；不调用模型或 Harbor |
| `checksums.sha256` | 示例文件 SHA-256 |

## 结果口径

| 结果 | Reward | 性质 |
| --- | ---: | --- |
| source-result-v4 | 0.125 | regrade12 原始 Harbor 正式结果 |
| merged-result-v5 | 0.250 | 基于相同最终 P/F 判定的确定性分组示例，不是一次新 regrade |
| direct-result-v6 | 0.625 | v3 Rubric 与固定证据包 direct Judge 的正式 Harbor regrade |
| direct-result-v7 | 0.500 | 当前 v4 范围一致 Rubric 的正式 Harbor regrade |

合并后分组为：PRD 33.33%、Tech Design 25.00%、Test Design 75.00%。22 条 Rubric、权重、P/F 判定、证据和 issue ID 均未改变。

## 复现

在仓库根目录执行：

```bash
python3 examples/document-rubric-evaluation/build_merged_result.py
python3 examples/document-rubric-evaluation/build_direct_report.py
shasum -a 256 -c examples/document-rubric-evaluation/checksums.sha256
```

`build_merged_result.py` 只重做确定性聚合。若要得到 v2 分组下的正式 Harbor score，必须使用 v2 manifest 重新执行独立 Judge。

v3 用于新的固定证据包 direct Judge，不能通过重聚合历史 P/F 得到结果，必须重新
regrade。其分组为 PRD 8 项、Tech Design 8 项、Test Design 6 项；
`target-schema.graphql` 仍保留为工作流产物，但不提供给 LLM，后续由独立 GraphQL
GT checker 评分。Markdown 章节和模板格式不作为 v3 的独立评分项。

v3 正式运行发现 TDD4 仍以“权威 SDL 未进入证据包”为失败依据，与 GraphQL 已移交
外部 checker 的范围不一致，因此只保留为校准历史。v4 仅修订 TDD4 的评分边界，
其余 Rubric 和证据范围不变。

当前 `direct-result-v7` 对应 `sdlc-doc-direct-v4-regrade4-20260928`：1/1 trial
完成、0 exception、16/22 Rubric 通过；PRD 87.50%、Tech Design 50.00%、
Test Design 83.33%，最终 reward 取最低组为 0.500。两次首轮 Judge 均使用
`gpt-5.6-sol`；Tech Design 经过第三次裁决，共 7 次模型调用，stderr 全空、
没有协议重试。TDD4 最终通过，且未以目标 SDL 缺失作为失败依据。详细运行与安全
验收见 `direct-result-v7/validation.json`。

## 边界

- 原始运行：`sdlc-doc-gpt56-r2-regrade12-20260927`。
- Runner：`openai/gpt-5.6-sol`；Judge：`openai/gpt-5.6-sol`，2 replicas。
- v4 Judge 通过 OpenAI-compatible Chat Completions SSE 直接调用，不启动 Judge Agent。
- 不包含认证信息、VKE 配置、原始事件流或完整 Agent 轨迹。
- PRD Golden 属于私有 Judge 输入，未提交到仓库，因此此目录不是可直接重新调用 Judge 的完整私有评测包。
- `examples/` 不会由 `prepare_workflow.py` 复制到候选 Agent 工作区。
