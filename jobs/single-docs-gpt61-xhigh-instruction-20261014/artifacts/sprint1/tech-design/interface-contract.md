# 接口对齐文档：Saleor 3.23 主商业链路统一合同

版本：v1（2026-10-14）
责任：后端技术设计
依据：后端技术设计 v1，backend-design.md
修订：首次交付；本阶段未实施。接口编号发布后稳定，不重排不复用。

## 1. 通用约定

- 入口沿用 Core `/graphql/`（部署域配置），Query/Mutation/Subscription 三根；SDL唯一目标为 `target-schema.graphql`，给定Base为Core3.22.0，不取未来schema。文档里的片段由目标SDL逐字段抽出，是定位用子集而非另一个可部署schema；完整定义始终在目标文件。
- 认证沿用Saleor JWT/App bearer与合法checkout capability。ID为Relay type+pk、UUID/token和channel slug各自类型，不能互换。id/token别名只能给一个；typed globalID解码/type匹配先于查对象。无权限FORBIDDEN，不返回成功empty；合法不存在single null、合法connectionempty与非法input不同。
- 默认失败层：transportfailure无业务结果；parse/validation/coercion标准GraphQLerrors；业务mutationerrors(field/code/message)；异步accepted/pending不代表completed。错误可脱敏，未知错误INTERNAL_ERROR不得吞。权限层不回敏感参数/余额/identity。mutation成功必须payload存在、errors=[]及需要的result存在，不能仅HTTP200或data非null。
- Relay连接first/last=1..100且互斥，无pagination默认20，显式null/负/越界/非法cursor明错。列表与元素nullability逐接口说明；空[]仅合法没有数据。cursor是绑定query/sort/scope的opaque值，不能跨上下文复用。同静态数据顺序有pk tie-break；更新导致无效游标可明确从第一页重启，不假称跨多页永久快照。
- Money只用有限Decimal+currencyquantize，不用浮点累计。输入PositiveDecimal标量≥0，但移动资金动作要求>0。金额动作runtime非空idempotencykey、scope/key唯一和inputhash冲突，PSP用同稳定key；schema兼容可选参数不是免除幂等要求。查询不会移动资金，只有明确legacyexportmutation写Job。
- 更新省略保留，显式null按字段清除或INVALID，绝不忽略坏项继续部分写。配置expectedrevision新Dashboard必发，旧client省略仍原子但无optimistic保护。所有worker/事件也受同资格、对象/字段scope。一次businesscomplete只有一次logicalevent，网络重送仍可能多次到达，消费按eventID去重。
- 非GraphQLnative边界见I15/I16/I17/I18/I19及interfaces文件。没有新增gRPC。除目录/表单与eventID扩展外，同步税/配送/PSP服务合同字段不改，沿给定Base，不编造新服务地址。

## 2. 接口契约

### I01 · 显式重算结账配送
- 所属设计单元：BD01
- 提供方：saleor / saleor/graphql/checkout/schema.py；拟新增 mutations/checkout_shipping_refresh.py::CheckoutShippingRefresh
- 调用方：外部 Storefront，合法 checkout 持有人或有 MANAGE_CHECKOUTS 的员工/App
- 目标定义：target-schema.graphql：`Mutation.checkoutShippingRefresh`；`CheckoutShippingRefresh`

```graphql
type Mutation {
  checkoutShippingRefresh(id: ID!): CheckoutShippingRefresh
}

"""
I01: recompute options without assigning or clearing a saved delivery method.
"""
type CheckoutShippingRefresh {
  checkout: Checkout
  shippingMethods: [ShippingMethod!]!
  collectionPoints: [Warehouse!]!
  deliveryMethod: DeliveryMethod
  selectedMethodValid: Boolean!
  calculatedAt: DateTime!
  errors: [CheckoutError!]!
}
```

- 字段说明：id 是 Checkout Relay ID、不可用 UUID/token 冒充。payload可空；成功 checkout 必有值、errors=[]，shippingMethods/collectionPoints 为非空列表且元素非空，允许合法 []；deliveryMethod 可空是保存的当前选择；selectedMethodValid 是本次事实而非已选即有效；calculatedAt 必填。出错仍返回errors与calculatedAt，选项列表[]但必须按errors解释，不能当合法空。数字商品无需配送时无选择仍 valid。
- 权限：checkout身份/对象与渠道scope先于重算；匿名合法checkout capability沿用现有Storefront合同，不是任意枚举列表权限。税/私人字段按I25另校验，不从错误返回受限配送内容。
- 错误：缺地址 SHIPPING_ADDRESS_NOT_SET/MISSING_ADDRESS_DATA，未知结账 NOT_FOUND，失效上下文 CONFLICT，同步服务 SHIPPING_SERVICE_ERROR，字段按id/shippingAddress；FORBIDDEN标准GraphQL层。未知执行错误 INTERNAL_ERROR，不能转换为成功空选项。
- 完成判定：成功仅说明一次完整、revision一致的选项计算；不分配/清空/保存delivery，不修改业务updatedAt、不产生完成事件。失败不覆盖任何原有效选择。选择和成单必须再走I02，旧不可用项不进可选列表。
- 变更与兼容：Base无显式操作，本轮新增；现有checkout.shippingMethods读取保留但不代替用户触发重算；旧availableShippingMethods/shippingMethod保持弃用读取。

### I02 · 配送选择、完成及旧标识兼容
- 所属设计单元：BD01
- 提供方：saleor / graphql/checkout/mutations/checkout_delivery_method_update.py、checkout_shipping_method_update.py、checkout_complete.py；checkout/complete_checkout.py
- 调用方：外部Storefront；手动/自动完成服务；Dashboard不新建Storefront页面
- 目标定义：target-schema.graphql：`Mutation.checkoutDeliveryMethodUpdate,checkoutShippingMethodUpdate,checkoutComplete`；`Checkout.shippingMethods,deliveryMethod,availableShippingMethods,shippingMethod`；`CheckoutComplete`；`CheckoutErrorCode`

```graphql
type Mutation {
  """
  Updates the delivery method (shipping method or pick up point) of the checkout. Updates the checkout shipping_address for click and collect delivery for a warehouse address. 
  
  Triggers the following webhook events:
  - SHIPPING_LIST_METHODS_FOR_CHECKOUT (sync): Triggered when updating the checkout delivery method with the external one.
  - CHECKOUT_UPDATED (async): A checkout was updated.
  """
  checkoutDeliveryMethodUpdate(
    """Delivery Method ID (`Warehouse` ID or `ShippingMethod` ID)."""
    deliveryMethodId: ID
    """The checkout's ID."""
    id: ID
    """Checkout token."""
    token: UUID @deprecated(reason: "Use `id` instead.")
  ): CheckoutDeliveryMethodUpdate @doc(category: "Checkout") @webhookEventsInfo(asyncEvents: [CHECKOUT_UPDATED], syncEvents: [SHIPPING_LIST_METHODS_FOR_CHECKOUT])
  """
  Updates the shipping method of the checkout.
  
  Triggers the following webhook events:
  - SHIPPING_LIST_METHODS_FOR_CHECKOUT (sync): Triggered when updating the checkout shipping method with the external one.
  - CHECKOUT_UPDATED (async): A checkout was updated.
  """
  checkoutShippingMethodUpdate(
    """The ID of the checkout."""
    checkoutId: ID @deprecated(reason: "Use `id` instead.")
    """The checkout's ID."""
    id: ID
    """Shipping method."""
    shippingMethodId: ID
    """Checkout token."""
    token: UUID @deprecated(reason: "Use `id` instead.")
  ): CheckoutShippingMethodUpdate @doc(category: "Checkout") @webhookEventsInfo(asyncEvents: [CHECKOUT_UPDATED], syncEvents: [SHIPPING_LIST_METHODS_FOR_CHECKOUT]) @deprecated(reason: "Use `checkoutDeliveryMethodUpdate` instead.")
  """
  Completes the checkout. As a result a new order is created. The mutation allows to create the unpaid order when setting `orderSettings.allowUnpaidOrders` for given `Channel` is set to `true`. When `orderSettings.allowUnpaidOrders` is set to `false`, checkout can be completed only when attached `Payment`/`TransactionItem`s fully cover the checkout's total. When processing the checkout with `Payment`, in case of required additional confirmation step like 3D secure, the `confirmationNeeded` flag will be set to True and no order will be created until payment is confirmed with second call of this mutation.
  
  Triggers the following webhook events:
  - SHIPPING_LIST_METHODS_FOR_CHECKOUT (sync): Optionally triggered when cached external shipping methods are invalid.
  - CHECKOUT_FILTER_SHIPPING_METHODS (sync): Optionally triggered when cached filtered shipping methods are invalid.
  - CHECKOUT_CALCULATE_TAXES (sync): Optionally triggered when checkout prices are expired.
  - ORDER_CREATED (async): Triggered when order is created.
  - NOTIFY_USER (async): A notification for order placement.
  - NOTIFY_USER (async): A staff notification for order placement.
  - ORDER_UPDATED (async): Triggered when order received the update after placement.
  - ORDER_PAID (async): Triggered when newly created order is paid.
  - ORDER_FULLY_PAID (async): Triggered when newly created order is fully paid.
  - ORDER_CONFIRMED (async): Optionally triggered when newly created order are automatically marked as confirmed.
  """
  checkoutComplete(
    """The ID of the checkout."""
    checkoutId: ID @deprecated(reason: "Use `id` instead.")
    """The checkout's ID."""
    id: ID
    """
    Fields required to update the checkout metadata. Can be read by any API client authorized to read the object it's attached to.
    
    Warning: never store sensitive information, including financial data such as credit card details.
    """
    metadata: [MetadataInput!]
    """Client-side generated data required to finalize the payment."""
    paymentData: JSONString
    """
    URL of a view where users should be redirected to see the order details. URL in RFC 1808 format.
    """
    redirectUrl: String
    """Determines whether to store the payment source for future usage."""
    storeSource: Boolean = false @deprecated(reason: "Use checkoutPaymentCreate for this action.")
    """Checkout token."""
    token: UUID @deprecated(reason: "Use `id` instead.")
  ): CheckoutComplete @doc(category: "Checkout") @webhookEventsInfo(asyncEvents: [ORDER_CREATED, NOTIFY_USER, NOTIFY_USER, ORDER_UPDATED, ORDER_PAID, ORDER_FULLY_PAID, ORDER_CONFIRMED], syncEvents: [SHIPPING_LIST_METHODS_FOR_CHECKOUT, CHECKOUT_FILTER_SHIPPING_METHODS, CHECKOUT_CALCULATE_TAXES])
}

type Checkout {
  """
  Shipping methods that can be used with this checkout.
  
  Triggers the following webhook events:
  - SHIPPING_LIST_METHODS_FOR_CHECKOUT (sync): Optionally triggered when cached external shipping methods are invalid.
  - CHECKOUT_FILTER_SHIPPING_METHODS (sync): Optionally triggered when cached filtered shipping methods are invalid.
  """
  shippingMethods: [ShippingMethod!]! @webhookEventsInfo(asyncEvents: [], syncEvents: [SHIPPING_LIST_METHODS_FOR_CHECKOUT, CHECKOUT_FILTER_SHIPPING_METHODS])
  """
  The delivery method selected for this checkout.
  
  Triggers the following webhook events:
  - SHIPPING_LIST_METHODS_FOR_CHECKOUT (sync): Optionally triggered when cached external shipping methods are invalid.
  - CHECKOUT_FILTER_SHIPPING_METHODS (sync): Optionally triggered when cached filtered shipping methods are invalid.
  """
  deliveryMethod: DeliveryMethod @webhookEventsInfo(asyncEvents: [], syncEvents: [SHIPPING_LIST_METHODS_FOR_CHECKOUT, CHECKOUT_FILTER_SHIPPING_METHODS])
  """
  Shipping methods that can be used with this checkout.
  
  Triggers the following webhook events:
  - SHIPPING_LIST_METHODS_FOR_CHECKOUT (sync): Optionally triggered when cached external shipping methods are invalid.
  - CHECKOUT_FILTER_SHIPPING_METHODS (sync): Optionally triggered when cached filtered shipping methods are invalid.
  """
  availableShippingMethods: [ShippingMethod!]! @webhookEventsInfo(asyncEvents: [], syncEvents: [SHIPPING_LIST_METHODS_FOR_CHECKOUT, CHECKOUT_FILTER_SHIPPING_METHODS]) @deprecated(reason: "Use `shippingMethods` instead.")
  """
  The shipping method related with checkout.
  
  Triggers the following webhook events:
  - SHIPPING_LIST_METHODS_FOR_CHECKOUT (sync): Optionally triggered when cached external shipping methods are invalid.
  - CHECKOUT_FILTER_SHIPPING_METHODS (sync): Optionally triggered when cached filtered shipping methods are invalid.
  """
  shippingMethod: ShippingMethod @webhookEventsInfo(asyncEvents: [], syncEvents: [SHIPPING_LIST_METHODS_FOR_CHECKOUT, CHECKOUT_FILTER_SHIPPING_METHODS]) @deprecated(reason: "Use `deliveryMethod` instead.")
}

"""
Completes the checkout. As a result a new order is created. The mutation allows to create the unpaid order when setting `orderSettings.allowUnpaidOrders` for given `Channel` is set to `true`. When `orderSettings.allowUnpaidOrders` is set to `false`, checkout can be completed only when attached `Payment`/`TransactionItem`s fully cover the checkout's total. When processing the checkout with `Payment`, in case of required additional confirmation step like 3D secure, the `confirmationNeeded` flag will be set to True and no order will be created until payment is confirmed with second call of this mutation.

Triggers the following webhook events:
- SHIPPING_LIST_METHODS_FOR_CHECKOUT (sync): Optionally triggered when cached external shipping methods are invalid.
- CHECKOUT_FILTER_SHIPPING_METHODS (sync): Optionally triggered when cached filtered shipping methods are invalid.
- CHECKOUT_CALCULATE_TAXES (sync): Optionally triggered when checkout prices are expired.
- ORDER_CREATED (async): Triggered when order is created.
- NOTIFY_USER (async): A notification for order placement.
- NOTIFY_USER (async): A staff notification for order placement.
- ORDER_UPDATED (async): Triggered when order received the update after placement.
- ORDER_PAID (async): Triggered when newly created order is paid.
- ORDER_FULLY_PAID (async): Triggered when newly created order is fully paid.
- ORDER_CONFIRMED (async): Optionally triggered when newly created order are automatically marked as confirmed.
"""
type CheckoutComplete @doc(category: "Checkout") @webhookEventsInfo(asyncEvents: [ORDER_CREATED, NOTIFY_USER, NOTIFY_USER, ORDER_UPDATED, ORDER_PAID, ORDER_FULLY_PAID, ORDER_CONFIRMED], syncEvents: [SHIPPING_LIST_METHODS_FOR_CHECKOUT, CHECKOUT_FILTER_SHIPPING_METHODS, CHECKOUT_CALCULATE_TAXES]) {
  """Placed order."""
  order: Order
  """
  Set to true if payment needs to be confirmed before checkout is complete.
  """
  confirmationNeeded: Boolean!
  """Confirmation data used to process additional authorization steps."""
  confirmationData: JSONString
  checkoutErrors: [CheckoutError!]! @deprecated(reason: "Use `errors` field instead.")
  errors: [CheckoutError!]!
}

enum CheckoutErrorCode @doc(category: "Checkout") {
  BILLING_ADDRESS_NOT_SET
  CHECKOUT_NOT_FULLY_PAID
  GRAPHQL_ERROR
  PRODUCT_NOT_PUBLISHED
  PRODUCT_UNAVAILABLE_FOR_PURCHASE
  INSUFFICIENT_STOCK
  INVALID
  INVALID_SHIPPING_METHOD
  NOT_FOUND
  PAYMENT_ERROR
  QUANTITY_GREATER_THAN_LIMIT
  REQUIRED
  SHIPPING_ADDRESS_NOT_SET
  SHIPPING_METHOD_NOT_APPLICABLE
  DELIVERY_METHOD_NOT_APPLICABLE
  SHIPPING_METHOD_NOT_SET
  SHIPPING_NOT_REQUIRED
  TAX_ERROR
  UNIQUE
  VOUCHER_NOT_APPLICABLE
  GIFT_CARD_NOT_APPLICABLE
  ZERO_QUANTITY
  MISSING_CHANNEL_SLUG
  CHANNEL_INACTIVE
  UNAVAILABLE_VARIANT_IN_CHANNEL
  EMAIL_NOT_SET
  NO_LINES
  INACTIVE_PAYMENT
  NON_EDITABLE_GIFT_LINE
  NON_REMOVABLE_GIFT_LINE
  SHIPPING_CHANGE_FORBIDDEN
  MISSING_ADDRESS_DATA
  DELIVERY_METHOD_EXPIRED
  SHIPPING_SERVICE_ERROR
  CONFLICT
  UNSUPPORTED_PAYMENT_METHOD
}
```

