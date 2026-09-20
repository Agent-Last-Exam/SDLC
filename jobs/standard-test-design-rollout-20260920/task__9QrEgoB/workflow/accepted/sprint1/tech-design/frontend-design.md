# 前端技术设计：Commerce Core 收敛与经营连续性
版本：v1
责任：前端技术设计
依据：PRD v1，artifacts/sprint1/prd/prd.md
修订：首次设计；以 Base Dashboard 现有路由、表单与 GraphQL 生成链路为基础。

## 1. 方案概述

Dashboard 继续使用现有 React、GraphQL codegen、Relay 游标和权限守卫。变更集中在经营设置、渠道、订单资金、交易、认证、扩展与应用管理，不另建平行管理端。所有表单都以服务端返回值为事实源，提交中锁定本区域，失败只保留本区域草稿；跨区域操作不合并成“整体成功”。

前端不承担资金、权限、SSRF 或策略判定，只显示服务端能力并处理明确错误。敏感信息仅显示掩码值；URL、卡码、令牌和私有 metadata 不进入通知、埋点或客户端日志。`target-schema.graphql` 是 codegen 唯一输入，退出字段不得保留在查询文档中。

## 2. 需求覆盖

| 需求 | 设计单元 |
| --- | --- |
| R01 | FD01 经营资料分区保存 |
| R02、R03、R04 | FD02 内容、图片与搜索反馈 |
| R05、R06 | FD03 渠道库存和外部运费 |
| R07、R12 | FD04 退出入口与历史只读连续性 |
| R08、R09、R10、R11 | FD05 统一资金视图、退款与交易定位 |
| R13、R14 | FD06 密码策略体验与恢复提示 |
| R15 | FD07 五类详情 Widget |
| R16 | FD08 应用健康状态 |
| R17、R18、R19 | FD09 Webhook 契约编辑与投递 |
| R20 | FD10 发布门槛和前端验收 |

## 3. 详细设计

### FD01 经营资料分区保存
- 覆盖需求：R01；AC-01-1～AC-01-10。
- 设计说明：在 `src/siteSettings/components/SiteSettingsPage` 将“经营信息”“经营地址”拆为两个 form state、dirty state、submit state 和 toast/error 区。信息区调用既有 `shopSettingsUpdate`，地址区调用 `shopAddressUpdate`；展示名称不调用 `shopDomainUpdate`。地址清空使用独立确认对话框并传显式 `null`，普通未编辑字段不进入 variables。
- 字段：信息区承载展示名称、description/header、发件名称/邮箱、公共/私有 metadata；地址区直接编辑 `Address.companyName` 与国家规则字段。公共 metadata 旁固定展示非敏感信息警示，私有 metadata 沿用权限门控。
- 状态：一方成功后只用该 mutation 返回值刷新对应初值；另一方的草稿和错误不清除。字段错误按 `field` 绑定控件，无法定位的错误落在本卡片顶部。重复保存仍以读回对象为准。
- 权限：无 `MANAGE_SETTINGS` 时只读；无私有 metadata 权限时不查询对应字段。地址清空确认文案明确历史订单快照不受影响。

### FD02 内容、图片与搜索反馈
- 覆盖需求：R02、R03、R04；AC-02-1～8、AC-03-1～8、AC-04-1～6。
- 设计说明：扩展 `src/utils/richText` 的统一适配层，把旧字符串列表规范化为内存中的递归列表节点；保存时保留合法层级、顺序、样式和额外元数据。预览与只读展示统一使用安全 renderer，不使用原始 HTML 注入；空块只跳过本节点，不能终止后续遍历。
- 提交：客户端只做快速结构提示，最终合法性由 API 决定。收到内容路径错误时保留完整旧值和草稿，定位到块/列表项；读取到异常存量时展示安全可读部分及非阻断告警，不自动回写。
- 图片：产品外部媒体和 App 品牌图保留原 URL 输入，显示上传中/成功/失败。失败不替换已有图片；错误映射为地址、超时、格式、大小、像素等可行动文案，并允许修改后重试。客户端不做 HEAD、扩展名或 Content-Type 真实性判断。
- 搜索：沿用商品、订单、顾客和礼品卡既有入口与空查询语义；索引更新失败显示可重试提示但不伪报保存失败。运维重建/失败对象信息只在既有有权入口呈现，不显示私有索引材料。

### FD03 渠道库存和外部运费
- 覆盖需求：R05、R06；AC-05-1～10、AC-06-1～9。
- 设计说明：在 `src/channels/pages/ChannelDetailsPage` 增加“库存来源”和“外部配送”两张卡。库存模式绑定 `stockSettings.inventoryMode`，展示 `SHIPPING_ZONES`（兼容配送区域）与 `CHANNEL_WAREHOUSES`（仅渠道仓库）；同时显示关联仓库、排序、分配策略及旧模式要求。
- 切换：改为渠道仓库模式前读取当前关联并展示差异；可能扩大销售区域的变化必须二次确认。无 `MANAGE_CHANNELS` 只读。后端返回缺省值时也总显示兼容模式，不在客户端猜测库存。
- 运费：TTL 输入单位秒，范围 0～86400，0 文案为“不缓存”，默认读回 43200；过滤默认开启。关闭过滤前提示候选方式可能扩大。两字段独立前端校验，但一次 `channelUpdate` 原子保存，失败保留草稿。
- 结账/订单错误：外部报价或过滤故障只展示具体不可配送及重试，不制造零价选项。前端不得缓存服务端报价，也不得绕过成交前重新校验/涨价确认。

