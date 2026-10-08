
# Saleor 3.22 -> 3.23 新增需求说明

## 1. 文档目的

本文从冻结交付包中的 production code patch 与 test patch 反向整理 Saleor Core `3.22.0`、Saleor Dashboard `3.22.9` 到两者 `3.23.0` 的新增或改变需求，并给出如下追踪关系：

> 需求与验收行为 -> 实现 patch -> 测试证据 -> 本次实际验证结果

本文描述用户可感知的业务能力、API 合同和 Dashboard 交互变化。纯重构、依赖升级、CI、测试基础设施、遥测实现等内部变化不作为独立需求。

## 2. 基线、证据与方法

| 项目             | Base                                                      | Target                                                    |
| ---------------- | --------------------------------------------------------- | --------------------------------------------------------- |
| Saleor Core      | `3.22.0` / `6cfb77430ddbc53f48dfd3462fbefaad4e8c3d45` | `3.23.0` / `e11a5557eff29fbb2eed36e6ff3cd0af08ab9e10` |
| Saleor Dashboard | `3.22.9` / `e934ff0abf5e643d2e8eab5cce609387fe0e37b6` | `3.23.0` / `61a3c045f7d7aba8dc343563757fdfdd249cd656` |

主要证据：

- Core 实现：`standard/solution/saleor.code.patch`，601 个文件。
- Dashboard 实现：`standard/solution/saleor-dashboard.code.patch`，3,104 个文件。
- Core 测试：`standard/tests/saleor.test.patch`，486 个文件。
- Dashboard 测试：`standard/tests/saleor-dashboard.test.patch`，492 个文件。
- Git 历史：`references/git-history/`，仅用于核对意图与提交背景，不作为需求判定依据。

需要注意：base 和 target 是从共同 merge base 分出的并行发布分支，base 不是 target 的直接祖先。因此本文没有把 `base..target` commit 列表直接等价为需求清单，而是以 patch 的最终行为和测试断言为准。

## 3. 验证结果摘要

在 `sdlcbench/saleor-3.23-test:standard-a-20260920` 容器中应用两份 solution code patch，启动 PostgreSQL、Valkey、API、Celery 与构建后的 Dashboard 后执行定向测试。

本次使用的重建镜像如下：

| 镜像                                               | Image ID         | 含义                                  |
| -------------------------------------------------- | ---------------- | ------------------------------------- |
| `sdlcbench/saleor-3.23-base:standard-a-20260920` | `e5d10cd80d48` | base 源码与离线依赖环境               |
| `sdlcbench/saleor-3.23-test:standard-a-20260920` | `41988b6468c0` | base 环境加官方 test patch 和验证工具 |

`test` 镜像不是固化后的 target production 镜像。本文验证的 target 工作树由该镜像启动后，再执行 `solution/apply_patches.py code` 应用 Core 与 Dashboard code patch 得到。

| 验证批次         | 覆盖范围                                                                                   |                               结果 |
| ---------------- | ------------------------------------------------------------------------------------------ | ---------------------------------: |
| V1 Core API      | 显式配送、App Problems、交易筛选/排序、外部媒体、密码登录模式                              |                     `198 passed` |
| V2 Core 领域逻辑 | 直接仓库库存、产品/订单/礼品卡/结账/页面/用户搜索                                          |                     `195 passed` |
| V3 Core 支付     | 礼品卡 Transaction API 的授权、撤销、退款、查询                                            |                      `37 passed` |
| V4 Core 补充     | 自动完成结账、EditorJS、App Extension、员工删除、配送元数据                                |                     `183 passed` |
| V5 Dashboard     | Product Doctor、变体生成器、自动完成配置、App Problems、订单支付、元数据、登录页、翻译扩展 |          `365 passed`，26 suites |
| 合计             | 代表性定向测试                                                                             | **`978 passed`，0 failed** |

生产前端构建成功，API 与 Dashboard 健康检查成功。本次没有运行全部 13,082 个冻结选择测试，也没有运行完整 Playwright E2E；因此“通过”表示下文列出的代表性行为已验证，不表示全量回归结论。

## 4. 新增与改变的需求

### R01 显式计算结账配送选项

**类型：新增功能 + API 行为改变**

**需求与验收行为**