- 字段说明：id/token/checkoutId 每个支持入口必须且只能给一个定位参数（deprecated别名仍类型检查），id是Relay、token为UUID；deliveryMethodId 可null用于清选择，只在对应行为允许时，omitted不代替选择。支持ShippingMethod、Warehouse与合法外部App ID，各自当前上下文解析。CheckoutComplete.order 可空、confirmationNeeded 非空，errors非空列表。
- 权限：当前checkout对象持有人/有权管理身份，method不得越当前channel和地址上下文；无权错误不回传受限方法。自动worker使用已授权服务上下文但仍执行所有业务validator，不能假员工放宽资格。
- 错误：INVALID/NOT_FOUND、DELIVERY_METHOD_NOT_APPLICABLE、DELIVERY_METHOD_EXPIRED、SHIPPING_METHOD_NOT_SET、CHANNEL_INACTIVE、INSUFFICIENT_STOCK、PAYMENT_ERROR/TAX_ERROR及现行CheckoutErrorCode；id/token多/缺参数 INVALID/REQUIRED。错误定位配送、地址或支付字段，失败不留下半订单。
- 完成判定：选择更新只有当前有效时原子保存；完成必须当前资金/商品/地址/配送/库存资格全部通过，order实际持久存在才complete。confirmationNeeded=true只表示需客户动作，不是已完成；自动化不能依此生成成功。相同checkout返回唯一旧结果，不重扣、不重复逻辑事件；PSP未知用I08命令对账，不凭DB回滚认为未扣款。
- 变更与兼容：保留旧shipping标识/选择mutation与deprecatedread，不放宽归属；新增错误分支。新客户端使用deliveryMethod/update与id。

### I03 · 渠道库存资格与跨入口库存语义
- 所属设计单元：BD02
- 提供方：saleor / graphql/channel/types.py、mutations/channel_create.py；warehouse/availability.py 与 product/utils/availability.py（统一资格方法拟新增）
- 调用方：FD01及外部商品/checkout/order/fulfillment/draft消费者
- 目标定义：target-schema.graphql：`StockAvailabilityStrategyEnum`；`StockSettings`；`StockSettingsInput`

```graphql
"""I03: warehouse eligibility, independent from allocation ordering."""
enum StockAvailabilityStrategyEnum {
  LEGACY
  CHANNEL_WAREHOUSES
}

"""Represents the channel stock settings."""
type StockSettings @doc(category: "Products") {
  """
  Allocation strategy defines the preference of warehouses for allocations and reservations.
  """
  allocationStrategy: AllocationStrategyEnum!
  availabilityStrategy: StockAvailabilityStrategyEnum!
}

input StockSettingsInput @doc(category: "Products") {
  """
  Allocation strategy options. Strategy defines the preference of warehouses for allocations and reservations.
  """
  allocationStrategy: AllocationStrategyEnum
  availabilityStrategy: StockAvailabilityStrategyEnum
}
```

- 字段说明：availabilityStrategy输出非空，LEGACY默认，新/历史渠道均保持旧资格；CHANNEL_WAREHOUSES只计算直连集合；allocationStrategy输入由必填收紧改为可选，使仅改资格不必重复提交排序。两输入省略保留（创建用安全默认），显式null拒绝INVALID，空settings对象合法不改。输出两策略都非空。
- 权限：读取/配置按MANAGE_CHANNELS及对象scope；库存公开可售值按现行product查询可见性，管理仓库明细权限不因公开库存返回放宽。
- 错误：ChannelError INVALID/CONFLICT/NOT_FOUND；下游不足沿既有INSUFFICIENT_STOCK、仓库/variant字段错误；无权FORBIDDEN。
- 完成判定：保存后的设置重新读一致；product查询、checkout reservation、draft/order allocation、fulfillment新增分配共用集合/剩余值。不足整体回滚，无部分reservation/oversell。关系更改与下单共channel锁/revision，历史allocation不擅自重写。
- 变更与兼容：旧地址/country参数仍接受；仅CHANNEL_WAREHOUSES下不改变资格集合，仍有独立shipping可达性。LEGACY未切换旧行为不变。

### I04 · 商品按渠道可售诊断分页
- 所属设计单元：BD03
- 提供方：saleor / graphql/product/schema.py；拟新增 diagnostics resolver/types
- 调用方：FD02 / ProductUpdate ChannelsAvailabilityCard
- 目标定义：target-schema.graphql：`Query.productAvailabilityDiagnostics`；`ProductAvailabilityDiagnosticFilterInput`；`ProductAvailabilityDiagnostic`；`ProductAvailabilityCheck`；`ProductAvailabilityDiagnosticConnection`；`AvailabilityCheckSeverityEnum`；`AvailabilityCheckCodeEnum`

```graphql
type Query {
  productAvailabilityDiagnostics(id: ID!, filter: ProductAvailabilityDiagnosticFilterInput, before: String, after: String, first: Int, last: Int): ProductAvailabilityDiagnosticConnection
}

input ProductAvailabilityDiagnosticFilterInput {
  search: String
  channelIds: [ID!]
}

type ProductAvailabilityDiagnostic {
  channel: Channel!
  evaluatedAt: DateTime!
  isAvailable: Boolean!
  blockingCount: Int!
  warningCount: Int!
  checks: [ProductAvailabilityCheck!]!
}

type ProductAvailabilityCheck {
  code: AvailabilityCheckCodeEnum!
  severity: AvailabilityCheckSeverityEnum!
  message: String!
  variantId: ID
}

type ProductAvailabilityDiagnosticConnection {
  pageInfo: PageInfo!
  edges: [ProductAvailabilityDiagnosticEdge!]!
  totalCount: Int!
}

enum AvailabilityCheckSeverityEnum {
  PASS
  BLOCKING
  WARNING
  NOT_APPLICABLE
}

enum AvailabilityCheckCodeEnum {
  CHANNEL_INACTIVE
  PRODUCT_NOT_PUBLISHED
  PURCHASE_NOT_AVAILABLE
  NO_VARIANTS
  VARIANT_NOT_AVAILABLE
  NO_WAREHOUSES
  INSUFFICIENT_STOCK
  SHIPPING_ZONE_UNAVAILABLE
}
```

- 字段说明：id是Product Relay ID必填。filter省略所有可见渠道，search按name/currency不区分大小写；channelIds []是空集合。connection可空表示错误/不存在，合法empty edges=[]，edges/node不含null；totalCount同scope，channelname+pk序；severity=PASS/BLOCKING/WARNING/NOT_APPLICABLE，counts只计对应错误/警告，不将NOT_APPLICABLE算通过数。
- 权限：MANAGE_PRODUCTS和当前product/channel可见scope。不能将权限拒绝或受限渠道返回为“不可售问题”。
- 错误：GraphQL BAD_USER_INPUT（search/pagination/type/cursor），FORBIDDEN，NOT_FOUND，INTERNAL_ERROR；不是mutationerrors形状。message只含允许原因，不泄露受限warehouse/stock。
- 完成判定：只读已保存事实，evaluatedAt明确；未保存编辑不能使server诊断成为当前输入结论。数字商品仅shipping NOT_APPLICABLE，其他核心检查正常。查询失败不保留假最新结论。
- 变更与兼容：新增独立连接，不改变Product.channelListings既有列表；前端停止本地重复库存算法。

### I05 · 自动完成设置、单位及保存冲突
- 所属设计单元：BD04
- 提供方：saleor / channel/models.py、graphql/channel/types.py、mutations/channel_create.py/channel_update.py（新增字段与revision）
- 调用方：FD01 ChannelForm及有权配置集成App
- 目标定义：target-schema.graphql：`CheckoutSettings`；`CheckoutSettingsInput`；`Channel.settingsRevision`；`ChannelUpdateInput.expectedSettingsRevision`；`ChannelErrorCode`

```graphql
"""Represents the channel-specific checkout settings."""
type CheckoutSettings {
  """
  Default `true`. Determines if the checkout mutations should use legacy error flow. In legacy flow, all mutations can raise an exception unrelated to the requested action - (e.g. out-of-stock exception when updating checkoutShippingAddress.) If `false`, the errors will be aggregated in `checkout.problems` field. Some of the `problems` can block the finalizing checkout process. The legacy flow will be removed in Saleor 4.0. The flow with `checkout.problems` will be the default one.
  """
  useLegacyErrorFlow: Boolean!
  """
  I05: enable supported fully authorized/charged Transaction and compatible Payment flows. Saving this flag does not complete checkouts.
  """
  automaticallyCompleteFullyPaidCheckouts: Boolean!
  """
  I05: nonnegative minutes, 0..10080. Eligibility requires now - checkout.updatedAt > delay. New channels and migrated channels use 0 unless explicitly configured.
  """
  automaticCompletionDelay: Minute!
  """
  I05: nullable inclusive lower bound on checkout creation time. Null means no lower bound; this is not a task stop time.
  """
  automaticCompletionCutoff: DateTime
}

input CheckoutSettingsInput @doc(category: "Checkout") {
  """
  Default `true`. Determines if the checkout mutations should use legacy error flow. In legacy flow, all mutations can raise an exception unrelated to the requested action - (e.g. out-of-stock exception when updating checkoutShippingAddress.) If `false`, the errors will be aggregated in `checkout.problems` field. Some of the `problems` can block the finalizing checkout process. The legacy flow will be removed in Saleor 4.0. The flow with `checkout.problems` will be the default one.
  """
  useLegacyErrorFlow: Boolean @deprecated
  """
  I05: enable supported fully authorized/charged Transaction and compatible Payment flows. Omission preserves the current value.
  """
  automaticallyCompleteFullyPaidCheckouts: Boolean
  automaticCompletionDelay: Minute
  automaticCompletionCutoff: DateTime
}

type Channel {
  settingsRevision: String!
}

input ChannelUpdateInput {
  expectedSettingsRevision: String
}

enum ChannelErrorCode @doc(category: "Channels") {
  ALREADY_EXISTS
  GRAPHQL_ERROR
  INVALID
  NOT_FOUND
  REQUIRED
  UNIQUE
  CHANNELS_CURRENCY_MUST_BE_THE_SAME
  CHANNEL_WITH_ORDERS
  DUPLICATED_INPUT_ITEM
  CONFLICT
}
```

- 字段说明：automaticCompletionDelay为Minute，0..10080（技术选择），新/迁移默认0；输出必填。cutoff DateTime可空，null=不限creation下界，省略更新保留；delay null非法，开关省略保留。future cutoff允许，closing开关不清参数。now-lastChange>delay且created>=cutoff才候选，等delay不选、等cutoff选。revision为不透明string，不自行算+1。
- 权限：MANAGE_CHANNELS与目标scope；不得用更新warehouse等入口绕过。
- 错误：INVALID/REQUIRED（非法单位/范围/值）、CONFLICT（expectedSettingsRevision不匹配），forbidden标准层；所有设置字段同事务，错误保留上一生效值。
- 完成判定：channelUpdate errors=[]且channel包含新值/revision仅说明保存；不表示任务发现/订单生成。客户端保存后读writer/current事实；实际执行I06。
- 变更与兼容：旧false不变、旧true以0延迟/nullcutoff保留旧无额外静默期行为。旧客户端省略expected revision仍原子last-write，不享乐观冲突；新Dashboard必发并明确冲突合并。

### I06 · 已支付结账自动完成状态与结果
- 所属设计单元：BD05
- 提供方：saleor / checkout/tasks.py、complete_checkout.py；拟新增 CheckoutCompletion模型和 graphql/checkout completion status resolver
- 调用方：FD01/FD03按业务上下文展示；Storefront及checkout管理App
- 目标定义：target-schema.graphql：`Query.checkoutCompletionStatus`；`CheckoutCompletionStatus`；`CheckoutCompletionStatusEnum`

```graphql
type Query {
  checkoutCompletionStatus(id: ID!): CheckoutCompletionStatus
}

"""
I06: durable completion result; the checkout may already have been deleted.
"""
type CheckoutCompletionStatus {
  status: CheckoutCompletionStatusEnum!
  order: Order
  lastAttemptAt: DateTime
  nextAttemptAt: DateTime
  errorCode: CheckoutErrorCode
  errorField: String
}

enum CheckoutCompletionStatusEnum {
  DISABLED
  WAITING
  PROCESSING
  BLOCKED
  RETRYING
  COMPLETED
}
```

- 字段说明：id必填Checkout Relay ID；持久completion记录与checkout token绑定，checkout删除后仍能查COMPLETED及order。order可空只在尚未完成；completed必须order有值。lastAttempt/nextAttempt/errorField/errorCode可空表示未尝试/无需安排/没有错误。status有DISABLED/WAITING/PROCESSING/BLOCKED/RETRYING/COMPLETED，不等同支付status。
- 权限：原checkout持有人/合法capability、MANAGE_CHECKOUTS对应channel或允许相关order身份；已完成时继承order对象scope，记录不能泄露他人的order。
- 错误：非法ID与cursor语义按I23；无权FORBIDDEN，合法不存在返回null；错误code只来自CheckoutErrorCode，不包含token/余额/用户资料。
- 完成判定：batchscan+eventhint共同发现候选，延迟/下界/足额与所有资格再查。Transaction fullcharge/fullauth与兼容Payment支持矩阵见backend BD05；pending/challenge/不受支持provider不成单。持久锁+providercommand+outbox保证一个order、一个逻辑完成通知；修复BLOCKED再试不重复钱。扫描周期/批大小不在API承诺。
- 变更与兼容：Base无状态查询，新增；原开关与单task保留为调度入口，不假称原任务已满足批次/时间。

### I07 · 礼品卡交易、余额及事件
- 所属设计单元：BD06
- 提供方：saleor / giftcard/models.py；拟新增 giftcard ledger service、graphql/payment gift_card_transaction_initialize.py；既有transaction动作分派
- 调用方：外部Storefront合法checkout持有人；FD03读取/有权售后；支付/礼品卡管理App
- 目标定义：target-schema.graphql：`Mutation.giftCardTransactionInitialize`；`GiftCardTransactionInitializeInput`；`GiftCardTransactionInitialize`；`GiftCardTransactionError`；`GiftCardTransactionErrorCode`；`GiftCard.authorizedBalance,availableBalance`；`GiftCardEvent.transactionId,amount`；`GiftCardEventsEnum`；`GiftCardPaymentMethodDetails`；`PaymentMethodTypeEnum`

```graphql
type Mutation {
  giftCardTransactionInitialize(input: GiftCardTransactionInitializeInput!): GiftCardTransactionInitialize
}

input GiftCardTransactionInitializeInput {
  id: ID!
  code: String!
  amount: PositiveDecimal!
  action: TransactionFlowStrategyEnum!
  idempotencyKey: String!
}

type GiftCardTransactionInitialize {
  transaction: TransactionItem
  transactionEvent: TransactionEvent
  giftCard: GiftCard
  errors: [GiftCardTransactionError!]!
}

type GiftCardTransactionError {
  field: String
  message: String
  code: GiftCardTransactionErrorCode!
}

enum GiftCardTransactionErrorCode {
  GRAPHQL_ERROR
  INVALID
  REQUIRED
  NOT_FOUND
  INACTIVE
  EXPIRED
  CURRENCY_MISMATCH
  INSUFFICIENT_FUNDS
  CONFLICT
  UNIQUE
}

type GiftCard {
  authorizedBalance: Money!
  availableBalance: Money!
}

type GiftCardEvent {
  transactionId: ID
  amount: Money
}

enum GiftCardEventsEnum @doc(category: "Gift cards") {
  ISSUED
  BOUGHT
  UPDATED
  ACTIVATED
  DEACTIVATED
  BALANCE_RESET
  EXPIRY_DATE_UPDATED
  TAGS_UPDATED
  SENT_TO_CUSTOMER
  RESENT
  NOTE_ADDED
  USED_IN_ORDER
  TRANSACTION_INITIALIZED
  AUTHORIZED
  AUTHORIZATION_CANCELED
  CHARGED
  REFUNDED
}

type GiftCardPaymentMethodDetails implements PaymentMethodDetails {
  name: String!
  last4: String!
  giftCardId: ID!
}

"""
Represents possible payment method types.

    The following types are possible:
    CARD - represents a card payment method.
    OTHER - represents any payment method that is not a card payment.
"""
enum PaymentMethodTypeEnum @doc(category: "Payments") {
  CARD
  OTHER
  GIFT_CARD
}
```

