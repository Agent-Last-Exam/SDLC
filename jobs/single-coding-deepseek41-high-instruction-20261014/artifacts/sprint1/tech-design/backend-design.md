# 后端技术设计：Saleor 3.23 结账、收款与商户运营一致性交付

版本：v1
责任：后端技术设计
依据：PRD v1，artifacts/sprint1/prd/prd.md
修订：首次交付。

## 1. 方案概述

本轮后端交付以 Core 3.22.0 为基线，围绕「可售判断 → 配送选择 → 支付 → 成单 → 履约 → 售后」这一条链路做一致性收口，不新增与主体链路无关的独立能力。设计遵循 PRD §5.2 的五条产品决策：设置与执行分离、弃用读取优先于静默成功、同一事实单一来源、失败可分支且不产生部分结果、权限与可见范围与入口无关。

现有行为链与落点（源码依据为当前基线仓库）：

- **结账与配送**：`saleor/checkout/fetch.py` 中的 `CheckoutInfo.valid_shipping_methods`（约 L278）、`get_available_built_in_shipping_methods_for_checkout_info`（L643）、`get_valid_internal_shipping_methods_for_checkout_info`（L672）、`get_external_shipping_methods_for_checkout_info`（L680）、`update_delivery_method_lists_for_checkout_info`（L702）负责按地址、行项目、渠道与同步配送服务结果计算配送方式；校验集中在 `saleor/graphql/checkout/mutations/utils.py:75 clean_delivery_method`；写入口是 `checkoutDeliveryMethodUpdate`（`saleor/graphql/checkout/mutations/checkout_delivery_method_update.py`）与已弃用的 `checkoutShippingMethodUpdate`；成单在 `saleor/checkout/complete_checkout.py`。
- **库存**：`saleor/warehouse/models.py:265 ChannelWarehouse` 提供渠道与仓库的直接关联，`saleor/warehouse/models.py:329 StockQuerySet.for_channel_and_country`（L377）是按配送国家/地址取库存的现有语义；`AllocationStrategy` 在 `saleor/channel/__init__.py`。
- **自动完成**：渠道开关 `Channel.checkoutSettings.automaticallyCompleteFullyPaidCheckouts`（Django 模型字段 `automatically_complete_fully_paid_checkouts`）只控制布尔值；触发点 `saleor/checkout/actions.py:330`，任务 `saleor/checkout/tasks.py:135 automatic_checkout_completion_task`（`max_retries=5`、`default_retry_delay=60`，队列 `settings.AUTOMATIC_CHECKOUT_COMPLETION_QUEUE_NAME`）；任务体没有批次扫描；成单复用 `saleor/checkout/complete_checkout.py:1753 complete_checkout_with_transaction(is_automatic_completion=...)`。
- **交易与礼品卡**：`saleor/payment/models.py:31 TransactionItem`、`:194 TransactionEvent`；金额重算 `saleor/payment/transaction_item_calculations.py:352 recalculate_transaction_amounts`；礼品卡目前只作为结账总额抵扣（`saleor/checkout/calculations.py:129 calculate_checkout_total_with_gift_cards`、`saleor/order/utils.py:464 add_gift_cards_to_order`），`saleor/graphql/giftcard/mutations/` 下不存在退款类操作。
- **订单金额**：`saleor/order/models.py:309/314/319/322`（`total_charged_amount`、`total_authorized_amount` 与对应 MoneyField）、`saleor/order/utils.py:1073 _update_order_total_charged`、`:1110 _update_order_total_authorized`、`saleor/order/actions.py:484` 附近的 `total_refunded` 累加。
- **搜索**：Product/Order 使用 Postgres 全文检索与 `SearchRank`（`saleor/product/search.py`、`saleor/order/search.py`）；GiftCard 使用 `websearch`（`saleor/giftcard/search.py:64`）；User 使用 `search_document__ilike`（`saleor/account/search.py:128`）；Page 使用 trigram（`saleor/graphql/page/filters.py:58`）。Page 与 User 确实没有 RANK 排序。
- **认证**：`saleor/graphql/account/mutations/authentication/` 下的 `create_token.py`、`request_password_reset.py`、`set_password.py`、`password_change.py`；OIDC 插件 `saleor/plugins/openid_connect/plugin.py:222-229` 目前只拼装 `offline_access` scope，没有 `access_type` 参数；`saleor/plugins/openid_connect/utils.py:391 get_or_create_user_from_payload`。
- **富文本**：`saleor/core/utils/editorjs.py:32 clean_editor_js`，当前只有 `BLACKLISTED_URL_SCHEMES = ("javascript",)`（L8）的黑名单，没有嵌套深度校验，也没有 scheme 白名单。
- **扩展**：`saleor/app/manifest_validations.py:143 clean_manifest_data`、`:291 _clean_extensions`；模型 `saleor/app/models.py:156 AppExtension`（只有 `mount`/`target`/`http_target_method`）。
- **Webhook**：投递模型在 `saleor/core/models.py:206 EventDelivery`、`:223 EventDeliveryAttempt`；延迟载荷 `saleor/webhook/transport/utils.py:94 prepare_deferred_payload_data` 与 `saleor/webhook/transport/asynchronous/transport.py:500 generate_deferred_payloads`；重试上限 `MAX_WEBHOOK_RETRIES = 5`（`saleor/webhook/transport/asynchronous/transport.py:77`）。
- **校验**：`saleor/graphql/core/validators/__init__.py`（`validate_one_of_args_is_in_mutation`、`validate_price_precision`、`validate_limit_of_list_input` 等）；`Minute`/`Hour`/`Day` 标量在 `saleor/graphql/core/scalars.py:202/206/210` 是 `graphene.Int` 的空子类，**当前不拒绝负数**。

整体方案：

1. **新增一条以结账为主体的配送选项查询**，把 `checkout/fetch.py` 已有的计算能力暴露为可主动调用的只读查询，并在更新配送选择与完成结账时复用同一校验函数，使「页面看到的」与「提交时确认的」来自同一计算语义。
2. **库存计算引入渠道级模式开关**，默认保持 `SHIPPING_ZONES`（现有配送区域/地址语义），切换到 `CHANNEL_WAREHOUSES` 后才由 `ChannelWarehouse` 直接关联决定参与计算的仓库，商品查询、结账、订单、履约与草稿订单共用同一个查询集入口。
3. **自动完成从「布尔开关」升级为「渠道级策略 + 批次扫描 + 可诊断状态」**，在任务边界内重新校验支付、客户、地址、配送、库存与金额，并以结账状态机保证同一结账只产生一个订单结果。
4. **礼品卡进入统一交易生命周期**：以 `TransactionItem` + `TransactionEvent` 记录礼品卡的授权、取消、扣款与退款，礼品卡交易不计入普通交易的已授权/已扣款/已退款汇总，订单侧新增 `totalGiftCard` 单独呈现。
5. **补齐身份、内容与接口治理**：密码登录模式成为商店级生效点；OIDC 使用 `access_type=offline`；富文本在保存前做结构、scheme 与深度校验；输入校验前移到执行前；弃用能力给出明确的弃用读取或迁移错误。

对外接口的权威定义集中在 `interface-contract.md`，完整目标 SDL 见 `target-schema.graphql`（由基线 `saleor/graphql/schema.graphql` 逐处锚定修改生成，基线定义逐字保留）。

## 2. 需求覆盖

下表只列后端承接的需求。R15、R16、R21、R22、R30、R31 由 Dashboard 前端承接，后端不新增对外接口，见 §6「前端承接需求的后端边界」；其中 R15、R31 的后端部分只是既有查询的筛选与权限语义不变，不构成新接口。

