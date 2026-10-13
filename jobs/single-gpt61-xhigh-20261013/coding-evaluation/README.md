# 本次代码评测结果

使用本次真实 Single Agent 的冻结代码补丁，2026-10-13 完成无模型评测。三组后端单测、后端 E2E、Dashboard 单测；浏览器 E2E 排除。Harbor oracle 执行器仅用于应用本次候选补丁，不是参考实现。

- [最终报告](report.md)：按相同冻结清单对照历史参考 Oracle 与本次 Agent。
- [逐项对照](test-comparison.csv)：20194 个选中测试的基线、Oracle、候选状态。
- [P2P 回归](p2p-regressions.csv)：3 个 Dashboard metadataUpdateHandler 回归。
- [分组汇总](summary.json)：通过、失败、错误、跳过、缺失及转换统计。

本次 F2P 95/5182，P2P 15009/15012，正式 reward=0。参考 Oracle 对上述选中集合全部通过。测试缺失与执行后失败分开；未调用模型，未修改 Agent 代码或冻结测试。没有把全套原始日志/测试数据上传，原始证据仍保留在本机。

此结果晚于原 rollout 的 QA 自检；各 result.json/state.json 仍保留原 rollout 的真实失败状态，不用后续评测覆盖历史。原 rollout 关闭官方 verifier，这次则是独立执行的代码评测。