- 字段说明：目标id为Checkout或Order Relay ID；code必填非空8..16字符沿卡格式，amount PositiveDecimal动作必须>0且币种quantize，action明确AUTHORIZATION/CHARGE，key必填非空≤512。初始化与auth/charge同原子结果。GiftCard.currentBalance是账面余额，authorizedBalance占用，availableBalance=current−hold；非空Money。event.transactionId/amount可空仅旧非交易事件；events沿原非空列表允许[]。methoddetails只name/last4/giftCardId，不有fullcode。
- 权限：checkout初始化须当前合法checkout capability/身份；order初始化管理支付需MANAGE_ORDERS+HANDLE_PAYMENTS，卡管理读MANAGE_GIFT_CARD或匹配持卡场景。不因猜code取得全卡资料。客户仅自己的checkout授权CANCEL例外，不可order退款。
- 错误：NOT_FOUND/INACTIVE/EXPIRED/CURRENCY_MISMATCH/INSUFFICIENT_FUNDS/INVALID/CONFLICT/UNIQUE，field指input.code/amount/id/key；权限先验，不回显余额或卡code。非法卡统一限流/安全响应。
- 完成判定：同目标/card/action/amount/key重放唯一transaction/event，book/hold/cardevent/transactionstate一起落库。授权占hold不扣book；charge消耗hold且book减，cancel只释放hold；orderrefund可退额内book加。同transactionRequestAction CHARGE/CANCEL/REFUND走内置ledger，无外部webhook，不失败改普通支付。
- 变更与兼容：历史giftcard discount/USED_IN_ORDER保存不重扣/重算；checkoutAddPromoCode/remove旧礼品卡写法受同ledger适配去重。新订单giftcard为资金而非discount，Dashboard用I08 summary。

### I08 · 统一金额摘要、可操作额与资金幂等
- 所属设计单元：BD07
- 提供方：saleor / payment/models.py、transaction_item_calculations.py、gateway.py、order/utils.py；graphql/payment/mutations/payment与transaction、graphql/order/mutations；拟新增PaymentCommand/source投影
- 调用方：FD03；有订单/支付权限员工/App；PSP事件报告App
- 目标定义：target-schema.graphql：`Order.paymentSummary`；`OrderPaymentSummary`；`TransactionItem.availableCaptureAmount,availableRefundAmount`；`Mutation.transactionInitialize,transactionRequestAction,transactionRequestRefundForGrantedRefund,paymentCapture,paymentRefund,paymentVoid,orderCapture,orderRefund,orderVoid,orderMarkAsPaid,transactionCreate,transactionUpdate,transactionProcess,transactionEventReport`；`TransactionRequestActionErrorCode`；`TransactionRequestRefundForGrantedRefundErrorCode`

```graphql
type Order {
  paymentSummary: OrderPaymentSummary!
}

"""
I08: all amounts use order currency; remainingDue is max(-totalBalance, 0).
"""
type OrderPaymentSummary {
  totalPayable: Money!
  netCharged: Money!
  successfulCharged: Money!
  authorized: Money!
  refunded: Money!
  chargePending: Money!
  refundPending: Money!
  grantedRefund: Money!
  giftCardCharged: Money!
  legacyGiftCardDiscount: Money!
  totalBalance: Money!
  remainingDue: Money!
}

type TransactionItem {
  availableCaptureAmount: Money!
  availableRefundAmount: Money!
}

type Mutation {
  """
  Initializes a transaction session. It triggers the webhook `TRANSACTION_INITIALIZE_SESSION`, to the requested `paymentGateways`. There is a limit of 100 transaction items per checkout / order.
  """
  transactionInitialize(
    """
    The expected action called for the transaction. By default, the `channel.paymentSettings.defaultTransactionFlowStrategy` will be used.The field can be used only by app that has `HANDLE_PAYMENTS` permission.
    """
    action: TransactionFlowStrategyEnum
    """
    The amount requested for initializing the payment gateway. If not provided, the difference between checkout.total - transactions that are already processed will be send.
    """
    amount: PositiveDecimal
    """
    The customer's IP address. If not provided Saleor will try to determine the customer's IP address on its own. The customer's IP address will be passed to the payment app. The IP should be in ipv4 or ipv6 format. The field can be used only by an app that has `HANDLE_PAYMENTS` permission.
    """
    customerIpAddress: String
    """The ID of the checkout or order."""
    id: ID!
    """
    The idempotency key assigned to the action. It will be passed to the payment app to discover potential duplicate actions. If not provided, the default one will be generated. If empty string provided, INVALID error code will be raised.
    """
    idempotencyKey: String
    """Payment gateway used to initialize the transaction."""
    paymentGateway: PaymentGatewayToInitialize!
  ): TransactionInitialize @doc(category: "Payments")
  """
  Request an action for payment transaction. 
  
  I08: order-linked funds actions require both MANAGE_ORDERS and HANDLE_PAYMENTS plus object/channel scope; checkout actions require the corresponding checkout scope. Only cancellation of the caller-owned gift-card checkout authorization is exempt from staff payments management.
  
  I08: a nonempty idempotencyKey is required at execution for money-moving commands; same principal/key and identical normalized input replay the original result. Conflicting reuse returns a typed error. Event reports may use the stable PSP reference plus event type as their legacy replay key.
  """
  transactionRequestAction(
    """Determines the action type."""
    actionType: TransactionActionEnum!
    """
    Transaction request amount. If empty, maximal possible amount will be used.
    """
    amount: PositiveDecimal
    """The ID of the transaction. One of field id or token is required."""
    id: ID
    """
    Reason of the refund
    
    Added in Saleor 3.22.
    """
    refundReason: String
    """
    ID of a `Page` (Model) to reference in reason.
    
    Added in Saleor 3.22.
    """
    refundReasonReference: ID
    """The token of the transaction. One of field id or token is required."""
    token: UUID
    idempotencyKey: String
  ): TransactionRequestAction @doc(category: "Payments")
  """
  Request a refund for payment transaction based on granted refund. 
  
  I08: order-linked funds actions require both MANAGE_ORDERS and HANDLE_PAYMENTS plus object/channel scope; checkout actions require the corresponding checkout scope. Only cancellation of the caller-owned gift-card checkout authorization is exempt from staff payments management.
  
  I08: a nonempty idempotencyKey is required at execution for money-moving commands; same principal/key and identical normalized input replay the original result. Conflicting reuse returns a typed error. Event reports may use the stable PSP reference plus event type as their legacy replay key.
  """
  transactionRequestRefundForGrantedRefund(
    """The ID of the granted refund."""
    grantedRefundId: ID!
    """
    The ID of the transaction. One of field id or token is required, if `transactionItem` is not already assigned to the `orderGrantedRefund`. If `transactionItem` is already assigned to the grantedRefund the field will be ignored.
    """
    id: ID
    """
    The token of the transaction. One of field id or token is required, if `transactionItem` is not already assigned to the `orderGrantedRefund`. If `transactionItem` is already assigned to the grantedRefund the field will be ignored.
    """
    token: UUID
    idempotencyKey: String
  ): TransactionRequestRefundForGrantedRefund @doc(category: "Payments")
  """
  Captures the authorized payment amount. 
  
  I08: order-linked funds actions require both MANAGE_ORDERS and HANDLE_PAYMENTS plus object/channel scope; checkout actions require the corresponding checkout scope. Only cancellation of the caller-owned gift-card checkout authorization is exempt from staff payments management.
  
  I08: a nonempty idempotencyKey is required at execution for money-moving commands; same principal/key and identical normalized input replay the original result. Conflicting reuse returns a typed error. Event reports may use the stable PSP reference plus event type as their legacy replay key.
  """
  paymentCapture(
    """Transaction amount."""
    amount: PositiveDecimal
    """Payment ID."""
    paymentId: ID!
    idempotencyKey: String
  ): PaymentCapture @doc(category: "Payments")
  """
  Refunds the captured payment amount. 
  
  I08: order-linked funds actions require both MANAGE_ORDERS and HANDLE_PAYMENTS plus object/channel scope; checkout actions require the corresponding checkout scope. Only cancellation of the caller-owned gift-card checkout authorization is exempt from staff payments management.
  
  I08: a nonempty idempotencyKey is required at execution for money-moving commands; same principal/key and identical normalized input replay the original result. Conflicting reuse returns a typed error. Event reports may use the stable PSP reference plus event type as their legacy replay key.
  """
  paymentRefund(
    """Transaction amount."""
    amount: PositiveDecimal
    """Payment ID."""
    paymentId: ID!
    idempotencyKey: String
  ): PaymentRefund @doc(category: "Payments")
  """
  Voids the authorized payment. 
  
  I08: order-linked funds actions require both MANAGE_ORDERS and HANDLE_PAYMENTS plus object/channel scope; checkout actions require the corresponding checkout scope. Only cancellation of the caller-owned gift-card checkout authorization is exempt from staff payments management.
  
  I08: a nonempty idempotencyKey is required at execution for money-moving commands; same principal/key and identical normalized input replay the original result. Conflicting reuse returns a typed error. Event reports may use the stable PSP reference plus event type as their legacy replay key.
  """
  paymentVoid(
    """Payment ID."""
    paymentId: ID!
    idempotencyKey: String
  ): PaymentVoid @doc(category: "Payments")
  """
  Capture an order. 
  
  I08: order-linked funds actions require both MANAGE_ORDERS and HANDLE_PAYMENTS plus object/channel scope; checkout actions require the corresponding checkout scope. Only cancellation of the caller-owned gift-card checkout authorization is exempt from staff payments management.
  
  I08: a nonempty idempotencyKey is required at execution for money-moving commands; same principal/key and identical normalized input replay the original result. Conflicting reuse returns a typed error. Event reports may use the stable PSP reference plus event type as their legacy replay key.
  """
  orderCapture(
    """Amount of money to capture."""
    amount: PositiveDecimal!
    """ID of the order to capture."""
    id: ID!
    idempotencyKey: String
  ): OrderCapture @doc(category: "Orders")
  """
  Refund an order. 
  
  I08: order-linked funds actions require both MANAGE_ORDERS and HANDLE_PAYMENTS plus object/channel scope; checkout actions require the corresponding checkout scope. Only cancellation of the caller-owned gift-card checkout authorization is exempt from staff payments management.
  
  I08: a nonempty idempotencyKey is required at execution for money-moving commands; same principal/key and identical normalized input replay the original result. Conflicting reuse returns a typed error. Event reports may use the stable PSP reference plus event type as their legacy replay key.
  """
  orderRefund(
    """Amount of money to refund."""
    amount: PositiveDecimal!
    """ID of the order to refund."""
    id: ID!
    idempotencyKey: String
  ): OrderRefund @doc(category: "Orders")
  """
  Void an order. 
  
  I08: order-linked funds actions require both MANAGE_ORDERS and HANDLE_PAYMENTS plus object/channel scope; checkout actions require the corresponding checkout scope. Only cancellation of the caller-owned gift-card checkout authorization is exempt from staff payments management.
  
  I08: a nonempty idempotencyKey is required at execution for money-moving commands; same principal/key and identical normalized input replay the original result. Conflicting reuse returns a typed error. Event reports may use the stable PSP reference plus event type as their legacy replay key.
  """
  orderVoid(
    """ID of the order to void."""
    id: ID!
    idempotencyKey: String
  ): OrderVoid @doc(category: "Orders")
  """
  Mark order as manually paid. 
  
  I08: order-linked funds actions require both MANAGE_ORDERS and HANDLE_PAYMENTS plus object/channel scope; checkout actions require the corresponding checkout scope. Only cancellation of the caller-owned gift-card checkout authorization is exempt from staff payments management.
  
  I08: a nonempty idempotencyKey is required at execution for money-moving commands; same principal/key and identical normalized input replay the original result. Conflicting reuse returns a typed error. Event reports may use the stable PSP reference plus event type as their legacy replay key.
  """
  orderMarkAsPaid(
    """ID of the order to mark paid."""
    id: ID!
    """The external transaction reference."""
    transactionReference: String
    idempotencyKey: String
  ): OrderMarkAsPaid @doc(category: "Orders")
  """
  Creates transaction for checkout or order. 
  
  Requires one of the following permissions: HANDLE_PAYMENTS.
  
  I08: a nonempty idempotencyKey is required at execution for money-moving commands; same principal/key and identical normalized input replay the original result. Conflicting reuse returns a typed error. Event reports may use the stable PSP reference plus event type as their legacy replay key.
  """
  transactionCreate(
    """The ID of the checkout or order."""
    id: ID!
    """Input data required to create a new transaction object."""
    transaction: TransactionCreateInput!
    """Data that defines a transaction event."""
    transactionEvent: TransactionEventInput
    idempotencyKey: String
  ): TransactionCreate @doc(category: "Payments")
  """
  Update transaction.
  
  Requires the following permissions: OWNER and HANDLE_PAYMENTS for apps, HANDLE_PAYMENTS for staff users. Staff user cannot update a transaction that is owned by the app.
  
  I08: a nonempty idempotencyKey is required at execution for money-moving commands; same principal/key and identical normalized input replay the original result. Conflicting reuse returns a typed error. Event reports may use the stable PSP reference plus event type as their legacy replay key.
  """
  transactionUpdate(
    """The ID of the transaction. One of field id or token is required."""
    id: ID
    """The token of the transaction. One of field id or token is required."""
    token: UUID
    """Input data required to create a new transaction object."""
    transaction: TransactionUpdateInput
    """Data that defines a transaction transaction."""
    transactionEvent: TransactionEventInput
    idempotencyKey: String
  ): TransactionUpdate @doc(category: "Payments")
  """
  Processes a transaction session. It triggers the webhook `TRANSACTION_PROCESS_SESSION`, to the assigned `paymentGateways`.
  
  I08: a nonempty idempotencyKey is required at execution for money-moving commands; same principal/key and identical normalized input replay the original result. Conflicting reuse returns a typed error. Event reports may use the stable PSP reference plus event type as their legacy replay key.
  """
  transactionProcess(
    """
    The customer's IP address. If not provided Saleor will try to determine the customer's IP address on its own. The customer's IP address will be passed to the payment app. The IP should be in ipv4 or ipv6 format. The field can be used only by an app that has `HANDLE_PAYMENTS` permission.
    """
    customerIpAddress: String
    """The data that will be passed to the payment gateway."""
    data: JSON
    """
    The ID of the transaction to process. One of field id or token is required.
    """
    id: ID
    """
    The token of the transaction to process. One of field id or token is required.
    """
    token: UUID
    idempotencyKey: String
  ): TransactionProcess @doc(category: "Payments")
  """
  Report the event for the transaction.
  
  Requires the following permissions: OWNER and HANDLE_PAYMENTS for apps, HANDLE_PAYMENTS for staff users. Staff user cannot update a transaction that is owned by the app.
  
  Triggers the following webhook events:
  - TRANSACTION_ITEM_METADATA_UPDATED (async): Optionally called when transaction's metadata was updated.
  - CHECKOUT_FULLY_PAID (async): Optionally called when the checkout charge status changed to `FULL` or `OVERCHARGED`.
  - ORDER_UPDATED (async): Optionally called when the transaction is related to the order and the order was updated.
  
  I08: a nonempty idempotencyKey is required at execution for money-moving commands; same principal/key and identical normalized input replay the original result. Conflicting reuse returns a typed error. Event reports may use the stable PSP reference plus event type as their legacy replay key.
  """
  transactionEventReport(
    """
    The amount of the event to report. 
    
    Required for all `REQUEST`, `SUCCESS`, `ACTION_REQUIRED`, and `ADJUSTMENT` events. For other events, the amount will be calculated based on the previous events with the same pspReference. If not possible to calculate, the mutation will return an error.
    """
    amount: PositiveDecimal
    """List of all possible actions for the transaction"""
    availableActions: [TransactionActionEnum!]
    """
    The url that will allow to redirect user to payment provider page with event details.
    """
    externalUrl: String
    """The ID of the transaction. One of field id or token is required."""
    id: ID
    """
    The message related to the event. The maximum length is 512 characters; any text exceeding this limit will be truncated.
    """
    message: String
    """
    Details of the payment method used for the transaction.
    
    Added in Saleor 3.22.
    """
    paymentMethodDetails: PaymentMethodDetailsInput
    """PSP Reference of the event to report."""
    pspReference: String!
    """
    The time of the event to report. If not provide, the current time will be used.
    """
    time: DateTime
    """The token of the transaction. One of field id or token is required."""
    token: UUID
    """
    Fields required to update the transaction metadata. Can be read by any API client authorized to read the object it's attached to.
    
    Warning: never store sensitive information, including financial data such as credit card details.
    """
    transactionMetadata: [MetadataInput!]
    """
    Fields required to update the transaction private metadata.
    
    Requires permissions to modify and to read the metadata of the object it's attached to.
    
    Warning: never store sensitive information, including financial data such as credit card details.
    """
    transactionPrivateMetadata: [MetadataInput!]
    """Current status of the event to report."""
    type: TransactionEventTypeEnum!
    idempotencyKey: String
  ): TransactionEventReport @doc(category: "Payments") @webhookEventsInfo(asyncEvents: [TRANSACTION_ITEM_METADATA_UPDATED, CHECKOUT_FULLY_PAID, ORDER_UPDATED], syncEvents: [])
}

enum TransactionRequestActionErrorCode @doc(category: "Payments") {
  INVALID
  REQUIRED
  GRAPHQL_ERROR
  NOT_FOUND
  MISSING_TRANSACTION_ACTION_REQUEST_WEBHOOK
  CONFLICT
  AMOUNT_EXCEEDED
  ACTION_NOT_ALLOWED
}

enum TransactionRequestRefundForGrantedRefundErrorCode @doc(category: "Payments") {
  INVALID
  GRAPHQL_ERROR
  NOT_FOUND
  AMOUNT_GREATER_THAN_AVAILABLE
  MISSING_TRANSACTION_ACTION_REQUEST_WEBHOOK
  REFUND_ALREADY_PROCESSED
  REFUND_IS_PENDING
  CONFLICT
  AMOUNT_EXCEEDED
  ACTION_NOT_ALLOWED
}
```

