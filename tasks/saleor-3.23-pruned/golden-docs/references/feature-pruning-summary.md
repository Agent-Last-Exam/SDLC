# Saleor 3.23 功能剪枝与代码规模摘要

## 1. 文档目的

本文说明从架构升级后的未剪枝 Target 到最终 Golden Target：

- 实际减少了多少代码；
- 删除了哪些用户可见能力及配套实现；
- 哪些相邻能力被明确保留；
- 统计数字如何复核，以及哪些数字不能混为一谈。

本文描述的是功能剪枝，不是 Saleor 3.22 到 3.23 的全部变更。Golden code patch 的总规模同时包含架构升级和保留需求，不能作为剪枝代码量。

## 2. 统计基线与口径

权威统计直接比较以下四个 Git combined tree，均包含 code patch 和 test patch 应用后的版本：

| 仓库 | 未剪枝 Target tree | 最终剪枝 Target tree |
| --- | --- | --- |
| Saleor Core | `dcbfb3104aefc53a42341bc5e8e1d4d4ba48e1ad` | `0b4ecb1130bcc42aad5facd1657f088ed0d7b7ac` |
| Saleor Dashboard | `c6118fb692f8811654c2f955545403d49efa8cf8` | `8e16e2dc3fa083aceef5bc99b46e73be86573dfe` |

最终 tree 与 `../evidence/golden-patch-manifest.json` 记录的交付 target 一致。Dashboard 未剪枝统计基线是在 incoming Candidate combined tree `0173eb8fa4e64158817f5de80a7246ac05b573c0` 上补齐同样的 22 行 Fabbrica codegen outputs 后得到的规范化 tree。这样比较只反映功能剪枝，不把 Candidate 的生成配置遗漏误算为剪枝差异。

本文采用 Git diff 行数口径：

- **删除行**：未剪枝 Target 中存在、最终 Target 中不存在或被替换的行。
- **恢复/适配新增行**：剪枝时为恢复 Base 行为、保留共享能力、增加负向契约或重新生成产物而加入的行。它不表示新增了另一项业务功能。
- **净减少**：删除行减去恢复/适配新增行。
- **文件数**：最终两个 tree 直接比较得到的去重文件数；重命名按 Git rename detection 处理。

## 3. 最终代码规模

| 仓库 | 变化文件 | 恢复/适配新增 | 删除 | 净减少 |
| --- | ---: | ---: | ---: | ---: |
| Saleor Core | 141 | 7,684 | 14,494 | 6,810 |
| Saleor Dashboard | 130 | 15,482 | 24,688 | 9,206 |
| **合计** | **271** | **23,166** | **39,182** | **16,016** |

因此，对“剪切了多少代码”的直接回答是：

> 功能剪枝共删除 39,182 行，同时恢复或适配 23,166 行，净减少 16,016 行，涉及 271 个文件。

这个数字包含生产代码、测试、migration、GraphQL schema 和 Dashboard 生成文件。它是最终 tree 的去重结果，也是本文推荐引用的交付数字。

### 3.1 为什么删除很多，同时也新增很多

剪枝不是简单删除目录。为了让剩余系统仍可构建、迁移和测试，需要恢复旧实现、调整调用方、保留共享合同并重新生成派生产物。

三份 GraphQL schema 文件的重新生成占了大部分表面行变更：

| 范围 | 恢复/适配新增 | 删除 | 净减少 |
| --- | ---: | ---: | ---: |
| Core `saleor/graphql/schema.graphql` | 6,852 | 7,204 | 352 |
| Dashboard `schema-main.graphql`、`schema-staging.graphql` | 13,834 | 14,232 | 398 |
| **三份 schema 合计** | **20,686** | **21,436** | **750** |
| **排除三份 schema 后** | **2,480** | **17,746** | **15,266** |

这说明 23,166 行“新增”中的 20,686 行是 schema 重新生成产生的替换行，而不是新增业务。排除这三份大 schema 后，其他源码、测试、migration 和生成文件合计净减少 15,266 行。Fabbrica 的 22 行配置在未剪枝和剪枝两侧都存在，因此不进入功能剪枝增删统计。

