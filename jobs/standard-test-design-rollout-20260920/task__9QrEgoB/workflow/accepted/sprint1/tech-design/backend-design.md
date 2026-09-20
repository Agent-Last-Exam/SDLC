# 后端技术设计：Commerce Core 收敛与经营连续性
版本：v1
责任：后端技术设计
依据：PRD v1，artifacts/sprint1/prd/prd.md
修订：首次设计；基于 Base Saleor 的 Django、Celery、GraphQL 与 webhook/outbox 约定。

## 1. 方案概述

设计遵循“事实先落库、事务提交后派生、旧事实不重放资金动作”。在现有领域模块内扩展 Channel、TransactionItem、App/Webhook 与内容处理，不引入新搜索产品或第二套库存/支付账本。GraphQL 新增部分见完整 `target-schema.graphql`；经营资料仍复用现有 mutation，避免把地址和设置重新耦合。

资金和通知使用稳定业务幂等键。历史归一只写带迁移来源的账务映射/交易事实，不调用 PSP、不调整礼品卡余额。新增异步事件在业务事务内写 outbox，提交后投递至少一次；消费者通过稳定事件 ID 去重。所有权限、渠道和字段选择在注册与投递两次校验。

## 2. 需求覆盖

| 需求 | 设计单元 |
| --- | --- |
| R01 | BD01 经营资料边界与事件 |
| R02 | BD02 EditorJS 兼容与净化 |
| R03 | BD03 受限外部图片获取 |
| R04 | BD04 搜索更新与可恢复重建 |
| R05 | BD05 渠道库存模式 |
| R06 | BD06 外部运费缓存和过滤 |
| R07 | BD07 数字内容 GraphQL 退出 |
| R08 | BD08 礼品卡交易记账 |
| R09 | BD09 多来源退款编排 |
| R10 | BD10 历史资金归一与对账 |
| R11 | BD11 交易连接查询 |
| R12 | BD12 四类支付插件退出 |
| R13、R14 | BD13 密码策略与切换门禁 |
| R15 | BD14 扩展挂载点 |
| R16 | BD15 应用运行状态 |
| R17、R18、R19 | BD16 通知契约与可靠投递 |
| R20 | BD17 受控切换和恢复 |

## 3. 详细设计

### BD01 经营资料边界与事件
- 覆盖需求：R01；AC-01-1～10。
- 设计说明：保留 `shopSettingsUpdate`、`shopAddressUpdate`、`shopDomainUpdate` 三个事务边界。缺省字段不写，契约允许的显式 `null` 才清空；地址更新采用已有 get-or-create/update 规则和幂等比较，地址清空只断开 Shop 当前地址，绝不改历史订单快照。
- 校验：邮件地址、发件名换行、长度、国家地址规则在各 mutation 内原子校验，任一字段错误时该 mutation 零写入。展示名称只更新 Shop 设置，不触碰 Domain。公共/私有 metadata 沿用 `ObjectWithMetadata` 权限和敏感信息约束。
- 通知：普通设置实际变化登记 `SHOP_UPDATED`，地址实际变化登记 `SHOP_ADDRESS_UPDATED`；metadata 只变更时继续登记 `SHOP_METADATA_UPDATED`，并保留旧通用事件的既有兼容触发。失败、回滚、同值写入不登记。

### BD02 EditorJS 兼容与净化
- 覆盖需求：R02；AC-02-1～8。
- 设计说明：建立一个领域无关的 EditorJS walker，商品、分类、集合、Page/PageType、属性与翻译的读、校验、纯文本抽取共用。list item 接受旧字符串或 `{content, items, ...metadata}`；递归按输入顺序遍历并设深度/节点/字符串长度有限上限，空节点返回空结果而非结束兄弟节点。
- 安全：在所有文本、链接、image、embed/source/caption 分支调用同一白名单净化器；移除 script、事件属性和危险协议。服务端以路径数组记录错误（block/index/items/index），新写入遇到结构错误整体拒绝，存量读取则隔离异常节点、写脱敏告警并保持原 JSON 不变。
- 搜索：纯文本 visitor 只收集可见文字，保持阅读顺序，不包含 HTML、结构键、脚本或不可见元数据。若需重建，先生成对象清单与原始内容备份引用，不就地破坏性重写。