| 需求 | 设计单元 |
| --- | --- |
| R01 | BD01 |
| R02 | BD01 |
| R03 | BD02 |
| R04 | BD03 |
| R05 | BD04 |
| R06 | BD05 |
| R07 | BD06 |
| R08 | BD07 |
| R09 | BD07 |
| R10 | BD08 |
| R11 | BD09 |
| R12 | BD10 |
| R13 | BD11 |
| R14 | BD12 |
| R17 | BD13 |
| R18 | BD14 |
| R19 | BD15 |
| R20 | BD16 |
| R23 | BD17 |
| R24 | BD17 |
| R25 | BD18 |
| R26 | BD19 |
| R27 | BD20 |
| R28 | BD21 |
| R29 | BD22 |
| R32 | BD23 |

无对外接口变更的后端设计单元：**BD19**（保留既有元数据读写，不新增类型与字段）、**BD23**（只做范围约束，不新增类型与字段）。其余设计单元都至少改变了一个对外契约（新增操作、新增字段或改变既有操作的行为语义），均登记在 §4 与 `interface-contract.md`。

## 3. 详细设计

### BD01 · 结账配送选项计算与重校验
- 覆盖需求：R01、R02
- 设计说明：
  - **模块落点**：计算逻辑沿用 `saleor/checkout/fetch.py`（`get_available_built_in_shipping_methods_for_checkout_info`、`get_valid_internal_shipping_methods_for_checkout_info`、`get_external_shipping_methods_for_checkout_info`、`update_delivery_method_lists_for_checkout_info`、`CheckoutInfo.valid_shipping_methods`）。新增 GraphQL 查询 `checkoutDeliveryOptions`，落在 `saleor/graphql/checkout/schema.py` 注册、`saleor/graphql/checkout/resolvers.py`（或同级新模块）实现 resolver，返回新增类型 `CheckoutDeliveryOptions` / `DeliveryOption`。校验复用 `saleor/graphql/checkout/mutations/utils.py:75 clean_delivery_method`，并把其中「地址缺失」「方式不在有效集合内」「同步配送服务错误」三类判断抽成可被查询与变更共用的函数，避免两套判断漂移。
  - **业务逻辑**：查询以结账 token 定位结账（`Checkout.token`，`UUID`），按当前收货地址、行项目、渠道、币种与同步配送服务（`SHIPPING_LIST_METHODS_FOR_CHECKOUT`、`CHECKOUT_FILTER_SHIPPING_METHODS`）的当前结果计算选项列表。`availableDeliveryOptions` 只包含当前适用项；`selectedDeliveryOption` 返回结账当前 `delivery_method` 对应的选项，即使已不适用也返回（`status: UNAVAILABLE`），使客户端能识别失效选择，满足 AC-01-2 与 AC-01-3。选项 `id` 使用配送方式自身的 ID（`Warehouse.id` 或 `ShippingMethod.id`），与 `checkoutDeliveryMethodUpdate(deliveryMethodId:)` 的入参口径一致。
  - **失败语义**：地址缺失/不完整返回 payload 内 `errors`（`CheckoutErrorCode.SHIPPING_ADDRESS_NOT_SET`、`MISSING_ADDRESS_DATA`）；同步配送服务报错返回 `DELIVERY_SERVICE_ERROR` 且不返回部分选项；结账不存在或不属于调用方返回顶层 `NOT_FOUND`；无权限返回权限错误。查询是只读的，绝不写入结账的配送选择，满足 AC-01-4、AC-01-5。
  - **重校验**：`checkoutDeliveryMethodUpdate`、已弃用的 `checkoutShippingMethodUpdate` 与 `checkoutComplete` 在写/成单前都调用同一校验函数。失效原因区分：未设置 → `SHIPPING_METHOD_NOT_SET`/`DELIVERY_METHOD_NOT_APPLICABLE`；地址缺失 → `SHIPPING_ADDRESS_NOT_SET`；方式在提交时刻失效 → 新增 `CheckoutErrorCode.DELIVERY_METHOD_INVALIDATED`；配送方式不属于当前结账（归属错误）→ 新增 `CheckoutErrorCode.DELIVERY_METHOD_OUT_OF_SCOPE`。`checkoutComplete` 的失败在 `saleor/checkout/complete_checkout.py` 的事务边界外返回，订单创建保持单事务，不留下半成品订单，满足 AC-02-1 至 AC-02-5。
  - **数据模型**：无新增持久字段。`DeliveryOption.status` 由计算时判定，不落库。
  - **事务/异步/失败语义**：查询为同步只读；变更类操作在既有事务边界内执行，校验失败不产生任何写入；不新增异步任务。
  - **迁移与验证方法**：无数据迁移。验证点：同一结账在地址/行项目/渠道变化前后调用 `checkoutDeliveryOptions`，断言列表差异；把 `deliveryMethodId` 换成其他结账的配送方式，断言 `DELIVERY_METHOD_OUT_OF_SCOPE`；在提交前失效配送方式后调用 `checkoutComplete`，断言不创建订单。

### BD02 · 配送标识归属与旧字段弃用兼容
- 覆盖需求：R03
- 设计说明：
  - **模块落点**：`saleor/graphql/checkout/mutations/checkout_shipping_method_update.py`（已弃用入口）与 `checkout_delivery_method_update.py` 共用归属校验；`saleor/graphql/checkout/types.py` 与 `saleor/graphql/order/types.py` 上的 `shippingMethod` 字段保持现状。
  - **业务逻辑**：旧入口接收的 `shippingMethodId` 与新入口的 `deliveryMethodId` 走同一归属判定：只接受属于当前结账渠道、且在当前结账有效集合内的配送方式；旧客户端传入的地址类参数仍被接受，但不参与归属判定（归属只由渠道与 `ChannelWarehouse`/配送区域关系决定）。旧字段 `Checkout.shippingMethod`、`Order.shippingMethod`、`Checkout.availableShippingMethods` 继续返回与 `deliveryMethod` 一致的对象，并保留基线已有的 `@deprecated` 标记，满足 AC-03-1。
  - **失败语义**：归属错误返回 `DELIVERY_METHOD_OUT_OF_SCOPE`，不返回其他渠道的配送方式名称、价格或地址；权限不足与结账不存在分别返回权限错误与 `NOT_FOUND`。
  - **数据模型**：无变化。
  - **迁移与验证方法**：无迁移。验证点：用旧入口提交属于/不属于当前结账的配送标识各一次；断言旧字段读取结果与 `deliveryMethod` 相同且带弃用标记。

### BD03 · 渠道-仓库库存计算统一
- 覆盖需求：R04
- 设计说明：
  - **模块落点**：`saleor/warehouse/models.py:329 StockQuerySet` 新增按渠道模式分派的入口（在 `for_channel_and_country` 旁新增 `for_channel_and_mode`/等价方法），`saleor/warehouse/availability.py`、`saleor/graphql/product/`、`saleor/checkout/`、`saleor/order/`、`saleor/graphql/order/` 与草稿订单相关 resolver 统一改为调用该入口，替换现在各自直接调用 `for_channel_and_country` 的位置。渠道侧配置落点是 `saleor/channel/models.py` 的渠道库存设置与 `StockSettings` 类型。
  - **业务逻辑**：新增渠道级模式 `StockAvailabilityModeEnum`，取值 `SHIPPING_ZONES`（默认，等价现有配送区域 + 地址关联语义）与 `CHANNEL_WAREHOUSES`（只取 `ChannelWarehouse` 直接关联当前渠道的仓库）。默认值必须保证 AC-04-1：未切换的渠道行为与升级前逐字一致。切换后所有入口共用同一查询集，地址参数被接受但不影响结果，满足 AC-04-2、AC-04-3。预留与分配（`saleor/warehouse/allocation.py`）沿用同一查询集，失败时整笔回滚，不产生部分预留，满足 AC-04-4。渠道/仓库可见性沿用既有权限过滤，无权限返回权限错误而不是空结果，满足 AC-04-5。
  - **数据模型**：`Channel` 增加库存可用性模式字段（Boolean/CharField with choices，默认 `SHIPPING_ZONES`），配一条只改默认值、不改既有行的迁移；`StockSettings`/`StockSettingsInput` 暴露 `stockAvailabilityMode`。
  - **事务/异步/失败语义**：库存预留与订单创建在同一事务内；库存不足抛出既有 `InsufficientStock`，映射为可分支错误码。
  - **迁移与验证方法**：迁移为纯新增字段 + 默认值，可在空库与既有库执行。验证点：同一商品在 `SHIPPING_ZONES` 与 `CHANNEL_WAREHOUSES` 两种模式下分别查询商品可售性、结账可用量、履约库存，断言结果一致；对已切换渠道传入地址参数，断言结果不变。

