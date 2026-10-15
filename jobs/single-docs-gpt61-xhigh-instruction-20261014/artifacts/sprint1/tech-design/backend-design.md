# 后端技术设计：Saleor 3.23 结账、资金与商户运营一致性

版本：v1（2026-10-14）
责任：后端技术设计
依据：PRD v1，artifacts/sprint1/prd/prd.md
修订：首次交付；冻结 PRD 与测试不修改。本文件为待实施方案，目标 SDL 不表示当前代码已具备目标能力。

## 1. 方案概述

基于 Core 3.22.0（给定 Base commit c864e66b8e537d30732ddba62d3a4c47e49e4a3e），保留 Django/PostgreSQL、Graphene、Celery、插件管理器及 Relay 连接。不是另建服务，也不获取未来版本 schema。`target-schema.graphql` 是从给定 `saleor/graphql/schema.graphql` 推导的完整目标；接口名称、错误、可空与兼容以 `interface-contract.md` 为权威。

统一四类事实来源：①渠道库存资格服务；②当前结账配送/成单资格服务；③按逻辑资金来源去重的金额投影；④经过对象/字段权限过滤的事件与查询。GraphQL resolver、mutation、后台任务及旧写入适配器必须调用这些服务，不各自复制判断。非资金读查询不产生后台资金动作；查询导出是真正只读分页，不在 Query 中隐式创建导出 Job。

### 基线与差异

| 已读代码/测试 | 当前事实 | 目标处理 |
| --- | --- | --- |
| `checkout/actions.py`、`checkout/tasks.py` | 仅 full authorization 状态跃迁触发单任务；开关默认 false | 批次发现 + 最近变更延迟/cutoff + 锁内再校验，保留通知触发为调度提示 |
| `checkout/complete_checkout.py:1596`、`:1817` | 已有 checkout 锁、已完成查询；Payment 外部处理在事务外 | 复用但补持久 completion 记录/资金命令和 outbox，不能把已有锁视为全过程幂等证明 |
| `warehouse/models.py:43`、`:87` | 已有渠道直连与国家/zone 查询；allocationStrategy 是排序 | 新 eligibility 设置与排序分离，所有入口统一仓库集合 |
| `payment/models.py:186`、`:247` | Transaction/App 与事件幂等约束已有，但 App identifier 可 null | 新命令显式非空 scope，摘要不以“有 Transaction 就忽略 Payment”分支 |
| `payment/transaction_item_calculations.py:91`、`:173` | CHARGE 消耗授权，REFUND 请求/成功消耗 charged；charged 是可用净额，不是所有扣款事件之和 | 保留投影语义，pending 单独展示，禁止重复扣减退款 |
| `graphql/order/types.py:2298` | Transaction totalBalance 含 chargePending 和 grantedRefund；存在 active Payment 走另一分支 | 混合来源统一适配，保留纯旧支付与纯交易的余额语义，不重算历史订单 |
| `graphql/checkout/tests/mutations/test_checkout_delivery_method_update.py` | 现有测试覆盖渠道与自提不适用 | 新增显式重算、失效与并发断言；冻结用例只报告差异 |
| `webhook/transport/asynchronous/tests/test_deferred_payload.py` | 已支持 payload=None 的 deferred delivery，模型不存在时失败 | 扩展订单/草稿/履约适用事件到 worker 边界，增加稳定事件快照与接收方隔离 |
| `account/utils.py:146` | 有历史订单的员工仅取消 is_staff | 改真实删除，保留 SET_NULL 商业历史并拒绝自删 |
| Core `AppExtension` vs Dashboard `extensions/queries.ts` | mount/target/options 与 mountName/targetName/settings 漂移 | 一次规范化与迁移，旧字段只作弃用读取/受约束安装适配 |
| `core/utils/editorjs.py` 与原测试 | 黑名单替换危险 URL、未知 block 宽松 | 结构与 URL 白名单前置拒绝；现有合法 block 保留 |

所有下述模型、方法和迁移若未在 Base 中出现均为拟新增；不声称已经存在。

## 2. 需求覆盖

| 需求 | 设计单元 |
| --- | --- |
| R01、R02 | BD01 |
| R03 | BD02 |
| R04 | BD03 |
| R05 | BD05、BD06、BD07 |
| R06 | BD04、BD05 |
| R07、R08 | BD06、BD07 |
| R09、R10 | BD07 |
| R11 | BD08 |
| R12、R13 | BD09 |
| R14 | BD10 |
| R15 | BD10（去重、稳定对象分页；布局/返回路径由前端负责） |
| R16、R17 | BD11 |
| R18 | BD12 |
| R19、R20、R21 | BD13（R20 接收与 R21 展示主要在 Dashboard，协议由此共同管理） |
| R22、R23 | BD14 |
| R24、R25 | BD15、BD14 |
| R26 | BD16及各写服务 |
| R27、R28 | BD16、BD10、BD11、BD13 |
| R29 | BD04、BD11、BD16（版本/失败原子性；脏字段回填属于前端） |
| R30 | BD17（资格及真实 API 值；重量、locale/timezone 分组属于前端） |
| R31 | BD09、BD16、BD17 |

## 3. 详细设计

### BD01 · 显式配送重算与最后一步重校验
- 覆盖需求：R01、R02、R26。
- 设计说明：在 `graphql/checkout/mutations/` 拟新增 `CheckoutShippingRefresh`，注册到 `graphql/checkout/schema.py`；`checkout/fetch.py`、`checkout/utils.py` 与插件 manager 统一封装 current shipping evaluation。使用地址、行、渠道、折扣/税/总额上下文的同一 revision 计算，调用当前同步 SHIPPING_LIST_METHODS_FOR_CHECKOUT / CHECKOUT_FILTER_SHIPPING_METHODS；不得读旧方法缓存当作本次结果。
- 重算不选择也不清空保存值。成功返回当前可用 shippingMethods/collectionPoints、已保存 deliveryMethod 和 selectedMethodValid；不可用旧选择仍可在 deliveryMethod 解释，但不进可选列表。完整数字类结账返回空配送列表且 selectedMethodValid=true（无配送选择所需），仍校验商品/渠道。地址缺失/服务失败返回对应 CheckoutError，不能写半成品选择；跨 revision 结果 CONFLICT，可重算。
- 更新选择和成单复用同一评估器。旧 ShippingMethod Relay ID、合法外部 APP_ID_PREFIX ID 及 Warehouse ID 走各自受限解析；错类型 INVALID，不存在 NOT_FOUND，已过期 DELIVERY_METHOD_EXPIRED，当前条件不适用 DELIVERY_METHOD_NOT_APPLICABLE。所有归属与权限检查先于敏感选项输出。
- 网络计算不能长期占库存锁；先计算 revision-bound 结果，提交时锁 checkout、相关 channel 设置 revision 和配送依赖版本，复核当前 revision；任何地址/行/关联改变使结果失效。在订单写入/资金命令之前必须通过 current eligibility，不允许失效配送留下订单、预留或扣款。失败不改变原选择，已有选择本身失效时也不能据此成单。
- 验证：I01/I02 对照 AC-01-*、AC-02-*；外部服务超时、删除选择、跨渠道 ID、自提、同一 checkout 并发编辑、失效时保持旧有效值；复用已读 delivery 更新 pytest fixture。