### BD03 受限外部图片获取
- 覆盖需求：R03；AC-03-1～8。
- 设计说明：产品外部媒体与 App 品牌图调用同一 `SafeImageFetcher`。仅接收 HTTP/HTTPS；逐个解析 A/AAAA 并拒绝非公网、回环、链路本地、私网和元数据地址；连接到已验证 IP 且校验 Host/TLS，阻断 DNS 重绑定。首版禁用重定向，3xx 返回最终直链错误。
- 预算：流式 GET 总计时默认 20 秒、最多 20 MiB，部署值必须有限且为正。先写隔离临时文件，实际解码并校验支持格式与最多 4000 万像素，成功后才原子建立/替换媒体记录；异常统一清理临时文件。
- 语义：不先发 HEAD，不以扩展名或声明 Content-Type 判真；解码器是最终依据。错误分类为 URL/网络/状态/重定向/非图片/损坏/格式/体积/像素，绑定原输入字段。日志只留 scheme、host 与不可逆关联 ID，移除 query/fragment/凭证。

### BD04 搜索更新与可恢复重建
- 覆盖需求：R04；AC-04-1～6。
- 设计说明：沿用 PostgreSQL 搜索与现有 query/filter。保存事务提交后写带对象 ID、目标 revision 的索引任务；worker 更新时先比较当前 revision，旧任务不得覆盖新提交。商品派生文本使用 BD02，订单纳入既有字段和不截断的精确交易参考关联，顾客/礼品卡保持既有权限和渠道范围。
- 重建：按主键水位分页，记录 run、游标、成功/失败对象、重试次数和完成 revision；单对象失败进入隔离清单继续其他对象。重建写 staging 版本或逐对象 compare-and-swap，查询期间旧索引保持可用，尾部回放重建期间的更新后切换。
- 可观察性：标准本地验收负载目标为提交后 60 秒内可搜；积压、最后成功时间、失败对象和重试结果可观测。报告只含 ID/错误类别，不含私有字段或原始敏感搜索文本。

### BD05 渠道库存模式
- 覆盖需求：R05；AC-05-1～10。
- 设计说明：Channel 持久化 `inventory_mode`，缺省/升级回填与新建默认均为 `SHIPPING_ZONES`；GraphQL 暴露于 `StockSettings`，写入仅 `MANAGE_CHANNELS`。不创建渠道库存表，库存仍是 Warehouse/Stock 唯一事实。
- 选择器：抽取 `warehouses_for_channel(channel, address, purpose)`。兼容模式复用配送区域交集；渠道仓库模式只取 Channel-Warehouse 关联，同时继续执行国家合法性、配送方式、税、库存跟踪、预售、自提/私有仓与仓库排序规则。报价、预留、分配、补货使用同一选择器。
- 并发：扣减/分配锁定真实 Stock 行，跨渠道共享仓库竞争同一记录。模式或关系切换只影响后续校验，既有 Allocation/Fulfillment/Return 来源不重写。未完成 checkout 每次报价/预留/完成重新读取模式，预留释放保持现有幂等键。

### BD06 外部运费缓存和过滤
- 覆盖需求：R06；AC-06-1～9。
- 设计说明：Channel 增加 `quote_cache_ttl`（0～86400，默认 43200）和 `use_external_shipping_method_filtering`（默认 true）。仅 `MANAGE_CHANNELS` 可写；配置只接入外部 shipping quote/filter 路径。
- 缓存键：版本、App/Webhook ID、渠道 ID、规范化地址、line/variant/quantity、金额/折扣、币种、订阅 query 选择摘要、应用身份和相关配置 revision 的哈希；TTL=0 跳过读写。仅缓存通过契约验证的成功响应（合法空列表允许），超时、错误、无效币种/金额/标识不缓存。
- 过滤：关闭时只跳过外部过滤 webhook，仍调用外部报价和本地配送校验。开启且过滤超时、失败或熔断时，对应外部候选为不可成交；不生成零价方式，不无限使用过期缓存。完成订单前重新报价/校验，涨价走既有确认流程，订单保留成交快照。

