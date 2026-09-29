# 后端技术设计：

版本：golden-v2  
责任：后端技术设计  
依据：Saleor 3.23 剪枝后精简 Golden PRD v2（`../PRD/prd-golden.md`）；`../PRD/prd.md` 仅用于历史追踪

## 1. 方案概述

后端保持 Saleor 的 Django domain model、Celery task、Graphene GraphQL schema 和 migration 分层。变更集中在 checkout/shipping、payment/gift card、channel/warehouse availability、account/auth、app/webhook、order 和 core validation。公开 GraphQL 由 `saleor/graphql/schema.graphql` 生成并作为接口契约输入；migration 必须能从空数据库执行，也必须保留升级数据语义。

已剪枝能力不建立新的后端设计单元：App Problems、Page/User 高级搜索、Transaction 日期/事件 where 与 sorting、外部媒体异步 fallback、Variant Generator UI、独立 metadata dialog UI。对这些功能仍存在的基础模型或共享字段，只保留当前 16 个保留需求需要的合同。

技术基线：配对 artifact 为剪枝 patch；Core target tree 为 `0b4ecb1130bcc42aad5facd1657f088ed0d7b7ac`，Dashboard target tree 为 `8e16e2dc3fa083aceef5bc99b46e73be86573dfe`。Core/Dashboard agent baseline、patch SHA 和组合 tree 见 `../evidence/golden-patch-manifest.json`。本设计只以 `../PRD/prd-golden.md` 的 16 个保留需求为活动输入。

## 2. 需求覆盖

| 需求 | 设计单元 |
| --- | --- |
| R01 | BD01、BD02 |
| R02 | BD03 |
| R03 | BD03 |
| R04 | BD04 |
| R05 | BD05 |
| R06 | BD06 |
| R08 | BD07 |
| R09 | BD08 |
| R10 | BD09 |
| R12 | BD10 |
| R13 | BD11 |
| R14 | BD15 |
| R15 | BD12 |
| R16 | BD13 |
| R17 | BD14 |
| R18 | 复用 BD04、BD05、BD10、BD14 |

## 3. 详细设计

### BD01 · Checkout delivery calculation

- 覆盖需求：R01。
- 代码归属：`saleor/graphql/shipping/mutations/delivery_options_calculate.py`、`saleor/checkout/delivery_context.py`、`saleor/checkout/models.py`、`saleor/graphql/checkout/mutations/checkout_delivery_method_update.py`。
- `deliveryOptionsCalculate(id)` 根据 checkout 地址、行项目、渠道和同步 shipping webhooks 重新计算 `CheckoutDelivery`。返回可选 delivery、当前选择、过期/不可用错误；更新操作再次校验 delivery 的 freshness 和可用性。
- 旧 `shippingMethod`/`availableShippingMethods` 字段继续以 deprecated 形式提供；新客户端使用 `delivery`/`shippingMethods`。计算和选择必须在同一事务边界内更新 checkout delivery 状态。
- 失败不写入部分选择；错误采用 mutation `errors` 列表，错误 code 可被客户端稳定分支处理。

### BD02 · Checkout completion consistency

- 覆盖需求：R01、R09。
- 代码归属：`saleor/checkout/complete_checkout.py`、`saleor/checkout/actions.py`、`saleor/checkout/tasks.py`。
- checkout complete 前重新检查 delivery、支付状态、库存、客户/地址和金额。自动完成和显式完成共用条件检查，避免旁路逻辑。
- delivery 变化使已选项 stale 时返回可重试错误，不能创建半成品订单。

### BD03 · Transaction and gift-card payments

- 覆盖需求：R02、R03、R12、R17。
- 代码归属：`saleor/payment/`、`saleor/giftcard/`、`saleor/graphql/payment/`、`saleor/graphql/giftcard/`、`saleor/order/`。
- Gift card 作为 transaction payment method 参与 initialize/authorize/cancel/charge/refund；校验 active、expiry、currency、balance，重复初始化使用幂等键和现有 transaction item。
- `transactionCreate`、`transactionEventReport` 保留订单/checkout、provider/app 等基础查询与事件合同；不实现已剪枝的 date/event where 或排序参数。
- 订单 capture/refund/mark-as-paid 与 legacy payment 统一计算 authorized、charged、refunded 和 remaining balance，金额校验在服务层完成。

### BD04 · Authentication and shop settings

- 覆盖需求：R04、R16、R18。
- 代码归属：`saleor/account/`、`saleor/core/auth_backend.py`、`saleor/graphql/account/`、`saleor/graphql/shop/mutations/shop_settings_update.py`。
- `Shop.passwordLoginMode` 支持 `ENABLED`、`CUSTOMERS_ONLY`、`DISABLED`；认证后端和 password mutation 使用同一模式判断。OIDC 使用 offline/refresh-token 兼容参数并防止旧密码绕过已关联身份。
- EditorJS 清理位于 `saleor/core/editorjs/`，对未知字段、非法链接、过深嵌套执行 schema validation 和 URL sanitization。

### BD05 · Warehouse-channel stock availability

