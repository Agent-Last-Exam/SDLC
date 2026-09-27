# 接口对齐文档：

版本：golden-v2  
责任：接口契约  
依据：精简 Golden PRD v2（`../PRD/prd-golden.md`）；后端/前端技术设计 golden-v2

## 1. 通用约定

本文只登记当前剪枝后交付需要的公开 GraphQL、事件和持久化行为。完整目标 schema 见 `target-schema.graphql`，来源是 target Core tree 的 `saleor/saleor/graphql/schema.graphql`。以下接口名以目标 schema 为准；字段级生成类型由 Dashboard target tree 生成文件消费。

- 入口：Saleor GraphQL HTTP endpoint；Dashboard 使用 Apollo client，Storefront/App 使用公开 GraphQL。
- 认证：匿名 checkout 查询按现有 token 规则；客户使用 JWT/session；Dashboard 使用 staff JWT/session；App 使用 app token 与 permission。
- 成功：HTTP/GraphQL 请求可成功但 mutation `errors` 非空，因此调用方必须同时检查 transport errors 和 payload `errors`，并以返回对象/状态变化确认完成。
- 错误：参数错误、权限错误、业务条件错误均使用 Saleor typed error code；未知错误不得被转换为成功空列表。
- ID：公开 Node ID 使用 Relay global ID；checkout token、UUID 和 channel slug 按 schema 类型使用，不在客户端互换。
- 并发：涉及金额、库存、delivery 或状态转换的 mutation 在服务层重新读取最新对象并执行幂等检查。
- 兼容：deprecated 字段可在 schema 中继续读取，新的调用方必须使用 replacement 字段；已剪枝能力不得通过隐式 alias 恢复。

## 2. 接口契约

### I01 · deliveryOptionsCalculate

- 所属设计单元：BD01
- 提供方：`saleor/graphql/shipping/mutations/delivery_options_calculate.py`
- 调用方：Storefront、FD01

```graphql
mutation DeliveryOptionsCalculate($id: ID!) {
  deliveryOptionsCalculate(id: $id) {
    delivery { id ... }
    errors { field code message }
  }
}
```

- 字段说明：`delivery` 是当前 checkout 可选 delivery 列表/结果；错误列表可为空。具体字段以 target schema 的 `DeliveryOptionsCalculate` 类型为准。
- 权限：checkout owner/token 或具备相应 staff 权限；无权访问的 checkout 不泄露 delivery 数据。
- 错误：checkout 不存在、地址/商品不完整、shipping app 返回错误或 delivery 过期时返回 typed error。
- 完成判定：返回成功且 checkout 的 delivery options/assigned delivery 与返回结果一致；不得只以 HTTP 200 判定。
- 变更与兼容：新合同使用 `delivery`/`shippingMethods`；旧 `availableShippingMethods` 仅 deprecated 读取。

### I02 · checkoutDeliveryMethodUpdate

- 所属设计单元：BD01、BD02
- 提供方：`saleor/graphql/checkout/mutations/checkout_delivery_method_update.py`
- 调用方：Storefront、FD01
- 输入：checkout token/id 与 `deliveryMethodId`；服务器重新校验 delivery 所属 checkout、stale 状态和可用性。
- 字段说明：返回更新后的 checkout、assigned delivery 和 `errors`；失败时 assigned delivery 保持原值。
- 权限：checkout owner/token、staff 或允许的 app；错误不得改变既有 assigned delivery。
- 错误：checkout 不存在、delivery 不属于 checkout、delivery 过期或不可用时返回字段级 typed error。
- 完成判定：返回更新后的 checkout 和空 errors，并能再次读取相同 assigned delivery；失败保持原状态。
- 变更与兼容：新客户端使用当前 delivery 标识；旧配送字段按 deprecated 兼容规则读取。

### I03 · transactionCreate / transactionEventReport

