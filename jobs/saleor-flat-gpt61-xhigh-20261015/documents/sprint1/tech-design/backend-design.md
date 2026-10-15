# 后端技术设计：Saleor 3.23 结账、资金与商户运营一致性

版本：v1  
责任：后端技术设计（Tech Owner）  
依据：PRD v1，`artifacts/sprint1/prd/prd.md`；`instruction.md`、`business-conversations.md` 共同作为业务输入  
修订：首次交付；仅设计和只读核对，不开发、不执行迁移、不修改冻结 PRD。

## 1. 方案概述

采用既有 Django/PostgreSQL + Graphene GraphQL + Celery 架构，不拆新服务。以“当前业务事实 + 原子本地写入 + 外部请求幂等 + 提交后独立事件”为一条链路：库存来源、配送资格、支付净额、成单资格均由共享服务决定，API、后台任务、订单和 Dashboard 不各自重新实现规则。完整协议权威为 `interface-contract.md` 与 `target-schema.graphql`；目标 SDL 以提供的 Core Base 完整 schema 增量形成，未读取升级后版本。

基线 Core 提交为 `c864e66b8e537d30732ddba62d3a4c47e49e4a3e`，Dashboard 为 `aebb2401b5079fbbb8c60150289d1896c108feca`。现有可复用落点包括：
- 配送：`saleor/graphql/checkout/mutations/checkout_delivery_method_update.py:43` 的 `CheckoutDeliveryMethodUpdate`，`checkout/fetch.py`、`graphql/checkout/mutations/utils.py`；`shippingMethods`、`deliveryMethod` 已存在，主动重算是新增。
- 成单：`checkout/complete_checkout.py:1596`、`:1817` 已有 checkout 锁及既有订单查找；`checkout/tasks.py:134` 是单结账任务，不具备本轮批次/时间范围合同；`order/models.py` 的 `checkout_token` 不能当成已经存在唯一约束。
- 库存：`warehouse/models.py`、`warehouse/availability.py`、`warehouse/management.py` 的现有分配/预留。`allocationStrategy` 是仓库优先次序，不能代替库存来源策略。
- 支付：`payment/transaction_item_calculations.py`、`payment/models.py`、`payment/utils.py`；交易 `chargedAmount`、`authorizedAmount` 和 Payment `capturedAmount` 为当前剩余额度。礼品卡 Base 是抵扣/成单扣卡，尚无完整交易生命周期。
- 身份/安全：`graphql/account/mutations/authentication/`、`plugins/openid_connect/`、`core/utils/editorjs.py`。Base 尚无密码三态；宽松清洗不能充当保存前结构校验。
- App/事件：`app/manifest_validations.py`、`app/installation_utils.py`、`webhook/transport/asynchronous/transport.py`、`graphql/webhook/mutations/event_delivery_retry.py`。Base `mount/target/options` 向当前合同迁移；延期构建不能只覆盖已有 checkout 特例。

所有拟新增服务、模型及字段均是实施计划，不表示已经实现。仓库路径下述均相对 `/workspace/repos/saleor/`。

## 2. 需求覆盖

本轮有明确对外接口变更，完整目标 SDL 为必交。R14/R15/R20/R21/R29 的界面上下文归前端，后端仅承接过滤/授权/保存冲突和相关协议；不新建 Storefront。

| 需求 | 设计单元 |
| --- | --- |
| R01、R02 | BD01 |
| R03 | BD02 |
| R04 | BD03 |
| R05、R06 | BD04 |
| R07、R08 | BD05 |
| R09、R10 | BD06 |
| R11 | BD07 |
| R12、R13 | BD08 |
| R14、R15（对象过滤、导出授权） | BD09 |
| R16、R17 | BD10 |
| R18 | BD11 |
| R19、R20（安装及表单保存）、R21（现有目录边界） | BD12 |
| R22、R23 | BD13 |
| R24、R25 | BD14 |
| R26、R27、R28、R29（保存版本）、R30、R31 | BD15；各业务单元共同遵守 |

## 3. 详细设计

### BD01 · 当前配送重算、更新与最终验证
- 覆盖需求：R01、R02、R26。
- 在现有 checkout mutation 层新增 `CheckoutDeliveryRecalculate`，抽出共享 `recalculate_delivery_options` / `validate_delivery_selection`（拟新增）供重算、更新、人工及自动完成调用。用当前主库 checkout、行、地址、渠道、插件管理器重新获取 SHIPPING_LIST_METHODS_FOR_CHECKOUT 和 CHECKOUT_FILTER_SHIPPING_METHODS 适用结果；缓存须绑定 checkout revision、渠道关系/服务结果有效期，显式重算不复用过期结果。
- 新增 `Checkout.version`，业务变更（行/地址/渠道/客户/配送/资金事实）递增；配送计算先读取版本，外部调用在锁外完成，随后短事务锁 checkout、复核版本和对象授权。版本变动返回 `CONFLICT` 不写；避免持锁等待服务。最终成单使用同一版本/有效期令牌重新确认，服务返回的有效期过期须重新请求；没有有效期的外部方式在完成边界再次验证。
- 成功计算一次性保存所需缓存/清理失效选择；返回所有 shippingMethods（inactive 可保留 `active=false/message`）、合法 collectionPoints、有效 `deliveryMethod`。原选择失效：清为空，`selectionStatus=INVALID`、`selectionError` 表明 expired/unavailable/not applicable，不自动代选。输入/服务失败：原选择和所有已保存数据不变，payload `errors` 非空，结果列表为稳定空列表而非“成功无选项”；调用方不得仅看列表。
- 兼容 ShippingMethod、Warehouse 和 Base 外部 App 编码 ID；ID 本身可为全局共享配送实体，不要求虚构“每结账专用ID”，但必须由当前结账的计算结果确认适用性，外部 ID 不得从其他结账缓存解析。旧 `checkoutShippingMethodUpdate` 按 Base shipping-only 语义适配，`shippingMethod` 对自提为空且保持弃用；`deliveryMethodId=null` 明确清除。数字商品只免配送检查。
- 更新/完成失败不部分改地址、选择、预留、资金或订单。不存在、无对象权先于配送计算；敏感价格/地址不可出现在错误。验证覆盖现有 `graphql/checkout/tests/mutations/test_checkout_delivery_method_update.py` 及 complete/shipping 测试，新增失效原因、同步失败、版本竞争、合法旧 ID、自提/清除场景。

