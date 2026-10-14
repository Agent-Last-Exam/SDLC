# 接口对齐文档：Saleor Core 与 Dashboard 3.23 协调升级

版本：v1
责任：后端技术设计
依据：后端技术设计 v1，backend-design.md
修订：首次交付

## 1. 通用约定

- **入口**：GraphQL 单端点 `POST /graphql/`（core 仓库 `saleor/graphql/api.py` 装配）；Dashboard 经 Apollo Client（`src/graphql/client.ts`）访问。目标 SDL 的权威文件为 `target-schema.graphql`（完整 35,185 行 SDL，本轮改动后由 core 重新生成并同步为 Dashboard 仓库根 `schema.graphql`）。
- **认证**：staff 用户使用 JWT（`Authorization: Bearer`）；App 使用 App Token（`Authorization: Bearer <app-token>`）； storefront 匿名消费者仅限公开查询。App Extension 场景由 Dashboard 在 URL/表单参数中附带 `accessToken`（extension JWT）。
- **错误分层**：(a) schema/语法错误——GraphQL 校验错误，`data` 为 null；(b) 业务错误——各 mutation 的 `errors: [<Domain>Error!]!` 数组返回（`field`/`code`/`message`），HTTP 200；(c) 权限错误——相应 `*Error.code`（如 `PermissionDeniedErrorCode`）或字段级 null（按字段可空性）。
- **ID 规则**：所有对象 ID 为全局 ID（`relay` 风格 base64 `"TypeName:PK"`）；输入中的 ID 参数均按全局 ID 解析（`graphene.relay` 解码），类型不匹配返回业务错误。
- **成功判定**：mutation 返回 `errors` 为空且载荷字段非 null（按各 mutation 返回类型）；查询以 `data` 正常返回为准；异步副作用（webhook、celery 任务）以各自事件/任务可见性为准。
- **废弃约定**：`filter` 参数、`attribute`/`attributes`、`mount`/`target`/`options` 等废弃项以 `@deprecated` 标注保留可用，本轮不删除任何既有字段（R11）。

## 2. 接口契约

### I01 · orders 查询 where/search/排序
- 所属设计单元：BD03
- 提供方：core 仓库 `/workspace/repos/saleor/saleor/graphql/order/schema.py`（`orders` 字段）、`saleor/graphql/order/filters.py:974`（`OrderWhereInput`）、`saleor/graphql/order/sorters.py:9`（`OrderSortField.STATUS`）
- 调用方：Dashboard `/workspace/repos/saleor-dashboard/src/orders/queries.ts`（`$where: OrderWhereInput`、`$search: String`）；外部消费者：任何 staff/App API 客户端
- 目标定义：target-schema.graphql 中 `Query.orders`、`OrderWhereInput`（及其嵌套输入）、`OrderSortField`、`OrderCountableConnection`

```graphql
orders(
  # ...分页参数...
  sortBy: OrderSortingInput
  filter: OrderFilterInput @deprecated(reason: "Use `where` and `search` instead.")  # 含 DEPRECATED_IN_3X_INPUT 前缀说明
  where: OrderWhereInput
  search: String
  # ...channel 参数...
): OrderCountableConnection
```

- 字段说明：
  - `where`：`OrderWhereInput`，支持 `AND`/`OR`/`NOT` 组合与 `eq`/`oneOf`/`range` 操作符；字段覆盖既有 filter 项（`ids`、`channelId`、`customer`、`createdAt`、`updatedAt`、`status`、`authorizeStatus`、`chargeStatus`、`paymentStatus`、`isClickAndCollect`、`isPreorder`、`checkoutToken`、`checkoutId`、`isGiftCardUsed`、`isGiftCardBought`、`number`、`metadata`）与扩展项（`user`、`userEmail`、`voucherCode`、`hasInvoices`、`invoices`、`hasFulfillments`、`fulfillments`、`lines`、`linesCount`、`transactions`（`PaymentMethodDetailsFilterInput`）、`totalGross`、`totalNet`、`productTypeId`、`events`、`billingAddress`、`shippingAddress`）。列表参数为可空输入列表，项不可空。
  - `search`：独立 `String` 参数，PostgreSQL 全文检索（websearch 模式），结果按权重 A（订单号/ID/用户邮箱/姓名）→ B（客户备注/外部引用/地址字段）→ C（订单行字段，限 `SEARCH_ORDERS_MAX_INDEXED_LINES`）→ D（折扣名/支付与交易 PSP 引用/发票 ID/订单事件消息，各受 `SEARCH_ORDERS_MAX_INDEXED_*` 限制）排序。
  - `sortBy.field` 新增/包含 `STATUS`（按订单状态排序）。
  - `filter`：deprecated 但功能与 3.22 一致。
