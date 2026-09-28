# 后端技术设计：Saleor 商家经营与应用接入升级

版本：v1
责任：后端技术设计
依据：PRD 1.0，artifacts/sprint1/prd/prd.md
修订：首次交付

## 1. 方案概述

方案在 Saleor 现有 Django/Graphene/PostgreSQL/Celery/Redis 架构内演进，采用“先加模型与约束、后台幂等回填、影子核对、维护窗口切读、最后移除公开接口/插件”的顺序。资金、权益和通知均以数据库提交事实为准：礼品卡扣款与平台 TransactionItem 同事务；混合退款按来源 allocation 独立终态；Webhook 使用 transactional outbox，明确至少一次而非 exactly-once。

现有关键链路：

- Shop：`saleor/site/models.py`、`graphql/shop/mutations/shop_settings_update.py`、`shop_address_update.py`。
- 内容/图片/搜索：`core/utils/editorjs.py`、`core/db/fields.py`、`graphql/product/mutations/product_media_create.py`、`core/search_tasks.py` 及各域 `search.py/tasks.py`。
- 库存/运费：`channel/models.py`、`warehouse/management.py`、`warehouse/reservations.py`、`checkout/fetch.py`、`plugins/webhook/plugin.py`。
- 数字权益：`product/models.py` 的 `DigitalContent/DigitalContentUrl`、`product/views.py`、`graphql/product/mutations/digital_contents.py`。
- 资金：`payment/models.py` 的 `Payment/TransactionItem/TransactionEvent`、`order/utils.py` 礼品卡扣款、transaction mutations。
- 认证：`account/models.py.jwt_token_key`、`core/jwt.py`、`graphql/account/mutations/authentication/`。
- 应用/Webhook：`app/types.py`、manifest validation、`webhook/models.py`、subscription query、同步 breaker 与异步 transport。

静态 Base 只证明这些结构存在，不证明部署或测试结果。本阶段不执行迁移、服务或测试。

## 2. 需求覆盖

| 需求 | 设计单元 |
| --- | --- |
| R01 | BD01 |
| R02、R03、R04 | BD02 |
| R05、R06 | BD03 |
| R07 | BD04 |
| R08、R09 | BD05 |
| R10 | BD06 |
| R11、R12 | BD07 |
| R13、R14 | BD08 |
| R15 | BD09 |
| R16 | BD10 |
| R17、R18、R19 | BD11 |
| R20 | BD12 |

## 3. 详细设计

### BD01 · Shop 资料原子更新与变化事件
- 覆盖需求：R01
- 设计说明：保留 `SiteSettings` 单例、`Address` 与现有三个 mutation，不新建重复 Shop 表。`ShopSettingsUpdate` 在 `transaction.atomic()` 内 `select_for_update()` SiteSettings，区分 GraphQL `Undefined`、显式 null 和非法空值；普通字段与 metadata 按差异保存。同事务向 BD11 outbox 写 `SHOP_UPDATED` 或 `SHOP_METADATA_UPDATED`，值未变不写。`ShopAddressUpdate` 锁 SiteSettings，在同事务创建/原地更新/解除 company_address 并写 `SHOP_ADDRESS_UPDATED`；清空先断开 FK，提交后仅清理确认无引用的旧 Address，历史订单快照不触碰。`ShopDomainUpdate` 允许只传 name，domain 省略时保持。sender name 增加 CR/LF 拒绝，邮箱和地址继续复用 Base 校验。普通、地址 mutation 独立事务，符合分区部分成功语义。GraphQL 契约见 I01；验证以 mutation 单测、metadata 权限、outbox 数量和地址幂等为主。