### BD02 · 渠道仓库来源与库存一致性
- 覆盖需求：R03、R05、R30。
- `Channel.stock_source_strategy` 新增 `SHIPPING_ZONE|CHANNEL`；GraphQL `stockSettings.sourceStrategy`，与 `allocationStrategy` 正交。新店及迁移默认 `SHIPPING_ZONE`；读取旧地址参数保持可用。在 CHANNEL 模式，候选集合仅为渠道直接关联仓库，地址不可改变集合；配送区域仍可影响配送，不可偷偷限制库存来源。
- 在 `warehouse/models.py` 的 stocks queryset / `warehouse/availability.py` 抽出共享 `eligible_warehouse_ids(channel, address, ...)`（拟新增）。商品 availability/quantityAvailable、checkout validation/reservation、order allocation/reallocation、draft completion、fulfillment creation/change warehouse 和 collection-point 验证均消费它。先确定合法集合，再扣 allocations/有效 reservations，最后按既有 allocationStrategy 排序；不跟踪库存、预售合法规则仍走原例外，不强行归零。
- 关系修改与 sourceStrategy 保存锁 Channel、递增 settingsVersion 并使库存/配送缓存失效。新增预留/分配时短事务锁渠道配置及 stocks，按稳定 pk 顺序锁行；多行 all-or-nothing，数量比较使用 DB 整数，失败回滚本动作的全部 reservations/allocations。禁止只凭 replica 读出的可售量提交。已有分配不凭新关系丢账；新增或改仓动作要求最新合法关系，履约既有合法分配按已记录事实完成，不自动删除历史 allocations。
- 迁移只加策略默认值，不新增/删除渠道仓库或改库存数量；关系/库存变化立即失效对应查询缓存。测试 legacy 模式等价、关联3/未关联10、新模式地址不影响结果、移除关系、两请求抢最后库存、任一行失败回滚，覆盖 warehouse/checkout/order 的现有测试。

### BD03 · 商品编辑上下文的服务端渠道诊断
- 覆盖需求：R04。
- 拟新增 `Product.channelAvailability`，后端在 product/channel listings、变体价格、共享库存来源、发布时间、渠道状态及 shipping zones 上计算，不调用外部配送/税务，不修改商品。过滤 `search` 为渠道名不区分大小写包含，`currency` 为合法币种精确匹配；固定 channel pk 稳定分页，最多100。仅 MANAGE_PRODUCTS 且具备渠道读取权限/对象范围的员工或 App；先过滤可见渠道再计算 count/detail。
- 诊断规则优先展示 CHANNEL_INACTIVE / PRODUCT_NOT_LISTED_IN_CHANNEL / PRODUCT_NOT_PUBLISHED / PRODUCT_NOT_YET_AVAILABLE 等根阻断。上游未满足时不把正常依赖重复计阻断；检查适用的变体价格/合法仓库/库存，无一个可售变体才报商品级阻断，单个缺货变体在其他可售变体存在时为 WARNING。数字商品 `SHIPPING_NOT_REQUIRED/NOT_APPLICABLE`，库存/发布照查。SHIPPING_ZONE 模式的可配送商品检查配置可达区域；CHANNEL 模式只把缺配送区域作为配送资格问题，不改库存候选规则。
- `issueCount` 只计 BLOCKING+WARNING，与本行 issues 一致，不计 NOT_APPLICABLE；`evaluatedAt` 是本次计算时间，不宣称预测成交结果。Core 最终检查仍为权威。批量 loaders/prefetch 避免每渠道每变体重复查询；测试未发布正常依赖、数字缺货、多变体 warning、权限/分页/币种和结果数量。

### BD04 · 自动完成配置、批次复核与一次成单
- 覆盖需求：R05、R06、R29。
- `CheckoutSettings` 增 `automaticCompletionDelay: Minute!`、`automaticCompletionCutoffDate: DateTime`；DB delay 默认0（技术默认，非业务提供 SLA），cutoff 默认 null，原开关默认false且不改变已明确配置的值。启用且参数合法才保存。所有配置保存整体 CAS：`Channel.settingsVersion` 与 `ChannelUpdateInput.expectedVersion`，修改 checkoutSettings/stockSettings 必须传版本；显式 null delay/开关非法，omission保留，cutoff null 清下界；失败留最后生效值。checkout-only 配置保持 Base MANAGE_CHANNELS 或 MANAGE_CHECKOUTS 权限，stock/关系要求 MANAGE_CHANNELS；混合更新必须满足整个组合权限。
- 使用 Celery beat 的有界扫描（复用现行任务队列/重试设施），每批固定 pk 游标，有任务级 batch_size/batch_count，非新增业务数值承诺。候选：渠道开启、未完成、created >= cutoff（inclusive），`last_change < now-delay`（严格超过）。支付事件及最近修改可唤醒处理，但不能绕过delay/cutoff；旧单结账入口转入同一服务。旧 funds TTL/cutoff 原字段原语义独立。
- 资格复核不看包含 pending 的 charge_status=FULL 就结束：成功当前授权+扣款净额足以覆盖当前应付、无冲突的扣款/退款/取消 pending，并满足所支持 Transaction/Payment 流程；Legacy Payment 仅接受其真实合法授权/扣款状态。客户或有效邮箱、账单、适用配送/地址、非空可售行、库存、total>0 都执行。完整授权路径后续是否捕获沿用渠道/支付原策略，不因自动化再扣已捕获款。
- 新建内部 `CheckoutCompletionRecord`，唯一 checkout token，持久化 `status/attempt_version/order_id/error_code/field/sanitized_message/next_attempt_at`；claim用短事务 `select_for_update(skip_locked)`，PROCESSING 有 lease 可恢复。最终先锁配置复核开关，再锁 checkout/关联交易/库存，复用 complete_checkout 分支；以 completion record 的唯一键而非假设现有 order.checkout_token唯一保证人工、后台、重试共享互斥。创建订单和记录COMPLETED、库存写入、transaction/Payment关联迁移在同一本地事务；checkout删除后通过 record 返回已完成 order，不从“checkout不存在”推定成功。
- 不在数据库事务内重复调用外部扣款：支付请求表+稳定动作key先记录待确认，外部返回明确成功后进入成单；未知结果先对账再重试同key。失败回滚本地订单/库存，不逆向抹除已经发生的真实资金成功事件。事件 outbox 唯一 `(completion_record,event_type)`；一次 ORDER_CREATED/完成通知，delivery 可独立重投但不新生成业务事件。成功订单金额永久不因重试重算。
- 资格失败 BLOCKED，外部/基础设施失败 FAILED，已到范围尚未执行 WAITING；条件改变/lease恢复/受控重试可再次处理；失败批次不阻断其他checkout。`Checkout.automaticCompletion`仅暴露受管理权限保护的当前记录，无新增独立自动化报表。测试冻结时钟的恰好delay/超过delay/cutoff等于、排队后停用/改库存、Legacy Payment、fully authorized/charged/pending、人工竞态及重试。记录补迁移从既有 order.checkout_token建立关联（先检查重复，不删除/改金额）。