- 字段说明：所有Money同ordercurrency且非空。totalPayable冻结order总额；netCharged是当前可用净款，successfulCharged是成功扣款减成功退款的现金事实（pendingrefund未成功仍属现金）；authorized是剩余授权；charge/refundPending单列。giftCardCharged是netCharged子集，legacyGiftCardDiscount已含total不可重加。totalBalance保留pending/grant业务语义；remainingDue=max(−balance,0)，正balance表示credit。actions和availableamount服务器最新；PositiveDecimal支持非负标量但移动动作amount=0运行层INVALID，默认缺amount用当时上限。新增key参数SDL可选为分阶段兼容；实际移动命令非空key必需（缺REQUIRED），eventreport旧稳定(pspReference,type,provider)可作legacykey。
- 权限：员工/App必须HANDLE_PAYMENTS与MANAGE_ORDERS（order）或MANAGE_CHECKOUTS（管理checkout）、目标渠道/对象与provider范围；transactionInitialize Storefront原合法checkout上下文沿用。PSP只能报告自身transaction，不因HANDLE_PAYMENTS获得其他provider。客户只I07 cancel例外。
- 错误：现行域error enum加CONFLICT；requestaction/refund加AMOUNT_EXCEEDED/ACTION_NOT_ALLOWED，其他order/payment金额超限用INVALID/PAYMENT_ERROR并field=amount。无动作、已有记录不允许markpaid、billing/state不满足明确errors，不成功null。权限FORBIDDEN且不带上限。
- 完成判定：businesssuccess判断为errors=[]和对应result存在；对App异步action只表示已受理，待transactioneventterminal才资金成功。scope/key+normalized input一致重放原结果，不同input CONFLICT；命令预占额度并对PSP用稳定key，timeout保持pending/reconcile不重扣。markpaid锁内无任何支付/transaction/command且合法订单，一次结果/event。成功统一刷新order/transaction/cardbalance，失败无部分本地金额变更；已发生PSP副作用不能说DBrollback撤销，必须对账/补偿。
- 变更与兼容：保留Payment与Transaction，source映射明确去重，不以任意相同金额猜一笔。不改历史order.total；totalCaptured弃用→totalCharged；纯Payment/Transaction的totalBalance按BD07保持，pending不是paideligibility；新增field/key/errors由新Dashboard同版消费。

### I09 · 根交易基础定位与对象范围
- 所属设计单元：BD08
- 提供方：saleor / graphql/payment/schema.py、filters.py；拟新增rootqueryfilter/connection resolver
- 调用方：FD03客服基础lookup、支付App、合法客户本人订单/checkout查询
- 目标定义：target-schema.graphql：`Query.transactions,transaction`；`TransactionQueryFilterInput`；`TransactionItemCountableConnection`；`TransactionItemCountableEdge`；`TransactionItem.appIdentifier`

```graphql
type Query {
  transactions(filter: TransactionQueryFilterInput, before: String, after: String, first: Int, last: Int): TransactionItemCountableConnection
  """
  I09: look up a transaction using exactly one Relay id or UUID token. Access requires staff payments plus related business-domain/object/channel scope, owning App provider scope, or customer ownership of the associated order/checkout. Invalid input or forbidden access is an error, not a successful null result.
  """
  transaction(
    """
    ID of a transaction. Either it or token is required to fetch the transaction data.
    """
    id: ID
    """
    Token of a transaction. Either it or ID is required to fetch the transaction data.
    """
    token: UUID
  ): TransactionItem @doc(category: "Payments")
}

"""
I09: AND between fields, OR within each ID list; no date/event filters or client ordering.
"""
input TransactionQueryFilterInput {
  ids: [ID!]
  orders: [ID!]
  checkouts: [ID!]
  pspReference: String
  appIdentifier: String
}

type TransactionItemCountableConnection {
  pageInfo: PageInfo!
  edges: [TransactionItemCountableEdge!]!
  totalCount: Int!
}

type TransactionItemCountableEdge {
  cursor: String!
  node: TransactionItem!
}

type TransactionItem {
  appIdentifier: String
}
```

- 字段说明：filter各字段AND、列表内OR，空[]表示无匹配；pspReference/appIdentifier精确非空string，省略不限制。ids是TransactionItem Relay ID；orders/checkouts是各自RelayID，不能token代替。root无sortBy/date/eventfilter，按pk稳定cursor；connection edges/node非空允许[]，count同scope。单transaction id/token exactlyone，token为UUID。
- 权限：HANDLE_PAYMENTS+对应业务域/渠道scope；App限其provider和授权目标，customer限本人order/合法checkout。无根查询权限FORBIDDEN，不空列表伪装；可见query合法不匹配edges=[]；受限field一并阻断/脱敏。
- 错误：BAD_USER_INPUT/INVALID_CURSOR/INVALID_PAGE_SIZE/FORBIDDEN/INTERNAL_ERROR在标准GraphQLerrors.extensions.code，单query定位参数缺/多INVALID_ARGUMENT；不用MutationError。
- 完成判定：只读无资金副作用，金额/方式/events与I07/08共同投影，count/pageInfo与过滤一致。未出现下一页合法[]，无效cursor明错。
- 变更与兼容：新增connection+独立TransactionQueryFilterInput，现有Order用TransactionFilterInput完整保留；修正单transaction token忽略id行为。无专用日期索引/排序。

### I10 · 主体搜索与Page/User基础搜索
- 所属设计单元：BD09
- 提供方：saleor / product/search.py、order/search.py、giftcard/search.py、account/search.py、graphql/page/filters.py；拟新增 checkout subject search/dirty更新
- 调用方：FD04列表/弹窗/选择器与外部有权运营查询
- 目标定义：target-schema.graphql：`GiftCardFilterInput.search`；`CheckoutSortField`；`GiftCardSortField`

```graphql
input GiftCardFilterInput {
  search: String
}

enum CheckoutSortField @doc(category: "Checkout") {
  """Sort checkouts by creation date."""
  CREATION_DATE
  """Sort checkouts by customer."""
  CUSTOMER
  """Sort checkouts by payment."""
  PAYMENT
  RANK
}

enum GiftCardSortField @doc(category: "Gift cards") {
  """Sort gift cards by product."""
  PRODUCT
  """Sort gift cards by used by."""
  USED_BY
  """Sort gift cards by current balance."""
  CURRENT_BALANCE
  """Sort gift cards by created at."""
  CREATED_AT
  RANK
}
```

- 字段说明：现有Query.products/orders/giftCards/checkouts search/filter.search继续；GiftCardFilter.search新增可空string，与root同时值相同合法/不同拒绝。长度≤256/词≤32；空词有界普通分页。NFKC/casefold/de-dup裸词前缀AND、phrase保留组合语义；主体sortRANK仅非空search可用，pk tie-break。Page title/slug/content基础trigram/icontains，User文档空格词AND，不支持RANK/高级prefix。
- 权限：使用各主体既有域/客户/员工scope与I25字段保护，搜索名称/email/address不能变隐私旁路。
- 错误：超长/非法输入 BAD_USER_INPUT，错sort组合INVALID_ARGUMENT，cursor上下文变化INVALID_CURSOR，服务/DB异常INTERNAL_ERROR，noresult合法empty，不能混淆。
- 完成判定：数据write置dirty，subjectworker成功更新后clear；基础Userdocument维护保留，Page引用名称变更使Productdirty。最终一致窗口Q01未给数字，必须发布落实，当前scheduler20秒不是SLA。稳定静态分页/count；动态变化可重启，不承诺永久跨页快照。
- 变更与兼容：四主体增强保留/补齐checkout，新增Checkout/GiftRANK；Page/User无新vector/index/job/migration，旧基础入口不删除。

### I11 · 商品、礼品卡与voucher当前查询导出
- 所属设计单元：BD10
- 提供方：saleor / graphql/csv/schema.py；拟新增readonlyexport resolver，复用各域scopebuilder
- 调用方：FD05导出button、获对应导出业务权限的App
- 目标定义：target-schema.graphql：`Query.productsExport,giftCardsExport,voucherCodesExport`；`ProductExportQueryInput`；`GiftCardExportQueryInput`；`VoucherCodeExportQueryInput`；`ProductExportConnection`；`GiftCardExportConnection`；`VoucherCodeExportConnection`；`ProductExportRow`；`GiftCardExportRow`；`VoucherCodeExportRow`

```graphql
type Query {
  productsExport(input: ProductExportQueryInput!, before: String, after: String, first: Int, last: Int): ProductExportConnection
  giftCardsExport(input: GiftCardExportQueryInput!, before: String, after: String, first: Int, last: Int): GiftCardExportConnection
  voucherCodesExport(input: VoucherCodeExportQueryInput!, before: String, after: String, first: Int, last: Int): VoucherCodeExportConnection
}

"""
I11: read-only export rows; ALL means all permitted rows intersected with every supplied constraint.
"""
input ProductExportQueryInput {
  scope: ExportScope!
  filter: ProductFilterInput
  lockedFilter: ProductFilterInput
  where: ProductWhereInput
  lockedWhere: ProductWhereInput
  ids: [ID!]
  channel: String
  search: String
  sortBy: ProductOrder
  exportInfo: ExportInfoInput
}

input GiftCardExportQueryInput {
  scope: ExportScope!
  filter: GiftCardFilterInput
  lockedFilter: GiftCardFilterInput
  ids: [ID!]
  search: String
  sortBy: GiftCardSortingInput
}

input VoucherCodeExportQueryInput {
  voucherId: ID
  ids: [ID!]
}

type ProductExportConnection {
  pageInfo: PageInfo!
  edges: [ProductExportEdge!]!
  totalCount: Int!
}

type GiftCardExportConnection {
  pageInfo: PageInfo!
  edges: [GiftCardExportEdge!]!
  totalCount: Int!
}

type VoucherCodeExportConnection {
  pageInfo: PageInfo!
  edges: [VoucherCodeExportEdge!]!
  totalCount: Int!
}

type ProductExportRow {
  id: ID!
  data: JSON!
}

type GiftCardExportRow {
  id: ID!
  data: JSON!
}

type VoucherCodeExportRow {
  id: ID!
  voucherId: ID!
  code: String!
}
```

- 字段说明：input必填，scope ALL/FILTER/IDS为初始集合，所有filter/where/locked/search/channel/ids继续相交，ALL不忽略filter；IDS需非空ids，FILTER需至少一个条件，否则INVALID_ARGUMENT。productsort用ProductOrder，gift用GiftCardSortingInput，默认同列表，vouchercodepk序。所有row.data为对象JSON!不可null；完整字段/投影/缺省/decimal形状见 [interfaces/query-export-row-data.md](interfaces/query-export-row-data.md)，不以JSON标量假称所有列可透传。列表/节点非空、允许合法empty。Money/weight十进制用字符串和currency/unit，dateISO，不返回locale格式。新gift查询只给displayCode脱敏字段，完整code仅有权旧export流程，不在新JSON偷加。
- 权限：Base没有EXPORT_*枚举：商品MANAGE_PRODUCTS、giftMANAGE_GIFT_CARD、voucherMANAGE_DISCOUNTS并受channel/warehouse/字段scope；真实giftcode只有现行许可读/导身份。权限始终在Core，不是URLlock。
- 错误：BAD_USER_INPUT/INVALID_ARGUMENT/INVALID_CURSOR/FORBIDDEN/INTERNAL_ERROR标准GraphQLerrors；query不能填ExportError伪装mutationpayload。任意页error不标下载完成，空IDS绝不转ALL。
- 完成判定：Query完全只读，不创建ExportFile/Celeryjob/完成事件；分页limit100同listquerybuilder，frontend显式生成CSV/XLSX并formulaescape。合法empty可生成仅header文件，错误不能产生partial成功文件。不承诺跨数据变更永久snapshot。
- 变更与兼容：Base无queryexports；现有Mutation.exportProducts/GiftCards/VoucherCodes保留deprecated异步Job，准确errors+owner/scope，I24给旧调用过渡；新Dashboard优先只读路径，明确大数据legacyjob分支。旧input缺where/lock/search时仅能先枚举有效交集后以IDS提交非空ids（voucher显式code ids），不得回退ALL放宽范围，worker按最新权限/资格处理并明确反馈变化。

### I12 · 锁定筛选与批量范围
- 所属设计单元：BD10
- 提供方：saleor / graphql/product/order/giftcard/checkout schema与filters，bulk mutations统一scopeguard（拟新增）
- 调用方：FD05列表/层级选择器/导出/bulk，外部运营App
- 目标定义：target-schema.graphql：`Query.products,orders,giftCards,checkouts`；`Mutation.productBulkDelete,giftCardBulkDelete,orderBulkCancel`