### BD02 · 内容、远程图片与可恢复索引
- 覆盖需求：R02、R03、R04
- 设计说明：重构 `core/utils/editorjs.py` 为无副作用的 validate/sanitize/plaintext 三步，修复 image `ulr` 错拼。递归 list 支持 string 与 `{content, items, ...metadata}`，限制文档字节、block 数、深度和单字段长度；非法新输入在 mutation clean 阶段返回 JSON path，不进入 model save。存量异常走 tolerant read：保留原 JSON，只产安全可读 projection 与结构化告警。所有 HTML-bearing 文本统一 allowlist sanitizer，拒绝 javascript/data/vbscript、事件属性和脚本，安全 http/https/mailto 及明确允许标签保留。搜索 plaintext 只从清理后的可见节点按阅读顺序生成。

  新增 `core/files/remote_image.py.fetch_remote_image`，商品单条/bulk 与 App brand 共用。使用 hardened client，只允许公网 HTTP/HTTPS、禁止 redirect；GET streaming 同时检查 Content-Length 和实际 20 MiB 上限，总预算 20 秒，Pillow/magic bytes 验证真实格式、4000 万像素与解压炸弹。网络阶段不持 DB 锁，完整校验后短事务落存储和媒体；异常清理临时文件并脱敏 URL。I02 仅增加稳定错误码。

  搜索采用 writer 上 versioned dirty queue：对象增加 `search_index_version`、`search_indexed_version` 与 dirty partial index；业务提交以 `F()+1` 标脏。worker `select_for_update(skip_locked)` 领取批次，计算后仅在 version 未变化时清 dirty，避免旧快照覆盖并发编辑；异常按对象记录后继续。新增 `SearchIndexJob/SearchIndexJobFailure` 持久进度，支持 checkpoint、续批、失败重试和全量重建双索引/原子切换。商品、订单、顾客、礼品卡沿用原语义，Transaction 精确定位由 BD06 实现。I03 只暴露脱敏状态；标准本地环境 60 秒目标由后续验证配置测量，不写成生产 SLA。

### BD03 · 渠道库存来源与外部运费隔离
- 覆盖需求：R05、R06
- 设计说明：在 `Channel` 增加 `inventory_mode`（`LEGACY_SHIPPING_ZONES` 默认）以及 `external_shipping_quote_cache_ttl=43200`、`external_shipping_filtering_enabled=true`，TTL check constraint 为 0..86400。不要复用 `allocation_strategy`：模式选择候选仓库，strategy 只排序候选。抽取 `get_stock_source_warehouses(channel, shipping_address)`，兼容模式沿 Base 的 Channel+ShippingZone 交集，渠道仓库模式只取 Channel.warehouses；可售、checkout validation、reservation、allocation、补货和 preorder/自提相关路径全部调用同一服务。国家、配送方式、税和地址校验不进入该候选函数。已有 Allocation/Reservation 不回写；未完成 checkout 在报价/预留/complete 重新验证。库存扣减继续锁 Stock 行，多 Channel 共享仓库不复制行。

  运费 quote cache key 使用 webhook/app ID、Channel ID、canonical quote payload hash、subscription selected fields hash 与相关配置版本；TTL 取订单/checkout Channel，0 跳过 cache。成功合法空列表可缓存；异常、超时、负值/币种/精度/ID 非法不缓存。外部 filtering 关闭时仍获取 quote、执行本地校验，只跳过 checkout/order filter webhook；开启且 filter 失败/breaker open 时把受影响外部方式标 inactive。成交前重新解析选择，过期不续用，价格变化走 Base 确认。Channel 更新事务后配置版本使旧 key 不命中，不执行昂贵全量删除。I04 定义字段、权限和默认值。

### BD04 · 数字内容接口退出与不可变历史授权
- 覆盖需求：R07
- 设计说明：不能直接删除现有 `DigitalContent`，其 CASCADE 会删除 `DigitalContentUrl`。先新增不可变 `DigitalAsset(file, filename, content_type, size, sha256)` 与 `DigitalDownloadGrant(token unique, asset PROTECT, order_line SET_NULL, max_downloads null, valid_until null, download_count, created_at)`；现有 active content 与历史 URL 迁移引用 asset。回填把当时 max/url days 固化，null 保持无限，不根据当前 Shop 默认重算。下载视图只读 grant+asset，使用条件 UPDATE/row lock 原子校验并增加次数，不从 replica 判断后再 writer 自增。文件删除仅在无 active/history reference 后异步执行。

  目标 GraphQL 一次性删除冻结范围，完整清单见 I05/target schema；内部迁移模型暂保留但不注册 Graphene。切换前运行只读 consumer inventory、asset/grant 校验和对账及未交付订单报告。新销售没有已验证外部履约时由部署 preflight 阻断相关商品销售/切换，不影响历史 endpoint。恢复按 token+grant 唯一键幂等，下载计数只取较大可信事实。HTTP 契约见 `interfaces/digital-download.md`。

