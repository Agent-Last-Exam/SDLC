# Golden 测试设计与 Test Patch 双向追踪审计

版本：golden-v2  
日期：2026-09-26  
测试用例：`test-cases.v1.csv`  
依据：精简 Golden PRD v2（`../PRD/prd-golden.md`）、历史追踪 PRD（`../PRD/prd.md`）、Backend/Frontend Design golden-v2、Interface Contract golden-v2

## 1. 审计结论

本次完成了两个方向的设计审计和运行验证：

1. 充分性（需求 -> 测试）：精简 PRD 的 16 个保留需求被拆解为更细的验收条件，CSV 使用 65 条场景级用例聚合验证相关条件；R07、R11 仅保留删除边界回归，不作为当前产品需求。测试设计与 BD/FD/I 编号关联，但不是对每条细化 AC 的机械一对一映射。现有 test patch 对保留业务主线有广泛自动化证据，但对三个“UI/功能不存在”的剪枝边界缺少专用负向自动化断言：R07 异步媒体 fallback、R11 Variant Generator UI、R13 独立 metadata dialog UI。
2. 必要性（测试 -> 需求）：test patch 的业务测试族可回溯到当前保留需求 R01-R06、R08-R10、R12-R18；fixture、测试框架和生成适配可回溯到执行依赖或 P2P 回归。不能直接由精简 PRD 解释的测试主要是架构升级回归，不应伪装成业务需求，但可作为升级后基线的兼容性保护。

配对剪枝 patch 已按 Base/Target 使用同一份最终 test patch 的标准重新校准并完成评分：F2P `5365/5365`、P2P `15013/15013`、reward `1`。测试设计仍保留一个透明限制：R07、R11、R13 的“功能不得恢复”主要由删除后的代码面、schema/路由边界和回归集合共同证明，没有为每个删除面都建立独立端到端负向用例。

## 2. 实际基线

使用的标准包：

```text
tasks/saleor-3.23-pruned/（正式配对 Golden Harbor）
```

| 仓库 | Upstream base | 实际 Agent base | 剪枝后 target |
| --- | --- | --- | --- |
| Core | `6cfb77430ddbc53f48dfd3462fbefaad4e8c3d45` | `c864e66b8e537d30732ddba62d3a4c47e49e4a3e` | `0b4ecb1130bcc42aad5facd1657f088ed0d7b7ac` |
| Dashboard | `e934ff0abf5e643d2e8eab5cce609387fe0e37b6` | `aebb2401b5079fbbb8c60150289d1896c108feca` | `8e16e2dc3fa083aceef5bc99b46e73be86573dfe` |

实际 Agent base 已包含 environment/architecture patch：Core 的 Python 依赖文件已经升级；Dashboard 已完成 npm 到 pnpm 及依赖/测试配置升级。`upstream_base` 只表示更早的来源版本，不是 Agent 开始实现时的工作树。

## 3. Patch 清点

| Patch | SHA-256 | 文件数 | 增加 | 删除 | `git apply --check` |
| --- | --- | ---: | ---: | ---: | --- |
| `tests/saleor.test.patch` | `1f544aa7a18f316f6e9df997b4da0bd35be24eea4671b025b4368d3fa3599e80` | 435 | 44,282 | 26,427 | 通过 |
| `tests/saleor-dashboard.test.patch` | `14488c9b7e8127976f2ab8abfd78543185d2e48979d005965906358db4456bae` | 470 | 29,920 | 5,328 | 通过 |

Patch manifest 已记录 code/test 双顺序组合到同一 combined tree；运行证据另见 `../evidence/verification-summary.md` 与 `../evidence/reward.json`。

## 4. 需求到 Test Patch 的充分性

| 需求 | Golden 用例 | Test patch 主要证据 | 判定 |
| --- | --- | --- | --- |
| R01 | TC001-TC004 | `graphql/shipping/.../test_delivery_options_calculate.py`；`graphql/checkout/.../test_checkout_delivery_method_update.py`；`checkout/tests/test_delivery_context.py` | 充分 |
| R02 | TC005-TC008 | `giftcard/tests/test_gateway.py`；payment transaction mutation tests；Dashboard `OrderTransactionGiftCard`、`OrderUsedGiftCards` tests | 充分 |
| R03 | TC009-TC011 | `graphql/payment/tests/queries/test_transactions*.py`；target schema 与 Dashboard generated contract | 充分，须保留 schema 负向校验 |
| R04 | TC012-TC014 | password/token mutation tests；staff login E2E；Dashboard `LoginPage.test.tsx` | 充分 |
| R05 | TC015-TC018 | `warehouse/tests/test_stock_availability.py`；checkout/order/fulfillment tests；channel warehouse tests | 充分 |
| R06 | TC019-TC022 | checkout search indexing/loaders；gift-card/order search tests；Dashboard SearchInput/modal search tests | 充分，Page/User 负向主要依赖 schema 合同 |
| R07 | TC023 | 保留的 product media create/bulk tests 与既有同步媒体 E2E | 部分充分：缺少 pending/503/proxy 和 fallback UI 不存在的专用断言 |
| R08 | TC024-TC028 | manifest validation/install/query tests；Dashboard extension manifest、form、popup、catalog tests | 充分 |
| R09 | TC029-TC032 | `checkout/tests/test_tasks.py`；automatic completion Core E2E；Dashboard automatic-completion handler/warning/validation tests | 充分 |
| R10 | TC033-TC036 | Dashboard `ProductDoctor/**` tests；Core stock/preorder availability tests | 充分 |
| R11 | TC037 | 普通 variant create/bulk/required-attribute tests 与 product E2E | 部分充分：缺少 Generator 路由、菜单和任务不存在的专用断言 |
| R12 | TC038-TC041 | order capture/refund/mark-as-paid tests；Dashboard payment summary、transaction、refund tests；orders E2E | 充分 |
| R13 | TC042-TC044 | checkout/draft order shipping metadata tests；meta mutations；Dashboard basic metadata tests | 部分充分：Core snapshot 充分，独立 dialog/路由不存在缺专用断言 |
| R14 | TC045-TC048 | ConditionalFilter、Assign*Dialog、list filters、export、SearchInput tests；Playwright list flows | 充分 |
| R15 | TC049-TC052 | checkout/order webhook subscription/static payload tests；async transport/promise/circuit-breaker tests；Dashboard webhook alert tests | 充分 |
| R16 | TC053-TC056 | `core/editorjs/tests/**`、URL cleaner tests、OIDC plugin tests、password mode tests | 充分 |
| R17 | TC057-TC062 | Federation resolver/schema、staff delete、attribute/input、export、tax permission 和 order query tests | 充分 |
| R18 | TC063-TC065 | channel/site loading、weight/media/discount/order history、draft order unit/E2E tests | 充分 |

