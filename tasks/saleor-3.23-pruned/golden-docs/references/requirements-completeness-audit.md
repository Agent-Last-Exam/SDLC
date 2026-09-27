# Base -> Target 需求完整性审计

> 本文记录初始 base -> target 需求识别和完整性审计，包含已删除候选功能的分析。当前剪枝后的产品范围以 `../PRD/prd-golden.md` 为准；这里的 R07、R11 及已删子范围只用于审计追踪，不构成当前活动需求。

## 1. 审计结论

当前需求文档没有发现一块未被识别的、足以改变主体范围的大型业务域。Checkout 配送、库存、支付/礼品卡、自动完成、搜索、媒体、App Extension、Dashboard 订单操作和安全/API 变化均有对应条目。

但是，原 R 清单中有四类内容描述过于粗略，不能直接用于后续剪枝。它们已补充为子需求，后续必须作为独立合同审查：

1. App 安装与 manifest 兼容行为，归入 R08。
2. App Extension marketplace/self-hosted 目录行为，归入 R08。
3. Webhook 新事件与 deferred/Promise payload 合同，归入 R15。
4. GraphQL 权限、查询筛选和输入约束，归入 R17。

另外，Checkout/Order 并发、死锁、缓存和任务重试修复被识别为可靠性修复，不应因为不属于“主体业务功能”而回退。依赖升级、CI、生成产物、SDK 搬迁和 telemetry 被识别为基础设施或内部实现，不作为可删除业务需求。

因此，当前文档可以作为下一轮剪枝的需求基线，但剪枝时必须使用本审计中的补充子需求和分类，不得只按旧 R 标题删除。

## 2. 审计范围与方法

审计输入：

| 对象 | 结果 |
| --- | --- |
| Core | Base `6cfb77430ddbc53f48dfd3462fbefaad4e8c3d45` -> Target `e11a5557eff29fbb2eed36e6ff3cd0af08ab9e10` |
| Dashboard | Base `e934ff0abf5e643d2e8eab5cce609387fe0e37b6` -> Target `61a3c045f7d7aba8dc343563757fdfdd249cd656` |
| 生产变更路径 | Core 602 个非测试/非纯生成路径；Dashboard 3,184 个非测试/非纯生成路径 |
| migration | Core 全部新增/修改 migration 逐项检查 |
| GraphQL/API | schema、type、query、mutation、enum、deprecation 和 generated output 检查 |
| 测试 | Core 476 个、Dashboard 387 个测试相关变更路径检查 |
| Git 参考 | Core target-side 240 个提交、Dashboard target-side 331 个提交标题与高风险提交 diff stat 交叉核对 |

判定顺序：

1. 先以 code patch/test patch 识别用户、API、数据和运行时行为。
2. 用 migration 和 schema 检查是否存在持久化或公开合同。
3. 用测试 patch 确认输入、输出、错误和边界条件。
4. 用 Git commit 只做主题交叉核对，不把 commit 标题直接当作 PRD。
5. 将无法映射的变更分为业务合同、可靠性/安全修复、内部实现或基础设施；只有第一类才需要新增需求条目。

## 3. 需求覆盖矩阵