- 权限：`MANAGE_ORDERS`（staff 或具有该权限的 App）。
- 错误：未知 `where` 字段在 schema 校验期报 GraphQL 错误；操作符与类型不匹配（如对 enum 用 `range`）同为校验错误；无权限返回权限错误。
- 完成判定：查询即读即得，无写副作用；排序/过滤结果在响应 `edges` 中最终可见。
- 变更与兼容：相对 Base 无契约变化（本轮冻结现状）；旧消费者继续使用 `filter` 不受影响。

### I02 · draftOrders 与 pages 查询 where/search
- 所属设计单元：BD04
- 提供方：core 仓库 `saleor/graphql/order/schema.py`（`draftOrders`）、`saleor/graphql/order/filters.py:1084`（`DraftOrderWhereInput`）；`saleor/graphql/page/schema.py:60-66`、`saleor/graphql/page/filters.py:756`（`PageWhereInput`）
- 调用方：Dashboard `src/orders/`（草稿订单列表）、`src/modeling/`（Models 页面列表）；外部 staff/App 客户端
- 目标定义：target-schema.graphql 中 `Query.draftOrders`（`DraftOrderWhereInput`）、`Query.pages`（`PageWhereInput`、`search`）

```graphql
draftOrders(
  sortBy: OrderSortingInput
  filter: OrderDraftFilterInput @deprecated(reason: "Use `where` and `search` instead.")
  where: DraftOrderWhereInput
  search: String
  # ...分页参数...
): OrderCountableConnection

pages(
  sortBy: PageSortingInput
  filter: PageFilterInput @deprecated(reason: "Use `where` and `search` instead.")
  where: PageWhereInput
  search: String
  # ...分页参数...
): PageCountableConnection
```

- 字段说明：
  - `DraftOrderWhereInput`：含 `ids`、`number`、`updatedAt`、`user`、`userEmail`、`authorizeStatus`、`chargeStatus`、`isClickAndCollect`、`voucherCode`、`lines`、`linesCount`、`transactions`、`totalGross`、`totalNet`、`productTypeId`、`events`、`billingAddress`、`shippingAddress`、`channelId`、`customer`、`createdAt`、`metadata`；**不含** `status`、`checkoutToken`、`checkoutId`、`isGiftCardUsed`、`isGiftCardBought`、`hasInvoices`、`invoices`、`hasFulfillments`、`fulfillments`（schema 级不存在即拒绝）。
  - `PageWhereInput`：`ids`、`pageType`、`slug`、`metadata` 与属性过滤 `attributes`（数值 `eq`/`oneOf`/`range`、布尔、日期/日期时间、引用属性按 ID/slug、`containsAll`/`containsAny`）。
  - 两查询的 `search`：draftOrders 与 orders 语义一致；pages 在标题/slug/内容上检索（与原 `filter.search` 相同）。
- 权限：`MANAGE_ORDERS`（draftOrders）、`MANAGE_PAGES`（pages）。
- 错误：同 I01 分层；pages 引用属性过滤的 ID/slug 无法解析时按空结果集处理（不报错）。
- 完成判定：即读即得。
- 变更与兼容：无契约变化（冻结现状）；`filter` 继续可用。

### I03 · 属性体系：SINGLE_REFERENCE / referenceTypes / AssignedAttribute / choices
- 所属设计单元：BD05
- 提供方：core 仓库 `saleor/graphql/attribute/types.py`（`Attribute.referenceTypes`、`Attribute.choices`）、`saleor/graphql/attribute/schema.py`、`saleor/graphql/attribute/mutations/`（create/update/bulkCreate/bulkUpdate）、`saleor/graphql/attribute/types/`（`AssignedAttribute` 接口族）
- 调用方：Dashboard `src/attributes/`、`src/products/`（属性赋值界面）、`src/modelTypes/`、`src/modeling/`；外部 App 客户端
- 目标定义：target-schema.graphql 中 `AttributeInputTypeEnum.SINGLE_REFERENCE`、`AttributeEntityTypeEnum`（含 `CATEGORY`、`COLLECTION`）、`Attribute.referenceTypes`、`AttributeCreateInput.referenceTypes`、`AttributeUpdateInput.referenceTypes`、`AssignedAttribute` 接口与 `Assigned*Attribute` 实现类型、`Page/Product/ProductVariant.assignedAttribute(s)`、`Attribute.choices(where, search)`

