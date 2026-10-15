# 接口对齐文档：Saleor 3.23 结账、资金与商户运营一致性

版本：v1  
责任：后端技术设计（Tech Owner），前后端共同引用  
依据：后端技术设计v1，`backend-design.md`；PRD v1  
修订：首次交付；所有新增协议均由给定Base与本次设计推导，不代表运行时已经实现。

## 1. 通用约定

### 入口、类型与兼容

- GraphQL沿用Core `/graphql/`；完整权威SDL为同目录 `target-schema.graphql`，保留未改Base定义。下述片段是精确子集，不代替完整schema。I编号可登记一组紧密相关字段；§3对变更边界逐项归属，不重排编号。
- 身份沿用现有用户JWT/会话及App bearer token；不新建认证REST。ID为带typename的Relay ID；Checkout token/Transaction token是UUID，Channel参数是slug字符串；不能相互替代。TransactionItem ID编码UUID token，兼容旧整数ID仅在Base允许的旧ID适配器内，不能将root ids直接当PK。
- Nullable参数省略一般保留/缺省；**明确允许null的清除语义逐项说明**。GraphQLinput nullable不表示业务必然接受null。新列表输出原则上列表和项目非空，Base未改列表沿原SDL。输入`[T!]`允许省略，非法null item由coercion拒绝；显式null列表如未规定清除则业务校验拒绝。
- DateTime输入必须带Z或offset（RFC3339），持久化UTC；Minute/Hour/Day非负，动作正金额规则独立于允许0的PositiveDecimal标量。Money/TaxedMoney使用Core Decimal和币种精度，客户端不固定两位、不重复税费/退款/礼品卡。
- 新分页固定上限100，first/last恰一项且1..100，invalid cursor/类型/越界/非法组合为输入错误；末尾无数据正常empty。Base未改connection参数维持既有合法签名，但实现统一修复truthiness/assert错误，不把非法参数变空页。

### 权限与错误分层

| 层 | 表达 | 客户端判定 |
| --- | --- | --- |
| 通信失败 | HTTP/网络异常 | 未确认业务，保留编辑，按幂等key重试或对账 |
| GraphQL验证/coercion | 顶层errors含message/locations/path（适用时），稳定扩展code `GRAPHQL_VALIDATION_FAILED` / `INPUT_ERROR` | 不显示完成，无执行副作用 |
| 顶层对象/field授权 | 顶层errors，extensions.code=`PERMISSION_DENIED`；显式受限对象以NOT_FOUND保护存在性 | 不是“没有数据”；不透金额/地址/token |
| 可处理mutation业务错误 | payload.errors `[Error!]!`，各项field/code/message；field null是非字段错误 | errors非空失败，不只看HTTP200 |
| Query运行时输入/服务异常 | 顶层errors，`INPUT_ERROR` / `INTERNAL_ERROR`及path，field可用extensions.field | 不转success empty；安全message不含内部凭据 |
| 异步资金/任务 | payload无errors仅受理，TransactionEvent/request及Job/delivery状态 | pending≠success，确认成功事实才业务完成 |
| 合法无匹配/空events | 无顶层/payload错误，正常空列表/空页 | 成功空结果，不视为请求失败 |

读某对象不自动取得支付、private metadata、导出、tax等权限。既有PermissionsField的列表通常是one-of；需要domain权和export权同时满足时显式AND实现。全局无权限是权限错误；在允许scope中无匹配才是空结果，不能用count/错误旁路探查受限对象。Node、嵌套关联、字段、Webhook subscription与根入口使用同scope服务。

### 保存、幂等与完成

- 配置版本与metadata版本从服务端读取；新Dashboard修改checkoutSettings/stockSettings/warehouseOrder/仓库关系、password mode、App extensions必须expectedVersion。冲突errors.code=CONFLICT，失败不写；其他不涉及这些受控字段的Base部分更新可省版本但仍锁对象并递增版本。控制参数不改变业务权限分类。
- 请求key为1..255字符非空字符串（Dashboard用UUID），作用域为身份+原始对象+动作/provider，输入fingerprint含金额/币种/目标/重要data。same key same input复用原结果，same key异参IDEMPOTENCY_CONFLICT；key不含明文card/token。初始化/新客户端资金key持久化，成单后来源checkout保留，不因FK迁移生成新动作。
- 无key旧资金消费者仍有锁/真实额度/pending占用保护，但不能把一段时间后相同金额的另一次请求自动推定为网络重试。已受理外部动作超时先对账，重试同key；不能删除已发生真实失败/pending事件假称原样回滚。
- 本地业务event生成once靠唯一outbox，delivery为既有at-least-once，远端消费者需幂等；不承诺网络exactly-once。配置已保存与订单生成/资金确认/文件完成/通知成功是不同事实。

## 2. 接口契约

### I01 · 主动重算当前结账配送
- 所属设计单元：BD01。
- 提供方：`saleor/graphql/checkout/schema.py`、拟新增 `mutations/checkout_delivery_recalculate.py::CheckoutDeliveryRecalculate`，共享strict/fresh配送服务。
- 调用方：外部Storefront checkout消费者；Dashboard无新客户页。
- 目标定义：Mutation.checkoutDeliveryRecalculate、Checkout.version、CheckoutDeliveryRecalculate、DeliverySelectionStatusEnum。

```graphql
checkoutDeliveryRecalculate(id: ID!, expectedVersion: Int): CheckoutDeliveryRecalculate
```

- 字段说明：id必填Checkout Relay ID；新消费者传最近version，旧省略也在内部staged计算后CAS。payload checkout可空，shippingMethods `[ShippingMethod!]!`、collectionPoints `[Warehouse!]!`、deliveryMethod union可空、selectionStatus可空、selectionError可空、errors `[CheckoutError!]!`。业务错误时checkout/selectionStatus为null、结果数组[]且errors非空；success无选项为无errors的empty。成功selectionStatus NONE/VALID/INVALID/NOT_REQUIRED，INVALID时deliveryMethod=null、selectionError明确旧方式原因；inactive shipping项必须active=false/message。
- 权限：Base结账token/ID受允许的checkout能力合同，客户只能自身或合法持有匿名结账能力，员工/App需适用checkout权限及对象渠道范围；无范围先拒，不调用配送服务/返回价格。ID不当作允许枚举结账的授权。
- 错误：NOT_FOUND、MISSING_ADDRESS_DATA/SHIPPING_ADDRESS_NOT_SET、SHIPPING_SERVICE_ERROR、CONFLICT；服务返回非法/熔断不能当成功[]。
- 完成判定：完整计算并版本相符才原子写入；失败原选择不变，成功确认失效则清除且不代选。async CHECKOUT_UPDATED只在实质持久化变化时一次发，读取/无变化重算不重复完成事件。
- 变更与兼容：新增显式入口，复用shippingMethods字段/价格状态，不用读取碰运气；不改变合法Base读取。

### I02 · 配送选择、兼容读取与完成边界
- 所属设计单元：BD01。
- 提供方：`graphql/checkout/mutations/checkout_delivery_method_update.py::CheckoutDeliveryMethodUpdate`，旧shipping更新、CheckoutComplete、`checkout/complete_checkout.py`；draft共享资格。
- 调用方：Storefront；FD10的草稿完成消费者。
- 目标定义：checkoutDeliveryMethodUpdate.expectedVersion、原checkoutShippingMethodUpdate/checkoutComplete/Checkout.deliveryMethod/shippingMethod、ShippingMethod.active/message。