### FD04 退出入口与历史只读连续性
- 覆盖需求：R07、R12；AC-07-1～9、AC-12-1～7。
- 设计说明：删除所有 `digitalContent*` 查询、mutation、片段、默认下载设置与页面入口；保留非配送商品、文件属性、礼品卡和普通履约。历史订单只显示后端允许的兼容权益/履约结果，不构造旧下载 mutation。
- 支付插件：从配置导航和安装选择器移除 Dummy、DummyCreditCard、Braintree、Razorpay；历史 `Payment` 行仍用通用字段渲染，即使 gateway 不在当前注册表也显示保存的名称、金额、币种、参考号和状态，不导入已移除插件模块。
- 人工结果：历史外部售后使用 FD05 的“外部处理登记”，显著标注“登记而非平台发起”，要求参考号、时间与证据；前端不提供修改已确认金额的捷径。

### FD05 统一资金视图、退款与交易定位
- 覆盖需求：R08、R09、R10、R11；AC-08-1～8、AC-09-1～10、AC-10-1～7、AC-11-1～9。
- 设计说明：新增财务交易列表路由，使用 `transactions` 连接，默认 `CREATED_AT DESC`，保留游标于 URL。筛选支持 ID/token、PSP 参考号、订单/结账、渠道、UTC 时间范围、应用标识和礼品卡；不同控件 AND、同控件多值 OR。加载失败、零结果和清空筛选分别显示。
- 列表/详情：按币种分组金额，显示来源、创建时间（本地时区并提示 UTC 边界）、订单/结账、应用历史标识、对账状态。礼品卡只显示掩码标识；订单深链仍由目标页校验权限。`PENDING_REVIEW` 提供只读旧账提示和有权人工登记入口。
- 订单资金卡：每个 `TransactionItem` 展示实扣、成功退款、处理中、可退、事件与真实来源；礼品卡交易与外部交易同列但来源标签明确。旧补偿字段不参与前端合计。
- 混合退款：表单以来源为行，正金额且按币种精度，提交生成稳定 idempotency key，并调用 `transactionRefundCreate`。返回 `PROCESSING` 时轮询订单/交易事实；部分成功逐行显示成功与失败，重试只重建失败行且沿用原业务幂等关联。礼品卡过期/停用退款后仍提示不可消费。
- 外部登记：`transactionExternalRefundReport` 对话框要求 PSP 参考号、处理时间、证据引用、结果和说明；再次提交同一幂等键只展示原结果。入口同时要求订单访问与 `HANDLE_PAYMENTS`，卡管理动作另受 `MANAGE_GIFT_CARD` 控制。

### FD06 密码策略体验与恢复提示
- 覆盖需求：R13、R14；AC-13-1～10、AC-14-1～4。
- 设计说明：认证 shell 启动时匿名查询 `shop.passwordPolicy` 与 `availableExternalAuthentications`。`ALL` 显示本地登录/找回；`CUSTOMERS_ONLY` 对 Dashboard 员工隐藏本地入口；`DISABLED` 对所有 Dashboard 本地入口隐藏。查询失败采取关闭本地入口的安全状态并提供刷新。
- 登录失败若收到 `PASSWORD_NOT_ALLOWED_BY_POLICY`，展示外部登录或联系管理员，不提示账号是否存在。重置、设置/修改密码、邀请页面均处理同一错误；旧链接不能因客户端页面可见而绕过后端。
- 设置页只读显示当前策略、外部方式与“部署配置修改”说明，不提供在线切换。切换前账号盘点、管理员真实登录和恢复演练属于部署门禁，Dashboard 仅展示最近验证结果/阻断原因，不提供自动放宽按钮。

### FD07 五类详情 Widget
- 覆盖需求：R15；AC-15-1～8。
- 设计说明：在现有扩展解析和详情页 slot 上增加 `CATEGORY_DETAILS_WIDGETS`、`PAGE_DETAILS_WIDGETS`、`PAGE_TYPE_DETAILS_WIDGETS`、`MENU_DETAILS_WIDGETS`、`PROMOTION_DETAILS_WIDGETS`。继续支持已有更多操作和 `POPUP` 默认；目标为 `WIDGET` 时渲染详情卡槽，无扩展时不留空容器。
- 上下文：只传当前对象 global ID，存在渠道时只传当前渠道。扩展与员工权限双重满足才挂载；停用、卸载或撤权后立即从查询结果消失。凭证通过已有受信 origin 消息通道传送，不进 URL/日志。
- 故障隔离：超时、来源不匹配和 iframe 失败只影响单个 Widget，显示局部重试；原生详情读取和保存始终可用。同一扩展同一 slot 去重，旧入口行为不变。

