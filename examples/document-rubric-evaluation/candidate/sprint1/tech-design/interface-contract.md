# 接口对齐文档：Saleor 商家经营与应用接入升级

版本：v1
责任：后端技术设计
依据：后端技术设计 v1，backend-design.md
修订：首次交付

## 1. 通用约定

- GraphQL 入口沿用 Saleor Base 的 `/graphql/`；完整权威 SDL 为同目录 `target-schema.graphql`。下文片段只用于解释语义，不替代完整 SDL。
- ID 沿用 Relay Global ID；UUID token 和幂等键使用 `UUID`。时间按 UTC `DateTime` 传输，金额由 `Money` 返回、输入金额用 `PositiveDecimal`，币种用 ISO 4217 字符串且不跨币种求和。
- 查询分页沿用 Relay `before/after/first/last`，单页上限 100。默认排序在业务字段后追加唯一主键作为稳定 tie-breaker。
- mutation 的参数/业务错误进入 payload `errors`；认证或顶层权限错误沿用 Saleor GraphQL 权限错误。失败 mutation 不产生部分字段写入；跨外部资金系统的部分成功通过来源分配状态显式表达。
- 输入字段省略表示“保持既有值”；只有契约明确允许的 `null` 才表示清空。列表与列表项的可空性以 SDL 为准；`[T!]!` 表示列表和列表项都不可空。
- 新通知采用至少一次投递。`eventId` 标识逻辑事件，重试保持不变；`EventDelivery.id` 标识对某 Webhook 的投递，attempt 递增。接收方必须按 `eventId` 幂等。
- 所有字段先执行对象权限和渠道隔离，再解析 subscription selection；`privateMetadata`、完整卡码、密码、长期凭证及无关人员信息不进入无权响应或通知。

## 2. 接口契约

### I01 · Shop 经营资料与密码策略
- 所属设计单元：BD01、BD08
- 提供方：`saleor/graphql/shop/schema.py`、`shop_settings_update.py`、`shop_address_update.py`、`shop_domain_update.py`；`Shop.passwordLoginPolicy` 为拟新增字段
- 调用方：`saleor-dashboard/src/siteSettings/`（FD01）、`src/auth/`（FD07）；匿名认证页面可读取策略
- 目标定义：`Shop`、`ShopSettingsInput`、`shopSettingsUpdate`、`shopAddressUpdate`、`shopDomainUpdate`、`PasswordLoginPolicyEnum`

```graphql
enum PasswordLoginPolicyEnum { ALL CUSTOMERS_ONLY DISABLED }
extend type Shop { passwordLoginPolicy: PasswordLoginPolicyEnum! }
```

- 字段说明：经营名称继续由 `shopDomainUpdate(input.name)` 更新，省略 `domain` 不改变域名；介绍/页头、sender 和 metadata 由 `shopSettingsUpdate` 更新；公司名称属于 `AddressInput.companyName`。策略来自实例部署配置，只读且不可通过 Dashboard mutation 修改。
- 权限：策略和外部认证方式允许匿名读取；经营普通字段和公共/私有 metadata 修改要求 `MANAGE_SETTINGS`；私有 metadata 读取仍按 Base 权限裁剪。
- 错误：地址、邮箱、换行 sender 和空值错误沿用 `ShopError` 并定位 `field`；密码入口新增 `PASSWORD_LOGIN_DISABLED`、`PASSWORD_LOGIN_STAFF_DISABLED`。
- 完成判定：资料和地址是两个独立 mutation，各自在单一数据库事务提交并登记 outbox 后成功；一项失败不回滚另一项，也不得被 Dashboard 报为整体成功。
- 变更与兼容：保留现有 mutation 和字段；新增只读策略和 `SHOP_UPDATED`、`SHOP_ADDRESS_UPDATED` 事件，不把展示名称与域名合并提交。

### I02 · 受限外部图片导入
- 所属设计单元：BD02
- 提供方：`saleor/graphql/product/mutations/product/product_media_create.py`、bulk product media 路径、`saleor/app/installation_utils.py`；统一下载器拟新增于 `saleor/core/files/remote_image.py`
- 调用方：既有 Product media mutation 消费者与应用安装流程；Dashboard 商品媒体页（FD02）
- 目标定义：保留既有 `productMediaCreate`/bulk 操作，扩展 `ProductErrorCode`