```graphql
checkoutDeliveryMethodUpdate(deliveryMethodId: ID, id: ID, token: UUID, expectedVersion: Int): CheckoutDeliveryMethodUpdate
```

- 字段说明：id/token按Base兼容只能定位同一checkout，新的客户端用id；deliveryMethodId为ShippingMethod/Warehouse/Base App编码ID，null清除。Warehouse union表示自提，shippingMethod弃用读取对自提为空，不假装shipping。CheckoutComplete各Base参数/可空语义不变，payload order可空/errors必看。
- 权限：同I01；清除、旧ID和token不能绕对象授权。草稿完成MANAGE_ORDERS+channel。
- 错误：INVALID/NOT_FOUND、DELIVERY_METHOD_NOT_APPLICABLE、DELIVERY_METHOD_EXPIRED、DELIVERY_METHOD_UNAVAILABLE、CONFLICT；完成缺需配送方式SHIPPING_METHOD_NOT_SET，其他客户/金额/库存错误沿Core码。失效与服务通信失败区分。
- 完成判定：更新和最终成单重新算/确认当前归属和有效性，失败不部分写订单/地址/库存/资金；无需配送只免配送。重复completion通过BD04 record返回同order。
- 变更与兼容：新version参数可选以容旧消费者；旧字段沿SDL弃用原因/替代读取，合法旧方式仍适配并复查，不立即切断。

### I03 · 渠道库存来源、仓库关系与原子排序
- 所属设计单元：BD02、BD04。
- 提供方：`graphql/channel/types.py`、`mutations/channel_create.py/channel_update.py/channel_reorder_warehouses.py`、warehouse共享source服务。
- 调用方：FD01配置；商品/checkout/订单/fulfillment外部消费者；FD10草稿。
- 目标定义：StockSourceStrategyEnum、StockSettings/Input.sourceStrategy、Channel.settingsVersion、ChannelUpdateInput.expectedVersion/warehouseOrder；现有add/removeWarehouses及allocationStrategy。

```graphql
input StockSettingsInput {
  allocationStrategy: AllocationStrategyEnum
  sourceStrategy: StockSourceStrategyEnum
}
enum StockSourceStrategyEnum { SHIPPING_ZONE CHANNEL }
```

- 字段说明：输出sourceStrategy/现有allocationStrategy非空；新及迁移channel默认SHIPPING_ZONE，输入省略保留，显式null非法。allocation输入由必填改为可省，创建采用Base默认，允许source-only patch。warehouseOrder `[ID!]`是修改后完整仓库ID顺序，null非法、重复/缺漏/外部ID错误；与settings/关系同一次CAS，省略保留现有顺序。
- 权限：MANAGE_CHANNELS修改stock/关系/order，按现有channel/warehousescope；配置expectedVersion不让checkout-only权限误分类。商品/库存读取沿各对象权限/数量cap，scope前于数量。
- 错误：Channel INVALID/DUPLICATED_INPUT_ITEM/NOT_FOUND/CONFLICT；预留/分配不足按原INSUFFICIENT_STOCK等，受限仓库不在message/ID列表暴露。
- 完成判定：来源+关系+顺序事务保存和version递增，后续所有入口同候选集合；新策略地址参数接受但不改变集合，失败多行不部分预留/分配。
- 变更与兼容：新增来源非分配顺序；旧策略保留Base区域/地址聚合，旧client更新allocation不意外切换来源。旧独立reorder仍执行权限/锁/version，但新UI整体保存不用两次请求。

### I04 · 商品按渠道可售诊断
- 所属设计单元：BD03。
- 提供方：拟新增Product字段resolver/diagnosis service，基于 `graphql/product/types/products.py` 与warehouse source/listings。
- 调用方：FD02 商品编辑，受权限App。
- 目标定义：Product.channelAvailability、ProductChannelAvailabilityFilterInput/Connection/Edge/Issue、相关code/severity枚举。

```graphql
channelAvailability(filter: ProductChannelAvailabilityFilterInput, before: String, after: String, first: Int, last: Int): ProductChannelAvailabilityConnection!
```

- 字段说明：filter.search nullable渠道名包含（最多256字符）、currency nullableISO币种精确；列表/edge/node/issue均非空。每row channel!、isAvailable!、issues!、issueCount!、evaluatedAt!，variantIds为可见变体ID空列表非null。issueCount=blocking+warning，不算not-applicable；未分配渠道也可诊断，不只现有listing。
- 权限：MANAGE_PRODUCTS并具channel读权限（MANAGE_CHANNELS或对应Base域渠道读取资格），对象/渠道scope同时生效，先收敛后count。
- 错误：顶层PERMISSION_DENIED/INPUT_ERROR，服务错误不当0问题。不存在商品沿原product读取null，禁止受限信息旁路。
- 完成判定：只读计算本次已保存事实，数字配送not-applicable但仍查库存/发布；不调用外部税务/配送，不改form/draft，不代替成交检查。
- 变更与兼容：新增分页只读字段，不取代channelListings编辑，未发布根阻断不重复计正常依赖。

### I05 · 已支付结账自动完成的执行事实
- 所属设计单元：BD04。
- 提供方：`checkout/tasks.py::automatic_checkout_completion_task`、拟新增batch task/completion record共享服务；graphql Checkout字段。
- 调用方：后台任务，获准checkout管理消费者；FD01必要状态显示。
- 目标定义：Checkout.automaticCompletion、CheckoutAutomaticCompletion(StatusEnum)；checkoutComplete原order结果。

```graphql
automaticCompletion: CheckoutAutomaticCompletion
```

- 字段说明：null为没有尝试记录；record.status! DISABLED/WAITING/PROCESSING/BLOCKED/FAILED/COMPLETED，lastAttemptAt/nextAttemptAt/error/order可空。completed后checkout可能已删除，消费者使用completion返回order/既有订单查询，不能从checkout=null反推自动完成。旧订单重复token审计不能自动删。
- 权限：读取执行诊断MANAGE_CHECKOUTS或HANDLE_CHECKOUTS+对象scope；order按其字段权限。不新增客户可枚举失败日志。
- 错误：记录安全CheckoutError，资格阻断BLOCKED与worker失败FAILED分开；存在性/字段权限顶层错误。
- 完成判定：候选与执行均验证严格delay/含等于cutoff/最新开关及成功fully paid；pending不达资格。客户/账单/配送/可售库存/total>0齐全，completion唯一record+fencing产生一个order/一次有效资金动作/业务完成event；别条失败不阻断整批。
- 变更与兼容：加强Base开关/单任务，Transaction与受支持legacy Payment都可，但已成功款不再次gateway扣；配置保存不是执行完成。无公开手工“重试自动化”独立新mutation，条件修复/有界任务按记录重试。

### I06 · 自动完成设置的版本保存
- 所属设计单元：BD04。
- 提供方：ChannelCreate/Update、`graphql/channel/types.py`，现有CheckoutSettings/Input。
- 调用方：FD01。
- 目标定义：CheckoutSettings/Input及Channel版本。

```graphql
# 输出
# automaticallyCompleteFullyPaidCheckouts: Boolean!
# automaticCompletionDelay: Minute!
# automaticCompletionCutoffDate: DateTime
```