### BD07 数字内容 GraphQL 退出
- 覆盖需求：R07；AC-07-1～9。
- 设计说明：目标 schema 精确移除 `digitalContent(s)`、四个 mutation、ProductVariant/OrderLine 旧字段、Shop 默认值及不再引用的专属 input/payload/connection/type。Dashboard 消费者一并删除；普通非配送商品、文件属性、礼品卡和履约保持。
- 数据：本轮 schema 删除不级联删除 digital content、历史文件、订单行关系、token、次数、期限或自动履约配置。兼容下载仍由非 GraphQL 历史路径服务已购权益，使用不可猜 token、订单/用户校验和原次数/期限；计数用条件更新/行锁保证并发只消费一次。
- 门禁：切换前导出文件校验和、关联、token 状态、次数/期限和设置；对已付款未签发、活跃消费者和新履约路径做阻断检查。无已验证替代路径时禁售相关新商品而不影响历史下载。

### BD08 礼品卡交易记账
- 覆盖需求：R08；AC-08-1～8。
- 设计说明：checkout 完成事务中，按 GiftCard `created_at,id` 锁行排序；验证激活、未过期、同币种后，逐卡取 `min(有效余额, 剩余应付)`。每张实际扣款卡创建一个平台拥有的 `TransactionItem(source=GIFT_CARD, gift_card, source_identifier)` 与成功 charge 事件，稳定键为 checkout+gift-card+charge。
- 原子性：只在既有成功成交点扣余额并落交易；报价、加卡、失败完成不落成功事实。重复完成/异步重试按稳定键返回原交易，跨 checkout 由卡行锁防超用。外部输入不能设置 `GIFT_CARD` source。
- 计算：统一 paid/remaining 仅汇总交易成功事件，旧 `gift_card_compensation` 只用于历史审计，不再二次计入；支付应用只接收礼品卡之后的剩余金额。税基、订单确认与全额礼品卡原规则保持。GraphQL 始终只返回掩码卡标识，完整码受既有专门权限保护。

### BD09 多来源退款编排
- 覆盖需求：R09；AC-09-1～10。
- 设计说明：`transactionRefundCreate` 以 order+idempotencyKey 唯一，校验每行正数/精度/币种、实际成功 charge 减成功与处理中 refund 的可退额。持久化总请求和每来源 line 后再派发，重试只处理 FAILED line。
- 礼品卡：在事务内锁原卡，增加余额并写平台 refund event；卡过期/停用不阻止退款且不改激活/到期，找不到卡则明确失败。外部来源调用所属 App/支付路径；外部成功先持久化 PSP 事实，再更新本地汇总，避免落账失败后再次发起。
- 汇总：逐行 `PROCESSING/SUCCEEDED/FAILED`，总状态允许 `PARTIALLY_SUCCEEDED`，不得用订单取消或库存回库推导资金成功。只有所有事实确认后显示全成功。入口要求 `HANDLE_PAYMENTS` 和订单可见性；卡状态管理另需 `MANAGE_GIFT_CARD`。

### BD10 历史资金归一与对账
- 覆盖需求：R10；AC-10-1～7。
- 设计说明：离线命令先盘点 Payment、TransactionItem/Event、GiftCardEvent、旧补偿与订单金额，按证据规则输出候选/冲突/未知。可信礼品卡事实创建 `source=GIFT_CARD,reconciliationStatus=NORMALIZED,migrationReference` 的交易/事件或映射；绝不调用 PSP、扣/增卡余额或触发顾客通知。
- 作业：以 run ID、对象游标和确定性 migration key 分批续跑；启用新记账前设切换水位，订单只能由新旧一个流程扣卡。证据不足保留旧账并标 `PENDING_REVIEW`，不开放自动退款。
- 对账：逐币种核对卡余额、订单实付/已退、交易事件和来源，输出处理数、差异、审计映射、重试结果。人工登记使用 `transactionExternalRefundReport` 或受限映射入口，保存审核人、时间、证据引用且不触发资金动作。