### BD05 · 礼品卡交易账本与来源退款
- 覆盖需求：R08、R09
- 设计说明：扩展 `TransactionItem`：`source_type`（EXTERNAL_APP/GIFT_CARD/MANUAL/LEGACY）、nullable `gift_card`（SET_NULL）、`gift_card_code_last4` 和 source app snapshot；增加 `(gift_card, created_at)`、`(source_type, created_at, id)` 索引及 gift source check constraint。checkout complete 现有订单原子事务内，按 GiftCard 创建时间/ID 确定消耗，再按 PK 排序 `select_for_update()` 防死锁；逐卡计算 min(余额,剩余应付)，原子扣余额，创建一个 TransactionItem、`CHARGE_SUCCESS` event、GiftCardEvent 和 outbox。以 checkout+gift_card+charge kind 唯一键阻止重复；失败事务不留扣款。订单实付统一从 TransactionItem 聚合，旧 gift-card compensation 字段只作迁移核对、不再累加。

  新增 `TransactionRefundRequest` 与 `TransactionRefundAllocation`，唯一 `(order,idempotency_key)` 和 `(refund_request,transaction)`。I07 强制显式来源 allocation。创建时锁所有 TransactionItem，再按 PK 锁 GiftCard，校验同 order/币种/可退额。礼品卡项在同事务恢复余额、增加 refunded_value、写 `REFUND_SUCCESS` 与 GiftCardEvent；过期/停用不激活延期。外部项先写 `REFUND_REQUEST`/pending 后调用对应 transaction app，回报按现有 transaction event 幂等键落账。跨外部系统不宣称原子：每项独立状态，聚合可为 PARTIALLY_SUCCEEDED；重试只创建失败项后续请求且不改成功项。找不到原卡明确失败，不转现金。退款与取消/退货状态分离。权限和掩码输出见 I06/I07。

### BD06 · Transaction 精确查询与渠道权限
- 覆盖需求：R10
- 设计说明：在 payment GraphQL 增加 I06 Relay connection，保留单笔 `transaction(id/token)`。构建统一 `get_transactions_for_user(info)`：要求 `HANDLE_PAYMENTS`，staff restricted channels 与 App channel scope 都转成 order/checkout Channel predicate；单笔和 connection 共用，修复只按 ID/token 取对象的潜在边界。filter 的不同字段 AND、列表 OR，递归 AND/OR 限制深度/节点数；PSP reference 对 TransactionItem 和 TransactionEvent 用精确索引/EXISTS，不走全文限额并 `distinct`。索引包含 `(created_at,id)`、`(order_id,created_at,id)`、`(checkout_id,created_at,id)`、`(app_identifier,created_at,id)`、`psp_reference` 和 event reference。默认 `-created_at,-id`，反向分页保持稳定。旧 Global ID/UUID token 解析保持；卸载 App 通过 identifier/name snapshot 显示来源。`totalCount` 使用同一权限 queryset，避免侧信道。

### BD07 · 历史资金归一与四插件退出
- 覆盖需求：R11、R12
- 设计说明：新增 `PaymentReconciliationRecord(legacy_payment unique, transaction_item nullable, status, evidence_reference, reviewed_by, reviewed_at, migration_batch)` 和 checkpoint/job。后台任务按 Payment PK 分批 writer 读取，可信证据用 `get_or_create(legacy_payment_id)` 生成 `source_type=LEGACY` TransactionItem，并把成功 Transaction 映射为 event；不调用 gateway、不改礼品卡余额、不发消费/退款业务通知。证据不足状态 `REQUIRES_REVIEW`，旧账只读。每批按 order/currency 核对 charged/refunded/pending 和一对一 mapping，错配不切读。新旧读路径影子比较，维护窗口后禁旧 Payment 新写入，但不删除表。

  Dummy、DummyCreditCard、Braintree、Razorpay 分阶段退出：先 preflight 枚举 PluginConfiguration/Channel 与未决授权退款；有使用且无验证路径即阻断；再从 available gateways、新配置及 settings 注册移除，保留历史模型查询；确认售后交接后移除专属代码/依赖，不碰 plugin framework。I08 允许有权财务登记外部已发生结果：`ExternalPaymentResult` 以 `(payment,action,idempotency_key)` 唯一，证据私有，事务内映射 event，绝不发起资金。Stripe 即使 Base changelog 标 deprecated 也不在冻结四项内，不删除。