- 字段说明：输入三字段可省；switch/delay显式null非法，cutoff null清下界；delay非负分钟、设计默认0；cutoff必须带时区。开关新默认false、旧已明确值保留。delay条件`last_change < now-delay`，cutoff `created_at >= cutoff`，与PaymentSettings.checkoutTtlBeforeReleasingFunds/checkoutReleaseFundsCutOffDate无关。ChannelUpdate checkoutSettings需expectedVersion，version null/缺失返回REQUIRED。
- 权限：创建MANAGE_CHANNELS；仅checkoutSettings更新MANAGE_CHANNELS或MANAGE_CHECKOUTS，混合请求按所有实际字段权限，version不算业务字段。
- 错误：Channel REQUIRED/INVALID/CONFLICT，组合/时间格式/input type执行前拒，权限顶层，不改别channel/原生效值。
- 完成判定：同channel保存成功返回新version/当前值，重新读相同；只有实际任务结果才订单完成。关闭开关在提交前复核，未执行新动作停止。
- 变更与兼容：新增delay/cutoff/CAS，原开关描述更新支持合法Payment但不pending；旧Base-only消费者须迁移新配置保存version，字段缺省不擅启自动化。

### I07 · 内建礼品卡初始化、授权与扣款
- 所属设计单元：BD05。
- 提供方：`graphql/payment/mutations/transaction/transaction_initialize.py`、transaction_process.py，拟新增gift-card adapter/reservation model。
- 调用方：Storefront/支付集成，FD03只消费真实交易；订单礼品卡初始化获准员工/App。
- 目标定义：TransactionInitialize/Process现有输入及新增process.idempotencyKey，Checkout.availablePaymentGateways内建方式（id="saleor.gift-card"、name="Gift card"、config=[]、currencies=[当前币种]；不含卡code且不是旧checkoutPaymentCreate的普通gateway回退），GiftCardPaymentMethodDetails、GiftCard.availableBalance/reservedBalance、PaymentMethodTypeEnum.GIFT_CARD。

```graphql
# 对现有transactionInitialize变量示例（不是新操作）
# paymentGateway: {id: "saleor.gift-card", data: {code: "customer-secret-code"}}
# action: AUTHORIZATION 或 CHARGE
```

- 字段说明：amount可省（取服务端当前需支付额度）、显式0拒；card code非空不回显；adapter data只接受code，其他字段INVALID。initialize.idempotencyKey现有可省但新消费者必传；内部稳定provider key分离App FK，process continuation同source/action/transaction，data省略允许，不接受另一个card变更。action override一般Base仅HANDLE_PAYMENTS App；内建giftcard为owner客户/获准订单调用方明确例外，不放宽其他gateway。
- 权限：客户合法own checkout/own payable order能力；员工订单范围需MANAGE_ORDERS并HANDLE_PAYMENTS，App HANDLE_PAYMENTS且处理对象scope。card code作为消费秘密不允许全卡查询；GiftCard余额管理读取MANAGE_GIFT_CARD+对象范围，customer transaction只遮罩details。
- 错误：TransactionInitialize/Process增GIFT_CARD_NOT_FOUND/GIFT_CARD_INACTIVE/GIFT_CARD_EXPIRED/GIFT_CARD_CURRENCY_MISMATCH/GIFT_CARD_INSUFFICIENT_BALANCE、INVALID_AMOUNT/STATE/AMOUNT_EXCEEDS_BALANCE/IDEMPOTENCY_CONFLICT；参数/权限拒绝无余额/事件副作用，不回退普通支付。
- 完成判定：授权增加active reserved，available=current-reserved；成功charge一次减少current并消费reservation，标准事件/对象支付事实同金额；initialized/请求pending不当charge success。成单关联FK切换不丢sourceCheckoutId/原幂等结果。
- 变更与兼容：Base抵扣路径原语义只对legacy basis保留，不能与adapter同checkout混用；历史合成交易不重新扣卡，事件源唯一键迁移不改变金额。GiftCardMethod实现PaymentMethodDetails且默认name“Gift card”、遮罩displayCode/last4，无完整code字段。

### I08 · 礼品卡授权取消与订单退款
- 所属设计单元：BD05。
- 提供方：TransactionRequestAction/gift-card adapter，与I10共用动作账。
- 调用方：Storefront未完成checkout取消；FD03获准订单售后。
- 目标定义：transactionRequestAction(actionType:CANCEL|REFUND,amount,id|token,idempotencyKey)、标准TransactionEvent/GiftCard金额。

- 字段说明：CANCEL只释放未消费授权，订单charge后REFUND；省amount取当前合法剩余额度，显式0/负拒。取消可以部分释放合法剩余，退款小于等于availableRefundAmount。退款恢复原成功扣款，不创建普通支付；原卡已停用/过期不禁止合法资金退回，新的消费仍禁止。
- 权限：一般transactionRequestAction HANDLE_PAYMENTS+channel；仅内建giftcard未完成checkout CANCEL允许owner消费能力的例外，REFUND订单需HANDLE_PAYMENTS及对象范围，不因能看订单即可退款。
- 错误：RequestAction INVALID_STATE/INVALID_AMOUNT/AMOUNT_EXCEEDS_BALANCE/IDEMPOTENCY_CONFLICT及card特有码，禁止泄露受限额度。
- 完成判定：余额、reservation、成功标准event、order/checkout状态一次原子一致；同key取消/退款只释放/回充一次。事件empty查询成功不是动作失败。
- 变更与兼容：Base无此礼品卡完整链路，复用当前交易入口、标准events及余额字段，不新造无法查账抵扣。

### I09 · 统一金额摘要、流程与礼品卡口径
- 所属设计单元：BD06。
- 提供方：Order/Checkout resolver与拟新增payment summary calculator。
- 调用方：FD03、Storefront及获准支付集成。
- 目标定义：Order.paymentSummary/Checkout.paymentSummary、PaymentSummary、GiftCardAmountBasisEnum、PaymentAggregationFlowEnum。

- 字段说明：summary非空；所有TaxedMoney/Money/枚举非空。merchandiseAfterDiscounts+shippingAfterDiscounts为已优惠商品/配送事实；discount和tax为解释项（税含gross不再加）。total是服务端当前总额；payableBeforeGiftCards为原始应付解释；giftCardCharged是卡成功净支付贡献，authorized/charged当前净额，refunded历史成功退款，chargePending/refundPending各自未决；balance沿Core欠款负，outstanding=max(-balance,0)。LEGACY_TOTAL_DEDUCTION total已经减卡，不再用合成卡交易减balance；TRANSACTION_PAYMENT total完整，卡贡献charged一次。paymentFlow PAYMENT/TRANSACTION不盲双加。
- 权限：对象owner/允许订单checkout读取可取安全summary，不解锁transaction/private/card详情；字段相同scope，税务敏感user/private另查权限。
- 错误：未知计算失败顶层错误，不返回零总结；历史缺乏证据不可由当前卡余额编原金额，采用历史审计失败/保守已有总额，不改order。
- 完成判定：与Core totalBalance/当前净事件一致；charged80/refunded20仍净80，授权转charge不两次计，pending不意味着fully paid，待付≥0。兼容Payment用其capturedAmount专有规则。
- 变更与兼容：新增权威summary，既有authorized/charged描述校准为净额语义，不改历史金额；客户端不套另一公式。

### I10 · 当前额度、幂等人工资金动作
- 所属设计单元：BD06。
- 提供方：transaction_request_action.py、transaction_process.py、order_capture.py/order_refund.py/order_mark_as_paid.py及gateway。
- 调用方：FD03；获准支付App。
- 目标定义：TransactionItem.availableChargeAmount/availableRefundAmount/sourceCheckoutId，orderCapture/Refund/MarkAsPaid和transactionRequestAction/Process.idempotencyKey，新增相关error codes。