### BD04 · 已支付结账自动完成的执行与幂等
- 覆盖需求：R05
- 设计说明：
  - **模块落点**：`saleor/checkout/tasks.py:135 automatic_checkout_completion_task` 保留为单结账执行入口；新增批次扫描任务（同文件）负责按渠道配置挑选候选结账并逐个派发；成单复用 `saleor/checkout/complete_checkout.py:1753 complete_checkout_with_transaction(is_automatic_completion=True)`。
  - **业务逻辑**：`is_fully_paid` 判定按支付方式分派：Transaction 流程看 `charged + authorized >= total`（沿用现有语义），兼容 `Payment` 流程按 `Payment` 的 charge 状态判定。前置条件在**执行时刻**重新校验：fully paid、存在客户或邮箱、账单地址、需配送时具备收货地址与配送方式、商品可售、总额大于零。已经完成或已被处理过的结账（订单已存在或结账状态已变更）直接短路，不创建第二个订单。
  - **事务/异步/失败语义**：任务体在 `transaction.atomic()` 内完成「校验 + 创建订单 + 发送完成事件」；条件不满足时写诊断状态并结束（不重试），可恢复的并发/数据库错误按现有 `self.retry()`（`max_retries=5`、`default_retry_delay=60`）重试。幂等由两重保证：结账状态机 + 订单对结账的唯一约束（订单创建使用既有 `checkout` 关联，重复创建触发 `IntegrityError` 并被短路）。完成事件只在真正创建订单后发出一次。
  - **数据模型**：结账上新增自动完成的诊断状态（状态枚举、最近尝试时间、阻断原因集合），可由 `Checkout.automaticCompletion` 读取；不新增订单侧字段。
  - **迁移与验证方法**：新增字段迁移可在空库执行。验证点：构造不满足各前置条件的结账逐一断言不创建订单；对同一结账并发调用任务两次，断言只有一个订单与一次完成事件；条件修复后重试，断言订单金额与首次一致。

### BD05 · 自动完成的渠道级配置
- 覆盖需求：R06
- 设计说明：
  - **模块落点**：`Channel.checkoutSettings.automaticallyCompleteFullyPaidCheckouts` 保留；在渠道结账设置上新增 `automaticCompletionDelay`（`Minute`）与 `automaticCompletionCutoff`（`DateTime`）；写入路径复用 `channelUpdate`（`saleor/graphql/channel/mutations/channel_update.py`）的 `checkoutSettings` 输入。
  - **业务逻辑**：延迟从结账最近一次修改时间起算，`modified + delay <= now` 才进入待处理范围；cutoff 是结账创建时间的下界（`created >= cutoff`），不是任务停止时间。两个参数未配置时保持关闭或既有默认行为，未配置的旧渠道不被改为自动完成，满足 AC-06-2。配置保存是设置写入，不触发任何结账处理，也不改变结账/订单状态，满足 AC-06-6。
  - **失败语义**：范围或组合非法（延迟为负、cutoff 与延迟组合不合法）在执行前返回 `ChannelErrorCode.INVALID`；无权限返回 `FORBIDDEN`/`OUT_OF_SCOPE_CHANNEL`；保存冲突返回 `UNIQUE`/`ALREADY_EXISTS`。所有失败路径保留上次生效值。
  - **数据模型**：渠道设置新增两个可空字段（延迟为分钟整数、cutoff 为时间戳），默认 NULL 表示未配置。
  - **迁移与验证方法**：新增可空字段迁移，既有渠道全部为 NULL。验证点：保存后重读一致；未配置渠道的任务扫描不产生候选；构造 `modified` 早于/晚于延迟的结账各一个，断言只有满足的进入范围；构造早于 cutoff 的结账，断言不进入范围。

### BD06 · 商品渠道可售性诊断
- 覆盖需求：R07
- 设计说明：
  - **模块落点**：新增查询 `productChannelDiagnostics`，resolver 放在 `saleor/graphql/product/`（新模块，如 `diagnostics.py`），复用 `saleor/product/` 与 `saleor/warehouse/availability.py` 的既有可售性判定，不另写一套计算。新增类型 `ProductChannelDiagnostics`、`ProductChannelDiagnostic`、`ProductChannelDiagnosticSeverityEnum`、`ProductChannelDiagnosticCodeEnum`、`ProductChannelDiagnosticsFilterInput` 与 Countable 连接。
  - **业务逻辑**：按商品所属渠道逐渠道输出 `isAvailable` 与按严重度分类的 findings。严重度三分：`ERROR`（阻断，如渠道停用、未发布、可购买时间未到、无可售变体、无仓库关联、无可用库存、缺少渠道价）、`WARNING`（不阻断但需注意）、`NOT_APPLICABLE`（该商品在该渠道不适用的检查）。判定清单的实现以现有可售性计算为准，避免把正常满足的依赖报成错误（AC-07-3）；数字类（不需配送）商品只把配送区域类检查标为 `NOT_APPLICABLE`，库存、发布与核心条件继续执行（AC-07-4）。筛选支持渠道名、币种、可用性与严重度，分页沿用游标连接，满足 AC-07-1。权限沿用 `MANAGE_PRODUCTS` 与渠道可见性，无权限返回权限错误且不返回受限字段（AC-07-5）。
  - **失败语义**：诊断计算失败返回错误而不是上一次结果；不缓存跨请求的旧结论，满足 AC-07-6 的服务端部分（「不把旧诊断当最新结论」由每次请求重算保证）。
  - **数据模型**：不新增持久字段；findings 为计算产物。
  - **迁移与验证方法**：无迁移。验证点：构造多渠道路径差异的商品断言筛选与计数；构造未发布/库存不足/无仓库/无配送区域的渠道断言对应 code 与严重度；数字类商品断言配送区域类检查为 `NOT_APPLICABLE`。

### BD07 · 主体搜索范围与索引维护
- 覆盖需求：R08、R09
- 设计说明：
  - **模块落点**：保持 `saleor/product/search.py`、`saleor/order/search.py`、`saleor/giftcard/search.py` 的全文检索实现；`saleor/account/search.py:128` 的 `search_document__ilike` 与 `saleor/graphql/page/filters.py:58` 的 trigram 保持；索引维护沿用 `saleor/product/tasks.py:301` 与 `saleor/giftcard/tasks.py:32` 的 `search_index_dirty` 批次任务。
  - **业务逻辑**：结账、礼品卡、商品、订单保留各自的关键词、前缀、组合词、短语与相关度行为；Page/User 不新增向量检索、前缀或相关度增强、RANK 排序、专用索引、后台任务与迁移（AC-08-3）。**范围声明**：礼品卡与结账在基线中即没有独立的 RANK 排序字段，本轮不新增；「按相关度排序」在礼品卡上由 `websearch` 检索语义决定，在订单与商品上由既有 `RANK` 排序提供（AC-08-1 按此解释，见 §6）。页面标题变化影响商品引用名称时，商品搜索向量仍由 `saleor/product/tasks.py` 的更新任务重建，不因页面侧改动而失效（AC-08-4）。
  - **一致性、分页与异常（R09）**：新值在既有最终一致性窗口内可检索，`search_index_dirty` 标记保证更新不丢；排序与游标沿用各域既有 `sorters.py`，保证翻页稳定；空关键词不触发全量查询（沿用现有 filter 的空值短路）；过长/非法输入与检索服务异常返回空态、校验错误或错误状态，不阻塞其他列表；客户与员工的隐私字段继续受权限过滤（AC-09-5）。
  - **数据模型**：无变化（不新增索引）。
  - **迁移与验证方法**：无迁移。验证点：创建/修改/归档对象后在窗口后检索新值；重复关键词跨页断言无重复无遗漏；空关键词与非法输入断言响应可解释。

