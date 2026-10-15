# 接口对齐文档：Saleor 3.23 结账、收款与商户运营一致性交付

版本：v1
责任：后端技术设计
依据：后端技术设计 v1，artifacts/sprint1/tech-design/backend-design.md
修订：首次交付。

## 1. 通用约定

### 入口与传输

- 所有接口均为 GraphQL。Core 侧统一入口为 `/graphql/`；Dashboard 侧通过 `saleorClient`/`apolloClient`（`src/graphql/client.ts`）消费同一 schema。
- 权威类型定义见同目录 `target-schema.graphql`（完整 SDL，基线定义逐字保留，新增项在文末集中定义）。本契约中的「目标定义」列出的操作、类型与字段名与 SDL 逐字一致。
- 非 GraphQL 的协议（Google OIDC 离线授权参数）见 `interfaces/oidc-offline-access.md`。

### 认证

| 调用方 | 认证方式 |
| --- | --- |
| 客户 / Storefront | JWT（`tokenCreate`）或结账 `token`（`UUID`） |
| 员工 / Dashboard | JWT（会话） |
| App | App token（`Authorization: Bearer <token>`） |
| 匿名 | 允许的公开查询（如按 token 的结账查询） |

### 错误分层

| 层 | 位置 | 用途 |
| --- | --- | --- |
| 传输层 | HTTP 状态码 | 只表示请求是否到达。**HTTP 200 不代表业务成功** |
| 顶层 GraphQL 错误 | `errors` 数组 | 请求级失败：未认证、无权限、对象不存在、输入类型不合法、参数越界 |
| Payload 级错误 | `payload.errors[].code / field / message` | 业务级失败：库存不足、金额超限、配送失效、礼品卡不可用 |
| 空结果 | `edges: []` + `totalCount: 0` | 合法的空集合，仅用于合法请求 |

规则：**没有权限不是「没有数据」**（返回权限错误而非空列表），**失败不是「操作成功」**（失败不产生部分写入），**未知底层错误不转成成功空列表**（R27、R29）。

### ID 与标识规则

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| 对象 ID | `ID`（base64 全局 ID） | 如 `productId`、`orderId`、`transactionId` |
| 结账 token | `UUID` | 结账的唯一入口标识，不能与对象 ID 互换 |
| 交易 token | `UUID` | `TransactionItem.token` |
| 渠道标识 | `String`（slug） | 如 `channel` 参数 |
| 幂等键 | `String` | 客户端生成的请求级标识 |

类型不匹配在执行前报错（R27）。

### 成功判定

1. 无顶层 `errors`；
2. mutation 的 `payload.errors` 为空数组；
3. 需要结果时 `node` 非空、连接返回的 `edges`/`pageInfo` 自洽。

### 编号

I 编号发布后不重排、不复用。新增接口往后编号。BD 编号的权威定义在 `backend-design.md`。

## 2. 接口契约

### I01 · 结账配送选项重算查询
- 所属设计单元：BD01
- 提供方：拟新增 —— `saleor/graphql/checkout/schema.py`（注册 `Query.checkoutDeliveryOptions`）、`saleor/graphql/checkout/resolvers.py`（resolver）；计算复用 `saleor/checkout/fetch.py` 的 `get_available_built_in_shipping_methods_for_checkout_info`、`get_valid_internal_shipping_methods_for_checkout_info`、`get_external_shipping_methods_for_checkout_info`、`update_delivery_method_lists_for_checkout_info`。
- 调用方：Storefront 集成方；Dashboard 结账详情（可选）。
- 目标定义：`Query.checkoutDeliveryOptions(token: UUID!): CheckoutDeliveryOptions!`；类型 `CheckoutDeliveryOptions`、`DeliveryOption`；枚举 `DeliveryOptionStatusEnum`；联合 `DeliveryMethod`；错误类型 `CheckoutError`、枚举 `CheckoutErrorCode`。
- 接口定义片段：

```graphql
query CheckoutDeliveryOptions($token: UUID!) {
  checkoutDeliveryOptions(token: $token) {
    checkout { id token deliveryMethod { __typename ... on ShippingMethod { id name } ... on Warehouse { id name } } }
    availableDeliveryOptions { id name price { currency amount } minimumDeliveryDays maximumDeliveryDays status deliveryMethod { __typename } }
    selectedDeliveryOption { id name status }
    errors { field message code }
  }
}
```

- 字段说明：

| 字段 | 语义 |
| --- | --- |
| `availableDeliveryOptions` | 当前结账可用的配送选项；已不适用的旧选项不出现 |
| `selectedDeliveryOption` | 结账当前选择的选项；已失效时仍返回且 `status: UNAVAILABLE` |
| `DeliveryOption.id` | 配送方式自身的 ID，可直接作为 `checkoutDeliveryMethodUpdate(deliveryMethodId:)` 入参 |
| `DeliveryOption.name` / `price` | 可用于展示的名称与价格 |
| `status` | `AVAILABLE` / `UNAVAILABLE` |

- 权限：结账 `token` 即凭证；结账不存在或不属于调用方返回顶层 `NOT_FOUND`，响应不含配送或地址信息。
- 错误：

| 场景 | 错误 |
| --- | --- |
| 地址缺失或不完整 | `errors[].code = SHIPPING_ADDRESS_NOT_SET` 或 `MISSING_ADDRESS_DATA`，`field` 指向地址字段 |
| 同步配送服务报错 | `errors[].code = DELIVERY_SERVICE_ERROR` |
| 结账不存在 / 不属于调用方 | 顶层 `NOT_FOUND` |
| 无权限 | 顶层权限错误 |

- 完成判定：调用返回且 `errors` 为空；结账的 `deliveryMethod` 与 `selectedDeliveryOption.id` 指向同一对象（AC-01-2）。失败时结账的配送选择未被写入（AC-01-4）。
- 变更与兼容：新增查询，纯只读，不改变任何既有字段语义。AC-01-3 的「重新计算」由每次请求重算保证，不使用跨请求缓存。

### I02 · 配送有效性重校验与失效错误码
- 所属设计单元：BD01
- 提供方：`saleor/graphql/checkout/mutations/checkout_delivery_method_update.py`、`saleor/graphql/checkout/mutations/checkout_complete.py`；共用校验抽自 `saleor/graphql/checkout/mutations/utils.py:75 clean_delivery_method`。
- 调用方：Storefront 集成方；Dashboard 结账详情。
- 目标定义：`Mutation.checkoutDeliveryMethodUpdate`、`Mutation.checkoutComplete`（签名不变）；`enum CheckoutErrorCode` 新增 `DELIVERY_METHOD_INVALIDATED`、`DELIVERY_METHOD_OUT_OF_SCOPE`。
- 接口定义片段：

```graphql
mutation CheckoutDeliveryMethodUpdate($id: ID, $deliveryMethodId: ID) {
  checkoutDeliveryMethodUpdate(id: $id, deliveryMethodId: $deliveryMethodId) {
    checkout { id deliveryMethod { __typename ... on ShippingMethod { id } } }
    errors { field message code }
  }
}

mutation CheckoutComplete($id: ID) {
  checkoutComplete(id: $id) { order { id } errors { field message code } }
}
```

