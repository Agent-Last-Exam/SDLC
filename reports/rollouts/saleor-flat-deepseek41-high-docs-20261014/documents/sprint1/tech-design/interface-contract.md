# 接口对齐文档：Saleor 3.23 结账、收款与商户运营一致性交付

版本：v1
责任：后端技术设计
依据：后端技术设计 v1，backend-design.md
修订：首次交付（sprint1/tech-design 第 1 轮）。后续修复轮次只更新受影响条目，I 编号不重排、不复用。

目标接口描述：`target-schema.graphql`（本目录），由 `/workspace/repos/saleor/saleor/graphql/schema.graphql`（Base，Saleor Core 3.22.0，35185 行）按本设计完整推导生成；未变更的 Base 定义全部原样保留。补充协议描述见 `interfaces/`（§3.3）。

## 1. 通用约定

**入口与协议。** 全部对外边界为 GraphQL。单一入口 `POST /graphql/`（Core），Dashboard 通过生成的 Apollo 客户端消费。操作分为三类：根级 `Query` 字段、根级 `Mutation` 字段，以及既有操作的语义收敛（不改变签名）。

**标识规则。**

- 对象 ID 一律为全局 base64 ID（`Node`），经 `graphql_relay.from_global_id` 解析。
- 结账对外使用 `id`（全局 ID）或 `token`（UUID）；`token` 在既有操作中保留并弃用（reason 指向 `id`），新操作 `checkoutDeliveryOptionsRecalculate` 同时接受二者，语义等价。
- 配送标识沿用既有三态（详见 I01/I02 与 `interfaces/delivery-option-id.md`）：内置 `ShippingMethod:<pk>`、外部 base64 `app:<identifier>:<method>`、自提点 `Warehouse:<uuid>`。
- 金额统一 `Money`（含 `amount` 与 `currency`），入参金额统一 `PositiveDecimal`（负值在执行前被标量校验拒绝）。

**认证与权限分层。**

| 层 | 表现 |
| --- | --- |
| 未认证 | `PermissionDenied`，`extensions.exception.code = "PermissionDenied"`，HTTP 200 |
| 已认证但缺权限 | 同上，错误信息不含受限数据 |
| 对象越界（不属于调用方可见范围） | `NOT_FOUND`，不区分「不存在」与「不可见」，不泄露其他对象信息 |
| 参数/业务条件不满足 | mutation 返回 payload 的 `errors: [XxxError!]!`，每项含 `field`、`code`、`message` |

**成功判定。** HTTP 200 与 `data` 非空都不足以判定成功。调用方必须同时检查：GraphQL `errors` 为空；mutation payload 的 `errors` 为空；且 payload 内的目标对象字段非 `null`。查询类操作以 `data` 字段非 `null` 判定；列表类以连接对象存在（`edges` 可为空数组）判定，**不以空结果代替错误**。

**错误分层。** 传输层（HTTP/JSON 解析）、GraphQL 校验层（未知字段、错误类型、必填缺失）、业务层（payload `errors`）三层分离。非法输入（错误类型、越界分页、必填缺失、枚举非法、负值）在执行前由 GraphQL 校验层或标量拒绝，不产生部分写入，不转为成功空结果。

**幂等与并发。** 资金与库存动作依据最新对象状态做幂等检查；失败不产生部分写入。带 `idempotencyKey` 的操作按该键去重；设置类操作按 `expectedUpdatedAt` 做乐观并发控制。

**版本标注。** 所有新增 schema 元素在描述中标注 `Added in Saleor 3.23.`；弃用一律 `@deprecated(reason: "...")`，reason 必须给出替代路径。

**未配置/未切换即沿用既有行为。** `StockSettings.useChannelWarehousesForStock = false`、未配置自动完成的渠道、历史订单的配送元数据、`AppExtension` 旧字段读取，均保持升级前语义。

## 2. 接口契约

### I01 · 结账配送选项重算
- 所属设计单元：BD01
- 提供方：Core，拟新增 `saleor/graphql/checkout/mutations/checkout_delivery_options_recalculate.py`（resolver 复用 `saleor/checkout/fetch.py` 的 `CheckoutInfo.get_all_shipping_methods()` / `valid_delivery_methods` / `get_delivery_method_info()`）；类型定义在 `saleor/graphql/checkout/types.py`
- 调用方：本次新增，由 Storefront / 外部集成方调用；Dashboard 本轮不新增调用点（仅重新 codegen 保证生成客户端可编译）
- 目标定义：`target-schema.graphql` 中的 `Mutation.checkoutDeliveryOptionsRecalculate`、`CheckoutDeliveryOptionsRecalculate`、`CheckoutDeliveryOptions`、`DeliveryOption`

```graphql
"""
Recalculates delivery options for a checkout using the current checkout facts
(address, lines, channel and the results of the synchronous shipping webhooks).
Returns the available options, the currently selected option and whether that
selection is still applicable.

This operation does not change the checkout. When the recalculation fails the
previously selected delivery option is preserved and no partial selection is
written.

Requires one of the following permissions: AUTHENTICATED_APP, AUTHENTICATED_STAFF_USER.

Added in Saleor 3.23.
"""
checkoutDeliveryOptionsRecalculate(
  """The ID of the checkout."""
  id: ID

  """Checkout token."""
  token: UUID @deprecated(reason: "Use `id` instead.")
): CheckoutDeliveryOptionsRecalculate @doc(category: "Checkout") @webhookEventsInfo(asyncEvents: [], syncEvents: [SHIPPING_LIST_METHODS_FOR_CHECKOUT, CHECKOUT_FILTER_SHIPPING_METHODS])

type CheckoutDeliveryOptionsRecalculate {
  checkout: Checkout
  deliveryOptions: CheckoutDeliveryOptions
  errors: [CheckoutError!]!
}

type CheckoutDeliveryOptions {
  availableDeliveryOptions: [DeliveryOption!]!
  selectedDeliveryOptionId: ID
  isSelectedDeliveryOptionAvailable: Boolean
}

type DeliveryOption {
  id: ID!
  deliveryMethod: DeliveryMethod
  name: String!
  price: Money
  message: String
}
```

- 字段说明：
  - `id: ID` 与 `token: UUID` 二选一；均未提供时返回 `CheckoutError`（`field: "id"`）。`token` 已弃用但继续可用。
  - `checkout: Checkout` 可空：仅在成功解析结账时返回。
  - `deliveryOptions: CheckoutDeliveryOptions` 可空：计算失败时为 `null`，此时 `errors` 非空。
  - `availableDeliveryOptions: [DeliveryOption!]!` —— 列表本身非空（可为空数组），列表项非空。仅包含**当前结账下有效**的选项；已失效的旧选项不出现。
  - `selectedDeliveryOptionId: ID` 可空：`null` 表示结账当前没有有效选择。
  - `isSelectedDeliveryOptionAvailable: Boolean` 可空：三态语义 —— `null` 无选择、`true` 选择仍有效、`false` 选择已失效（此时该 ID 不出现在 `availableDeliveryOptions` 中）。
  - `DeliveryOption.id: ID!` —— 可直接传给 `checkoutDeliveryMethodUpdate(deliveryMethodId:)` 的三态标识之一。
  - `DeliveryOption.deliveryMethod: DeliveryMethod` 可空：底层方法无法映射到 `DeliveryMethod` union 成员时为 `null`。
  - `DeliveryOption.name: String!` 非空；`price: Money` 可空（自提点为 `zero_money` 时仍返回 `Money`）；`message: String` 可空，承载同步配送服务给出的排除/提示信息。