```graphql
type Attribute implements Node @doc(category: "Attributes") {
  # ...既有字段...
  referenceTypes(
    # ...分页参数...
  ): ReferenceTypeCountableConnection  # 实际为 ProductType | PageType union 连接，以 SDL 为准
  choices(
    sortBy: AttributeChoicesSortingInput
    filter: AttributeChoiceFilterInput @deprecated(reason: "Use `where` and `search` instead.")
    where: AttributeChoiceWhereInput
    search: String
    # ...分页参数...
  ): AttributeValueCountableConnection
}

input AttributeCreateInput {
  # ...既有字段（含 inputType 可取值 SINGLE_REFERENCE、entityType 可取 CATEGORY/COLLECTION）...
  referenceTypes: [ID!]
}

interface AssignedAttribute @doc(category: "Attributes") {
  attribute: Attribute!
}

type Page implements Node & ObjectWithMetadata {
  assignedAttribute(slug: String!): AssignedAttribute
  assignedAttributes: [AssignedAttribute!]!
  attribute(slug: String!): SelectedAttribute @deprecated(reason: "Use the `assignedAttribute` field instead.")
  attributes: [SelectedAttribute!]! @deprecated(reason: "Use the `assignedAttributes` field instead.")
}
# Product / ProductVariant 同型
```

- 字段说明：
  - `referenceTypes`：`Attribute` 输出为限定类型连接（`PRODUCT`/`PRODUCT_VARIANT` 实体返回 ProductType 集合，`PAGE` 实体返回 PageType 集合）；输入为 `[ID!]` 全局 ID 列表，未设置（null）表示不限定。
  - `SINGLE_REFERENCE`：单值引用，赋值时仅允许一个引用对象；`REFERENCE` 行为不变。
  - `AssignedAttribute` 接口实现族：`AssignedNumericAttribute`、`AssignedTextAttribute`、`AssignedPlainTextAttribute`、`AssignedFileAttribute`、`AssignedSingleChoiceAttribute`、`AssignedMultiChoiceAttribute`、`AssignedSwatchAttribute`、`AssignedSingleReferenceAttribute` 等（完整清单以 SDL 为准），各自携带类型化 `value`。
  - `choices` 的 `where`：`AttributeChoiceWhereInput`（`ids`、`slug`、`name`，操作符 `eq`/`oneOf`）；`search` 匹配名称与 slug。
- 权限：`MANAGE_PRODUCTS`/`MANAGE_PAGES`/`MANAGE_PRODUCT_TYPES_AND_ATTRIBUTES`（按属性归属与操作类型）。
- 错误：`referenceTypes` 传入非全局 ID、类型与 `entityType` 不匹配（如 PAGE 实体传 ProductType ID）→ `AttributeError`（`INVALID` 类 code）；`SINGLE_REFERENCE` 赋多个引用 → 赋值校验错误。
- 完成判定：mutation `errors` 为空且返回对象持久化生效；`attribute` 查询立即可见。
- 变更与兼容：无契约变化（冻结现状）；废弃 `attribute`/`attributes` 字段保留可用。

### I04 · RefundSettings 与退款 mutation 的 reasonReference 规则
- 所属设计单元：BD07
- 提供方：core 仓库 `saleor/graphql/shop/schema.py`（`refundSettings`）、`saleor/graphql/shop/mutations/`（`refundSettingsUpdate`、`refundReasonReferenceTypeClear`）、`saleor/graphql/order/mutations/`（`orderGrantRefundCreate`、`orderGrantRefundUpdate`、`orderRefund`、`fulfillmentRefundProducts`）、`saleor/graphql/payment/mutations/`（`transactionRequestAction`）
- 调用方：Dashboard `src/refundsSettings/`（配置）、`src/orders/components/`（退款表单）；外部 App（退款类 mutation，免强制原因）
- 目标定义：target-schema.graphql 中 `Query.refundSettings`、`refundSettingsUpdate`、`refundReasonReferenceClear`、`OrderGrantRefundCreateInput.reasonReference`（及其余四个 mutation 的对应输入）

