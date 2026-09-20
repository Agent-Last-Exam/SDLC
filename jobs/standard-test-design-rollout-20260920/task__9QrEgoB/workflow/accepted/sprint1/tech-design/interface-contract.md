# 接口契约：Commerce Core 收敛与经营连续性
版本：v1
责任：跨端接口契约
依据：PRD v1，artifacts/sprint1/prd/prd.md
修订：首次契约；完整权威 SDL 为 `artifacts/sprint1/tech-design/target-schema.graphql`。

## 1. 通用约定

- GraphQL global ID、Relay cursor、`PageInfo`、mutation `errors` 和既有权限模型保持 Base 约定。除明确说明外，省略 input 字段表示保留，显式 `null` 仅在该字段既有契约允许时表示清空。
- 时间以 UTC 存储/筛选并使用 ISO-8601 `DateTime`；金额必须携带其对象币种，禁止跨币种汇总。`PositiveDecimal` 还须满足币种精度。
- 列表页最大单页 100；默认稳定排序在相同业务排序键后追加唯一 ID。不同 filter 字段 AND，同一数组内 OR。
- mutation 业务错误通过 payload `errors` 返回且不部分覆盖输入对象；认证、解析或基础设施级失败仍按既有 GraphQL transport 语义处理。
- 所有私有 metadata、完整礼品卡码、密码、密钥、长期令牌和敏感 URL query 均不得进入新增列表、事件、样例或日志。Dashboard 不应依赖仅由 UI 实施的权限或策略判断。
- 新增 webhook 异步事件是至少一次投递：同一逻辑事件的重试保持稳定 event ID。只保证单对象可比较版本/时间，不保证跨对象全局顺序。

## 2. 接口条目

### I01 · 经营设置与地址独立更新
- 对应需求：R01、R17；AC-01-1～10、AC-17-1。
- 提供方：BD01。
- 调用方：FD01、FD09。
- 目标接口定义：复用 `shopSettingsUpdate(input: ShopSettingsInput!)`、`shopAddressUpdate(input: AddressInput)` 和已弃用但保持兼容的 `shopDomainUpdate`。展示名称/介绍/页头/发件信息/metadata 走 settings；公司名称走 `AddressInput.companyName`；显示名称更新不调用 domain mutation。地址显式 `null` 是经确认的清空，省略 mutation 则不变。
- SDL 片段：
  ```graphql
  type Mutation {
    shopSettingsUpdate(input: ShopSettingsInput!): ShopSettingsUpdate
    shopAddressUpdate(input: AddressInput): ShopAddressUpdate
  }
  ```
- 字段语义：每个 mutation 独立事务、独立错误与返回对象；重复相同地址更新结果幂等。实际普通设置变化发 `SHOP_UPDATED`，实际地址变化发 `SHOP_ADDRESS_UPDATED`；仅 metadata 变化继续发 `SHOP_METADATA_UPDATED`。
- 权限：写均要求 `MANAGE_SETTINGS`；私有 metadata 继续要求对象私有 metadata 权限。匿名 Shop 不暴露私有 metadata。
- 错误：使用既有 `ShopError`/`AddressError` 字段路径；非法邮箱、换行、超长、国家地址非法时该 mutation 零写入。
- 完成标准：前后端可分别保存、失败和重试；一方失败不回滚已成功的另一方，也不产生整体成功假象。
- 兼容性：不改现有 input 名称和 null 语义；domain mutation 的 deprecated 状态不变。

### I02 · 内容、图片与既有搜索的强化语义
- 对应需求：R02～R04。
- 提供方：BD02～BD04。
- 调用方：FD02 及所有既有富文本/媒体/搜索消费者。
- 目标接口定义：GraphQL 字段形状保持 Base，不新增搜索产品。EditorJS JSON 接受旧字符串 list item 和新递归 item；外部图片 URL 仍从产品媒体/App 品牌图既有 input 进入；商品、订单、顾客、礼品卡既有 search/filter 不变。
- 字段语义：非法新内容错误路径精确到 block/item 且目标字段不变；异常旧内容返回可安全部分但不自动覆盖。图片以受限 GET 后实际解码为准，默认 20 MiB、4000 万像素、20 秒、HTTP(S) 公网、零重定向。搜索派生更新目标为标准本地负载提交后 60 秒内可见。
- 权限：沿用各对象写/读权限、渠道隔离与空查询行为。
- 错误：内容结构/URL/网络/状态/格式/损坏/大小/像素必须为可定位字段错误；索引异步失败进入可重试运维状态而非伪造保存失败。
- 完成标准：所有共用 EditorJS 和两类外部图片入口使用相同安全规则；重建可续跑且新 revision 不被旧任务覆盖。
- 兼容性：合法旧 JSON、现有本地上传、视频/oEmbed 和既有 search 语义保持。