### BD02 · 渠道库存资格服务
- 覆盖需求：R03、R26、R28。
- 设计说明：`channel/models.py` 新增 availability_strategy（LEGACY 默认）；GraphQL StockSettings 分开输出 availabilityStrategy 和 allocationStrategy。`warehouse/availability.py` 拟新增 `eligible_warehouses(channel, country, collection_point)`，`product/utils/availability.py`、checkout stock/reservation、订单分配、draft 完成和 fulfillment 统一调用。
- LEGACY 保留当前国家/zone/渠道/自提语义；CHANNEL_WAREHOUSES 只取直接 channel.warehouses（旧 country 参数仍接受但不改变集合），自提目标必须属于该集合且可自提。独立配送资格仍按 BD01/BD03 校验，不因为库存存在就宣称可送达。preorder、不跟踪库存等既有特例沿用，只改变资格集合，分配排序继续由 allocationStrategy 决定。
- 移动资金与成单遵守一个全局锁层级：必要的 completion 幂等记录→目标 checkout/order（同类主键升序）→channel/settings→TransactionItem/Payment（固定表序与主键序）→giftcard→stock→reservation/allocation/ledger/command 等附属行。纯库存入口无需已有资金 source 时跳过该层，不得持 stock 后反取 channel/目标锁；仓库关系管理只锁 channel 后更新关系，不反取业务目标。使用 `available = stock.quantity - allocations - 有效其他 checkout reservations`；本 checkout reservation 转 allocation 不重复扣除。关系变更也获取相同 channel 锁并提升 revision，所有行先检查再原子写，避免资格读取后仓库被移出或部分预留。
- 新字段迁移旧渠道全部 LEGACY，不根据是否有仓库自动切换。切换不删除旧 allocations；新预留按新规则，原 reservation 需重新验证，不对已完成订单重分配。fulfillment 使用已有 allocation 的合法剩余量，新增分配才按当前策略，不改历史履约。
- 验证：相同 SKU/数量在 product、checkout、draft、order、fulfillment 对照；country 变化新模式结果不变；关系变更、库存耗尽、两个 checkout 抢最后一件、取消释放与全量回滚。

### BD03 · 按渠道可售诊断
- 覆盖需求：R04、R28、R29。
- 设计说明：`graphql/product/` 拟新增 diagnostics resolver/类型，调用 BD02 库存与发布规则，返回独立分页连接，不改变原 `Product.channelListings` 列表合同。channel 名/币种不区分大小写 search、channelIds 与权限取交集，按 channel.name + pk 稳定排序。
- 一个检查一个确定 code/severity（PASS/BLOCKING/WARNING/NOT_APPLICABLE），检查 channel active、publishedAt、availableForPurchaseAt、存在可售 variant/price、eligible warehouses、stock 与 shipping zone；数字商品只将 shipping 检查置 NOT_APPLICABLE。真实阻断只计一次；未发布导致不可买时核心条件为阻断，依赖已正常的 warehouse/zone 不报额外错。用户对象/渠道无权先拒绝，不在 message 暴露仓库名或余量。
- 检查只读，不逐渠道触发无订阅税务/配送远程服务；snapshot `evaluatedAt` 表示服务端已保存事实。编辑中的未保存改变不是服务端诊断，前端须标记陈旧。页面查询失败不降级为空 checks。
- 验证：商品 ChannelsAvailabilityCard 现有 fixture 可扩展；数字商品缺库存仍阻断、合法依赖不重复计数、分页过滤、权限与编辑/查询延迟。

### BD04 · 自动完成配置与乐观冲突
- 覆盖需求：R06、R29。
- 设计说明：`channel/models.py` 新增 `automatic_completion_delay` 分钟整数（0..10080）与 nullable aware datetime cutoff，`settings_revision` 单调版本。技术选择默认延迟 0，以保持旧明确开启渠道“无额外等待”；旧 false 不变、true 不变，cutoff null，不推定业务另有新默认。
- 开关、delay、cutoff 分别可配置；关闭时保留时间设置以便再启用。delay 的显式 null 非法，cutoff null 清下界，省略保留；未来 cutoff 合法，表示仅将来创建 checkout 入选。时区统一 UTC 入库。`ChannelUpdateInput.expectedSettingsRevision` 新客户端必发；有权旧客户端省略仍在锁内原子更新但不享受乐观冲突保护，需公开提示。新客户端版本不匹配 CONFLICT，不更新任一字段。
- 资格时间为 `now - checkout.updatedAt > delay * 60秒`，等值不入选；`created_at >= cutoff`，等值入选。保存刷新配置及 revision，不生成订单。数据库 CHECK 保护非负/上限；整个 settings 更新事务全有或全无。读/写路由避免保存后从滞后副本显示旧事实。
- 验证：0、10080、-1、10081，D 边界/C 边界，omit/null，旧 false/true，冲突并发与关闭再启用。参数值是方案选择，不修改 PRD Q02。