### BD08 · 礼品卡交易生命周期
- 覆盖需求：R10
- 设计说明：
  - **模块落点**：`saleor/payment/models.py:31 TransactionItem` 与 `:194 TransactionEvent` 作为统一记录；礼品卡侧复用 `saleor/giftcard/`（`models.py`、`events.py`、`utils.py`）；新增 GraphQL 变更 `checkoutGiftCardAuthorize`（`saleor/graphql/checkout/mutations/`）与类型 `GiftCardPaymentMethodDetails`。金额重算复用 `saleor/payment/transaction_item_calculations.py:352 recalculate_transaction_amounts`。
  - **业务逻辑**：授权时校验礼品卡存在、启用、未过期、币种与结账币种一致、余额充足，任一不满足即失败且**不修改**余额与支付状态。成功后创建 `TransactionItem`（`paymentMethodDetails` 为 `GiftCardPaymentMethodDetails`，`giftCard` 指向该卡），写入 `AUTHORIZATION_SUCCESS` 类事件并冻结相应余额。`TransactionItem.giftCard` 与 `PaymentMethodTypeEnum.GIFT_CARD` 让 Dashboard 与交易查询能区分礼品卡（AC-10-1）。幂等：以结账 + 礼品卡 + 幂等键定位已有授权，重复请求直接返回既有交易，不产生第二次冻结（AC-10-4）。权限不足、状态非法或金额超限返回错误，绝不静默改走普通支付（AC-10-3）。
  - **数据模型**：复用 `TransactionItem`/`TransactionEvent`；`TransactionItem.giftCard` 为新增字段（Django 模型字段 `gift_card`，外键，可空），配迁移；礼品卡余额与冻结沿用既有礼品卡字段与事件。
  - **事务/异步/失败语义**：授权在单事务内完成「校验 → 建交易 → 写事件 → 调余额」；任一步失败整体回滚；并发同请求由幂等键 + 唯一约束保证只产生一次冻结。
  - **迁移与验证方法**：新增可空外键迁移。验证点：五类不合格礼品卡逐一断言失败且余额不变；同一请求重复提交断言只有一次余额变化与一条授权交易。

### BD09 · 礼品卡取消与退款
- 覆盖需求：R11
- 设计说明：
  - **模块落点**：新增 `checkoutGiftCardCancel`（`saleor/graphql/checkout/mutations/`）与 `orderGiftCardRefund`（`saleor/graphql/order/mutations/`），分别返回 `CheckoutGiftCardCancel` 与 `OrderGiftCardRefund` payload。
  - **业务逻辑**：取消只作用于结账阶段尚未扣款的授权，释放冻结金额并写取消事件，结账支付状态同步（AC-11-1）；退款只作用于订单上已扣款的礼品卡交易，金额不得超过该交易的可退余额，等于边界可成功（AC-11-2）。两者都不混用：结账取消走结账路径，订单退款走订单路径。交易事件、礼品卡余额、结账/订单支付与退款状态在同一事务内更新，保证三者反映同一结果（AC-11-3）。
  - **失败语义**：礼品卡交易不存在 → `NOT_FOUND`；金额超过可退余额 → `OrderErrorCode.AMOUNT_GREATER_THAN_AVAILABLE`；状态不允许 → `OrderErrorCode.TRANSACTION_ERROR`；无权限 → 权限错误且不泄露金额。无事件时返回空事件列表且整体视为成功（AC-11-5）。
  - **数据模型**：无新增字段（复用 `TransactionEvent` 与礼品卡余额）。
  - **事务/异步/失败语义**：单事务；幂等键 + 状态检查防止重复退款。
  - **迁移与验证方法**：无迁移。验证点：结账取消后断言冻结归零、结账支付状态与事件一致；订单退款等于可退余额成功、超一分失败且状态不变。

### BD10 · 订单金额摘要一致性
- 覆盖需求：R12
- 设计说明：
  - **模块落点**：`saleor/order/models.py` 的金额字段与 `saleor/order/utils.py` 的 `_update_order_total_charged`（L1073）、`_update_order_total_authorized`（L1110）以及 `saleor/order/actions.py:484` 附近的退款累加；GraphQL 侧 `saleor/graphql/order/types.py` 的 `Order` 解析。
  - **业务逻辑**：摘要口径固定为——商品 = `subtotal`，折扣 = `discounts`，税费 = `total.tax`，配送 = `shippingPrice`，礼品卡 = 新增 `totalGiftCard`，已授权 = `totalAuthorized`，已扣款 = `totalCharged`，已退款 = `totalRefunded`，剩余待付 = `totalBalance`。**去重规则**：礼品卡交易不计入 `totalAuthorized`、`totalCharged`、`totalCanceled`、`totalRefunded`，只计入 `totalGiftCard`（礼品卡已扣款净额 = 已扣款 − 已退款）；`totalBalance = total − (totalCharged − totalRefunded) − totalGiftCard`。兼容旧 `Payment` 与新 `TransactionItem`：汇总时按记录维度去重，同一事件的金额只计一次（AC-12-2、AC-12-3）。由此 AC-12-4 的「礼品卡既不重复计入也不遗漏」由字段口径保证。
  - **失败语义**：金额字段只读，无写入失败路径；计算依赖最新订单状态，幂等。
  - **数据模型**：`Order` 新增 `totalGiftCard`（可由交易聚合派生，按现有 `total_charged` 的做法决定是否持久化；本设计选择派生计算，避免多一份可能与交易不一致的持久状态）。
  - **迁移与验证方法**：无强制迁移（若选择持久化则补一条回填迁移）。验证点：构造含折扣/税费/配送/礼品卡/多笔支付的订单，断言各项之和与 `total` 一致；同一订单同时存在旧支付与新交易时断言不重复计入。

### BD11 · 人工资金动作的约束与幂等
- 覆盖需求：R13
- 设计说明：
  - **模块落点**：`saleor/graphql/order/mutations/order_mark_as_paid.py`、`order_capture.py`、`order_refund.py`；可执行动作由 `saleor/graphql/order/types.py:2167 resolve_actions` 与 `saleor/graphql/payment/types.py:224 resolve_actions` 计算；订单动作枚举 `saleor/graphql/payment/enums.py:47 OrderAction`。
  - **业务逻辑**：`Order.actions` 只返回当前支付方式与状态允许的动作（AC-13-1 前半）。`orderMarkAsPaid` 在订单已有支付/交易记录时拒绝，无记录且满足条件时成功（AC-13-2）。`orderCapture` 的金额上限为当前可捕获授权，等于边界成功、超过拒绝（AC-13-3）。`orderRefund` 的金额上限为可退余额，多笔交易共享同一额度、不重复占用（AC-13-4）。金额为负由 `PositiveDecimal` 与新增的负数校验在执行前拒绝。
  - **失败语义**：新增 `OrderErrorCode.AMOUNT_GREATER_THAN_AVAILABLE`（金额超限）、`OrderErrorCode.PAYMENT_ALREADY_EXISTS`（已有支付记录仍尝试标记已支付）；其余沿用 `CAPTURE_INACTIVE_PAYMENT`、`VOID_INACTIVE_PAYMENT`、`PAYMENT_MISSING`、`TRANSACTION_ERROR`。失败不改变订单状态、不写事件。无权限返回权限错误且响应不含受限金额（AC-13-7）。
  - **事务/异步/失败语义**：单事务；幂等由「按最新订单状态判定上限」保证——重复提交在额度耗尽后自然被拒，不产生第二次扣款/退款或冲突事件（AC-13-5）。成功后 resolver 返回刷新后的订单与交易，客户端重新读取即可（AC-13-6）。
  - **数据模型**：无新增字段。
  - **迁移与验证方法**：无迁移。验证点：捕获等于/超过授权边界；多交易订单连续退款到额度耗尽；重复提交同一动作断言金额与事件数量不变。