### BD05 · 礼品卡统一交易、取消与退款
- 覆盖需求：R07、R08、R09、R11。
- 内建 `saleor.gift-card` adapter（拟新增）接入现有 `transactionInitialize/transactionProcess/transactionRequestAction`，不是 App token、不是普通支付回退。初始化 data 合同 `{code: string}`，gateway可见性只对允许消费礼品卡的结账/订单开放；授权与扣款按 action AUTHORIZATION/CHARGE。产生 `TransactionItem`、受遮罩 `GiftCardPaymentMethodDetails` 和标准 TransactionEvent。`transactionProcess` 延续同一对象及初始化策略，不重新建另一授权。
- 新增 `GiftCardTransactionReservation`（transaction/card唯一关联，active/reserved/charged/released状态及 Decimal 金额）和内部资金动作记录。授权锁卡/业务对象、验证存在/启用/有效期/币种/可用额度/权限，增加 reservation而非从currentBalance永久扣款；`availableBalance=currentBalance-active reservations`。扣款消耗本授权占用并一次减少currentBalance；直接CHARGE仅在余额足够时一次完成。金额全程币种quantize，任意同卡并发不可超用。
- Checkout 未完成有效授权可 CANCEL，释放未消费reservation且写取消事件；订单已扣款REFUND受availableRefundAmount限制、一次回充currentBalance。不能用取消抹掉已扣款，不能因卡余额变动把历史事件金额改掉。订单退款允许按原交易退回过期/停用卡（退款是恢复该交易资金，不是新的消费）；不存在卡的历史关联先执行可诊断修复，不凭空创建普通交易。错误码区分卡不存在/停用/过期/币种/不足、状态/金额/幂等冲突，先授权再暴露金额。
- 幂等账 `(actor, object, action, key)` 关联请求指纹及结果；same key same fingerprint 返回原有效结果，异参返回IDEMPOTENCY_CONFLICT。网络重试禁止生成新key；请求发起/事件/余额写同事务。Base giftcard抵扣路径过渡期间与新adapter互斥（同checkout不得混模式），避免 add_gift_cards_to_order 再扣统一交易卡。迁移既有使用记录为带来源唯一键的合成历史CHARGE/REFUND事件，**只写交易映射，不动余额、不重发事件/通知、不改总额**；保留关联显示和无事件合法空列表。
- 新增礼品卡 amount-basis标志：既有订单LEGACY_TOTAL_DEDUCTION，新adapter订单TRANSACTION_PAYMENT。旧 checkout 带抵扣卡时延续 legacy完成，已切换checkout按完整总额支付，禁止混加旧抵扣。测试授权/扣款/取消/等额退款/超额/同卡竞争、失败原事实不变、历史重复迁移和20+30=50对账。

### BD06 · 服务端金额摘要、净额和资金动作
- 覆盖需求：R09、R10、R26。
- 新增共享 payment summary calculator，Order/Checkout.paymentSummary消费。不重算税或优惠：商品/配送使用持久化或当前计算 `TaxedMoney`，discount为解释项，tax已包含gross，不再加一次；余额沿用Core totalBalance语义（欠款负），`outstanding=max(-balance,0)`。声明 `paymentFlow` 选择主流程，Transaction/Payment不能盲目双加，同业务映射去重。
- `authorized/charged` 是成功事件后**当前净额**；`refunded`是历史成功退款解释项，不能再从charged减；pending分字段。Base Payment capturedAmount按其独立算法聚合。LEGACY_TOTAL_DEDUCTION：total保持历史已减卡金额，payableBeforeGiftCards由可靠历史消费记录还原，balance不再扣合成卡交易；TRANSACTION_PAYMENT：total为完整商品应付，礼品卡列入charged一次。礼品卡单列是charged组成项，不是另外优惠。无法恢复的历史giftcard细节不按当前余额编造，保留审计标识并阻止迁移虚构金额。
- 交易 `availableChargeAmount=max(authorizedAmount-chargePending-cancelPending,0)`，`availableRefundAmount=max(chargedAmount-refundPending,0)`，还需减本动作已经占用且尚未同步进聚合的内部reservation（只计一次）。订单granted refund不能被当成已执行退款，但相同退款请求需去重/占用。动作锁交易/订单并复核最新额度；移除 `or maximal` 和 `min`裁剪：未传amount才取接口允许的max，显式0或负值拒绝，超額拒绝，等额合法。
- orderCapture/orderRefund沿用要求amount必填且>0；transactionRequestAction可省amount，用提交时当前合法额度，0拒绝。orderMarkAsPaid先拒绝任意冲突 Payment/Transaction，再校验账单/状态，按 markAsPaidStrategy生成一条对应事实；legacy gateway和giftcard方法仅展示实际支持actions。
- transactionRequestAction/process及order资金动作新增可选idempotencyKey；Dashboard必传稳定UUID字符串。无key旧客户端不能获得“重发相同请求”的承诺，服务端仍用锁+pending额度防超用；成功mark重复可返回原结果不新建。外部request用持久化action/outbox key，HTTP超时保持pending，只有确认事件更新净额，失败事件保持可追踪，不假装完整回滚外部事实。
- 使用 order mutations、transaction request action、transaction calculations现有测试加币种精度/零/边界/超额/同key/不同key并发/打开弹窗后额度改变/净额80不变60/Payment退款等用例。

### BD07 · 根级基础交易定位与受限分页
- 覆盖需求：R11、R26、R28。
- Query新增 transactions，独立 `RootTransactionFilterInput`，不误用Base供Order where使用的TransactionFilterInput。过滤仅orderIds/checkoutIds/ids/pspReference/appIdentifier：字段之间AND，数组内OR；omission不限此维度，空数组明确合法空集合，null项/错误ID类型拒绝。pspReference精确匹配交易及其事件参考号并distinct；appIdentifier精确匹配App.identifier，giftcard内建adapter不伪装成App。
- 固定主键升序游标（可反向last/before），无sortBy、无日期/事件过滤，无专用新索引。使用既有FK/主键/identifier读取，权限scope先于count/pagination。first或last必须有且在1..100，二者互斥；after与before组合按Base游标合法窗口，非法游标/超界值为顶层INPUT错误，数据集尾页是合法空页。
- 客户仅已认证且其订单/checkout所有者，不允许通过知道另一个token列举其他交易；员工需HANDLE_PAYMENTS并具对象/渠道范围；App需HANDLE_PAYMENTS且交易属于自己或明确被授予的处理对象（普通管理App不自动列全商店）。单条transaction旧HANDLE_PAYMENTS入口保留，扩展customer-owned读取同时严格字段保护。交易私有metadata/createdBy/user/卡code字段单独检查；public payment method只给遮罩。无全局权限显式权限错误，指定受限对象按NOT_FOUND保护存在性，不能把整个失败假装success empty。
- 合法组合、多交易/礼品卡、准确净额/事件、无事件空列表、分页稳定、非法null/UUID/slug混用和身份矩阵均新建resolver测试。