### BD08 · 三态密码策略与会话失效
- 覆盖需求：R13、R14
- 设计说明：新增部署配置 `PASSWORD_LOGIN_POLICY`，启动时严格解析 ALL/CUSTOMERS_ONLY/DISABLED，缺省 ALL，未知值 fail-fast。I01 `Shop.passwordLoginPolicy` 公开只读。抽取 `assert_password_operation_allowed(user_or_intent)`，接入 tokenCreate、passwordChange/set/reset request/confirm、带密码注册和 staff invite；`CUSTOMERS_ONLY` 以当前 `is_staff` 为准。找回始终返回防枚举通用响应，受限账号不 enqueue email。无密码注册、外部 auth 和 App token 不走本地密码 gate。

  User 增加 `session_version bigint default 1`；JWT access/refresh/delegation token 写 claim 并在认证时与 writer/权威缓存比较。策略收紧 migration command 在维护窗口按受影响用户批量 `F()+1`，无法辨别来源的旧 token 在切换点由全局 token epoch 失效；不清密码 hash、账号、订单或 external identity。密码设置/重置、员工升格和停用与 session_version 更新同事务。放宽不减 version，旧会话不复活。外部身份员工绑定必须依赖已验证 provider subject，不按可控邮箱自动提权。preflight 管理命令要求记录至少一个管理员外部登录/refresh 验证和 ALL 配置恢复演练。

### BD09 · 五类 Widget Manifest 契约
- 覆盖需求：R15
- 设计说明：在 `app/types.py.AppExtensionMount`、GraphQL enum、manifest validation 和 fixtures 同步增加 I09 五个常量。把 Widget allowlist 收敛为 `APP_EXTENSION_MOUNT_CONFIG`，每项定义 target=WIDGET、领域权限、允许 GET/POST 和 context kind；旧 mount 全保留。Manifest install/update 先完整 parse/validate URL、target、options、权限和重复项，再在事务内 replace，任一错误不部分覆盖。运行 query 继续过滤 App active、extension permissions 和 caller permissions；停用/卸载/撤权即时不可查询/token 不可用。后端只签发短期 extension token/context claim（object ID、可选 Channel），不注入对象数据、订单/人员或长期凭证。验证覆盖五 mount、权限矩阵、非法 manifest 原子性和旧默认 target。

### BD10 · 应用状态聚合而不改变熔断策略
- 覆盖需求：R16
- 设计说明：I10 `App.operationalStatus` 是 resolver 聚合，不新增外部 health probe：安装失败沿 `AppInstallation`，主动停用沿 `App.is_active`，同步熔断读 Base breaker board，异步投递读 EventDelivery 最新失败/EXHAUSTED。监控配置映射 NOT_ENABLED/OBSERVE_ONLY/ENFORCING；Redis/状态源不可用返回 UNKNOWN/null 并记录观测错误，不回退 CLOSED。失败原因只取归一化 code/message，清理 URL query、header、payload、卡码和 token。聚合查询批量 dataloader 避免 N+1，并限制无日志权限只看计数/影响摘要。保持 Base 默认阈值、cooldown 和自动恢复，升级不自动启用 breaker；不新增调阈值、清零或资金重放接口。App 粒度 breaker 对同 App 事件影响必须在 UI/文档明确，不扩散其他 App。

### BD11 · Channel-aware subscription 与 transactional outbox
- 覆盖需求：R17、R18、R19
- 设计说明：新增 `WebhookChannel(webhook,channel)` unique 关系，I11 input 以 Channel ID 保存；旧 query `channels` slug 过渡读取并迁移，Channel 改 slug 不丢关系。Webhook create/update 在事务内一次替换基础字段、events、Channel 关系、规范化 subscription query/hash/schema version；新增事件无 query 拒绝，失败不改旧值。显式 Channel 与 query channels 冲突拒绝。注册时验证 event-field-schema 和 App permission，投递时再次按当前权限/Channel裁剪。

  新增 `WebhookOutboxEvent(UUID id,event_type,aggregate_type/id,aggregate_sequence,channel,principal,snapshot,created/available/processed,attempt_count,last_error)`；业务事务只写事实+outbox。dispatcher 用 `select_for_update(skip_locked)` 领取，解析订阅后为每 Webhook 建 EventDelivery，unique `(outbox_event,webhook)`，再标 processed。EventDelivery 增加 stable `event_id`、attempt_count、next_attempt_at 和 EXHAUSTED，成功记录保留期后清理；Celery 丢消息由周期 scanner 补投。请求头携带 Saleor-Event-ID/Delivery-ID/Attempt。同步重试沿现有结果语义且资金调用者必须幂等。

  I12 新增 SHOP_UPDATED/ADDRESS、Transaction created/updated/refunded 和八类 metadata 事件。统一 `metadata_changed(instance, changed_keys, created=False)` 由通用、内嵌、bulk 成功路径调用；创建仅进创建事件。transaction update 根据 committed aggregate 差异合并同事务同类事件。每个 aggregate 维护数据库 sequence 或在 outbox 表对 `(aggregate_type,id)` 加锁递增；payload 暴露 eventId/sequence，不承诺全局顺序。删除对象使用最小安全 snapshot，不因 resolver 查无对象无限重试。private metadata 由 subscription selection + App 领域权限双重决定。旧通用 updated 事件过渡期继续发送。