充分性统计：65 条场景用例均有测试设计；当前 16 个保留需求均有对应测试族，R07、R11 的历史删除边界和 R13 独立 dialog 删除边界作为附加回归。R07、R11、R13 的边界证据部分充分，不表示生产功能错误，而是现有 test patch 未用自动化测试锁定完整的“已删除能力不能恢复”边界。

## 5. Test Patch 到需求的必要性

### 5.1 A 类：直接业务验收，必须保留

这些测试验证当前保留需求 R01-R06、R08-R10、R12-R18 的可观察行为，包括 delivery、gift card transaction、password mode、warehouse-channel availability、主体搜索、App Extension、automatic completion、Product Doctor、订单支付、metadata snapshot、Webhook、EditorJS/OIDC、GraphQL validation 和 Dashboard 工作流。删除任何测试族前，必须证明对应场景仍由同层级或更高层级测试覆盖。

### 5.2 B 类：跨模块回归，必须保留为 P2P

例如 checkout/order/payment/discount/tax/fulfillment 的旧行为、普通 variant create、同步媒体、基础 Page/User 搜索、legacy payment 兼容和权限边界。这些不是新增需求，但变更触达共享模块；它们用于证明升级没有破坏 PRD 明确要求保留的行为。

### 5.3 C 类：测试执行基础设施，属于架构升级必要项

Dashboard 的 Vitest/Jest/Storybook/Playwright、pnpm、mock 和 test utility 适配，以及 Core fixture、E2E helper、schedule/SQS/runtime 适配，不是业务需求。它们的必要性来自“升级后的 Agent base 能收集并执行测试”，不能在 PRD 中新增虚假功能条目。当前 patch 中至少可识别 29 个 Dashboard 和 34 个 Core 基础设施/运行适配文件；这些数字只用于说明规模，不替代逐项 code review。

### 5.4 D 类：已剪枝功能的测试

正向测试必须删除或改写，负向边界测试必须保留。当前 Core test patch正确新增：

```text
saleor/graphql/app/tests/test_app_problems_removed.py
```

该测试断言 `AppProblem`、`App.problems`、`appProblemCreate` 和 `appProblemDismiss` 不在 schema。Dashboard `useAppsAlert.test.ts` 已改为只验证 webhook failure，不再依赖 App Problems。这是必要的剪枝回归保护。

### 5.5 不能证明必要的项目

当前未发现配对的剪枝 test patch 中仍存在 App Problems 正向测试文件。对其余宽泛的 3.23 架构回归测试，单凭 PRD 无法证明每一个 case 的业务必要性；其保留依据是 P2P 选择和共享模块风险。如需进一步缩减，只能基于覆盖等价、运行结果和 mutation/risk 分析删除，不能按“未直接命中 AC”批量删除。

## 6. 冻结选择与运行结果

| 集合 | 冻结条数 | 通过 | 状态 |
| --- | ---: | ---: | --- |
| F2P | 5,365 | 5,365 | 通过 |
| P2P | 15,013 | 15,013 | 通过 |
| 合计 | 20,378 | 20,378 | 评分集合内失败、跳过、pending、other 均为 0 |

`reward.json` 的 reward 为 `1`；CTRF 汇总为 `20378/20378`。结果 SHA-256、selection SHA 和原始证据位置记录在 `../evidence/verification-summary.md`。

## 7. 残余限制

1. R07、R11、R13 的删除边界没有为每个 UI/路由面分别增加独立端到端负向用例；当前证据来自代码面删除、合同审计及剩余回归集合。
2. `saleor-standard-20260926-01` 仍不是本 Golden 文档的配对实现：其 patch SHA 与未剪枝 Candidate 相同。正式配对实现是 `saleor-standard-20260927-01`，不得用旧包的 `3002/17647` 结果替代本文的剪枝验证结果。
3. 正式 Harbor 包已使用同一份最终 test patch 构造 Base/Target，并由官方 exporter 生成。交付身份与实际 C/D tree 见 `../evidence/harbor-delivery.json`。

## 8. 当前状态

状态：Golden 测试设计已冻结；需求到测试、测试到需求的双向审计已完成；配对剪枝 patch 的 F2P/P2P 运行验证通过；`saleor-standard-20260927-01` 已完成正式配对。