```graphql
extend enum ProductErrorCode {
  REMOTE_FETCH_FAILED
  REMOTE_FILE_TOO_LARGE
  INVALID_IMAGE
}
```

- 字段说明：URL 输入及成功输出不变；GET 实际内容是权威来源，HEAD 仅可优化。默认限制为 20 MiB、4000 万像素和总预算 20 秒。
- 权限：沿用媒体创建和应用安装权限；下载器只允许生产策略许可的公网 HTTP/HTTPS。
- 错误：超时/非成功响应为 `REMOTE_FETCH_FAILED`，字节或像素超限为 `REMOTE_FILE_TOO_LARGE`，损坏、网页或不支持格式为 `INVALID_IMAGE`，错误均定位 URL/input 字段。
- 完成判定：实际解码、安全校验和存储成功后才创建媒体记录；失败无媒体记录和孤立文件。
- 变更与兼容：不再因扩展名、Content-Type 或 HEAD 失败拒绝合法图；仍不自动跟随 3xx，也不放宽 SSRF 过滤。

### I03 · 搜索索引任务可观测接口
- 所属设计单元：BD02
- 提供方：拟新增 `saleor/graphql/search/`，任务模型与服务位于 `saleor/core/search/`
- 调用方：Dashboard 维护状态区（FD03）、实施与运维
- 目标定义：`searchIndexJob(s)`、`searchIndexJobRetry`、`SearchIndexJob*`

```graphql
type SearchIndexJob implements Node {
  id: ID!
  scope: SearchIndexScopeEnum!
  status: SearchIndexJobStatusEnum!
  processedCount: Int!
  totalCount: Int!
  failedCount: Int!
  failures: [SearchIndexFailure!]!
}
```

- 字段说明：`failures` 列表及条目均不可空，只含对象 ID、脱敏错误码/信息和可重试标记；任务 connection 支持 scope/status 过滤。
- 权限：查询和重试要求 `MANAGE_SETTINGS`；报告不包含对象私有内容。
- 错误：不存在、任务未结束或无可重试失败分别返回 `NOT_FOUND`、`INVALID`、`NOT_RETRYABLE`。
- 完成判定：retry 创建新 job 并引用原失败集合；mutation 成功只表示可靠登记，不表示索引完成。最终状态及计数由 job 查询判定。
- 变更与兼容：现有对象搜索字段、权限、空查询和渠道隔离不变；本接口不引入新搜索产品。

### I04 · 渠道库存与外部运费设置
- 所属设计单元：BD03
- 提供方：`saleor/graphql/channel/`、`saleor/channel/models.py`；字段拟新增
- 调用方：Dashboard Channel create/details（FD04）
- 目标定义：`StockSettings.inventoryMode`、`ExternalShippingSettings` 及 Channel create/update 输入

```graphql
enum ChannelInventoryModeEnum { LEGACY_SHIPPING_ZONES CHANNEL_WAREHOUSES }
type ExternalShippingSettings { quoteCacheTtl: Int! filteringEnabled: Boolean! }
input ExternalShippingSettingsInput { quoteCacheTtl: Int filteringEnabled: Boolean }
```

- 字段说明：新建和迁移默认 `LEGACY_SHIPPING_ZONES`；`quoteCacheTtl` 范围 0..86400，缺省 43200，0 表示不缓存；`filteringEnabled` 缺省 true。更新 input 内字段省略时分别保留。
- 权限：读取遵循 Channel 现有字段权限；保存要求 `MANAGE_CHANNELS`。
- 错误：越界 TTL、无效 enum 及不存在仓库返回 `ChannelError` 对应字段；切到 `CHANNEL_WAREHOUSES` 允许零仓库，但会使跟踪库存且非预售商品不可购买。
- 完成判定：Channel 三个配置字段和关系在同一事务提交；完成后使旧报价 key 自然失效并登记 `CHANNEL_UPDATED`。
- 变更与兼容：保留 `allocationStrategy`，它只控制已选仓库排序；库存模式控制候选仓库集合，不复制库存。税费、地址和支付通知契约不变。