```graphql
type Query {
  """
  List of the shop's products. Requires one of the following permissions to include the unpublished items: MANAGE_ORDERS, MANAGE_DISCOUNTS, MANAGE_PRODUCTS.
  """
  products(
    """Filtering options for products."""
    filter: ProductFilterInput @deprecated(reason: "Use `where` filter instead.")
    """Where filtering options for products."""
    where: ProductWhereInput
    """Sort products."""
    sortBy: ProductOrder
    """Search products."""
    search: String
    """Slug of a channel for which the data should be returned."""
    channel: String
    """Return the elements in the list that come before the specified cursor."""
    before: String
    """Return the elements in the list that come after the specified cursor."""
    after: String
    """
    Retrieve the first n elements from the list. Note that the system only allows fetching a maximum of 100 objects in a single query.
    """
    first: Int
    """
    Retrieve the last n elements from the list. Note that the system only allows fetching a maximum of 100 objects in a single query.
    """
    last: Int
    lockedFilter: ProductFilterInput
    lockedWhere: ProductWhereInput
  ): ProductCountableConnection @doc(category: "Products")
  """
  List of orders. The query will not initiate any external requests, including filtering available shipping methods, or performing external tax calculations.
  
  Requires one of the following permissions: MANAGE_ORDERS.
  """
  orders(
    """Sort orders."""
    sortBy: OrderSortingInput
    """Filtering options for orders."""
    filter: OrderFilterInput @deprecated(reason: "Use `where` filter instead.")
    """
    Where filtering options for orders.
    
    Added in Saleor 3.22.
    """
    where: OrderWhereInput
    """Slug of a channel for which the data should be returned."""
    channel: String
    """
    Search orders.
    
    Added in Saleor 3.22.
    """
    search: String
    """Return the elements in the list that come before the specified cursor."""
    before: String
    """Return the elements in the list that come after the specified cursor."""
    after: String
    """
    Retrieve the first n elements from the list. Note that the system only allows fetching a maximum of 100 objects in a single query.
    """
    first: Int
    """
    Retrieve the last n elements from the list. Note that the system only allows fetching a maximum of 100 objects in a single query.
    """
    last: Int
    lockedFilter: OrderFilterInput
    lockedWhere: OrderWhereInput
  ): OrderCountableConnection @doc(category: "Orders")
  """
  List of gift cards.
  
  Requires one of the following permissions: MANAGE_GIFT_CARD.
  """
  giftCards(
    """Sort gift cards."""
    sortBy: GiftCardSortingInput
    """Filtering options for gift cards."""
    filter: GiftCardFilterInput
    """
    Search gift cards by email and name of user, who created or used the gift card, and by code.
    """
    search: String
    """Return the elements in the list that come before the specified cursor."""
    before: String
    """Return the elements in the list that come after the specified cursor."""
    after: String
    """
    Retrieve the first n elements from the list. Note that the system only allows fetching a maximum of 100 objects in a single query.
    """
    first: Int
    """
    Retrieve the last n elements from the list. Note that the system only allows fetching a maximum of 100 objects in a single query.
    """
    last: Int
    lockedFilter: GiftCardFilterInput
  ): GiftCardCountableConnection @doc(category: "Gift cards")
  """
  List of checkouts. The query will not initiate any external requests, including fetching external shipping methods, filtering available shipping methods, or performing external tax calculations.
  
  Requires one of the following permissions: MANAGE_CHECKOUTS, HANDLE_PAYMENTS.
  """
  checkouts(
    """Sort checkouts."""
    sortBy: CheckoutSortingInput
    """Filtering options for checkouts."""
    filter: CheckoutFilterInput
    """Slug of a channel for which the data should be returned."""
    channel: String
    """Return the elements in the list that come before the specified cursor."""
    before: String
    """Return the elements in the list that come after the specified cursor."""
    after: String
    """
    Retrieve the first n elements from the list. Note that the system only allows fetching a maximum of 100 objects in a single query.
    """
    first: Int
    """
    Retrieve the last n elements from the list. Note that the system only allows fetching a maximum of 100 objects in a single query.
    """
    last: Int
    lockedFilter: CheckoutFilterInput
  ): CheckoutCountableConnection @doc(category: "Checkout")
}

type Mutation {
  """
  Deletes products. 
  
  Requires one of the following permissions: MANAGE_PRODUCTS.
  """
  productBulkDelete(
    """List of product IDs to delete."""
    ids: [ID!]!
    lockedFilter: ProductFilterInput
    filter: ProductFilterInput
    lockedWhere: ProductWhereInput
    where: ProductWhereInput
    channel: String
    search: String
  ): ProductBulkDelete @doc(category: "Products")
  """
  Deletes gift cards. 
  
  Requires one of the following permissions: MANAGE_GIFT_CARD.
  
  Triggers the following webhook events:
  - GIFT_CARD_DELETED (async): A gift card was deleted.
  """
  giftCardBulkDelete(
    """List of gift card IDs to delete."""
    ids: [ID!]!
    lockedFilter: GiftCardFilterInput
    filter: GiftCardFilterInput
    search: String
  ): GiftCardBulkDelete @doc(category: "Gift cards") @webhookEventsInfo(asyncEvents: [GIFT_CARD_DELETED], syncEvents: [])
  """
  Cancels orders. 
  
  Requires one of the following permissions: MANAGE_ORDERS.
  """
  orderBulkCancel(
    """List of orders IDs to cancel."""
    ids: [ID!]!
    lockedFilter: OrderFilterInput
    filter: OrderFilterInput
    lockedWhere: OrderWhereInput
    where: OrderWhereInput
    channel: String
    search: String
  ): OrderBulkCancel @doc(category: "Orders")
}
```

- 字段说明：lockedFilter为各域原filter类型；product/order额外lockedWhere原where类型。锁、省略/普通条件皆权限scope后AND，不是同key覆盖。数组内部OR照原filter，空[]不等全量。bulkids=[ID!]!；三个bulk新增filter/search，product/order另有where/channel，与锁参数一起完整承接当前有效条件。全部结果有界枚举ids后逐批携同scope提交，不承诺跨批快照或全原子；范围外/资格变化逐项明错。其它保留bulkactions沿旧签名，只可使用重新确认的当前交集ids和共同域权限/资格guard，不新全选API。
- 权限：域permission+对象/channel/warehouse，与list相同。客户端lock不是安全权限：即使用户删URLlock，server仍不能越权限scope；该入口businessscope显式锁也不能被普通条件覆盖。
- 错误：filter/type/pagingI23，范围外ID或最新状态不适用按原逐项errors的INVALID/NOT_FOUND/NOT_EDITABLE等，不将失败项计success；permissionFORBIDDEN不能totalCount泄露。
- 完成判定：list/display/export共享当前effectivequery；bulk=selectedIDs∩有效query，server重新查询状态，逐项结果明确。hierarchy查询按ID去重/真parent，取消值不残留；frontend返回路径保留上下文但不自行写层级。
- 变更与兼容：新增可选locked参数不改变无参数旧合法查询；旧filter与where并存取AND。新Dashboardreset仅清editable，不复用旧selection或旧缓存导出。

### I13 · 密码认证模式和设置即时生效
- 所属设计单元：BD11
- 提供方：saleor / site/models.py、graphql/shop/types.py/mutations/shop_settings_update.py、graphql/account及corejwt/middleware policyguard（新增）
- 调用方：FD06 settings/login/reset/newpassword、外部受支持用户认证客户端
- 目标定义：target-schema.graphql：`PasswordAuthenticationModeEnum`；`Shop.passwordAuthenticationMode,settingsRevision`；`ShopSettingsInput.passwordAuthenticationMode,expectedSettingsRevision`；`AccountErrorCode`；`ShopErrorCode`

```graphql
"""I13: applies to password-origin credentials only."""
enum PasswordAuthenticationModeEnum {
  ENABLED
  CUSTOMERS_ONLY
  DISABLED
}

type Shop {
  passwordAuthenticationMode: PasswordAuthenticationModeEnum!
  settingsRevision: String!
}

input ShopSettingsInput {
  passwordAuthenticationMode: PasswordAuthenticationModeEnum
  expectedSettingsRevision: String
}

enum AccountErrorCode @doc(category: "Users") {
  ACTIVATE_OWN_ACCOUNT
  ACTIVATE_SUPERUSER_ACCOUNT
  DUPLICATED_INPUT_ITEM
  DEACTIVATE_OWN_ACCOUNT
  DEACTIVATE_SUPERUSER_ACCOUNT
  DELETE_NON_STAFF_USER
  DELETE_OWN_ACCOUNT
  DELETE_STAFF_ACCOUNT
  DELETE_SUPERUSER_ACCOUNT
  GRAPHQL_ERROR
  INACTIVE
  INVALID
  INVALID_PASSWORD
  LEFT_NOT_MANAGEABLE_PERMISSION
  INVALID_CREDENTIALS
  NOT_FOUND
  OUT_OF_SCOPE_USER
  OUT_OF_SCOPE_GROUP
  OUT_OF_SCOPE_PERMISSION
  PASSWORD_ENTIRELY_NUMERIC
  PASSWORD_TOO_COMMON
  PASSWORD_TOO_SHORT
  PASSWORD_TOO_SIMILAR
  PASSWORD_RESET_ALREADY_REQUESTED
  REQUIRED
  UNIQUE
  JWT_SIGNATURE_EXPIRED
  JWT_INVALID_TOKEN
  JWT_DECODE_ERROR
  JWT_MISSING_TOKEN
  JWT_INVALID_CSRF_TOKEN
  CHANNEL_INACTIVE
  MISSING_CHANNEL_SLUG
  ACCOUNT_NOT_CONFIRMED
  LOGIN_ATTEMPT_DELAYED
  UNKNOWN_IP_ADDRESS
  PASSWORD_AUTHENTICATION_DISABLED
  PASSWORD_AUTHENTICATION_RESTRICTED
}

enum ShopErrorCode {
  ALREADY_EXISTS
  CANNOT_FETCH_TAX_RATES
  GRAPHQL_ERROR
  INVALID
  NOT_FOUND
  REQUIRED
  UNIQUE
  CONFLICT
}
```

- 字段说明：输出mode非空，初始ENABLED；省略更新不变，null非法。revision不透明，newDashboard必发expected；旧client省略lastwrite。CUSTOMERS_ONLY员工即使有客户订单亦不能password员工会话；DISABLED拒绝login/reset/set/change以及oldpasswordtoken/refresh/verify/access。外部认证独立配置，不通过禁用后password重试fallback。
- 权限：mode读公开供登录渲染；revision与设置改MANAGE_SETTINGS；所有受支持密码API每次读生效policy，不依页面隐藏。
- 错误：PASSWORD_AUTHENTICATION_DISABLED/RESTRICTED加入AccountErrorCode；不泄露账户存在性或身份详情。settingsCONFLICT/INVALID/权限标准层，保留原policy。
- 完成判定：shopSettingsUpdate业务成功仅保存，立即对所有worker认证生效；新JWTauthsource+epoch/当前policyguard，old来源缺失保守password，不因refresh绕过。加载/保存失败不改变生效值，已有password会话必要时重新登录。
- 变更与兼容：ENABLED旧商店行为不变；已有不受支持passwordtoken会因新policy明确拒绝；accountRegister等密码入口同guard，非密码外部能力不被一刀关闭。

### I14 · OIDC离线授权及稳定身份关联
- 所属设计单元：BD11
- 提供方：saleor / plugins/openid_connect/plugin.py、utils.py；拟新增ExternalIdentity/credentialepoch
- 调用方：FD06外部登录与身份集成、可信OIDC provider
- 目标定义：target-schema.graphql：`Mutation.externalAuthenticationUrl,externalObtainAccessTokens,externalRefresh,externalLogout,externalVerify`

```graphql
type Mutation {
  """Prepare external authentication URL for user by custom plugin."""
  externalAuthenticationUrl(
    """The data required by plugin to create external authentication url."""
    input: JSONString!
    """The ID of the authentication plugin."""
    pluginId: String!
  ): ExternalAuthenticationUrl @doc(category: "Authentication")
  """Obtain external access tokens for user by custom plugin."""
  externalObtainAccessTokens(
    """The data required by plugin to create authentication data."""
    input: JSONString!
    """The ID of the authentication plugin."""
    pluginId: String!
  ): ExternalObtainAccessTokens @doc(category: "Authentication")
  """Refresh user's access by custom plugin."""
  externalRefresh(
    """The data required by plugin to proceed the refresh process."""
    input: JSONString!
    """The ID of the authentication plugin."""
    pluginId: String!
  ): ExternalRefresh @doc(category: "Authentication")
  """Logout user by custom plugin."""
  externalLogout(
    """The data required by plugin to proceed the logout process."""
    input: JSONString!
    """The ID of the authentication plugin."""
    pluginId: String!
  ): ExternalLogout @doc(category: "Authentication")
  """Verify external authentication data by plugin."""
  externalVerify(
    """The data required by plugin to proceed the verification."""
    input: JSONString!
    """The ID of the authentication plugin."""
    pluginId: String!
  ): ExternalVerify @doc(category: "Authentication")
}
```

- 字段说明：保持Base pluginId:String!与JSONStringinput/既有payload；Google enableRefreshToken使用access_type=offline不offline_access，其他provider按合同。code/state/redirectURI/nonce/issuer/aud/expiry校验；issuer/sub作为唯一identity，不能只邮箱反复当新用户。敏感token字段仅必要认证回执，不message/log/额外浏览器持久化。
- 权限：provider是商店配置可信issuer；首次已有email关联要求验证email与受控匹配或已认证本人确认，不能任意同email接管员工。group/员工权限由当前允许映射，不让客户端input定义。
- 错误：原ExternalAuthenticationError/AccountError等错误路径按Base，provider拒绝/invalidstate可识别脱敏；无credentialepoch或策略不符相应PASSWORD_AUTHENTICATION_*，标准JSONtype错I23。不回显token/provideruserpayload。
- 完成判定：首次绑定事务set_unusable_password、提升epoch禁旧password/reset/token路径；后续issuer/sub重查关联不重复绑定/重置。成功外部会话仍受scope；失败不创建半identity/user权限。
- 变更与兼容：GraphQL签名不变，HTTP授权参数/安全语义变化；Google与非Google分支明确，不额外获取未来provider/schema。

### I15 · EditorJS结构、链接与深度合同
- 所属设计单元：BD12
- 提供方：saleor / core/utils/editorjs.py、所有产品/页面/分类/集合/属性/翻译富文本mutation输入；FD07客户端预校验
- 调用方：FD07编辑/翻译、FD08extensionform及有权内容API消费者
- 目标定义：target-schema.graphql：`Mutation.productCreate,productUpdate,pageCreate,pageUpdate,productTranslate,pageTranslate`

```graphql
type Mutation {
  """
  Creates a new product. 
  
  Requires one of the following permissions: MANAGE_PRODUCTS.
  """
  productCreate(
    """Fields required to create a product."""
    input: ProductCreateInput!
  ): ProductCreate @doc(category: "Products")
  """
  Updates an existing product. 
  
  Requires one of the following permissions: MANAGE_PRODUCTS.
  """
  productUpdate(
    """External ID of a product to update."""
    externalReference: String
    """ID of a product to update."""
    id: ID
    """Fields required to update a product."""
    input: ProductInput!
  ): ProductUpdate @doc(category: "Products")
  """
  Creates a new page. 
  
  Requires one of the following permissions: MANAGE_PAGES.
  """
  pageCreate(
    """Fields required to create a page."""
    input: PageCreateInput!
  ): PageCreate @doc(category: "Pages")
  """
  Updates an existing page. 
  
  Requires one of the following permissions: MANAGE_PAGES.
  """
  pageUpdate(
    """ID of a page to update."""
    id: ID!
    """Fields required to update a page."""
    input: PageInput!
  ): PageUpdate @doc(category: "Pages")
  """
  Creates/updates translations for a product. 
  
  Requires one of the following permissions: MANAGE_TRANSLATIONS.
  """
  productTranslate(
    """Product ID or ProductTranslatableContent ID."""
    id: ID!
    """Fields required to update product translations."""
    input: TranslationInput!
    """Translation language code."""
    languageCode: LanguageCodeEnum!
  ): ProductTranslate @doc(category: "Products")
  """
  Creates/updates translations for a page. 
  
  Requires one of the following permissions: MANAGE_TRANSLATIONS.
  """
  pageTranslate(
    """Page ID or PageTranslatableContent ID."""
    id: ID!
    """Fields required to update page translations."""
    input: PageTranslationInput!
    """Translation language code."""
    languageCode: LanguageCodeEnum!
  ): PageTranslate @doc(category: "Pages")
}
```

- 字段说明：完整非SDL约束在 [interfaces/editorjs-content.md](interfaces/editorjs-content.md)：paragraph/header/list/quote/image/embed支持集、root与block字段白名单、UTF8 1MiB/1000blocks/L8/有限items。现有业务JSON/JSONStringnullability不变；合法空blocks清空，null按所属输入可空业务合同。schema并不授权任意JSON保存。
- 权限：各内容/产品/翻译域原permission+objectscope，扩展返回不能绕开；没有customschemewhitelist配置。
- 错误：原域errors.code=INVALID，field定位具体description.blocks等路径，message原因类别STRUCTURE/UNKNOWN_FIELD/URL_SCHEME/LINK_ATTRIBUTE/DEPTH/SIZE，不回显危险内容。scalar/coercion错I23。
- 完成判定：先完整结构验证再允许URL/HTML规范化；_blank固定noopener noreferrer。非法scheme/额外field/过深整体拒绝，无部分保存，不危险URL替换#invalid后成功。同一mutation其它字段随之回滚；历史读显示仍安全。
- 变更与兼容：合法旧stringlist/image/embed可读编辑；Base宽松未知block/替换危险URL不是目标承诺；历史超集不批量重写，保存明确迁移错误，冻结测试不改。