- Storefront 可通过 `deliveryOptionsCalculate` 主动决定何时调用配送相关同步 Webhook，并获得 `CheckoutDelivery` 列表，避免查询字段或地址更新隐式产生不可控的 Webhook 流量。
- `Checkout.delivery` 返回当前选择；旧的 `shippingMethod`、`deliveryMethod` 进入弃用路径。
- 结账变化使已选配送过期时返回 `CheckoutProblemDeliveryMethodStale`；该问题不立即阻止完成，但 `checkoutComplete` 必须重新校验。
- 配送方式已不可用时返回 `CheckoutProblemDeliveryMethodInvalid` 并阻止完成。
- `checkoutDeliveryMethodUpdate.deliveryMethodId` 接受 `CheckoutDelivery` ID，继续接受旧 `ShippingMethod` ID但后者已弃用。

**实现 patch**

- Core：`saleor/graphql/shipping/mutations/delivery_options_calculate.py`、`saleor/checkout/delivery_context.py`、`saleor/graphql/checkout/types.py`、`saleor/graphql/checkout/mutations/checkout_delivery_method_update.py`。
- Schema：`saleor/graphql/schema.graphql`。

**测试证据**

- `saleor/graphql/shipping/tests/mutations/test_delivery_options_calculate.py`
- `saleor/checkout/tests/test_delivery_context.py`
- checkout delivery/problem/complete 相关 GraphQL tests。

**实际验证**：V1 通过。Git 参考：`66b8f9b`、`92f6b36`、`1c76047`、`dc72612`、`1dbb644`。

### R02 礼品卡纳入 Transaction API

**类型：新增支付能力**

**需求与验收行为**

- 礼品卡可作为 Transaction API 的支付方式，对 checkout/order 发起授权或扣款。
- 必须校验礼品卡存在、启用、未过期、币种一致且余额足够；重复初始化同一礼品卡不能造成重复或冲突授权。
- 支持取消 checkout 礼品卡授权，以及对 order 礼品卡扣款退款；礼品卡已删除等异常状态需被明确处理。
- Transaction 查询暴露礼品卡支付方式详情和 `isSaleorGiftCard`，Dashboard 在订单交易中以专用礼品卡样式显示，且相关事件进入礼品卡历史。

**实现 patch**

- Core：`saleor/payment/models.py`、`saleor/payment/gateways/gift_card.py`、`saleor/graphql/payment/mutations/transaction_initialize.py`、`transaction_request_action.py`、`saleor/payment/migrations/0066_transactionitem_gift_card.py`。
- Dashboard：`src/orders/components/OrderTransaction/components/GiftCardPaymentMethod.tsx`、`src/orders/components/OrderTransactionGiftCard/`、gift card history/provider 文件。

**测试证据**

- `saleor/graphql/payment/tests/mutations/test_transaction_initialize.py`
- `saleor/graphql/payment/tests/mutations/test_transaction_request_action.py`
- `saleor/graphql/payment/tests/mutations/test_transaction_request_refund_for_granted_refund.py`
- `saleor/graphql/payment/tests/queries/test_transaction.py`

**实际验证**：V3 的 37 个礼品卡交易测试全部通过；Dashboard 礼品卡专用展示由 patch 测试与静态代码核对。Git 参考：`e2ebabee`、`37fbfd1`、`bf22f8e`；Dashboard `6cbec4c`。

### R03 Transaction 查询支持筛选与排序

**类型：新增 API 查询能力**

**需求与验收行为**

- `transactions` query 支持按 `CREATED_AT`、`MODIFIED_AT` 排序。
- 支持按 transaction 的创建/修改时间范围筛选，也支持按 transaction event 的类型和创建时间筛选。
- 订单 transaction 条件可使用 PSP reference 等字段，组合条件保持 GraphQL `where` 语义。

**实现 patch**

- `saleor/graphql/payment/filters.py`、`saleor/graphql/payment/sorters.py`、`saleor/graphql/payment/schema.py`、`saleor/graphql/schema.graphql`。

**测试证据**

- `saleor/graphql/payment/tests/queries/test_transactions_where.py`
- `saleor/graphql/payment/tests/queries/test_transactions_sorting.py`

**实际验证**：V1 通过。Git 参考：`4d333d0`、`8116df6`。