### BD12 · 根级交易查询
- 覆盖需求：R14
- 设计说明：
  - **模块落点**：`saleor/graphql/payment/schema.py` 新增 `Query.transactions`，resolver 与过滤器放在 `saleor/graphql/payment/`（如 `resolvers.py`/`filters.py`），返回新增 `TransactionCountableConnection`/`TransactionCountableEdge`。
  - **业务逻辑**：`TransactionFilterInput` 扩展 `ids`、`tokens`、`orderIds`、`checkoutIds`、`pspReferences`、`appIds`、`appIdentifiers`，与既有 `paymentMethodDetails`、`metadata` 组合，覆盖 AC-14-1、AC-14-2。返回字段包含订单/结账关联、金额、`paymentMethodDetails`、`actions`、`events` 与 `app`/`appIdentifier`，满足 AC-14-3。**明确不做**：不新增按创建/修改日期、事件类型或日期筛选，不新增该查询的 `sortBy` 与专用索引（AC-14-5）；默认排序按 `-created_at, -id` 固定，游标稳定。
  - **权限与可见范围**：`HANDLE_PAYMENTS` 基础上叠加既有对象范围：客户只能看到与自己订单/结账关联的交易，App 只能看到自己创建或有权访问的交易，员工按渠道/仓库可见性过滤（AC-14-4）。
  - **失败语义**：空分页项、越界分页、错误过滤类型、无权限均返回稳定错误，不用成功空结果掩盖（AC-14-6）。
  - **数据模型**：不新增索引（按 AC-14-5）。
  - **迁移与验证方法**：无迁移。验证点：按四类主体条件各查一次；以客户身份查询断言只返回自己的交易；越界分页断言错误。

### BD13 · 密码登录策略
- 覆盖需求：R17
- 设计说明：
  - **模块落点**：商店级设置落点在 `saleor/site/` 的商店设置模型与 `Shop` 类型；生效点在 `saleor/graphql/account/mutations/authentication/` 下的 `create_token.py`、`request_password_reset.py`、`set_password.py`、`password_change.py`，以及可绕过策略的旧 token 路径（`tokenCreate`/`tokenRefresh` 相关实现）。
  - **业务逻辑**：`PasswordLoginModeEnum` 三值。`ENABLED` 按账户状态放行；`CUSTOMERS_ONLY` 下只有客户身份可用密码，员工凭密码不得取得员工会话或后台权限（AC-17-2）；`DISABLED` 同时拒绝登录、重置、设置与修改密码，以及旧 token 路径（AC-17-3）。所有入口读取同一个生效值，不缓存跨请求副本，因此保存后立即生效（AC-17-4）。外部认证独立按自身配置处理，不受该模式影响。
  - **失败语义**：新增 `AccountErrorCode.PASSWORD_LOGIN_DISABLED` 与 `AccountErrorCode.PASSWORD_LOGIN_CUSTOMERS_ONLY`，返回明确原因。修改需要商店设置权限，无权限返回 `OUT_OF_SCOPE_PERMISSION`/`FORBIDDEN`（AC-17-5）。加载或保存失败保留上次生效值（AC-17-6）。
  - **数据模型**：商店设置新增一个带 choices 的字段，默认 `ENABLED` 以保持既有行为；配迁移。
  - **事务/异步/失败语义**：设置为同步写入，无异步副作用。
  - **迁移与验证方法**：新增字段默认值迁移。验证点：三种模式各跑一遍登录/重置/设置/修改/旧 token 路径；切换后立即发起认证断言读到新值。

### BD14 · 外部身份关联与离线授权
- 覆盖需求：R18
- 设计说明：
  - **模块落点**：`saleor/plugins/openid_connect/plugin.py:222-229` 的 scope 拼装与授权参数；`saleor/plugins/openid_connect/utils.py:391 get_or_create_user_from_payload` 的身份关联。
  - **业务逻辑**：Google provider 在需要 refresh token 时改为携带 `access_type=offline` 参数，不再用 `offline_access` scope；其他 provider 保持各自现有合同。首次把外部身份关联到已存在的本地用户时，清理或禁用该用户的本地密码路径（置空可用密码/禁用密码登录标记），使旧密码不能绕过外部身份策略（AC-18-3）。同一 OIDC 身份后续登录按既有 `sub`/email 关联稳定命中同一用户，不重复创建（AC-18-4）。
  - **失败语义**：授权失败返回可识别的错误码，错误响应与前端存储都不含 token 或敏感身份信息（AC-18-2）。
  - **数据模型**：若需要记录「外部身份已关联」，复用现有外部身份关联记录；不新增独立表。
  - **迁移与验证方法**：无数据迁移。验证点：断言授权请求参数与 scope；对已存在本地用户的邮箱走一次首次关联，断言旧密码登录失败、二次登录命中同一用户。

### BD15 · 富文本与外链校验
- 覆盖需求：R19
- 设计说明：
  - **模块落点**：`saleor/core/utils/editorjs.py:32 clean_editor_js` 及 `clean_text_data_block`（L122）；写入路径为 `SanitizedJSONField`（`saleor/core/db/fields.py:12`）与 RICH_TEXT 属性处理器（`saleor/graphql/attribute/utils/type_handlers.py:569 RichTextAttributeHandler`）。
  - **业务逻辑**：把当前「只黑名单 javascript」的清理升级为「先结构校验、再 URL/属性清理、最后深度校验」：白名单允许的块与字段之外的多余/未知字段被拒绝；链接按 `http`、`https`、`mailto`、`tel` 白名单保留，其余 scheme 拒绝；嵌套深度超过上限拒绝；`target="_blank"` 的外链补安全 `rel` 行为。协议白名单不可通过配置扩展（AC-19-4）。
  - **失败语义**：新增错误码 `RICH_TEXT_INVALID`（结构/未知字段）、`RICH_TEXT_UNSAFE_LINK`（非法 scheme）、`RICH_TEXT_TOO_DEEP`（超深嵌套），加入 `AttributeErrorCode`、`PageErrorCode`、`ProductErrorCode`；错误指向具体字段或链接位置，且在写库前抛出，不留下部分危险数据（AC-19-2、AC-19-5）。合法内容（含嵌套列表与常用链接）正常保存（AC-19-1、AC-19-3）。
  - **数据模型**：无变化（沿用 `SanitizedJSONField`）。
  - **迁移与验证方法**：无迁移。验证点：合法内容保存成功；未知字段/`javascript:`/超深嵌套各断言拒绝且库中无部分写入。