### I16 · App manifest、安装及扩展字段迁移
- 所属设计单元：BD13
- 提供方：saleor / app/manifest_validations.py、installation_utils.py、models.py、graphql/app/types.py/mutations；App提供manifest HTTP GET/可选token接收POST
- 调用方：FD08安装/升级/render；有MANAGE_APPS的员工/App和受权扩展调用方
- 目标定义：target-schema.graphql：`AppExtension.mountName,targetName,settings,mount,target,options,accessToken`；`AppManifestExtension`；`AppExtensionFilterInput`；`AppInstallInput`；`Mutation.appCreate,appInstall,appFetchManifest,appUpdate`；`AppCreate.authToken`；`Manifest.tokenTargetUrl`

```graphql
type AppExtension {
  mountName: String!
  targetName: String!
  settings: JSON!
  """Place where given extension will be mounted."""
  mount: AppExtensionMountEnum! @deprecated(reason: "Use mountName.")
  """Type of way how app extension will be opened."""
  target: AppExtensionTargetEnum! @deprecated(reason: "Use targetName.")
  """
  App extension options.
  
  Added in Saleor 3.22.
  """
  options: AppExtensionPossibleOptions @deprecated(reason: "Use settings; legacy widgetTarget/newTabTarget mapping is preserved.")
  """JWT token used to authenticate by third-party app extension."""
  accessToken: String
}

type AppManifestExtension @doc(category: "Apps") {
  """List of the app extension's permissions."""
  permissions: [Permission!]!
  """Label of the extension to show in the dashboard."""
  label: String!
  """URL of a view where extension's iframe is placed."""
  url: String!
  """Place where given extension will be mounted."""
  mount: AppExtensionMountEnum! @deprecated(reason: "Use mountName.")
  """Type of way how app extension will be opened."""
  target: AppExtensionTargetEnum! @deprecated(reason: "Use targetName.")
  mountName: String!
  targetName: String!
  settings: JSON!
}

input AppExtensionFilterInput @doc(category: "Apps") {
  mount: [AppExtensionMountEnum!] @deprecated(reason: "Use mountName.")
  target: AppExtensionTargetEnum @deprecated(reason: "Use targetName.")
  mountName: [String!]
  targetName: String
}

input AppInstallInput @doc(category: "Apps") {
  """Name of the app to install."""
  appName: String!
  """URL to app's manifest in JSON format."""
  manifestUrl: String!
  """Determine if app will be set active or not."""
  activateAfterInstallation: Boolean = true
  """List of permission code names to assign to this app."""
  permissions: [PermissionEnum!]
}

type Mutation {
  """
  Creates a new app. Requires the following permissions: AUTHENTICATED_STAFF_USER and MANAGE_APPS.
  
  Triggers the following webhook events:
  - APP_INSTALLED (async): An app was installed.
  """
  appCreate(
    """Fields required to create a new app."""
    input: AppInput!
    issueToken: Boolean = false
  ): AppCreate @doc(category: "Apps") @webhookEventsInfo(asyncEvents: [APP_INSTALLED], syncEvents: [])
  """
  Install new app by using app manifest. Requires the following permissions: AUTHENTICATED_STAFF_USER and MANAGE_APPS.
  """
  appInstall(
    """Fields required to install a new app."""
    input: AppInstallInput!
  ): AppInstall @doc(category: "Apps")
  """
  Fetch and validate manifest. 
  
  Requires one of the following permissions: MANAGE_APPS.
  """
  appFetchManifest(
    """URL to app's manifest in JSON format."""
    manifestUrl: String!
  ): AppFetchManifest @doc(category: "Apps")
  """
  Updates an existing app. 
  
  Requires one of the following permissions: MANAGE_APPS.
  
  Triggers the following webhook events:
  - APP_UPDATED (async): An app was updated.
  
  I16: when manifestUrl is supplied, fetch and validate the complete manifest against this existing app before atomically updating its extensions, settings and webhooks. Omission preserves the existing manifest configuration. No install token is returned or rotated by this operation.
  """
  appUpdate(
    """ID of an app to update."""
    id: ID!
    """Fields required to update an existing app."""
    input: AppInput!
    manifestUrl: String
  ): AppUpdate @doc(category: "Apps") @webhookEventsInfo(asyncEvents: [APP_UPDATED], syncEvents: [])
}

type AppCreate {
  """
  I16: null unless the authorized caller explicitly requests issueToken=true. Returned once; never stored in browser persistence.
  """
  authToken: String
}

type Manifest {
  """
  Endpoint used during process of app installation, [see installing an app.](https://docs.saleor.io/developer/extending/apps/installing-apps#installing-an-app)
  """
  tokenTargetUrl: String
}
```

- 字段说明：完整规范化manifest见 [interfaces/app-manifest.schema.json](interfaces/app-manifest.schema.json)，完整GET/可选POST边界见 [interfaces/app-installation.openapi.yaml](interfaces/app-installation.openapi.yaml)。rootid/name/version必需、extensions/webhooks/permissions缺省[]、targetName=POPUP/settings={}；String名只能Base受支持mount/target，settings已知newTabTarget/widgetTarget.method GET/POST且互斥匹配。webhook isActive省略true/customHeaders按Base验证，不丢合法旧项。appName/manifestUrl String!且非空，tokenTargetUrl可省略（不是必须）。appUpdate新增manifestUrl:String，省略仅基础资料更新并保留扩展，显式null/空值INVALID；提供URL才进行同App完整manifest升级，失败不覆盖旧配置。legacyfields只compat映射/弃用读，新frontend发current名。
- 权限：安装/更新MANAGE_APPS及targetscope，permissions不得超App/caller范围，readowner/manager与字段scope。扩展accessToken仅当前employee∩App∩extension短期权限，未经frame鉴别不发送。
- 错误：AppError REQUIRED/INVALID/INVALID_MANIFEST_FORMAT/INVALID_PERMISSION/INVALID_URL_FORMAT/UNIQUE/OUT_OF_SCOPE_*，重复identifier并发DB约束映射UNIQUE；unknown/target-mismatched settings拒绝。无权FORBIDDEN，不错误回secret。
- 完成判定：fetchvalidate无写入，合法manifest全部通过后安装Job/更新原子保存，成功result不等Job安装completed；失败保留旧有效extensions/settings。迁移mount/target/options/httpmethod保留所有可信内容不要求重装。issueToken默认false，authToken=null；安装只有配置tokenTargetUrl需要时生成并投递，不返回Dashboardtoken。
- 变更与兼容：旧mount/target/options规范化适配，双组值冲突拒绝，旧getterdeprecated映射同值。optional tokenTarget缺省合法，确需长期token的POST配置无相应能力则REQUIRED不默给高权token。identifier条件unique是全部notremoved非空记录，停用App也保留占用，旧冲突先审计不自动删App。Base appUpdate无manifest更新，本轮可选manifestUrl补齐；升级不轮换/返回安装token，目标identity必须一致或显式受控迁移。

### I17 · 扩展响应只应用当前对应表单
- 所属设计单元：BD13
- 提供方：saleor-dashboard / extensions/views/ViewManifestExtension/components/AppFrame/useAppActions.ts、appActionsHandler.ts、AppExtensionContextProvider.tsx（handler增强）
- 调用方：FD08及FD07当前product/translationform、运行于受权frame的App
- 目标定义：本接口为非GraphQL协议，完整定义见下述 interfaces 引用。

- 字段说明：完整nativepostMessage合同见 [interfaces/extension-form-response.md](interfaces/extension-form-response.md)。经鉴别notifyReady后以formProtocolHello/Ready协商v1，才发formContext；formResponse/response ACK字段、frameId/context/revision/actionId、status与optionalfields/errors均明定。缺fields不清空，明确null仍经允许字段validator。1MiB/100字段，无nullerror项。AppFrame onLoad不直接交接token，不当成notifyReady完成。
- 权限：严格eventorigin+source+registeredframe+handshake+activeapp+fieldscope；不单凭sameorigin。token只在受验证握手内存；导航/卸载/src改/context换立即失效。
- 错误：ok=false+STALE_CONTEXT/INVALID_RESPONSE/UNKNOWN_ACTION/FRAME_NOT_READY/PERMISSION_DENIED/APP_CLOSED/VALIDATION_ERROR；invalidorigin/source丢弃不ACK泄露。
- 完成判定：SUCCESS全字段校验后仅更新当前dirtyform，不自动保存，不更新已保存Apollocache；随后Coremutation成功才saved。duplicateaction同payload重放原ACK，不重复apply，不同payload拒绝。revision变化不能覆盖用户新输入，errorstatus不能应用fields。
- 变更与兼容：保留SDK原非form动作；旧无frame/context的message不能改form。新增form协议显式协商v1，不为兼容降低身份判定。

### I18 · 自托管扩展目录来源
- 所属设计单元：BD13
- 提供方：部署方静态GET /extensions/catalog.json；完整协议 [interfaces/extensions-catalog.openapi.yaml](interfaces/extensions-catalog.openapi.yaml)
- 调用方：FD09 / useAppStoreExtensions与ExploreExtensions
- 目标定义：本接口为非GraphQL协议，完整定义见下述 interfaces 引用。

- 字段说明：OpenAPI完整定义version=1、extensionCategories/categories/extensions/localizedname/logos/app/plugin/manifestURL。categoryid固定四域，lists可[]但元素非null，missing必需字段schemaerror。EXTENSIONS_CATALOG_URL优先否则同源；旧APPS_MARKETPLACE_API_URL只显式兼容不默认访问旧服务。所有请求不发Saleor bearer，HTTPS外源需部署allowlist+CORS。
- 权限：目录只读可浏览，Core身份决定MANAGE_APPS/相关plugin权限，readonly不会安装/配置；目录installed字段不作为权威，真实installed来自Core。
- 错误：404配置未部署、503网络服务error、invalidshape、CORS错误分别显示；200合法empty空态，不假安装成功；304仅有同来源cache才复用。
- 完成判定：加载schema合法data只表示目录可用，install成功须I16Job真实完成；取消/源切换旧响应丢弃。部署须实际提供同源JSON，本阶段未部署。
- 变更与兼容：保留现有ExploreUI基础浏览/筛选与权限，按categoryid不是英文name猜分组；没有新marketplace后台，不重引退出插件推荐。

### I19 · 按订阅字段解析与worker边界载荷
- 所属设计单元：BD14
- 提供方：saleor / graphql/webhook/subscription_types.py、plugins/webhook/plugin.py、webhook/transport/asynchronous/transport.py；拟新增eventoutbox版本记录
- 调用方：配置subscriptionQuery的外部App；FD10只读delivery，不参与服务工作
- 目标定义：target-schema.graphql：`Subscription.orderCreated,orderUpdated,draftOrderCreated,draftOrderUpdated,draftOrderDeleted`；`EventDelivery.payload,payloadGeneratedAt`

```graphql
type Subscription {
  """
  Event sent when new order is created.
  
  Added in Saleor 3.20.
  
  Note: this API is currently in Feature Preview and can be subject to changes at later point.
  """
  orderCreated(
    """
    List of channel slugs. The event will be sent only if the object belongs to one of the provided channels. If the channel slug list is empty, objects that belong to any channel will be sent. Maximally 500 items.
    """
    channels: [String!]
  ): OrderCreated @doc(category: "Orders")
  """
  Event sent when order is updated.
  
  Added in Saleor 3.20.
  
  Note: this API is currently in Feature Preview and can be subject to changes at later point.
  """
  orderUpdated(
    """
    List of channel slugs. The event will be sent only if the object belongs to one of the provided channels. If the channel slug list is empty, objects that belong to any channel will be sent. Maximally 500 items.
    """
    channels: [String!]
  ): OrderUpdated @doc(category: "Orders")
  """
  Event sent when new draft order is created.
  
  Added in Saleor 3.20.
  
  Note: this API is currently in Feature Preview and can be subject to changes at later point.
  """
  draftOrderCreated(
    """
    List of channel slugs. The event will be sent only if the object belongs to one of the provided channels. If the channel slug list is empty, objects that belong to any channel will be sent. Maximally 500 items.
    """
    channels: [String!]
  ): DraftOrderCreated @doc(category: "Orders")
  """
  Event sent when draft order is updated.
  
  Added in Saleor 3.20.
  
  Note: this API is currently in Feature Preview and can be subject to changes at later point.
  """
  draftOrderUpdated(
    """
    List of channel slugs. The event will be sent only if the object belongs to one of the provided channels. If the channel slug list is empty, objects that belong to any channel will be sent. Maximally 500 items.
    """
    channels: [String!]
  ): DraftOrderUpdated @doc(category: "Orders")
  """
  Event sent when draft order is deleted.
  
  Added in Saleor 3.20.
  
  Note: this API is currently in Feature Preview and can be subject to changes at later point.
  """
  draftOrderDeleted(
    """
    List of channel slugs. The event will be sent only if the object belongs to one of the provided channels. If the channel slug list is empty, objects that belong to any channel will be sent. Maximally 500 items.
    """
    channels: [String!]
  ): DraftOrderDeleted @doc(category: "Orders")
}

type EventDelivery {
  """Event payload."""
  payload: String
  payloadGeneratedAt: DateTime
}
```

- 字段说明：完整HTTP约定见 [interfaces/webhook-delivery.openapi.yaml](interfaces/webhook-delivery.openapi.yaml)；GraphQL subscription字段和Basepayload保持，新Order/Fulfillmentsnapshot字段I21按selection返回。PENDINGpayload可null为未生成，generatedAt可null；稳定Saleor-Event-Id为outbox事件UUID，非attemptID，同logicaleventretry同值。
- 权限：selectionresolver按App域/字段/object/channel；同步税/配送服务只解析实际选择字段，fragment/alias同规则。pureasyncallow_sync_webhooks=false，不能提前触发未订阅服务。
- 错误：同步超时/invalidresponse沿现行服务错误与业务域error，不重复解析冲上限；asyncpayloadfailure仅该deliveryFAILED且latestError脱敏，业务事务不回滚。
- 完成判定：事务提交保存必要不可变事件事实/版本引用和唯一outbox，on_commitworker构建完整payload并创建独立delivery；业务请求不等待完整payload。快照不能worker读最新易变pk伪当eventfacts。no-op保存不logicalnotify，含variantdiscountprice实际变化一次event；networkretry不exactlyonce送达承诺。
- 变更与兼容：现行signatures/headers/legacygenerator形状保留，新增eventID可供去重；重试/timeout/circuit上限不扩大。无AppProblems。

### I20 · delivery状态、失败隔离与单条重试
- 所属设计单元：BD14
- 提供方：saleor / core/models.py、core/__init__.py、graphql/webhook/types.py与mutations/event_delivery_retry.py、asynchronoustransport
- 调用方：FD10 / AppWebhooksDisplay与AppAlerts；有权App/业务域管理员
- 目标定义：target-schema.graphql：`EventDelivery.status,latestError,nextRetryAt,payloadGeneratedAt,attempts`；`EventDeliveryStatusEnum`；`Mutation.eventDeliveryRetry`；`EventDeliveryRetry.delivery,errors`

```graphql
type EventDelivery {
  """Event delivery status."""
  status: EventDeliveryStatusEnum!
  latestError: String
  nextRetryAt: DateTime
  payloadGeneratedAt: DateTime
  """Event delivery attempts."""
  attempts(
    """Event delivery sorter"""
    sortBy: EventDeliveryAttemptSortingInput
    """Return the elements in the list that come before the specified cursor."""
    before: String
    """Return the elements in the list that come after the specified cursor."""
    after: String
    """
    Retrieve the first n elements from the list. Note that the system only allows fetching a maximum of 100 objects in a single query.
    """
    first: Int
    """
    Retrieve the last n elements from the list. Note that the system only allows fetching a maximum of 100 objects in a single query.
    """
    last: Int
  ): EventDeliveryAttemptCountableConnection
}

enum EventDeliveryStatusEnum @doc(category: "Webhooks") {
  PENDING
  SUCCESS
  FAILED
  RETRYING
}

type Mutation {
  """
  I20: queue a retry of one failed delivery. Requires App owner/MANAGE_APPS or corresponding event business-domain permission, with recipient App, object and channel scope. Replays an already queued retry without creating a new logical event; does not grant access to webhook secrets or unrestricted payload.
  """
  eventDeliveryRetry(
    """ID of the event delivery to retry."""
    id: ID!
  ): EventDeliveryRetry @doc(category: "Webhooks")
}

type EventDeliveryRetry {
  """Event delivery."""
  delivery: EventDelivery
  errors: [WebhookError!]!
}
```