- 覆盖需求：R05、R10、R18。
- 代码归属：`saleor/warehouse/`、`saleor/channel/models.py`、`saleor/graphql/product/filters/product_helpers.py`、`saleor/checkout/`、`saleor/order/`。
- `Shop.useLegacyShippingZoneStockAvailability` 为兼容开关。关闭时通过直接 warehouse-channel link 计算 availability，忽略地址/旧 shipping-zone 推导；开启时保留旧行为。
- checkout、order、fulfillment、draft order 和 Product 查询调用同一 availability helper；迁移保留已有 channel/warehouse 关系。

### BD06 · Domain search

- 覆盖需求：R06。
- 代码归属：`saleor/{checkout,giftcard,product,order,account,attribute}/search` 与对应 GraphQL filters。
- 保留主体对象的 search vector/loader 和客户、员工、订单、商品、gift card、checkout 搜索。Page/User 高级 relevance、prefix、去重音符、dirty task 和专用索引不进入当前设计。
- search 输入为空、过长或非法时返回稳定校验错误，不改变基础分页合同。

### BD07 · App Extension and manifest

- 覆盖需求：R08。
- 代码归属：`saleor/app/manifest_schema.py`、`saleor/app/manifest_validations.py`、`saleor/app/installation_utils.py`、`saleor/graphql/app/`、`saleor/app/migrations/0033-0037`。
- manifest 的 extension 使用 `mountName`、`targetName`、`settings`；安装/迁移接受缺省可选值但拒绝重复 identifier 和无效权限。旧存储数据通过 migration reshape 到新字段。
- self-hosted extensions catalog 不依赖旧 marketplace URL；权限检查仍在 resolver/service 层执行。

### BD08 · Automatic checkout completion

- 覆盖需求：R09。
- 代码归属：`saleor/checkout/tasks.py`、`saleor/checkout/models.py`、`saleor/channel/models.py`、`saleor/channel/migrations/0024-0027`、`saleor/checkout/migrations/0083-0085`。
- channel 配置 `automaticallyCompleteFullyPaidCheckouts`、delay、cut-off；周期任务筛选 eligible checkout，按 attempt timestamp 和 batch size 调度单 checkout task。
- task 在完成前检查 fully paid、customer/email、billing/shipping address、delivery、variant availability、total > 0 和幂等状态；失败记录 attempt 并可重试，不重复创建订单。

### BD09 · Product availability diagnostic data

- 覆盖需求：R10。
- 代码归属：产品 channel listing、warehouse availability、shipping-zone resolver 和现有 Product GraphQL 查询；Dashboard 通过这些查询组成 Product Doctor。
- 后端只返回可验证的发布、库存、warehouse、shipping-zone、时间配置事实及权限错误，不新增独立持久化诊断状态。
- 不适用的检查（例如 non-shippable product 的 shipping zone）必须返回 skipped/无错误语义，避免误报。

### BD10 · Order totals and transaction actions

- 覆盖需求：R12、R18。
- 代码归属：`saleor/graphql/order/mutations/`、`saleor/graphql/payment/mutations/`、`saleor/order/`、`saleor/payment/`。
- capture 不能超过 authorization，refund 不能超过 captured，mark-as-paid 只在无现有支付记录或合同允许时成功。所有 mutation 返回 typed errors 和刷新后的 transaction/order。
- Gift card transaction 与普通 transaction 使用统一金额汇总，但保留 gift-card-specific event details。

### BD11 · Shipping metadata persistence

- 覆盖需求：R13。
- 代码归属：shipping method/checkout/order/fulfillment models、`saleor/checkout/migrations/`、`saleor/order/migrations/`、metadata webhook serializers。
- 创建订单时复制 shipping metadata snapshot；源 shipping method 后续修改/删除不回写历史订单。基础 metadata 字段和 GraphQL mutation 保留，独立 metadata dialog UI 不属于后端新增合同。

### BD12 · Lazy webhook payloads

- 覆盖需求：R15。
- 代码归属：`saleor/webhook/`、`saleor/graphql/webhook/`、`saleor/webhook/transport/{synchronous,asynchronous}/`、`saleor/graphql/webhook/dataloaders/`。
- 同步 webhook 仅在 subscription query 实际选择字段时解析 payload；订单/draft/fulfillment 异步事件在任务边界构建 payload。promise、circuit breaker、retry 和 payload call-count 保持既有上限。
- 单个 App delivery 失败只影响自身 delivery 状态，不中断无关 webhook。

### BD13 · Input and identity security

- 覆盖需求：R16。
- 代码归属：`saleor/core/editorjs/`、`saleor/core/cleaners/`、`saleor/core/jwt*.py`、`saleor/account/`。
- 所有外部内容先验证结构再清理 URL；OIDC claims 与本地用户关联使用明确的唯一性和密码策略。

### BD14 · GraphQL validation and compatibility cleanup