- 所属设计单元：BD03
- 提供方：`saleor/graphql/payment/mutations/`
- 调用方：FD02、FD03、FD10、支付 App
- 输入必须包含合法 transaction item、action、currency/amount 和必要 event metadata；金额不可为负，事件与 action 枚举必须匹配。
- 字段说明：返回 transaction、event 和 `errors`；没有对应事件时返回空事件列表，不表示请求失败。
- 权限：staff/app 按 payment/transaction permission；客户不能任意写 transaction。
- 错误：currency mismatch、amount over balance、invalid action、metadata validation 和 permission error 使用 typed errors。
- 完成判定：transaction/event 持久化，相关 order/checkout 状态及 webhook 按合同更新；重复请求不生成重复授权。
- 变更与兼容：保留基础 order/provider/app 查询语义，不提供已剪枝的日期、事件 where 或排序参数。

### I04 · Gift-card payment contract

- 所属设计单元：BD03
- 提供方：`saleor/giftcard/`、`saleor/graphql/giftcard/`、payment resolvers
- 调用方：FD02、FD10、Storefront checkout、支付 App
- Gift card 必须 active、未过期、币种一致且余额足够；checkout authorization 可 cancel，order charge 可 refund。
- 字段说明：交易详情返回 payment method、金额、余额和事件；没有事件时返回空列表。
- 权限：checkout owner 可应用自己的 gift card；staff/app 按 gift-card/payment 权限读写。
- 错误：礼品卡不存在、停用、过期、币种不匹配、余额不足或重复请求冲突时返回 typed business error。
- 完成判定：transaction item 与 gift-card event/balance 同步，Dashboard 可读取 payment method details；重试保持幂等。
- 变更与兼容：礼品卡纳入统一 Transaction 合同；普通 payment 读取继续按兼容合同工作。

### I05 · shopSettingsUpdate / password and OIDC

- 所属设计单元：BD04
- 提供方：`saleor/graphql/shop/mutations/shop_settings_update.py`、account auth/OIDC handlers
- 调用方：FD04、Storefront 登录页、Dashboard 登录页
- `passwordLoginMode` 枚举为 `ENABLED`、`CUSTOMERS_ONLY`、`DISABLED`。模式变化立即影响 password login/reset/change；OIDC 授权需要离线/refresh-token 兼容参数。
- 字段说明：返回 shop 配置、认证结果和 `errors`；未授权入口不返回可用于绕过模式的 token 或敏感配置。
- 权限：仅 owner/staff settings permission 修改；认证入口按当前用户身份和模式返回。
- 错误：模式冲突、无权限、密码入口关闭或 OIDC provider 返回错误时返回 typed auth/settings error。
- 完成判定：shop 配置持久化，后续认证请求读取同一值；OIDC 关联用户不被旧密码绕过。
- 变更与兼容：旧客户端读取模式缺省值时按兼容默认值处理；新客户端必须按枚举渲染入口。

### I06 · Channel/warehouse availability

- 所属设计单元：BD05
- 提供方：channel/warehouse/product GraphQL filters
- 调用方：FD05、FD09、checkout/order services
- 当 legacy flag 关闭时，availability 由直接 warehouse-channel link 决定；开启时按旧 shipping-zone/address 规则。
- 字段说明：返回商品/变体可售数量、渠道和仓库关联事实；没有可售库存时返回零或不可售状态。
- 权限：公开 product 查询遵守 channel visibility；管理查询需要 product/channel/warehouse permission。
- 错误：渠道不存在、仓库无权访问或输入组合非法时返回校验/权限错误。
- 完成判定：同一商品、仓库、channel 在 product、checkout、order、fulfillment 入口返回一致可售结果。
- 变更与兼容：legacy flag 打开时保留旧地址/配送区算法；关闭时地址不能绕过直接关联规则。

### I07 · App manifest and extension