### BD11 交易连接查询
- 覆盖需求：R11；AC-11-1～9。
- 设计说明：新增 `transactions` Relay connection，要求 `HANDLE_PAYMENTS` 并与节点/计数共享渠道 scope。支持 ID、token、交易或事件 PSP reference、order、checkout、channel、UTC created range、历史 app identifier、gift card ID；字段间 AND，数组内 OR，以 `distinct` 防重复。
- 排序：默认 `created_at DESC,id DESC`，反向分页使用相同复合游标，最大页大小沿用平台 100，不提供无界导出。PSP 精确查询直接关联 TransactionItem/Event 索引，不依赖订单全文索引或数量截断。
- 兼容：保留既有 `transaction(id|token)`；卸载应用的 identifier 作为历史快照保留。giftCard 关系遵守礼品卡权限且不暴露完整码，订单深链继续执行订单权限。

### BD12 四类支付插件退出
- 覆盖需求：R12；AC-12-1～7。
- 设计说明：从插件发现/默认配置、安装入口、环境示例和运行注册移除 Dummy、DummyCreditCard、Braintree、Razorpay，仅删除其专属依赖；插件框架、Webhook 支付、保留的内置能力、Payment 模型及未列入范围的 API 保留。
- 历史：订单与 Payment resolver 只依赖持久化通用字段，不 import 已删插件。预检按 plugin/channel 列出 checkout、authorization、refund、pending event 和售后义务；无已验证替代路径时阻断切换。
- 外部处理用 BD09 的登记接口，保存渠道、PSP reference、操作者、时间、证据和幂等键，并明确不执行 provider action。凭证备份、撤销及替代端真实验证属于 BD17 门禁。

### BD13 密码策略与切换门禁
- 覆盖需求：R13、R14；AC-13-1～10、AC-14-1～4。
- 设计说明：部署配置 `PASSWORD_POLICY` 枚举为 ALL/CUSTOMERS_ONLY/DISABLED，缺省 ALL，未知值在启动配置检查中失败。`Shop.passwordPolicy` 和可用外部认证匿名可读且不接收账号参数。
- 强制点：集中 `assert_password_allowed(user/current_is_staff, operation)`，接入 token 登录、注册密码、set/change password、reset 请求与完成、员工邀请及 refresh/session 建立。CUSTOMERS_ONLY 只允许当前 `is_staff=false`。拒绝统一返回 `PASSWORD_NOT_ALLOWED_BY_POLICY`；找回请求保持防枚举成功外观但不发邮件。
- 收紧：策略 revision 纳入本地会话/refresh 校验，受影响会话及来源不明旧会话失效；密码哈希、订单和外部身份不删，放宽也不复活会话。外部身份必须以 provider 已验证 subject 绑定，不能仅靠可控邮箱取得员工权限。
- 门禁：预检只输出人数、外部覆盖和未知会话统计；切换到收紧值要求有管理权限的外部账号真实登录/回调/刷新记录、无密码邀请说明、恢复 ALL 演练和责任人。外部服务故障不自动放宽。

### BD14 扩展挂载点
- 覆盖需求：R15；AC-15-1～8。
- 设计说明：在 `AppExtensionMountEnum` 和 Manifest validator 加五个详情 Widgets 值；既有 mount、target、参数与 POPUP 默认不改。WIDGET 仍使用现有扩展实体、所需权限、HTTPS URL、GET/POST options 与签发 token 流程。
- 校验：manifest 安装/更新整体验证 mount/target/origin/options/权限，失败不部分替换。启动时同时检查员工权限与 App 权限，只下发对象 ID 和可选当前渠道；token audience/origin 精确匹配，停用/卸载/撤权立即使新 token 和入口失效。