### BD16 · 扩展安装约定与历史扩展适配
- 覆盖需求：R20
- 设计说明：
  - **模块落点**：`saleor/app/models.py:156 AppExtension`、`saleor/app/manifest_validations.py:143 clean_manifest_data` 与 `:291 _clean_extensions`；GraphQL 侧 `saleor/graphql/app/types.py`、`saleor/graphql/app/resolvers.py:72 resolve_app_extensions`、`saleor/graphql/app/mutations/`。
  - **业务逻辑**：`AppExtension` 与 `AppManifestExtension` 暴露 `mountName`、`targetName`、`settings`，`mount`/`target` 加弃用标记并继续按既有映射返回，使历史扩展无需重装即可查询、编辑与渲染（AC-20-1、AC-20-2）。安装/更新前校验 identifier 唯一性、权限合法性、target 合法性、settings 可解析性，失败时拒绝且不破坏已有数据（AC-20-3）。可选安装信息（含 `tokenTargetUrl`）缺省不影响合法安装，不需要时不返回新建或安装 token（AC-20-4）。新客户端使用新字段，旧字段仅作弃用读取（AC-20-5）。安装与更新需要 App 管理权限，读取按调用方可见范围过滤。
  - **数据模型**：`AppExtension` 增加 `mount_name`、`target_name`、`settings` 字段；配数据迁移，把既有 `mount`/`target` 值映射到新字段并保留 `settings` 内容，可在空库执行且不重复生成记录。
  - **事务/异步/失败语义**：安装/更新在单事务内完成；manifest 拉取失败不写库。
  - **迁移与验证方法**：新增字段 + 数据回填迁移。验证点：对迁移前数据断言新字段可读且 `settings` 保留；非法 identifier/权限/target/settings 各断言拒绝且原数据不变。

### BD17 · Webhook 载荷构建与投递隔离
- 覆盖需求：R23、R24
- 设计说明：
  - **模块落点**：订阅解析 `saleor/graphql/webhook/subscription_payload.py`（`generate_payload_promise_from_subscription` L81、`generate_payload_from_subscription` L165）；延迟载荷 `saleor/webhook/transport/utils.py:94 prepare_deferred_payload_data` 与 `saleor/webhook/transport/asynchronous/transport.py:500 generate_deferred_payloads`；投递 `send_webhook_request_async`（L603）、`send_webhooks_async_for_app`（L678）；重试 `saleor/webhook/transport/utils.py:333 handle_webhook_retry` 与 `MAX_WEBHOOK_RETRIES = 5`（`asynchronous/transport.py:77`）；模型 `saleor/core/models.py:206 EventDelivery`、`:223 EventDeliveryAttempt`。
  - **业务逻辑**：同步订阅只解析被选中的字段（AC-23-1）；订单、草稿订单与履约等允许异步的事件在后台任务边界构建完整载荷，业务请求不等待（AC-23-2）；纯异步订阅不触发无关同步通知，也不额外调用未需要的税务/配送服务（AC-23-3）；调用次数、超时、重试与熔断沿用既有上限，不通过重复解析放大负载（AC-23-4）。投递以 delivery 为单位隔离：一个接收方失败不重做其他已成功的投递（AC-24-1），重试只作用于该 delivery（AC-24-2）。变体折扣价等已定义事件在实质变化时产生一次通知，无实质变化的保存不重复触发（AC-24-3）。
  - **失败语义**：投递状态新增 `RETRYING`，与 `PENDING`/`SUCCESS`/`FAILED` 一起区分「尚未生成内容」与「已失败」；异步内容未生成不显示为成功（AC-24-4）。单条重试走既有 `eventDeliveryRetry`（`saleor/graphql/webhook/mutations/event_delivery_retry.py`），需相关 App 或业务域权限，内容仍遵守 App 可见字段边界（AC-24-5）。既有失败告警保留，不扩展为 App Problems（AC-24-6）。
  - **数据模型**：`EventDelivery.status` 复用既有状态字段并扩展取值，配迁移（仅 choices 扩展，无数据回填）。
  - **迁移与验证方法**：choices 扩展迁移。验证点：一个事件配两个接收方，其中一个目标地址不可达，断言另一个成功且不被重做；断言失败 delivery 进入 `RETRYING` 并按上限重试。

### BD18 · 订单配送元数据快照
- 覆盖需求：R25
- 设计说明：
  - **模块落点**：结账成单在 `saleor/checkout/complete_checkout.py`（`_prepare_order_data` L641、`create_order_from_checkout` L1562）写订单时取快照；草稿订单成单在 `saleor/graphql/order/mutations/draft_order_complete.py`；读取侧在 `saleor/graphql/order/types.py`（`Order`、`Fulfillment`）。
  - **业务逻辑**：两条成单路径都在订单创建时把当时的配送方式（`ShippingMethod` 或自提 `Warehouse`）的 public 与 private 元数据复制到订单侧快照；源对象之后被修改、停用或删除都不回写快照（AC-25-3）。公开与私有元数据仍按权限可见，事件内容与订单一致（AC-25-4）。订单与履约都可读同一份快照。
  - **数据模型**：订单侧新增快照字段（配送方式 ID、名称、public/private 元数据），由 `Order` 与 `Fulfillment` 暴露为 `deliveryMethodSnapshot: DeliveryMethodSnapshot`；配迁移把既有订单按当前可得的配送方式元数据回填一次，无元数据的历史记录返回稳定空值（AC-25-5）。
  - **事务/异步/失败语义**：快照在订单创建事务内写入，与订单同生共死；回填迁移为幂等（按订单是否已有快照判断），可重复执行不产生重复记录。
  - **迁移与验证方法**：新增字段 + 幂等回填迁移。验证点：结账成单与草稿成单各断言快照存在；删除配送方式后断言订单快照不变；重复执行回填迁移断言记录数不变。

### BD19 · 基础元数据读写边界
- 覆盖需求：R26
- 设计说明：
  - **模块落点**：结账、草稿订单、订单、履约的既有元数据字段与变更（`updateMetadata`/`deleteMetadata`、`updatePrivateMetadata`/`deletePrivateMetadata`），以及订单行元数据能力。
  - **业务逻辑**：保留必要的基础读写，不新增订单/履约/仓库的独立元数据弹窗、专用路由或独立入口所对应的后端类型与变更。合法键值按权限保存与读取；非法值、权限不足或保存失败不改变原值，且不出现部分写入（AC-26-1 至 AC-26-3）。
  - **对外接口变更**：**无**。本轮不新增元数据相关类型、字段或变更；`target-schema.graphql` 中相关定义与基线逐字一致。
  - **迁移与验证方法**：无迁移。验证点：对四类对象执行合法读写断言成功；非法键值/无权限断言原值不变。

### BD20 · 输入校验与失败语义
- 覆盖需求：R27
- 设计说明：
  - **模块落点**：`saleor/graphql/core/validators/__init__.py`（`validate_one_of_args_is_in_mutation`、`validate_price_precision`、`validate_limit_of_list_input` 等）、`saleor/graphql/core/connection.py:382` 起的分页校验（`GRAPHQL_PAGINATION_LIMIT = 100`，`saleor/settings.py:839`）、`saleor/graphql/core/scalars.py:202/206/210` 的 `Minute`/`Hour`/`Day`。
  - **业务逻辑**：把校验前移到执行前：`Minute`/`Hour`/`Day` 拒绝负数（当前是 `graphene.Int` 空子类，不拒绝）；枚举取值非法、必填缺失、组合关系不成立在执行前返回校验错误；Federation representations 为 null 或含 null 项返回稳定错误；数组空项、错误类型、越界分页返回稳定错误。失败统一返回可按 field/code/message 分支的错误，不产生部分写入；底层未知错误不被转换成成功空列表（AC-27-5）。合法的单值、数组与组合查询继续可用；对象 ID、结账 token、UUID、渠道 slug 各按自身类型解析，类型不匹配即报错（AC-27-7）。
  - **失败语义**：GraphQL 响应体（含 `errors` 与 payload 内 `errors`）是业务成功与否的唯一依据；HTTP 200 不代表业务成功（AC-27-1）。
  - **数据模型**：无变化。
  - **迁移与验证方法**：无迁移。验证点：负数分钟/小时/天数、非法枚举、越界分页、null representation、错误类型参数各断言执行前报错且无写入。

