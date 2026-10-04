# 文档 Rubric Judge

Standard Single Workflow 可对以下冻结文档产物执行独立评测：

- PRD；
- 前端设计、后端设计和接口契约；
- 测试设计用例。

本评测不执行代码、测试、服务或部署验证。`target-schema.graphql` 的
GraphQL 差异与 GT 一致性由独立 checker 负责，不进入 LLM 文档 Judge。

## 输入

私有评测清单使用 JSON，包含：

- Rubric 集与版本；
- 来源文档 revision；
- 评分分组；
- 每组固定注入的候选、公开输入与可选私有语义参考；
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

直接 Judge 还需要通过 verifier 环境配置 `OPENAI_API_KEY` 与
`OPENAI_BASE_URL`。Verifier 在宿主侧读取 manifest 明确声明的小型文本文件，按
SHA-256 构造固定证据包，再在独立 verifier sandbox 中通过 SSE 直接调用
OpenAI-compatible Chat Completions API。Judge 不启动 Codex/OpenCode Agent，不使用
文件、终端、网络检索或其他工具。

证据包设置总字节上限。候选缺失文件作为评分事实进入证据包；公开评测输入缺失、
API 失败或输出协议失败属于基础设施错误。保存到结果目录的 Prompt 仅包含证据路径、
大小和哈希，不复制私有证据全文。

API 凭证不进入 sandbox 命令行。Verifier 每次调用生成权限为 `0600` 的一次性凭证
文件，通过 Kubernetes exec 的 stdin 文件上传通道发送；runner 读取后立即删除，
sandbox 回收前再次执行清理。

## 结果

Verifier 输出：

- `verifier/reward.json`：Harbor 数值分数；
- `verifier/reward-details.json`：RewardKit-compatible 分组与逐项指标，Harbor Viewer 可直接展示；
- `verifier/document-evaluation.json`：逐项结构化结果、分组得分和 Judge 元数据；
- `verifier/document-evaluation.md`：面向人工复核的证据报告；
- `verifier/document-judge/`：各次 Judge 的证据清单、请求 Schema、结构化结果和 API 元数据。

每个评分项只有 P/F。默认 `reward` 取各分组通过率的最小值，避免一个阶段的高分抵消另一个阶段的缺陷；同时用 RewardKit metrics 结构保留总体通过率、关键项通过率、各组分数和逐项理由。

文档评测模式不会因缺少候选交付文件而中断：Controller 记录缺失文件和受影响的下游输入，继续运行到测试设计边界。Judge 仍评价已有产物；缺少任一要求交付文件时，`delivery_completeness=0`，最终 `reward=0`。

Judge、认证、网络或输出协议失败属于评测基础设施失败，不记为候选 0 分。未启用文档评测时，缺少阶段声明输出仍按运行错误处理。

文档结构只有在单独 Rubric 明确要求时才由 LLM 评价；当前 v4 不检查 Markdown
章节、模板占位或 GraphQL SDL。TDD4 明确禁止以目标 SDL 未进入证据包作为失败依据。
GraphQL GT checker 尚未接入 Document Verifier，后续应作为独立 reward 分量实现，
避免与文档 Judge 重复扣分。