```graphql
orderCapture(amount: PositiveDecimal!, id: ID!, idempotencyKey: String): OrderCapture
orderRefund(amount: PositiveDecimal!, id: ID!, idempotencyKey: String): OrderRefund
orderMarkAsPaid(id: ID!, transactionReference: String, idempotencyKey: String): OrderMarkAsPaid
```

- 字段说明：order amount必填>0；requestAction可省max但0拒且不裁剪。availableCharge净授权扣当前charge/cancel占用；availableRefund净charged扣pending refund占用（内部尚未入聚合的reservation只扣一次）。sourceCheckoutId可空不可编辑，保留原结账来源且同交易可见范围。key规则§1。
- 权限：orderCapture/Refund/MarkAsPaid沿Base MANAGE_ORDERS+channel（不机械叠HANDLE_PAYMENTS）；transactionRequestAction HANDLE_PAYMENTS+channel/owner App范围。giftcard owner CANCEL例外见I08。不是PermissionsField one-of误当AND。
- 错误：Order INVALID_AMOUNT/AMOUNT_EXCEEDS_BALANCE/IDEMPOTENCY_CONFLICT/PAYMENT_ALREADY_EXISTS等；RequestAction同码。输入/权限/额度失败原事实不变；发外部后pending/failed真实事件保留。
- 完成判定：先查同key既有结果再状态拒绝，锁最新额度，占用/请求ledger后单次外部action。无支付记录及账单/状态合法才能mark paid；已有任意冲突记录拒新key。服务商确认事件才成功，动作受理后刷新Core，不能靠errors=[]提示已到账。
- 变更与兼容：修复Base amount or/max/min裁剪，新增可选key以保旧client签名，最新Dashboard必传。旧Payment capture/refund保留其动作和净额，不强加新交易算法。

### I11 · 根级交易基础定位与分页
- 所属设计单元：BD07。
- 提供方：`graphql/payment/schema.py/resolvers.py/types.py`，拟新增授权queryset/root-list resolver。
- 调用方：FD03，客服/支付App、owner客户读取。
- 目标定义：Query.transaction/transactions、RootTransactionFilterInput、TransactionCountableConnection/Edge。

```graphql
transactions(filter: RootTransactionFilterInput, before: String, after: String, first: Int, last: Int): TransactionCountableConnection
```

- 字段说明：root filter仅orderIds/checkoutIds/ids `[ID!]`、pspReference/appIdentifier String；字段AND，数组OR，[]为空范围非所有，省略不限维度，null list/item非法。checkoutIds包括当前及sourceCheckoutId持久化来源，已成单可查；旧无来源null不伪造。PSP精确匹配transaction或其event参考并distinct；App.identifier精确，内建giftcard无假App。edges/node非空，events `[TransactionEvent!]!`空正常；稳定PK升序/反向分页，无sortBy/日期/event筛选，分页§1。
- 权限：客户认证owner且排除无权draft，员工HANDLE_PAYMENTS+对象channel，App HANDLE_PAYMENTS+自身交易/明确处理scope。single id/token必须恰一或同一对象兼容，矛盾INVALID；Node/嵌套同授权。Transaction公私metadata按HANDLE_PAYMENTS及其scope，customer owner不解锁；createdBy/user敏感字段保持字段guard。
- 错误：顶层PERMISSION_DENIED/INPUT_ERROR，受限明确id NOT_FOUND；合法无匹配empty，无权限不以empty掩盖。
- 完成判定：交易方式/净额/事件与订单summary一致，固定集无重复漏项；不新增专用索引排序。
- 变更与兼容：root list新增；single Base HANDLE_PAYMENTS合法消费保留，扩展安全owner读；不复用Base Order用TransactionFilterInput、不借别名暴露非目标。

### I12 · 主体增强与页面用户基础搜索
- 所属设计单元：BD08。
- 提供方：product/order/giftcard search、checkout filters；account/search.py、page filters及原更新tasks。
- 调用方：FD04/FD05，各主体列表/分配弹窗与外部管理消费者。
- 目标定义：现有products(search,sortBy:ProductOrder)、orders(search,sortBy:OrderSortingInput)、giftCards(search,sortBy:GiftCardSortingInput)、checkouts(filter:CheckoutFilterInput,sortBy:CheckoutSortingInput)及filter.search；CheckoutSortField/GiftCardSortField新增RANK，User/Page排序未改。

- 字段说明：trim/Unicode/case正规化、重复词去重、空格AND，双引号短语顺序匹配，仅未引号末词prefix，主体ID/checkout token/PSP exact快捷定位保留；搜索最多256 Unicode字符，不闭引号/控制符非法。空词回过滤/权限/分页限制默认列表。RANK仅四主体有词时用，rank_key=`round(SearchRank*1000000)::bigint`与pk同时用于排序/游标/seek（量化值为技术取值），短语不得跨独立字段拼接；Page/User基础组合词搜索不加高级prefix/RANK。
- 权限：域管理及对象scope，客户/staff隐私字段及count受限；窗口不放宽。
- 错误：顶层INPUT_ERROR/服务错误，不success empty；合法空结果正常。
- 完成判定：mutation提交后的有界dirty/version任务最终反映新名称/SKU/email/关联，旧worker不能清新dirty；drain任务测试更新，不无来源承诺秒数。Page引用变更继续更新Product。
- 变更与兼容：只增强四主体，未关闭Base page/user基础；不新增Page/User高级索引/tasks/migration，排序相同rank稳定PK。

### I13 · 当前筛选查询导出及兼容作业
- 所属设计单元：BD09。
- 提供方：拟扩展 `graphql/csv/schema.py` query/resolvers、csv tasks/export及ExportFile授权service。
- 调用方：FD04产品/礼品卡/voucher/代码导出，授权集成。
- 目标定义：Query.productsExport/giftCardsExport/vouchersExport/voucherCodesExport、新四输入、ExportVouchers；旧exportProducts/exportGiftCards/exportVoucherCodes弃用；PermissionEnum新增三个export码。

```graphql
productsExport(input: ProductsExportInput!): ExportProducts
giftCardsExport(input: GiftCardsExportInput!): ExportGiftCards
vouchersExport(input: VouchersExportInput!): ExportVouchers
voucherCodesExport(input: VoucherCodesExportInput!): ExportVoucherCodes
```

- 字段说明：scope/fileType/key必填，ids `[ID!]`可省；product同列表where/search/channel/sortBy及exportInfo，giftcard同filter/search/sortBy，voucher同filter/channel/sortBy，code同voucherId/ids。IDS非空+有效scope交集、FILTER必须有effective过滤（锁定亦算）、ALL无约束才允许；错组合/null/重复/范围外ID拒而非退全量。返回exportFile可空/errors `[ExportError!]!`，job.status!=SUCCESS或无url未完成；url可空，旧events可空按Base。
- 权限：分别MANAGE_PRODUCT_EXPORTS + MANAGE_PRODUCTS、MANAGE_GIFT_CARD_EXPORTS + MANAGE_GIFT_CARD、MANAGE_VOUCHER_EXPORTS + MANAGE_DISCOUNTS，AND且范围收敛；历史等价授权迁移避免意外锁出，不拓权。ExportFile/File列表同owner/domain/当下导出权，App only own jobs，worker执行时再鉴权。
- 错误：Export REQUIRED/INVALID/NOT_FOUND；权限顶层，后台job FAILED安全message，不文件成功空响应。
- 完成判定：Query有创建/replay job语义，不是纯读，same key异参为Export INVALID（message安全说明幂等参数冲突）、同参返回同job；Apollo no-cache、HTTP private/no-store、不启GET/CDN共享query缓存，只有显式用户动作调用。接收保存授权effective snapshot，后台按范围输出全部匹配，不只当前页；文件完成/事件才下载成功。排序只文件顺序。
- 变更与兼容：Base仅三旧mutation，保留实作/同权限的弃用，当前query新增voucher主体及code替代，未假称Base exportVouchers存在。giftcard code若导出使用仅未使用卡的Base安全规则，列表导出可导允许的基础信息但full code不对已用/受限卡放开。