- 权限：`AUTHENTICATED_APP` 或 `AUTHENTICATED_STAFF_USER`。无权限或结账不属于调用方可见范围时返回权限错误或 `NOT_FOUND`，不返回任何配送信息。
- 错误：payload `errors: [CheckoutError!]!`。
  - `field: "shippingAddress"`, `code: SHIPPING_ADDRESS_NOT_SET` —— 地址缺失或不完整，无法计算。
  - `field: "deliveryOptions"`, `code: DELIVERY_OPTIONS_SERVICE_ERROR`（新增）—— 同步配送服务报错。
  - `field: "id"`, `code: GRAPHQL_ERROR` / `NOT_FOUND` —— 结账不存在或不可见。
  - 失败时**不覆盖**已保存的有效选择，也不保存半成品选择。
- 完成判定：本操作**只读**，不写 `Checkout.shipping_method`、`shipping_method_name`、`undiscounted_base_shipping_price_amount`、`last_change`，不产生任何持久化。完成判定为「返回的 `availableDeliveryOptions` 与 `selectedDeliveryOptionId` 反映本次请求时刻的地址、行项目、渠道与同步配送服务结果」。重复调用无副作用。
- 变更与兼容：与 Base 的差异是**纯新增**。Base 的 `Checkout.availableShippingMethods`、`Checkout.shippingMethods`、`Checkout.shippingMethod`、`Checkout.deliveryMethod` 与 `checkoutShippingMethodUpdate` 保持原 resolver 与原弃用 reason 不变；旧客户端不受影响。

### I02 · 配送方式有效性与完成结账复核
- 所属设计单元：BD02
- 提供方：Core，`saleor/checkout/checkout_cleaner.py` 新增共用复核函数（供 `checkoutDeliveryMethodUpdate` / `checkoutComplete` / 已弃用的 `checkoutShippingMethodUpdate` 共用），并在 `saleor/checkout/complete_checkout.py` 完成路径内接入
- 调用方：既有 Storefront 客户端（`checkoutDeliveryMethodUpdate`、`checkoutComplete`、`checkoutShippingMethodUpdate`）；Dashboard 复用通用错误映射，不新增调用点
- 目标定义：**既有操作签名不变**，仅错误语义与错误码扩展。

```graphql
checkoutDeliveryMethodUpdate(
  """The ID of the delivery method."""
  deliveryMethodId: ID

  """The checkout's ID."""
  id: ID

  """Checkout token."""
  token: UUID @deprecated(reason: "Use `id` instead.")
): CheckoutDeliveryMethodUpdate

checkoutComplete(
  """Checkout ID."""
  checkoutId: ID @deprecated(reason: "Use `id` instead.")
  id: ID
  metadata: [MetadataInput!]
  paymentData: JSONString
  redirectUrl: String
  storeSource: Boolean
  token: UUID @deprecated(reason: "Use `id` instead.")
): CheckoutComplete

"""Deprecated: use `checkoutDeliveryMethodUpdate` instead."""
checkoutShippingMethodUpdate(...): CheckoutShippingMethodUpdate

enum CheckoutErrorCode {
  # ... Base 既有值保持不变 ...
  DELIVERY_METHOD_NOT_FOUND
  DELIVERY_OPTIONS_SERVICE_ERROR
}
```

- 字段说明：无签名变化。`deliveryMethodId` 接受 I01 返回的 `DeliveryOption.id`，同时兼容旧客户端提交的 `ShippingMethod:<pk>` 与 `Warehouse:<uuid>` 形式；外部 base64 `app:<identifier>:<method>` 与旧格式 `app:<pk>:<method>` 归一化后比对。只接受**属于当前结账**的配送方式。
- 权限：与 Base 相同（结账自身可访问性规则；无权限/不归属时不泄露配送信息、不改动原选择）。
- 错误：payload `errors: [CheckoutError!]!`，失效原因可区分：

  | 情形 | `field` | `code` |
  | --- | --- | --- |
  | 需配送但未设置方式 | `shipping_method` | `SHIPPING_METHOD_NOT_SET` |
  | 已设置但地址无效 | `shipping_address` | `SHIPPING_ADDRESS_NOT_SET` |
  | 已设置但不在当前有效集合 | `shipping_method` | `DELIVERY_METHOD_NOT_APPLICABLE` |
  | 标识不属于当前结账 / 无法解析 | `delivery_method_id` | `DELIVERY_METHOD_NOT_FOUND`（新增） |
  | 同步配送服务报错 | `delivery_method_id` | `DELIVERY_OPTIONS_SERVICE_ERROR`（新增） |

- 完成判定：
  - `checkoutDeliveryMethodUpdate`：通过复核后写入 `shipping_method` / `shipping_method_name` 与 `last_change`；失败不写入、不改动原选择。
  - `checkoutComplete`：提交前复核；失效时阻止完成，不创建 `Order`、不产生 `Payment` / `TransactionItem` / 库存预留副作用，结账保持可重试（不留下半成品订单）。
  - 已弃用的 `checkoutShippingMethodUpdate` 落库结果与 `checkoutDeliveryMethodUpdate` 完全一致。
- 变更与兼容：签名与字段**零变化**，仅新增两个 `CheckoutErrorCode` 枚举值与复核时机。旧客户端继续可用；旧配送标识按兼容约定处理。`Checkout.shippingMethod` 保留弃用读取。

### I03 · 渠道-仓库直连库存开关
- 所属设计单元：BD03
- 提供方：Core，`saleor/graphql/channel/mutations/utils.py` 与渠道类型；语义落点 `saleor/warehouse/availability.py`、`saleor/checkout/complete_checkout.py`、`saleor/product/managers.py`
- 调用方：本次新增字段，由商户运营/Dashboard 渠道设置页（FD06，可选暴露）与外部集成方读写
- 目标定义：

```graphql
"""Represents the channel stock settings."""
type StockSettings {
  """Allocation strategy defines the preference of warehouses for allocations and reservations."""
  allocationStrategy: AllocationStrategyEnum!

  """
  Determines whether stock is calculated from warehouses directly assigned to the
  channel instead of the shipping zones and addresses of the delivery context.
  Default `false` keeps the existing behaviour.

  Added in Saleor 3.23.
  """
  useChannelWarehousesForStock: Boolean!
}

input StockSettingsInput {
  allocationStrategy: AllocationStrategyEnum!
  useChannelWarehousesForStock: Boolean
}
```

- 字段说明：输出字段非空，默认 `false`；输入字段可空，`null` 表示不修改该设置（沿用当前值）。切换开关不改变任何既有仓库-配送区域关联数据。
- 权限：读随 `Channel` 既有可见性；写随 `channelUpdate` / `channelCreate` 既有权限（`MANAGE_CHANNELS`）。
- 错误：`ChannelError` payload（沿用既有错误码；开关本身为布尔值，无新增错误码）。
- 完成判定：写入后 `Channel.stockSettings.useChannelWarehousesForStock` 读回一致。生效语义：`true` 时只有**直接关联当前渠道**且可用库存大于零的仓库参与可售库存、预留与分配计算；商品查询、结账、订单、履约与草稿订单使用同一语义；`false` 时保持升级前的配送区域/地址关联行为。
- 变更与兼容：纯新增字段。`false`（默认）下行为与 Base 完全一致，未切换设置的商户不受影响。旧客户端继续传地址参数时被接受，但在新方式下不改变「直接关联」决定的结果。

### I04 · 商品按渠道可售性诊断
- 所属设计单元：BD04
- 提供方：Core，`saleor/graphql/product/types/products.py` 新增字段与类型，计算落点 `saleor/product/utils/availability.py`、`saleor/warehouse/models.py`、`saleor/shipping/models.py`
- 调用方：本次新增，由 Dashboard 商品编辑页消费（FD01）；外部集成方可复用
- 目标定义：