| 变更域 | 现有需求 | 覆盖状态 | 备注 |
| --- | --- | --- | --- |
| Checkout delivery、shipping method 迁移、stale/invalid 问题 | R01 | 已覆盖 | 包含 migration、GraphQL 和同步/Promise webhook 关系 |
| Gift card Transaction API、退款、事件和 Dashboard 展示 | R02 | 已覆盖，需补事件子项 | `USED_IN_ORDER`、`REFUNDED_IN_ORDER` 和 transaction detail 属于同一支付合同 |
| Transaction where/sort、PSP reference | R03 | 已覆盖；阶段 04-A 部分剪枝 | date/event where、sorting 和专用索引已删除；基础 query、ID/PSP/app where 保留 |
| Password login mode、OIDC compatibility、密码失效 | R04/R16 | 已覆盖 | 安全行为不能作为普通无关 UI 删除 |
| Warehouse-channel stock availability | R05 | 已覆盖 | 跨 checkout/order/fulfillment/product 调用链 |
| Search vectors、tsearch、accent、email/domain、gift-card suffix、checkout/page/user search | R06 | 已覆盖；阶段 04 已冻结 | Page/User vector/rank 已删除；Base 搜索及 Checkout/Gift Card/Product/Order 搜索作为主线保留 |
| Async external media、MIME/provider/503、Dashboard fallback | R07 | 已覆盖；阶段 03 已剪枝 | 异步/pending/fallback 合同已删除；Base 同步 `mediaUrl` 合同保留 |
| AppExtension 新字段、migration、双向表单、mount point、popup action | R08 | 已覆盖，需补安装和目录子项 | 见第 4 节 |
| Automatic checkout completion 和 channel settings | R09 | 已覆盖 | 包括 retry、cutoff、delay、legacy gift-card 配置边界 |
| Product Doctor | R10 | 已覆盖 | 与库存/可售性主链有直接关系，默认保留 |
| Variant Generator、required attributes、hasVariants 弃用 | R11 | 已覆盖 | Dashboard 主功能，Core 只保留必要合同 |
| Order payment/transaction redesign、capture、gift-card payment display | R12 | 已覆盖 | 仅 Dashboard UI 可按范围拆分，不能删除 Core 支付合同 |
| Metadata dialogs 和 shipping metadata denormalization | R13 | 已覆盖，必须拆分 | UI 可选；Core metadata 固化属于订单数据合同 |
| Dashboard list/filter/navigation fixes | R14 | 已覆盖为缺陷修复 | 不应整批回退；逐项判断是否会恢复已知 bug |
| Deferred/Promise webhook payload、事件、调用次数和 circuit breaker | R15 | 已覆盖，需补新事件子项 | 见第 4 节 |
| EditorJS/OIDC/密码等安全行为 | R16 | 已覆盖 | 不属于普通无关功能 |
| Scalars、Federation、权限、where 查询、deprecated/removal API | R17 | 部分覆盖，需补 API 子项 | 见第 4 节 |
| 其余 Dashboard 配置/展示 | R18 | 聚合项，不能直接剪 | 逐项拆为功能、缺陷修复或基础设施 |

## 4. 必须补入需求文档的子需求

### R08-A App 安装与 manifest 兼容

Target 还改变了以下 App 安装合同：

- manifest 可以不提供 `tokenTargetUrl`；安装流程不应因为缺少该字段而失败。
- 重复 identifier 使用稳定的唯一性错误，而不是未分类异常。
- 不需要时不返回新建/安装 App token，避免无必要的敏感信息暴露。
- AppExtension 数据迁移需要兼容 migration 前后格式，并支持新字段过滤。

证据包括 Core 的 `installation_utils.py`、manifest validation、install/create command 和对应测试。该子项不能因“App Problems 已删除”一起删除；二者是不同功能。

### R08-B App Extension marketplace 与 self-hosted 目录

Dashboard 对 self-hosted 场景提供静态 extensions catalog，并移除旧的 marketplace URL 环境变量；Explore Extensions 页面、扩展筛选和配置入口仍属于 App Extension 生态合同。删除 R08 时必须明确是否连同该目录能力一起删除，不能只删除表单双向同步。

证据：`src/extensions/data/extensions.json`、Explore Extensions hooks/view、运行配置和对应测试。

### R15-A Webhook 事件与 payload 合同

除 deferred/Promise 实现外，Target 新增或改变了可观察的 webhook 行为：

- `PRODUCT_VARIANT_DISCOUNTED_PRICE_UPDATED` 事件。
- 订阅 payload 的事件信息结构和每个 App 的隔离处理。
- order、fulfillment、checkout 的 deferred payload、sync/async 调用次数和 circuit-breaker 错误边界。
- gift-card、transaction 等事件的业务触发条件。

这些是外部 App 可观察的 API 合同，不能按“内部异步重构”整体删除。

### R17-A GraphQL 权限、查询和输入约束

现有 R17 需要显式包含：

- `HANDLE_TAXES` 权限下 Checkout/Order 的 `privateMetadata` 和 `user` 可见性。
- `user.orders(where=...)` 及订单查询过滤/排序扩展。
- list resolver 分页修正。
- `NonNegativeInt`、Federation representations 非空约束、Attribute 非空字段。
- export/digital-content/旧支付插件等 deprecated/removal 合同。