### BD21 · 弃用读取与迁移边界
- 覆盖需求：R28
- 设计说明：
  - **模块落点**：`saleor/graphql/schema.graphql` 生成源中的 `@deprecated` 标记；插件注册（旧 Adyen、NP Atobarai）；`saleor/graphql/order/mutations/draft_order_create.py`/`draft_order_update.py` 的 `voucherCode`。
  - **业务逻辑**：仍支持的旧用法给出弃用读取与替代路径；已不支持的能力返回不存在或迁移错误，不返回无解释的成功空响应（AC-28-1、AC-28-2）。本轮新增弃用标记：`Payment.partial`、数字商品查询与变更（`digitalContent`、`digitalContents`、`digitalContentCreate`、`digitalContentDelete`、`digitalContentUpdate`、`digitalContentUrlCreate`）、`ProductVariant.digitalContent`、草稿订单的 `voucher`（改用 `voucherCode`），见 `target-schema.graphql`。属性的 `name`/`slug`/`type` 不能为空、App 安装的 `appName`/`manifestUrl` 必填（`AppInstallInput` 两者改为非空），满足 AC-28-5。
  - **导出**：本基线中导出只有一种方式——`exportProducts`/`exportGiftCards`/`exportVoucherCodes` 创建任务、`exportFile`/`exportFiles` 读取文件。不存在可被弃用的旧导出变更，因此**不新增弃用标记**，现有入口即为「当前查询导出方式」，权限沿用 `MANAGE_PRODUCTS`/`MANAGE_GIFT_CARD`/`MANAGE_DISCOUNTS`（AC-28-3 按此解释，见 §6）。AC-28-6 的一致性由 `target-schema.graphql` 与 `interface-contract.md` 的 I 编号逐条对应保证。
  - **数据模型**：无变化。
  - **迁移与验证方法**：迁移须能从空库执行并保留既有订单、交易、扩展、库存与元数据的业务含义（AC-28-7）。验证点：空库 `migrate` 全绿；对弃用字段断言带标记且可读；对 `AppInstallInput` 缺字段断言校验错误。

### BD22 · 权限与可见范围一致性
- 覆盖需求：R29
- 设计说明：
  - **模块落点**：`saleor/graphql/core/permissions.py` 与各域 resolver 的权限装饰；员工删除 `saleor/graphql/account/mutations/staff/`；导出 `saleor/graphql/csv/`；税务敏感字段解析。
  - **业务逻辑**：员工删除执行真正的删除（含目标员工有历史订单的情况），自删或无权限删除被拒（AC-29-2）。属性更新、App 安装、导出、敏感税务字段读取在所有入口保持同一权限判定，不因换入口放宽（AC-29-1、AC-29-3）。结账与订单的私有元数据、用户等税务敏感字段遵循 `HANDLE_TAXES` 等权限（AC-29-4）。客户/员工/App 的对象范围、渠道与仓库可见性在列表、导出、批量操作与错误信息中一致；无权限返回权限错误而不是空列表，失败不表现为成功（AC-29-5）。
  - **对外接口变更**：**无新增字段或类型**；本轮只收敛既有权限判定与可见范围过滤的行为一致性。
  - **迁移与验证方法**：无迁移。验证点：对每个入口用无权限身份断言拒绝且响应不含受限数据；有权限员工删除含历史订单的员工断言记录真正删除。

### BD23 · 交付范围边界
- 覆盖需求：R32
- 设计说明：
  - **模块落点**：schema 生成与代码评审约束，无运行时落点。
  - **业务逻辑**：不新增 App Problems 的类型、字段、创建/关闭操作与问题列表；不新增 Page/User 的高级搜索、RANK 排序与专用索引；不新增交易日期/事件筛选与该查询的专用排序索引；不新增异步外链图片抓取与 pending/503/proxy 状态；不新增独立变体生成器页面、菜单、任务与状态；不新增订单/履约/仓库的独立元数据入口所对应的后端类型。同时保留：普通单变体创建、必填属性、`hasVariants` 兼容行为与普通批量创建；同步外链图片、本地上传与外部视频/oEmbed；基础交易查询；基础元数据编辑；Webhook 失败告警（AC-32-1 至 AC-32-5）。
  - **对外接口变更**：**无**。本单元的作用是「不新增」，`target-schema.graphql` 与基线相比的新增项都能逐条追溯到 R01–R31，没有额外类型。
  - **验证方法**：对照 `target-schema.graphql` 与基线 schema 的差集逐条核对归属需求；检查 Dashboard 生成客户端不包含被排除操作。

## 4. 接口清单

完整契约集中写在 `interface-contract.md`（I 的权威定义）。下表中「无对外接口变更」的设计单元保留行并说明原因。

| 接口 | 所属设计单元 | 说明 |
| --- | --- | --- |
| I01 | BD01 | `checkoutDeliveryOptions` 结账配送选项重算查询 |
| I02 | BD01 | `checkoutDeliveryMethodUpdate`/`checkoutComplete` 的配送有效性重校验与失效错误码 |
| I03 | BD02 | 旧 `shippingMethod` 字段与已弃用配送入口的兼容读取与归属校验 |
| I04 | BD03 | `StockSettings.stockAvailabilityMode` 库存模式配置与地址参数兼容 |
| I05 | BD04 | `Checkout.automaticCompletion` 自动完成状态与阻断原因 |
| I06 | BD05 | 渠道自动完成策略的延迟与 cutoff 配置 |
| I07 | BD06 | `productChannelDiagnostics` 商品渠道可售性诊断查询 |
| I08 | BD07 | 主体搜索范围与排序边界（无新增排序字段） |
| I09 | BD07 | 搜索一致性、分页与异常语义 |
| I10 | BD08 | 礼品卡支付方式、授权变更与交易关联 |
| I11 | BD09 | `checkoutGiftCardCancel` 与 `orderGiftCardRefund` |
| I12 | BD10 | 订单金额摘要字段与去重口径 |
| I13 | BD11 | 人工资金动作的金额边界、错误码与幂等 |
| I14 | BD12 | 根级 `transactions` 查询与筛选条件 |
| I15 | BD13 | `Shop.passwordLoginMode` 的读取与配置 |
| I16 | BD14 | Google OIDC 离线授权与身份关联（非 GraphQL，见 `interfaces/oidc-offline-access.md`） |
| I17 | BD15 | 富文本校验错误码 |
| I18 | BD16 | 扩展 `mountName`/`targetName`/`settings` 与旧字段弃用 |
| I19 | BD16 | `AppInstallInput` 必填校验与 `tokenTargetUrl` 可选约定 |
| I20 | BD17 | Webhook 载荷构建边界与投递状态 |
| I21 | BD17 | `eventDeliveryRetry` 单条重试 |
| I22 | BD18 | 订单与履约的配送元数据快照读取 |
| I23 | BD19 | 基础元数据读写语义（无对外接口变更） |
| I24 | BD20 | 输入校验与可分支失败语义 |
| I25 | BD21 | 弃用读取与迁移边界 |
| I26 | BD22 | 权限与可见范围一致性（无对外接口变更） |
| — | BD23 | 无对外接口变更：只做范围约束，不新增类型或字段 |

## 5. 工程任务与依赖

### BT01 · 结账配送与库存一致性
- 覆盖设计单元：BD01、BD02、BD03
- 依赖：无
- 工作与验证：先抽出 `clean_delivery_method` 中的共用校验（地址、有效集合、同步服务错误），再实现 `checkoutDeliveryOptions` 与 `CheckoutDeliveryOptions`/`DeliveryOption`/`DeliveryOptionStatusEnum`；补 `CheckoutErrorCode` 的四个新值并在更新/完成路径复用校验；随后实现渠道库存模式（字段 + 迁移 + `StockQuerySet` 分派）并把商品、结账、订单、履约、草稿订单统一到同一入口。完成依据：`target-schema.graphql` 中相关定义通过 SDL 校验；两种库存模式下各入口结果一致；旧配送入口的归属校验与新入口一致。