### BD15 应用运行状态
- 覆盖需求：R16；AC-16-1～7。
- 设计说明：构建只读 `AppOperationalStatus` projection：安装 Job 失败、App `isActive=false`、异步 delivery 失败耗尽、同步 breaker OPEN/HALF_OPEN、健康或未知；监控状态另分 DISABLED/OBSERVING/ENFORCING/UNKNOWN。列表、详情与提醒复用同一 resolver/service。
- 聚合：返回最近状态变化、脱敏原因、受影响 sync event 和有权 delivery 引用。权限不足时仍可返回必要影响状态但 issue 细节/投递按既有权限置空或过滤。底层查询/监控不可用映射 UNKNOWN，不映射 HEALTHY。
- 恢复：保留 Base 阈值、半开和自动恢复，不改变升级默认监控开关；隔离粒度为 app+event。保留异步 retry 与启停，API 不新增阈值编辑、强制清零或同步资金动作重放。

### BD16 通知契约与可靠投递
- 覆盖需求：R17、R18、R19；AC-17-1～5、AC-18-1～9、AC-19-1～11。
- 设计说明：新增 SHOP_UPDATED、SHOP_ADDRESS_UPDATED、TRANSACTION_ITEM_CREATED/UPDATED 与八类 metadata event；AttributeValue 保留原创建/更新/删除事件。新增事件仅允许 subscription query；旧事件保留 FIXED/已有 query。Webhook `channels=null` 表示全渠道，空数组非法。
- 触发：业务事务内按 `(event_type, object_id, commit_group)` 合并实际变化并写 outbox；创建的初始 metadata 只随 created event，批量只登记成功对象，同值/失败/回滚不登记。交易状态或金额/退款事实变化触发 UPDATED。事件 ID 在逻辑事件创建时固定，重试复用；每个对象的 `objectVersion` 单调递增，供消费者检测乱序但不承诺跨对象顺序。
- 授权：创建/更新时验证事件所需领域权限、query 结构/字段、App 权限和渠道；投递时按当前权限再次裁剪/拒绝。subscription resolver 只执行所选字段，私有 metadata、员工信息、卡码、密码/密钥/凭证均不越权。渠道对象按 Webhook scope 过滤；撤权即时生效。
- 样例：`webhookSubscriptionSample` 使用固定合成对象、事件 ID/时间，不查询生产数据、不触发资金动作。字段权限仍验证，错误定位到 query。
- 投递：提交后 worker 锁 outbox，创建 PENDING delivery，有限退避重试，成功/耗尽持久化；worker 崩溃可重复但不丢。签名沿用 Base，队列中不视为成功。Webhook 停用后不登记新 delivery，重启只处理明确未成功记录。同步 webhook 维持现有响应和 breaker 语义。

### BD17 受控切换和恢复
- 覆盖需求：R20；AC-20-1～11。
- 设计说明：交付 runbook 固定 API/worker/Dashboard 镜像摘要与本目标 schema。预检汇总旧数字消费者、固定 payload、四插件渠道、密码影响、资金未知与对象规模，不输出密钥。外部管理员、替代支付/售后、数字履约和受控通知端须有责任方真实验证记录。
- 顺序：一致性备份及校验 → 停入口写、排空/暂停 worker、盘点回调/outbox → schema/数据前向变更 → 历史权益保护 → 资金归一/逐币种对账 → 索引重建 → 订阅预检 → P0 验证 → 开流。每步有停止条件、checkpoint 和责任人。
- 恢复：开放后若产生订单/资金/通知，先停写并保留增量对账，优先前向修复或可重放恢复；禁止直接恢复旧数据库抹除事实。RTO/维护时长只记录演练实测，不在设计中虚构。

## 4. 接口清单