- 字段说明：错误码语义 —— `DELIVERY_METHOD_INVALIDATED`：所选配送方式在提交时刻已不适用于当前结账（地址、渠道或同步配送服务结果变化导致）；`DELIVERY_METHOD_OUT_OF_SCOPE`：配送方式不属于当前结账（归属错误）。未设置配送方式沿用 `SHIPPING_METHOD_NOT_SET`；地址缺失沿用 `SHIPPING_ADDRESS_NOT_SET`；不适用的配送方式沿用 `DELIVERY_METHOD_NOT_APPLICABLE`。
- 权限：结账归属与权限校验沿用既有语义；失败时原有配送选择不被改写，不泄露配送信息。
- 错误：见上表；`checkoutComplete` 失败时不创建订单（AC-02-2、AC-02-3）。
- 完成判定：成功时 `errors` 为空且结账状态/订单已生成；失败时结账保持未完成、配送选择不变（AC-02-4）。
- 变更与兼容：`checkoutDeliveryMethodUpdate` 与 `checkoutComplete` 的**签名不变**，仅行为加严（提交时刻重新校验）。新增两个错误码值属于向后兼容的枚举扩展。

### I03 · 旧配送字段与旧入口的兼容读取
- 所属设计单元：BD02
- 提供方：`saleor/graphql/checkout/types.py`（`Checkout.shippingMethod`、`Checkout.shippingMethods`、`Checkout.availableShippingMethods`）、`saleor/graphql/order/types.py`（`Order.shippingMethod`、`Order.shippingMethods`、`Order.availableShippingMethods`）、`saleor/graphql/checkout/mutations/checkout_shipping_method_update.py`。
- 调用方：旧版 Storefront 与旧版集成方。
- 目标定义：`Checkout.shippingMethod: ShippingMethod @deprecated`、`Order.shippingMethod: ShippingMethod @deprecated`（基线已带弃用标记，保持不变）；`Mutation.checkoutShippingMethodUpdate @deprecated`（保持不变）。
- 接口定义片段：

```graphql
query LegacyCheckoutDelivery($token: UUID!) {
  checkout(token: $token) {
    deliveryMethod { __typename ... on ShippingMethod { id name } ... on Warehouse { id name } }
    shippingMethod { id name }
  }
}
```

- 字段说明：`shippingMethod` 返回与 `deliveryMethod` 一致的 `ShippingMethod` 对象；当 `deliveryMethod` 为自提 `Warehouse` 时返回 `null`。`availableShippingMethods` 返回与 `shippingMethods` 一致的结果。
- 权限：旧入口与旧字段不绕过渠道归属与权限校验。
- 错误：旧入口提交不属于当前结账的配送标识返回 `DELIVERY_METHOD_OUT_OF_SCOPE`，与 I02 一致（AC-03-3）。
- 完成判定：旧字段读取结果与当前配送约定一致且带弃用标记（AC-03-1）；旧入口提交合法标识成功、不合法被拒（AC-03-2）。
- 变更与兼容：字段与入口均为基线已有，本轮只保证归属校验与错误码与新入口一致，不新增弃用标记、不改变返回类型。

### I04 · 渠道库存可用性模式
- 所属设计单元：BD03
- 提供方：`saleor/graphql/channel/mutations/channel_update.py`（`checkoutSettings` 之外经 `stockSettings`）、`saleor/graphql/channel/types.py`（`Channel.stockSettings`）、`saleor/warehouse/models.py:329 StockQuerySet`。
- 调用方：商户运营、渠道运营（Dashboard 渠道设置页）；Storefront 与各入口间接消费（可售性结果）。
- 目标定义：`StockSettings.stockAvailabilityMode: StockAvailabilityModeEnum!`、`StockSettingsInput.stockAvailabilityMode: StockAvailabilityModeEnum`、`enum StockAvailabilityModeEnum { SHIPPING_ZONES CHANNEL_WAREHOUSES }`。
- 接口定义片段：

```graphql
mutation ChannelUpdate($id: ID!, $input: ChannelUpdateInput!) {
  channelUpdate(id: $id, input: $input) {
    channel { id slug stockSettings { stockAvailabilityMode allocationStrategy } }
    errors { field message code }
  }
}
```

- 字段说明：`SHIPPING_ZONES`——按配送区域与地址关联计算（默认，等价升级前行为）；`CHANNEL_WAREHOUSES`——只由 `ChannelWarehouse` 直接关联当前渠道的仓库参与计算。地址类参数在新模式下被接受但不影响结果。
- 权限：修改需要渠道管理权限；读取需要渠道可见性。
- 错误：无权限返回顶层权限错误；非法枚举值在执行前报错（I24）。
- 完成判定：保存后重新读取返回一致值；切换模式后商品查询、结账、订单、履约与草稿订单的可售性与库存结果一致（AC-04-2）；未切换渠道结果与升级前一致（AC-04-1）。
- 变更与兼容：`StockSettings` 新增**必填**字段 `stockAvailabilityMode`。必填意味着消费方必须在查询中选择它之外的字段不受影响；由于是新增字段而非修改既有字段，旧查询不受破坏。`StockSettingsInput.stockAvailabilityMode` 可空，未提供时保持当前模式。

### I05 · 自动完成状态与阻断原因
- 所属设计单元：BD04
- 提供方：`saleor/checkout/tasks.py:135 automatic_checkout_completion_task`（写入状态）、`saleor/graphql/checkout/types.py`（`Checkout.automaticCompletion` resolver）。
- 调用方：Dashboard 订单/结账运营。
- 目标定义：`Checkout.automaticCompletion: CheckoutAutomaticCompletion`；类型 `CheckoutAutomaticCompletion`；枚举 `CheckoutAutomaticCompletionStatusEnum`、`CheckoutAutomaticCompletionBlockerEnum`。
- 接口定义片段：

```graphql
query CheckoutAutomaticCompletion($token: UUID!) {
  checkout(token: $token) {
    id
    automaticCompletion {
      enabled
      status
      eligibleAt
      blockers
      lastAttemptAt
    }
  }
}
```

- 字段说明：`status` 取 `DISABLED` / `WAITING` / `READY` / `BLOCKED` / `COMPLETED`；`blockers` 取 `NOT_FULLY_PAID`、`MISSING_CUSTOMER`、`MISSING_BILLING_ADDRESS`、`MISSING_SHIPPING_ADDRESS`、`MISSING_DELIVERY_METHOD`、`DELIVERY_METHOD_NOT_APPLICABLE`、`PRODUCT_NOT_AVAILABLE`、`ZERO_TOTAL`、`ALREADY_COMPLETED`；`eligibleAt` 为最近修改时间 + 渠道延迟，未启用时为 `null`。
- 权限：需要 `MANAGE_ORDERS`；无权限返回 `null`（字段级不可见），不泄露结账处理细节。
- 错误：无错误路径；无权限时不返回该字段内容。
- 完成判定：失败后商户能看到可诊断原因与可重试状态（AC-05-6）；状态反映实际结账与订单事实，不表示「设置已保存」（AC-06-6）。
- 变更与兼容：新增字段，只读。

### I06 · 自动完成策略配置
- 所属设计单元：BD05
- 提供方：`saleor/graphql/channel/mutations/channel_update.py`（`checkoutSettings` 输入）、`saleor/graphql/channel/types.py`（`Channel.checkoutSettings`）。
- 调用方：渠道运营（Dashboard 渠道设置页）。
- 目标定义：`CheckoutSettings.automaticCompletionDelay: Minute`、`CheckoutSettings.automaticCompletionCutoff: DateTime`、`CheckoutSettingsInput.automaticCompletionDelay: Minute`、`CheckoutSettingsInput.automaticCompletionCutoff: DateTime`；既有 `automaticallyCompleteFullyPaidCheckouts: Boolean!` 保留。
- 接口定义片段：