```graphql
type Product {
  # ...
  """
  Recalculated, per-channel diagnostics explaining why the product can or cannot
  be sold. ...
  Requires one of the following permissions: MANAGE_PRODUCTS.

  Added in Saleor 3.23.
  """
  channelAvailabilityDiagnostics(
    filter: ProductChannelAvailabilityDiagnosticsFilterInput
    sortBy: ProductChannelAvailabilityDiagnosticsSortingInput
    before: String
    after: String
    first: Int
    last: Int
  ): ProductChannelAvailabilityDiagnosticsCountableConnection
}

type ProductChannelAvailabilityDiagnostics {
  problemsCount: Int!
  warningsCount: Int!
  notApplicableCount: Int!
  problems: [ProductChannelAvailabilityProblem!]!
}

type ProductChannelAvailabilityProblem {
  type: ProductChannelAvailabilityProblemTypeEnum!
  severity: ProductChannelAvailabilityProblemSeverityEnum!
  message: String!
  field: String
  variantId: ID
}

enum ProductChannelAvailabilityProblemSeverityEnum { BLOCKER WARNING NOT_APPLICABLE }

enum ProductChannelAvailabilityProblemTypeEnum {
  NOT_PUBLISHED
  NOT_AVAILABLE_FOR_PURCHASE
  NOT_VISIBLE_IN_LISTINGS
  NO_STOCK
  NO_WAREHOUSE_ASSIGNED
  NO_SHIPPING_ZONE
  NO_VARIANTS
  SHIPPING_NOT_APPLICABLE
  PRODUCT_TYPE_CONFIGURATION
  DIAGNOSTICS_UNAVAILABLE
}

enum ProductChannelAvailabilityDiagnosticsSortField { CHANNEL_NAME CURRENCY }

input ProductChannelAvailabilityDiagnosticsSortingInput {
  direction: OrderDirection!
  field: ProductChannelAvailabilityDiagnosticsSortField!
}

input ProductChannelAvailabilityDiagnosticsFilterInput {
  channel: String
  currency: String
  severity: [ProductChannelAvailabilityProblemSeverityEnum!]
}

type ProductChannelAvailabilityDiagnosticsCountableConnection {
  pageInfo: PageInfo!
  edges: [ProductChannelAvailabilityDiagnosticsCountableEdge!]!
  totalCount: Int
}

type ProductChannelAvailabilityDiagnosticsCountableEdge {
  node: ProductChannelAvailabilityDiagnostics
  cursor: String!
  channel: Channel!
}
```

- 字段说明：
  - 连接为**按渠道分页**：每个 edge 对应一个渠道，`edge.channel` 给出该渠道（非空），`edge.node` 为该渠道的诊断（可空，取不到时为 `null` 且该渠道的诊断内含 `DIAGNOSTICS_UNAVAILABLE`）。
  - `filter.channel` 按渠道名或 slug 匹配；`filter.currency` 按渠道币种匹配；`filter.severity` 为多值，命中任一即返回该渠道。
  - `sortBy.field` 仅支持 `CHANNEL_NAME`、`CURRENCY`，`direction` 为 `OrderDirection`。
  - `problems: [ProductChannelAvailabilityProblem!]!` 列表非空、项非空。`severity` 区分阻断（`BLOCKER`）、警告（`WARNING`）与不适用（`NOT_APPLICABLE`）；不适用项不计入 `problemsCount`。
  - 数字类商品（不需配送）只跳过配送区域相关检查，其余检查照常执行。
- 权限：`MANAGE_PRODUCTS`。无权限时返回权限错误，不返回诊断内容；错误信息不泄露受限渠道配置。
- 错误：查询类，参数非法由 GraphQL 校验层拒绝（未知枚举值、错误类型）。`DIAGNOSTICS_UNAVAILABLE` 是**数据层**的分类结果而非请求失败：某渠道诊断不可计算时该渠道的诊断项标记为不可用，其他渠道照常返回，整体请求仍成功。
- 完成判定：返回的计数与 `problems` 明细一致，且与当前发布状态、可购买时间、库存、仓库关联、配送区域等事实一致。诊断按请求实时计算，前端不得把上一次结果当作最新结论。
- 变更与兼容：纯新增字段与类型，不影响 `Product` 既有字段。

### I05 · 渠道自动完成设置
- 所属设计单元：BD05/BD06
- 提供方：Core，`saleor/graphql/channel/types.py`（`CheckoutSettings`）、`saleor/graphql/channel/mutations/utils.py`（并发校验）；任务落点 `saleor/checkout/tasks.py`
- 调用方：本次新增字段，由 Dashboard 渠道设置页消费（FD06）；外部集成方读写
- 目标定义：

```graphql
type CheckoutSettings {
  useLegacyErrorFlow: Boolean!
  automaticallyCompleteFullyPaidCheckouts: Boolean!

  """
  Time that has to pass since the checkout was last modified before an eligible
  fully paid checkout is picked up by the automatic completion. `null` keeps the
  existing behaviour (no delay). Negative values are rejected.

  Added in Saleor 3.23.
  """
  automaticCompletionDelay: Minute

  """
  Lower bound of the checkout creation time. Only checkouts created at or after
  this moment are picked up by the automatic completion. `null` keeps the existing
  behaviour (no lower bound). This value is not a moment at which the task stops
  running.

  Added in Saleor 3.23.
  """
  automaticCompletionCutoffDate: DateTime

  """
  Date and time at which the checkout settings were last modified. Used as an
  optimistic concurrency token when updating the settings.

  Added in Saleor 3.23.
  """
  updatedAt: DateTime!
}

input CheckoutSettingsInput {
  useLegacyErrorFlow: Boolean @deprecated
  automaticallyCompleteFullyPaidCheckouts: Boolean
  automaticCompletionDelay: Minute
  automaticCompletionCutoffDate: DateTime
  expectedUpdatedAt: DateTime
}

enum ChannelErrorCode {
  # ... Base 既有值保持不变 ...
  CHECKOUT_SETTINGS_OUTDATED
}
```

- 字段说明：
  - `automaticCompletionDelay: Minute` 可空；`null` = 无延迟（沿用既有行为）；负值在执行前拒绝。
  - `automaticCompletionCutoffDate: DateTime` 可空；`null` = 无创建时间下界。它是**结账创建时间的下界**，不是任务停止执行的时间点。
  - `updatedAt: DateTime!` 非空，作为并发令牌读取。
  - `CheckoutSettingsInput.expectedUpdatedAt` 可空；提供时与服务端当前 `updatedAt` 比对，不匹配则拒绝整次更新。`CheckoutSettingsInput.automaticCompletionDelay` / `automaticCompletionCutoffDate` 传 `null` 表示清除该限制（回到默认行为）。
  - 入口为既有的 `channelUpdate(id, input)` / `channelCreate(input)` 的 `checkoutSettings` 字段，不新增 mutation。
- 权限：`MANAGE_CHANNELS`（沿用 `channelUpdate`/`channelCreate`）。无权限返回权限错误，保留上次生效值。
- 错误：`ChannelError` payload，`field` 指向 `checkoutSettings` 或其子字段。
  - `code: CHECKOUT_SETTINGS_OUTDATED`（新增）—— `expectedUpdatedAt` 与当前值不匹配；**拒绝整次更新，保留上次生效值**。
  - `code: GRAPHQL_ERROR` / `INVALID` —— 范围或组合非法（含负的 delay）。
  - 保存成功**不**意味着订单已生成：设置状态与执行结果分离，订单是否完成以实际结账与订单状态为准。