### BD12 · 迁移、预检和恢复编排
- 覆盖需求：R20
- 设计说明：提供只读 impact/preflight 管理命令与可续跑 migration jobs，不通过 schema migration 同步扫大表。阶段顺序：A 新增 nullable 字段/表；B concurrent indexes；C 数字 grant、礼品卡账、旧 Payment、Webhook Channel、search version 回填；D shadow compare；E 维护窗口停止写入/排空 worker并记录 callback/outbox；F 对账和切读；G 移除数字 GraphQL/四插件注册；破坏性清表延期。每 job 有 checkpoint、batch ID、幂等唯一键、失败对象和重试报告。

  备份覆盖 DB、media、App config、必要密钥和构建摘要；外部 callback 由持久入口接收或验证发送方重试。部署固定 API/worker/Dashboard/schema 同一摘要。开放前执行权限、资金、数字权益、索引与外部登录/支付/履约检查。开放后有新事实时禁止回滚旧 DB，先关写、保留增量并前向修复/可重放恢复。命令输出脱敏 JSON 供责任人签字；RTO 只由演练测量。

## 4. 接口清单

| 接口 | 所属设计单元 | 说明 |
| --- | --- | --- |
| I01 | BD01、BD08 | Shop 资料更新及只读密码策略 |
| I02 | BD02 | 远程图片导入稳定错误语义 |
| I03 | BD02 | 搜索索引 job 查询与失败重试 |
| I04 | BD03 | Channel 库存模式和运费配置 |
| I05 | BD04 | 数字 GraphQL 退出与历史 HTTP 下载 |
| I06 | BD05、BD06 | Transaction connection 和来源字段 |
| I07 | BD05 | 按来源幂等混合退款 |
| I08 | BD07 | 旧支付外部结果受限登记 |
| I09 | BD09 | 五类 Widget mount enum |
| I10 | BD10 | App 故障状态聚合 |
| I11 | BD11 | Webhook Channel 和稳定投递 |
| I12 | BD11 | Shop/Transaction/metadata 新通知 |

## 5. 工程任务与依赖

### BT01 · Outbox 基础与稳定投递
- 覆盖设计单元：BD11
- 依赖：无
- 工作与验证：新增 outbox/EventDelivery 字段、dispatcher、scanner、唯一约束、保留清理及请求头；验证提交/回滚、worker 崩溃、重复 enqueue、耗尽/retry 和 eventId 稳定。

### BT02 · Shop 原子 mutation 与事件
- 覆盖设计单元：BD01
- 依赖：BT01
- 工作与验证：收敛字段省略/null、地址事务、sender 校验和三类 Shop outbox 事件；验证部分成功由两个 mutation 明确表达。

### BT03 · EditorJS 兼容 sanitizer
- 覆盖设计单元：BD02
- 依赖：无
- 工作与验证：实现 validator/sanitizer/plaintext、限制和告警，修复 `ulr`；覆盖旧/新列表、空节点、危险协议、存量异常与各业务域调用。

### BT04 · 统一远程图片下载器
- 覆盖设计单元：BD02
- 依赖：无
- 工作与验证：替换 Product 单条/bulk 与 App brand 路径，验证 SSRF、DNS、HEAD failure、stream limit、像素、redirect、临时文件清理和日志脱敏。

### BT05 · 版本化搜索队列
- 覆盖设计单元：BD02
- 依赖：无
- 工作与验证：模型/partial index、worker、SearchIndexJob API 与重建切换；验证并发编辑、续跑、单条异常、权限和标准环境 60 秒目标。

### BT06 · Channel 配置与库存路径统一
- 覆盖设计单元：BD03
- 依赖：BT01
- 工作与验证：加 Channel 字段/约束/I04，替换可售/预留/分配/补货候选函数；多 Channel 共享库存、旧 allocation、无仓库和自提矩阵验证。

### BT07 · 外部运费缓存与过滤
- 覆盖设计单元：BD03
- 依赖：BT06
- 工作与验证：canonical key、Channel TTL/filter、响应校验和成交前重验；覆盖 TTL 0/43200/86400、空列表、breaker、配置变化、涨价和订单快照。

