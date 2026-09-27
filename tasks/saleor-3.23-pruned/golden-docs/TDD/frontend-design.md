# 前端技术设计：

版本：golden-v2  
责任：前端技术设计  
依据：Saleor 3.23 剪枝后精简 Golden PRD v2（`../PRD/prd-golden.md`）；`../PRD/prd.md` 仅用于历史追踪

## 1. 方案概述

Dashboard 采用现有 React、Apollo、React Hook Form 和页面路由结构。订单/交易、商品可售性、渠道/仓库、App 扩展、认证设置和列表筛选沿用现有模块，新增行为通过 GraphQL query/mutation 和缓存更新实现。页面应显示 loading、permission、empty、validation、stale 和 retry 状态，不以删除后端字段来规避异常。

技术基线：Dashboard target tree 为 `38d10cfc303166d7ea2d3a93d3991bff151b5eeb`，实现参考为配对剪枝 Dashboard patch；完整 SHA 见 `../evidence/golden-patch-manifest.json`。GraphQL 操作使用 target schema 生成的 hooks/types，不直接依赖被剪枝的 App Problems、Variant Generator、Page/User 高级搜索或独立 metadata dialog 路由。

## 2. 需求覆盖

| 需求 | 设计单元 |
| --- | --- |
| R01 | FD01 |
| R02 | FD02 |
| R03 | FD03 |
| R04 | FD04 |
| R05 | FD05 |
| R06 | FD06 |
| R08 | FD07 |
| R09 | FD08 |
| R10 | FD09 |
| R12 | FD10 |
| R13 | FD16 |
| R14 | FD11 |
| R15 | FD12（消费事件结果，不改变 transport） |
| R16 | FD13 |
| R17 | FD14 |
| R18 | FD15 |

## 3. 详细设计

### FD01 · Checkout delivery selector

- 覆盖需求：R01。
- 代码归属：checkout/shipping 页面、GraphQL operation 和 generated types。
- 页面请求 `deliveryOptionsCalculate` 展示可选 delivery、当前项、过期和不可用提示；选择后调用 `checkoutDeliveryMethodUpdate`，成功后刷新 checkout totals。旧字段仅用于兼容旧客户端数据，不作为新 UI 的主入口。

### FD02 · Gift-card transaction presentation

- 覆盖需求：R02、R12。
- 代码归属：`src/orders/components/OrderTransactionGiftCard/`、`OrderUsedGiftCards/`、giftCards 页面。
- 订单交易卡显示 gift-card payment details、余额/事件和可用 action；操作成功后以 mutation 返回对象更新 Apollo cache，错误按 typed code 显示。

### FD03 · Transaction list and filters

- 覆盖需求：R03。
- 保留订单、provider/app 和主体搜索过滤；不渲染已删除的 transaction date/event where、sorting 控件。服务器返回不支持参数时显示通用 validation error，避免静默伪成功。

### FD04 · Authentication settings

- 覆盖需求：R04、R16。
- 在 shop settings 中以 enum 控件编辑密码登录模式，展示 CUSTOMERS_ONLY 对 staff 的影响；OIDC/密码入口根据当前配置渲染并显示 loading/permission/error 状态。

### FD05 · Channel and warehouse availability

- 覆盖需求：R05、R18。
- 渠道设置页维护 warehouse assignment 和 legacy stock availability 开关；商品/订单页面使用同一 availability 数据，切换后清理相关查询缓存，避免不同页面出现冲突结果。

### FD06 ·主体搜索

- 覆盖需求：R06。
- Checkout、Gift Card、Product、Order、Customer/Staff 列表保留搜索输入、分页和空状态。Page/User 专用 relevance/prefix/dedup 控件和入口不再注册；基础 Page/User 列表仍可用。

### FD07 · App extension UI

- 覆盖需求：R08。
- `src/extensions/` 使用 `mountName`、`targetName` 和 `settings` 渲染扩展；安装、popup/form response 处理缺省可选值、重复 identifier、权限错误和 self-hosted catalog。迁移期间旧字段只在适配层读取，不向新表单传播。

### FD08 · Automatic checkout completion settings

- 覆盖需求：R09。
- 渠道设置页面提供开关、delay 和 cut-off 控件；保存前校验范围与组合。页面展示最后保存值和 mutation errors，任务执行结果通过 checkout/order 状态可观察，不在前端模拟完成。

### FD09 · Product Doctor