### I03 · 渠道库存与外部配送配置
- 对应需求：R05～R06。
- 提供方：BD05～BD06。
- 调用方：FD03、checkout/order 库存及配送服务。
- 目标接口定义：
  ```graphql
  enum ChannelInventoryModeEnum { SHIPPING_ZONES CHANNEL_WAREHOUSES }
  type StockSettings {
    allocationStrategy: AllocationStrategyEnum!
    inventoryMode: ChannelInventoryModeEnum!
  }
  type ExternalShippingSettings {
    quoteCacheTtl: Int!
    useExternalShippingMethodFiltering: Boolean!
  }
  input StockSettingsInput {
    allocationStrategy: AllocationStrategyEnum!
    inventoryMode: ChannelInventoryModeEnum
  }
  input ExternalShippingSettingsInput {
    quoteCacheTtl: Int
    useExternalShippingMethodFiltering: Boolean
  }
  ```
- 字段语义：`SHIPPING_ZONES` 为升级/新渠道默认并保留既有仓库-配送区交集；`CHANNEL_WAREHOUSES` 只从渠道关联仓取库存，但不绕过国家、配送、税、预售、自提与私有仓规则。TTL 单位秒，0 不缓存，范围 0～86400，默认 43200；过滤默认 true。Channel create/update input 增加 `externalShippingSettings`，Channel 增加同名非空字段。
- 权限：读取沿用 Channel 字段权限；写要求 `MANAGE_CHANNELS`。
- 错误：TTL 越界、未知模式或关系 ID 无效使用 `ChannelError` 的 `INVALID/NOT_FOUND` 与字段路径；整个 `channelUpdate` 原子失败。
- 完成标准：库存所有路径共享一个仓库选择器且不复制 Stock；缓存键包含 app/webhook、channel、完整报价上下文、query/身份/配置 revision。
- 兼容性：未提交新字段的旧客户端保持默认；allocation strategy 和已有 Channel input 不删除。

### I04 · 交易来源、历史状态与分页查询
- 对应需求：R08、R10、R11。
- 提供方：BD08、BD10、BD11。
- 调用方：FD05、财务工具。
- 目标接口定义：
  ```graphql
  enum TransactionSourceEnum { PAYMENT_APP GIFT_CARD MANUAL LEGACY }
  enum TransactionReconciliationStatusEnum { NOT_REQUIRED NORMALIZED PENDING_REVIEW }
  type TransactionItem {
    source: TransactionSourceEnum!
    giftCard: GiftCard
    sourceIdentifier: String
    reconciliationStatus: TransactionReconciliationStatusEnum!
    migrationReference: String
  }
  type Query {
    transactions(
      filter: TransactionItemFilterInput
      sortBy: TransactionItemSortingInput
      before: String, after: String, first: Int, last: Int
    ): TransactionItemCountableConnection
  }
  ```
- 字段语义：`GIFT_CARD` 只可由平台成交/归一流程设置；外部 App 不可伪装。`giftCard` 仅在来源为礼品卡且调用方有权时返回。filter 包含 `ids,tokens,pspReferences,orderIds,checkoutIds,channelIds,createdAt,appIdentifiers,giftCardIds`。默认 `CREATED_AT DESC`，同时间按 ID DESC；游标包含两键。
- 权限：查询、节点和 `totalCount` 均要求 `HANDLE_PAYMENTS` 并应用相同渠道 scope；订单跳转另校验订单权限，gift card 字段不扩展完整码权限。
- 错误：无权按现有 GraphQL 权限语义拒绝；非法 cursor/range 返回 GraphQL 输入错误。过滤零结果返回空 connection，不返回错误。
- 完成标准：PSP 参考号直接匹配 transaction/event 且不假设唯一；双向分页无重漏；旧单笔 `transaction(id|token)` 保留。
- 兼容性：现有 TransactionItem 字段、ID/token 与 app 历史记录不变；新字段非破坏性增加。