```graphql
mutation ChannelCheckoutSettingsUpdate($id: ID!, $input: ChannelUpdateInput!) {
  channelUpdate(id: $id, input: $input) {
    channel {
      id
      checkoutSettings {
        automaticallyCompleteFullyPaidCheckouts
        automaticCompletionDelay
        automaticCompletionCutoff
      }
    }
    errors { field message code }
  }
}
```

- 字段说明：`automaticCompletionDelay` —— 结账最近一次修改之后需要经过的最短时间，`null` 表示无延迟（成为 fully paid 后立即进入待处理）；`automaticCompletionCutoff` —— 结账创建时间的下界，只处理在该时间或之后创建的结账，`null` 表示不限，**不是任务停止时间**。
- 权限：修改需要渠道管理权限；无权限返回顶层权限错误（`PERMISSION_DENIED`），`ChannelErrorCode` 无 `FORBIDDEN` 值，不新增。
- 错误：范围或组合非法返回 `ChannelErrorCode.INVALID`；保存冲突返回 `UNIQUE`/`ALREADY_EXISTS`；所有失败路径保留上次生效值（AC-06-5）。
- 完成判定：保存后重读一致（AC-06-1）；未配置渠道沿用关闭或既有默认行为（AC-06-2）；保存成功不改变任何结账或订单状态（AC-06-6）。
- 变更与兼容：`CheckoutSettings` 与 `CheckoutSettingsInput` 各新增两个可空字段。`automaticallyCompleteFullyPaidCheckouts` 语义不变。

### I07 · 商品渠道可售性诊断查询
- 所属设计单元：BD06
- 提供方：拟新增 —— `saleor/graphql/product/schema.py`（注册 `Query.productChannelDiagnostics`）、`saleor/graphql/product/diagnostics.py`（resolver）。
- 调用方：商品运营、渠道运营（Dashboard 商品编辑页）。
- 目标定义：`Query.productChannelDiagnostics(productId: ID!, filter: ProductChannelDiagnosticsFilterInput, before/after/first/last): ProductChannelDiagnosticsCountableConnection!`；类型 `ProductChannelDiagnostics`、`ProductChannelDiagnostic`、`ProductChannelDiagnosticsCountableConnection`、`ProductChannelDiagnosticsCountableEdge`；枚举 `ProductChannelDiagnosticSeverityEnum { ERROR WARNING NOT_APPLICABLE }`、`ProductChannelDiagnosticCodeEnum`；输入 `ProductChannelDiagnosticsFilterInput`。
- 接口定义片段：

```graphql
query ProductChannelDiagnostics($productId: ID!, $filter: ProductChannelDiagnosticsFilterInput, $first: Int, $after: String) {
  productChannelDiagnostics(productId: $productId, filter: $filter, first: $first, after: $after) {
    totalCount
    pageInfo { hasNextPage endCursor }
    edges {
      node {
        id
        isAvailable
        errorCount
        warningCount
        notApplicableCount
        channel { id slug name currencyCode }
        findings { code severity message field warehouse { id name } variants { id name } }
      }
    }
  }
}
```

- 字段说明：`isAvailable` 为该渠道下商品整体是否可售；三个计数按严重度统计 findings；`findings[].code` 取值见 `ProductChannelDiagnosticCodeEnum`（`CHANNEL_INACTIVE`、`NOT_PUBLISHED`、`PUBLICATION_DATE_IN_FUTURE`、`NOT_AVAILABLE_FOR_PURCHASE`、`AVAILABLE_FOR_PURCHASE_DATE_IN_FUTURE`、`MISSING_CHANNEL_LISTING`、`MISSING_PRICE`、`NO_VARIANTS`、`VARIANT_NOT_PUBLISHED`、`NO_WAREHOUSE_ASSIGNED`、`NO_SHIPPING_ZONE`、`SHIPPING_ZONE_NOT_COVERING_WAREHOUSE`、`OUT_OF_STOCK`、`MISSING_STOCK_FOR_VARIANTS`、`NO_DELIVERY_METHOD`）；数字类商品的配送区域检查返回 `severity: NOT_APPLICABLE`，其余检查照常返回。
- 权限：`MANAGE_PRODUCTS`；渠道可见性生效；无权限返回顶层权限错误，响应不含受限信息（AC-07-5）。
- 错误：无权限 → 顶层权限错误；`productId` 不存在 → 顶层 `NOT_FOUND`；非法枚举/越界分页 → 执行前报错（I24）。
- 完成判定：按渠道名或币种筛选与翻页返回过滤后的结果与计数（AC-07-1）；阻断原因与严重度正确（AC-07-2）；正常满足的依赖不出现为 `ERROR`（AC-07-3）；数字类商品配送区域检查为 `NOT_APPLICABLE`（AC-07-4）。
- 变更与兼容：新增查询与类型。每次请求重算，不返回缓存的旧结论（AC-07-6 的服务端侧）。

### I08 · 主体搜索范围与排序边界
- 所属设计单元：BD07
- 提供方：`saleor/product/search.py`、`saleor/order/search.py`、`saleor/giftcard/search.py`、`saleor/account/search.py:128`、`saleor/graphql/page/filters.py:58`；各域 `sorters.py`。
- 调用方：客服、运营支持（Dashboard 各列表）。
- 目标定义：**本轮不新增任何字段与枚举值**。既有排序枚举保持原样：`OrderSortField.RANK`、`ProductOrderField.RANK` 保留；`GiftCardSortField`、`CheckoutSortField`、`PageSortField`、`UserSortField` **保持无 `RANK`**。
- 接口定义片段：

```graphql
query OrderSearch($filter: OrderFilterInput, $sortBy: OrderSortingInput, $first: Int) {
  orders(filter: $filter, sortBy: $sortBy, first: $first) {
    totalCount
    edges { node { id number userEmail } }
  }
}

query UserSearch($filter: StaffUserInput, $first: Int) {
  staffUsers(filter: $filter, first: $first) {
    totalCount
    edges { node { id email } }
  }
}
```

- 字段说明：`OrderFilterInput.search`/`ProductFilterInput.search`/`CheckoutFilterInput.search` 以及根级 `giftCards(search: String)` 参数保留关键词、前缀、组合词、短语与相关度语义；`CustomerFilterInput.search`/`StaffUserInput.search` 按空格组合词匹配 `search_document`；`PageFilterInput.search` 按标题、slug 与内容匹配。
- 权限：客户与员工的隐私、地址与身份信息继续受权限过滤（AC-09-5）。
- 错误：非法或过长输入返回校验错误或错误状态，不阻塞其他列表。
- 完成判定：AC-08-1 至 AC-08-3 逐条成立，且 schema 中不出现 Page/User 的 RANK 排序或被排除的高级搜索字段（AC-32-2）。
- 变更与兼容：**无 schema 变更**。本接口登记的目的是把「不新增」固化为契约，防止实现期借别名或隐藏入口重新暴露被排除能力。

### I09 · 搜索一致性、分页与异常语义
- 所属设计单元：BD07
- 提供方：`saleor/product/tasks.py:301`、`saleor/giftcard/tasks.py:32`（索引更新任务）、各域 filter/sorter；`saleor/graphql/core/connection.py:382`（分页校验）。
- 调用方：客服、运营支持。
- 目标定义：沿用既有 `search_index_dirty` 机制与各域连接的 `pageInfo`/`totalCount`；不新增字段。
- 接口定义片段：