```graphql
type Query {
  refundSettings: RefundSettings! @doc(category: "Shop")
}

refundSettingsUpdate(
  input: RefundSettingsUpdateInput!   # { refundReasonReferenceType: ID! }（PageType 全局 ID）
): RefundSettingsUpdate

refundReasonReferenceClear: RefundReasonReferenceTypeClear

input OrderGrantRefundCreateInput {
  # ...amount、lines 等既有字段...
  reason: String
  reasonReference: ID   # Page（Model）全局 ID，类型须等于已配置的 reference type
}
# orderGrantRefundUpdate / orderRefund / fulfillmentRefundProducts / transactionRequestAction 同型携带 reasonReference
```

- 字段说明：
  - `RefundSettings.reasonReferenceType`：`PageType`，可空（未配置）。
  - `reasonReference`：可空输入；配置生效期间 staff 必填，且解析出的 Page 的 `page_type` 必须等于配置的 `reasonReferenceType`。
- 权限：配置 mutation 需 `MANAGE_SETTINGS`；退款类 mutation 需 `MANAGE_ORDERS`；App 身份调用退款 mutation 不强制要求 `reasonReference`。
- 错误：已配置原因类型时 staff 未提供 `reasonReference` → 退款 mutation `errors[].code` 为必填类错误（field=`reasonReference`）；引用对象不存在或 PageType 不符 → 校验类错误；`refundReasonReferenceClear` 执行后再传 `reasonReference` → 明确报错（拒绝接受）；`refundSettingsUpdate` 传入非 PageType ID → `RefundSettingsUpdateError`。
- 完成判定：配置 mutation `errors` 为空后 `shop.refundSettings` 立即可见；退款 mutation `errors` 为空即退款已按既有事务语义持久化（订单事件、金额计算不变）。
- 变更与兼容：无契约变化（冻结现状）；未配置时行为与 3.22 完全一致。

### I05 · TransactionItem.paymentMethodDetails 与 Money 分数字段
- 所属设计单元：BD08
- 提供方：core 仓库 `saleor/graphql/payment/types.py:467`（`PaymentMethodDetails` 接口）、`:486`/`:531`（实现类型）、`:646`（`resolve_payment_method_details`）；交易 mutation（`transactionCreate`/`transactionUpdate`/`transactionEventReport`）；`saleor/webhook/` 交易同步事件处理；`saleor/graphql/core/types/money.py`（`Money`）
- 调用方：Dashboard `src/ordersV2/`、`src/orders/components/`（交易区块，只读消费）；外部支付类 App（写入）
- 目标定义：target-schema.graphql 中 `PaymentMethodDetails`、`CardPaymentMethodDetails`、`OtherPaymentMethodDetails`、`TransactionItem.paymentMethodDetails`、`TransactionCreateInput.paymentMethodDetails`（及 Update/EventReport 同型输入）、`PaymentMethodDetailsFilterInput`、`Money.fractionalAmount`/`fractionDigits`

```graphql
interface PaymentMethodDetails {
  name: String
}

type CardPaymentMethodDetails implements PaymentMethodDetails {
  name: String
  brand: String
  firstDigits: String
  lastDigits: String
  expMonth: Int
  expYear: Int
}

type OtherPaymentMethodDetails implements PaymentMethodDetails {
  name: String
}

type TransactionItem implements Node & ObjectWithMetadata {
  paymentMethodDetails: PaymentMethodDetails
  # ...既有字段...
}

input PaymentMethodDetailsInput {
  card: CardPaymentMethodDetailsInput
  other: OtherPaymentMethodDetailsInput
}

type Money {
  amount: Float!
  currency: String!
  fractionalAmount: Int!
  fractionDigits: Int!
}
```

- 字段说明：
  - `paymentMethodDetails` 输入二选一（`card` 或 `other`）；输出按存储类型解析为对应实现类型（`__typename` 区分）。
  - `Money.fractionalAmount`：最小货币单位整数（USD 12.95 → 1295）；`fractionDigits`：货币小数位（USD 2、JPY 0）。
  - 订单/草稿订单过滤：`OrderWhereInput.transactions: PaymentMethodDetailsFilterInput`（按支付方式名称/类型与 card 子字段过滤），仅命中写入过明细的交易。