- 完成判定：合法配置保存后可读回一致；生效范围为「`automaticallyCompleteFullyPaidCheckouts = true` 且结账创建时间 ≥ `cutoff` 且距结账最近一次变化已超过 `delay`」的已支付结账。自动完成仍须通过完整资格复核（支付 fully paid、客户或邮箱、账单地址、需配送时的地址与配送方式、商品可售、总额大于零），已完成或处理过的结账不得再次成单；同一结账无论重试多少次只形成一个订单结果。未配置的旧渠道不被改为自动完成。
- 变更与兼容：`CheckoutSettings` / `CheckoutSettingsInput` 上纯新增字段；`ChannelErrorCode` 新增一个枚举值。`null` 默认值保证未配置渠道行为与 Base 一致。

### I06 · 礼品卡支付生命周期
- 所属设计单元：BD07
- 提供方：Core，拟新增 `saleor/graphql/payment/mutations/transaction/checkout_gift_card_payment_create.py` 与 `..._cancel.py`；类型落点 `saleor/graphql/payment/types.py`；模型落点 `saleor/payment/models.py`、`saleor/giftcard/models.py`、`saleor/giftcard/__init__.py`
- 调用方：本次新增，由 Storefront / 支付集成方调用；Dashboard 订单详情消费呈现（FD08）
- 目标定义：

```graphql
"""
Pays a checkout with a gift card. Creates a gift card backed transaction and
reserves the corresponding balance. Repeated requests with the same idempotency
key produce a single authorization.

Requires one of the following permissions: HANDLE_PAYMENTS.

Added in Saleor 3.23.
"""
checkoutGiftCardPaymentCreate(
  """The ID of the checkout."""
  id: ID!

  """Input data required to pay the checkout with a gift card."""
  input: CheckoutGiftCardPaymentCreateInput!

  """
  Idempotency key. Repeated requests carrying the same key do not create a
  second authorization or a second balance change.
  """
  idempotencyKey: String
): CheckoutGiftCardPaymentCreate

"""
Cancels a gift card authorization made for a checkout and releases the held
balance.

Requires one of the following permissions: HANDLE_PAYMENTS.

Added in Saleor 3.23.
"""
checkoutGiftCardPaymentCancel(
  """The ID of the checkout."""
  id: ID!

  """The ID of the gift card transaction to cancel."""
  transactionId: ID!
): CheckoutGiftCardPaymentCancel

type CheckoutGiftCardPaymentCreate {
  checkout: Checkout
  transaction: TransactionItem
  errors: [PaymentError!]!
}

type CheckoutGiftCardPaymentCancel {
  checkout: Checkout
  transaction: TransactionItem
  errors: [PaymentError!]!
}

input CheckoutGiftCardPaymentCreateInput {
  """The code of the gift card used to pay the checkout."""
  giftCardCode: String!
}

type GiftCardPaymentMethodDetails implements PaymentMethodDetails {
  """Name of the payment method."""
  name: String!

  """The gift card used to pay for the transaction."""
  giftCard: GiftCard!
}

input GiftCardPaymentMethodDetailsInput {
  """The gift card code."""
  giftCardCode: String
}

type GiftCard {
  # ...
  """Amount of the gift card reserved by open authorizations."""
  reservedBalance: Money!

  """Balance available for new payments (current balance minus reserved)."""
  availableBalance: Money!
}

type TransactionItem {
  # ...
  """Gift card used to pay for this transaction."""
  giftCard: GiftCard
}

type Order {
  # ...
  """List of user gift cards."""
  giftCards: [GiftCard!]! @deprecated(reason: "Gift cards used as a payment method are tracked as transactions. Use the order transactions instead.")
}

type Checkout {
  # ...
  """List of gift cards associated with this checkout."""
  giftCards: [GiftCard!]! @deprecated(reason: "Gift cards used as a payment method are tracked as transactions. Use the checkout transactions instead.")
}

enum GiftCardEventsEnum {
  # ... Base 既有值保持不变 ...
  AUTHORIZED
  AUTHORIZATION_RELEASED
  REFUNDED
}

enum PaymentMethodTypeEnum { CARD OTHER GIFT_CARD }

input PaymentMethodDetailsInput {
  card: CardPaymentMethodDetailsInput
  other: OtherPaymentMethodDetailsInput
  giftCard: GiftCardPaymentMethodDetailsInput
}

enum PaymentErrorCode {
  # ... Base 既有值保持不变 ...
  GIFT_CARD_NOT_APPLICABLE
  GIFT_CARD_INVALID
  GIFT_CARD_INSUFFICIENT_BALANCE
  IDEMPOTENCY_KEY_REUSED
}
```

- 字段说明：
  - `checkoutGiftCardPaymentCreate.id: ID!` 必填（结账全局 ID）。`input.giftCardCode: String!` 必填。`idempotencyKey: String` 可空；提供时按该键去重。
  - 两个 payload 的 `checkout` 与 `transaction` 可空：失败时可为 `null`，此时 `errors` 非空。`errors: [PaymentError!]!` 列表非空、项非空，每项含 `field`、`code`、`message`。
  - `GiftCard.reservedBalance: Money!` 与 `availableBalance: Money!` 均非空。不变量：`currentBalance >= 0`、`reservedBalance >= 0`、`availableBalance = currentBalance - reservedBalance >= 0`。`currentBalance` 语义不变。
  - `TransactionItem.giftCard: GiftCard` 可空：仅礼品卡类交易非 `null`。`GiftCardPaymentMethodDetails.giftCard: GiftCard!` 非空。
  - `PaymentMethodDetailsInput.giftCard` 可空，与既有 `card`、`other` 并列，用于 `transactionCreate` 侧写入礼品卡方式。
  - `GiftCardEventsEnum` 三个新事件：`AUTHORIZED`（授权）、`AUTHORIZATION_RELEASED`（取消授权）、`REFUNDED`（退款）。
  - `Checkout.giftCards` / `Order.giftCards` 保留**可读**并弃用（reason 指向交易生命周期），历史结账与订单仍可解释。
- 权限：`HANDLE_PAYMENTS`（`PaymentPermissions.HANDLE_PAYMENTS`）。无权限时不能使用礼品卡支付，且错误响应不含礼品卡余额信息。
- 错误：payload `errors: [PaymentError!]!`。
  - `GIFT_CARD_NOT_APPLICABLE` —— 礼品卡不存在、已停用或已过期。
  - `GIFT_CARD_INVALID` —— 币种与结账/订单币种不一致。
  - `GIFT_CARD_INSUFFICIENT_BALANCE` —— 可用余额不足（不做部分扣减）。
  - `IDEMPOTENCY_KEY_REUSED`（新增）—— 同一幂等键被用于语义不同的请求。
  - 任一失败：**余额与支付状态不变**，且**不改走普通支付**。
- 完成判定：
  - 创建：形成一条 `TransactionItem`（`paymentMethodDetails` 为 `GiftCardPaymentMethodDetails`）与 `AUTHORIZED` 事件，`reservedBalance` 增加对应金额，结账支付状态经既有状态刷新逻辑更新。
  - 扣款：`chargedAmount` 增加、`currentBalance` 减少、`reservedBalance` 减少，礼品卡余额与结账/订单支付状态反映同一结果。
  - 取消：`reservedBalance` 释放，授权状态与可用余额回到可解释状态，写入 `AUTHORIZATION_RELEASED` 事件。
  - 退款：受可退余额约束（已扣款减已退款），写入 `REFUNDED` 事件，`currentBalance` 增加。
  - 幂等：同一结账/订单对同一礼品卡同一金额的重复请求只形成一次有效授权或扣款、一次余额变化，不形成冲突授权。
  - 无事件时返回**空事件列表**，不因此判定请求失败。