- 字段说明：EventDeliveryRetry.delivery是返回字段名（沿Base），payload可空；status非空增加RETRYING，error/nextretry/generation时间可空。PENDING未生成或首次排队，SUCCESS接收端2xx确认，FAILED已失败，RETRYING已受理有界重试。attempts连接按Base可空（错误），合法空edges不是成功投递；payload需更高读权限。
- 权限：Appowner/MANAGE_APPS或对应事件业务域+object/channel/recipientAppscope允许单retry；不能因MANAGE_ORDERS读/改其他Appsecret或webhook配置。payloadprivate与I25同边界。
- 错误：EventDeliveryRetry原error形状NOT_FOUND/INVALID等，FORBIDDEN标准层；HTTP网络错误写脱敏attempt。无payload不falseSUCCESS。
- 完成判定：retry返回同delivery已受理RETRYING，只是一条排队不是sendcompleted；queued重复返回原结果，锁delivery不新logicalevent。其他SUCCESSdelivery不重送，payloadbuild/sendfailure按recipient隔离；deliveryIDs+eventID去重，App失败告警仍在。
- 变更与兼容：原PENDING/SUCCESS/FAILED保留，多一个明确处理中状态；老客户端未知enum需升级，不能fallback绿色success。

### I21 · 创建时配送public/private元数据快照
- 所属设计单元：BD15
- 提供方：saleor / order/models.py、checkout/complete_checkout.py、graphql/order/types.py、draft完成及fulfillment读resolver（新增快照字段）
- 调用方：FD11 order/fulfillment详情，授权订单/履约App与Webhookselection
- 目标定义：target-schema.graphql：`Order.shippingMethodMetadata,shippingMethodPrivateMetadata,shippingMetadataSnapshotStatus`；`Fulfillment.shippingMethodMetadata,shippingMethodPrivateMetadata,shippingMetadataSnapshotStatus`；`ShippingMetadataSnapshotStatusEnum`

```graphql
type Order {
  shippingMethodMetadata: [MetadataItem!]!
  shippingMethodPrivateMetadata: [MetadataItem!]!
  shippingMetadataSnapshotStatus: ShippingMetadataSnapshotStatusEnum!
}

type Fulfillment {
  shippingMethodMetadata: [MetadataItem!]!
  shippingMethodPrivateMetadata: [MetadataItem!]!
  shippingMetadataSnapshotStatus: ShippingMetadataSnapshotStatusEnum!
}

enum ShippingMetadataSnapshotStatusEnum {
  CAPTURED
  LEGACY_PRESERVED
  UNAVAILABLE
}
```

- 字段说明：public/private各[MetadataItem!]!，无数据稳定[]；status非空CAPTURED/LEGACY_PRESERVED/UNAVAILABLE。是method创建snapshot不是shippingTaxClassMetadata；fulfillment读order对应快照。不合法恢复历史为空且UNAVAILABLE，不从当前源造假历史。
- 权限：public按合法order/fulfillmentscope；private现行域管理/ownerApp受限权限，税App仅HANDLE_TAXES对应允许字段；仅public字段权限不能读private。
- 错误：无权标准FORBIDDEN，不能用[]假装无权；源删除后snapshot仍合法不NOT_FOUND。部分field权限错按GraphQLnull传播，consumer不得当整体合法空。
- 完成判定：checkout/draft两成单路径同order事务deepcopy，源后改/停/删不变；events同版本快照。历史保留已有可信数据，未有为空/UNAVAILABLE，backfill幂等不重复记录、不重算金额。snapshotreadonly，普通metadataedit不能改历史创建事实。
- 变更与兼容：新增明确字段与状态，不替换原taxclassmetadata/普通metadata；旧历史缺数据稳定返回[]，不得借此删资产。

### I22 · 基础metadata原子读写
- 所属设计单元：BD15
- 提供方：saleor / graphql/meta/mutations与各域metadataresolver；现有MetaMutations/updateMetadata等
- 调用方：FD11已有inline/orderline form与合法Storefront/draft/order/fulfillment集成
- 目标定义：target-schema.graphql：`Mutation.updateMetadata,deleteMetadata,updatePrivateMetadata,deletePrivateMetadata`；`Order.metadata,privateMetadata`；`Fulfillment.metadata,privateMetadata`；`Checkout.metadata,privateMetadata`

```graphql
type Mutation {
  """
  Updates metadata of an object.Requires permissions to modify and to read the metadata of the object it's attached to.
  
  Warning: never store sensitive information, including financial data such as credit card details.
  """
  updateMetadata(
    """ID or token (for Order and Checkout) of an object to update."""
    id: ID!
    """Fields required to update the object's metadata."""
    input: [MetadataInput!]!
  ): UpdateMetadata
  """
  Delete metadata of an object. To use it, you need to have access to the modified object.
  """
  deleteMetadata(
    """ID or token (for Order and Checkout) of an object to update."""
    id: ID!
    """Metadata keys to delete."""
    keys: [String!]!
  ): DeleteMetadata
  """
  Updates private metadata of an object. Requires permissions to modify and to read the metadata of the object it's attached to.
  
  Warning: never store sensitive information, including financial data such as credit card details.
  """
  updatePrivateMetadata(
    """ID or token (for Order and Checkout) of an object to update."""
    id: ID!
    """Fields required to update the object's metadata."""
    input: [MetadataInput!]!
  ): UpdatePrivateMetadata
  """
  Delete object's private metadata. To use it, you need to be an authenticated staff user or an app and have access to the modified object.
  """
  deletePrivateMetadata(
    """ID or token (for Order and Checkout) of an object to update."""
    id: ID!
    """Metadata keys to delete."""
    keys: [String!]!
  ): DeletePrivateMetadata
}

type Order {
  """List of public metadata items. Can be accessed without permissions."""
  metadata: [MetadataItem!]!
  """List of private metadata items. Requires staff permissions to access."""
  privateMetadata: [MetadataItem!]!
}

type Fulfillment {
  """List of public metadata items. Can be accessed without permissions."""
  metadata: [MetadataItem!]!
  """List of private metadata items. Requires staff permissions to access."""
  privateMetadata: [MetadataItem!]!
}

type Checkout {
  """List of public metadata items. Can be accessed without permissions."""
  metadata: [MetadataItem!]!
  """List of private metadata items. Requires staff permissions to access."""
  privateMetadata: [MetadataItem!]!
}
```

- 字段说明：沿Base id:ID!、MetadataInput与listitemnonnull，key非空≤255、value字符串≤5000、单mutation≤100项为本方案保护值，重复keyINVALID；合法空list为无改（不清全部），delete只有显式keys。普通metadata可写，与I21readonlysnapshot分开。
- 权限：现行各业务域/ownercapability、对象/channel，private比public严格。HANDLE_TAXES仅相关字段/事件语境，不开放任意object私有数据；orderline同order范围。
- 错误：MetadataError.code INVALID/REQUIRED/NOT_FOUND/NOT_UPDATED与FORBIDDEN层，非法项/重复keys拒绝整mutation，保存失败不部分更新。
- 完成判定：合法键值整体原子保存，业务payloaderrors=[]及受权对象读回才success；事件on_commit按实质变化，failed不更新cache。
- 变更与兼容：基础已有读写/inline保留；无新order/fulfillment/warehousemetadata独立dialog/API/route，退出独立入口不删除此合同。

### I23 · 公开输入、分页、错误分层及关联查询
- 所属设计单元：BD16
- 提供方：saleor / graphql/core/scalars.py、fields/connection.py、core/federation/schema.py、order/account queryresolver
- 调用方：FD13及所有接口消费者、Federationrouter
- 目标定义：target-schema.graphql：`Query._entities`；`Minute`；`Hour`；`Day`

```graphql
type Query {
  _entities(representations: [_Any!]!): [_Entity]
}

"""
I23: a finite GraphQL integer number of minutes. Value must be nonnegative and fit signed 32-bit input bounds; field-specific maxima are checked before execution.
"""
scalar Minute

"""
I23: a finite GraphQL integer number of hours. Value must be nonnegative and fit signed 32-bit input bounds; field-specific maxima are checked before execution.
"""
scalar Hour

"""
I23: a finite GraphQL integer number of days. Value must be nonnegative and fit signed 32-bit input bounds; field-specific maxima are checked before execution.
"""
scalar Day
```

- 字段说明：Minute/Hour/Day必须有限非负32bit整数，delay另有0..10080；其他Scalar沿合法finite/currency规则，null/NaN/Inf拒绝。_entities representations=[_Any!]!，列表与每项nonnull，[]合法返回[]；每项必须对象/__typename与所需ID键正确，未知typename非法而不是没entity；输出按Base[_Entity]允许合法不存在为null。first/last必须1..100、互斥，null显式拒绝；before/after不能空/非法并按合法方向组合，未提供分页用有界默认20（技术选择）。
- 权限：所有root/node/nested/user.orders/federation有同对象/渠道/域scope；非存在与无权限分别处理，错误不回余额/地址/身份。
- 错误：GraphQLerrors包含message/path（coercion前无executionpath则可缺）和extensions.code：GRAPHQL_PARSE_FAILED、GRAPHQL_VALIDATION_FAILED、BAD_USER_INPUT、INVALID_ARGUMENT、INVALID_PAGE_SIZE、INVALID_CURSOR、FORBIDDEN、NOT_FOUND、INTERNAL_ERROR。mutation运行validation才使用errors[field/code/message]。未授权标准层，不人为补一个mutation对象；HTTP200不判断success。
- 完成判定：执行前全参数校验，未知error不吞成empty，无partialmutation。合法order条件单值/数组/组合与User.orders准确分页；不同ID类型/UUID/token/slug不相互替换。必须处理transport、GraphQL层、business层和asynccompletion四种状态。
- 变更与兼容：收紧原nullablefederationinput与负时间，合法单/数组原合同保留。旧显式nullpagination需要迁移，不能静默跳校验；完整target保留1338未变定义。

### I24 · 弃用、退出与必填迁移矩阵
- 所属设计单元：BD16
- 提供方：saleor / graphql/csv/schema.py、graphql/attribute/mutations、graphql/order draftinputs、graphql/app installation、paymentgatewayregistry
- 调用方：FD13/FD05/FD08和现有外部Storefront/App消费者
- 目标定义：target-schema.graphql：`Mutation.exportProducts,exportGiftCards,exportVoucherCodes`；`AttributeCreateInput.name,slug,type`；`AttributeUpdateInput.name,slug`；`DraftOrderCreateInput.voucher,voucherCode`；`DraftOrderInput.voucher,voucherCode`；`AppInstallInput`

```graphql
type Mutation {
  """
  Export products to csv file. 
  
  Requires one of the following permissions: MANAGE_PRODUCTS.
  
  Triggers the following webhook events:
  - NOTIFY_USER (async): A notification for the exported file.
  - PRODUCT_EXPORT_COMPLETED (async): A notification for the exported file.
  """
  exportProducts(
    """Fields required to export product data."""
    input: ExportProductsInput!
  ): ExportProducts @doc(category: "Products") @webhookEventsInfo(asyncEvents: [NOTIFY_USER, PRODUCT_EXPORT_COMPLETED], syncEvents: []) @deprecated(reason: "Use read-only Query.productsExport. Legacy mutation still creates an export job with the same permissions; errors do not indicate success.")
  """
  Export gift cards to csv file. 
  
  Requires one of the following permissions: MANAGE_GIFT_CARD.
  
  Triggers the following webhook events:
  - NOTIFY_USER (async): A notification for the exported file.
  - GIFT_CARD_EXPORT_COMPLETED (async): A notification for the exported file.
  """
  exportGiftCards(
    """Fields required to export gift cards data."""
    input: ExportGiftCardsInput!
  ): ExportGiftCards @doc(category: "Gift cards") @webhookEventsInfo(asyncEvents: [NOTIFY_USER, GIFT_CARD_EXPORT_COMPLETED], syncEvents: []) @deprecated(reason: "Use read-only Query.giftCardsExport. Legacy mutation still creates an export job with the same permissions; errors do not indicate success.")
  """
  Export voucher codes to csv/xlsx file.
  
  Added in Saleor 3.18.
  
  Note: this API is currently in Feature Preview and can be subject to changes at later point. 
  
  Requires one of the following permissions: MANAGE_DISCOUNTS.
  
  Triggers the following webhook events:
  - VOUCHER_CODE_EXPORT_COMPLETED (async): A notification for the exported file.
  """
  exportVoucherCodes(
    """Fields required to export voucher codes."""
    input: ExportVoucherCodesInput!
  ): ExportVoucherCodes @doc(category: "Discounts") @webhookEventsInfo(asyncEvents: [VOUCHER_CODE_EXPORT_COMPLETED], syncEvents: []) @deprecated(reason: "Use read-only Query.voucherCodesExport. Legacy mutation still creates an export job with the same permissions; errors do not indicate success.")
}

input AttributeCreateInput {
  """Name of an attribute displayed in the interface."""
  name: String!
  """Internal representation of an attribute name."""
  slug: String!
  """The attribute type."""
  type: AttributeTypeEnum!
}

input AttributeUpdateInput {
  """Name of an attribute displayed in the interface."""
  name: String
  """Internal representation of an attribute name."""
  slug: String
}

input DraftOrderCreateInput {
  """ID of the voucher associated with the order."""
  voucher: ID @deprecated(reason: "Use voucherCode. If both are supplied, execution rejects the ambiguous input.")
  """
  A code of the voucher associated with the order.
  
  Added in Saleor 3.18.
  """
  voucherCode: String
}

input DraftOrderInput {
  """ID of the voucher associated with the order."""
  voucher: ID @deprecated(reason: "Use voucherCode. If both are supplied, execution rejects the ambiguous input.")
  """
  A code of the voucher associated with the order.
  
  Added in Saleor 3.18.
  """
  voucherCode: String
}

input AppInstallInput @doc(category: "Apps") {
  """Name of the app to install."""
  appName: String!
  """URL to app's manifest in JSON format."""
  manifestUrl: String!
  """Determine if app will be set active or not."""
  activateAfterInstallation: Boolean = true
  """List of permission code names to assign to this app."""
  permissions: [PermissionEnum!]
}
```

- 字段说明：AttributeCreate name/slug/type !，空字符串运行INVALID；update提供null/空拒绝，省略保留，type创建后不可变。AppInstallname/URL !。draftnew只voucherCode；旧voucherdeprecated，仅可唯一转换时执行，双提供INVALID_VOUCHER_CODE。legacyexportsdeprecated仍ExportFilejob与errors。
- 权限：attribute域permission（PRODUCT_TYPES_AND_ATTRIBUTES或PAGE_TYPES_AND_ATTRIBUTES）、AppMANAGE_APPS、export对应I11domain和owner；不能借旧入口绕过。
- 错误：退出字段/操作GraphQL_VALIDATION_FAILED；旧gateway配置/调用明确NOT_SUPPORTED_GATEWAY/PAYMENT_ERROR迁移说明，非successnull。required/null/类型在schema层，其余INVALID/REQUIRED在域payload；旧voucher不唯一明确migrationerror不随机取。
- 完成判定：新Core打印SDL与target逐定义一致，新Dashboard先改源operations再codegen；空库与旧库迁移不重写completed金额、卡balance/库存、扩展settings/metadata资产。未实施不能宣称升级完成。
- 变更与兼容：保留deprecatedread：availableShippingMethods→shippingMethods、shippingMethod→deliveryMethod、totalCaptured→totalCharged、mount/target/options→currentfields及显式legacyexportjobs；移除Payment.partial、全部DigitalContent根操作/类型/ProductVariant.digitalContent/OrderLine.digitalContentUrl及Shop旧digitalsettings。Adyen/NP Atobarai不注册新支付能力，数据库历史Payment/Digital资产保留只作审计/迁移，不新建退出API。数字商品Apps/现行流程仍可提供。

