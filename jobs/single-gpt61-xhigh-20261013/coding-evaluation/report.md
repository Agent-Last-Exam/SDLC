# Single Agent 代码评测与参考答案 Oracle 对照

本次于 2026-10-13 13:57:15–15:06:44 UTC 完成，约 1 小时 9 分钟。Harbor 无模型执行器只应用本次真实 Agent 的冻结补丁；不是参考答案。运行器无异常退出。未跑浏览器 E2E。

参考为 saleor-oracle-20261013-r4 的 post 报告；两者均按本次不含浏览器的同一冻结清单取交集统计。历史 Oracle 整体 Harbor 输出解析失败不等于其选中测试失败，以下是其保存的真实测试报告结果。

| 集合 | 测试组 | 总数 | 参考 Oracle 通过 | 本次 Agent 通过 | 失败 | 错误 | 跳过 | 缺失 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| F2P | core-unit | 4050 | 4050 | 95 | 1005 | 458 | 0 | 2492 |
| F2P | core-e2e | 15 | 15 | 0 | 0 | 0 | 0 | 15 |
| F2P | dash-unit | 1117 | 1117 | 0 | 296 | 0 | 0 | 821 |
| P2P | core-unit | 12760 | 12760 | 12760 | 0 | 0 | 0 | 0 |
| P2P | core-e2e | 210 | 210 | 210 | 0 | 0 | 0 | 0 |
| P2P | dash-unit | 2042 | 2042 | 2039 | 3 | 0 | 0 | 0 |

F2P：95/5182（1.83%）；P2P：15009/15012（99.98%）。正式 reward=0，partial=0.747945；partial 是评分器辅助指标，不能解释为做题通过。

本次基线 F2P 通过 0/5182、P2P 通过 15012/15012。缺失表示测试报告没有该 ID，并非已经实际执行且断言失败；它可能来自测试无法收集/加载或对应实现尚不存在。错误表示 pytest error，官方评分器统一将 error 归为非通过。

95 个 F2P 基线非通过→候选通过；其中有明确基线 failed/error 记录的转通过 95 个，其余基线缺失/跳过转通过不得称为观察到了断言失败转通过。

## P2P 回归（3 个）

- saleor-dashboard.dash-unit.src/utils/handlers/metadataUpdateHandler.test.ts.createMetadataUpdateHandler should call only updateMetadata mutation
- saleor-dashboard.dash-unit.src/utils/handlers/metadataUpdateHandler.test.ts.createMetadataUpdateHandler should call only updatePrivateMetadata mutation
- saleor-dashboard.dash-unit.src/utils/handlers/metadataUpdateHandler.test.ts.createMetadataUpdateHandler should return updatePrivateMetadata errors if exists

## 结论和限制

参考答案三组的选中 F2P/P2P 全通过；本次 Agent 只修复了少量选中 F2P，且引入 3 个 P2P 回归，未通过代码评测。不能由健康检查或文档封存推断完整迁移完成。

本次和历史参考并非同一次同时运行，应保留环境时序差异限制。基线及候选均有 CheckoutDelivery 导入错误、E2E teardown 错误，Dashboard 也有模块加载错误。没有为了评分改测试、安装依赖、修改候选实现或重跑。单测与 E2E 原始统计会包含不入评分的用例及 setup/teardown 记录，因此与本表选中清单计数不同。后续需结合失败证据区分候选未实现的目标能力与测试环境/加载问题，不能把所有缺失直接归为具体业务断言失败。

附件 test-comparison.csv 覆盖 20194 个选中 ID，含基线、Oracle、本次候选及转换标记；p2p-regressions.csv 单列回归。

三项 P2P 回归均位于 metadataUpdateHandler.test.ts：两项预期返回空错误数组，实际返回 GRAPHQL_ERROR；另一项预期透传 privateError1/privateError2，实际也返回同样的通用错误。此处仅记录测试观察，尚未进一步裁定实现与需求是否冲突。