- 变更与兼容：新增 mutation、类型、字段与枚举值。`checkoutAddPromoCode` 的礼品卡分支改为**拒绝**并给出替代路径（指向 `checkoutGiftCardPaymentCreate`），不再新增折扣式抵扣；其 docstring 已标注该变化。历史 `Checkout.giftCards` / `Order.giftCards` 关联保留可读并弃用。

### I07 · 订单金额分解与人工资金动作边界
- 所属设计单元：BD08
- 提供方：Core，`saleor/graphql/order/types.py`（`Order.totalGiftCard`、`Order.actions`）、`saleor/graphql/payment/types.py`（`TransactionItem.actions`）；动作落点 `saleor/order/utils.py`、`saleor/payment/utils.py`
- 调用方：Dashboard 订单详情（FD08）；外部集成方读取
- 目标定义：

```graphql
type Order {
  # ...
  """
  Total amount covered by gift cards. Gift card amounts are reported by this
  field and are not counted again as regular payments.

  Added in Saleor 3.23.
  """
  totalGiftCard: Money!

  """List of actions that can be performed in the current state of an order."""
  actions: [OrderAction!]!
}

type TransactionItem {
  # ...
  """List of actions that can be performed in the current state of a transaction."""
  actions: [TransactionActionEnum!]!
}
```

- 字段说明：`Order.totalGiftCard: Money!` 非空，等于该订单礼品卡类交易的有效扣款/授权合计，**只计一次**，不叠加到普通支付；无礼品卡时为 `Money(0, order.currency)`。`Order.actions: [OrderAction!]!` 与 `TransactionItem.actions: [TransactionActionEnum!]!` 的签名不变，语义收敛为「按**当前支付方式与订单状态**产出允许动作」。金额分解字段（商品、折扣、税费、配送、礼品卡、已授权、已扣款、已退款、剩余待付）均由既有 resolver 提供，口径统一：新交易路径取 `TransactionItem.amount*`，兼容路径取 `Payment` 汇总；同一笔金额不被两条路径重复计入。
- 权限：读随订单既有可见性；`totalGiftCard` 与 `Order.actions` 同 `Order` 的 `MANAGE_ORDERS` 边界。人工动作 `orderMarkAsPaid` / `orderCapture` / `orderRefund` / `transactionRequestAction` 需 `MANAGE_ORDERS` / `HANDLE_PAYMENTS`；无权限不操作，错误不泄露受限金额。
- 错误：既有 mutation 的 `OrderError` / `PaymentError` payload（沿用既有错误码）。
  - 金额为负 —— 执行前由 `PositiveDecimal` 标量拒绝。
  - 标记已支付但已有支付或交易记录 —— 拒绝。
  - 捕获金额超过当前可捕获授权 —— 拒绝，订单与支付状态不变；等于合法边界可成功。
  - 退款超过可退余额 —— 拒绝；多笔交易不重复占用同一额度。
- 完成判定：
  - `totalGiftCard` 与礼品卡交易事件一致，且与订单金额分解的其余部分相加可解释（不重复计入）。
  - 动作成功时返回**刷新后**的订单、`TransactionEvent` 与余额。
  - 资金动作幂等：重复提交不产生重复扣款、退款或冲突事件；失败保留原状态并给可区分错误，失败与事件写入在同一事务内，不产生部分写入。
- 变更与兼容：`Order.totalGiftCard` 为新增字段（resolver 派生，无迁移）。`Order.actions` / `TransactionItem.actions` 为签名不变、语义收紧；对既有合法调用是行为一致或更严格（不再出现不允许的动作）。

### I08 · 根级交易查询
- 所属设计单元：BD09
- 提供方：Core，`saleor/graphql/payment/schema.py` 新增根级字段，复用 `saleor/graphql/payment/types.py` 的 `TransactionItem`
- 调用方：本次新增，由客服工具 / 外部集成方调用；Dashboard 本轮不新增调用点
- 目标定义：

```graphql
type Query {
  # ...
  """
  List of payment transactions. Allows locating transactions by basic business
  relations and payment identifiers. Date based and event based filtering are not
  provided by this field.

  Requires one of the following permissions: HANDLE_PAYMENTS, MANAGE_ORDERS,
  MANAGE_CHECKOUTS.

  Added in Saleor 3.23.
  """
  transactions(
    """Filtering options for transactions."""
    where: TransactionWhereInput

    """Return the elements in the list that come before the specified cursor."""
    before: String

    """Return the elements in the list that come after the specified cursor."""
    after: String

    """Return the first n elements from the list."""
    first: Int

    """Return the last n elements from the list."""
    last: Int
  ): TransactionItemCountableConnection
}

input TransactionWhereInput {
  """Filter by transaction IDs."""
  ids: [ID!]

  """Filter by the order the transaction belongs to."""
  orderId: ID

  """Filter by the checkout the transaction belongs to."""
  checkoutId: ID

  """Filter by payment service provider reference."""
  pspReference: String

  """Filter by the app that created the transaction."""
  appId: ID

  """Filter by metadata fields of transactions."""
  metadata: MetadataFilterInput
}

type TransactionItemCountableConnection {
  pageInfo: PageInfo!
  edges: [TransactionItemCountableEdge!]!
  totalCount: Int
}

type TransactionItemCountableEdge {
  node: TransactionItem!
  cursor: String!
}
```

- 字段说明：
  - `where` 各字段为「与」关系；同一字段内的 `ids` 为多值。`where` 省略时按调用方可见范围返回全部交易。
  - 分页为 Relay 游标式，`first`/`last` 与 `before`/`after` 语义遵循 `CountableConnection`；`totalCount` 可空。
  - 返回项复用 `TransactionItem` 全部既有字段（`pspReference`、`amountAuthorized`/`amountCharged`/`amountRefunded`、`actions`、`events`、`paymentMethodDetails`、`giftCard`、`order`、`checkout`），足以支撑订单金额、支付方式、状态与事件展示。
  - **明确不提供**：交易创建/修改日期筛选、事件类型或事件日期筛选、本查询专用排序与索引。请求这些能力时字段不存在，由 GraphQL 校验层报错，不静默忽略为空。
- 权限：`HANDLE_PAYMENTS`、`MANAGE_ORDERS` 或 `MANAGE_CHECKOUTS`；并叠加对象范围 —— 客户仅见自己订单/结账的交易，App 仅见自身可见范围的交易，员工按权限与对象范围。不属于当前对象的交易不泄露详情。权限失败返回权限错误而非空列表。
- 错误：参数与分页由 GraphQL 校验层拒绝（错误过滤类型、越界分页、空分页项）。无权限返回 `PermissionDenied`。不以成功空结果掩盖非法请求。
- 完成判定：返回结果、数量、顺序与游标稳定且可解释；礼品卡、普通支付与多交易订单都能按上述条件定位。
- 变更与兼容：纯新增根级字段与输入/连接类型，不影响既有单条 `transaction` 查询与 `TransactionItem` 类型。

### I09 · 密码登录策略
- 所属设计单元：BD11
- 提供方：Core，`saleor/graphql/shop/types.py`（`Shop.passwordLoginMode`）、`saleor/graphql/shop/mutations/shop_settings_update.py`（写入）；执行点 `saleor/graphql/account/mutations/authentication/*`、`saleor/core/jwt.py`
- 调用方：Dashboard 设置页与登录页（FD04）；Storefront / 外部集成方读取
- 目标定义：