### I14 · 列表、层级与锁定范围
- 所属设计单元：BD09。
- 提供方：现有product/order/giftcard/category/warehouse query、assignment及bulk mutation。
- 调用方：FD04/FD05。
- 目标定义：Base各CountableConnection/filter/where/AND/parent/ids、I13导出输入；无新增独立导航协议。

- 字段说明：锁定条件是前端context AND普通条件；分页/排序当前scopeFingerprint；selected ids和filter全范围分开确认。层级对象用ID去重，不label拼接，取消必须移除。Core不把可改URL“锁定”当授权来源。
- 权限：所有直接query/bulk/export执行真实scope，受限warehouse/category不借候选/count泄露。
- 错误：查询network/input/permission和无匹配各自独立；bulk沿Base每对象错误原子合同，新UI不得隐式操作范围外旧选择。
- 完成判定：列表/count/export/bulk用当前有效范围，旧响应/失败范围不能用于动作；回列表保导航和锁定范围。没有Core对象写的纯导航不产生event。
- 变更与兼容：签名基本保留，统一客户端范围构造/服务器边界；不新增独立UI服务。

### I15 · 密码三态及商店版本
- 所属设计单元：BD10。
- 提供方：Shop/ShopSettingsUpdate、account authentication guard、core.auth_backend。
- 调用方：FD01/FD06；外部customer认证消费者。
- 目标定义：Shop.passwordAuthenticationMode/settingsVersion、ShopSettingsInput.passwordAuthenticationMode/expectedVersion、PasswordAuthenticationModeEnum和AccountErrorCode三新policy码。

```graphql
enum PasswordAuthenticationModeEnum { ENABLED CUSTOMERS_ONLY DISABLED }
```

- 字段说明：公开有效mode非空，默认/迁移ENABLED；settingsVersion非空但MANAGE_SETTINGS字段guard。输入mode省略保留/null非法，修改mode expectedVersion必需；saved后下次认证主库立即读新值。外部providers不受password mode误禁。
- 权限：读mode无需登录，改MANAGE_SETTINGS。CUSTOMERS_ONLY is_staff用户无password员工会话（不能降级绕后台）；DISABLED拒登录/reset/set/change/register密码路径及password-derived旧refresh/verify，guard先于写密码/邮件任务/签token。
- 错误：policy Account PASSWORD_AUTHENTICATION_DISABLED/PASSWORD_AUTHENTICATION_CUSTOMERS_ONLY/EXTERNAL_AUTHENTICATION_REQUIRED；Shop REQUIRED/INVALID/CONFLICT，权限顶层。reset错误不能枚举邮箱。
- 完成判定：保存只生效mode，不代表登录；旧本地token按policy generation失效，external owner token按provider合同不全禁。未保存/失败draft不进入policy cache。
- 变更与兼容：新策略保存CAS，旧未配置保旧密码能力；login/reset独立route同样gating，无provider稳定empty。

### I16 · OIDC provider参数与首次身份关联
- 所属设计单元：BD10。
- 提供方：`plugins/openid_connect/plugin.py/utils.py`、externalAuthenticationUrl/externalObtainAccessTokens及refresh/verify。
- 调用方：FD06及外部OIDC消费者。
- 目标定义：Base externalAuthenticationUrl/externalObtainAccessTokens/ExternalRefresh等JSON/JSONString字段，签名保留；OAuth2授权/回调沿provider既有边界，不新增REST服务。

- 字段说明：Google refresh请求access_type=offline，不附offline_access；其他provider按其own合同。首次合法issuer/sub+verified email关联原用户，保存唯一identity、disable本地password/旧password token，后续同sub复用。回调state/nonce/redirect规则沿现有安全流程，不输出token敏感原串。
- 权限：provider身份校验/现有用户关联条件，不能按未验证邮箱自动合并；外部认证独立于password mode。
- 错误：BaseAccount INVALID/JWT类/安全认证错误，不部分关联；本地password再开被EXTERNAL_AUTHENTICATION_REQUIRED阻止。
- 完成判定：token成功且identity关联完整才登录，失败无新用户/半关联；前端不不必要持久化refresh token。
- 变更与兼容：仅provider参数/首关联密码旁路修复，Base外部API签名保留。

### I17 · EditorJS结构、固定协议与深度
- 所属设计单元：BD11。
- 提供方：`core/utils/editorjs.py`、所有SanitizedJSONField保存前mutation validators。
- 调用方：FD09 product/page/collection/shipping/translation内容保存，授权App。
- 目标定义：现有description/translation.description JSONString输入及Product/Page/Collection/Shipping/TranslationErrorCode新增INVALID_RICH_TEXT_STRUCTURE/UNSAFE_URL/RICH_TEXT_TOO_DEEP；其他richtext入口沿其INVALID返回相同安全路径。

- 字段说明：JSON形状和block固定allowlist见 `interfaces/app-boundaries.schema.json#/$defs/EditorJS`，legacy字符串list与结构化nested list最大10（root item=1），未知/多余字段/非法类型拒；Dashboard不得继续降维丢失合法nested子项。URL固定http/https/mailto/tel及安全相对站内，scheme解码正规化后验证，不可配置扩协议；新窗口安全rel。
- 权限：原域编辑/translation权限不变。
- 错误：payload.field定位description，message含blocks路径/深度位置但不回显危险原串；整个业务保存失败保持原文，不清洗部分后报success。bulk按既有明确事务策略，不把一项失败当整批成功。
- 完成判定：validate全输入再sanitize再原子保存，合法nested/link往返，后端数据库字段仍防御；历史读取/搜索抽取容错不意味着允许重新保存危险数据。
- 变更与兼容：安全语义加强/三可分支码，Base合法block继续；image.file.url正确清理，不继承旧ulr拼写错误。

### I18 · App安装、当前扩展及历史编辑
- 所属设计单元：BD12。
- 提供方：`graphql/app/mutations/app_install.py/app_update.py/app_fetch_manifest.py`、manifest_validations/installation_utils、AppExtension types。
- 调用方：FD07、授权App管理人员/集成。
- 目标定义：AppInstallInput appName!/manifestUrl!；AppExtension/AppManifestExtension mountName/targetName/settings!及旧deprecated别名，AppExtensionFilterInput新字段；App.settingsVersion、AppInput.extensions/expectedVersion、AppExtensionSettingsInput；manifest JSON `interfaces/app-boundaries.schema.json`，HTTP说明 `interfaces/app-http.openapi.yaml`。