- 所属设计单元：BD07
- 提供方：`saleor/app/manifest_schema.py`、`saleor/graphql/app/`
- 调用方：FD07、外部 App
- manifest extension 使用 `mountName`、`targetName`、`settings`；可选字段缺省有稳定默认值，重复 identifier/无效 permission 拒绝。
- 字段说明：返回已安装 extension、mount/target/settings 和 `errors`；缺省 settings 使用稳定默认值。
- 迁移：0033-0037 将旧 mount/target/settings reshape 到新结构；安装和读取同时支持迁移前后持久化记录。
- 权限：安装/更新需要 app 管理权限；扩展读取只返回当前调用方允许的 mount、target 和 settings。
- 错误：manifest 结构、identifier、permission、target 或 migration 数据非法时返回字段级错误。
- 完成判定：安装/更新返回 extension 列表与 typed errors；self-hosted catalog 不依赖旧 marketplace 地址。
- 变更与兼容：旧持久化字段只在 migration/适配层读取，新客户端使用 mountName、targetName、settings。

### I08 · Automatic checkout completion settings/task

- 所属设计单元：BD08
- 提供方：channel GraphQL settings、`saleor/checkout/tasks.py`
- 调用方：FD08、Celery scheduler
- 输入：boolean、delay、cut-off；服务器校验范围与组合。
- 字段说明：配置查询返回开关、delay、cut-off 和适用渠道；任务状态返回 attempt、成功或可重试失败信息。
- 任务 eligibility：fully paid、customer/email、address、delivery、available variants、total > 0、未完成且未重复处理。
- 权限：渠道配置需要 channel/settings permission；任务只处理当前商店可见且满足条件的 checkout。
- 错误：配置范围非法、无权限或 checkout eligibility 不满足时返回 typed validation/business error。
- 完成判定：订单创建或明确记录失败 attempt；失败可重试，不能重复创建订单。配置 mutation 成功不等于 checkout 已自动完成。
- 变更与兼容：旧渠道没有配置时使用关闭或既有默认值，不改变历史手工完成流程。

### I09 · Order payment actions

- 所属设计单元：BD10
- 提供方：`orderCapture`、`orderRefund`、`orderMarkAsPaid` 和 payment transaction actions
- 调用方：FD02、FD10、客服/订单管理员
- 输入金额必须在 authorization/captured/remaining 边界内；mutation 返回 order/transaction 与 errors。
- 字段说明：返回刷新后的订单、交易、authorized/captured/refunded/balance 和 `errors`。
- 权限：staff payment/order permission 或授权 app；无权操作不能泄露可用金额。
- 错误：金额越界、状态不允许、重复请求或权限不足时返回 typed error，原状态不变。
- 完成判定：持久化金额和 transaction event，Dashboard 重新查询后显示新余额；重复提交不重复扣款。
- 变更与兼容：gift-card transaction 与普通 transaction 共用余额计算；legacy payment 读取保持兼容。

### I10 · Shipping metadata snapshot

- 所属设计单元：BD11
- 提供方：checkout/order/shipping models 与 metadata fields
- 调用方：FD16、FD15、checkout/order/fulfillment consumers
- 创建 order 时复制 shipping metadata；源对象变化不追溯修改历史 order/fulfillment。
- 字段说明：读取返回订单创建时快照；历史记录无 metadata 时返回稳定空值。
- 权限：metadata read/write 按对象权限；已剪枝的独立 metadata dialog 不产生额外 endpoint。
- 错误：非法键值、对象不存在或无权限修改时返回 typed metadata error，原值保持不变。
- 完成判定：从订单读取到创建时快照，migration 后历史数据可读，metadata webhook payload 与对象一致。
- 变更与兼容：保留基础字段和 mutation；独立 dialog 路由和专用接口不属于当前合同。

### I11 · Webhook subscription and delivery