### BD05 · 批次自动成单、持久状态与幂等
- 覆盖需求：R05、R06、R26。
- 设计说明：`checkout/tasks.py` 拟新增 bounded scan；保持原 single task 为共享执行器入口。配置扫描周期与批大小由部署配置，沿用当前队列/重试上限，不假称 PRD 指定数值。按 channel + (updatedAt, pk) keyset 扫描，支付跃迁仅 on_commit 提示入队，不能成为唯一发现途径。修复地址/库存/配送后已支付 checkout 会再次被扫描，不能因前一次 BLOCKED 永久跳过。
- 新 `CheckoutCompletion`：checkout_token UUID unique（非 FK，checkout 删除后仍可定位）、channel FK、order FK PROTECT nullable、status、last/next attempt、error field/code（无敏感 message）、revision、lease_until。手动 checkoutComplete 与自动任务统一获取该持久记录和 checkout 锁，固定 lock 顺序，完成记录唯一是商业幂等屏障；现有 `Order.get_by_checkout_token` 用于历史结果查找，不能依赖 first() 掩盖历史多订单冲突。
- 状态：DISABLED / WAITING（时间或未足额）→ PROCESSING → COMPLETED；资格失败 BLOCKED；可恢复网络/数据库失败 RETRYING。lease 超时可恢复但先对账外部资金命令。COMPLETED 不再改金额，不再产生逻辑完成事件。I06 只向合法 checkout 持有人/管理者返回状态，checkout 被删除仍返回已关联 order，明确 actual result。
- 锁内再确认开关、时间、足额、channel active、客户或 email、账单地址、配送地址/选择（需要配送时）、商品/变体可售、库存、总额>0。allowUnpaidOrders、零价手动能力不豁免自动资格。凭 pending 或 actionRequired 不能入选。
- **支付支持矩阵（技术合同）**：Transaction 受支持成功 FULL charge 或可捕获 FULL authorization（净 charge+剩余授权覆盖同一 total，不重复额度），App 的当前 actions/渠道配置合法；内置 gift card 成功 charge/auth 同样支持。兼容 Payment：active 且成功捕获足额、to_confirm=false、无 action_required/pending，可直接转订单，不再次 process_payment；完整 auth 仅在 gateway 提供并通过幂等 capture、状态查询/reconcile 适配时支持后台捕获。Stripe/Authorize.Net 是现有候选落点，须完成合同测试后启用 capability，不能凭插件名无条件支持；dummy 仅测试。部分支付、人工/离线 pending、需客户 challenge、不支持 reconcile 的 auth、退出 Adyen/NP Atobarai 均 BLOCKED/UNSUPPORTED_PAYMENT_METHOD。多 Payment/Transaction 合并按 BD07 source 去重；未适配 mixed gateway 自动完成明确拒绝，不静默选择一笔或重复扣款。
- 外部副作用三步：①资格和资金命令/库存短期 reservation 事务提交；②事务外向 PSP 发送稳定 provider key，收到/查询结果；③锁内重检订单资格与 reservation、转 allocation、挂接 Payment/Transaction、冻结金额、删除 checkout、标记 COMPLETED，并在同事务写唯一 outbox。资格变化而 PSP 已成功不创建半订单，持久记录进入待修复/补偿流程（可识别 payment state），不能以 DB rollback 声称 PSP 未扣款；按同 command reconcile 或补偿 refund，不换 key 重扣。授权方式无需新 capture 的 transaction 成单沿用可授权订单合同，但不能把 auth 展示为 charge。
- 验证：两个 worker+手动同时完成、崩溃在 PSP成功/DB提交/发布事件之间、重复消息、条件修复再扫、completed checkout 删除后查询、库存/配送/设置队列后改变。只有一个 order/result/outbox logical event；delivery 传输重发不构成逻辑重复。

### BD06 · 礼品卡账本与 Transaction 生命周期
- 覆盖需求：R07、R08、R05、R09。
- 设计说明：在 `giftcard/` 拟新增 ledger service 与 `GiftCardTransactionLink`（transaction OneToOne、giftcard FK PROTECT、currency、初始化 owner/目标标识）、`GiftCardLedgerEntry`（command/event 唯一关联、book_delta、hold_delta、sequence）。TransactionItem provider scope 使用非空固定 `saleor.giftcard`，不能依赖 null app_identifier 的唯一约束。checkout→order 转换保持 transaction 与 ledger 关联，不创建第二笔交易。
- I07 显式 giftCardTransactionInitialize，必填 code/amount/action/key；初始化 Transaction 与授权/扣款一个原子结果。遵守 BD02 层级锁目标、channel、transaction（已有时）再锁 giftcard pk 升序，不能与资金动作反向锁卡→交易；新 transaction 在已锁目标范围内创建。校验存在、启用、expiry_date（当天合法）、currency、正金额且不超过当前目标可覆盖额/卡可用额。相同 scope/key + 规范化目标/卡/action/amount 返回原结果，异输入冲突；若已转订单，原 checkout 请求可通过 command 记录重放，不需要再次消费 card。
- 书面例：book=100，authorize30 → book100/hold30/available70；capture30 → book70/hold0/available70；cancel auth30 仅 hold-30/book不变；refund charge30 → book+30。部分 capture/cancel 均按剩余 hold，订单 refund ≤该 transaction 当前可退额，不能取整卡余额作为退款界限。授权释放、过期结账清理/取消在同一服务上写 CANCEL_SUCCESS 与卡事件；卡过期/停用后允许取消释放与合法已扣款退款，但禁止新授权/扣款。
- GiftCardPaymentMethodDetails 只返回 cardId/last4/name，不显示 code；GiftCard 对象/余额字段使用原 giftcard 权限或匹配持卡结账范围，猜 code 限流与统一脱敏错误。使用现有 transactionRequestAction 的 CHARGE/CANCEL/REFUND 分派到内置 ledger，不请求外部 App webhook、不“失败转普通支付”。客户 checkout 只可取消自身授权（通过合法 checkout capability），不能获得订单退款管理权限。
- 新订单 gift card 是资金不是 discount，旧 checkoutAddPromoCode 礼品卡路径适配到同 ledger 且每张卡/目标查重复使用；remove/cancel 释放同笔 hold。历史 completed order 的 USED_IN_ORDER 与折扣保留，不迁移重扣卡；可追溯但不可信的旧事件不猜测授权/净额，不补造资金。ledger opening book 来自 current_balance，不重复录入历史扣款；可恢复在途 checkout 按订单/command 映射建 hold，遇冲突报告并阻断，不能 reset 余额。
- 验证：同卡两个 checkout 授权总额≤余额；authorize/capture/cancel/refund边界、事件列表空态、初始化重复/冲突、card余额与 transaction event 一致、旧历史金额不变。