- 覆盖需求：R17、R18。
- 代码归属：各 domain GraphQL `inputs.py`、`filters.py`、`mutations/`、`schema.py` 及 generated `schema.graphql`。
- 数值、分页、required input、Federation、Attribute、App install、staff delete 和权限输入在入口统一验证。已移除支付插件、数字商品字段仅返回当前弃用/迁移合同，不在新 schema 中恢复。
- 每次 schema 变更必须同步生成 Core schema、Dashboard generated hooks/types，并运行 schema validation。

### BD15 · Dashboard list/filter support contracts

- 覆盖需求：R14、R18
- 代码归属：商品、订单、礼品卡、仓库和分配类 GraphQL filters、pagination、export input 与 permission resolvers。
- 后端接受 Dashboard 当前有效筛选、锁定条件和分页参数，按同一条件执行列表、导出与批量操作；不使用过期缓存条件替代请求输入。
- 分层对象返回稳定 ID、父子关系和游标；重复条件、空输入、越界分页或无权限访问返回稳定结果或 typed error。
- 本单元不规定页面布局，前端状态合并、长文本和导航行为由 FD11、FD15 承接。

## 4. 接口清单

| 接口 | 所属设计单元 | 说明 |
| --- | --- | --- |
| I01 | BD01 | `deliveryOptionsCalculate` |
| I02 | BD01 | `checkoutDeliveryMethodUpdate` |
| I03 | BD03 | `transactionCreate` / `transactionEventReport` |
| I04 | BD03 | Gift-card payment fields and mutations |
| I05 | BD04 | `shopSettingsUpdate` and password/OIDC mutations |
| I06 | BD05 | Channel/warehouse assignment and product availability filters |
| I07 | BD07 | App manifest/install/extension queries and mutations |
| I08 | BD08 | Channel automatic completion settings and task contract |
| I09 | BD10 | `orderCapture`, `orderRefund`, `orderMarkAsPaid` |
| I10 | BD11 | Shipping metadata fields and snapshot behavior |
| I11 | BD12 | Webhook subscription, payload and delivery contracts |
| I12 | BD14 | Validation, deletion and compatibility semantics |
| I13 | BD15 | Dashboard list filters, pagination and export conditions |

### BT01 · Checkout delivery and completion tests

- 覆盖设计单元：BD01、BD02
- 依赖：无
- 验证 delivery 计算、过期选择、完成前重新校验、失败不产生半成品 checkout/order。

### BT02 · Transaction and gift-card tests

- 覆盖设计单元：BD03、BD10
- 依赖：BT01
- 验证礼品卡 transaction 生命周期、幂等、授权/退款边界和订单支付金额汇总。

### BT03 · Authentication and content security tests

- 覆盖设计单元：BD04、BD13
- 依赖：无
- 验证三态密码模式、OIDC 关联、EditorJS 结构/URL 清理和权限错误。

### BT04 · Availability and Product Doctor contract tests

- 覆盖设计单元：BD05、BD09
- 依赖：BT01
- 验证 warehouse-channel availability 在 Product、checkout、order、fulfillment、draft order 中一致，以及不适用诊断返回 skipped。

### BT05 · Domain search tests

- 覆盖设计单元：BD06
- 依赖：无
- 验证主体搜索、分页、权限、索引更新和已删除高级搜索参数不再进入公开合同。

### BT06 · App manifest migration tests

- 覆盖设计单元：BD07
- 依赖：无
- 验证 manifest 缺省字段、重复 identifier、权限校验、旧记录 migration 和 self-hosted catalog。

### BT07 · Automatic checkout completion tests

- 覆盖设计单元：BD08
- 依赖：BT01、BT02、BT04
- 验证 eligibility、调度、失败重试和订单创建幂等。

### BT08 · Shipping metadata persistence tests

- 覆盖设计单元：BD11
- 依赖：BT01
- 验证配送 metadata snapshot、源对象变化不回写和历史 migration。

### BT09 · Webhook payload and delivery tests

- 覆盖设计单元：BD12
- 依赖：BT02、BT07
- 验证 lazy payload、异步 worker、调用次数、retry/circuit breaker 和 delivery 隔离。

### BT10 · GraphQL schema and validation tests

- 覆盖设计单元：BD14
- 依赖：BT01-BT09
- 验证 schema generation、输入/权限校验、deprecated/removed contract 和 generated 文件同步。

### BT11 · Cross-module regression tests

- 覆盖设计单元：BD01-BD15
- 依赖：BT01-BT10
- 验证冻结 F2P/P2P 选择；不得通过扩大 skip、删除断言或测试专用生产 stub 制造通过。

## 6. 其他

- 目标 schema 完整文件见 `target-schema.graphql`，来源为 target Core tree 的 `saleor/saleor/graphql/schema.graphql`。
- migration 只记录需要保存的业务数据合同；纯测试 fixture、依赖和生成工具不作为单独需求。
- 运行期间使用标准 Harbor 的长驻验证容器与 bind mount；代码迭代不要求重建 base/test image。
- 每个 BD 单元至少保留 unit、GraphQL integration、migration（若有）和相关 E2E 断言。当前保留需求（R01-R06、R08-R10、R12-R18）的验证入口是标准包内冻结的 F2P/P2P 选择；R07/R11 只作为历史删除边界回归，不作为新增业务需求。