### R04 密码登录模式可配置

**类型：新增安全策略 + Dashboard 配置**

**需求与验收行为**

- Shop 提供 `PasswordLoginMode`：`ENABLED`、`CUSTOMERS_ONLY`、`DISABLED`。
- `DISABLED` 时，`tokenCreate`、`setPassword`、`passwordChange`、`requestPasswordReset`、`tokenRefresh` 等密码认证流程返回业务错误。
- `CUSTOMERS_ONLY` 时，staff 用密码登录只能获得 customer 身份，不获得 staff 能力；外部认证仍可用于后台登录。
- Dashboard 设置页可修改模式；登录页在密码登录关闭时隐藏邮箱/密码表单，仅展示外部认证，若也没有外部认证则展示空状态。

**实现 patch**

- Core：`saleor/site/models.py`、`saleor/site/migrations/0046_sitesettings_password_login_mode.py`、account authentication mutations、shop settings schema。
- Dashboard：`src/configuration/` 的登录方式设置、`src/auth/components/LoginPage/`。

**测试证据**

- `test_token_create.py`、`test_token_refresh.py`、`test_set_password.py`、`test_password_change.py`、`test_request_password_reset.py`
- `src/auth/components/LoginPage/LoginPage.test.tsx`

**实际验证**：Core V1、Dashboard V5 通过。Git 参考：Core `094d2e9`；Dashboard `65922df`。

### R05 库存可按仓库-渠道直连关系计算

**类型：新增兼容开关 + 行为改变**

**需求与验收行为**

- Shop 新增 `useLegacyShippingZoneStockAvailability`，已有安装默认保持 legacy 行为。
- 开关关闭时，库存可用性、预留和分配以 warehouse-channel 直接关系判断，忽略 shipping zone 与目的地址。
- checkout 创建/改行/改地址、从订单创建 checkout、draft/order 行操作、完成 draft、履约、产品库存筛选及 `isAvailable` 均使用同一规则。
- `ProductVariant.stocks(address)`、`quantityAvailable(address)`、`Product.isAvailable(address)` 的 address 参数进入弃用；新模式下忽略 address。

**实现 patch**

- `saleor/site/migrations/0048_sitesettings_include_shipping_zones_in_stock_availability.py`
- `saleor/warehouse/availability.py`、checkout/order/product/fulfillment 库存调用链及 GraphQL shop settings。

**测试证据**

- `saleor/warehouse/tests/test_stock_availability.py`
- checkout、draft order、order line、fulfillment、product availability 相关测试。

**实际验证**：V2 通过。Git 参考：`652df5e`。

### R06 App 可报告问题，Dashboard 可聚合、查看和关闭

**类型：新增运维功能**

**需求与验收行为**

- App 可上报带 key、类型、消息和元数据的问题；重复 key 应聚合 occurrence 次数与时间，而不是无限生成重复记录。
- Critical 问题、输入校验、单 App 容量上限及旧问题淘汰必须有确定行为。
- App 或有权限的 staff 可按 ID/key 关闭问题；查询支持活跃/已关闭状态。
- Dashboard 在已安装扩展列表和详情中显示问题数量、严重性、发生时间及关闭状态；即使 App 已禁用，问题仍需可见。

**实现 patch**

- Core：`saleor/app/models.py`、`saleor/app/migrations/0035_appproblem.py`、`saleor/graphql/app/mutations/app_problem_create.py`、`app_problem_dismiss.py`、query/dataloader/schema。
- Dashboard：`src/extensions/views/InstalledExtensions/components/AppProblems/`、`useExtensionProblems.ts`、sidebar/app alert 逻辑。

**测试证据**

- Core `test_app_problem_create*`、`test_app_problem_dismiss*`、`test_app_problems.py`
- Dashboard `AppProblems/utils.test.ts`、`useExtensionProblems.test.ts`

**实际验证**：Core V1、Dashboard V5 通过。Git 参考：Dashboard `fca0cbf`、`94e85a4`。

### R07 跨业务对象增强搜索

**类型：查询体验增强**

**需求与验收行为**

