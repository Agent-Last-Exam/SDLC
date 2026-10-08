# 从完整版本变化反向提取未剪枝 PRD

本目录提供 case 制作的第一条 workflow：从固定的完整 Base/Target、生产与测试差异中，提取未剪枝的产品需求和可观察验收条件，并交付可审计的需求基线。

适用于单仓库、多仓库、不同语言和不同接口协议。仓库、环境、测试框架与生成工具由输入配置提供；流程不依赖某个项目的业务名称、目录布局或测试数量。

## 使用入口

1. 阅读 [workflow.md](workflow.md)，按阶段执行。
2. 按 [data-contracts.md](data-contracts.md) 填写输入与审计清单。
3. 将 [templates/inputs.json](templates/inputs.json) 复制到独立运行目录，填入真实配置。模板中的空值和占位字符串不是可执行配置。
4. 按 `inputs.json` 指定的 PRD 模板写文档；[templates/prd.md](templates/prd.md) 提供本仓库既有 Atlassian 模板的业务写作版本。
5. 用需求追踪和审计材料完成双向核对，再冻结输出。
6. 将冻结的运行记录归档到最终 Harbor 包的 `golden-docs/evidence/reverse-extraction/<run_id>/`，作为随包交付的证据；归档和包版本绑定由第二条 workflow 完成。

目录中的文件是方法与空模板。实际 case 的 PRD、台账和报告写入配置的运行目录，不写回此目录。运行记录最终必须随 Harbor 包交付；执行期间的独立目录是归档前的暂存位置。冻结输入、原始差异、证据和修订历史均归档，临时工作树、依赖缓存等可再建内容留在 `scratch/`。

## 文件说明

| 文件 | 用途 |
| --- | --- |
| [workflow.md](workflow.md) | 执行步骤、完成检查、异常处理、恢复与交付规则 |
| [data-contracts.md](data-contracts.md) | 配置、清单字段、ID、关联和状态的统一定义 |
| [templates/](templates/) | 输入配置、证据、变更、需求、追踪、审计、检查点及 PRD 空模板 |

## 与后续 workflow 的交接

本流程交付完整、未剪枝的 `prd.md`、稳定需求 ID、变更清单、追踪关系、审计报告和输入/输出身份。

最终包内的运行记录是未剪枝阶段的历史证据，不替代剪枝后的活动 Golden PRD。包内索引须绑定 case、run、阶段范围和运行 manifest 哈希，确保移动目录后仍可核对证据。

[第二条 workflow](../feature_pruning/README.md) 据此确认业务主体、决定保留与删除，再生成剪枝后的 Harbor 包。第三条 workflow 基于最终范围及配对实现生成其他 Golden 文档。本流程不提前替后续流程做剪枝，也不生成 Query、技术设计或测试用例文档。

“未剪枝”指保留完整升级中的产品行为变化，包括新增能力、既有行为调整、用户可见修复、弃用与移除；纯内部实现变化仍需分类和审计，但不自动成为产品需求。