- 字段说明：新manifest扩展required label/url/mountName/targetName，permissions缺省[]、settings缺省{}；target-specific method GET/POST（已知WIDGET/NEW_TAB），unknownsettings或非法target拒，完整JSON存储。旧mount/target/options只读映射、历史已存method确定转settings，无法恢复options不伪造。AppInstall名字/URL非空，activateAfterInstallation Base默认true，permissions数组项目nonnull。
- 权限：安装AUTHENTICATED_STAFF_USER AND MANAGE_APPS且可授予权限范围；appUpdate MANAGE_APPS+appscope/权限子集。identifier非空唯一（更新排自身），扩展权限不超过App。读取按允许的App/extensions范围，token/settings敏感项不泄露。
- 错误：App INVALID/REQUIRED/UNIQUE/OUT_OF_SCOPE_PERMISSION/CONFLICT/MIGRATION_REQUIRED沿实际enum；非法旧manifest输入明确迁移而非静默忽略，重复identifierrace由DB/锁归约同错。缺需要token的POST可信origin配置INVALID；合法无token GET/POPUP可装。
- 完成判定：install返回appInstallation是受理，worker真正installed后刷新；tokenTargetUrl缺省跳过不需要token，不返回新token。若需要token，独立POST `{auth_token}`沿既有安全合同，目标origin验证、不入public响应。appUpdate更新extensions需要expectedVersion，整组验证/替换事务，省略保留/[]清空，id只能自己扩展；失败原App有效数据不破坏。新客户端不再提交旧扩展字段。
- 变更与兼容：CoreBase旧字段而Dashboard部分query已有新字段，修复实际接缝；保留旧读取弃用不重装，GraphQL预览沿BaseManifest字段及新增extension JSON，不假称已有customHeaders预览。

### I19 · App frame对当前表单回应
- 所属设计单元：BD12。
- 提供方：App iframe、Dashboard AppFrame/useAppActions及AppExtensionContext；拟新增form-response action。
- 调用方：FD07、FD02/FD09商品/翻译表单。
- 目标定义：非网络postMessage协议 `interfaces/app-boundaries.schema.json#/$defs/FormMessage`；Base notification/redirect/requestPermissions等action及actionId保留安全约束，不新增GraphQL操作。

- 字段说明：type固定SALEOR_FORM_RESPONSE、action=formResult，frameId/requestId/contextVersion/formType必填，status SUCCESS/VALIDATION_ERROR/PERMISSION_ERROR/CLOSED；SUCCESS含values对象，VALIDATION_ERROR含errors `[field,code,message]`非空、可有只展示的previewValues，其余不带values/previewValues。首轮formType为PRODUCT/TRANSLATION：产品仅name/slug/seoTitle/seoDescription/description，翻译仅name/seoTitle/seoDescription/description；握手可进一步收窄allowedFields/nullableFields（description是EditorJS对象/null），不接受价格、权限、metadata等未开放路径。省略保留、null仅本次允许nullable时清，SUCCESS {}为no-op，未知/type错误拒整message。VALIDATION_ERROR的安全previewValues只供用户查看和修正，不自动合并dirty字段，不表示保存；permission/closed无draft写。FormContext→FormReady握手、FormMessage→FormAck结构均在附加schema，沿既有actionId可选echo，ACK仅受理编辑/展示，不代表保存。
- 权限：postMessage不具Core授权效力；同时验origin（完整scheme/host/port）、source===对应contentWindow、frameId+requestId+ready握手+当前context。字段保存仍Core域权限。
- 错误：本地协议reject/忽略无效，不throw未知action导致page崩；permission/closed保持baseline，validation errors定位字段。重复已应用message只回原ACK，不重应用。
- 完成判定：合法当前回应仅更新draft，用户继续编辑/context变更后旧回应拒；最终manual save成功才已保存事实。多个frame不交叉写。
- 变更与兼容：保留旧actionId相关性/targetOrigin，新form envelope需App opt-in握手；未支持App仍现有actions，不盲读任何来自同origin消息。

### I20 · 自托管扩展目录浏览
- 所属设计单元：BD12。
- 提供方：部署配置的 `EXTENSIONS_API_URL` 既有JSON静态/目录HTTP服务（无新Core服务），`interfaces/app-http.openapi.yaml` Catalog路径及app-boundaries Catalog schema。
- 调用方：FD07 ExploreExtensions/useAppStoreExtensions/useExploreExtensions。
- 目标定义：GET配置URL，BaseAPIExtensionsResponse分组数组（id/name/ extensions），APP/PLUGIN discriminant；对应JSONschema。GraphQL安装用I18，不把catalog加载当安装。

- 字段说明：每组id稳定（payments/taxes/cms/automation），name.en非空，extensions[]可空且nonnull；每item id/name/description/logo必填，APP含kind OFFICIAL/OSS、manifestUrl/repositoryUrl nullable，PLUGIN不带APP字段。缺配置使用本地[]并明确未配置，合法无匹配正常empty；logo/链接URL安全验证。installed/AppId仅Core已安装查询对照，目录布尔不能可信替代。
- 权限：浏览只读允许，安装MANAGE_APPS/配置plugin MANAGE_PLUGINS；自托管不因非Cloud一律禁止合法安装。Core仍权限scope，installed query无权/失败显示unknown而非未安装，完整分页。
- 错误：HTTP/network/CORS/invalid JSON局部error+retry，不throw整个page，不success empty；abort/旧generation忽略。
- 完成判定：成功clear旧error并显示目录，filter只浏览，不建App；实际I18安装结果才状态变。
- 变更与兼容：沿已有可配JSON边界换可靠配置，不依赖不可用legacy address唯一来源；HTTP字段shape兼容Base，不自建REST安装API。

### I21 · 订阅驱动Webhook、独立delivery与重试
- 所属设计单元：BD13。
- 提供方：subscription_types/SyncWebhookControlContext、webhook async transport/tasks、event_delivery_retry；已有Webhook.eventDeliveries。
- 调用方：App订阅接收方；FD08 delivery/attempt/失败告警。
- 目标定义：EventDelivery.payloadState/lastError，EventPayloadStateEnum，EventDeliveryStatusEnum新增PROCESSING/RETRYING；原eventDeliveryRetry、event/Order/DraftOrder/Fulfillment/ProductVariantUpdated类型和既有事件；HTTP `interfaces/app-http.openapi.yaml` Webhook路径。

- 字段说明：payload nullable不代表成功；payloadState WAITING/READY/FAILED，status PENDING/PROCESSING/RETRYING/FAILED/SUCCESS；lastError可空脱敏。事件时必要snapshot/recipe持久化，完整payload后台构建；成功delivery保留最小审计，不即时整条删除，payload/attempt按既有配置清理。eventDeliveryRetry.errors非空失败，retry job无error只排队。
- 权限：订阅按App权限与业务scope，只实际selection字段解析；retry沿Base MANAGE_APPS并校验对应App/对象scope，payload可读边界不扩大。HANDLE_TAXES允许对应tax事件必要字段，不所有private。
- 错误：Webhook INVALID/NOT_FOUND/权限等沿Base；构建失败写payloadState FAILED/lastError，A失败不影响B/C；缺payloadretry先重建不直接标success。
- 完成判定：pure async业务请求只event/outbox，不完整解析或调用无关税务/配送；同event每App独立delivery，每次重投保持原事件；variant discounted price实质变化在提交后一次PRODUCT_VARIANT_UPDATED / ProductVariantUpdated通知，no-op不触发，不新增未经Base证实专用价格事件。subscription可按channel读取其价格字段。
- 变更与兼容：状态/后台边界增强，HTTP raw JSON、Saleor/X-Saleor headers、secret HMAC或无secret JWS、既有超时/重试/熔断策略不改；Base没有event/delivery-id header不虚称存在。消费者按已有payload对象/事件业务key+签名幂等，无远端exactly-once承诺。保留失败告警，不AppProblems。