- 产品、订单、礼品卡、checkout、page/model、用户搜索支持前缀、`AND`/`OR`/`-`、引号短语和去重音符匹配。
- 精确命中优先于前缀命中；使用 search 时默认按相关度返回，并提供 `RANK` 排序覆盖入口。
- 用户可由邮箱、姓名和地址检索；checkout 可索引客户、地址、行、支付和 transaction；礼品卡可索引标签和末四位。
- checkout/page/user 等对象维护 search vector 与 dirty flag，由后台任务批量更新，并处理删除、异常重试与并发。

**实现 patch**

- `saleor/core/search.py`、`saleor/core/search_tasks.py`
- `saleor/product/search.py`、`saleor/order/search.py`、`saleor/giftcard/search.py`、`saleor/checkout/search/`、`saleor/page/search.py`、`saleor/account/search.py` 及对应 migrations/query filters。

**测试证据**

- Core/search、account/page/checkout search 单元测试。
- `test_orders_search.py`、`test_gift_card_search.py`、`test_pages_search.py` 及产品搜索测试。

**实际验证**：V2 通过。Git 参考包括 `2c9e886`、`bb61600`、`332e00b`、`3e5172f`、`1233f8e`、`c29d642`。

### R08 外部产品图片异步下载并提供失败回退

**类型：性能改进 + 用户可见状态**

**需求与验收行为**

- `productMediaCreate`、`productBulkCreate` 对外部 URL 图片不再阻塞 mutation，而是创建任务异步拉取。
- 下载未完成时访问媒体图片返回 HTTP 503，使客户端能区分“处理中”和永久不存在。
- 同一个图片资源避免重复抓取；provider、MIME type、空 alt 等输入错误被稳定处理。
- Dashboard 图片加载失败时展示占位图标和说明，不显示浏览器破图。

**实现 patch**

- Core：`saleor/graphql/product/mutations/product/product_media_create.py`、bulk create、`saleor/product/tasks.py`、媒体模型/存储逻辑。
- Dashboard：`src/products/components/ProductMedia/` 及通用缩略图/媒体回退组件。

**测试证据**

- `saleor/graphql/product/tests/mutations/test_product_media_create.py`
- product bulk create media tests 与 HTTP cassette。
- Dashboard 产品媒体组件测试。

**实际验证**：Core V1 通过；Dashboard 回退为静态 patch/test 证据，未单独运行其组件测试。Git 参考：Core `1145535`；Dashboard changelog `e7890fc`。

### R09 App Extension 合同升级并支持双向表单集成

**类型：API 合同改变 + 扩展能力增强**

**需求与验收行为**

- `AppExtension`/manifest extension 使用 `mountName`、`targetName`、`settings`；移除旧 `mount`、`target`、`options` GraphQL 字段。
- 后端安装 manifest 时允许字符串 mount/target 与 JSON options/settings，把具体前端合同校验交由 Dashboard。
- 新增 `TRANSLATIONS_MORE_ACTIONS` mount；翻译页与产品页 popup 扩展能接收当前表单状态，并将 App 返回字段实时写回表单。
- 迁移前后的 AppExtension 数据均可解析，HTTP/native settings 转换稳定。

**实现 patch**

- Core：AppExtension migrations/model/manifest parsing、`saleor/graphql/app/types.py`、queries。
- Dashboard：`src/extensions/domain/app-extension-manifest*`、popup/form payload update、`src/translations/components/TranslationsProductsPage/`。

**测试证据**

- Core `test_app_extension.py`、`test_app_extensions.py`、manifest tests。
- Dashboard extension domain tests、`use-translation-product-form-app-response.test.ts`。

**实际验证**：Core V4、Dashboard V5 通过。Git 参考：Core `3d23b76`、`d2b8ef0`、`b356a52`；Dashboard `db8fc50`、`7465a3a`、`ccc854d`。

### R10 自动完成已支付 checkout 可按渠道配置

**类型：新增自动化业务能力 + Dashboard 配置**

**需求与验收行为**

- 渠道可开启已支付 checkout 自动完成，并配置延迟时间与 cutoff。
- 后台任务只选择满足条件的 checkout：已付款、有客户或邮箱、有账单地址、需要配送时有配送方式、行仍可售、总额非零且未过期。
- 支持 Transaction API 和 legacy Payment 流；按批次处理，优先从未尝试过的 checkout，并记录失败后重试状态。
- Dashboard 提供开关、延迟设置和风险提示，关闭或不合法组合不能保存成矛盾状态。