### BD07 · 金额投影与安全资金命令
- 覆盖需求：R09、R10、R07、R08、R26、R28。
- 设计说明：`payment/transaction_item_calculations.py`、`payment/utils.py`、`order/utils.py`、`graphql/order/types.py` 共享拟新增 order payment projection。普通 transaction 的 PSP reference + scope 映射为唯一 logical source；Payment 与其映射 Transaction 若代表同笔资金只取一个，非映射的真实多笔均计入。不能靠相同金额或有 transactions 就忽略旧 payments。迁移 `PaymentSourceLink` 明确映射可信关系；模糊映射进入核对清单，不静默 merge。
- `netCharged` 采用 Transaction `charged_value`（已消耗 successful/pending refunds）+兼容 Payment captured_amount 净额的适配；`successfulCharged` 为成功 capture 净额（含已退扣减，未退 pending 仍作为现金事实），通过事件/source adapter 生成，不重复加扣款事件；授权是剩余可捕获而非初始授权。refundPending 不再次从 Transaction netCharged 扣减。giftCardCharged 是 netCharged 内的可解释子集，不在摘要再次相加；历史 giftcard 折扣单列 legacyGiftCardDiscount 已含在冻结 payable，不能加回历史 order.total。
- `totalBalance` 统一为既有服务投影：纯 Payment 保留 total_charged-total.gross；纯 Transaction 保留 Σ(charged_value+charge_pending_value)−(total.gross−grantedRefund)。mixed 时分别适配，grantedRefund 只归属一次且不能既扣 payable 又重复增加 charged。pending refund 所消耗的 Transaction charged 保留现有行为，Payment pending 用显式 source adapter，totalBalance 的业务 credit 不是“现金扣款成功”。`remainingDue=max(-totalBalance,0)`；正 balance 显示超付/credit，不显示负待付。BD05 足额资格另用成功资金/合法 auth，而非含 pending 的余额。
- 用 `PaymentCommand`（principal_scope、key 非空、normalized input hash、object/action、amount、currency、status、provider_key、result ref、reconcile info；unique(scope,key)）承接 I08。按 BD02 全局层级锁目标→channel→source→giftcard→stock 及附属行，预占可捕获/可退额度，其他 command 看当前剩余；同请求重放结果，冲突 CONFLICT，未终结重放 pending。错误消息不含受限金额。外部网络在锁外，on_commit 或 outbox 发送，PSP failure 释放本命令占用，timeout 保持 pending 并 reconcile，不能直接当失败重发另一扣款。
- capture ≤ availableCaptureAmount（已扣除 pending），refund ≤ availableRefundAmount（charged 可用净额，旧 Payment 需减 pending occupancy），等边界合法；动作金额须>0（PositiveDecimal 标量允许0但动作层拒绝），默认未填 amount 使用当时剩余。orderMarkAsPaid 必须无任何 Payment/Transaction/资金命令、有效状态/账单地址、total>0，锁内复查，按 channel mark-paid strategy 形成一次结果。统一 MANAGE_ORDERS + HANDLE_PAYMENTS 及 channel/object scope；仅 HANDLE_PAYMENTS App 不能借 order action 获取订单权限。客户不得管理资金，BD06 自身授权取消例外。
- 验证：PRD 100−(30 gift+50普通)=20；授权100/capture40剩余60不算140；mixed去重、grant/pending/refund/chargeback、两并发refund争同余额、PSP未知与double click key、无权限不能读上限。历史摘要已有优先级表达式差异仅在前端修正计划中报告。

### BD08 · 根级交易基础查询
- 覆盖需求：R11、R26、R28、R31。
- 设计说明：`graphql/payment/schema.py` 新增 transactions connection 和独立 TransactionQueryFilterInput，不覆盖已有用于 Order 的 TransactionFilterInput。ids/orders/checkouts/pspReference/appIdentifier 逐字段 AND、同数组 OR，空数组表示空集合；不新增交易 date/event 过滤、sortBy、查询专用索引。采用原主键稳定排序/游标、limit100，计数同可见 queryset。
- 单 transaction 的 id/token 使用 exactly-one（现状 token 优先忽略 id 需修正）；管理员须 HANDLE_PAYMENTS 和对应业务域/渠道权限，App 限自己 provider identifier 与被授权对象；客户仅本人相关订单/合法 checkout，不因 token 获得任意 transaction。列表通过 subject scope 先筛可见对象再筛字段；无业务权限 FORBIDDEN，不返回成功空列表。合法不存在/已无下一页与无效 cursor/input 分开。
- 验证：单ID、数组、组合、PSP引用、重新安装App identifier、gift card、跨对象字段保护、客户/员工/App矩阵。沿用查询 pytest fixture，增加 root connection 测试。

### BD09 · 主体增强搜索与基础 Page/User 边界
- 覆盖需求：R12、R13、R31。
- 设计说明：复用 `product/search.py`、`order/search.py`、`giftcard/search.py` vector/dirty 更新，checkout 拟新增主体 vector/dirty service，采集 token、邮件、姓名、line SKU/名称和支付引用等允许主体标识。共用规范化 NFKC、trim、大小写折叠、重复词去重和 safe query builder；裸词采用前缀/AND，双引号短语按 PostgreSQL phrase，组合词遵守 AND/显式 OR，所有参数绑定，不能拼任意 tsquery SQL。
- GiftCardFilterInput.search 与现有 root search 同语义；同时不同值 INVALID，不能一边列表 root、一边export filter。Checkout/GiftCard 新增 RANK，仅搜索非空可选；product/order保留既有RANK。相关度+主键 tie-break，count与连接同条件，cursor绑定规范化query/filter/sort/对象范围，错上下文 INVALID_CURSOR。动态数据变更游标依当前一致视图，可能需重新开始；不承诺跨多次请求数据库快照，但静态数据不得重复漏项。
- Page 保留 `graphql/page/filters.py:61` title/slug基础 trigram+content icontains；User 保留 `account/search.py:124` search_document 按空格词 AND。不新增 Page/User vector/RANK/prefix/专用index/job/migration。页面关联名称变更继续标 dirty 产品；用户 basic document 维护保留而非删掉已有任务。
- 技术输入限制 search≤256字符、≤32词，空输入是有界普通分页不是无界全量；非法/超长 BAD_USER_INPUT，数据库异常 INTERNAL_ERROR，均不成功空表。subject dirty在原写事务置位、批次 bounded update，成功才清 dirty；失败保留重试。当前 20 seconds 调度默认不是 Q01 业务SLA；发布需确定最终窗口，监控 dirty age 与失败恢复，未确定不得报已满足时延。
- 验证：主体关键词/前缀/短语/rank、重复词大小写、关联名称/邮箱变化、旧值不永久唯一、稳定cursor、Page/User无增强、权限和异常。