### BT08 · 历史数字授权快照
- 覆盖设计单元：BD04
- 依赖：无
- 工作与验证：DigitalAsset/Grant、回填/对账、下载原子计数和恢复工具；消费者门槛满足后移除目标 SDL 明确字段，验证历史 token/无限权益。

### BT09 · 礼品卡 TransactionItem 双写与切读
- 覆盖设计单元：BD05
- 依赖：BT01
- 工作与验证：模型字段/约束、checkout 锁序、交易/event 创建和旧补偿影子核对；覆盖重复 checkout、多卡顺序和跨 checkout 并发。

### BT10 · 来源退款编排
- 覆盖设计单元：BD05
- 依赖：BT09
- 工作与验证：RefundRequest/Allocation/I07、gift card 原子恢复、外部 report、部分成功和 retry；覆盖同幂等键、超退、原卡停用/缺失及本地落账补偿。

### BT11 · Transaction connection 与权限
- 覆盖设计单元：BD06
- 依赖：BT09
- 工作与验证：统一 queryset、filter/sort/index 和 I06；验证精确 reference、稳定前后分页、Channel restriction、count/detail 一致与无重复。

### BT12 · 历史账迁移与插件退出
- 覆盖设计单元：BD07
- 依赖：BT11
- 工作与验证：reconciliation jobs/I08/preflight，禁四插件新配置与注册；按插件/Channel/义务清单验证，保留旧 Payment 查询且不删除其他插件。

### BT13 · 密码策略与会话版本
- 覆盖设计单元：BD08
- 依赖：无
- 工作与验证：配置 fail-fast、所有密码 gate、session_version claim/refresh、收紧命令与 preflight；覆盖三态、员工升格、旧 reset/invite、防枚举和外部 subject。

### BT14 · Widget mount 与权限矩阵
- 覆盖设计单元：BD09
- 依赖：无
- 工作与验证：五常量、manifest config、GraphQL enum 与短期 context；验证非法声明原子失败、撤权失效和旧 mount 回归。

### BT15 · App 状态聚合
- 覆盖设计单元：BD10
- 依赖：BT01
- 工作与验证：dataloader resolver/I10 和脱敏；模拟状态源失败、observe/enforce、breaker、异步耗尽和权限差异。

### BT16 · Channel subscription 与新增事件
- 覆盖设计单元：BD11
- 依赖：BT01、BT02、BT09
- 工作与验证：WebhookChannel、query 原子编译、I11/I12、metadata hooks/sequence；验证 fixed payload 兼容、字段最小化、撤权、bulk 部分失败和删除 snapshot。

### BT17 · 受控切换工具与演练
- 覆盖设计单元：BD12
- 依赖：BT05、BT08、BT10、BT12、BT13、BT16
- 工作与验证：impact/preflight/backup manifest/checkpoint/reconciliation/open checks 与恢复 runbook；所有 P0 有结果且无数据/权限/资金 blocker 才允许切换。

## 6. 其他

- 数据库风险：Transaction、EventDelivery、Payment、Digital URL 和商品索引均可能是大表；新增索引使用 `atomic=False` + concurrent index，回填后再 attach NOT NULL/CHECK，避免长事务。
- 锁风险：礼品卡、TransactionItem、Stock 始终按主键排序锁定；网络请求不在持锁事务中执行。混合退款的外部动作不可形成分布式原子事务，必须保留部分成功事实。
- 安全风险：图片 SSRF、private metadata、完整卡码、下载 token、Webhook header/payload 和证据引用均按敏感数据处理；日志做 allowlist 输出。
- 契约风险：目标 SDL 使用 type/input/enum extension 保留 Base 定义，并完整删除 `DigitalContent`。当前环境的 `graphql-core 2.3.2` 不支持 Base 使用的现代 description/extension 语法，无法完成兼容 parser validation；实施必须用项目支持的 GraphQL 工具执行 schema build、codegen 和 breaking-change 检查。
- PRD/Base 差异记录：Base 的 Channel `allocationStrategy` 不是冻结 PRD 的库存模式；不得采用“关闭库存跟踪”替代“仅按渠道仓库”。Base 有同步 breaker 手工 re-enable，但 PRD 不允许把强制清零作为故障页恢复方案，本设计不新增该入口。
- 未决上线依赖不是设计缺失：真实插件使用、消费者清单、历史证据、外部管理员登录、支付/履约路径、存量规模及维护窗口仍由 PRD §6 指定责任方补齐；证据缺失时 preflight 失败。