```graphql
type Shop {
  # ...
  """
  Determines whether users are allowed to authenticate with a password and which
  identities are covered. Read by the server-side authentication flows, the
  dashboard login screen and the settings page.

  Added in Saleor 3.23.
  """
  passwordLoginMode: PasswordLoginModeEnum!
}

input ShopSettingsInput {
  # ...
  passwordLoginMode: PasswordLoginModeEnum
}

"""
Determines which identities are allowed to authenticate with a password.

    ENABLED - password authentication is available to all supported users whose
    account state allows it.
    CUSTOMERS_ONLY - password authentication is available to customer accounts
    only. Staff accounts cannot obtain a staff session or dashboard access with a
    password.
    DISABLED - password authentication is turned off together with the related
    entry points: password login, password reset, password set and password
    change. Token paths that could otherwise bypass the policy are rejected as
    well.

Added in Saleor 3.23.
"""
enum PasswordLoginModeEnum { ENABLED CUSTOMERS_ONLY DISABLED }

enum AccountErrorCode {
  # ... Base 既有值保持不变 ...
  PASSWORD_LOGIN_DISABLED
  PASSWORD_LOGIN_CUSTOMERS_ONLY
}
```

- 字段说明：`Shop.passwordLoginMode: PasswordLoginModeEnum!` 非空，默认 `ENABLED`（与升级前行为一致）。`ShopSettingsInput.passwordLoginMode` 可空，`null` 表示不修改。入口为既有的 `shopSettingsUpdate(input)`，不新增 mutation。
- 权限：读取随 `Shop` 既有可见性；写入需 `MANAGE_SETTINGS`（沿用 `shopSettingsUpdate`）。无权限返回权限错误，保留上次生效值。
- 错误：`ShopError` payload（沿用既有错误码）。
  - `PASSWORD_LOGIN_DISABLED`（新增）—— `DISABLED` 下密码登录、重置、设置或修改被拒绝，以及可绕过策略的旧 token 路径被拒绝。
  - `PASSWORD_LOGIN_CUSTOMERS_ONLY`（新增）—— `CUSTOMERS_ONLY` 下员工账号尝试密码登录/取得员工会话时拒绝。
- 完成判定：保存后认证请求**立即**读取新值（策略读取无缓存）。三种模式语义：
  - `ENABLED` —— 符合账户状态的受支持用户可用密码。
  - `CUSTOMERS_ONLY` —— 仅客户身份可使用密码能力；员工不能凭密码取得员工会话或后台权限。
  - `DISABLED` —— 关闭密码认证及相关入口，含重置、设置、修改与旧 token 路径。
  外部认证独立按自身配置处理，不受本策略影响。加载或保存失败保留原生效值，不把未保存值当成功。
- 变更与兼容：纯新增字段与枚举值；默认 `ENABLED` 保证既有部署行为不变。

### I10 · 扩展字段与安装校验
- 所属设计单元：BD14
- 提供方：Core，`saleor/graphql/app/types.py`（`AppExtension`、`AppManifestExtension`）；数据落点 `saleor/app/models.py`
- 调用方：Dashboard 扩展宿主与扩展目录（FD05）；外部 App 集成方
- 目标定义：

```graphql
type AppExtension implements Node {
  # ...
  """Place where given extension will be mounted."""
  mount: AppExtensionMountEnum! @deprecated(reason: "Use `mountName` instead.")

  """Type of way how app extension will be opened."""
  target: AppExtensionTargetEnum! @deprecated(reason: "Use `targetName` instead.")

  """App extension options."""
  options: AppExtensionPossibleOptions @deprecated(reason: "Use `settings` field instead.")

  """Name of the extension mount point in the dashboard."""
  mountName: String!

  """Name of the extension target in the dashboard."""
  targetName: String!

  """App extension settings."""
  settings: JSON!
}

type AppManifestExtension {
  permissions: [Permission!]!
  label: String!
  url: String!

  mount: AppExtensionMountEnum! @deprecated(reason: "Use `mountName` instead.")
  target: AppExtensionTargetEnum! @deprecated(reason: "Use `targetName` instead.")

  """Name of the extension mount point in the dashboard."""
  mountName: String!

  """Name of the extension target in the dashboard."""
  targetName: String!

  """App extension settings."""
  settings: JSON!
}
```

- 字段说明：`mountName` / `targetName` / `settings` 均为非空（`settings` 为 `JSON!`，无设置时为 `{}`，不返回 `null`）。三个旧字段保留可读并弃用，reason 指向替代字段。`AppManifestExtension` 与 `AppExtension` 采用同一契约，使 Core 与 Dashboard 生成客户端一致。
- 权限：读取随 `app` 既有可见性，仅返回调用方允许的扩展数据；安装/更新需 `AUTHENTICATED_STAFF_USER` + `MANAGE_APPS`。
- 错误：`AppError` payload（沿用既有错误码）。重复 `identifier`、无效权限、非法 `target`、无法解析的 `settings` 均拒绝安装或更新，且不破坏已有有效数据。
- 完成判定：迁移与读取适配后，历史扩展仍可查询、编辑与渲染，且 `settings` 内容保留（不因迁移丢失）。新客户端使用 `mountName`/`targetName`/`settings`。
- 变更与兼容：新增字段 + 旧字段弃用（不删除）。旧客户端继续读取 `mount`/`target`/`options`；Dashboard 的 `schema.graphql` 已包含三新字段，Core 侧对齐后双方生成客户端一致。

### I11 · 安装输入必填与 token 语义
- 所属设计单元：BD14/BD19
- 提供方：Core，`saleor/graphql/app/mutations/app_install.py`、`saleor/app/manifest_validations.py`
- 调用方：Dashboard 扩展安装表单（FD05）；外部 App 集成方
- 目标定义：

```graphql
input AppInstallInput {
  """What app will be installed."""
  appName: String!

  """App manifest URL."""
  manifestUrl: String!

  """Determine if app will be set active or not."""
  activateAfterInstallation: Boolean

  """List of permission code names to assign to this app."""
  permissions: [PermissionEnum!]
}

mutation appInstall(input: AppInstallInput!): AppInstall
```

- 字段说明：`appName: String!` 与 `manifestUrl: String!` 为必填（Base 中为可空 `String`）。`activateAfterInstallation` 与 `permissions` 保持可选。`tokenTargetUrl` **不属于** `AppInstallInput`（Base 与目标 schema 均无该字段），属可选安装信息：缺省不使合法安装失败；不需要新建或安装 token 时不返回 token（`AppInstall` payload 不提供 `token` 字段）。
- 权限：`AUTHENTICATED_STAFF_USER` + `MANAGE_APPS`。
- 错误：`AppError` payload。必填缺失由 GraphQL 校验层在执行前拒绝（`appName`/`manifestUrl` 为 `String!`）。
- 完成判定：合法安装创建 `App` 与 `AppExtension`；无 `tokenTargetUrl` 时不新建 token、不发送 token。
- 变更与兼容：`appName`/`manifestUrl` 由可空收紧为必填，属**破坏性收紧**；Dashboard 安装表单已提供这两个字段，不受影响；未提供二者的第三方调用方会收到 schema 校验错误（明确的迁移信号，而非静默失败）。

### I12 · 投递状态与单条重试
- 所属设计单元：BD15
- 提供方：Core，`saleor/core/__init__.py`（`EventDeliveryStatus`）、`saleor/core/models.py`、`saleor/graphql/webhook/enums.py`（`EventDeliveryStatusEnum`）；重试落点 `saleor/graphql/webhook/mutations/event_delivery_retry.py`
- 调用方：Dashboard Webhook 投递展示与单条重试（FD10）；外部 App 管理方
- 目标定义：

```graphql
enum EventDeliveryStatusEnum {
  PENDING
  SUCCESS
  FAILED
  RETRYING
}

type EventDelivery implements Node {
  # ... Base 既有字段 ...
  """Event delivery status."""
  status: EventDeliveryStatusEnum!
  # ...
}

"""
Retries event delivery.

Requires one of the following permissions: MANAGE_APPS.
"""
eventDeliveryRetry(
  """ID of the event delivery to retry."""
  id: ID!
): EventDeliveryRetry
```