### I22 · 订单与履约的配送历史快照
- 所属设计单元：BD14。
- 提供方：Checkout/draft成单最终事务、Order/Fulfillment resolver。
- 调用方：FD09、订单/履约App与event消费者。
- 目标定义：Order/Fulfillment.shippingMethodMetadata/privateShippingMethodMetadata `[MetadataItem!]!`。

- 字段说明：列表和项非空，无配送/无可恢复历史[]；取实际创建时已验证配送资料deep copy。外部Base shipping结果只有public metadata，private没有受支持来源则[]，不虚构。源method后改/停用/删不变；与shippingTaxClass及对象metadata不同。
- 权限：public按可读order/fulfillment；private MANAGE_ORDERS+channel或对应tax event必要范围，查询无權字段顶层error，不返回源shipping权限替代。事件同scope。
- 错误：字段PERMISSION_DENIED，不从错误泄露key/value；成单snapshot采集失败不部分order。
- 完成判定：checkout/draft两条最终锁内创建一次，Fulfillment投影所属order，不另生成可变副本；已完成order不回写。
- 变更与兼容：新增只读字段，迁移不从当前源伪造历史，不改旧对象元数据；无snapshot给稳定empty而非伪数据。

### I23 · 基础元数据与多对象原子保存
- 所属设计单元：BD14。
- 提供方：拟新增graphql/meta metadataBundle/metadataUpdate/metadataBulkUpdate，现有update/delete四路径共享write service。
- 调用方：FD09既有订单行内/订单行-variant编辑、checkout/履约基础业务。
- 目标定义：Query.metadataBundle、Mutation.metadataUpdate/metadataBulkUpdate、MetadataBundle/AtomicMetadata(Update/BulkUpdate)/Input，MetadataErrorCode.CONFLICT。

```graphql
metadataBundle(id: ID!): MetadataBundle
metadataUpdate(input: AtomicMetadataUpdateInput!): AtomicMetadataUpdate
metadataBulkUpdate(input: [AtomicMetadataUpdateInput!]!): AtomicMetadataBulkUpdate
```

- 字段说明：支持Checkout/CheckoutLine/Order(含draft)/OrderLine/Fulfillment/ProductVariant既有业务metadata，不含配送snapshot；输入id/expectedVersion必填，metadata/privateMetadata upserts、deleteKeys/deletePrivateKeys，省略不变/null非法/[]no-op，duplicate key/同key改删/空key拒；bulk非空、无重复对象、全部权限/版本验证。输出bundle metadata/version/id非空，private列表nullable（public-only读null，不fake[]）；bulk metadataBundles `[MetadataBundle!]!`，失败[]和errors非空。
- 权限：Checkout/Line public沿Base合法checkout能力，private MANAGE_CHECKOUTS；Order/Line/Fulfillment MANAGE_ORDERS及范围；ProductVariant MANAGE_PRODUCTS，相关private严格Base；每个非空动作分别检查。tax-only上下文可必要private读，不放开编辑。
- 错误：Metadata INVALID/REQUIRED/NOT_FOUND/CONFLICT，业务message包含输入索引/field安全定位，无权限顶层；所有输入校验先于创建独立CheckoutMetadata行。
- 完成判定：共享版本+全局锁序，先锁Checkout/Order等父对象，再在同级按type/pk锁具体metadata对象，避免bulk反转业务锁序；一次事务所有object public/private/delete成功，任一失败全部回滚；旧update/delete也递增同version、不能stale整字段覆盖。订单行+variant用bulk一请求，订单confirm与metadata保存是清晰独立动作，不暗中先确认造成半成功。
- 变更与兼容：旧四metadata mutations单请求保留合法签名/权限/原子性，新Dashboard一个业务save不拆多请求；不新增订单/履约/仓库独立metadata UI。

### I24 · 公开参数校验、类型及查询失败
- 所属设计单元：BD15及各业务BD。
- 提供方：core scalars/connection/federation/validators、order where/User.orders及所有mutations。
- 调用方：FD01—FD10、Storefront/App。
- 目标定义：Query._entities改 `representations:[_Any!]!`，现有Minute/Hour/Day/PositiveDecimal/where/list，各新增错误码。

```graphql
_entities(representations: [_Any!]!): [_Entity]
```

- 字段说明：representations整体/项目nonnull并运行时验证对象typename/key，合法[]是空实体结果，合法单项/数组可用；数值非负、动作正金额、时区必有，分页1..100及组合/ID类型稳定校验。数组null不能执行到len/assert崩溃，amount0不当省略。Order条件单/数组/组合、User.orders保owner权限/channel/客户不见draft。
- 权限：各对象/field原动作权限，不把transport成功当授权。
- 错误：coercion/top-level与payload分层§1，field/code/message可处理；unknown内部错误安全失败非[]。
- 完成判定：前置校验失败无外部/本地写；合法无匹配success empty与input failure明确不同，状态写按最新锁与幂等。
- 变更与兼容：Federation收紧危险null，合法数组不变；公开字段未改签名也修执行语义，非“API200所以成功”。

### I25 · 当前客户端、必填与退出能力
- 所属设计单元：BD15。
- 提供方：schema registration/attribute/app/draft/export/plugin路径。
- 调用方：FD10、全部生成client/外部集成。
- 目标定义：移除Payment.partial及DigitalContent*全类型/根query/mutation/variant.digitalContent/旧Shop数字设置；AppInstallInput必填、DraftOrderCreateInput/DraftOrderInput.voucherCode和voucher弃用、AttributeCreate/Update原输入。

- 字段说明：attribute name/type创建必填，slug省略自动生成，update字段省略不改，显式null/空name/slug非法；不新增不可更新type输入。draft voucherCode沿Base已存在/当前值读取，旧voucher输入明确migration error，不同时接受二者形成歧义。退出native下载不退出数字商品/Apps。
- 权限：原attribute type/product管理权限、App install及export专用权限依I18/I13。
- 错误：移除操作GraphQL不存在，旧插件新动作PAYMENT_ERROR/MIGRATION_REQUIRED安全错误，旧voucher Order MIGRATION_REQUIRED；旧导出保实际授权job不empty。
- 完成判定：Core生成runtime SDL与本target语义一致，Dashboard本地codegen/operation validation，错误映射同步，无退出operation继续生成或发送；空库/旧数据迁移保金额/余额/对象事实。
- 变更与兼容：旧Adyen/NP Atobarai不注册新调用，历史Payment继续读；shipping等弃用读取保留明确替代。非目标AppProblems/PageUser高级/transaction高级/generator/async media/独立metadata全不暴露。

### I26 · 真删除、导出与税务敏感字段授权
- 所属设计单元：BD15。
- 提供方：staffDelete/StaffBulkDelete、attribute/app/export、Checkout/Order/private metadata/user field guard。
- 调用方：FD10/FD04/FD07；授权管理App、tax App。
- 目标定义：Base staffDelete/staffBulkDelete真实删除语义、I13导出权限、Checkout/Order.user/privateMetadata/privateMetafield/privateMetafields及Node/订阅；SDL签名保留。