### I05 · 旧数字内容 GraphQL 退出与历史下载
- 所属设计单元：BD04
- 提供方：GraphQL 删除位于 `saleor/graphql/product/`、`saleor/graphql/order/types.py`；兼容 HTTP 位于 `saleor/product/views.py`
- 调用方：迁移后的外部履约；历史下载消费者
- 目标定义：`target-schema.graphql` 不含任何 `DigitalContent` 引用；HTTP 完整协议见 `interfaces/digital-download.md`

```text
Removed: Query.digitalContent(s), digitalContentCreate/Update/Delete,
digitalContentUrlCreate, ProductVariant.digitalContent,
OrderLine.digitalContentUrl, Shop.automaticFulfillmentDigitalProducts,
Shop.defaultDigital* and dedicated types.
```

- 字段说明：GraphQL 无替代“新数字分发”字段；新销售由商家选定的既有应用/外部服务承接。历史 URL 的 path/token 保持。
- 权限：历史 token 是随机能力凭证；不得以 ID 替代，不得返回永久公开文件。
- 错误：HTTP 语义见补充协议；schema 删除属于门槛控制的破坏性变更。
- 完成判定：消费者清单为零、未交付订单已交接且历史 grant 对账通过后才使用目标 schema 开放流量。
- 变更与兼容：仅删除冻结范围；普通数字商品、文件属性、非配送商品与订单履约保留。

### I06 · 分页交易查询与来源
- 所属设计单元：BD05、BD06
- 提供方：`saleor/graphql/payment/schema.py`、`types.py`、拟新增 filters/sort
- 调用方：Dashboard `/transactions` 与详情（FD05）、有权外部财务集成
- 目标定义：`transactions`、`TransactionWhereInput`、`TransactionSortingInput`、`TransactionItem.sourceType/giftCardSource/channel`

```graphql
transactions(where: TransactionWhereInput, sortBy: TransactionSortingInput,
  before: String, after: String, first: Int, last: Int
): TransactionItemCountableConnection!
```

- 字段说明：不同 where 字段 AND，同字段列表 OR；显式 `AND`/`OR` 可组合。默认 `CREATED_AT DESC, id DESC`。`giftCardSource.maskedCode` 永不返回完整卡码，`giftCard` 在无卡权限时为 null。
- 权限：根查询与单笔查询统一要求 `HANDLE_PAYMENTS` 并按用户可访问 Channel 限制；订单/礼品卡深链由目标对象再次校验权限。
- 错误：ID 类型或筛选错误为 GraphQL/参数错误；越权对象按不可见处理，避免枚举。
- 完成判定：结果从 writer/一致可接受读库读取稳定 connection；同一交易只返回一次，精确 PSP 查询不走全文结果上限。
- 变更与兼容：保留现有 `transaction(id/token)` 和 Order/Checkout 内嵌列表；新增根 connection 和来源字段。

### I07 · 按来源幂等退款
- 所属设计单元：BD05
- 提供方：拟新增 `saleor/graphql/payment/mutations/transaction_refund_request.py`
- 调用方：Dashboard 订单/交易退款入口（FD05）
- 目标定义：`transactionRefundRequest`、`TransactionRefund*`

```graphql
input TransactionRefundRequestInput {
  orderId: ID!
  idempotencyKey: UUID!
  allocations: [TransactionRefundAllocationInput!]!
  reason: String
  reasonReference: ID
}
```

- 字段说明：allocations 和条目均不可空且至少一项；同一 transaction 只允许一项，金额必须大于 0、符合币种精度且不超过“实扣-已退-处理中”。所有项必须属于 order 且同币种。
- 权限：要求 `HANDLE_PAYMENTS`，读取 order 另需对应订单权限；礼品卡余额变更由平台服务身份执行，不能用订单权限直接调用普通余额修改代替。
- 错误：输入级错误进入 `TransactionRefundError`；外部处理失败记录在 allocation 的 `FAILED` 与 error 字段，不把已成功礼品卡恢复回滚成失败。
- 完成判定：同一 `orderId + idempotencyKey` 重复调用返回原 `TransactionRefund`。礼品卡项提交时原子成功；外部项可靠登记为 processing，回报后变为终态；总状态按各项聚合。
- 变更与兼容：现有单交易 action 保留给非混合兼容消费者；Dashboard 新入口只使用本接口，绝不把礼品卡退款降级为 `giftCardUpdate(balanceAmount)`。