**实现 patch**

- Core：`saleor/checkout/tasks.py`、channel/checkout models 与 migrations、channel GraphQL inputs。
- Dashboard：`src/channels/components/ChannelForm/automatic-checkout-complete/`。

**测试证据**

- `saleor/checkout/tests/test_tasks.py` 中 `automatic_checkout_completion*` 和 trigger tests。
- Dashboard automatic-checkout-complete 下 handlers/warnings/utils tests。

**实际验证**：Core V4、Dashboard V5 通过。

### R11 Product Doctor 提供渠道可售性诊断

**类型：Dashboard 新功能**

**需求与验收行为**

- 商品编辑页按渠道汇总发布、可购买时间、listing 可见性、库存、仓库与配送区配置问题。
- 区分 error/warning，支持按渠道名或币种搜索、分页和问题计数。
- 未发布且不可售渠道不做无意义检查；非配送商品跳过 shipping-zone 告警但仍执行核心与仓库检查。
- 在权限不足时呈现权限状态，编辑中的表单渠道数据应即时并入诊断结果。

**实现 patch**

- Dashboard：`src/products/components/ProductDoctor/`，并接入 ProductUpdate 页面。

**测试证据**

- ProductDoctor hooks、sections、availabilityChecks、availabilityStatus、channelUtils、dateUtils、mapping/merge tests。

**实际验证**：Dashboard V5 通过。Git 参考：`972ca64`、`cf1c8aa`。

### R12 Product Variant Generator 批量生成变体

**类型：Dashboard 新功能**

**需求与验收行为**

- 用户可选择多个 variant selection attributes 的值，预览笛卡尔积并仅创建尚不存在的组合。
- 可为批次配置 SKU 前缀、是否生成 SKU、仓库及初始库存；库存 0 合法，负库存不写入。
- 非 selection 的必填属性支持 plain text、numeric、boolean、date、datetime、dropdown 等正确 GraphQL 输入。
- 超过安全组合数时截断预览并显示真实总数，避免页面和请求失控。
- 产品类型的 legacy `hasVariants` 不再限制分配 variant attributes；`hasVariants` 字段弃用。

**实现 patch**

- Dashboard：`src/products/components/ProductVariantGenerator/`。
- Core：product type attribute assignment validation/schema deprecation。

**测试证据**

- `src/products/components/ProductVariantGenerator/utils.test.ts`
- Core product type create/update 与 attribute assignment tests。

**实际验证**：Dashboard V5 的 generator 测试通过；Core `hasVariants` 行为由静态 patch/test 证据确认，未单独运行相关文件。Git 参考：Core `a057b4b`；Dashboard `972ca64`。

### R13 订单金额、支付和交易操作重构

**类型：Dashboard 业务流程重构**

**需求与验收行为**

- 订单摘要统一展示商品、配送、折扣、礼品卡、税费、已授权、已扣款和应付余额，并兼容 Transaction API 与 legacy Payments API。
- 无支付记录且有权限时显示 Mark as paid；不同 API 模式只展示其合法操作。
- Capture 对话框显示总额、已扣款、可捕获额和授权状态，支持全额、最大可捕获额、自定义金额；无授权或金额越界时禁止提交。
- 多 transaction 情况按 order balance 计算结果；交易卡将 CHARGE 作为主操作，取消等次要操作进入菜单，退款走统一退款流程。

**实现 patch**

- Dashboard：`src/orders/components/OrderSummary/`、`OrderCaptureDialog/`、`OrderTransaction/`、order view model/utils。

**测试证据**

- `OrderSummary.test.tsx`、`OrderValue.test.tsx`
- `OrderCaptureDialog.test.tsx`、`useCaptureState.test.ts`
- OrderDetailsViewModel、transaction card/action tests。

**实际验证**：Dashboard V5 通过。Git 参考：`62f2911`、`9670756`、`f824411`。

### R14 Dashboard 可编辑订单、订单行、履约和仓库元数据

**类型：新增后台操作能力**

**需求与验收行为**

