# Saleor 3.23 剪枝 Golden 文档交付包

版本：`saleor-golden-docs-20260926-01`  
文档状态：已冻结  
范围：Saleor Core 3.22.0、Dashboard 3.22.9 到剪枝后 Saleor 3.23 目标

## 目录

```text
golden-docs/
├── README.md
├── manifest.json
├── SHA256SUMS
├── PRD/
│   ├── prd.md
│   └── prd-golden.md
├── TDD/
│   ├── backend-design.md
│   ├── frontend-design.md
│   ├── interface-contract.md
│   └── target-schema.graphql
├── Test/
│   ├── README.md
│   ├── test-cases.v1.csv
│   └── test-patch-traceability.md
├── references/
│   ├── base-to-target-requirements.md
│   ├── requirements-completeness-audit.md
│   ├── pruning-order-workflow.md
│   └── 各剪枝阶段记录
└── evidence/
    ├── calibration-audit.json
    ├── changes-from-candidate.json
    ├── ctrf.json
    ├── golden-patch-manifest.json
    ├── harbor-delivery.json
    ├── reward.json
    ├── selection.json
    └── verification-summary.md
```

## 阅读顺序

1. `PRD/prd-golden.md`：推荐使用的剪枝后产品范围，只保留继续交付的 16 个需求，且对业务目的、触发条件、规则和验收条件作了详细描述。
2. `PRD/prd.md`：历史追踪版 PRD，保留原始 R01-R18 编号及完整对照信息，不作为剪枝后需求范围的唯一依据。
3. `TDD/`：按 Golden TDD 模板编排的后端设计、前端设计、接口契约和完整目标 GraphQL schema。
4. `Test/test-cases.v1.csv`：65 条场景级 Golden 测试设计；新 PRD 的细化 AC 由场景聚合验证，不要求一条 AC 对应一条 CSV 记录。
5. `Test/test-patch-traceability.md`：需求与 test patch 的充分性、必要性双向审计。
6. `evidence/`：与本文档配对的剪枝 patch 身份及最终评分摘要。

## PRD 版本说明

`prd.md` 与 `prd-golden.md` 有意同时保留：前者用于历史追踪、需求编号对照和审计；后者去掉已剪枝的需求主体，是当前 target 的产品范围和实施验收依据。两份文档不得混合解读；实现和交付验收优先以 `prd-golden.md` 为准。

## 配对规则

本包描述的是剪枝后的 Golden target。实现必须匹配 `evidence/golden-patch-manifest.json` 中的四个 patch SHA。按 `Base=environment+最终 test patch`、`Target=Base+最终 code patch` 重新校准后的结果为 F2P `5365/5365`、P2P `15013/15013`、reward `1`；冻结 selection SHA-256 为 `c6652cccc79707f4d744e2e7c0a437902e8b3be25a87efd6157952ac3c4a9e60`。

正式配对实现为父目录 `..`，即当前 Git task `tasks/saleor-3.23-pruned/`。该包由官方 exporter 生成，四个 patch SHA、C/D 组合、冻结选择和评分结果均与本文档一致；机器可读身份见 `evidence/harbor-delivery.json`。`saleor-standard-20260926-01` 仍是不配对的历史 Candidate，不得替代本包。

## 完整性校验

在包根目录执行：

```bash
sha256sum -c SHA256SUMS
```
