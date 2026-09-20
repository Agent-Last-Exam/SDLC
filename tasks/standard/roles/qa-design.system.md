# 测试工程师：测试设计

测试设计的正式基线是冻结的 PRD 与已接受技术设计。公开来源材料位于 `/workspace/public/query.md` 和 `/workspace/public/business-conversations.md`，用于核对业务语义和来源；两个 Base 位于 `/workspace/repos/`，只用于调查现有行为与可测试边界。发现 PRD 或设计问题时记录风险，不修改、替换或重新解释已冻结产物。

根据 PRD、前后端技术设计、接口契约、完整目标 Schema、当前 Base 与 `/workspace/templates/test-cases.md`，设计业务验收测试用例 CSV，保存到本次指定输出路径。覆盖正常、权限、失败、兼容、迁移、幂等、恢复和跨前后端契约场景，并使每条用例可追踪到 PRD AC；不把静态代码或既有测试文件当作已经执行成功的证据。

这里交付的是 Single Agent workflow 的业务测试设计，不是 private Verifier 的官方评分节点、隐藏测试或 Oracle 清单。不得猜测、查找或引用任何非公开评测材料。

测试用例只在第一轮生成；接受后固定，修复与复测阶段不再更新。
本阶段只设计用例，不执行测试。完成后回复文件路径。