- 字段说明：`EventDeliveryStatusEnum` 新增 `RETRYING`，用于表达「重试进行中」。`EventDelivery.status` 与 `EventDeliveryAttempt.status` 均使用该枚举。`eventDeliveryRetry` 的签名与权限不变，语义收敛为「按单条 delivery 重试」。
- 权限：`MANAGE_APPS`；此外需具备相关 App 或业务域权限。无权限拒绝。重试内容不超出 App 可见字段边界。
- 错误：既有 `EventDeliveryRetry` payload 的 `errors`（沿用既有错误码）。
- 完成判定：单条 delivery 失败只影响该 delivery，其他订阅继续；失败按策略重试并记录 `RETRYING` → `SUCCESS`/`FAILED` 的状态迁移。**异步内容尚未生成时不得显示为成功**，`PENDING` 与 `RETRYING` 均为非终态。既有 Webhook 失败告警保留，不扩展为 App Problems 功能。
- 变更与兼容：新增一个枚举值；`eventDeliveryRetry` 为既有操作。旧客户端若未识别 `RETRYING` 需按「非终态」处理（新枚举值对旧客户端的风险已在 §3.1 记录）。

### I13 · 订单配送元数据快照
- 所属设计单元：BD16
- 提供方：Core，`saleor/graphql/order/types.py`；写入落点 `saleor/checkout/complete_checkout.py` 与 `saleor/graphql/order/mutations/draft_order_complete.py`；模型落点 `saleor/order/models.py`
- 调用方：Dashboard 订单详情与履约视图（FD08）；外部集成方
- 目标定义：

```graphql
type Order implements Node & ObjectWithMetadata {
  # ...
  """
  Public metadata snapshot of the delivery method as it was when the order was
  created. Never reflects later changes to the source delivery method.

  Added in Saleor 3.23.
  """
  shippingMethodMetadata: [MetadataItem!]!

  """Look up a single metadata key in the delivery method snapshot."""
  shippingMethodMetafield(key: String!): String

  """Look up metadata keys in the delivery method snapshot."""
  shippingMethodMetafields(keys: [String!]): Metadata

  """
  Private metadata snapshot of the delivery method as it was when the order was
  created. Requires staff permissions to access. Never reflects later changes to
  the source delivery method.

  Added in Saleor 3.23.
  """
  shippingMethodPrivateMetadata: [MetadataItem!]!

  """Look up a single private metadata key in the delivery method snapshot."""
  shippingMethodPrivateMetafield(key: String!): String

  """Look up private metadata keys in the delivery method snapshot."""
  shippingMethodPrivateMetafields(keys: [String!]): Metadata
}
```

- 字段说明：`shippingMethodMetadata: [MetadataItem!]!` 与 `shippingMethodPrivateMetadata: [MetadataItem!]!` 列表非空（无快照时为空数组，稳定空值，不返回 `null`）。`shippingMethodMetafield(key)` / `shippingMethodPrivateMetafield(key)` 未命中返回 `null`。`shippingMethodMetafields(keys)` / `shippingMethodPrivateMetafields(keys)` 的 `keys` 省略时返回全部。快照为**创建时事实**，源配送方式后续修改、停用或删除不回写。
- 权限：公开快照随订单既有可见性；私有快照需 staff 权限（沿用订单私有元数据权限规则）。未授权身份不可读私有快照。
- 错误：查询类，参数错误由 GraphQL 校验层拒绝；无权限返回权限错误而非空值。
- 完成判定：结账成单与草稿订单成单两条路径都在创建订单时写入当时的 public/private 元数据快照，供订单与履约读取。相关事件内容与订单一致。迁移后已有订单元数据仍可读，不重复生成记录、不丢数据；没有元数据的历史记录返回空数组。
- 变更与兼容：纯新增字段。历史订单按 §3.2 的回填策略处理。

### I14 · Federation representations 校验
- 所属设计单元：BD18
- 提供方：Core，`saleor/graphql/core/federation/schema.py`
- 调用方：Apollo Federation 网关与子图消费者
- 目标定义：

```graphql
type Query {
  # ...
  _entities(representations: [_Any!]!): [_Entity]
  _service: _Service!
}
```

- 字段说明：`representations` 由 `[_Any]` 收紧为 `[_Any!]!` —— 参数本身必填、列表本身非空、**列表项非空**。传入 `null`、数组中的 `null` 项或错误类型在执行前被拒绝。
- 权限：无额外权限要求（Federation 基础设施接口），沿用既有可见性。
- 错误：参数校验由 GraphQL 校验层/标量拒绝；`__typename` 未知或 representation 无法解析时返回可分支处理的错误，不返回成功空列表。
- 完成判定：合法的单值、数组与组合查询继续可用；非法输入不产生部分写入。
- 变更与兼容：**破坏性收紧**。发送 `representations: null` 或含 `null` 项的旧网关会收到 schema 校验错误，这是本轮要求的显式失败语义（BC-026）。合法调用不受影响。

### I15 · 弃用读取与已退出能力
- 所属设计单元：BD19
- 提供方：Core，`saleor/graphql/product/mutations/digital_contents.py`、`saleor/graphql/product/types/products.py`、`saleor/graphql/order/types.py`、`saleor/graphql/payment/types.py`、`saleor/graphql/order/mutations/draft_order_create.py`
- 调用方：所有既有客户端；Dashboard 重新 codegen 后不再生成不支持的操作
- 目标定义（相对 Base 的差异，其余字段保持不变）：

```graphql
type Mutation {
  # 已移除（Base 中存在，目标 schema 中不存在）：
  #   digitalContentCreate(input: DigitalContentUploadInput!, variantId: ID!): DigitalContentCreate
  #   digitalContentDelete(variantId: ID!): DigitalContentDelete
  #   digitalContentUpdate(input: DigitalContentInput!, variantId: ID!): DigitalContentUpdate
  #   digitalContentUrlCreate(input: DigitalContentUrlCreateInput!): DigitalContentUrlCreate
}

type ProductVariant {
  """Digital content for the product variant. Requires MANAGE_PRODUCTS."""
  digitalContent: DigitalContent @deprecated(reason: "The legacy digital content interface is not supported. Provide digital goods through Apps.")
}

type OrderLine {
  digitalContentUrl: DigitalContentUrl @deprecated(reason: "The legacy digital content interface is not supported. Provide digital goods through Apps.")
}

type Query {
  """Look up digital content by ID. Requires MANAGE_PRODUCTS."""
  digitalContent(id: ID!): DigitalContent @deprecated(reason: "The legacy digital content interface is not supported. Provide digital goods through Apps.")

  """List of digital content. Requires MANAGE_PRODUCTS."""
  digitalContents(...): DigitalContentCountableConnection
}

type Payment {
  """Informs whether this is a partial payment."""
  partial: Boolean! @deprecated(reason: "The `Payment` flow does not support partial payments. Use transactions instead.")
}

input DraftOrderInput {
  """ID of the voucher associated with the order."""
  voucher: ID @deprecated(reason: "Use `voucherCode` instead.")
}
```

- 字段说明：
  - 四个数字商品 mutation 从公开 schema **移除**：调用方收到 GraphQL 校验层「字段不存在」错误，等价于迁移错误，不再出现无解释的成功空响应。其 payload/input 类型在 SDL 中保留（未被引用），不影响解析与校验。
  - `ProductVariant.digitalContent`、`OrderLine.digitalContentUrl`、`Query.digitalContent`、`Query.digitalContents` 保留**可读**并弃用（reason 指向 Apps/现行方案）。
  - `Payment.partial` 保留可读并弃用（reason 指向 transactions）。
  - `DraftOrderInput.voucher`（`draftOrderCreate` 与 `draftOrderUpdate` 两个输入共用）保留可读并弃用，替代路径 `voucherCode`。
  - 旧 Adyen、NP Atobarai 插件随附能力不再承诺（属部署/插件配置边界，不在 GraphQL schema 中体现）。