| 接口 | 提供方设计单元 | 对应需求 | 状态 |
| --- | --- | --- | --- |
| 既有 `shopSettingsUpdate`、`shopAddressUpdate` 及新增事件 | BD01 | R01、R17 | 复用并扩展语义 |
| 既有内容/媒体 mutations | BD02～BD03 | R02～R03 | SDL 不变，强化实现语义 |
| `Channel.stockSettings.inventoryMode`、`externalShippingSettings` | BD05～BD06 | R05～R06 | 新增字段 |
| 旧数字内容字段集合 | BD07 | R07 | 从目标 SDL 删除 |
| `TransactionItem` 来源/对账字段、`transactions` | BD08、BD10～BD11 | R08、R10～R11 | 新增字段和查询 |
| `transactionRefundCreate`、`transactionExternalRefundReport` | BD09、BD12 | R09、R12 | 新增 mutation |
| `Shop.passwordPolicy`、`PASSWORD_NOT_ALLOWED_BY_POLICY` | BD13 | R13～R14 | 新增只读字段/错误值 |
| 五个 `AppExtensionMountEnum` 值 | BD14 | R15 | 枚举扩展 |
| `operationalStatus` | BD15 | R16 | App/AppInstallation 新字段 |
| Webhook 新事件、channels/payloadMode、合成样例 | BD16 | R17～R19 | 新增并兼容旧订阅 |

## 5. 验证设计

### BT01 内容与图片边界
- 覆盖：R02～R04。
- 用例：旧/新/多层列表、空节点、异常节点、脚本/协议；公网无扩展名图片、HEAD 不支持、3xx、DNS 重绑定、私网、20 MiB/4000 万像素/20 秒边界；索引旧任务晚到、单对象失败和中断续跑。
- 判定：合法内容保真、危险内容不可执行、非法新写零覆盖；媒体失败零记录/零孤立文件；新 revision 不被旧索引覆盖。

### BT02 库存与运费
- 覆盖：R05～R06。
- 用例：升级/新渠道默认、两模式、共享仓并发、无仓/预售/不跟踪、切换后旧 allocation；TTL 0/43200/86400/越界、缓存维度变化、空成功、过滤故障/熔断和成交前涨价。
- 判定：无渠道库存副本或超卖，旧订单事实不变；失败响应不缓存、不产生零价配送，关闭过滤不关闭报价/本地校验。

### BT03 资金、归一与查询
- 覆盖：R08～R12。
- 用例：多卡稳定排序、重复/并发 checkout、全额/混合支付；多来源部分退款、外部成功本地失败、原卡停用/缺失；归一重跑/断点/证据不足；PSP 非唯一、复合筛选和双向分页；已删插件历史订单。
- 判定：每张实扣卡恰一平台交易，统一实付不重复；幂等重试不重复资金动作，部分成功真实；逐币种对账闭合，查询无漏项且权限一致。

### BT04 认证、扩展与应用状态
- 覆盖：R13～R16。
- 用例：三策略覆盖全部密码入口、升格员工、旧 reset/refresh、外部 subject；五新/旧 mount、越权 manifest/origin；安装失败、停用、delivery 耗尽、OPEN/HALF_OPEN、监控关闭和查询故障。
- 判定：后端不能被直调绕过，收紧不删密码且会话失效；旧扩展兼容；未知不显示健康，故障隔离到 app+event。

### BT05 事件契约与切换
- 覆盖：R17～R20。
- 用例：各新增事件、通用/内嵌/批量 metadata、同值/回滚/部分失败、撤权/渠道、合成样例；worker 崩溃/重试/耗尽/停用重启；旧 FIXED 订阅不变；切换后产生增量事实的恢复演练。
- 判定：提交事实不丢、逻辑事件去重且投递至少一次；载荷最小授权，无敏感数据；旧订阅逐个迁移，恢复不抹除新增事实。

## 6. 其他

- 实施迁移、运行测试、启动服务和部署均不在本设计阶段执行。
- 数据库字段、索引和作业表的最终 migration 名称由实施阶段按依赖图生成，但默认值、唯一键、状态机与停止条件不得弱化。
- 任何对 PRD P0 外部路径的模拟只算接口验证，不得作为生产可用证明。