### BD10 · 锁定范围、查询导出与批量一致
- 覆盖需求：R14、R15、R27、R28。
- 设计说明：列表 Query 新增 lockedFilter，where 已支持域另有 lockedWhere。权限 queryset ∩ locked ∩ editable ∩ channel/search；不能合并 dict 覆盖相同键。legacy filter与where同时出现也取AND，并有统一构建器；URL锁仅业务上下文，真正授权还是服务端，不依赖客户端锁当安全边界。
- Query.productsExport/giftCardsExport/voucherCodesExport 真正只读 Relay 数据流。scope ALL/FILTER/IDS 是初始集合，所有已提供 filter/where/locked/search/channel/ids 都继续相交，不得 ALL 忽略页面条件。products/giftCards query 输入接受当前 sortBy，查询构建器与列表复用；voucherId/ids交集。JSON data的完整形状及Base ExportInfoInput逐枚举投影见 `interfaces/query-export-row-data.md`：Product以一product/row输出（variants嵌套，前端明确flatten），Gift固定脱敏displayCode/余额/状态、dateISO；新Gift查询不输出全code，旧确需完整code仅现行有权legacy流程。未选择字段省略、不存在字段按合同null/[]，十进制Money/weight输出字符串附currency/unit。ExportInfoInput只投影指定许可列，不能任意数据库列。大数据按limit100逐页读取，前端显式格式化下载CSV/XLSX；CSV formula转义，不能在 Query写job。新导出不承诺跨数据修改的永久快照。
- 旧 export mutations保留且标deprecated，继续同权限异步Job/errors，不空成功；旧input缺where/lock/search时不得声称完整表达新筛选，Dashboard降级只能先枚举有效交集后以IDS传入，worker重验权限及当前可用集合并明确报告资格变化，不允许IDS空回退ALL。旧客户端原单filter/ids行为保留。exportFile/exportFiles校验job owner/domain，不能仅MANAGE_PRODUCTS让gift/voucher导出泄露。商品 MANAGE_PRODUCTS、gift MANAGE_GIFT_CARD、voucher MANAGE_DISCOUNTS（Base无独立EXPORT权限，不凭空要求不存在枚举）；渠道/仓库/字段权限继续约束。
- productBulkDelete/giftCardBulkDelete/orderBulkCancel新增 locked 与当前 editable 参数：三者 filter/search，product/order 另有 where/channel；它们与列表共享全部有效集合构建器，不能只传 lock 而丢当前普通条件。显式 ids 必须重新与该交集核对，越界/资格变化按既有逐项错误合同拒绝，不能悄悄删除或取消旧选择。当前筛选全部结果由有界列表逐页收集 ids 后分批调用（不是跨批全有或全无快照），每批携同一 scope；错误/权限变化明确报告并停止未提交批次。其他保留批量动作沿用其参数及共同域资格/权限 guard；缺少表达完整锁/普通条件的旧入口只能提交重新验证的当前交集 ids，不允许悄悄切换成全量接口。
- 分类/仓库选择器沿用查询，按ID去重与权限/分页，不改对象层级数据；未知ID与cursor明错，不用空表掩盖权限。
- 验证：同键锁与普通筛选冲突只得交集；清普通条件保留锁；导出集合=当前列表条件全集，批量=选择集∩同范围；emptyIDS不全量、非权限字段、CSV公式、切filter后selection清理。

### BD11 · 统一密码策略和外部身份
- 覆盖需求：R16、R17、R28、R29。
- 设计说明：`site/models.py` 新password_authentication_mode默认ENABLED+settings_revision；`graphql/shop/`读生效policy/乐观更新。`graphql/account/`全部密码路径、JWTmiddleware/corejwt统一 guard，不只隐藏tokenCreate。CUSTOMERS_ONLY 对is_staff一律拒绝密码员工会话（即使同时有客户订单），DISABLED拒绝login/reset/set/change及accountRegister密码路径，仍允许合规非密码管理/外部流程。
- JWT新增auth_source（password/external）和policy版本。策略改变立即校验当前policy并拒绝不被支持的password token、refresh/verify/access；旧token无来源按password处理，不能猜为external绕过。策略缓存按revision短路失效，跨worker在请求时取得权威版本，不让旧cache继续放行。settings只有MANAGE_SETTINGS；读mode公开便于登录渲染，revision仅对设置管理可见。无入口给空态而非放宽policy。
- `plugins/openid_connect/plugin.py`Google issuer分支enable_refresh_token=true使用access_type=offline，不加offline_access；其他provider使用自身scope合同。保留state签名、nonce/issuer/audience/expiry/redirect URI与code校验；需要时使用PKCE，不打印code/token/provider payload。
- 新ExternalIdentity unique(issuer,sub)→user，首次绑定同事务锁本地用户、set_unusable_password并提升credential epoch使旧local password tokens/reset tokens无效。仅可由当前已认证用户确认绑定，或来自可信配置issuer且email_verified=true的受控匹配；不能仅凭任意同邮箱字符串接管员工。按稳定issuer/sub回查，后续登录不重复清密码或新建身份；policy/admin group映射遵守最小权限。敏感refresh token服务端安全存储，不暴露日志；前端不增加持久化存储。
- 验证：三模式×客户/员工/App与token/reset/set/change/旧token矩阵；两个worker立即生效；Google参数、非Googlescope、首次/重复关联、未验证邮箱、state错误、token脱敏。

### BD12 · 前置 EditorJS 安全验证
- 覆盖需求：R18、R26。
- 设计说明：替换 `core/utils/editorjs.py` 的黑名单/未知block放行逻辑；共同合同见 I15 / `interfaces/editorjs-content.md`。所有产品/页面/属性/翻译等输入先校验结构、已知字段、1MiB/1000blocks/深度8等限制，再HTML parser白名单及http/https/mailto/tel规则，_blank强制noopener noreferrer。未知字段和非法scheme拒绝，不用#invalid替换然后保存成功。
- 模型写入前产生全量规范化副本，整mutaton事务不部分保存；错误定位description.blocks等公开路径，不能回显攻击内容。历史超集只读取不批量改写，合法旧list/image/embed保留；目标断言与Base替换URL断言差异必须记录，不改冻结用例。
- 验证：已读 `core/utils/tests/test_editorjs.py` 合法fixture、深度L/L+1、结构/额外字段/encoded scheme、safe rel、翻译与扩展同guard。