## 4. 各剪枝阶段的操作量

下表用于解释每个功能阶段做了多少操作。它按阶段增量 patch 或冻结提交统计；同一文件可能在多个阶段重复修改，因此阶段合计不是最终去重数字。

| 阶段 | 仓库 | 触及文件 | 新增 | 删除 | 净减少 |
| --- | --- | ---: | ---: | ---: | ---: |
| App Problems | Core | 28 | 6,867 | 10,042 | 3,175 |
| App Problems | Dashboard | 60 | 14,177 | 17,806 | 3,629 |
| R13-A 独立 Metadata UI | Dashboard | 37 | 1,237 | 2,409 | 1,172 |
| R11 Product Variant Generator | Dashboard | 35 | 68 | 4,334 | 4,266 |
| R07 外部图片异步能力 | Core | 22 | 350 | 1,292 | 942 |
| R07 外部图片异步能力 | Dashboard | 7 | 3 | 148 | 145 |
| R03 Transaction 增强查询 | Core | 10 | 4 | 1,181 | 1,177 |
| R06 Page 增强搜索 | Core | 43 | 133 | 1,498 | 1,365 |
| R06 User 增强搜索 | Core | 46 | 332 | 487 | 155 |
| **阶段操作量合计** |  | **288 次文件触及** | **23,171** | **39,197** | **16,026** |

阶段合计与最终去重结果相差 10 行净值，是因为阶段是连续累积的：前一阶段修改过的 schema、测试或适配代码可能在后一阶段再次修改。对外说明总体规模时应使用第 3 节的 **净减少 16,016 行**；排查单个阶段时使用本表。Fabbrica 配置恢复属于 Harbor 完整性修复，不计入任何剪枝阶段。

## 5. 已删除功能

### 5.1 App Problems

删除 App 问题上报、聚合、展示和关闭处理的完整业务链路：

- Core 的 `AppProblem` 数据模型、错误类型、对象锁和相关 migration；
- GraphQL 的问题类型、枚举、查询字段、创建和 dismiss mutation；
- Dashboard 已安装扩展页的问题列表、数量 badge、严重性、时间信息和 dismiss 交互；
- 对应 dataloader、fixture、正向测试、Story、文案、Ripple 和生成 GraphQL 符号。

保留边界：Webhook delivery failure 告警是独立运维能力，仍保留。新增负向契约测试只用于防止 App Problems 字段重新进入 schema，不代表恢复该功能。

### 5.2 R13-A 独立 Metadata Dialog/UI

删除 Target 新增的订单、履约和仓库独立 metadata 弹窗及其入口：

- 通用 Metadata Dialog 及表单、校验、提交 hooks；
- Order、Order Line、Fulfillment、Warehouse 的新增弹窗入口；
- 专用路由、Ripple 和组件测试。

保留边界：恢复 Base 已有的订单详情 inline metadata 和订单行 metadata 操作；Core metadata API、数据库字段、shipping metadata denormalization 以及主体仍使用的共享控件不删除。

### 5.3 R11 Product Variant Generator

删除 Dashboard 商品详情中的批量变体组合生成器：

- Variant Generator 页面组件、矩阵、默认值和 required-attribute 配置 UI；
- 批量生成状态、任务衔接、商品页入口和批量处理接入；
- 专用 Ripple、文案、locale、changelog 和工具测试。

保留边界：普通单变体创建、required attributes 领域约束、`hasVariants` 兼容行为、Core schema/migration，以及普通 datagrid 仍使用的 bulk-create mutation 保留。

### 5.4 R07 外部产品图片异步下载与 Dashboard 失败回退

删除 Target 新增的异步外链图片抓取链路：

- Core 异步下载 task、queue/provider 和 pending external image 状态；
- pending 图片的 thumbnail/original 503 行为与原图 proxy；
- Dashboard `MediaWithFallback`、失败回退展示、Story 和文案；
- 专用 fixture、测试与 HTTP cassette。