### BD08 · 主体增强搜索及基础搜索边界
- 覆盖需求：R12、R13、R31。
- 结账/礼品卡/商品/订单用PostgreSQL既有搜索基础扩展主体search vector，仅对这四域维护。输入trim、Unicode规范化、大小写标准化、重复词去重；无引号词按AND；未闭引号拒绝；双引号短语使用phrase词序；仅未加引号末尾词允许prefix。相关度排序RANK仅在有search时有效，rank相同以pk稳定tie-break，游标携带rank/pk和过滤指纹；新增CheckoutSortField/GiftCardSortField.RANK，Product/Order沿用现有RANK。固定数据集保证游标稳定，变化后要求重查而非宣称快照分页。
- 技术支持边界：search原串最多256 Unicode字符（本设计取值，非PRD提供SLA），超长/不合法控制字符/词法错误INPUT错误；空串取消search回到受filter/permission及100页大小约束默认列表，不触发全量读取。前端和弹窗使用同一个规范化/语义说明，不自己作匹配。不得拿Page/User向量增强实现所有搜索。
- `account/search.py` 的用户基础search_document按空格组合词保留，Page标题/slug/content匹配保留，UserSortField/PageSortField不新增RANK；只维护原基础更新。商品引用Page名称更新仍调用商品搜索更新。主体creation/update/archival及related name/SKU/email改动在on_commit发有界dirty记录，worker按对象版本幂等更新，失败保留dirty/重试告警；版本新于工作输入时再排队，不能旧任务覆盖新文档。
- 搜索文档保留各Base已索引字段，不把隐私字段广播到新域：Product沿name(A)、SKU/变体/允许属性（原权重）及description(C)；Order沿number/ID/email(A)、customer note及原line/address/payment关联；GiftCard沿code和获准created_by/used_by姓名邮箱；Checkout补token/ID/email及当前行product/variant name/SKU（只在MANAGE_CHECKOUTS/HANDLE_PAYMENTS允许列表scope使用），重复lexeme不重复对象。关联内容按不同字段分段，短语不得跨商品名与邮箱等独立字段拼接误命中。config='simple'沿Base，NFKC/casefold/tokenizer正规化输入及文档，完整ID/token/PSP快捷定位仍先范围校验。rank_key采用`round(SearchRank * 1000000)::bigint`作为本设计量化键（非新业务SLA），ORDER BY rank_key方向+pk方向、cursor及seek全部用同键，不以EPSILON另一口径；RANK有search才允许。仅Checkout/GiftCard缺必要索引时补对应主体GIN/迁移，Product/Order沿既有索引，不新建Page/User或交易专用索引。
- 不指定无来源最终一致性秒数。验收通过drain已提交搜索任务后检查新词/旧词、重复/大小写/短语/prefix、分页和归档，工作队列lag提供运营诊断而非新增专用报表。索引/迁移仅四主体；Page/User专用vector/RANK后台任务不新增。

### BD09 · 有效筛选范围、导出和对象导航
- 覆盖需求：R14、R15、R27、R28。
- 当前查询导出统一 `productsExport/giftCardsExport/vouchersExport/voucherCodesExport`，使用当前列表同类型where/filter/search/channel/sort，不把筛选集合降为当前页。Query有作业创建语义：必须idempotencyKey、禁用共享响应缓存、前端no-cache；用户动作才请求，不挂页面自动查询，重试同key回同ExportFile，不重复外部副作用。沿用现有异步ExportFile/通知/完成事件，不在query resolver生成全文件。
- scope=ALL只在无选择/无普通或锁定过滤才允许；有任一限制用FILTER（过滤非空）；scope=IDS必须非空ID，仍与有效过滤取交集并检查每ID范围，越界/重复/失配拒绝，不静默全店导出。products的channel和warehouse filters通过AND合并；后端不能信任“URL锁定”本身为授权，一直检查真实对象范围。排序影响文件顺序，不改变集合。
- 新增专用导出permissions `MANAGE_PRODUCT_EXPORTS/MANAGE_GIFT_CARD_EXPORTS/MANAGE_VOUCHER_EXPORTS`，并要求对应域管理/读取范围。迁移向原本具备相应域管理、已能导出的permission groups/App授予等价导出权，保留既有授权含义；未拥有域权限者不凭新码扩权，权限界面可今后拆分。兼容 exportProducts/exportGiftCards/exportVoucherCodes 保留实际作业实现、同样授权，不成功空响应，SDL明确弃用替代。
- 分类/warehouse/assignment仍用现有queries稳定分页，后端对象去重和合法父子关系，不为R15新增独立导航API。批量请求对每对象执行权限/状态校验，前端选中集与有效filter快照关联，不依赖隐藏入口授权。
- 验证：列表有效范围与job输入/object集合一致、筛选立即导出、IDS错范围、ALL受限拒绝、查询缓存不跨用户/会话、无导出权/App scope/重复key、历史兼容导出。新增vouchers（含voucher主体）导出复用CSV/XLSX与ExportFile，仅必要字段，不做报表。

### BD10 · 密码策略与外部身份关联
- 覆盖需求：R16、R17、R28、R29。
- ShopSettings存password_authentication_mode，默认ENABLED；Shop公开只读该枚举供未登录login，settingsVersion需MANAGE_SETTINGS。shopSettingsUpdate修改mode必须expectedVersion，锁单例配置、校验CAS、写入递增版本；认证从主库或同步失效缓存立即读取最后生效模式，不能用replica延迟导致旧值生效。
- 一个policy guard包住tokenCreate、passwordChange、setPassword、requestPasswordReset、员工/客户设置密码路径、旧password-derived refresh/verify恢复路径。CUSTOMERS_ONLY对is_staff=true一律拒员工密码能力（兼具客户身份也不降成可拿staff会话），DISABLED拒所有密码派生能力；ENABLED仍执行active/confirmation等Base检查。外部provider流程不被误禁。
- JWT/refresh标记auth_method及policy_generation；旧无标记token按password派生处理，模式变更后校验禁用路径，防refresh延长旧会话；外部token标记独立。不是无差别撤销所有外部会话。request reset不能借错误枚举邮箱，模式拒绝可返回明确policy code，用户存在性不暴露。
- Google refresh场景access_type=offline；其他provider才使用其合规offline_access，参数分provider，不统一改写。首关联以(provider issuer, sub)唯一，在已验证邮箱/现有安全关联条件下原子创建关联、set_unusable_password、提升token generation并拒该用户password reset/set绕过；后续同sub复用，无部分关联；不把未验证邮箱直接合并。日志/错误删token/client secret，沿用最小必要session存储不新增token持久化。
- 覆盖authentication/account/OIDC现有测试，新增三态×客户/员工/App/external、立即策略生效、旧refresh、初次/重复关联、失败回滚、外部继续可用和配置冲突。