### BD13 · App 规范化、迁移及目录/表单协议
- 覆盖需求：R19、R20、R21、R27、R28。
- 设计说明：`app/models.py` 新mount_name/target_name/settings JSON，`app/manifest_validations.py`、`installation_utils.py`、GraphQL types与Dashboard zod统一规范化。完整规范化manifest见 `interfaces/app-manifest.schema.json`；旧mount/target/options只由兼容适配器映射，双组冲突拒绝，合法旧值不要求重装。AppExtension/Manifest输出旧字段标弃用，新增String名遵守Base支持mount/target集而非任意未注册字符串。
- 旧target默认POPUP；settings={}；原http_target_method按widgetTarget/newTabTarget.method保存（GET/POST），不得丢原设置。嵌套 settings已知字段/互斥/target匹配校验，unknown JSON拒绝。WIDGET仅当前7个*_WIDGETS挂载。APP_PAGE相对路径必须有appUrl；跨域/非法scheme拒绝，外部https与显式开发localhost白名单受HTTPClient SSRF规则，无重定向到内网，不能把richtext协议白名单套来放开App URL。
- tokenTargetUrl可缺省：不创建长期安装token/不调用投递；确需App token的POST/widget配置必须提供对应合法token能力，否则明确REQUIRED，不能默默换普通token。I16 appCreate.issueToken默认false，authToken缺省null；安装token只投递配置目标且不返回页面，扩展accessToken是按当前员工∩App∩extension权限的短期token，只在受验证frame握手使用。
- App.identifier 全部未删除记录加条件唯一（非空），含暂时停用的已安装 App；更新排除自身。Base `appUpdate` 仅更新基础资料，本轮在该 mutation 新增可选 `manifestUrl: String`：省略沿原基础更新且保留扩展，显式 null/空字符串 INVALID；提供合法 URL 才抓取/完整校验新 manifest，成功后锁原 App 原子替换当前扩展/settings/webhooks，无需重装，不新增另一编号。identifier 与原 App 需相同，若显式变更 identifier 必须与新 manifest 一致、检查引用迁移且不得孤立既有交易。manifest 拉取在写事务外；到提交时重查 App 权限/identity/当前配置，失败保留旧值。不轮换或返回安装 token，也不因更新覆盖既有 token；确需修改 tokenTargetUrl 的交接以单独现有受权 token 管理流程完成，不把投递失败当更新成功。并发安装锁 identifier/唯一约束报 UNIQUE。历史重复先审计停止约束迁移、人工指定保留 App 并保留 transaction.app_identifier 引用，不随机删除。fetch/validate 阶段无 App 写入；AppInstallInput name/URL nonnull/nonempty；读需 owner/manager 及字段权限，安装更新 MANAGE_APPS 和目标 scope。manifest webhook 保留 Base `isActive`（默认 true）、`customHeaders`，继续现行订阅/自定义头验证，不能因 strict schema 丢掉合法旧配置。
- I17由Dashboard handler提供，Core仍是最后保存安全边界，扩展不能假称已保存；I18目录由部署方托管同源静态 `/extensions/catalog.json` 或 EXTENSIONS_CATALOG_URL，不新建marketplace后端。旧APPS_MARKETPLACE_API_URL仅显式配置的兼容来源，不使用模板旧网址做默认回退；数据shape用完整OpenAPI，浏览不发送Saleor token，权限决定安装/配置，不是目录数据决定权限。
- 验证：空/旧库规范化、全settings保留、duplicate identifier/invalid permission/target/JSON、可选信息缺省、token曝光、更新失败原数据、同源两个frame、可用静态目录/404/合法空/只读。

### BD14 · 按订阅解析、deferred 事件与独立 delivery
- 覆盖需求：R22、R23、R24、R28。
- 设计说明：`graphql/webhook/subscription_types.py`、`plugins/webhook/plugin.py`将 SyncWebhookControlContext 贯穿字段resolver，只有订阅selection（含fragment/alias）需要时调用税务/配送manager。每事件/订阅共享loader/cache，沿用超时、调用次数、retry/circuit breaker上限，不通过重复读取绕过。纯异步事件allow_sync_webhooks=false，不为了payload额外发送同步通知。
- 复用 deferred transport；订单/草稿/履约适用事件事务内只写 `DomainEventOutbox`（logical_key唯一、event_type、aggregate_id/version、issued_at、actor ref、immutable domain事实版本/快照引用）与受限recipient计划，on_commit给worker事件ID。worker构造完整GraphQL订阅/legacy payload，业务请求不等待序列化。快照必须能还原当时订单/履约/配送元数据；不能只存可被修改/删除的pk然后worker读最新状态。事务保存必要业务列/版本引用不做完整GraphQL解析；无法版本化的删除事件保存最低必要删除快照，敏感字段只在接收App权限过滤后序列化。
- 事件去重键如(aggregate_id,version,event_type)，价格差实际变动才增加variant折扣通知版本；no-op不再发。独立 delivery unique(event_id,webhook_id)，payload未生成PENDING、失败FAILED、排队/执行合法重试RETRYING、2xx送达SUCCESS；2xx仅表示接收方确认而非其所有下游完成。recipient失败不回滚已提交业务，不重送其他SUCCESS，payload生成失败也只影响该delivery，error脱敏。
- 传输保留现有Saleor headers、签名与订阅数据形状，不改变消费者已选字段；新增稳定Saleor-Event-Id（outbox事件UUID）供去重，相同逻辑事件所有retry保持ID与已生成payload。payload首次生成按事件时/当前权限交集；权限收窄后旧payload不能泄露，安全重新过滤/阻断投递并记录原因，不能提升可见范围。手动单delivery重试限定App owner/MANAGE_APPS或对应业务域权限且符合对象/渠道及订阅Appscope；不允许借业务权改webhook配置/secret。短事务锁delivery，已排队请求重放原delivery，不生成新event。
- 验证：selection不含tax/shipping时manager零调用，含字段单次受限；业务事务不跑完整asyncpayload；object晚改/删保留event事实；一失败一成功不互相重发；崩溃/outbox重复发布；无变化无通知；existing AppAlerts保留，无AppProblems。