- 权限：`TransactionItem` 读取跟随订单权限（`MANAGE_ORDERS`）；交易 mutation 按 App/staff 既有权限。
- 错误：输入同时提供 `card` 与 `other` → 校验错误；card 字段格式非法（如非数字位串）→ 校验错误。
- 完成判定：mutation `errors` 为空即明细随交易持久化；同步 webhook 响应携带明细时在事务提交后可见；`Money` 两字段在任意金额查询中即时返回。
- 变更与兼容：无契约变化（冻结现状）；未写入明细的旧交易 `paymentMethodDetails` 返回 null。

### I06 · AppExtension/AppManifestExtension 新增 mountName/targetName/settings（本轮唯一 schema 变更）
- 所属设计单元：BD06
- 提供方：core 仓库 `saleor/graphql/app/types.py`（`AppExtension`、`AppManifestExtension` 类型与 resolver，本轮修改）；底层模型 `saleor/app/models.py:156`（`AppExtension.mount`/`target`/`http_target_method` 既有列）；校验 `saleor/app/manifest_validations.py`（不变）
- 调用方：Dashboard `src/extensions/queries.ts`（`extensionList` 已消费 `mountName`/`targetName`/`settings`）、`src/extensions/hooks/useExtensions.ts`、`src/extensions/components/AppWidgets/AppWidgets.tsx`；外部 App 安装流程（`appInstallations` 返回 `AppManifestExtension`）
- 目标定义：target-schema.graphql 中 `AppExtension`、`AppManifestExtension`、`AppExtensionOptionsWidget`/`AppExtensionOptionsNewTab`/`WidgetTargetOptions`/`NewTabTargetOptions` 的废弃标注、`scalar JSON`

```graphql
type AppExtension implements Node @doc(category: "Apps") {
  id: ID!
  permissions: [Permission!]!
  label: String!
  url: String!
  mount: AppExtensionMountEnum! @deprecated(reason: "Use `mountName` instead.")
  target: AppExtensionTargetEnum! @deprecated(reason: "Use `targetName` instead.")
  mountName: String!        # Added in Saleor 3.22 — mount 的字符串原值（如 "order_details_widgets"）
  targetName: String!       # Added in Saleor 3.22 — target 的字符串原值（如 "new_tab"）
  settings: JSON!           # Added in Saleor 3.22 — NEW_TAB: {"newTabTarget":{"method":"GET"|"POST"}}；WIDGET: {"widgetTarget":{"method":"GET"|"POST"}}；其余: {}
  app: App!
  accessToken: String
  options: AppExtensionPossibleOptions @deprecated(reason: "Use `settings` field instead.")
}

type AppManifestExtension @doc(category: "Apps") {
  permissions: [Permission!]!
  label: String!
  url: String!
  mount: AppExtensionMountEnum! @deprecated(reason: "Use `mountName` instead.")
  target: AppExtensionTargetEnum! @deprecated(reason: "Use `targetName` instead.")
  mountName: String!
  targetName: String!
  settings: JSON!           # manifest options 原样（缺省 {}）
}

type AppExtensionOptionsWidget @doc(category: "Apps") {
  widgetTarget: WidgetTargetOptions @deprecated(reason: "Use `settings` field directly.")
}
type WidgetTargetOptions @doc(category: "Apps") {
  method: HttpMethod! @deprecated(reason: "Use `settings` field directly.")
}
type AppExtensionOptionsNewTab @doc(category: "Apps") {
  newTabTarget: NewTabTargetOptions @deprecated(reason: "Use `settings` field directly.")
}
type NewTabTargetOptions @doc(category: "Apps") {
  method: HttpMethod! @deprecated(reason: "Use `settings` field directly.")
}
```

- 字段说明：
  - `mountName`/`targetName`：非空 String，值分别为 `mount`/`target` 枚举的底层字符串（与 manifest 中使用的名称一致），供 Dashboard 直接做字符串匹配。
  - `settings`：非空 JSON（`GenericScalar`，codegen 映射为 `JSON: any`）；由既有存储推导，`http_target_method` 为 NULL 时回退 `"GET"`（与既有 `options` resolver 语义一致）；对 `POPUP`/`APP_PAGE` 返回 `{}`。
  - 废弃字段保持原 resolver 与原返回类型，仅新增 `@deprecated` 标注。