### BD11 · EditorJS 保存前结构与安全链接
- 覆盖需求：R18、R26。
- 在 `core/utils/editorjs.py` 把处理拆为严格结构validate和安全sanitize，所有product/page/collection/shipping描述及translation相同入口，写库前全部校验。支持明确的paragraph/header/quote/list/embed及Core已支持image，字段形状在 `interfaces/app-boundaries.schema.json#/$defs/EditorJS`；legacy字符串list与结构化nested list兼容，Dashboard停止`convertEditorJSListBlocks`仅取顶层content的降维转换，正常子项不丢失。仅允许EditorJS顶层time/version/blocks（time/version可省），block id/type/data及空tunes；未配置的tunes或其他字段拒绝，不“清掉然后报成功”。
- 本设计支持嵌套列表深度最多10层（root item为1），固定常量、边界公开；支持正常嵌套而拒绝递归/过深。JSON形状、数组null、block类型、必要data类型先验证。HTML链接解析时解码控制符/实体后固定允许http/https/mailto/tel和合法站内相对URL，拒javascript/data/file、scheme混淆；禁止配置额外scheme。HTML标签/属性用现有清洗基础固定allowlist，target=_blank强制rel含noopener noreferrer；拒危险链接是整次保存失败，不默默删链接充当成功。
- payload错误field为description或translation.description等，message指出blocks索引/链接/深度，新增三个可分支码（结构/UNSAFE_URL/深度），不回显可执行原串。混合合法/非法原子回滚原文；批量API每项按其既有原子错误策略，不谎称整批成功。验证editorjs单测及product/page/translation mutation，嵌套9/10/11、合法协议、实体混淆、未知字段和opener。

### BD12 · App 合同迁移、表单与目录边界
- 覆盖需求：R19、R20、R21、R27。
- Base AppExtension DB只存mount/target/http_target_method，不存任意options；新增JSON settings，读投影mountName/targetName/settings，旧mount/target/options保留明确弃用读取。manifest新扩展输入只接受当前名称，已存旧扩展按确定映射读取；不得声称恢复Base已丢失任意options。已知widget/new_tab方法映射 `{method: GET|POST}`，其他settings为空对象；已有JSON原样保留，不能不明数据强改默认。
- manifest完整当前JSON规则与目录数据在 `interfaces/app-boundaries.schema.json`；identifier唯一、合法permissions<=App权限、mount/target组合、URL/JSON设置先全体校验后安装/更新。appName/manifestUrl GraphQL必填且非空。tokenTargetUrl可选：缺省不建立投递新token任务，不返回token；需要回传时按已有安全安装流程单次投递并加密/脱敏，token不进入manifest/settings/errors。appCreate.authToken仅当前明确创建token场景及MANAGE_APPS可返回，其余返回null。
- 安装保持AppInstallation异步结果（受理≠installed），失败原有效App/扩展不被部分替换，更新事务整体替换/版本校验。新客户端不提交mount/target/options旧字段；新manifest旧字段输入给迁移错误，历史DB读取不要求重装。
- 弹窗postMessage不是GraphQL mutation；前端先验证对应frame和当前上下文，写回仅dirty编辑值，最终仍用已有product/translation mutation及Core输入权限。协议在 `interfaces/app-boundaries.schema.json` 与I19，Core不替App消息直接保存。
- 目录沿用Dashboard现有APP store URL可配置JSON读取边界，改为自托管可配同源/明确HTTPS目录文件，不新增Core目录服务。加载、空、失败只是浏览事实，不写AppInstallation。无安装权限只读。
- 验证manifest验证/installation utils现有测试，新增optional token URL、同identifier、全体扩展回滚、完整settings往返、历史映射及消息integration前端测试。

### BD13 · 订阅驱动解析、异步载荷与独立 delivery
- 覆盖需求：R22、R23、R28、R31。
- 在GraphQL subscription/sync webhook解析入口仅执行订阅selection set（含实际片段），未选择字段不得触发其resolver。现有SyncWebhookControlContext贯穿计算；纯async不预解析shipping/tax相关字段，不复用“构建一切再裁剪”。订单/草稿/履约允许async事件创建最小持久化event/outbox（event id、对象id、对象version、snapshot/创建时事实）并on_commit入队；worker边界构建完整subscription payload。不是对所有同步通知强制异步化。
- payload构建输入必须保有事件时状态，不能排队后仅读取已经变动的live order。订单金额/配送metadata快照和变化字段存event snapshot；敏感字段按delivery订阅App上下文解析，不能多App共用带私有全量payload。事件来源被删时从事件快照构建或失败可诊断，不用空payload冒成功。
- 每(event,webhook)唯一delivery，worker分别处理，A失败不抛出阻断B/C。payloadState WAITING/READY/FAILED；status PENDING/PROCESSING/RETRYING/FAILED/SUCCESS区分等待/执行/重试/终态。幂等生成payload，retry只目标delivery并保留event id，不重新执行业务动作或重发成功接收者。缺payload重试先排payload构建，不继续Base“缺payload直接失败”的限制。
- 保留现行HTTP超时/次数/指数重试/熔断/队列上限，不另立任意SLA。本地以event/delivery id唯一，HTTP Base不提供这些id头，远端仅按既有payload业务key+签名/处理账幂等，不虚称已有event-id header或网络exactly-once；delivery重投仍对应同一本地业务event。variant折扣价比较生效值/价格版本，有实质变化才提交后一次使用已有PRODUCT_VARIANT_UPDATED / ProductVariantUpdated通知，no-op不发，不新增专用折扣价事件。
- EventDeliveryRetry保持已有MANAGE_APPS，进一步验证目标App/业务域scope，payload/lastError脱敏；原失败告警保留，不引入AppProblems。覆盖async transport/sync subscription/event retry及价格更新测试，检查resolver调用计数/无关外部调用、缺payload、A/B/C隔离、snapshot一致、重试受限。

