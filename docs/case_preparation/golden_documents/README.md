# 其他 Golden 文档生成

这是 case 制作的第三条 workflow。以 [第二条 workflow](../feature_pruning/README.md) 的最终活动 PRD、配对 Harbor 包及发布绑定为输入，生成 Golden 技术设计、接口合同、完整目标接口描述和测试设计，并与实际 code/test patch 做双向审计。

本目录的方法适用于不同技术栈和系统组成。前端、后端、数据库、GraphQL、OpenAPI、proto 等按实际能力及输入模板启用，不要求每个 case 都具有同一组文档。本文中的 TDD 指技术设计文档。

## 使用入口

1. 阅读 [workflow.md](workflow.md) 和 [data-contracts.md](data-contracts.md)。
2. 将 [inputs.json](templates/inputs.json) 复制到独立运行目录，绑定最终发布身份、活动 PRD、模板和文档适用范围。
3. 核验最终实现，生成设计与测试文档，完成需求、设计、接口、测试和实现的双向追踪。
4. 将文档及本次冻结记录归档到最终 Harbor 包，更新文档清单、证据清单和发布绑定。

模板提供 Markdown 设计文档、九列测试用例 CSV 及通用审核清单。实际运行优先使用配置指定并已冻结的模板；不得擅自改模板或在不存在的模块中编造设计。

## 产物与包内位置

```text
HARBOR_TASK_ROOT/
├── environment/、solution/、tests/    # 第二条冻结的运行包
├── manifest.json
├── release-binding.json              # 新文档版本绑定，保留旧版来源
└── golden-docs/
    ├── manifest.json                 # 活动 PRD/TDD/Test 文档清单
    ├── PRD/prd-golden.md              # 输入的最终 PRD，原样保留
    ├── TDD/
    │   ├── README.md
    │   ├── backend-design.md         # 实际有后端或模板要求时
    │   ├── frontend-design.md        # 实际有前端或模板要求时
    │   ├── interface-contract.md
    │   └── interfaces/               # 原生协议完整目标描述
    ├── Test/
    │   ├── README.md
    │   └── test-cases.v1.csv
    └── evidence/
        ├── manifest.json             # 三条 workflow 的证据与文档清单
        ├── reverse-extraction/
        ├── feature-pruning/
        └── golden-documents/
            ├── index.json
            └── <run_id>/             # 输入、来源、追踪、审核、检查与修订
```

文档文件名及接口描述位置由配置决定；图示为默认布局。模板要求目标描述在 TDD 根目录时遵守模板，不为统一目录而移动它。

生成 Golden 文档是参考答案制作。可阅读最终实现和官方测试，但产物及制作证据不注入待测 Agent 工作区。应用代码、G/T、选择集和评测语义的修复返回第二条 workflow；文档流程不能静默修改已配对的实现。

## 三项独立结论

- 文档是否充分且忠实地表达最终范围和实现。
- 现有自动测试对这些行为的覆盖是否充分，以及测试为何必要。
- 绑定版本实际执行了哪些测试及验证。

文档完成不等于新增测试已实现或用例已运行，F2P/P2P 通过也不等于全部 AC 均被自动覆盖。审核必须分别给出上述结论与限制。