- 权限：与 `AppExtension` 既有可见性一致（staff 用户与拥有该 app/extension 的 App 可读），新字段不扩大可见面。
- 错误：无新增错误模式；resolver 为纯派生逻辑。manifest 安装期目标/挂载点组合错误仍由 `manifest_validations.py` 以既有 `AppManifestError` 返回（如 `widgetTarget options must be set only on WIDGET target`）。
- 完成判定：`appExtensions`/`appInstallations` 查询返回新字段且与旧字段语义一致；Dashboard `extensionList` 查询对升级后服务端直接成功（消除当前对 3.22 服务端的报错）。
- 变更与兼容：**Base→Target 的唯一 schema diff**（新增 3 字段 ×2 类型 + 8 处 `@deprecated` 标注 + `scalar JSON` 位置归整）；旧消费者继续用 `mount`/`target`/`options` 不受影响；Dashboard 基线代码已是新消费者，无需迁移改动。

### I07 · 版本声明（非 GraphQL）
- 所属设计单元：BD01、FD01
- 提供方：core `saleor/__init__.py`（`__version__`/`schema_version`）、`pyproject.toml`；dashboard `package.json`（`version`、`config.saleor.schemaVersion`）
- 调用方：部署/运维工具链、Dashboard `fetch-schema` 脚本、评估环境
- 目标定义：非 GraphQL 接口，无 SDL 片段。目标值：`saleor.__version__ == "3.23.0"`、`saleor.schema_version == "3.23"`、`package.json#version == "3.23.0"`、`package.json#config.saleor.schemaVersion == "3.23"`。
- 字段说明：`schema_version` 为 `__version__` 的 `major.minor` 推导值，非独立声明。
- 权限：只读仓库声明，无运行时权限语义。
- 错误：无。
- 完成判定：两个仓库声明一致且均为 3.23/3.23.0；core 服务正常启动。
- 变更与兼容：纯声明变更，无行为差异；不影响任何 API 消费者。

## 3. 其他

- **无法用 SDL 表达的语义**：
  - I01/I02 的 `search` 权重排序（A–D 权重与 `SEARCH_ORDERS_MAX_INDEXED_*` 上限）为 resolver 层行为，SDL 仅体现参数存在；以上权重表即权威语义。
  - I04 的"staff 必填 / App 豁免 / 清除后传入即报错"三分支规则依赖调用方身份与全局配置的运行时组合，SDL 中 `reasonReference` 只能声明为可空 `ID`。
  - I06 的 `settings` JSON 内部结构（`newTabTarget.method`/`widgetTarget.method`）为约定结构，由本文件文字部分与 Dashboard 消费代码共同约束；`JSON` 标量在 codegen 中映射为 `any`（dashboard `types.generated.ts:42`）。
- **跨端一致性核对记录**：`target-schema.graphql` 与 Dashboard 基线 `schema.graphql`（消费面）逐字节一致；core 基线 schema 与 target 的 64 行差异全部位于 `AppExtension`/`AppManifestExtension`/`AppExtensionOptions*`（即 I06 范围），BD06 完成后 core 重生成 schema 必须与 target 一致。
- **实际执行的检查**：`graphql@16.11.0`（dashboard node_modules）`buildSchema` 解析 target-schema 通过（1418 个命名类型）；关键类型/字段断言脚本全部通过（AppExtension 新字段及 deprecated 标注、Money 分数字段、orders where/search/filter 参数、退款 mutation、paymentMethodDetails、mount/target 枚举、SINGLE_REFERENCE、CATEGORY/COLLECTION 实体类型、referenceTypes、assignedAttribute(s)）。
- **未运行的检查**：未执行 core 端 `schema.graphql` 重生成（属实施阶段 BT02）；未执行 `graphql-codegen`（属 FD01 实施）；未运行任何测试套件（本阶段不开发）。
- **未决项**：无阻塞未决项；若官方测试揭示 CHANGELOG 未覆盖的 3.23 契约差异，按 PRD 第 5 节假设在修复阶段修订本文档（编号沿用，新增顺延至 I08）。