- 所属设计单元：BD12
- 提供方：`saleor/webhook/`、`graphql/webhook/`
- 调用方：App、FD12
- sync query 只解析实际选择字段；async order/draft/fulfillment payload 在异步任务中构建。delivery 状态、retry、circuit breaker 和 event type 遵循 schema。
- 字段说明：delivery 返回 event type、状态、retry 次数、错误和 payload 可用状态；异步 payload 尚未生成时返回 pending 语义。
- 权限：MANAGE_APPS/OWNER 或相关 domain permission；payload 遵守 app 可见字段。
- 错误：订阅非法、payload 构建失败或 delivery 超时时返回可重试 webhook error，不伪装为成功 delivery。
- 完成判定：符合条件的订阅收到一次 delivery；单个失败只改变自身状态，retry 按策略执行。
- 变更与兼容：同步事件不再提前构建无关字段；旧订阅继续按 event type 和 payload schema 读取。

### I12 · Validation and compatibility semantics

- 所属设计单元：BD14
- 提供方：各 GraphQL input/filter/mutation
- 调用方：FD03、FD06、FD13、FD14、FD15、外部 API 客户端
- 负数时间、无效 entity、缺失 required、越界分页、无权限 staff delete 和不支持字段均返回明确 validation/permission error。
- 字段说明：错误返回 field、code、message；成功 mutation 返回更新对象，列表接口区分空列表和错误。
- 权限：每个 resolver 按对象、staff、app、税务和导出权限判定，不以 HTTP 200 替代授权结果。
- 错误：输入、权限、业务条件和 deprecated/removed contract 使用可区分的错误 code，不返回静默成功空结果。
- 已移除支付插件、数字商品旧接口、App Problems、Page/User 高级搜索等不属于当前公开合同；请求不得被当作成功空响应。
- 完成判定：schema generation、Dashboard generated hooks/types 和运行时 resolver 对同一合同一致；失败 mutation 不产生部分写入。
- 变更与兼容：deprecated 字段提供明确 replacement；已剪枝能力不通过 alias、隐藏路由或生成文件重新暴露。

### I13 · Dashboard list/filter support

- 所属设计单元：BD15
- 提供方：商品、订单、礼品卡、仓库和分配类 GraphQL filters、pagination、export input 与 permission resolvers
- 调用方：FD11、FD15、Dashboard 列表和批量操作页面
- 输入：当前页面筛选、URL 锁定条件、分页游标、排序和导出条件；服务端以请求中实际条件为准，不读取过期页面缓存。
- 字段说明：列表返回稳定对象 ID、父子层级、游标和当前筛选回显；无结果返回空列表，不与权限错误混淆。
- 权限：按对象、channel、warehouse、staff 和导出权限过滤列表与批量操作。
- 错误：筛选类型错误、越界分页、锁定条件冲突或无权限导出返回 typed validation/permission error。
- 完成判定：列表、导出和批量 mutation 使用同一有效筛选；重新读取页面后结果与服务端条件一致。
- 变更与兼容：新增筛选继续遵循现有 pagination/permission 合同；已剪枝的 Page/User 高级搜索参数不重新暴露。
- generated schema、Dashboard hooks/types 和测试 patch 必须在每次合同改变时同步更新。

## 3. 其他

非目标接口：`AppProblem` 相关类型/queries/mutations；Page/User vector/GIN/prefix/relevance/dirty search；transaction date/event where 与 sorting；外部媒体 pending/503/proxy fallback；Variant Generator UI/task API；独立 metadata dialog 路由/专用接口。普通 Page/User 搜索、同步媒体、普通 variant create 和 Core metadata snapshot 仍按现有合同工作。

交付与验证：使用配对剪枝 patch 的冻结 F2P/P2P 测试选择验证契约，结果为 F2P `5365/5365`、P2P `15013/15013`、reward `1`。验证顺序为 schema generation → migration → Core GraphQL/unit → Dashboard generated type/build/unit → E2E；完整结果摘要见 `../evidence/verification-summary.md`。