### BD14 · 配送历史快照与基础元数据原子编辑
- 覆盖需求：R24、R25。
- Order新增两个独立JSON字典shipping_method_metadata/private_shipping_method_metadata，默认{}；checkout complete及draft complete的成单事务读取当时合法ShippingMethodData元数据并deep copy，无配送/无资料为空。Fulfillment只读投影所属order快照，源method修改/停用/删除不得影响。与shippingTaxClass/Order.metadata不同字段；不提供编辑snapshot的mutation。
- 迁移只复制确有历史存储的对应配送事实；Base只有税类不能误拷，无法恢复的历史给[]，不拿当前shippingMethod伪造创建时内容。已有订单自身/税类metadata不动；重复迁移幂等。async事件使用同订单快照。
- 新增 `metadataBundle(id)` / `metadataUpdate(input)` / `metadataBulkUpdate(input)` 专门原子基础编辑，支持Checkout、CheckoutLine、Order（含draft）、OrderLine、Fulfillment、ProductVariant；输出revision、public、按权限nullable private。expectedVersion必传；metadata/privateMetadata为upsert、deleteKeys/deletePrivateKeys为删除，omission不变，null列表非法，空数组no-op。duplicate key/同key又改又删/空key/越界长度先拒；锁对象和metadata版本，校验所有public/private动作权限后一次更新两个字典。多对象请求先全体校验并解析父对象，遵守全局父对象→子对象锁序、同级type+pk稳定加锁，一事务成功或全部回滚。旧updateMetadata/deleteMetadata等单请求仍原子、递增同revision；不让旧调用绕锁或stale覆盖新表单。
- Dashboard的一次单对象保存只发metadataUpdate，订单行与variant联合保存发metadataBulkUpdate；不发送多条public/private删改mutation然后把部分成功叫整体成功。基础metadata不影响shipping snapshot；现有订单行与商品变体编辑保留。不新增订单/履约/仓库独立弹窗。字串长度沿用现有模型/metadata校验约束，不收紧历史数据；新增空key校验明确field。
- 权限public按业务对象范围，private按原对象private-metadata要求；HANDLE_TAXES仅在对应tax webhook允许必要私有读取，不能成为全商店private读取权。验证checkout/draft两成单快照、源删除、不恢复历史、事件一致、原子public/private失败、并发CAS、基础行内编辑。

### BD15 · 公开校验、退出能力、真实权限与工作台事实
- 覆盖需求：R26、R27、R28、R29、R30、R31。
- 共用输入验证在外部副作用前：时长非负，DateTime必含offset/Z，非法枚举/required由GraphQLcoercion；运行时空串/显式null/数组元素/组合由payload或顶层INPUT错误。Federation `_entities(representations:[_Any!]!)`并验证每项为含合法typename/key对象；Base无意义nullable路径退出。订单where单值/数组/组合和User.orders按对象scope测试，不把UUID当ID/channel slug。
- 当前退出：移除Payment.partial、DigitalContent*公开类型/queries/mutations/ProductVariant.digitalContent/Shop旧数字配送设置；数字商品isShippingRequired=false、App方案、正常variant/media保持。旧Adyen/NP Atobarai插件不注册，无调用成功回退；历史Payment记录继续读既有金额/事件，旧gateway新动作返回迁移/不支持错误。draft voucher保留弃用输入但返回MIGRATION_REQUIRED，不支持的旧输入不得静默成功，当前voucherCode按规则生效。
- AttributeCreateInput name/type仍必填，slug省略按Base生成；显式null/空name/slug拒绝。AttributeUpdateInput保留省略字段部分更新；显式null/空name/slug拒绝，不新增不可修改的type输入。AppInstall必填新SDL及生成client同步。
- 员工真删除：修改 `account/utils.py` 有历史订单只is_staff=false路径；先沿用MANAGE_STAFF、不得自删/删受限superuser/超管理权限检查，再transaction内删除User。Order.user等on_delete允许SET_NULL，保留user_email、地址、金额/交易/履约；其他引用逐项确认PROTECT并给稳定错误，不能级联删历史订单。相关token/权限关联撤销，customer转换不是删除成功。
- 敏感税务字段在Checkout/Order.privateMetadata/user等实际field resolver与tax subscription上下文授权，scope一贯；列表count/error同样不披露。exports新权限、attribute/apps现有权限统一调用，客户端隐藏不能替代。
- weight用既有Weight.value/unit和转换库；普通同步外链/上传/oEmbed接口保持，失败现有payload，不新增async pending/503/proxy/fallback。draft添加/完成再验证channel active、发布/价格/库存/配送及必要配置；与BD01/BD02服务共享。日期原始DateTime不改为本地日期，客户端locale/timezone处理。
- schema/路由/任务排除清单：无AppProblems、Page/User RANK/高级vector、transaction日期/事件过滤/sortBy、独立variant generator、独立metadata管理、async媒体任务。保留Product/Order既有RANK及普通变体批量、User/Page基础搜索、行内metadata和失败告警。

- 统一并发锁序为 Channel/相关Shop配置 → completion record（若适用）→ Checkout/Order父对象 → Transaction/Payment → GiftCard → Stock（各集合按pk），所有兼容写入口遵守；短claim不得反向等待Channel锁。completion record保存claim_generation并在每次续租/接管递增，旧worker的外部回调和最终提交同时校验generation/revision，lease到期不是允许旧worker继续提交。处理诊断不刷新业务last_change；影响支付额度但charge_status未变的写也更新version/last_change。channel CAS expectedVersion为控制参数，从权限判断的业务keys排除，不能误拒MANAGE_CHECKOUTS专用保存。
- 严格配送通道另需替换Base `plugins/webhook/plugin.py:3619-3646` 与 `webhook/transport/shipping.py:30-44` 将服务失败折叠为空列表的行为，调用无副作用staged计算而非会提前清选择/写价格的helper。
- 配置仓库排序与settings/关系若一个UI“保存”同时提交，新增ChannelUpdateInput.warehouseOrder在同一CAS事务内处理；旧channelReorderWarehouses继续参与settingsVersion递增/对象锁，新Dashboard不先保存settings再独立reorder并宣称整体成功。
- Base giftcard helper需要全链路替换App硬依赖：initialize/process/gateway动作均显式dispatch内建provider，稳定非空provider namespace与App FK分离；不创建虚拟可安装App。新增Transaction来源checkout ID持久化，成单后checkout FK清空仍可按来源查询和重试同key；旧交易没有可靠来源则null，不伪造。客户不能覆盖普通gateway action；内建giftcard的AUTHORIZATION/CHARGE为明确受支持客户例外，仍受当前渠道/对象权限和余额校验。
- 根transaction/node/嵌套transaction共享授权queryset；Transaction metadata按Base支付敏感权限，不随客户owner读取自动开放。query checkoutIds采用当前或持久化source关联；transaction ID解码UUID token而非直接数据库整数PK。
- rank统一量化rank_key同时用于ORDER BY、cursor与seek，替换仅EPSILON近似比较的风险；旧search worker不能读replica后无版本清dirty，使用writer快照+search_revision CAS。
- App.settingsVersion与AppInput.extensions/expectedVersion明确当前编辑入口：appUpdate整组替换extensions，permission<=App且可授予范围检查，省略保留/[]清空、非空更新必传CAS，id仅能属于当前App。identifier并发采用非空唯一约束/锁，先审计历史重复不删有效App。缺tokenTargetUrl时GET/POPUP合法；需要token的POST WIDGET/NEW_TAB必须配置可信tokenTargetUrl及与目标完整origin一致，缺省返回配置错误，不去掉原安全边界。相对URL仍需appUrl。
- delivery成功后只保留最小审计记录和确认时间（SUCCESS至少可在本次查看/刷新读到），payload/attempt按既有可配置清理策略定期移除；不再即时删除整条成功delivery。保留策略不新增任意天数业务SLA。变体折扣价实质变化使用Base已有PRODUCT_VARIANT_UPDATED / Subscription.event下ProductVariantUpdated合同一次触发，非虚称已有专用折扣价事件，也不新增专用事件类型；recipient按其channel查询discountedPrice读取同一价格事实。
- exportFile/exportFiles读取和导出worker必须带owner/domain/actor范围及新导出权，worker执行前再查当前授权（撤销则失败不产文件）。文件查询不能沿用Base单一MANAGE_PRODUCTS而让giftcard/voucher获准身份读不到或越权读别域；下载链接按现有安全存储机制有界，URL失效重新鉴权取得。
- staff删除时Checkout.user的CASCADE需要预处理：有有效资金的未完成checkout先解除用户关联并保留email/资金来源供安全处理，无资金checkout按合法删除图清理；不能级联丢失礼品卡占用或支付事实。
- 基础元数据支持CheckoutLine/ProductVariant既有能力，metadataBulkUpdate对多个对象先全体校验、按全局父子锁序和同级type+pk稳定锁序，同一事务更新/返回；订单行与variant现有联合编辑不得用Promise.all留下半结果。订单确认与metadata编辑拆成清晰独立业务动作，不先自动confirm再假称metadata整体保存成功。