- 订单详情提供 order、order line、fulfillment metadata 编辑入口；warehouse 详情也可编辑 metadata/private metadata。
- metadata 允许空值并进行 key/value 校验；有未保存改动时关闭 modal 必须提示或阻止意外丢失。
- order line 中 variant metadata 只链接到 variant，不把 variant metadata 错当成 order-line metadata 修改。
- checkout 转 order 和 draft complete 时复制配送方式 public/private metadata；订单创建后不再随原 shipping method 后续修改或删除而变化。

**实现 patch**

- Core：order shipping metadata fields/migration、checkout-to-order 与 `draft_order_complete.py`。
- Dashboard：`OrderMetadataDialog/`、`OrderLineMetadataDialog/`、`OrderFulfillmentMetadataDialog/`、通用 `MetadataDialog/`、`WarehouseMetadataDialog/`。

**测试证据**

- Core `test_draft_order_complete_builtin_shipping_method_metadata_denormalization` 及 order query tests。
- Dashboard MetadataDialog、OrderLineMetadataDialog、warehouse metadata tests。

**实际验证**：Core V4、Dashboard V5 的通用 metadata 测试通过；fulfillment/warehouse 对话框未在定向集合中单独运行。Git 参考：Dashboard `0c83a47`、`f519aa3`、`77ce8c2`、`2db65da`、`1a8279b`。

### R15 Dashboard 列表、选择器与导航体验修正

**类型：用户可见缺陷修复与效率提升**

**需求与验收行为**

- Assign dialogs 的搜索/filter 状态与 URL/modal 状态一致，锁定条件不能被用户条件覆盖；取消仓库选择后不产生重复项。
- Category 页面显示层级 breadcrumbs。
- 产品导出“Current search”准确复用当前 search/filter；礼品卡增加按 code 的显式过滤，避免等待异步索引。
- 批量操作可稳定处理最多 100 项；产品列表、collection 等 reorder/bulk 操作不产生错误请求。
- 搜索输入提供 tooltip 且宽度稳定，长文本不破坏布局。

**实现 patch**

- Dashboard：`src/components/Assign*Dialog/`、`ModalFilters/`、category views、product export filter mapper、gift card filters、bulk action hooks、`SearchInput/`。

**测试证据**

- ModalFilters locked/url/store tests、Assign dialog tests、ProductExportFieldMapper tests、gift card initial filter tests、SearchInput tests及相关 E2E。

**实际验证**：本批未单独运行上述完整集合；结论来自 code/test patch 静态证据。Git 参考：`ccdfdec`、`2632bf0`、`a0011cc`、`d310e49`、`271928b`。

### R16 Webhook 延迟求值并异步构建订单事件载荷

**类型：性能和调用语义改变**

**需求与验收行为**

- 发送 order/draft/fulfillment async webhook 前不再预先触发 `ORDER_CALCULATE_TAXES`、`ORDER_FILTER_SHIPPING_METHODS` 等 sync webhook。
- sync webhook 只在字段实际请求时执行，降低额外调用、延迟和费用。
- order 事件 payload 序列化下沉到后台任务，mutation 请求路径不承担完整 payload 构建成本。
- promise/circuit-breaker 与 checkout shipping webhook 路径保持错误隔离，不能因异步载荷而重复调用同步 App。

**实现 patch**

- Core：`saleor/webhook/` promise/async event 逻辑、`saleor/order/webhooks/`、checkout shipping webhook 与 tasks。

**测试证据**

- order static/subscription/calculate-taxes webhook tests、checkout webhook invocation count tests、async event payload tests。

**实际验证**：未执行该专项完整集合；结论来自 code/test patch 静态证据。Git 参考：`e138b36`、`0423c2f`、`b4cc3b3`、`90f3b85`。

### R17 内容输入与身份认证加固

**类型：安全行为改变 + 缺陷修复**

**需求与验收行为**

- EditorJS 输入拒绝未知/多余字段、非法或过深嵌套结构和不安全 URL；链接默认 `rel="noopener noreferrer"`，不再允许配置扩展 URL scheme allowlist。
- Google OIDC 开启 refresh token 时不发送不兼容的 `offline_access` scope，改用 `access_type=offline`。
- 已存在用户首次被 OIDC provider claim 时使旧密码失效，避免被删除/重建 staff 继续使用陈旧密码。

**实现 patch**