```graphql
query PaginatedSearch($filter: ProductFilterInput, $first: Int, $after: String) {
  products(filter: $filter, first: $first, after: $after) {
    totalCount
    pageInfo { hasNextPage hasPreviousPage startCursor endCursor }
    edges { cursor node { id name } }
  }
}
```

- 字段说明：`totalCount`、`pageInfo` 与 `edges[].cursor` 在相同筛选下稳定；重复关键词、大小写变化与组合词不产生重复项或漏项。
- 权限：可见范围过滤与列表一致。
- 错误：空关键词不触发全量查询（沿既有短路）；越界分页与错误类型在执行前报错（I24）；检索服务异常返回错误状态而不是成功空列表。
- 完成判定：AC-09-1 至 AC-09-4 逐条成立。
- 变更与兼容：无 schema 变更；行为语义固化。

### I10 · 礼品卡支付方式与交易关联
- 所属设计单元：BD08
- 提供方：拟新增 —— `saleor/graphql/checkout/mutations/checkout_gift_card_authorize.py`；`saleor/graphql/payment/types.py`（`GiftCardPaymentMethodDetails`）；`saleor/payment/models.py:31`（`gift_card` 外键）；金额重算复用 `saleor/payment/transaction_item_calculations.py:352`。
- 调用方：Storefront 集成方、支付集成方、客服（Dashboard 订单详情）。
- 目标定义：`Mutation.checkoutGiftCardAuthorize(token: UUID!, giftCardCode: String!, amount: PositiveDecimal, idempotencyKey: String): CheckoutGiftCardAuthorize`；类型 `CheckoutGiftCardAuthorize`、`GiftCardPaymentMethodDetails implements PaymentMethodDetails`；`TransactionItem.giftCard: GiftCard`；`PaymentMethodTypeEnum` 新增 `GIFT_CARD`；`CheckoutErrorCode` 新增 `GIFT_CARD_NOT_ACTIVE`、`GIFT_CARD_EXPIRED`、`GIFT_CARD_CURRENCY_MISMATCH`、`GIFT_CARD_INSUFFICIENT_BALANCE`。
- 接口定义片段：

```graphql
mutation CheckoutGiftCardAuthorize($token: UUID!, $giftCardCode: String!, $amount: PositiveDecimal, $idempotencyKey: String) {
  checkoutGiftCardAuthorize(token: $token, giftCardCode: $giftCardCode, amount: $amount, idempotencyKey: $idempotencyKey) {
    checkout { id token totalBalance }
    giftCard { id code currentBalance }
    transaction { id token chargedAmount authorizedAmount paymentMethodDetails { __typename ... on GiftCardPaymentMethodDetails { name last4CodeChars } } events { id type amount } }
    errors { field message code }
  }
}
```

- 字段说明：`transaction.paymentMethodDetails.__typename` 为 `GiftCardPaymentMethodDetails`；`transaction.giftCard` 指向被使用的礼品卡；`PaymentMethodTypeEnum.GIFT_CARD` 供筛选与展示分类。
- 权限：结账 `token`；权限不足返回顶层权限错误，不静默改用普通支付（AC-10-3）。
- 错误：不存在 → `NOT_FOUND`；未启用 → `GIFT_CARD_NOT_ACTIVE`；已过期 → `GIFT_CARD_EXPIRED`；币种不一致 → `GIFT_CARD_CURRENCY_MISMATCH`；余额不足 → `GIFT_CARD_INSUFFICIENT_BALANCE`；金额超限 → `GIFT_CARD_INSUFFICIENT_BALANCE`（或 `INVALID`）。失败时礼品卡余额与结账支付状态不变（AC-10-2）。
- 完成判定：成功时创建可追踪交易并冻结余额；同一结账 + 同一礼品卡 + 同一幂等键的重复请求只产生一次授权与一次余额变化（AC-10-4）。
- 变更与兼容：新增变更与类型。`PaymentMethodDetails` 接口新增实现者属于向后兼容扩展；`PaymentMethodTypeEnum` 新增值会让既有消费方在未处理时落入默认分支，已在 `frontend-design.md` 的 FD 单元中登记。

### I11 · 礼品卡取消与退款
- 所属设计单元：BD09
- 提供方：拟新增 —— `saleor/graphql/checkout/mutations/checkout_gift_card_cancel.py`、`saleor/graphql/order/mutations/order_gift_card_refund.py`。
- 调用方：客服（Dashboard 结账/订单详情）、Storefront 集成方（取消）。
- 目标定义：`Mutation.checkoutGiftCardCancel(token: UUID!, transactionId: ID!, idempotencyKey: String): CheckoutGiftCardCancel`；`Mutation.orderGiftCardRefund(orderId: ID!, transactionId: ID!, amount: PositiveDecimal, idempotencyKey: String): OrderGiftCardRefund`；类型 `CheckoutGiftCardCancel`、`OrderGiftCardRefund`；`OrderErrorCode` 新增 `AMOUNT_GREATER_THAN_AVAILABLE`。
- 接口定义片段：

```graphql
mutation CheckoutGiftCardCancel($token: UUID!, $transactionId: ID!) {
  checkoutGiftCardCancel(token: $token, transactionId: $transactionId) {
    checkout { id totalBalance }
    giftCard { id currentBalance }
    transaction { id authorizedAmount canceledAmount events { id type amount } }
    errors { field message code }
  }
}

mutation OrderGiftCardRefund($orderId: ID!, $transactionId: ID!, $amount: PositiveDecimal) {
  orderGiftCardRefund(orderId: $orderId, transactionId: $transactionId, amount: $amount) {
    order { id totalGiftCard totalBalance }
    giftCard { id currentBalance }
    transaction { id chargedAmount refundedAmount events { id type amount } }
    errors { field message code }
  }
}
```

- 字段说明：取消只作用于结账阶段未扣款的授权，释放冻结；退款只作用于订单上已扣款的礼品卡交易，金额不得超过该交易可退余额。
- 权限：取消需要结账 `token` 或结账管理权限；退款需要 `MANAGE_ORDERS`；无权限返回权限错误且响应不含受限金额。
- 错误：交易不存在 → `NOT_FOUND`；退款超可退余额 → `AMOUNT_GREATER_THAN_AVAILABLE`；状态不允许 → `TRANSACTION_ERROR`；按 ID 传入结账 token 或反之 → 类型错误（I24）。
- 完成判定：交易事件、礼品卡余额与结账/订单支付及退款状态反映同一结果（AC-11-3）；无事件时 `events` 为空数组且请求整体成功（AC-11-5）。
- 变更与兼容：新增变更与类型；`OrderErrorCode` 新增值属于兼容扩展。

### I12 · 订单金额摘要字段与去重口径
- 所属设计单元：BD10
- 提供方：`saleor/graphql/order/types.py`（`Order` 金额字段解析）；`saleor/order/utils.py`（`_update_order_total_charged`、`_update_order_total_authorized`）。
- 调用方：资金运营、商户运营（Dashboard 订单金额分解）、客服。
- 目标定义：`Order` 既有字段 `subtotal: TaxedMoney!`、`discounts: [OrderDiscount!]!`、`shippingPrice: TaxedMoney!`、`totalAuthorized: Money!`、`totalCharged: Money!`、`totalCanceled: Money!`、`totalRefunded: Money!`、`totalBalance: Money!`、`total: TaxedMoney!` 保持；新增 `Order.totalGiftCard: Money!`。
- 接口定义片段：