- 字段说明：staffDelete成功目标User真的不存在，Order.user SET_NULL而历史email/地址/金额/付款/履约保持；未完成有钱checkout先安全解除UserFK保事实，不能CASCADE丢reservation。自删/超管理scope/最后管理者保护保留；bulk按Base确定每项结果，不误装success。
- 权限：MANAGE_STAFF及可管理权限范围，App删除员工沿Base禁用；attribute/App/domain权限同直调；tax HANDLE_TAXES仅对应授权tax事件必要user/private字段，普通query的User隐私仍owner/实际权限，private普通读取保MANAGE_CHECKOUTS/MANAGE_ORDERS，不能Tax权全商店扩权。
- 错误：Account DELETE_OWN_ACCOUNT/OUT_OF_SCOPE_USER/OUT_OF_SCOPE_PERMISSION/LEFT_NOT_MANAGEABLE_PERMISSION/权限等沿Base，受限金额不可回显；export authorization不以empty伪装。
- 完成判定：事务删除/撤token后重读不在，历史订单保留；client导航回列表不等于后端已删。字段授权/列表count/error处处同scope。
- 变更与兼容：修复单staff有订单仅取消is_staff路径，与bulk统一，未扩大隐私/导出授权。

### I27 · 重量、金额、媒体、时间与草稿业务事实
- 所属设计单元：BD15、BD01、BD02。
- 提供方：Base Weight/TaxedMoney/OrderEvent时间、ProductMediaCreate/variant APIs、draftOrderComplete/orderLinesCreate等。
- 调用方：FD10（并FD03金额）。
- 目标定义：Base Weight.value/unit、Shop.defaultWeightUnit、媒体上传/同步mediaUrl/oEmbed、Order/OrderEvent DateTime、draft动作/Channel.isActive/Order.canFinalize及problems等适用资格字段；不新增媒体async状态。

- 字段说明：weight编辑把来源unit转提交shop单位，不能裸value改标签；金额用Core精度/税口径；日期保原DateTime客户端统一locale/timezone分组及标签；媒体普通errors按API，不pending/503/proxy/fallback。草稿添加商品/完成要求当前渠道/发布/价格/库存/配送必要配置，gating理由可由server资格及当前事实组成。
- 权限：product/order/channel各实际scope，Core直调仍复核，UI disabled不代授权。
- 错误：ProductMedia普通INVALID/UNSUPPORTED_MEDIA_PROVIDER等沿实际Base enum、Order CHANNEL_INACTIVE/PRODUCT_NOT_PUBLISHED/PRODUCT_UNAVAILABLE_FOR_PURCHASE/INSUFFICIENT_STOCK等，不虚构成功。
- 完成判定：合法weight往返不数量级变化，正常同步媒体/单及批量变体可用；草稿channel切正常恢复并最新事务资格完成，重复完成不重复分配。
- 变更与兼容：主要实现/消费修正，保普通媒体/变体和hasVariants，排除独立生成器及async外链fallback。

## 3. 其他

### 变更归属与完整交付

| 目标变更 | 权威编号 |
| --- | --- |
| Checkout revision/recalculate/selection/errors、delivery expectedVersion | I01、I02 |
| 库存source、allocation输入可省、Channel版本/warehouseOrder | I03、I06 |
| Product.channelAvailability及诊断types | I04 |
| 自动完成状态、delay/cutoff/config描述 | I05、I06 |
| GiftCard余额/details/支付方式enum、交易provider/来源/幂等/错误 | I07、I08、I10、I11 |
| Order/Checkout.paymentSummary全类型及净额描述 | I09 |
| root transaction/transactions、安全scope/filter/分页 | I11 |
| Checkout/GiftCard.RANK及四主体搜索行为 | I12 |
| 当前四query export/inputs/type、旧弃用、专用permissions及文件scope | I13 |
| Shop密码mode/version/CAS、Account policy errors | I15 |
| 安全richtext三错误码及执行前语义 | I17 |
| App必填/新扩展字段/弃用过滤/App版本+extensions更新/错误 | I18 |
| postMessage/目录/manifest/token/webhook附加描述 | I18—I21 |
| EventDelivery状态/payloadState/lastError、异步边界 | I21 |
| Order/Fulfillment配送快照 | I22 |
| metadata bundle/single+bulk原子输入输出/错误 | I23 |
| Federation非空、公开参数校验 | I24 |
| Payment.partial/DigitalContent及旧Shop字段退出，draft兼容migration | I25 |
| 原staff/field/Node/export权限修正 | I26 |
| 草稿gating、单位/媒体/时间消费修正 | I27 |

补充文件：`interfaces/app-boundaries.schema.json` 为manifest、目录、frame schema；`interfaces/app-http.openapi.yaml` 为既有HTTP manifest GET、目录GET、token POST及webhook POST完整操作描述。内部Celery非对外协议，不交proto；OIDC保provider既有授权协议而非新建REST。

### 实际检查与未运行

最终离线检查于2026-10-14执行，验证脚本/报告位于 `/workspace/scratch/validate-design.cjs`、`design-check-report.json`、`schema-boundary-diff.json`，仅为本阶段校验材料，不是产品实现或冻结测试替代。使用本机Dashboard安装的GraphQL16.11.0及AJV8，不访问外部schema。默认Python graphql解析Base描述语法失败，未使用它得出通过结论。

| 实际检查 | 结果与边界 |
| --- | --- |
| 完整SDL parse/buildASTSchema/validateSchema | PASS；Base 1408定义，target 1428定义，新增31、退出11个DigitalContent定义；无未引用类型错误 |
| Base保留和语义diff白名单 | PASS；1348个完整定义及6019个Base字段完全未变，219项字段/枚举/定义边界差异均登记I编号；未变内容由Base原文保留 |
| 前后端拟消费样例 | PASS；`/workspace/scratch/consumer-examples.graphql` 39个query/mutation/subscription，包含配送、配置、诊断、支付、导出、搜索、App、delivery、快照、metadata/Federation及基础兼容；GraphQL validation 0错误。初次样例误将appExtensions connection作列表，已改edges/node后通过；不是全仓库codegen或运行时授权测试 |
| 非目标与非法操作负向断言 | PASS；6个非法操作被拒，并检查无AppProblems/DigitalContent类型、Payment.partial、Page/User RANK、交易高级filter/sortBy及新async media/generator类型；不将SDL断言替代路由/任务实施回归 |
| 文档模板、编号与覆盖 | PASS；FD01—FD10、BD01—BD15、BT01—BT09、I01—I27及R01—R31引用/章节均存在，补充文件引用可解析 |
| App JSON Schema | PASS；37个defs，AJV draft2020-12编译及正负样例/HTTP示例共25次校验，含旧字段拒绝、form字段、nested depth10/11。未测试浏览器origin/source/运行时URL解码或真正sanitize |
| HTTP/OpenAPI补充协议 | PASS（基础结构）；4个HTTP操作，Node YAML及Python safe_load解析，内部/外部协议共77处引用可解析，HTTP示例通过对应JSON Schema；本机无专用OpenAPI全规范validator，未声称完整规范lint通过 |

上述只证明本阶段**设计描述和拟消费样例**一致，不证明Core/Dashboard已支持这些API。未运行runtime Graphene schema导出、Dashboard codegen/全量既有操作验证/typecheck/构建、Jest/pytest/Playwright、应用/数据库迁移、外部支付/OIDC/目录服务与Webhook集成或部署；其结果不作通过承诺。所有子Agent本Stage只读研究已结束，没有跨Stage后台工作。冻结PRD只读，未修改或替换。