## 4. 接口清单

完整权威契约集中于 `interface-contract.md`，本表仅索引。

| 接口 | 所属设计单元 | 说明 |
| --- | --- | --- |
| I01、I02 | BD01 | 配送重算、选择及最终有效性 |
| I03 | BD02 | 库存来源及渠道关系 |
| I04 | BD03 | 商品渠道诊断 |
| I05、I06 | BD04 | 自动完成状态及配置版本 |
| I07、I08 | BD05 | 礼品卡初始化/支付及取消/退款 |
| I09、I10 | BD06 | 金额摘要/可操作额度及幂等资金动作 |
| I11 | BD07 | 根级交易详情/基础分页 |
| I12 | BD08 | 主体增强/页面用户基础搜索 |
| I13、I14 | BD09 | 当前查询导出、列表/选择器 |
| I15、I16 | BD10 | 密码策略及OIDC |
| I17 | BD11 | 富文本校验 |
| I18、I19、I20 | BD12 | App安装/扩展、frame消息及目录 |
| I21 | BD13 | Webhook订阅/delivery状态/重试 |
| I22、I23 | BD14 | 历史配送快照及原子基础元数据 |
| I24、I25、I26、I27 | BD15 | 校验、退出、授权与日常业务事实 |

## 5. 工程任务与依赖

### BT01 · 冻结目标契约与基础模型迁移
- 覆盖设计单元：BD01—BD15。
- 依赖：无。
- 工作与验证：以交付SDL实现Graphene字段/枚举/错误码；新增版本、来源、时间配置、completion record、giftcard reservation、payment basis/metadata snapshot/settings JSON和必要outbox状态。持久化约束见下方模型登记。新导出权限初始化及旧权限等价迁移。先盘点既有checkout_token重复和历史giftcard可恢复来源，不能自动删除冲突事实；失败给操作性报告。空库与含旧订单/Payment/Transaction/App/库存/metadata样本分别迁移，重复数据回填幂等；不靠查询实时源伪造历史。

### BT02 · 库存来源与配送共享服务
- 覆盖设计单元：BD01、BD02、BD03、BD15。
- 依赖：BT01。
- 工作与验证：更新所有查询/预留/分配/履约/draft入口，用共同候选服务；完成前配送最新校验，显式重算及诊断。现有checkout/warehouse/order/product测试扩展，主库并发锁测试和legacy等价回归。

### BT03 · 资金动作账与礼品卡适配
- 覆盖设计单元：BD05、BD06、BD07。
- 依赖：BT01；资格关联需BT02。
- 工作与验证：动作幂等/占用、拒裁剪/零值，内建礼品卡生命周期、历史映射及summary；根级交易scope/pagination。单卡与多transaction竞争、超时未知结果对账、pending不算成功、净额/历史金额回归。外部provider沙箱集成不能用mock通过冒充真实确认。

### BT04 · 自动完成批次和一次成单
- 覆盖设计单元：BD04、BD01、BD02、BD05、BD06。
- 依赖：BT01、BT02、BT03。
- 工作与验证：扫描/严格delay/cutoff、统一completion record/人工互斥、开关CAS/执行复核、completion outbox；freeze time与worker integration覆盖修复重试、不重复订单/资金/通知、批次隔离，实际执行结果和设置保存分开。

### BT05 · 搜索、导出与导航基础权限
- 覆盖设计单元：BD08、BD09、BD15。
- 依赖：BT01；可与BT02/BT03并行。
- 工作与验证：仅四主体vector/RANK及dirty版本更新，保留page/user基础；导出query/job幂等及全范围筛选、专用权限/旧路径弃用。固定数据游标与过滤集合比对，断言无Page/User专用高级migration/task。

### BT06 · 身份策略与内容输入安全
- 覆盖设计单元：BD10、BD11、BD15。
- 依赖：BT01；可并行。
- 工作与验证：三态policy guard/CAS/token来源、OIDC首次关联和Google参数；strict EditorJS全入口。身份/权限矩阵、旧token旁路、保存失败原文保持、depth10边界。

### BT07 · App当前合同及历史兼容
- 覆盖设计单元：BD12。
- 依赖：BT01、BT06（安全URL规则可共享但manifest URL不允许mailto等）。
- 工作与验证：mountName/targetName/settings、manifest完整校验、optional token URL、保留已知历史method、安装原子与真实job状态。与FD06/FD07按附加JSON协议联调，不新建REST安装服务。

### BT08 · Webhook异步边界、历史快照与原子metadata
- 覆盖设计单元：BD13、BD14。
- 依赖：BT01；成单集成需BT02、BT03、BT04。
- 工作与验证：selection驱动sync、事件时snapshot/后台payload、App独立delivery/retry、成单两路径shipping快照、metadata原子CAS。断言未订阅字段零额外服务调用、等待不是成功、失败接收方隔离、基础metadata不改历史快照。

### BT09 · 退出接口、权限真删除与完整客户端联调
- 覆盖设计单元：BD15及所有单元。
- 依赖：BT02—BT08。
- 工作与验证：移除退出schema/plugins/client操作，staff真删除保留订单、税务field scope；输出运行时schema与target做semantic diff，Dashboard以target本地codegen，验证全部变更操作/错误映射/无非目标暴露；功能测试、typecheck、迁移与并发回归是实施完成条件，本阶段不执行。