### I08 · 旧支付外部结果登记
- 所属设计单元：BD07
- 提供方：拟新增 `legacyPaymentResultRecord` 与 reconciliation service
- 调用方：受权财务/实施人员（FD06 可从历史交易详情进入）
- 目标定义：`LegacyPaymentResultRecordInput`、`LegacyPaymentResultRecord`

```graphql
legacyPaymentResultRecord(input: LegacyPaymentResultRecordInput!): LegacyPaymentResultRecord
```

- 字段说明：必须给出旧 Payment、动作、金额/币种、PSP reference、实际执行时间、受限证据引用和 UUID 幂等键；接口只登记外部已发生事实。
- 权限：要求 `HANDLE_PAYMENTS`；证据引用按私有财务数据处理。
- 错误：超可处理金额、币种不符、重复结果和不存在分别返回明确 code；不得据当前余额推断成功。
- 完成判定：登记记录与映射 TransactionEvent 同事务提交；不调用支付插件、Webhook 或礼品卡余额服务，不复制收入。
- 变更与兼容：旧 `Payment` 和事件查询继续；四个退出插件不再运行注册或用于新操作。

### I09 · 五类详情 Widget 挂载
- 所属设计单元：BD09
- 提供方：`saleor/app/types.py`、manifest validation、GraphQL enum
- 调用方：Dashboard 五类详情页（FD08）、应用 Manifest
- 目标定义：`AppExtensionMountEnum` 新增五值

```graphql
extend enum AppExtensionMountEnum {
  CATEGORY_DETAILS_WIDGETS PAGE_DETAILS_WIDGETS PAGE_TYPE_DETAILS_WIDGETS
  MENU_DETAILS_WIDGETS PROMOTION_DETAILS_WIDGETS
}
```

- 字段说明：Manifest 的 label/url/permissions/options 结构不变；Widget GET/POST options 沿用 Base，默认 target 行为不改。
- 权限：安装/更新时验证 mount 的领域权限；运行时同时验证员工和 App 权限。上下文仅含对象 ID及存在时的 Channel。
- 错误：非法 mount/target/url/options 或越权声明返回 App 字段错误并保持旧扩展完整。
- 完成判定：合法 Manifest 原子替换扩展；停用、卸载或撤权后查询与 token 访问同步失效。
- 变更与兼容：全部旧 mount 保留，不要求应用重配。

### I10 · 应用运行状态
- 所属设计单元：BD10
- 提供方：`App.operationalStatus` 拟新增，聚合现有 breaker、EventDelivery 和监控配置
- 调用方：Dashboard 应用列表、详情和全局提醒（FD09）
- 目标定义：`AppOperationalStatus`、`AppMonitoringStatusEnum`；安装失败继续读取 Base `AppInstallation`

```graphql
type AppOperationalStatus {
  monitoring: AppMonitoringStatusEnum!
  circuitBreaker: CircuitBreakerStateEnum
  failedDeliveries: Int!
  lastFailedDeliveryAt: DateTime
  lastFailureMessage: String
  changedAt: DateTime
}
```

- 字段说明：主动停用仍由 `App.isActive` 表示；安装失败由 `AppInstallation.status` 表示；operationalStatus 不把这些状态压成单一“健康”。失败原因是脱敏摘要。
- 权限：`MANAGE_APPS` 或 OWNER；无详细投递权限的列表消费者只获得计数/影响摘要。
- 错误：Redis/breaker 或投递状态不可用时 `monitoring=UNKNOWN` 或字段 null；前端不得解释为健康。
- 完成判定：查询反映同一聚合快照；状态查询不执行恢复、重试或资金事件重放。
- 变更与兼容：保留 `breakerState`/`breakerLastStateChange` 和 Base 默认阈值；不新增自由调阈值或强制清零 mutation。