### BD15 · 配送元数据历史快照与基础读写
- 覆盖需求：R24、R25、R28。
- 设计说明：`order/models.py`新 shipping_method_metadata/private_metadata JSON 与 snapshot_status；checkout和draft完成两路径在订单创建事务从已验证所选method（外部App合法metadata同样）deep-copy。不是现有shipping_tax_class_metadata，不能混淆。新order CAPTURED，无源metadata也[]；fulfillment从所属order snapshot读取，部分履约不重新查询shipping对象。源修改/停用/删除不回写。
- 历史迁移优先保留旧order已保存同语义metadata，并标LEGACY_PRESERVED；无法证明创建时快照则[]+UNAVAILABLE，不能从当前shipping源“回填成历史真相”。不把其他order.private_metadata整体搬入。public/private读取分别权限；税App的HANDLE_TAXES仅限当前税合同字段与被授权event对象，不是通用任意private数据权限。
- metadata update/delete沿用既有通用mutation，checkout/draft/order/fulfillment及orderline行内能力保留；key非空、大小/重复键/非法项统一验证、整体写事务。snapshot字段是历史事实只读，不允许普通metadata写接口改创建事实；业务对象普通metadata仍可编辑。相关order/fulfillment事件从同一快照读，供scope同样过滤。不新增订单/履约/仓库独立metadata路由或接口。
- 验证：checkout/draft两成单、源后改/删、private字段权限/事件一致、迁移重跑、未知历史[]与status、非法键值全回滚。

### BD16 · 类型/权限、退出接口和迁移基线
- 覆盖需求：R26、R27、R28、R29、R31。
- 设计说明：`graphql/core/scalars.py` Minute/Hour/Day统一非负有限32bit整数；Decimal/PositiveDecimal保持有限/货币quantize，UUID严格拒绝不合法类型，不把解析None变成无结果。连接first/last 1..100互斥，null分页显式拒绝，错误cursor带稳定extensions.code；_entities representations=[_Any!]!，逐项对象/__typename/键字段验证，输出仍按Base允许不存在entity返回null，但错误表示不是合法不存在。
- 订单where/filter、user.orders采用一个scope/query builder，合法数组/组合维持AND/OR合同，先授权再查询；字段错误按I23，两层错误分开。通用权限middleware作用于list/node/nested/export/subscription，MANAGE_STAFF、MANAGE_PRODUCTS/PRODUCT_TYPES/TRANSLATIONS等既有域权限与channels、warehouse限制各入口相同；没有权限FORBIDDEN，不吞exception为[]。
- staffDelete依原 `check_permissions` / self/superuser/target-group guard，Apps仍不允许；事务真正user.delete，相关order/transaction/event FK SET_NULL、preserved email/actor snapshot保持历史；删除前收集脱敏actor event facts，on_commit单次STAFF_DELETED，不能先发事件再删失败。
- 目标退出Payment.partial、DigitalContent系列类型/根操作/ProductVariant.digitalContent/OrderLine.digitalContentUrl/旧Shop数字设置；schema查询明确不存在，数据库历史列/表先保留供迁移审计，不删除商业资产。Adyen/NP Atobarai注册/新操作拒绝迁移错误，不在payment plugins集合伪成功；旧Payment保留金额读与受支持现行售后适配，不能宣布未知旧gateway可自动扣款。
- AttributeCreate name/slug/type nonnull（slug本轮收紧），运行层reject空字符串/null；AttributeUpdate未提供保留，提供name/slug空值拒绝，type不可变且旧值不能空。draft旧voucher输入标deprecated，明确拒绝与voucherCode并发组合；新客户端只code，旧合法单voucher解析到唯一code，否则INVALID_VOUCHER_CODE，不假称所有旧ID仍可唯一转换。
- 迁移顺序：新增可空/有安全默认列→分批可信backfill和审计→CHECK/条件unique→目标读取→新客户端→退出不支持字段。新空库全链可执行；历史商业总额、现有库存allocations、gift余额不重算。迁移幂等按记录标志/unique，空表无需假fixture；回滚先停自动资金worker/outbox，前端回上一兼容读版本，再回应用层，保留已写ledger/snapshots，不能drop列抵消已发生资金。
- 验证：空库与真实分布fixture旧库迁移、主动重复backfill、冻结金额hash/关联/余额/仓库集合，所有schema差异与Dashboard operation diff；退出字段错误、基础variant/media元数据仍在、AppProblems和排除项无新类型/route/job/migration。

### BD17 · 草稿动作与展示事实
- 覆盖需求：R30、R29、R31。
- 设计说明：`graphql/order/types.py`为draft输出canAddProducts与draftOrderProblems，复用BD01/02/03的已保存资格。ADD_PRODUCTS只要求当前channel active、至少存在可选可售商品且有必要catalog/pricing，不将账单/配送完成条件错误用于禁加商品；COMPLETE要求lines、address/payment/channel/shipping等当前完整前提，canFinalize沿用字段但以同validator计算。非draft canAddProducts=false，problems=[]；不能靠按钮disabled替代mutation锁内校验。
- `graphql/order/mutations/draft_order_*`提交前再验证，切channel旧资格作废。API Weight真实单位/Decimal、discount类型与UTC DateTime保持基线，不为UI生成已格式化假日期或多一媒体pending状态。同步外链图片/上传/视频oEmbed、single/bulk普通variant、hasVariants兼容保留，不恢复独立生成器或异步外链抓取。
- 验证：inactive、无可售商品、只能添加但不能完成、切正常channel恢复、后台资格变化被拒绝；无需新重量/媒体接口。

## 4. 接口清单

完整契约集中在 `interface-contract.md`；下面是全部变更/强化边界，不重复字段权威定义。