### I05 · 多来源退款与外部结果登记
- 对应需求：R09、R10、R12。
- 提供方：BD09、BD10、BD12。
- 调用方：FD04～FD05。
- 目标接口定义：
  ```graphql
  input TransactionRefundInput {
    orderId: ID!
    idempotencyKey: String!
    lines: [TransactionRefundLineInput!]!
    reason: String
    reasonReference: ID
  }
  input TransactionRefundLineInput { transactionId: ID!, amount: PositiveDecimal! }
  type Mutation {
    transactionRefundCreate(input: TransactionRefundInput!): TransactionRefundCreate
    transactionExternalRefundReport(
      input: TransactionExternalRefundReportInput!
    ): TransactionExternalRefundReport
  }
  ```
- 字段语义：order+idempotencyKey 唯一；line 总额不超过该来源成功 charge 减成功/处理中 refund。总状态为 `PROCESSING/PARTIALLY_SUCCEEDED/SUCCEEDED/FAILED`，每行 `PROCESSING/SUCCEEDED/FAILED`。外部登记必填 transaction、幂等键、金额、PSP reference、UTC processedAt、evidenceReference、SUCCEEDED/FAILED 和可选 message，且只登记事实、不调用 provider。
- 权限：发起或登记要求 `HANDLE_PAYMENTS`，并校验订单可见性；直接改变礼品卡状态/余额的管理动作仍要求 `MANAGE_GIFT_CARD`。
- 错误：`TransactionRefundErrorCode` 为 `GRAPHQL_ERROR/INVALID/NOT_FOUND/REQUIRED/AMOUNT_GREATER_THAN_AVAILABLE/CURRENCY_MISMATCH/DUPLICATED_INPUT_ITEM/SOURCE_UNAVAILABLE`。业务错误零新增请求；执行后的来源失败进入 line 状态，不回滚其他已成功资金事实。
- 完成标准：重复/并发请求返回同一持久结果；混合退款可真实部分成功，重试只处理失败 line；礼品卡退款不调用 PSP。
- 兼容性：既有单 transaction action 和 Payment 历史接口保留；新编排入口供 Dashboard 优先采用。

### I06 · 三态密码策略
- 对应需求：R13～R14。
- 提供方：BD13。
- 调用方：FD06、所有认证入口。
- 目标接口定义：
  ```graphql
  enum PasswordPolicyEnum { ALL CUSTOMERS_ONLY DISABLED }
  type Shop {
    passwordPolicy: PasswordPolicyEnum!
    availableExternalAuthentications: [ExternalAuthentication!]!
  }
  enum AccountErrorCode { PASSWORD_NOT_ALLOWED_BY_POLICY }
  ```
- 字段语义：`ALL` 允许符合既有校验的本地密码；`CUSTOMERS_ONLY` 只允许当前 `is_staff=false`；`DISABLED` 全禁。部署缺省 ALL，未知配置使启动检查失败。策略覆盖登录、注册密码、设置/修改、重置请求/完成、员工邀请与 session/refresh；找回请求仍防枚举。
- 权限：两项 Shop 能力匿名可读，不接受邮箱/用户参数，不泄露账号存在性。配置只由授权运维修改，无 GraphQL 写入口。
- 错误：受限写入返回 `PASSWORD_NOT_ALLOWED_BY_POLICY` 且原子零改变；策略查询失败时客户端不得默认开放本地密码。
- 完成标准：收紧使受影响本地/refresh 会话失效，旧链接不可绕过；放宽不复活失效会话；外部身份以已验证 provider subject 绑定。
- 兼容性：默认 ALL 保持既有安装行为，密码哈希、账号、订单和外部关联均保留。

### I07 · 五类详情 Widget
- 对应需求：R15。
- 提供方：BD14。
- 调用方：FD07、App Manifest 消费者。
- 目标接口定义：`AppExtensionMountEnum` 新增 `CATEGORY_DETAILS_WIDGETS`、`PAGE_DETAILS_WIDGETS`、`PAGE_TYPE_DETAILS_WIDGETS`、`MENU_DETAILS_WIDGETS`、`PROMOTION_DETAILS_WIDGETS`。
- 字段语义：目标使用既有 `WIDGET`，旧扩展未声明 target 时继续默认 POPUP。详情上下文只含对象 ID 和可选当前渠道；GET/POST option、label、HTTPS URL、required permissions 沿用现有 manifest 字段。
- 权限：员工与 App 均须拥有扩展所需权限；token audience/origin 必须匹配验证后的 URL。
- 错误：非法 mount/target/URL/option/越权 permission 使 manifest 安装/更新整体失败并返回原字段路径。
- 完成标准：五类对象新旧入口并存，停用/卸载/撤权即时失效，单 Widget 故障不阻断原生页面。
- 兼容性：不删除/重命名任何旧 mount 或 target。