- `saleor/core/editorjs/`、相关 clean command/config。
- OIDC plugin authorization 与 user-claim 流程。

**测试证据**

- `saleor/core/editorjs/tests/test_editorjs.py`、nested list/management command tests。
- OIDC plugin tests。

**实际验证**：EditorJS 在 V4 通过；OIDC 专项未单独运行。Git 参考：`0bce4b9`、`484eb7c`。

### R18 API 约束、删除语义与不兼容清理

**类型：破坏性/兼容性变化**

**需求与验收行为**

- 新增 `NonNegativeInt`；`Minute`、`Hour`、`Day` 禁止负数，channel create/update 对负时间值产生 GraphQL input error。
- Federation `_entities.representations` 从 `[_Any]` 收紧为 `[_Any!]!`，空列表项和 null 输入按 schema 拒绝。
- `Attribute.name`、`slug`、`type` 改为 non-null；`AppInstallInput.appName`、`manifestUrl` 改为 schema required。
- `staffDelete` 即使 staff 有历史订单也真正删除，不再仅撤销 staff 状态。
- 移除 Adyen、NP Atobarai plugin、`Payment.partial` 与旧 digital-content API；数字商品本身仍支持，但集成方必须迁移到 Apps/现行数字商品方案。
- 弃用 `exportProducts`、`exportGiftCards`、`exportVoucherCodes` mutations，以及 draft order 的 `voucher` input，分别改用查询导出和 `voucherCode`。

**实现 patch**

- Core scalar/schema/federation/account mutation。
- payment plugin 删除、digital content GraphQL 清理、deprecated schema 标记。

**测试证据**

- scalar/channel validation、federation schema/resolver、staff delete、schema snapshot/deprecation tests。

**实际验证**：staff deletion 在 V4 通过；其余由 patch/schema tests 静态核对，未全部单独运行。Git 参考：`2075f4d`、`59d8fa1`、`afe12a4`、`5a8035e`、`492952d`。

### R19 其余 Dashboard 商户配置和展示变化

**类型：配置入口与用户可见缺陷修复**

**需求与验收行为**

- Channel 设置页提供自动完成 checkout 与 legacy gift-card channel 行为的控制项，并能容忍 settings query 加载期间为 undefined。
- Shop 设置页暴露 address validation 和 legacy update webhook emission 等后端开关。
- 简单商品也可正确编辑重量；产品媒体失败有占位回退；订单历史中的折扣内容、日期分组与状态标识正确。
- Draft order 在渠道停用或无商品时禁用“Add products”并给出准确 tooltip。

**实现 patch**

- Dashboard channel/configuration/product/order components 与 GraphQL operations。

**测试证据**

- Channel form、product weight、media fallback、OrderHistory、OrderDraftDetails 组件 tests。

**实际验证**：自动完成部分在 V5 通过；其余为静态 patch/test 证据。Git 参考包括 `51575d1`、`80b93f6` 与 Dashboard 3.23 changelog 条目。

## 5. 不计为新增需求的变化

以下内容虽存在于 patch，但没有被单独列为业务需求：

- Python、Node、Vite、Jotai、SDK 等依赖或工具链升级。
- CI workflow、Claude/Codex instruction、lint、format、release automation 变化。
- 只改变内部模块边界、文件名或代码风格且不改变外部行为的重构。
- 测试适配器、fixture、benchmark、snapshot 和 evaluator 配置本身。
- OTel/Sentry/usage telemetry 等仅供内部可观测性的变化；它们不形成商户工作流。

## 6. 结论与使用建议

本次迁移不是单纯版本号升级。影响最大的合同是显式配送计算、Transaction API 礼品卡、密码登录模式、库存可用性模型、App Problems、搜索语义以及 App Extension 字段迁移。升级实施时应优先检查 storefront 的 checkout 配送调用、支付 App、身份登录、库存/仓库配置及扩展 manifest。

Dashboard 已为主要新能力提供操作面，但 API 使用方仍需主动适配 R01、R04、R05、R09 和 R18 的合同或弃用项。本文的 978 个定向测试证明代表性目标行为在已构建镜像中成立；上线前仍建议按实际启用的支付 App、OIDC provider、Webhook 和 E2E 订单流程补充环境级验收。
