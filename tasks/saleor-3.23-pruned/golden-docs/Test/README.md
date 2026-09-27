# Golden Test 产物

- `test-cases.v1.csv`：依据当前精简 PRD、TDD 和历史剪枝边界编写的 65 条场景级测试用例。当前精简 PRD（`../PRD/prd-golden.md`）将保留需求拆解为更细的验收条件；CSV 以业务场景聚合多个相关条件，并额外保留 R07/R11 删除边界回归，不声称对每条细化 AC 一一对应。
- `test-patch-traceability.md`：Golden 测试设计与当前标准包 test patch 的充分性、必要性双向审计。

验证基线为 architecture-upgraded Agent base 与配对的剪枝 patch。Base 和 Target 使用同一份最终 test patch，Target 再增加最终 code patch。重新校准后的冻结选择为 F2P `5365`、P2P `15013`；当前结果为 F2P `5365/5365`、P2P `15013/15013`、reward `1`。R07/R11 的测试仅验证已删除入口不会恢复，不把它们计入当前产品需求数量。

测试 patch 与生产 code patch 成对交付；Base 阶段应用 environment 和最终 test patch，Target 阶段使用同一 test patch 并增加最终 code patch。完整 SHA、commit 和选择清单见同包 `../evidence/`。