### I08 · 应用运行状态投影
- 对应需求：R16。
- 提供方：BD15。
- 调用方：FD08。
- 目标接口定义：
  ```graphql
  type AppOperationalStatus {
    state: AppOperationalStateEnum!
    monitoringState: AppMonitoringStateEnum!
    changedAt: DateTime
    issues: [AppOperationalIssue!]!
  }
  type App { operationalStatus: AppOperationalStatus! }
  type AppInstallation { operationalStatus: AppOperationalStatus! }
  ```
- 字段语义：state 为 `HEALTHY/INSTALLATION_FAILED/DEACTIVATED/DELIVERY_FAILED/CIRCUIT_OPEN/CIRCUIT_RECOVERING/UNKNOWN`；monitoring 为 `DISABLED/OBSERVING/ENFORCING/UNKNOWN`。issue 含 code、脱敏 message、occurredAt、affectedSyncEvents 和可选 delivery。
- 权限：列表/详情沿用 App 可见性；delivery 和详细错误按 `MANAGE_APPS/OWNER` 及既有日志权限过滤。
- 错误：聚合依赖不可用时返回 UNKNOWN 状态；不得返回 HEALTHY 猜测值。resolver transport 失败仍显示可重试。
- 完成标准：安装、停用、异步耗尽、OPEN/HALF_OPEN 可区分；所有 UI 消费同一投影。
- 兼容性：`App.isActive`、Job status、delivery 与 Base breaker 继续存在；不新增阈值编辑/强制清零。

### I09 · 新增异步事件集合
- 对应需求：R17～R18。
- 提供方：BD01、BD08、BD16。
- 调用方：FD09、Webhook consumers。
- 目标接口定义：`WebhookEventTypeAsyncEnum` 与兼容的 deprecated `WebhookEventTypeEnum` 新增 `SHOP_UPDATED`、`SHOP_ADDRESS_UPDATED`、`TRANSACTION_ITEM_CREATED`、`TRANSACTION_ITEM_UPDATED`、`ATTRIBUTE_METADATA_UPDATED`、`CATEGORY_METADATA_UPDATED`、`MENU_METADATA_UPDATED`、`MENU_ITEM_METADATA_UPDATED`、`PAGE_METADATA_UPDATED`、`PAGE_TYPE_METADATA_UPDATED`、`PRODUCT_TYPE_METADATA_UPDATED`、`SHIPPING_METHOD_METADATA_UPDATED`。`Subscription` 暴露对应 camelCase 字段；交易、菜单/菜单项和配送方式字段接受可选 `channels: [String!]`。每项有对应 `Event` 实现和领域对象字段；Menu/MenuItem/ShippingMethod 另带可选 channel slug。
- 字段语义：每个新增事件包含稳定 `eventId: UUID!`、同对象单调递增的 `objectVersion: Int!`、`issuedAt` 与领域对象（可选 channel）；对象创建时初始 metadata 仅在 created event；通用/内嵌/批量 metadata 写均覆盖专用事件，批量仅成功对象；同提交同对象同类最多一逻辑事件。AttributeValue 不新增 metadata 事件。
- 权限：注册和投递双重检查领域权限、当前 App 权限与渠道；subscription query 只返回被选且有权字段。
- 错误：无权限/字段/渠道不匹配在 Webhook create/update 返回可定位 `WebhookError`，不覆盖旧订阅。投递期撤权则拒绝或裁剪，不泄露字段。
- 完成标准：提交后 outbox 可靠登记，event ID 重试稳定，删除/过期对象仍有足够快照/标识解析。
- 兼容性：既有普通/metadata 事件不删除；过渡期可能与原通用更新事件并存，消费者按类型与 event ID 处理。

