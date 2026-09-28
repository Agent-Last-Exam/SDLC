# Document Rubric Evaluation Example

这是一次真实 Harbor 文档评测的可审计示例，覆盖 PRD、Tech Design 和 Test Design。候选文档不是 Golden 或参考答案；它们是 Runner 的实际交付，最终文档验收未通过。

## 内容

| 路径 | 内容 |
| --- | --- |
| `candidate/` | source trial 封存的 PRD、技术设计和测试设计 |
| `rubrics/document-rubrics.v2.json` | 三阶段分组的冻结 P/F Rubric；Tech Design 含 12 项 |
| `source-result-v4/` | regrade12 的原始 Harbor 结果，保留历史 `tdd_schema` / `tdd_quality` 分组 |
| `merged-result-v5/` | 保持逐项最终判定不变、合并为 `tech_design` 后的确定性重聚合结果 |
| `merged-tech-design-report.html` | 面向人工查看的问题报告 |
| `build_merged_result.py` | 从原始结果重建合并结果；不调用模型或 Harbor |
| `checksums.sha256` | 示例文件 SHA-256 |

## 结果口径

| 结果 | Reward | 性质 |
| --- | ---: | --- |
| source-result-v4 | 0.125 | regrade12 原始 Harbor 正式结果 |
| merged-result-v5 | 0.250 | 基于相同最终 P/F 判定的确定性分组示例，不是一次新 regrade |

合并后分组为：PRD 33.33%、Tech Design 25.00%、Test Design 75.00%。22 条 Rubric、权重、P/F 判定、证据和 issue ID 均未改变。

## 复现

在仓库根目录执行：

```bash
python3 examples/document-rubric-evaluation/build_merged_result.py
shasum -a 256 -c examples/document-rubric-evaluation/checksums.sha256
```

`build_merged_result.py` 只重做确定性聚合。若要得到 v2 分组下的正式 Harbor score，必须使用 v2 manifest 重新执行独立 Judge。

## 边界

- 原始运行：`sdlc-doc-gpt56-r2-regrade12-20260927`。
- Runner：`openai/gpt-5.6-sol`；Judge：`openai/gpt-5.6-sol`，2 replicas。
- 不包含认证信息、VKE 配置、原始事件流或完整 Agent 轨迹。
- PRD Golden 属于私有 Judge 输入，未提交到仓库，因此此目录不是可直接重新调用 Judge 的完整私有评测包。
- `examples/` 不会由 `prepare_workflow.py` 复制到候选 Agent 工作区。