- 权限：读取侧沿用各对象既有权限；导出沿用 `exportProducts` / `exportGiftCards` / `exportVoucherCodes` 的导出权限（Base 中不存在其他旧导出 mutation，故无额外弃用对象）。
- 错误：已退出能力返回「字段不存在」的 schema 校验错误；弃用读取仍正常返回。
- 完成判定：迁移可从空库执行；既有订单、交易、扩展、库存与元数据的业务含义保留。Core 公开 schema、Dashboard 生成客户端与错误映射一致，不继续生成不支持的操作。
- 变更与兼容：移除操作是**破坏性**变更，按 BC-027 显式失败语义交付；弃用字段保留读取并给出替代路径，不通过别名、隐藏路由或生成文件重新暴露。

## 3. 其他

### 3.1 无接口变化的边界（保留章节并说明原因）

以下边界有行为/校验落点调整，但不新增或改变公开 schema 契约，因此不登记为 I 编号：

- **R12/R13 搜索语义（BD10）**：保留结账、礼品卡、商品、订单各自的主体增强搜索与客户/员工的基础搜索文档；仅明确「异常不转空结果、空关键词不引发全量」。无 schema 变化。
- **R14/R15 Dashboard 列表与选择器**：纯前端（FD02/FD03），无后端改动。
- **R17 Google OIDC 离线授权（BD12）**：`access_type=offline` 是外部 OIDC provider 的授权参数，不改变 Saleor 公开 schema。
- **R18 富文本与外链校验（BD13）**：校验在既有 `AttributeValue` 写入通道内完成，失败经既有 mutation 的 `errors` 表达。无新增字段/类型。
- **R20 扩展表单响应、R21 自托管扩展目录（FD05）**：前端承担。
- **R22 同步载荷构建边界（BD15）**：不改变 `WebhookEventInfo` 与订阅 schema。
- **R25 元数据基础读写（BD17）**：沿用既有 `graphql/meta/` mutation，不新增入口。
- **R28 权限边界（BD20）**：权限收紧与正确化，字段与类型不变。
- **R29/R30 工作台一致性（FD06/FD07）**：前端承担。
- **R31 非目标**：不新增任何类型、字段或操作（App Problems、独立变体生成器、交易日期/事件筛选与专用排序索引、异步外链媒体等均不出现）。

### 3.2 未决项与实现阶段决策

- **PRD Q6（交易根级查询的字段名与分页形式）**：本轮在 I08 中确定为 `Query.transactions(where, before, after, first, last): TransactionItemCountableConnection`，`where` 为 `TransactionWhereInput`；与既有单条 `transaction` 查询同目录，采用 Relay 游标分页。该决策已写入 `target-schema.graphql`。
- **历史订单配送元数据回填**：`Order.shippingMethodMetadata` / `shippingMethodPrivateMetadata` 对升级前订单返回稳定空值；是否用数据迁移从现存配送方式回填，由实现阶段按 AC-24-4「不重复生成记录、不丢数据」决定，不影响本接口契约。
- **数字商品 payload/input 类型的去留**：四个 mutation 移除后，`DigitalContentCreate` 等 payload 类型与 `DigitalContent*Input` 输入类型在 SDL 中未被引用。本轮保留它们以最小化 diff；是否在后续大版本清理不影响本接口契约。
- **`RETRYING` 对旧客户端的兼容**：新增枚举值可能使未识别该值的旧客户端解析失败。按 BC-023 的要求，状态必须可区分「等待/成功/失败/重试中」，故本轮引入；旧客户端需按非终态处理。

### 3.3 补充协议描述

本目录 `interfaces/` 下的补充描述，供前后端共同引用：

- `interfaces/delivery-option-id.md` —— 配送选项标识的三态格式与 `checkoutDeliveryOptionsRecalculate` ↔ `checkoutDeliveryMethodUpdate` 的取值约定（I01/I02）。
- `interfaces/event-delivery-status.md` —— `EventDelivery` / `EventDeliveryAttempt` 的状态机与非终态语义（I12）。

### 3.4 目标 SDL 校验记录

`target-schema.graphql` 由 `/workspace/scratch/build_target_schema.py` 从 Base 确定性生成：每处编辑锚定在 Base 中**恰好出现一次**的字符串上（脚本内置计数断言，锚点不唯一即报错），因此不存在静默空改。生成后执行了以下检查：

**已执行的检查**

| 检查 | 工具 | 结果 |
| --- | --- | --- |
| 语法解析（完整 SDL） | graphql-core 3.2.3 `parse` | 通过，1429 个定义 |
| 类型构建与类型引用解析 | `build_schema` | 通过，1439 个类型 |
| Schema 合法性（接口实现、非空输出、参数默认值等） | `validate_schema` | 通过，0 个错误 |
| I01–I15 目标元素存在性与签名 | 结构化断言脚本（47 项） | 全部通过，0 失败 |
| 锚点唯一性 | 生成脚本内置断言 | 全部唯一 |
| 未变更 Base 定义保留 | 与 Base 逐行 diff | 仅本设计涉及的 41 处编辑；删除行全部属于被移除/被替换的目标 |

**未运行的检查（及原因）**

| 检查 | 未运行原因 |
| --- | --- |
| 与真实 Core 实现的一致性（resolver 是否按本契约返回） | 本阶段只做设计，未实现 resolver；实现阶段由 BT01–BT21 的验证项覆盖 |
| 与 Dashboard 生成客户端（`src/graphql/types.generated.ts`）的编译一致性 | 需在实现阶段以更新后的 `schema.graphql` 重新 codegen 后验证；本轮无法提前运行 |
| Schema 快照测试（Saleor 自带的 `test_schema` 类快照） | 需要可运行的 Core 测试环境与数据库，本阶段未运行 |
| 前后端消费一致性（字段级） | 已做**人工**核对：`frontend-design.md` §4 引用的全部类型与字段名均存在于目标 SDL；未运行自动化的 codegen/类型检查（无构建环境） |
| 运行时行为（幂等、并发、事务回滚、任务调度） | 属实现阶段，由 BT 验证项与测试用例覆盖 |

**前后端消费一致性的人工核对结果**：`frontend-design.md` §4 依赖表中引用的 `CheckoutDeliveryOptionsRecalculate`、`CheckoutErrorCode` 新值、`StockSettings.useChannelWarehousesForStock`、`Product.channelAvailabilityDiagnostics` 及 `ProductChannelAvailabilityDiagnostics*`、`CheckoutSettings.automaticCompletion*`、`ChannelErrorCode.CHECKOUT_SETTINGS_OUTDATED`、`GiftCardPaymentMethodDetails`、`TransactionItem.giftCard`、`GiftCard.reservedBalance/availableBalance`、`GiftCardEventsEnum` 新值、`Order.totalGiftCard`、`Order.actions`、`TransactionItem.actions`、`Query.transactions` 与 `TransactionWhereInput`、`Shop.passwordLoginMode`、`PasswordLoginModeEnum`、`AccountErrorCode` 新值、`AppExtension`/`AppManifestExtension` 的 `mountName`/`targetName`/`settings`、`AppInstallInput` 必填项、`EventDeliveryStatusEnum.RETRYING`、`eventDeliveryRetry`、`Order.shippingMethodMetadata`/`shippingMethodPrivateMetadata`、`_entities` 与 I15 的弃用/移除项，均在 `target-schema.graphql` 中存在且签名一致。`backend-design.md` §4 的 I01–I15 表与本文件编号、标题一一对应。