### FD08 应用健康状态
- 覆盖需求：R16；AC-16-1～7。
- 设计说明：应用列表、详情与全局提醒都消费 `operationalStatus`，不自行从 `isActive` 或单次 delivery 推断。状态分别为安装失败、主动停用、异步投递失败、熔断、半开恢复、正常与未知；监控关闭/观察/执行单独呈现。
- 详情显示 `changedAt`、受影响同步事件、脱敏原因和允许访问的 `EventDelivery` 深链。请求失败必须显示 UNKNOWN 与刷新，不降级为 HEALTHY。保留既有异步重试和启停操作；不提供阈值编辑、强制清零或同步资金动作重放。

### FD09 Webhook 契约编辑与投递
- 覆盖需求：R17、R18、R19；AC-17-1～5、AC-18-1～9、AC-19-1～11。
- 设计说明：事件选择器加入经营设置/地址、交易创建/更新及八类 metadata 事件；明确不加入 AttributeValue metadata。编辑器显示 `payloadMode`、`channels`、订阅 query、目标、签名状态和投递记录。
- 规则：选择任一新增事件时 query 必填；旧事件可保留 FIXED 或既有 SUBSCRIPTION。渠道 `null` 显示“全部渠道”，不得提交空数组。保存前调用本地 schema 校验并以 mutation 服务端错误为准，错误不覆盖现有有效订阅。
- 样例：`webhookSubscriptionSample` 只用事件类型和 query 生成合成数据，界面标注“非真实业务数据”；禁止用真实扣款/退款测试。迁移按单个 Webhook 进行，保存成功后重读 `payloadMode`，不批量切换旧订阅。
- 可靠性：delivery 的排队、成功、失败耗尽明确区分；授权用户可沿用既有 retry。事件 ID、时间、签名和重试语义在详情展示，前端不承诺精确一次或跨对象顺序。

### FD10 发布门槛和前端验收
- 覆盖需求：R20；AC-20-1～11。
- 设计说明：codegen 固定读取本交付的完整 `target-schema.graphql`；CI 阻断退出字段残留、未知枚举、生成差异和旧插件入口。构建展示不可变版本摘要，禁止把 `latest` 作为验收证据。
- 验收矩阵覆盖：有/无权限、两种库存模式及共享仓、多币种混合资金、新旧订阅、异常 EditorJS、外部图片边界、三态密码策略、应用未知/熔断状态及历史数字权益。前端只记录验证结果，不把模拟外部端标成生产验证。
- 恢复：若开放后已有新订单、资金或通知，界面停写/维护状态必须保留增量事实；恢复采用服务端前向修复/可重放结果，客户端不得以旧缓存覆盖新状态。

## 4. 依赖与联调

| 接口 | 消费方设计单元 | 对应需求 | 开发依赖 |
| --- | --- | --- | --- |
| 既有 `shopSettingsUpdate`、`shopAddressUpdate` | FD01 | R01 | 后端保持省略/null/错误语义并发布经营事件 |
| 既有内容与媒体 mutations | FD02 | R02～R04 | 统一安全解析、受限图片 GET、索引作业可观察性 |
| `Channel.stockSettings.inventoryMode`、`externalShippingSettings`、`channelUpdate` | FD03 | R05～R06 | 默认值、范围校验及库存/报价运行时接线 |
| `transactions`、`TransactionItem.source/reconciliationStatus` | FD05 | R08、R10～R11 | 稳定排序、权限/渠道隔离、历史映射 |
| `transactionRefundCreate`、`transactionExternalRefundReport` | FD04～FD05 | R09、R12 | 资金幂等、逐来源状态、审计证据 |
| `Shop.passwordPolicy`、`availableExternalAuthentications` | FD06 | R13～R14 | 匿名安全读取、所有密码入口强制策略 |
| `AppExtensionMountEnum` 五个新值 | FD07 | R15 | Manifest 校验与 token origin 约束 |
| `App.operationalStatus`、`AppInstallation.operationalStatus` | FD08 | R16 | 状态聚合、脱敏和 delivery 权限 |
| Webhook 新事件、`channels`、`payloadMode`、`webhookSubscriptionSample` | FD09 | R17～R19 | outbox、最小授权序列化、至少一次投递 |

## 5. 其他

- Dashboard 不直接读取数据库、旧插件配置或历史下载 token；所有兼容信息必须经有权 API/既有历史页面提供。
- 所有新增文案需区分“平台发起”“外部登记”“处理中”“待核对”“未知”，避免把技术成功提示为资金成功。
- 实施测试和发布操作不属于本设计阶段；执行时以 PRD 的完整 AC 矩阵和不可变构建摘要为准。