| 接口 | 所属设计单元 | 说明 |
| --- | --- | --- |
| I01、I02 | BD01 | 显式重算、现有选择/完成重新验证 |
| I03 | BD02 | 库存资格策略与共用库存输出 |
| I04 | BD03 | 商品按渠道诊断连接 |
| I05 | BD04 | 配置delay/cutoff/revision |
| I06 | BD05 | 完成状态与批次结果可见性 |
| I07 | BD06 | 礼品卡初始化/动作/余额/事件 |
| I08 | BD07 | 摘要、可操作额、资金幂等 |
| I09 | BD08 | 根交易基础定位 |
| I10 | BD09 | 主体搜索和Page/User基本搜索 |
| I11、I12 | BD10 | 查询导出与锁定筛选/批量 |
| I13、I14 | BD11 | 密码policy与OIDC合同 |
| I15 | BD12 | EditorJS前置验证 |
| I16、I17、I18 | BD13 | manifest/安装、form响应、目录 |
| I19、I20 | BD14 | subscription/异步delivery/retry |
| I21、I22 | BD15 | 配送快照与基础metadata |
| I23、I24、I25 | BD16 | 输入错误、弃用迁移、敏感权限 |
| I26 | BD17 | 草稿动作资格 |

## 5. 工程任务与依赖

### BT01 · schema、输入与共同权限基础
- 覆盖设计单元：BD16。
- 依赖：无。
- 工作与验证：实现目标类型/标量/error-layer/common scope及退出矩阵，导出Core SDL与目标逐定义比对；pytest合法/非法ID/分页/federation，空库迁移骨架。不要手改Dashboard generated文件。

### BT02 · 安全配置与库存策略
- 覆盖设计单元：BD02、BD04。
- 依赖：BT01。
- 工作与验证：安全默认/乐观revision、通用仓库集合、reservation/allocation固定锁顺序与关系并发测试，旧行为不变和新模式各入口一致。

### BT03 · 配送与诊断及草稿资格
- 覆盖设计单元：BD01、BD03、BD17。
- 依赖：BT02。
- 工作与验证：shipping revision结果/选择/完成共validator、诊断分页、draft动作；地址/外部method/服务超时与无partial order，联调FD01/FD02/FD12。

### BT04 · 资金命令、礼品卡与金额投影
- 覆盖设计单元：BD06、BD07、BD08。
- 依赖：BT01、BT02。
- 工作与验证：command/ledger/source mapping、权限+amount锁内验证、PSP幂等/reconcile capability、root transaction与摘要；failure injection/concurrent refund/card用真实DB，不能仅mock证明。

### BT05 · 自动成单与outbox
- 覆盖设计单元：BD05、BD14。
- 依赖：BT03、BT04。
- 工作与验证：bounded scanner/lease/状态/Payment支持矩阵、complete共享屏障、once logical events；PSP已成功后崩溃、资格后变与补偿，证明只有一个订单且资金不重复。

### BT06 · 搜索及操作范围/导出
- 覆盖设计单元：BD09、BD10。
- 依赖：BT01。
- 工作与验证：主体safe搜索dirty更新与rank tie-break、Page/User basic保留，scope共享/readonlyexports/CSV字段权限与legacy jobs；与FD04/05集合比对；产品owner须落实Q01窗口。

### BT07 · 认证与内容安全
- 覆盖设计单元：BD11、BD12。
- 依赖：BT01。
- 工作与验证：policy立即生效/旧credential拦截、issuer-sub稳定关联、Google离线、EditorJS所有入口；安全矩阵和历史合法内容回归，联调FD06/07。

### BT08 · 扩展协议与自托管目录
- 覆盖设计单元：BD13。
- 依赖：BT01、BT07。
- 工作与验证：manifest current/旧归一/identifier审计/条件unique/token最小暴露、静态目录部署说明与frame协议；联调FD08/09，目录上线是部署验收而不是当前已完成事实。

### BT09 · 快照、事件载荷与历史权限
- 覆盖设计单元：BD14、BD15、BD16。
- 依赖：BT03、BT04、BT05、BT08。
- 工作与验证：order/draft shipping快照、fulfillment读取与event版本引用、delivery隔离/retry、实际staff删除；税/private权限跨subscription/node/export同测，无AppProblems。

### BT10 · 历史迁移与前后端发布验收
- 覆盖设计单元：BD01—BD17。
- 依赖：BT06、BT07、BT08、BT09。
- 工作与验证：空库/旧库迁移演练、余额/历史total/allocations/hash对比、active/disabled旧渠道、外部协议schema检查、Dashboard从目标codegen+types+Jest+Playwright，正反场景覆盖R01—R31。停worker/保数据回退演练作为发布门槛，不执行本阶段开发。

## 6. 其他

### 未决项的处理

- Q01 仍未给最终一致性SLA：不得把当前调度20秒当承诺；发布前明确窗口与故障恢复后才可判时延AC通过。
- Q02—Q05 已选技术合同：delay分钟/0..10080/默认0及旧开关不变；EditorJS支持集/深度8/大小；完整SDL/I编号/只读导出；同源目录与配置键。它们是本方案选择，不伪装为PRD已批准数值，PRD冻结不改。
- Q06 本方案给能力判定矩阵和pending/grant映射；真实provider配置和幂等/reconcile通过测试是启用后台capture的发布门槛。未知网关不假称受支持，也不能用门槛否认必须交付Transaction和兼容成功Payment成单。

### 实际检查与未执行

已执行：给定Base SDL parse；目标完整SDL parse/buildASTSchema/validateSchema；未变Base逐定义AST保留校验；26份代表性操作、18份拒绝负例、现行源402份operation与241份fragment依赖闭包静态审计；契约片段、manifest/目录/token样例及协议语法检查详见 `interface-contract.md` §3 的最终记录。基线1408定义、目标1433；59变更（含资金/投递权限说明对齐）、11旧数字定义移除、36新增、1338未变定义完整保留。没有以静态审计代替资金/权限/迁移运行测试。

未执行：任何代码开发、Django迁移、pytest、PSP访问、Celery/e2e运行、Dashboard codegen/npm lint（含autofix）/Jest/check-types/knip/Playwright、真实目录部署；材料和冻结PRD/测试未写。git status因repository dubious ownership未成功，未改safe.directory/global配置。本阶段可写仅tech-design/scratch，不为读-only设计运行会写源码的命令。上述BT是实施计划，不能据SDL静态通过声称运行行为已验收。

重点风险：PSP外部副作用不可随DB回滚；无法证明的历史source/link不自动去重重算；outbox版本化事件与敏感字段重过滤；旧token来源缺失的保守策略可能强制重登；richtext超集历史编辑需明确迁移提示；同步Core/Dashboard破坏性schema发布需先审计现行消费者。所有差异在本文件报告，不修改封存PRD或测试。