```graphql
query OrderAmountBreakdown($id: ID!) {
  order(id: $id) {
    id
    subtotal { gross { amount currency } }
    discounts { id amount { amount currency } }
    shippingPrice { gross { amount currency } }
    total { gross { amount currency } tax { amount currency } }
    totalGiftCard { amount currency }
    totalAuthorized { amount currency }
    totalCharged { amount currency }
    totalCanceled { amount currency }
    totalRefunded { amount currency }
    totalBalance { amount currency }
    giftCards { id code currentBalance }
    transactions { id chargedAmount refundedAmount paymentMethodDetails { __typename } }
  }
}
```

- 字段说明：**口径** —— 礼品卡交易**不**计入 `totalAuthorized`、`totalCharged`、`totalCanceled`、`totalRefunded`；`totalGiftCard = Σ(礼品卡交易 chargedAmount) − Σ(礼品卡交易 refundedAmount)`；`totalBalance = total − (totalCharged − totalRefunded) − totalGiftCard`。税费与商品金额来自 `total`/`subtotal`（基线 `Order` 无独立 `totalTax` 字段，税费通过 `total.tax` 读取）。多交易汇总额度不重复计入同一事件。
- 权限：金额字段沿用订单权限；无权限不返回受限金额。
- 错误：只读，无业务错误路径。
- 完成判定：含折扣、税费、配送、礼品卡与多笔支付的订单中，各项之和与 `total` 一致（AC-12-1、AC-12-4）；旧 `Payment` 与新 `TransactionItem` 并存时不重复计入（AC-12-2）；多交易不重复占用额度（AC-12-3）。
- 变更与兼容：`Order.totalGiftCard` 为新增字段。既有字段语义收紧为「仅普通交易」，对既有数据无影响（基线不含礼品卡交易记录）。

### I13 · 人工资金动作的边界与幂等
- 所属设计单元：BD11
- 提供方：`saleor/graphql/order/mutations/order_mark_as_paid.py`、`order_capture.py`、`order_refund.py`；动作计算 `saleor/graphql/order/types.py:2167 resolve_actions`、`saleor/graphql/payment/types.py:224 resolve_actions`。
- 调用方：资金运营、客服（Dashboard 订单详情）。
- 目标定义：`Mutation.orderMarkAsPaid(id: ID!, transactionReference: String)`、`orderCapture(amount: PositiveDecimal!, id: ID!)`、`orderRefund(amount: PositiveDecimal!, id: ID!)`、`orderVoid(id: ID!)`（签名不变）；`Order.actions: [OrderAction!]!`；`OrderErrorCode` 新增 `AMOUNT_GREATER_THAN_AVAILABLE`、`PAYMENT_ALREADY_EXISTS`。
- 接口定义片段：

```graphql
query OrderAvailableActions($id: ID!) {
  order(id: $id) {
    id
    actions
    totalAuthorized { amount }
    totalCharged { amount }
    totalRefunded { amount }
    totalBalance { amount }
  }
}

mutation OrderCapture($id: ID!, $amount: PositiveDecimal!) {
  orderCapture(id: $id, amount: $amount) {
    order { id totalCharged { amount } totalBalance { amount } transactions { id events { id type } } }
    errors { field message code }
  }
}
```

- 字段说明：`Order.actions` 只包含当前支付方式与状态允许的动作；`orderMarkAsPaid` 仅在订单无支付/交易记录且满足条件时可用；`orderCapture` 上限为当前可捕获授权；`orderRefund` 上限为可退余额，多笔交易共享额度。
- 权限：`MANAGE_ORDERS`；无权限返回顶层权限错误，且响应不含受限金额（AC-13-7）。
- 错误：负数金额在执行前报错（`PositiveDecimal` + I24）；捕获超授权 → `AMOUNT_GREATER_THAN_AVAILABLE`；已有支付记录仍标记已支付 → `PAYMENT_ALREADY_EXISTS`；无授权可捕获 → `CAPTURE_INACTIVE_PAYMENT`；无可退余额 → `CANNOT_REFUND`。失败不改状态、不写事件。
- 完成判定：等于合法边界成功、超过被拒（AC-13-3）；重复点击或失败重试不重复扣款/退款、不写冲突事件（AC-13-5）；成功后读取到刷新后的金额、事件与余额（AC-13-6）。
- 变更与兼容：签名不变；`OrderErrorCode` 新增两个值属于兼容扩展；`Order.actions` 的取值集合按状态收紧属于行为修正。

### I14 · 根级交易查询
- 所属设计单元：BD12
- 提供方：拟新增 —— `saleor/graphql/payment/schema.py`（注册 `Query.transactions`）、`saleor/graphql/payment/resolvers.py`、`saleor/graphql/payment/filters.py`。
- 调用方：客服、支付集成方。
- 目标定义：`Query.transactions(filter: TransactionFilterInput, before/after/first/last): TransactionCountableConnection!`；类型 `TransactionCountableConnection`、`TransactionCountableEdge`；`TransactionFilterInput` 扩展 `ids`、`tokens`、`orderIds`、`checkoutIds`、`pspReferences`、`appIds`、`appIdentifiers`（保留既有 `paymentMethodDetails`、`metadata`）；`TransactionItem` 新增 `giftCard`、`app`、`appIdentifier`。
- 接口定义片段：

```graphql
query Transactions($filter: TransactionFilterInput, $first: Int, $after: String) {
  transactions(filter: $filter, first: $first, after: $after) {
    totalCount
    pageInfo { hasNextPage endCursor }
    edges {
      node {
        id
        token
        pspReference
        name
        app { id name }
        appIdentifier
        giftCard { id code }
        order { id number total { gross { amount } } }
        checkout { id token }
        actions
        paymentMethodDetails { __typename name }
        chargedAmount { amount currency }
        authorizedAmount { amount currency }
        refundedAmount { amount currency }
        canceledAmount { amount currency }
        events { id type amount createdAt }
      }
    }
  }
}
```

- 字段说明：`ids`/`tokens` 精确定位；`orderIds`/`checkoutIds` 按关联主体筛选；`pspReferences` 按服务商参考号；`appIds`/`appIdentifiers` 按 App 标识。默认排序固定为 `-createdAt, -id`，**不提供 `sortBy`**。
- 权限：`HANDLE_PAYMENTS`；叠加对象范围——客户只见自己订单/结账的交易，App 只见自己创建或有权访问的交易，员工按渠道/仓库可见性（AC-14-4）。
- 错误：`first`/`last` 超过 100 或为空 → 执行前报错；越界游标 → 稳定错误；错误过滤类型 → 执行前报错；无权限 → 顶层权限错误。均不使用成功空结果掩盖（AC-14-6）。
- 完成判定：AC-14-1 至 AC-14-3 可定位且字段齐备；AC-14-5 成立（不出现日期/事件筛选与专用排序）。
- 变更与兼容：新增查询与连接类型；`TransactionFilterInput` 为兼容扩展（新增可选字段）；`TransactionItem` 新增三个可空字段。

### I15 · 密码登录模式
- 所属设计单元：BD13
- 提供方：`saleor/graphql/shop/mutations/shop_settings_update.py`、`saleor/graphql/shop/types.py`（`Shop.passwordLoginMode`）；生效点 `saleor/graphql/account/mutations/authentication/create_token.py`、`request_password_reset.py`、`set_password.py`、`password_change.py` 及旧 token 路径。
- 调用方：商店管理（Dashboard 设置页）、Dashboard 登录页；Storefront 登录入口。
- 目标定义：`Shop.passwordLoginMode: PasswordLoginModeEnum!`、`ShopSettingsInput.passwordLoginMode: PasswordLoginModeEnum`、`enum PasswordLoginModeEnum { ENABLED CUSTOMERS_ONLY DISABLED }`；`AccountErrorCode` 新增 `PASSWORD_LOGIN_DISABLED`、`PASSWORD_LOGIN_CUSTOMERS_ONLY`。
- 接口定义片段：

