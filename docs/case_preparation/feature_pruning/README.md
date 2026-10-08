# 功能剪枝与标准 Harbor 包生成

这是 case 制作的第二条 workflow。输入是第一条 [未剪枝 PRD 反向提取](../reverse_extraction/README.md) 的冻结结果、完整升级实现、明确的业务主体和范围规则；输出是剪枝后的生产/测试 patch、最终需求范围、重新校准的评测选择和标准 Harbor 包。

方法适用于任意数量的仓库及不同技术栈。业务主体、接口协议、迁移、生成器、测试框架和 exporter 通过输入配置接入，不内置具体项目的功能名单、目录、镜像或测试数量。

## 执行入口

1. 阅读 [workflow.md](workflow.md) 与 [data-contracts.md](data-contracts.md)。
2. 将 [inputs.json](templates/inputs.json) 复制到独立运行目录，绑定第一步产物的真实路径与哈希，并填写范围规则、环境、评测和 exporter。
3. 从完整或上一轮已验收目标创建可恢复工作树，按阶段剪枝、检查、校准和导出。
4. 将第一步与本步的冻结运行记录归档进最终包，核对完整性与实际 verifier 行为后交付。

模板中的占位符必须替换。模板不执行命令，也没有附带自动检查器；契约中的完成检查由可用工具或逐项审核落实。

## 文件与模板

| 文件 | 用途 |
| --- | --- |
| [workflow.md](workflow.md) | 产品边界、连续剪枝、patch 重建、校准、导出、留痕与恢复 |
| [data-contracts.md](data-contracts.md) | 配置、身份、范围、测试选择、清单与发布绑定的字段定义 |
| [templates/](templates/) | 范围政策、逐项决定、影响面、阶段计划、测试变化、patch、选择、校准、状态、审核与发布模板 |

## 最终包内的证据

```text
HARBOR_TASK_ROOT/
├── environment/                         # 标准 exporter 的运行输入
├── solution/                            # 每个仓库的最终生产 patch
├── tests/                               # 最终测试 patch 与 verifier
├── task.toml
├── manifest.json                        # exporter 管理的运行包身份
├── release-binding.json                 # 绑定运行包、证据清单和最终范围
└── golden-docs/
    ├── PRD/prd-golden.md                 # 剪枝后的活动产品范围
    └── evidence/
        ├── manifest.json                # 证据文件清单，独立于运行包清单
        ├── reverse-extraction/
        │   ├── index.json
        │   └── <extraction_run_id>/      # 第一步完整、未剪枝的历史证据
        └── feature-pruning/
            ├── index.json
            └── <pruning_run_id>/         # 本步配置、决定、各轮记录及验证
```

运行包的具体布局以指定 exporter/Harbor schema 为准；上图的 evidence 与发布绑定是本 workflow 的额外交付契约。指定 exporter 不管理这些附件时，使用独立证据清单登记，不手改其根 manifest。最终包必须实际携带证据文件，不能只引用制作机器的目录。

未剪枝 PRD、原始完整 patch 和阶段计划都是历史来源；活动范围以最终 `prd-golden.md` 和发布绑定为准。Golden 与制作证据供出题方/评审方使用，不能被任务准备脚本复制进待测 Agent 工作区。

## 与第三步的交接

[第三条 workflow](../golden_documents/README.md) 读取本步的最终 PRD、范围映射、code/test patch 身份、目标树、接口/生成链、选择集、校准报告和发布绑定，生成其他 Golden 文档。本步不提前编写 TDD 或 Golden 测试用例文档。