### I10 · Webhook 渠道、payload 模式与合成样例
- 对应需求：R19。
- 提供方：BD16。
- 调用方：FD09、App/Webhook 管理工具。
- 目标接口定义：
  ```graphql
  enum WebhookPayloadModeEnum { FIXED SUBSCRIPTION }
  type Webhook {
    channels: [Channel!]
    payloadMode: WebhookPayloadModeEnum!
  }
  input WebhookCreateInput { channels: [ID!] }
  input WebhookUpdateInput { channels: [ID!] }
  type Query {
    webhookSubscriptionSample(
      eventType: WebhookEventTypeAsyncEnum!
      query: String!
    ): WebhookSubscriptionSample!
  }
  type WebhookSubscriptionSample { eventId: UUID!, issuedAt: DateTime!, payload: JSONString! }
  ```
- 字段语义：`channels=null` 是全部渠道；create 缺省等于全部，update 省略保持原值、显式 null 切回全部，空数组非法。`payloadMode` 由现有 webhook 配置推导，只读。所有 I09 新事件必须有合法 query；旧事件可保持 FIXED 或已有 query。样例使用确定性合成对象，不读生产数据。
- 权限：管理沿用 `MANAGE_APPS` 或既有 App owner；样例要求 `MANAGE_APPS`，仍校验事件字段权限。
- 错误：沿用 `WebhookErrorCode`，缺 query 用 `MISSING_SUBSCRIPTION`，语法/字段/事件/权限/渠道分别以现有 `SYNTAX/INVALID/MISSING_EVENT` 等和字段路径返回；失败不替换现有订阅。
- 完成标准：Manifest、事件列表、schema、create/update、样例和 Dashboard 事件集合一致；异步 delivery 为 PENDING/成功/有限重试/耗尽可见，授权 retry 复用原事件。
- 兼容性：升级不改旧 Webhook 的事件、签名、URL、启用、payload 模式或字段含义；按单 Webhook 验证切换，不设本轮强制截止日。

### I11 · 旧数字内容接口删除边界
- 对应需求：R07。
- 提供方：BD07。
- 调用方：FD04、外部消费者迁移负责人。
- 目标接口定义：目标 SDL 不含 `digitalContent`、`digitalContents`、`digitalContentCreate/Delete/Update/UrlCreate`、ProductVariant.digitalContent、OrderLine.digitalContentUrl、三个 Shop 数字默认设置及仅被它们引用的 `DigitalContent*` 类型/input/payload/connection。
- 字段语义：删除仅指 GraphQL/Dashboard 公共面；历史权益下载仍是受保护的非 GraphQL 兼容边界，遵守原 token、期限和次数。
- 权限：兼容下载继续验证不可猜 token、订单/顾客归属并原子消费次数。
- 错误：旧字段在目标 schema 验证期成为 unknown field；上线前消费者扫描发现调用则阻断，不提供静默空值。
- 完成标准：目标 SDL 零残留，Dashboard codegen/query 零引用；数据库历史记录和媒体未被删除。
- 兼容性：这是经预检和迁移的明确破坏性删除；普通数字/非配送商品、文件属性、礼品卡和订单履约不在删除范围。

## 3. 其他

- 完整 SDL 的解析、类型引用与重复定义检查以 `target-schema.graphql` 为准；片段只帮助联调，不能替代完整文件生成客户端。
- 目标 SDL 对 Base 未涉及定义保持原样；删除范围仅为 I11，其他 deprecated API 不顺带清理。
- R20 的备份、维护、对账、外部验证和恢复属于交付门禁，不新增远程“执行切换”API，避免把高风险运维动作暴露给 Dashboard。
- 已执行检查：使用 GraphQL Core 3 对完整目标 SDL 执行 parse、`build_ast_schema` 与 `validate_schema`，结果为 0 个 schema 错误；逐项检查新增 Query/Mutation/字段、五个 mount 和十二个事件枚举/Subscription 字段均存在；与 Base AST 比较确认删除类型/字段仅为 I11 清单；全文检查旧数字内容符号为零残留；人工核对 FD/BD/I 的名称、默认值、权限和错误语义一致。
- 未运行检查：按本阶段约束未启动 Saleor/Dashboard、未导出运行时 schema、未运行 codegen、单元/集成/E2E、迁移、服务或部署；这些检查由实施阶段按 BD17 与 BT01～BT05 执行。