```graphql
query ShopPasswordLoginMode {
  shop { passwordLoginMode }
}

mutation ShopSettingsUpdate($input: ShopSettingsInput!) {
  shopSettingsUpdate(input: $input) { shop { passwordLoginMode } errors { field message code } }
}

mutation TokenCreate($email: String!, $password: String!) {
  tokenCreate(email: $email, password: $password) { token errors { field message code } }
}
```

- 字段说明：`ENABLED` 全部受支持用户可用密码；`CUSTOMERS_ONLY` 仅客户身份；`DISABLED` 关闭密码登录、重置、设置与修改密码，以及旧 token 路径。
- 权限：修改需要商店设置权限，无权限返回 `OUT_OF_SCOPE_PERMISSION`/顶层权限错误；读取 `Shop.passwordLoginMode` 为公开字段（配置页与登录页都需读取同一生效值）。
- 错误：`PASSWORD_LOGIN_DISABLED`、`PASSWORD_LOGIN_CUSTOMERS_ONLY`；保存失败保留上次生效值（AC-17-6）。
- 完成判定：AC-17-1 至 AC-17-5 逐条成立；保存后立即发起认证读到新值（AC-17-4）。
- 变更与兼容：新增字段与两个错误码值。`Shop.passwordLoginMode` 为必填非空字段，默认 `ENABLED` 以保持既有行为。

### I16 · Google OIDC 离线授权与身份关联（非 GraphQL）
- 所属设计单元：BD14
- 提供方：`saleor/plugins/openid_connect/plugin.py:222-229`（授权参数）、`saleor/plugins/openid_connect/utils.py:391 get_or_create_user_from_payload`。
- 调用方：Storefront、Dashboard 登录（外部认证入口）。
- 目标定义：非 GraphQL。完整协议见 `interfaces/oidc-offline-access.md`。
- 接口定义片段：见 `interfaces/oidc-offline-access.md` 的授权请求与回调约定。
- 字段说明：Google provider 需要 refresh token 时使用 `access_type=offline` 参数，不使用 `offline_access` scope；其他 provider 按各自合同。
- 权限：沿用 OIDC 插件配置。
- 错误：授权失败返回可识别错误码；错误响应与前端存储不含 token 或敏感身份信息（AC-18-2）。
- 完成判定：AC-18-1、AC-18-3、AC-18-4 逐条成立。
- 变更与兼容：改变 Google provider 的授权参数拼装；不改变 `Plugin` 的 GraphQL 字段签名。

### I17 · 富文本校验错误码
- 所属设计单元：BD15
- 提供方：`saleor/core/utils/editorjs.py:32 clean_editor_js`、`saleor/core/db/fields.py:12 SanitizedJSONField`、`saleor/graphql/attribute/utils/type_handlers.py:569 RichTextAttributeHandler`。
- 调用方：内容运营、商品运营、翻译运营（Dashboard 商品描述、页面内容、富文本属性）。
- 目标定义：`AttributeErrorCode`、`PageErrorCode`、`ProductErrorCode` 各新增 `RICH_TEXT_INVALID`、`RICH_TEXT_TOO_DEEP`、`RICH_TEXT_UNSAFE_LINK`。**不新增字段与类型**。
- 接口定义片段：

```graphql
mutation ProductUpdate($id: ID!, $input: ProductInput!) {
  productUpdate(id: $id, input: $input) {
    product { id }
    errors { field message code }
  }
}
```

- 字段说明：`RICH_TEXT_INVALID` —— 未知或多余字段、结构不合法；`RICH_TEXT_UNSAFE_LINK` —— 非法 scheme；`RICH_TEXT_TOO_DEEP` —— 嵌套深度超限。`field` 指向具体属性或字段，`message` 指向具体链接或深度问题。
- 权限：沿用各自变更的权限。
- 错误：拒绝时返回上述错误码之一，且在写库前抛出，不产生部分危险内容（AC-19-2）；合法内容正常保存（AC-19-1、AC-19-3）；不可通过配置扩展协议白名单（AC-19-4、AC-19-5）。
- 完成判定：AC-19-1 至 AC-19-5 逐条成立。
- 变更与兼容：只新增枚举值，签名不变。历史数据不受影响（校验只在写入路径生效）。

### I18 · 扩展 mountName/targetName/settings 与旧字段弃用
- 所属设计单元：BD16
- 提供方：`saleor/graphql/app/types.py`、`saleor/graphql/app/resolvers.py:72 resolve_app_extensions`、`saleor/app/models.py:156`（新增字段）。
- 调用方：App 集成方、商店管理（Dashboard 已安装扩展与目录）。
- 目标定义：`AppExtension` 与 `AppManifestExtension` 新增 `mountName: String`、`targetName: String`、`settings: JSON`；`mount`、`target` 加 `@deprecated`；`AppExtensionFilterInput` 新增 `mountName: [String!]`、`targetName: [String!]`，既有 `mount`、`target` 加 `@deprecated`。
- 接口定义片段：

```graphql
query AppExtensions($filter: AppExtensionFilterInput, $appId: ID) {
  appExtensions(filter: $filter, appId: $appId, first: 20) {
    totalCount
    edges {
      node {
        id
        label
        url
        mountName
        targetName
        settings
        mount
        target
        app { id name }
      }
    }
  }
}
```

- 字段说明：`mountName`/`targetName` 是当前约定的字符串标识；对未迁移到已知名称的历史数据返回 `null`；`settings` 保留 manifest 中声明的设置内容；`mount`/`target` 继续返回既有枚举映射，供旧客户端读取。
- 权限：读取按调用方可见范围过滤（App 只能看到自己的扩展，员工按 App 管理权限）；无权限返回权限错误（AC-20-5）。
- 错误：无。
- 完成判定：AC-20-1、AC-20-2 成立（历史扩展无需重装即可查询、编辑与渲染，`settings` 保留）。
- 变更与兼容：新增可空字段 + 旧字段弃用。`settings` 类型为 `JSON`（基线已存在 `JSON` 标量），避免为扩展设置新增专用类型。

### I19 · App 安装必填校验与可选安装信息
- 所属设计单元：BD16
- 提供方：`saleor/graphql/app/mutations/`（`appInstall`、`appFetchManifest`）、`saleor/app/manifest_validations.py:143 clean_manifest_data`。
- 调用方：商店管理、App 集成方。
- 目标定义：`AppInstallInput.appName: String!`、`AppInstallInput.manifestUrl: String!`（由可空改为必填）；`Manifest.tokenTargetUrl: String` 保持可空；`AppErrorCode` 新增 `INVALID_MOUNT_NAME`、`INVALID_TARGET_NAME`、`INVALID_SETTINGS`。
- 接口定义片段：

```graphql
mutation AppInstall($input: AppInstallInput!) {
  appInstall(input: $input) {
    appInstallation { id name }
    errors { field message code }
  }
}
```