### BT02 · 自动完成策略与执行
- 覆盖设计单元：BD04、BD05
- 依赖：BT01
- 工作与验证：在渠道结账设置上新增延迟与 cutoff（字段 + 迁移 + `channelUpdate` 输入），实现批次扫描任务与结账侧诊断状态字段，把执行入口收敛到 `complete_checkout_with_transaction(is_automatic_completion=True)` 并保证单事务与幂等。完成依据：前置条件矩阵逐条断言不创建订单；同一结账并发/重试只产生一个订单与一次完成事件；延迟与 cutoff 的范围判定按 AC-06-3、AC-06-4 通过。

### BT03 · 商品渠道诊断
- 覆盖设计单元：BD06
- 依赖：BT01
- 工作与验证：复用既有可售性判定实现诊断 resolver 与连接类型，落地严重度三分与数字类商品的不适用处理，接入 `MANAGE_PRODUCTS` 与渠道可见性。完成依据：多渠道路径差异、未发布、库存不足、无仓库、无配送区域、数字类商品各断言 finding code 与严重度正确。

### BT04 · 搜索范围与索引维护
- 覆盖设计单元：BD07
- 依赖：无
- 工作与验证：核对并保持各域检索实现与排序集合，明确 Page/User 不新增高级搜索与 RANK；补齐空关键词、非法输入与检索异常的响应语义；确认页面标题变化后商品搜索向量的更新链路。完成依据：AC-08 与 AC-09 的验收场景逐条通过，且 schema 中不出现被排除的排序或筛选字段。

### BT05 · 礼品卡交易生命周期与金额摘要
- 覆盖设计单元：BD08、BD09、BD10、BD11、BD12
- 依赖：BT01
- 工作与验证：先加 `TransactionItem.giftCard` 字段（Django 模型字段 `gift_card`）与 `GiftCardPaymentMethodDetails`/`PaymentMethodTypeEnum.GIFT_CARD`，再实现授权、取消、退款三个变更与 `Order.totalGiftCard` 口径，随后收敛 `orderMarkAsPaid`/`orderCapture`/`orderRefund` 的边界与错误码，最后实现根级 `transactions` 查询与筛选。完成依据：五类不合格礼品卡、金额边界、重复提交、多交易额度共享、四类主体筛选与权限可见范围逐条断言通过；金额摘要各项之和与订单总额一致。

### BT06 · 身份策略与内容安全
- 覆盖设计单元：BD13、BD14、BD15
- 依赖：无
- 工作与验证：新增密码登录模式字段与迁移，在登录、重置、设置、修改与旧 token 路径统一读取生效值；OIDC 改为 `access_type=offline` 并在首次关联时清理旧密码路径；`clean_editor_js` 升级为结构 + scheme + 深度校验并补三个错误码。完成依据：三种登录模式 × 五类入口的矩阵通过；授权请求参数断言通过；非法富文本拒绝且无部分写入。

### BT07 · 扩展与事件
- 覆盖设计单元：BD16、BD17
- 依赖：无
- 工作与验证：`AppExtension` 新增 `mount_name`/`target_name`/`settings` 并回填历史数据，暴露新字段并把 `mount`/`target` 标为弃用；`AppInstallInput` 必填校验；`EventDeliveryStatusEnum` 扩展 `RETRYING` 并确保单条重试与投递隔离。完成依据：迁移前后历史扩展可查可编辑、`settings` 保留；一个接收方失败不影响其他接收方；失败投递状态与重试次数符合既有上限。

### BT08 · 历史数据、接口治理与权限
- 覆盖设计单元：BD18、BD19、BD20、BD21、BD22、BD23
- 依赖：BT05、BT07
- 工作与验证：订单配送元数据快照字段与幂等回填迁移；`Minute`/`Hour`/`Day` 拒绝负数与分页/枚举/必填的前置校验；补弃用标记与 `AppInstallInput` 必填；核对权限与可见范围在所有入口一致；最后对照基线核对新增 schema 项逐条可追溯。完成依据：空库迁移可执行；快照回填幂等；校验与权限矩阵通过；schema 差集无范围外新增。

## 6. 其他

### 前端承接需求的后端边界

R15、R16、R21、R22、R30、R31 由 Dashboard 承接，后端不新增对外接口：

- R15（锁定筛选与作用范围）：后端只需保证列表、导出与批量操作读取同一组筛选参数时返回一致的对象集合，权限不因入口不同而放宽。这些查询与变更均已存在，行为不变。
- R16（选择器与层级导航）：纯前端交互，后端沿用既有分类、仓库、配送区查询。
- R21（扩展回应表单）：`AppFrame` 的 postMessage 协议由前端处理，后端只提供扩展数据（见 I18）。
- R22（自托管扩展目录）：目录数据来自 Dashboard 侧的扩展目录来源，安装与展示复用既有 `appFetchManifest`、`appInstall` 与 `AppExtension` 查询（见 I18、I19），后端不新增目录接口。
- R30（迟到配置数据）：纯前端状态管理，后端只需在保存成功后返回最新对象（既有变更语义）。
- R31（展示准确性）：重量单位、金额与日期分组为前端展示逻辑；草稿订单动作可用性依赖既有的 `Channel.isActive`、`DraftOrderCreateInput` / `DraftOrderInput` 校验与商品可售性字段，无新增接口。

### 与冻结基线的差异说明

- **R08 的「按相关度排序」**：基线中礼品卡与结账没有独立的 RANK 排序字段（`GiftCardSortField`、`CheckoutSortField` 均无 `RANK`）。本设计不新增，避免与 AC-08-3「不出现页面与用户的 RANK 排序及专用索引」的排除口径产生歧义。相关度由既有 `websearch` 检索语义与各域排序提供。
- **R28 的「旧导出 mutation」**：基线中不存在可被弃用的旧导出变更，导出只有 `export*` 变更 + `exportFile(s)` 查询一种方式，故不新增弃用标记。
- **R14 的「App 标识」**：模型 `TransactionItem` 同时有 `app` 外键与 `app_identifier` 字段（`saleor/payment/models.py:135-147`），因此筛选同时支持 `appIds` 与 `appIdentifiers`，并新增 `TransactionItem.app`/`appIdentifier` 供展示。

### 风险

- 库存模式切换涉及商品、结账、订单、履约、草稿订单五处入口，若漏改一处会出现「各算一套」。缓解：统一到 `StockQuerySet` 单入口，并以 AC-04-2 的跨入口一致性断言作为完成门禁。
- 自动完成的幂等依赖结账状态机与订单对结账的唯一约束；若并发窗口内两次任务同时通过前置校验，仍须由数据库约束兜底。缓解：在订单创建处依赖既有约束并捕获 `IntegrityError` 短路。
- 礼品卡交易的金额口径改变会影响既有 `totalAuthorized`/`totalCharged` 的语义边界。缓解：礼品卡交易是本轮新增形态，既有数据不含此类记录，口径变化不影响历史订单；以 AC-12-2 至 AC-12-4 的断言固定口径。
- 富文本校验加严可能拒绝历史合法内容。缓解：校验只在写入路径生效，不扫描既有数据；`clean_editor_js` 保留对既有结构的兼容分支。

### 待确认项（承接 PRD §5.4）

- 自动完成配置的默认延迟、默认 cutoff 与批次规模的具体数值：本设计不设定数值默认，`NULL` 表示未配置，批次规模取现有批次任务惯例值，需在实现时确认。
- 礼品卡在交易生命周期中的记录形态：本设计选择复用统一交易模型（`TransactionItem` + `TransactionEvent` + 新增 `TransactionItem.giftCard` 字段），需研发确认。
- 商品渠道诊断中「警告」与「阻断」的具体判定清单：本设计给出 `ProductChannelDiagnosticCodeEnum` 的候选集合与严重度三分框架，具体归类需与渠道运营确认。
- 搜索最终一致性窗口的目标时长：本设计沿用既有 `search_index_dirty` + celery beat 批次任务，未新增数值目标。

<!-- BD / I / BT 编号发布后不重排、不复用。I 的权威定义在 interface-contract.md。 -->