## 6. 其他

### 持久化模型、约束与状态登记

以下是拟迁移字段/内部表，不增加公开独立管理API；金额沿Base Decimal精度与币种，每个状态写必须锁定源业务对象并递增其资格revision。

| 落点 | 最小字段与数据库约束 | 生命周期/失败处理 |
| --- | --- | --- |
| Channel / ShopSettings / App | settings_version 非负整型；Channel.stock_source_strategy与自动delay/cutoff；Shop.password_mode/policy_generation；AppExtension.settings JSON及App.settings_version与非空identifier唯一约束 | 事务更新version；control参数不进入业务权限keys；历史重复identifier先审计，禁止自动删有效App；[]扩展替换也必须版本 |
| Checkout及成单资格 | version非负、last_change；Checkout/Order.gift_card_amount_basis及payment_flow；旧数据basis按可靠路径回填 | 所有行/地址/配送/客户/交易/卡事实入口触发revision，不只status改变；diagnostic/claim续租不刷新业务last_change |
| CheckoutCompletionRecord（拟新增） | checkout_token唯一UUID值（不是必需Checkout FK）；nullable order FK采用PROTECT；status、claim_generation、lease_until、eligibility_revision、attempt_count、error_code/field/safe_message、last_attempt_at/next_attempt_at | WAITING→PROCESSING→COMPLETED/BLOCKED/FAILED；FAILED/BLOCKED条件修复后可claim新generation；COMPLETED终态永远返回同order。Channel→record→源对象锁序；过期lease接管后旧generation禁止写入。订单先存在时回填record，重复token必须停报冲突 |
| PaymentActionRecord（拟新增共享动作账） | stable actor scope、source_kind/source_id（成单后保留原checkout token）、provider_namespace、action、idempotency_key、input_hash、requested_amount/currency、transaction或Payment关联、provider_reference、占用金额、状态与安全结果；unique(actor_scope,source_kind,source_id,provider_namespace,action,idempotency_key) | RESERVED→REQUESTED→SUCCEEDED/FAILED；超时保持REQUESTED/UNKNOWN并对账，不释放可能已发生动作的占用。same key先读原记录再状态/额度拒绝；不同key按有效未决占用保护。内建动作与余额/event同事务成功，外部调用在锁外，同稳定provider key重试 |
| GiftCardTransactionReservation（拟新增） | transaction/card关联、authorized/consumed/released Decimal、currency、状态；unique(transaction_id,card_id)，非负且consumed+released<=authorized；source/card动作唯一映射 | 未消费authorized构成active reservation，不永久减卡；部分charge/cancel逐步消费/释放；本地成功charge/refund与卡余额/标准event/动作记录一事务。退款不增加新的授权，重复退款动作去重 |
| Transaction来源与历史映射 | immutable source_checkout_token（不能FK级联清除）；provider_namespace不依赖App外键；历史giftcard事件source_event_id唯一映射到transaction/event（nullable旧来源不得猜） | 成单仍将现有FK移至Order，来源查询/幂等不变；回填只一次，旧basis合成流水不二扣总额/余额，不发业务outbox |
| BusinessEventOutbox / EventDelivery | outbox.source_key+event_type唯一，object_id/version、最小事件时snapshot、retry状态；delivery(event_id,webhook_id)唯一，payload_state、payload_recipe/snapshot引用、safe_error及确认时间 | 本地业务event once；后台按每App授权selection构建，重投同delivery/事件。SUCCESS最小审计保留，可按原配置清理payload/attempt；单订阅失败不影响其他delivery |
| Order配送snapshot / 基础metadata version | Order两独立JSON字典；支持对象各自metadata_version（CheckoutMetadata独立行也归父对象锁）；source snapshot只读与业务metadata分开 | 成单锁内deep-copy；Fulfillment投影；原子bulk先锁全部父对象及版本，公私删改同一事务。不能以metadata键模拟snapshot更新 |
| 四主体搜索/ExportFile作业 | search_revision及dirty版本仅四主体；ExportFile.domain/owner及effective_scope_snapshot/scope_hash/input_hash/idempotency_key，unique(actor_scope,domain,idempotency_key) | writer快照CAS写search并清同版本dirty；导出same key异参返回Export INVALID且不创建第二job，同参复用。worker及下载重查当前权限；不对Page/User或交易高级filter新建索引 |

外部callback写Transaction事实不因checkout已删除而丢失：通过稳定交易/动作账定位当前Order或未完成Checkout；业务qualification version和generation决定是否还能提交成单，已确认外部资金始终保留对账事实。异常若发生在本地commit之后、ACK/任务投递之前，重试从唯一record/outbox恢复，不反向撤销真实成功。

### 发布、迁移与回滚约束

采用expand→受控backfill→应用新路径→清理退出入口。先备份、核对数据数量/金额/余额，迁移在maintenance/受控队列边界执行；giftcard历史回填和completion record建立不得发业务事件。关闭自动完成开关/停止新扫描可以暂停新自动化，但不能抹掉已确认外部资金；队列恢复先对账未决action。回滚到旧代码需确保新giftcard交易未被旧抵扣路径二次扣卡，因此一旦启用新路径不得仅回滚二进制，先关闭新写入并做兼容读取/对账，保存数据库与事件审计。

### 本阶段实际检查与未执行项目

已完整阅读两份业务输入、冻结PRD、四模板，核对Base schema及源码/测试位置。以本地GraphQL 16.11.0执行Base完整SDL语法和类型验证，Base为1408定义；最终target为1428定义、39个消费操作0 validation错误，AJV协议及基础HTTP引用检查通过。完整结果和未运行边界见接口契约§3；未将设计样例当成功能或迁移已通过。本机默认Python graphql库版本不支持Base SDL描述语法，尝试解析失败，已改用Dashboard安装的GraphQL 16，不将该失败误报业务测试失败。

未改仓库、未运行应用、pytest/Jest/Playwright、lint/typecheck/codegen、数据库迁移、Celery/外部支付/Webhook集成或部署；材料只读，部分命令会写仓库，不在当前Stage执行。冻结PRD无替换。技术取值（search256、rank量化10^6、EditorJS深度10、delay默认0）是本设计明示边界，不是业务提供性能承诺。目录真实生产URL、provider账户和部署worker规模由实施配置提供，不阻碍契约落地，也不推断已经可用。

风险重点：历史options不可恢复部分、历史giftcard可审计来源不足、checkout_token旧重复、网络无法提供远端exactly-once、新增导出权限与自托管目录配置。均通过保守空值/审计冲突、持久化幂等/对账和明确错误处理，不以沉默降级或虚构历史解决。