### I11 · Webhook 渠道、稳定投递与重试
- 所属设计单元：BD11
- 提供方：`saleor/graphql/webhook/`、`saleor/webhook/models.py`、异步 transport
- 调用方：Dashboard Webhook 编辑和投递详情（FD10）、外部接收端
- 目标定义：`Webhook.channels`、create/update `channelIds`、`EventDelivery.eventId/attemptCount/status`

```graphql
extend input WebhookUpdateInput { channelIds: [ID!] }
extend type EventDelivery { eventId: UUID! attemptCount: Int! }
extend enum EventDeliveryStatusEnum { EXHAUSTED }
```

- 字段说明：create 时 channelIds 省略或空列表表示全部渠道；update 时省略保留、空列表改为全部。列表项不可空。query 内已有 channels argument 在过渡期仍可用，但与显式选择冲突时拒绝保存。
- 权限：`MANAGE_APPS` 或 App owner；Channel 选择还受调用者和 App 的 Channel 可见范围限制。
- 错误：不存在/越权 Channel、query 语法/事件/字段/权限错误进入 `WebhookError`，更新失败不覆盖原订阅。
- 完成判定：Webhook、事件、query 编译结果和 Channel 关系同事务提交。异步业务提交先写 outbox；delivery 可靠创建后发送。耗尽为 `EXHAUSTED`，授权 retry 沿用同一 eventId。
- 变更与兼容：旧事件、URL、签名、启用状态和 fixed payload 不自动改变；成功投递记录按保留期清理，不在发送成功时立即丢失审计。

### I12 · 新增变化通知
- 所属设计单元：BD11
- 提供方：`saleor/graphql/webhook/subscription_types.py`、event map/permissions、outbox dispatcher（拟扩展）
- 调用方：只使用 subscription payload 的新增订阅者、Dashboard Webhook editor（FD10）
- 目标定义：`SHOP_UPDATED`、`SHOP_ADDRESS_UPDATED`、三类 Transaction 事件及八类 metadata 事件；对应 `Subscription` 字段和 payload type

```graphql
transactionItemUpdated(channels: [String!]): TransactionItemUpdated
categoryMetadataUpdated: CategoryMetadataUpdated
```

- 字段说明：每个新增 payload 都有 `eventId: UUID!`、aggregate-local `sequence: BigInt!` 和业务对象。Transaction 的 channels 参数为空表示所有有权渠道，最多 500；Webhook 显式 Channel 选择先过滤，subscription query 再选字段。
- 权限：注册时按事件最小领域权限校验，投递时再次校验 App 当前权限和 Channel；撤权后不生成数据。私有 metadata 只有具备对应管理权限且 query 显式选择时可见。
- 错误：新增事件缺合法 subscription query 为 `MISSING_SUBSCRIPTION`；事件不匹配、无权字段或冲突 Channel 返回原子保存错误。
- 完成判定：仅数据库提交后的真实变化写一个逻辑 outbox 事件；失败/回滚/值未变/删除不存在 key 不写。网络重试复用 eventId，接收端可幂等。
- 变更与兼容：创建事件携带初始 metadata 而不伪造 metadata updated；过渡期原通用 updated 事件继续触发，旧 fixed payload 不设本轮停止日。

## 3. 其他

- `target-schema.graphql` 由核心 Base SDL 派生，保留未变定义并删除全部 `DigitalContent` 引用；未从更新版本检索 schema。
- 已执行结构与必要符号检查：括号/字符串闭合，目标 SDL 不含 `DigitalContent`/`digitalContent`/`defaultDigital`/`automaticFulfillmentDigitalProducts`，新增核心定义和引用均在完整文件中。环境仅有不支持现代 SDL description/extension 的 `graphql-core 2.3.2`，其解析器连未修改 Base schema 都在首个 description 处失败，因此未能执行兼容的完整 SDL parser/type validation；该限制不得解释为 schema 已运行验证。
- `BigInt` 按十进制字符串序列化，避免 JavaScript 精度损失。新增通知的 sequence 只在同一聚合对象内可比较，不承诺全局有序。
- 未决依赖：真实四插件使用清单、旧数字/固定 payload 消费者、外部管理员登录、支付和履约路径及历史账务证据由 PRD §6 指定责任方在切换前补齐。