这些变化属于 API 使用方合同；即使没有新的 Dashboard 页面，也不能按无关 UI 删除。

## 5. 高风险但非新增业务需求的变化

以下变更已核对，但不单列为可剪枝业务功能：

| 类别 | 例子 | 处理原则 |
| --- | --- | --- |
| 安全/可靠性 | checkout/order 死锁、竞态、缓存、数据库 replica 等待、任务提前结束 | 保留并以回归测试保护 |
| 兼容清理 | Adyen/NP Atobarai 删除、digital content 旧 API 删除、旧字段 deprecation | 保留 Target 的清理，除非产品明确要求恢复旧 API |
| 内部 GraphQL/序列化 | executor、orjson、metrics、deprecated-field monitoring、query limits | 不作为业务剪枝目标；需要单独的性能/安全决策 |
| SDK/前端架构 | legacy SDK 搬迁、ordersV2 清理、page code splitting、React strict、pnpm | 视为实现或构建基础设施 |
| 依赖/CI/发布 | Django/Node/Valkey/lockfile、workflow、Chromatic、Sentry/OTel/telemetry | 不进入 PRD 剪枝清单 |
| 小型 UI 缺陷修复 | Category breadcrumbs、search tooltip、默认商品状态、列表筛选、订单历史显示 | 逐项标为缺陷修复；不能整批回退 |

## 6. 未映射项处理结果

审计没有留下“未解释的大型生产变更”。存在的未独立列项内容均落入以下三个可解释类别：

1. 已有 R 的子项，尤其是 R08、R15、R17、R18。
2. 安全、可靠性、兼容清理或缺陷修复，不是可选业务功能。
3. 生成代码、依赖、CI、SDK 和 telemetry 等内部/基础设施变化。

## 7. 累计剪枝状态

需求完整性审计描述的是原始 `Base -> Target` 全量变化；累计交付会在此基础上按已批准边界删除弱关联功能。截至阶段 04-B2：

- R13-A metadata 独立编辑 UI 已剪枝，订单/履约 metadata 数据合同保留。
- R11 Variant Generator 已剪枝，普通变体、required attributes、`hasVariants` 和必要 Core 合同保留。
- R07 异步外链图片抓取、pending proxy/503 和 Dashboard fallback 已剪枝；同步 `mediaUrl` 图片下载、本地上传和外部视频/oEmbed 保留。
- R03 transaction date/event where、sorting 和四个专用索引已剪枝；根级 query、`TransactionWhereInput`、ID/PSP/app where 及 R02/R12 支付合同保留。
- R06 Page/Model 的 search vector、dirty task、属性/PageType 扩展命中、相关度排序和 migrations `0032`-`0035` 已剪枝；`pages(search:)`、Base title/slug/content 搜索、Page CRUD/EditorJS 和 Product 对 Page reference title 的索引一致性保留。
- R06 User search vector、GIN、prefix/relevance、`RANK` 和 migrations `0096`-`0098` 已剪枝；Base `search_document`、客户/员工 search API、账户/OIDC 和 Order email vector helper 保留。
- R06 的 Checkout、Gift Card、Product、Order 搜索子域经边界复核确认为结账、支付、商品可售和订单操作主线的强关联能力，批准保留；阶段 04 在 04-B2 已验收 tree 冻结，不再建立后续剪枝子阶段。

这些状态改变“最新累计交付包含什么”，不改变本审计对原始 Target 需求覆盖完整性的结论。

若后续发现某个变更不能归入上述三类，必须在继续剪枝前新增 `UNMAPPED-*` 条目，并暂停删除；禁止用“代码量小”作为忽略理由。

## 8. 下一步使用规则

- 将本审计作为 [base-to-target-requirements.md](base-to-target-requirements.md) 的补充，而不是重排已有 R 编号。
- R06 App Problems 保持历史编号并标记为已排除；后续不复用 R06 编号。
- 剪枝决策按“功能名称 + 子需求 ID”记录，不按文件路径或 commit 标题记录。
- 每一轮删除前，先确认该子需求是独立新增能力，而不是主体依赖、安全修复、兼容清理或缺陷修复。
- 每轮删除后，重新审计 schema、migration、测试 ID 和生成文件；全部累计 F2P/P2P 通过后才能固化父快照。