- 字段说明：缺 `appName` 或 `manifestUrl` 在执行前报错（AC-28-5）；`tokenTargetUrl` 缺省不影响合法安装，不需要时不返回新建或安装 token（AC-20-4）。
- 权限：安装与更新需要 App 管理权限；无权限返回 `AppErrorCode.FORBIDDEN` 或顶层权限错误（AC-20-5）。
- 错误：重复 identifier → `UNIQUE`；无效权限 → `INVALID_PERMISSION`；非法 target → `INVALID_TARGET_NAME`；非法 mount → `INVALID_MOUNT_NAME`；无法解析的 settings → `INVALID_SETTINGS`；所有失败路径不破坏已有有效数据（AC-20-3）。
- 完成判定：AC-20-3、AC-20-4 成立。
- 变更与兼容：`AppInstallInput` 两个字段由可空改为非空是**破坏性变更**，仅影响缺少必填项的调用；按 R28 的弃用/迁移边界处理，见 I25。

### I20 · Webhook 载荷构建边界与投递状态
- 所属设计单元：BD17
- 提供方：`saleor/graphql/webhook/subscription_payload.py`、`saleor/webhook/transport/utils.py:94`、`saleor/webhook/transport/asynchronous/transport.py:500/603/678`；`saleor/core/models.py:206`。
- 调用方：App 与 Webhook 集成方、商户支持（Dashboard 投递列表）。
- 目标定义：`EventDelivery.status: EventDeliveryStatusEnum!` 的取值集合扩展为 `{ PENDING RETRYING SUCCESS FAILED }`（新增 `RETRYING`）；`EventDeliveryAttempt` 字段不变。
- 接口定义片段：

```graphql
query EventDeliveries($appId: ID, $first: Int) {
  app(id: $appId) {
    webhooks {
      eventDeliveries(first: $first) {
        edges {
          node {
            id
            status
            eventType
            createdAt
            attempts { id status responseStatusCode duration createdAt }
          }
        }
      }
    }
  }
}
```

- 字段说明：`PENDING` —— 内容尚未生成或尚未投递；`RETRYING` —— 已失败且处于重试策略中；`SUCCESS` / `FAILED` —— 终态。异步内容未生成不显示为成功（AC-24-4）。
- 权限：需要相关 App 或业务域权限；内容遵守 App 可见字段边界（AC-24-5）。
- 错误：无。
- 完成判定：一个接收方失败不影响其他接收方（AC-24-1）；重试只作用于该 delivery（AC-24-2）；变体折扣价实质变化只产生一次通知（AC-24-3）；既有失败告警保留且不呈现为 App Problems（AC-24-6）。
- 变更与兼容：`EventDeliveryStatusEnum` 新增值属于兼容扩展；消费方需把未知值作为非终态处理，已在 `frontend-design.md` 登记。

### I21 · 单条投递重试
- 所属设计单元：BD17
- 提供方：`saleor/graphql/webhook/mutations/event_delivery_retry.py:16 EventDeliveryRetry`（基线已存在，权限 `MANAGE_APPS`）。
- 调用方：商户支持（Dashboard 投递详情）。
- 目标定义：`Mutation.eventDeliveryRetry(id: ID!): EventDeliveryRetry`（签名不变）。
- 接口定义片段：

```graphql
mutation EventDeliveryRetry($id: ID!) {
  eventDeliveryRetry(id: $id) {
    delivery { id status attempts { id status } }
    errors { field message code }
  }
}
```

- 字段说明：重试只作用于指定 delivery；重试次数仍遵守 `MAX_WEBHOOK_RETRIES = 5`。
- 权限：`MANAGE_APPS` 或相关业务域权限；无权限返回权限错误。
- 错误：delivery 不存在 → `NOT_FOUND`；已达重试上限 → `INVALID`。
- 完成判定：AC-24-2、AC-24-5 成立。
- 变更与兼容：**无签名变更**；行为受 I20 的状态语义影响（重试期间状态为 `RETRYING`）。

### I22 · 订单与履约的配送元数据快照
- 所属设计单元：BD18
- 提供方：`saleor/graphql/order/types.py`（`Order.deliveryMethodSnapshot`、`Fulfillment.deliveryMethodSnapshot`）；写入在 `saleor/checkout/complete_checkout.py` 与 `saleor/graphql/order/mutations/draft_order_complete.py`。
- 调用方：履约运营、订单运营、客服（Dashboard 订单与履约详情）。
- 目标定义：`Order.deliveryMethodSnapshot: DeliveryMethodSnapshot`、`Fulfillment.deliveryMethodSnapshot: DeliveryMethodSnapshot`；类型 `DeliveryMethodSnapshot`。
- 接口定义片段：

```graphql
query OrderDeliverySnapshot($id: ID!) {
  order(id: $id) {
    id
    shippingMethodName
    deliveryMethodSnapshot {
      deliveryMethodId
      name
      metadata { key value }
      privateMetadata { key value }
    }
    fulfillments {
      id
      deliveryMethodSnapshot { deliveryMethodId name metadata { key value } }
    }
  }
}
```

- 字段说明：`deliveryMethodId` 为创建时的配送方式 ID，源对象删除后为 `null`；`name` 为创建时名称；`metadata`/`privateMetadata` 为创建时的元数据快照，私有部分仍按权限可见。历史订单无快照时字段为 `null`（`Order`）或快照内各项为空（AC-25-5 的稳定空值）。
- 权限：private 元数据需要员工权限；无权限不返回私有部分（AC-25-4）。
- 错误：无。
- 完成判定：AC-25-1 至 AC-25-5 逐条成立。
- 变更与兼容：新增可空字段与类型；不改变既有 `shippingMethodName`、`shippingMethods` 字段。

### I23 · 基础元数据读写语义
- 所属设计单元：BD19
- 提供方：既有 `updateMetadata`/`deleteMetadata`/`updatePrivateMetadata`/`deletePrivateMetadata` 变更与各对象的 `metadata`/`privateMetadata`/`metafield(s)` 字段。
- 调用方：客服（Dashboard 结账、草稿订单、订单、履约详情的基础元数据编辑与订单行元数据）。
- 目标定义：**无对外接口变更**。`target-schema.graphql` 中元数据相关定义与基线逐字一致。
- 接口定义片段：

```graphql
mutation UpdateMetadata($id: ID!, $input: [MetadataInput!]!) {
  updateMetadata(id: $id, input: $input) { item { __typename } errors { field message code } }
}
```

- 字段说明：合法键值按权限保存与读取；非法值、权限不足或保存失败不改变原值，不出现部分写入。
- 权限：public 元数据按对象权限；private 元数据需要员工权限。
- 错误：沿用既有 `MetadataErrorCode`。
- 完成判定：AC-26-1 至 AC-26-3 成立；AC-26-4 的「不出现独立入口」由 I23 的无新增项 + `frontend-design.md` 的前端约束共同保证。
- 变更与兼容：明确**不新增**订单、履约与仓库的独立元数据弹窗、专用路由或独立入口所对应的后端类型与变更。

### I24 · 输入校验与可分支失败语义
- 所属设计单元：BD20
- 提供方：`saleor/graphql/core/validators/__init__.py`、`saleor/graphql/core/connection.py:382`、`saleor/graphql/core/scalars.py:202/206/210`（`Minute`/`Hour`/`Day`）。
- 调用方：所有集成方。
- 目标定义：**现有字段类型不变**。行为变更：`Minute`、`Hour`、`Day` 三个标量拒绝负值；分页、枚举、必填与组合关系在执行前校验；Federation representations 为 null 或含 null 项报错。
- 接口定义片段：

```graphql
query ValidationSurface($first: Int, $filter: OrderFilterInput) {
  orders(first: $first, filter: $filter) { totalCount pageInfo { hasNextPage } }
}
```