### I25 · 敏感权限、员工真实删除与字段范围
- 所属设计单元：BD16
- 提供方：saleor / graphql/account/mutations/staff/staff_delete.py、account/utils.py、graphql/corepermissionchecks、checkout/order subscription sensitivefields
- 调用方：FD13 staff/attribute/App/export操作与合法taxApp、各领域消费者
- 目标定义：target-schema.graphql：`Mutation.staffDelete,attributeUpdate`；`Checkout.user,privateMetadata`；`Order.user,privateMetadata`

```graphql
type Mutation {
  """
  Deletes a staff user. Apps are not allowed to perform this mutation. 
  
  Requires one of the following permissions: MANAGE_STAFF.
  
  Triggers the following webhook events:
  - STAFF_DELETED (async): A staff account was deleted.
  """
  staffDelete(
    """ID of a staff user to delete."""
    id: ID!
  ): StaffDelete @doc(category: "Users") @webhookEventsInfo(asyncEvents: [STAFF_DELETED], syncEvents: [])
  """
  Updates attribute. 
  
  Requires one of the following permissions: MANAGE_PRODUCT_TYPES_AND_ATTRIBUTES.
  
  Triggers the following webhook events:
  - ATTRIBUTE_UPDATED (async): An attribute was updated.
  """
  attributeUpdate(
    """External ID of an attribute to update."""
    externalReference: String
    """ID of an attribute to update."""
    id: ID
    """Fields required to update an attribute."""
    input: AttributeUpdateInput!
  ): AttributeUpdate @doc(category: "Attributes") @webhookEventsInfo(asyncEvents: [ATTRIBUTE_UPDATED], syncEvents: [])
}

type Checkout {
  """
  The user assigned to the checkout. Requires one of the following permissions: MANAGE_USERS, HANDLE_PAYMENTS, OWNER.
  """
  user: User
  """List of private metadata items. Requires staff permissions to access."""
  privateMetadata: [MetadataItem!]!
}

type Order {
  """
  User who placed the order. This field is set only for orders placed by authenticated users. Can be fetched for orders created in Saleor 3.2 and later, for other orders requires one of the following permissions: MANAGE_USERS, MANAGE_ORDERS, HANDLE_PAYMENTS, OWNER.
  """
  user: User
  """List of private metadata items. Requires staff permissions to access."""
  privateMetadata: [MetadataItem!]!
}
```

- 字段说明：staffDelete签名仍id:ID!；payload按Base返回被删快照/errors，不以is_staff=false判断已删。税敏感user/private字段nullability保持但resolverpermissions增加相同scope，合法缺user返回null与fieldFORBIDDEN错误不同。
- 权限：staffMANAGE_STAFF+目标可管理groups/非self/非superuser规则；Base Apps不能删员工保留。attribute对应types/attrs权限、App安装MANAGE_APPS、exportI11。MANAGE_ORDERS/MANAGE_CHECKOUTS用于管理对象；HANDLE_TAXES只允许税业务需要的已选user/private字段且限被授权checkout/order及subscribingApp，不由另root/unrelatedApp绕过。客户仅自身允许public范围。
- 错误：自删DELETE_OWN_ACCOUNT、目标scopeOUT_OF_SCOPE_USER/permission及原AccountError；无权FORBIDDEN不回敏感字段/金额。查询数量、错误message、nested/event/export不能成为旁路。
- 完成判定：合法user实际delete，order/Payment/Transaction/events商业历史按SET_NULL/冻结actor保留；failed无删除/事件，成功on_commit一次STAFF_DELETED。身份删除后再node不存在，已关联order事实仍存在。
- 变更与兼容：修正account/utils有订单只downgrade行为，schema无新删除入口；强化所有入口统一scope，不恢复AppProblems。

### I26 · 草稿动作资格与展示真实值
- 所属设计单元：BD17
- 提供方：saleor / graphql/order/types.py、draft mutations与共享eligibilityvalidator（新增资格输出）
- 调用方：FD12 / OrderDraftDetails及合法订单App
- 目标定义：target-schema.graphql：`Order.canAddProducts,canFinalize,draftOrderProblems`；`DraftOrderProblem`；`DraftOrderActionEnum`

```graphql
type Order {
  canAddProducts: Boolean!
  """
  Informs whether a draft order can be finalized(turned into a regular order).
  """
  canFinalize: Boolean!
  draftOrderProblems: [DraftOrderProblem!]!
}

type DraftOrderProblem {
  code: OrderErrorCode!
  field: String!
  message: String!
  action: DraftOrderActionEnum!
}

enum DraftOrderActionEnum {
  ADD_PRODUCTS
  COMPLETE
}
```

- 字段说明：canAddProducts新Boolean!；canFinalize既有Boolean!复用最新validator；problems=[DraftOrderProblem!]!可[]，code OrderErrorCode、field/message/action必填，不含受限warehouse。ADD_PRODUCTS与COMPLETE前提分开；非draftcanAddProducts=false/problemlist=[]。Weight/Money/UTCdate/media维持现有native值，不新媒体pending/proxy状态。
- 权限：MANAGE_ORDERS及目标channel，商品选择MANAGE_PRODUCTS或现行合法ordercatalog范围；隐私字段仍I25。
- 错误：CHANNEL_INACTIVE、NOT_AVAILABLE_IN_CHANNEL、PRODUCT_NOT_PUBLISHED、NO_LINES用对应现有OrderErrorCode（空lines映REQUIRED，非新增无SDL码）、MISSING_ADDRESS_DATA、SHIPPING_METHOD_REQUIRED等；无权标准FORBIDDEN。
- 完成判定：按钮preflight读当前fact，提交重新检查，channelinactive/无商品/必要配置分别阻断对应动作；缺完成地址不误禁其它合法编辑。切合法channelquery重新获得允许，server资格改变仍拒绝。
- 变更与兼容：新增资格field，不更改重量/金额事实；普通single/bulkvariant、hasVariants、同步media/上传/video基础保留，无独立generator或异步imagefallback。

## 3. 其他

### 补充协议与不在SDL中表达的约束

| 文件 | 接口 | 作用 |
| --- | --- | --- |
| [interfaces/query-export-row-data.md](interfaces/query-export-row-data.md) | I11 | JSON row完整字段、Base ExportInfo投影、十进制/列表/缺省及脱敏code |
| [interfaces/editorjs-content.md](interfaces/editorjs-content.md) | I15 | 完整结构/HTML/URL/depth/size及field错误定位 |
| [interfaces/app-manifest.schema.json](interfaces/app-manifest.schema.json) | I16 | 规范化后的完整manifest；Basepermission/mount/target/event枚举来源 |
| [interfaces/app-installation.openapi.yaml](interfaces/app-installation.openapi.yaml) | I16 | 完整manifest GET与可选安装token POST，非Dashboardtoken响应 |
| [interfaces/extension-form-response.md](interfaces/extension-form-response.md) | I17 | postMessage完整envelope、frame/context/revision、ACK去重 |
| [interfaces/extensions-catalog.openapi.yaml](interfaces/extensions-catalog.openapi.yaml) | I18 | 静态目录完整OpenAPI及200/empty/404/503合同 |
| [interfaces/webhook-delivery.openapi.yaml](interfaces/webhook-delivery.openapi.yaml) | I19、I20 | 现行投递HTTP边界和新稳定事件ID，payloadshape由GraphQLselection限定 |

I16 manifest HTTP来源由appFetchManifest.manifestUrl决定：GET JSON验证上面的完整schema，沿用HTTPClientSSRFlimit/timeout。optional tokenTargetUrl接收现有POSTJSON `{ "auth_token": "<仅此配置目标可见>" }` 与Saleor现行headers，2xx才投递确认，未配置不创建/发送安装token；这不是向Dashboard返回token。token目标失败安装Job明确失败，既有有效update不破坏。settings额外动态规则（target匹配、relativeURL需appUrl、WIDGET仅支持7个widgetmount、App权限subset、identifierunique）在BD13/I16执行，JSONSchema不独自证明业务合法。

### 完整目标SDL的变化登记

所有新增/改变对外边界已分配I编号；同一类型跨多个合同的字段仍以具体字段归属，不能在两个文件另定义。

| 变化定义集合 | 权威接口 |
| --- | --- |
| CheckoutShippingRefresh/Mutation.refresh；CheckoutErrorCode；shipping/update/complete业务语义 | I01、I02 |
| StockAvailabilityStrategyEnum/StockSettings/Input | I03 |
| ProductAvailability*、AvailabilityCheck*、Query.diagnostics | I04 |
| Channel.settingsRevision/ChannelUpdateInput.expected、CheckoutSettings/Input、ChannelErrorCode.CONFLICT | I05 |
| CheckoutCompletionStatus*、Query.completionstatus | I06 |
| GiftCardTransaction*、GiftCardPaymentMethodDetails、GiftCard.balance新增、GiftCardEvent/Events、PaymentMethodTypeEnum.GIFT_CARD | I07 |
| OrderPaymentSummary/Order.paymentSummary、TransactionItem.availableamount、moneycommandkeys、Transaction/Payment/Order CONFLICT/error分支 | I08 |
| TransactionQueryFilterInput/ItemCountableConnection/Edge、Query.transactions、TransactionItem.appIdentifier及singletransaction定位 | I09 |
| GiftCardFilter.search、Checkout/GiftSort.RANK及主体/basicsearch语义 | I10 |
| Product/Gift/VoucherExport*、Query.currentexports | I11 |
| rootlockedfilter/where、bulklockedfilter/where和scope guard | I12 |
| PasswordAuthenticationModeEnum/Shop/Input.mode/revision、AccountErrorCode/ShopErrorCode新增 | I13 |
| OIDC JSON接口语义/Googleauthorize参数 | I14 |
| 内容JSON写入验证和全部富文本入口 | I15 |
| AppExtension/Manifest新名/settings/旧deprecated、filternewnames、AppInstallInputrequired、appCreate.issueToken/回token与appUpdate.manifestUrl升级语义 | I16 |
| 非GraphQLform/catalog协议 | I17、I18 |
| subscription解析/worker边界和eventID；EventDelivery/statuserror/retry | I19、I20 |
| Order/Fulfillmentmethodsnapshot/status、ordinarymetadata | I21、I22 |
| Minute/Hour/Day和federationnonnull/pagination/errors | I23 |
| Attributecreaterequired、Draftvoucherdeprecated、legacyexportsdeprecated、Payment.partial和DigitalContent旧字段/类型及Shop旧digitalsetting移除 | I24 |
| 真staffdelete、attribute/App/export/taxscope增强 | I25 |
| Order.canAddProducts/draftOrderProblems、DraftOrderProblem/Action、canFinalize资格 | I26 |

### 待落实与验证记录

Q01最终搜索一致性窗口仍需发布前确定，不用20秒scheduler冒充SLA；Q02单位/范围/默认与旧开关、Q03支持集/资源值、Q04完整SDL/错误/只读exports、Q05同源catalog已经作为技术选择固化；Q06provider幂等/reconcile适配实际测试通过才允许后台authcapture，成功Transaction/兼容已捕获Payment必须在范围。没有追问/补写冻结PRD。

实际已执行：Base parse 1408定义；目标parse/buildASTSchema/validateSchema通过，目标1433定义；59个Base定义变化、11个DigitalContent定义移除、36新增、1338未变定义逐AST print一致（完整文本未变片段原样保留）。所有本节GraphQL片段由目标AST提取并在生成时检查存在操作/字段，不手写另一版签名。代表性消费、负例与协议检查结果另见本节末最终检查记录。

未执行：源码实施、运行客户端生成、pytest/Jest/Playwright/迁移/Celery/PSP/Catalog部署与performance；schema静态有效不代表worker/安全/资金已通过验收。现有生成客户端与运行语义须实施阶段按FD13迁移，不能据source operation静态通过承诺所有历史调用已满足幂等和权限新约定。材料/PRD/测试只读，所有产物仅tech-design，检查脚本仅scratch。

### 最终实际检查（2026-10-14）

使用已安装 `graphql`、GraphQL tag pluck、Babel parser、YAML、Ajv/Ajv2020，仅执行设计静态检查，不联网、不启动应用、不写仓库。

| 检查 | 实际结果与边界 |
| --- | --- |
| 完整 SDL | 给定 Base 1408 定义；目标1433定义，parse/buildASTSchema/validateSchema通过。59个Base定义变化（含资金/投递权限说明对齐）、11个DigitalContent旧定义移除、36新增、1338未变定义逐AST一致；未变原文本段完整保留。没有读取未来版本schema。 |
| 代表性新/保留消费 | 26份独立operation全部validate通过：12 Query、12 Mutation、2 Subscription，覆盖配置、配送重算/选择/完成、诊断、自动结果、礼品卡、金额/资金动作、根交易、主体搜索、查询导出、locked/bulk完整scope、密码/OIDC、扩展、安装/升级、delivery、快照/draft、federation及事件selection。 |
| 明确拒绝负例 | 18例全部在schema层如预期拒绝：Payment.partial、DigitalContent根/variant/orderline/Shop旧设置、AppProblems、Page/User RANK、交易sort/date/event筛选、ID数组null项、federation null列表/元素、Attribute.slug与App必填缺省、礼品卡key缺省。自定义scalar的值范围、分页数值/游标、权限/幂等为runtime约束，未以validate替代其测试。 |
| 现行Dashboard源消费 | 从122个生产源码文件静态抽取402个operation、241个fragment，按每个operation递归闭包校验：Base 401通过、目标402通过，pluck无错误，新目标未新增schema校验失败。现行ExtensionList在Base因mountName/targetName/settings失败，目标通过。抽取排除generated/tests/fixtures，不能外推为所有Storefront/App操作已适配。现行资金operation缺新runtime key仍须迁移；generated中的DigitalContent及旧Shop输入须重新生成清理。 |
| 契约与模板 | 26个I单元、103个SDL selector均存在；24个GraphQL片段parse通过、269个字段签名与目标AST逐项一致。FD01—13、BD01—17、BT01—10、I01—26连续唯一；三文档模板章节齐全；前后端均引用R01—31且明确前端不直接承接项，补充协议本地链接存在。 |
| Manifest JSON Schema | Ajv2020编译通过；11样例按预期通过/拒绝。合法省略tokenTargetUrl、保留webhook isActive/customHeaders；未知字段、缺标识、非法permission/target/settings、互斥设置、URL null及类型错拒绝。defaults为规范化实现责任，不声称JSONschema引擎会自动保存默认值；identity唯一、URL/target匹配与权限子集未执行runtime测试。 |
| OpenAPI与原生数据 | 3份OpenAPI YAML parse、顶层/路径/响应必要字段、operationId唯一及本地/外部文件引用检查通过，共4个HTTPoperation；未安装/未运行完整OpenAPI规范验证器。目录schema用本地转换为JSON Schema后校验6样例，token请求schema校验3样例，均符合预期。格式校验仅本地绝对URI/URI-reference/UUID，不能证明HTTPS/CORS/SSRF运行安全。 |
| frame协议 | 5个TypeScript envelope（Hello/Ready/Context/Response/ACK）语法parse通过；I11 JSON row的TypeScript完整字段定义也parse通过，未运行resolver投影/文件生成测试；origin/source、版本协商、去重/revision和关闭处理是明确合同，未运行浏览器postMessage安全/组件测试。EditorJS结构/URL协议已与Base工具及fixture核对，未实现或执行清理器，L/L+1/攻击链接不能称已验收。 |

设计收尾发现并已在当前文件/目标中修正的差异：Base appUpdate只有基础资料input，新增可选manifestUrl补齐同App升级；bulk旧参数无法表达当前普通筛选，新增filter/where/search/channel并与锁条件取交集；manifest严格schema补回Base合法isActive/customHeaders；legacy Webhook订单payload可能是对象数组，HTTP描述保留；重试回执实际字段是delivery，消费者样例已修正；Base iframe onLoad直接发token不等于已鉴别notifyReady，FD08/I17明确停止该绕过路径。没有修改封存PRD、冻结测试或应用源代码。

静态检查脚本/详细JSON结果位于 `/workspace/scratch/build-target-schema.cjs`、`/workspace/scratch/build-contract.cjs`、`/workspace/scratch/validate-design.cjs`、`/workspace/scratch/final-validation.json`，代表性操作在 `/workspace/scratch/representative-operations.graphql`。这些是本次设计验证证据，不是应用交付代码；实施与发布验收仍按BT01—10执行。