保留边界：Base 已有的同步 `mediaUrl` 下载、`productMediaCreate`、`productBulkCreate`、本地文件上传、外部视频/oEmbed 和 Dashboard 外链上传入口保留。

### 5.5 R03 Transaction 日期/事件筛选和排序

删除 Transaction 查询的独立增强条件：

- `createdAt`、`modifiedAt` 筛选；
- transaction event type/date 条件；
- `sortBy` 及对应 sorter；
- 四个专用数据库索引、叶子 migration `payment.0072` 和专项测试。

保留边界：根级 `transactions` 查询、`TransactionWhereInput`、ID/PSP/app 条件、基础索引，以及支付和订单交易主链全部保留。

### 5.6 R06 Page 增强搜索

删除 Page 的全文向量化搜索增强：

- Page search vector、dirty flag、后台索引任务和 GIN/相关 migration；
- 属性及 PageType 触发的 dirty 传播；
- relevance/prefix/`RANK` 行为和专用测试。

保留边界：`pages(search:)` API、Page CRUD、EditorJS，以及 Base 的 title/slug/content 搜索保留；Product 搜索引用 Page title 的索引能力也保留。

### 5.7 R06 User 增强搜索

删除 Customer/Staff User 的全文向量化搜索增强：

- User search vector、GIN 索引和 migrations `0096` 至 `0098`；
- dirty/index 更新链路；
- prefix、relevance、`RANK` 行为和专项测试。

保留边界：客户和员工 search API、Dashboard 客户/员工调用方、账户与 OIDC 能力、客户属性，以及 Order 搜索仍使用的 email vector helper 保留；基础 `search_document` 行为恢复为 Base 实现。

## 6. 明确保留的业务范围

本轮不是按模块大小删除功能，而是按“与主体业务链路的关联性”判断。最终继续保留：

- Checkout、配送、库存、支付、自动完成订单和 Dashboard 订单操作主线；
- Checkout、Gift Card、Product、Order 的增强搜索；
- App Extension 安装和 manifest 兼容、Webhook 与公开 GraphQL/API 合同；
- 密码安全、OIDC、EditorJS、安全清理和兼容行为；
- 并发、死锁、缓存、数据库副本等待、任务重试等可靠性修复；
- 普通商品变体创建、基础 Transaction 查询、Page/User 基础搜索；
- 与上述保留能力共用的模型、字段、migration 和生成合同。

## 7. 测试变化如何理解

删除功能后，对应的正向测试、fixture、Story 和 cassette 也必须删除，否则测试仍在要求系统提供已经明确排除的能力。与此同时，保留功能的回归测试和必要的负向契约继续存在。

因此：

- 删除测试行属于剪枝实现的一部分，但不等于生产功能本身减少的行数；
- F2P/P2P 名单中删除某个 ID，必须能追溯到已删除功能，不能仅为制造通过结果；
- 最终 Harbor 的重新校准结果为 F2P `5,365/5,365`、P2P `15,013/15,013`、reward `1`；这证明冻结选择通过，不表示仓库中的每一个测试都属于剪枝验收范围。

## 8. 复核方法与证据

核心证据：

- `../evidence/golden-patch-manifest.json`：最终 patch SHA、combined tree 和 evaluation base；
- `pruning-order-workflow.md`：各阶段删除边界、tree 和验收结论；
- `stage-02-r11-variant-generator.md`、`stage-03-r07-external-media.md`、`stage-04-r03-transaction-query.md`、`stage-04-b1-r06-page-search.md`、`stage-04-b2-r06-user-search.md`：阶段明细；
- `../Test/test-patch-traceability.md`：测试与保留/删除需求的双向追踪；
- `../evidence/verification-summary.md`：最终 F2P/P2P 验证结果。

最终规模通过 Git tree 直接比较得出，而不是通过 Golden patch 总行数反推。复核时应开启 Git rename detection，避免把纯文件移动重复计算为等量新增和删除。