- 字段说明：合法单值、数组与组合查询继续可用；对象 ID、结账 token、UUID、渠道 slug 各按自身类型解析，类型不匹配在执行前报错（AC-27-7）；`first`/`last` 上限为 100（`GRAPHQL_PAGINATION_LIMIT`）。
- 权限：校验先于权限判定执行；两者都失败时返回权限错误以外的校验错误只在无权限不成立时出现，不泄露对象是否存在。
- 错误：`GRAPHQL_ERROR` / `INVALID` / `REQUIRED` / 越界分页错误；返回可按 `field`、`code`、`message` 分支处理；失败不产生部分写入；未知底层错误不转成成功空列表（AC-27-5）。
- 完成判定：AC-27-1 至 AC-27-7 逐条成立。
- 变更与兼容：标量拒绝负值是**行为加严**，只影响传入非法负值的请求（原本会被当作合法整数接受）；按 R27 属于明确输入校验要求。

### I25 · 弃用读取与迁移边界
- 所属设计单元：BD21
- 提供方：schema 中的 `@deprecated` 标记与弃用变更实现；`saleor/graphql/order/mutations/draft_order_create.py`/`draft_order_update.py`（`voucherCode`）。
- 调用方：所有集成方；Dashboard 生成客户端。
- 目标定义：新增弃用标记 —— `Payment.partial`、`ProductVariant.digitalContent`、`Query.digitalContent`、`Query.digitalContents`、`Mutation.digitalContentCreate`、`digitalContentDelete`、`digitalContentUpdate`、`digitalContentUrlCreate`、`DraftOrderInput.voucher`、`DraftOrderCreateInput.voucher`、`AppExtension.mount`、`AppExtension.target`、`AppManifestExtension.mount`、`AppManifestExtension.target`、`AppExtensionFilterInput.mount`、`AppExtensionFilterInput.target`；`AttributeCreateInput.name/slug/type` 与 `AppInstallInput.appName/manifestUrl` 的必填性由 I19 与既有定义约束。
- 接口定义片段：

```graphql
mutation DraftOrderCreate($input: DraftOrderInput!) {
  draftOrderCreate(input: $input) {
    order { id voucherCode }
    errors { field message code }
  }
}
```

- 字段说明：仍支持的旧用法给出弃用读取与替代路径；已不支持的能力返回不存在或迁移错误，不返回无解释的成功空响应（AC-28-1、AC-28-2）。导出使用既有 `exportProducts`/`exportGiftCards`/`exportVoucherCodes` + `exportFile`/`exportFiles`，为当前唯一方式（AC-28-3）。
- 权限：弃用入口不绕过权限。
- 错误：已移除能力返回 `NOT_FOUND` 或迁移类错误。
- 完成判定：AC-28-1、AC-28-2、AC-28-4、AC-28-5、AC-28-7 成立；AC-28-6 由本文件与 `target-schema.graphql` 的逐条对应保证。
- 变更与兼容：新增 `@deprecated` 标记属于兼容变更；`AppInstallInput` 必填化见 I19 的兼容说明。

### I26 · 权限与可见范围一致性
- 所属设计单元：BD22
- 提供方：`saleor/graphql/core/permissions.py` 与各域 resolver 的权限装饰。
- 调用方：所有集成方。
- 目标定义：**无对外接口变更**。行为语义固化：员工删除、属性更新、App 安装、导出与敏感税务字段读取在所有入口使用同一权限判定；客户/员工/App 的对象范围、渠道与仓库可见性在列表、导出、批量操作与错误信息中一致。
- 接口定义片段：

```graphql
mutation StaffDelete($id: ID!) {
  staffDelete(id: $id) { errors { field message code } }
}
```

- 字段说明：有权限时合法员工被真正删除（含目标员工有历史订单），自删或无权限删除被拒。
- 权限：`MANAGE_STAFF`；导出按 `MANAGE_PRODUCTS`/`MANAGE_GIFT_CARD`/`MANAGE_DISCOUNTS`；敏感税务字段按 `HANDLE_TAXES` 等。
- 错误：权限错误而不是空结果；失败不表现为成功。
- 完成判定：AC-29-1 至 AC-29-5 逐条成立。
- 变更与兼容：无 schema 变更；语义固化。

## 3. 其他

### 与基线 schema 的对应关系

`target-schema.graphql` 由基线 `saleor/graphql/schema.graphql` 逐处锚定修改生成，基线定义逐字保留。本文件中的每个 I 编号都能在 SDL 中找到对应的操作、类型或字段；I08、I09、I23、I26 登记的「无对外接口变更」在 SDL 中体现为对应定义与基线逐字一致。

### 已执行的检查

- 用 python `graphql-core` 3.3.0 对 `target-schema.graphql` 执行 `build_schema` 与 `validate_schema`：构建成功，类型数 1440（基线 1418），校验错误 0。
- 用 node `graphql` 16.11.0（`/workspace/repos/saleor-dashboard/node_modules/graphql`）对同一文件执行 `buildSchema` 与 `validateSchema`：构建成功，类型数 1440，校验错误 0。
- 逐项断言关键新增面：`Query.checkoutDeliveryOptions` / `Query.productChannelDiagnostics` / `Query.transactions` 存在；`Mutation.checkoutGiftCardAuthorize` / `checkoutGiftCardCancel` / `orderGiftCardRefund` 存在；`Order.totalGiftCard` 存在；`GiftCardPaymentMethodDetails implements PaymentMethodDetails`；`PaymentMethodTypeEnum` 含 `GIFT_CARD`；`EventDeliveryStatusEnum` 含 `RETRYING`；`AppInstallInput.appName`/`manifestUrl` 为 `String!`；`AppExtension.mount`/`target` 带弃用原因；`Shop.passwordLoginMode: PasswordLoginModeEnum!`；`StockSettings` 含 `stockAvailabilityMode`；`CheckoutSettings` 含 `automaticCompletionDelay`/`automaticCompletionCutoff`；`TransactionFilterInput` 含 7 个新增筛选字段；`TransactionItem` 含 `giftCard`/`app`/`appIdentifier`；`Payment.partial`、`DraftOrderInput.voucher`、`ProductVariant.digitalContent` 带弃用原因；`AttributeErrorCode`/`PageErrorCode`/`ProductErrorCode` 含三个富文本错误码。
- 人工核对编号连续性：I01–I26 无重排、无复用；BD01–BD23 与 `backend-design.md` 一致；FD 编号与 `frontend-design.md` 一致。
- 用脚本逐条比对三份 Markdown 中反引号书写的 `类型.成员` 引用与构建后的 `target-schema.graphql`：共 102 条引用全部命中，无缺类型、无缺字段（脚本见 `/workspace/scratch/crosscheck_docs.py`）；同时对非 SDL 的 CamelCase 符号逐个回查仓库源码确认存在（Django 模型、字段、Dashboard 组件与 hook 等）。

### 未执行的检查

- **未运行 Core 的后端测试套件**（`pytest`）：本轮交付为设计文档，不开发代码，且仓库中对应的新实现尚不存在。
- **未运行代码生成器**（Dashboard 的 `graphql-codegen`）：生成结果会在实现阶段产生，本轮只保证 SDL 可被同一版本的 graphql 解析器构建，因此生成客户端不会因 schema 语法失败。
- **未运行数据库迁移**：迁移在实现阶段编写；本轮只描述迁移的形态与幂等要求。
- **未回读上游/升级后版本的 schema**：`target-schema.graphql` 由基线 schema 加本设计推导得出，未检索任何升级后版本的 schema 内容。
- **未验证真实 Webhook、支付网关与 OIDC provider 的连通性**：涉及外部服务，本轮只固定契约。