- 覆盖需求：R10。
- 代码归属：`src/products/components/ProductDoctor/`。
- 商品编辑页按 channel 展示 availability cards，支持 channel/currency 过滤、分页和 error/warning 计数。无配送商品跳过 shipping-zone 检查；权限错误、编辑中刷新和空数据均有明确状态。

### FD10 · Order totals and payment actions

- 覆盖需求：R12。
- 代码归属：`src/orders/components/OrderTransaction*`、`OrderPayment*`、`OrderRefund*`、`OrderMarkAsPaidDialog`。
- 金额摘要区分 authorized/captured/refunded/balance；capture 金额输入不超过授权，refund 不超过可退，mark-as-paid 仅在合法状态显示。提交期间禁用重复操作，成功后刷新 order/transactions。

### FD11 · Dashboard list/filter/navigation fixes

- 覆盖需求：R14。
- 过滤器使用 URL state 与 page-local locked filters 合并，锁定条件不会被普通筛选覆盖；warehouse/category 层级去重，导出/批量操作携带当前筛选；长搜索词使用稳定宽度和截断提示。

### FD12 · Webhook-facing views

- 覆盖需求：R15。
- Webhook 管理页展示 sync/async event 类型、circuit-breaker 和 delivery status；前端不假设 payload 已同步存在，使用 loading/empty/retry 状态并允许单条 delivery 重试。

### FD13 · Content and identity safety UX

- 覆盖需求：R16。
- EditorJS 表单显示字段、链接和深度校验错误；OIDC 登录/绑定页面说明需要的授权状态，不把 refresh token 暴露给浏览器持久化存储。

### FD14 · GraphQL validation compatibility

- 覆盖需求：R17。
- generated hooks/types 与 target schema 同步更新；API 错误映射到字段级/表单级提示。已删除字段不再生成 query、fragment、menu 或路由；deprecated 字段只保留兼容读取所需代码。

### FD15 · Configuration and display consistency

- 覆盖需求：R18。
- 渠道加载、重量、媒体、折扣、日期分组和 draft-order action 使用统一 loading/data guards；停用 channel 或无可售商品时禁用不适用动作并说明原因。

### FD16 · Shipping metadata snapshot and basic editing

- 覆盖需求：R13
- 代码归属：订单详情、履约详情、checkout/draft order metadata 展示与基础编辑组件，以及对应 generated operations。
- 页面只提供当前产品范围内的 metadata 读取和基础编辑；订单创建后展示配送 metadata 快照，不因源配送方式后续变化而回写历史订单。
- 独立 metadata dialog、专用路由、菜单和不可达入口不注册；权限错误、非法值和保存失败保留原展示值并显示可重试错误。

## 4. 依赖与联调

| 接口 | 消费方设计单元 | 对应需求 | 开发依赖 |
| --- | --- | --- | --- |
| I01-I02 | FD01 | R01 | 需等待后端 schema |
| I03-I04 | FD02、FD03、FD10 | R02、R03、R12 | 需等待后端 transaction contract |
| I05 | FD04 | R04、R16 | 可与后端并行，schema 冻结后联调 |
| I06 | FD05、FD09 | R05、R10 | 需等待 availability query |
| I07 | FD07 | R08 | 需等待 manifest contract |
| I08 | FD08 | R09 | 需等待 channel fields |
| I09 | FD10 | R12 | 需等待 action validation |
| I10 | FD16、FD15 | R13、R18 | 需等待 metadata snapshot contract |
| I11 | FD12 | R15 | 可先做状态组件，schema 后联调 |
| I12 | FD06、FD13、FD14、FD15 | R06、R16-R18 | 需等待 generated schema |
| I13 | FD11、FD15 | R14、R18 | 需等待 filter/export contract |

联调顺序：先冻结 schema 与 generated types，再接入后端 mutation；随后验证 Apollo cache、权限和错误映射；最后执行 Dashboard unit/E2E 与 F2P/P2P 选择。

## 5. 其他

- 删除功能的前端清理包括路由、menu、query、generated hook、专用组件、文案和测试；不能只隐藏按钮而留下可达入口。
- 不为历史剪枝边界 R07、R11 或 R13 的已删除 UI 设计新的替代页面；保留的同步媒体、普通 variant 和基础 metadata 操作沿用现有页面。R13 的基础 metadata 快照/编辑仍属于当前精简 PRD，删除的只是独立 dialog 路由和专用入口。
