# 文档 Rubric Judge

Standard Single Workflow 可对以下冻结文档产物执行独立评测：

- PRD；
- 前端设计、后端设计、接口契约和目标接口描述；
- 测试设计用例。

本评测不执行代码、测试、服务或部署验证。

## 输入

私有评测清单使用 JSON，包含：

- Rubric 集与版本；
- 来源文档 revision；
- 评分分组；
- 每组允许读取的候选、公开输入、Base 和私有参考材料；
- 固定的二值评分项、判定条件、引用、权重及关键项标记；
- Judge 独立运行次数和 Harbor 聚合方式。

清单及 Golden 保存在任务仓库外。运行器只把它们提供给独立 verifier，不复制进 Agent 工作区。

## 执行

```bash
python3 -m runtime.prepare_sources --task tasks/standard

python3 -m runtime \
  --task tasks/standard \
  --mode single \
  --stop-after-stage sprint1/test-design \
  --document-eval-manifest /absolute/private/path/document-rubrics.json \
  --judge-model gpt-6-astra \
  --use-local-codex-auth
```

Judge 在独立 verifier 容器中以只读 sandbox 运行。候选内容视为不可信证据；Judge 只能读取清单声明的路径，不得修改文件、联网检索或执行测试、服务、部署和迁移。

## 结果

Verifier 输出：

- `verifier/reward.json`：Harbor 数值分数；
- `verifier/reward-details.json`：RewardKit-compatible 分组与逐项指标，Harbor Viewer 可直接展示；
- `verifier/document-evaluation.json`：逐项结构化结果、分组得分和 Judge 元数据；
- `verifier/document-evaluation.md`：面向人工复核的证据报告；
- `verifier/document-judge/`：各次 Judge 的请求 Schema、结构化结果和事件日志。

每个评分项只有 P/F。默认 `reward` 取各分组通过率的最小值，避免一个阶段的高分抵消另一个阶段的缺陷；同时用 RewardKit metrics 结构保留总体通过率、关键项通过率、各组分数和逐项理由。

文档评测模式不会因缺少候选交付文件而中断：Controller 记录缺失文件和受影响的下游输入，继续运行到测试设计边界。Judge 仍评价已有产物；缺少任一要求交付文件时，`delivery_completeness=0`，最终 `reward=0`。

Judge、认证、网络或输出协议失败属于评测基础设施失败，不记为候选 0 分。未启用文档评测时，缺少阶段声明输出仍按运行错误处理。
