# 后端技术设计：Saleor Core 3.22 → 3.23 协调升级（后端部分）

版本：v1
责任：后端技术设计
依据：PRD v1，artifacts/sprint1/prd/prd.md
修订：首次交付

## 1. 方案概述

### 1.1 关键事实核查结论（设计前提）

在形成设计前，对两个仓库基线做了源码核查，结论直接决定方案形态：

1. **core 基线（`c864e66`）的功能代码已具备 3.23 目标行为**。`saleor/graphql/schema.graphql`（35,185 行）已包含 PRD R04–R09 要求的全部契约：`orders`/`draftOrders`/`pages`/`customers`/`attributes`/`productVariants`/`attribute.choices` 的 `where`+`search` 参数与废弃 `filter`、`SINGLE_REFERENCE`、`referenceTypes`、`AssignedAttribute` 接口族、`RefundSettings`/`refundSettingsUpdate`/`refundReasonReferenceClear`、`TransactionItem.paymentMethodDetails`（接口 + `CardPaymentMethodDetails`/`OtherPaymentMethodDetails`）、`Money.fractionalAmount`/`fractionDigits`、`AppExtensionMountEnum` 全部新挂载点、`AppExtensionTargetEnum.NEW_TAB/WIDGET`。对应实现代码齐备：`saleor/graphql/order/filters.py`（`OrderWhereInput` 第 974 行、`DraftOrderWhereInput` 第 1084 行）、`saleor/graphql/page/filters.py`（`PageWhereInput` 第 756 行）、`saleor/graphql/payment/types.py`（`PaymentMethodDetails` 接口第 467 行）、`saleor/site/models.py`（`refund_reason_reference_type` 第 99 行）、`saleor/order/models.py`（`OrderGrantedRefund.reason_reference` 第 925 行）、`saleor/app/types.py`（`NEW_TAB`/`WIDGET` 与全部挂载点枚举）、`saleor/app/manifest_validations.py`（目标/挂载点组合校验）。
2. **数据库迁移已就位**：`saleor/order/migrations/0217_ordergrantedrefund_reason_reference.py`、`saleor/site/migrations/0042_sitesettings_refund_reason_reference_type.py` 等 3.23 迁移已存在于迁移链末端，无需新增迁移（实施阶段仍须按 BD03 验证）。
3. **版本声明未升级**：`saleor/__init__.py:6` 为 `__version__ = "3.22.0"`，`pyproject.toml` 为 `version = "3.22.0"`；`schema_version`（第 24 行）由 `__version__` 推导为 `"3.22"`。这是 core 仓库唯一确定的缺失项。
4. **GraphQL 契约存在一处前后端不一致**：Dashboard 基线的 `schema.graphql` 与 core 的 `saleor/graphql/schema.graphql` 类型集合相同（各 1405 个命名类型），唯一实质差异是 Dashboard 版 schema 在 `AppExtension` 与 `AppManifestExtension` 上多了 `mountName: String!`、`targetName: String!`、`settings: JSON!` 三个字段，并把 `mount`/`target`/`options` 及 `AppExtensionOptionsWidget`/`AppExtensionOptionsNewTab`/`WidgetTargetOptions`/`NewTabTargetOptions` 标记为 deprecated。Dashboard 生产代码（`src/extensions/queries.ts` 的 `extensionList` 查询等）**已经在消费 `mountName`/`targetName`/`settings`**，而 core 端 `saleor/app/models.py` 的 `AppExtension` 模型尚无对应支撑。该差异即 Dashboard 3.22.9 CHANGELOG 所述 "Switched to the new AppExtension fields introduced in 3.22 patch (mount -> mountName, target -> targetName, options -> settings)" 的后端补丁，core 基线未包含，必须在本次迁移中补齐，否则 Dashboard 既有查询直接报错（属于 R11 回归破坏）。

### 1.2 整体方案

core 仓库（`/workspace/repos/saleor`）的改动收敛为两类：

- **BD01**：版本声明升级至 3.23.0（`saleor/__init__.py`、`pyproject.toml`），`schema_version` 自动推导为 `3.23`。
- **BD06**：补齐 AppExtension 契约——`AppExtension`/`AppManifestExtension` 类型新增 `mountName`/`targetName`/`settings` 字段并废弃 `mount`/`target`/`options`，使服务端 schema 与 `target-schema.graphql`（已与 Dashboard 消费面核对一致）完全吻合。`settings` 为 `JSON!`，由既有存储（`mount`、`target`、`http_target_method` 列）在 resolver 层推导，**不新增数据库列、不改变清单（manifest）安装校验行为**；`AppManifestExtension` 为安装流程中的 manifest 解析结果类型，同型补齐。

其余 PRD 后端需求（R03–R05、R07、R08、R10–R12）经核查在基线中已满足或属于验证性工作，分别由 BD02–BD05、BD07、BD08 以"确认 + 验证 + 守护"方式承接，不引入行为性改动。Dashboard 仓库侧无后端职责，其版本/schema/生成产物对齐见 frontend-design.md（FD01）。

现有行为链依据：GraphQL 服务装配在 `saleor/graphql/api.py`（schema 由 `saleor/graphql/*/schema.py` 聚合）；`saleor/graphql/schema.graphql` 是 codegen 产物（`saleor/graphql/management` / CI 生成），任何 graphene 层改动后须同步重生成该文件。

## 2. 需求覆盖

| 需求 | 设计单元 |
| --- | --- |
| R01 | BD01 |
| R03 | BD02 |
| R04 | BD03 |
| R05 | BD04 |
| R06 | BD05 |
| R07 | BD07 |
| R08 | BD08 |
| R09 | BD06 |
| R10 | BD09 |
| R11 | BD10 |
| R12 | BD11 |

无对外接口变更的需求说明：R02（Dashboard 版本/schema/生成产物对齐）由前端承接（frontend-design.md FD01），后端无设计单元；R04/R05/R06/R07/R08/R10/R11/R12 在 core 基线中已具备实现，后端承接方式为确认现状、补齐 schema 生成物与回归验证，不改变既有契约。

## 3. 详细设计

### BD01 · 版本声明升级至 3.23.0
- 覆盖需求：R01
- 设计说明：
  - 落点 1：`saleor/__init__.py:6`，`__version__ = "3.22.0"` → `"3.23.0"`。第 23–24 行 `schema_version = f"{_major}.{_minor}"` 由 split 推导，自动变为 `"3.23"`，无需改动。该值被 GraphQL schema 描述（`saleor/graphql/core/__init__.py` 或 api 装配处的版本标记）、webhook payload 等消费。
  - 落点 2：`pyproject.toml:7`，`version = "3.22.0"` → `"3.23.0"`。依赖约束（环境补丁已调整 `django[bcrypt]~=5.2.13`、`pillow>=12.1.1,<13`、`authlib>=1.6.9`、`cryptography<47` 等）不动，`uv.lock` 不重算。
  - 语义：仅声明性变更，不改变任何运行时行为；与 Dashboard `package.json` 版本升级（FD01）保持同号（3.23.0）。
  - 验证方法：`python -c "import saleor; print(saleor.__version__, saleor.schema_version)"` 输出 `3.23.0 3.23`；GraphQL 服务启动后内省可用（AC-01-1/AC-01-2）。

### BD02 · 数据库迁移链确认与验证
- 覆盖需求：R03
- 设计说明：
  - 核查结论：3.23 目标行为涉及的模型变更迁移均已存在——`saleor/order/migrations/0217_ordergrantedrefund_reason_reference.py`（`OrderGrantedRefund.reason_reference` FK）、`saleor/site/migrations/0042_sitesettings_refund_reason_reference_type.py`（`SiteSettings.refund_reason_reference_type` FK）、`saleor/app/migrations/0032_appextension_http_target_method_and_more.py`（扩展 http method 与新挂载点/target 选择值扩展）。`payment` 应用内 `paymentMethodDetails` 存储所需的迁移同样已在链上（`saleor/payment/migrations/` 末端，实施时按 `showmigrations` 复核连续性）。
  - BD06 不新增模型列（`settings` 由既有列推导），故**本轮不产生新迁移**。
  - 验证方法：在本地数据库（含预置 `replica_user.sql` 数据）上执行 `manage.py migrate`，确认迁移链从新库到末端一次通过、无 `InconsistentMigrationHistory`；抽查 3.22 存量订单/页面/属性数据在 3.23 代码下可读写（AC-03-1～AC-03-3）。若 `showmigrations` 发现断链或缺失（理论外情况），按断点补齐迁移并在此记录修订。

### BD03 · 订单 orders `where`/`search` 契约确认
- 覆盖需求：R04
- 设计说明：
  - 核查结论：`saleor/graphql/order/schema.py` 的 `orders` 已声明 `where=OrderWhereInput`、`search=String`，`filter` 标记 `DEPRECATED_IN_3X_INPUT + Use \`where\` and \`search\``；`saleor/graphql/order/filters.py:974` 的 `OrderWhereInput` 覆盖 PRD R04 列出的全部字段；`saleor/graphql/order/sorters.py:9` 的 `OrderSortField` 含 `STATUS`（第 18 行）；全文搜索与权重实现位于 `saleor/order/search.py`（A–D 权重、websearch、索引行数限制 settings）。
  - 本设计单元**无代码改动**，承接方式为：(a) 在 `target-schema.graphql` 中冻结该契约（I01）；(b) 以既有测试集（`saleor/graphql/order/tests/` 下 filter/search 相关用例）做回归验证；(c) 守护 BD06 的改动不得触碰 order 域。
  - 验证方法：运行 order 过滤/搜索相关单测；手工内省确认 schema 与 target-schema 一致（AC-04-1～AC-04-4）。

### BD04 · draftOrders 与 pages(Models) `where`/`search` 契约确认
- 覆盖需求：R05
- 设计说明：
  - 核查结论：`saleor/graphql/order/filters.py:1084` 的 `DraftOrderWhereInput` 覆盖 PRD R05 列出的草稿订单字段，且不含 `status`/`checkout_token`/`checkout_id`/`is_gift_card_*`/`has_invoices`/`invoices`/`has_fulfillments`/`fulfillments`（schema 级不存在即 AC-05-1 的拒绝语义）；`saleor/graphql/page/filters.py:756` 的 `PageWhereInput` 与 `saleor/graphql/page/schema.py:60-66`（`filter` 废弃 + `where`/`search` 参数）齐备，属性过滤（数值/布尔/日期/引用、`contains_all`/`contains_any`）在 page filters 中实现。
  - 无代码改动；验证方式同 BD03（page/draftOrder 相关测试 + schema 对比）。

### BD05 · 属性体系契约确认（SINGLE_REFERENCE / referenceTypes / AssignedAttribute / choices）
- 覆盖需求：R06
- 设计说明：
  - 核查结论：`AttributeInputTypeEnum` 含 `SINGLE_REFERENCE`（schema 第 6105 行）；`Attribute.referenceTypes` 字段与 `attributeCreate`/`attributeUpdate`/`attributeBulkCreate`/`attributeBulkUpdate` 的 `referenceTypes: [ID!]` 输入均已存在（schema 第 5955、29071、29188 行）；`AssignedAttribute` 接口族（`AssignedNumericAttribute`、`AssignedTextAttribute`、`AssignedSingleChoiceAttribute` 等，schema 34902 行起）与 `Page`/`Product`/`ProductVariant` 的 `assignedAttribute`/`assignedAttributes` 字段齐备，旧 `attribute`/`attributes` 标记 deprecated 但保留；`Attribute.choices`（`saleor/graphql/attribute/types.py:300`）支持 `filter`（废弃）+ `where`+`search`；`AttributeEntityTypeEnum` 含 `CATEGORY`/`COLLECTION`。
  - 无代码改动；验证方式同 BD03。

### BD06 · AppExtension/AppManifestExtension 契约补齐（mountName/targetName/settings）
- 覆盖需求：R09（同时消除 R11 回归风险：Dashboard 既有 `extensionList` 查询消费新字段）
- 设计说明：
  - **模块落点**：
    - `saleor/graphql/app/types.py`：`AppExtension`（ModelObjectType）新增三个字段——
      - `mountName = graphene.String(required=True)`，resolver 返回 `root.mount`（字符串原值，如 `"order_details_widgets"`）；
      - `targetName = graphene.String(required=True)`，resolver 返回 `root.target`；
      - `settings = GenericScalar(required=True)`（schema 中标量名为 `JSON`，映射 `GenericScalar`），resolver 由既有列推导：
        - `target == NEW_TAB` → `{"newTabTarget": {"method": <http_target_method 或默认 "GET">}}`；
        - `target == WIDGET` → `{"widgetTarget": {"method": <http_target_method 或默认 "GET">}}`；
        - `POPUP`/`APP_PAGE` → `{}`。
      - 既有 `mount`/`target` 字段 resolver 不变，仅在其 `description` 中标注废弃（`DEPRECATED_IN_3X_FIELD`，渲染为 `@deprecated(reason: "Use \`mountName\` instead.")` / `"Use \`targetName\` instead."`）；`options` 字段保留原 resolver（返回 `AppExtensionOptionsWidget`/`AppExtensionOptionsNewTab` union），标注 `@deprecated(reason: "Use \`settings\` field instead.")`。
    - `saleor/graphql/app/types.py` 或 manifest 相关类型定义处：`AppManifestExtension`（安装清单解析输出类型）同型新增 `mountName`/`targetName`（resolver 取 manifest dict 的 `mount`/`target` 原值）与 `settings: JSON!`（取 manifest `options` 原样，缺省 `{}`），`mount`/`target` 同步标注废弃。
    - `saleor/graphql/app/types.py` 中 `AppExtensionOptionsWidget.widgetTarget`、`WidgetTargetOptions.method`、`AppExtensionOptionsNewTab.newTabTarget`、`NewTabTargetOptions.method` 四个字段的描述标注 `@deprecated(reason: "Use \`settings\` field directly.")`。
    - `saleor/graphql/schema.graphql`：以上改动后按既有生成流程重生成，结果必须**与 `target-schema.graphql` 字节一致**（该文件已与 Dashboard 消费面核对，见 interface-contract.md I06）。
  - **业务逻辑与数据模型**：不新增/变更数据库列（`mount`、`target`、`http_target_method` 为既有存储）；`settings` 为只读派生视图，写入路径仍走 manifest 安装/`appExtension` 既有流程（`saleor/app/manifest_validations.py` 的校验不变）。事务/异步语义不变。
  - **权限**：沿用 `AppExtension` 既有权限规则（staff 与拥有该 app/extension 的调用方可见），新字段不改变可见性。
  - **失败语义**：resolver 纯函数无 I/O，无新失败模式；`http_target_method` 为 NULL 时按 `"GET"` 回退（与既有 `options` resolver 的语义一致，实施时对齐 `saleor/graphql/app/types.py` 现有 `resolve_options` 实现）。
  - **兼容**：`mount`/`target`/`options` 仅废弃不移除，旧消费者（含 3.22 Dashboard 旧查询）继续可用；`target-schema.graphql` 与 Dashboard 基线 `schema.graphql` 完全一致，Dashboard 无需改任何查询即可同时工作。
  - 验证方法：内省对比生成 schema 与 target-schema 一致；`appExtensions`/`appInstallations` 查询断言 `mountName`/`targetName`/`settings` 返回值；旧字段查询回归通过（AC-09-3、AC-09-4）。

### BD07 · 退款设置与结构化退款原因确认
- 覆盖需求：R07
- 设计说明：
  - 核查结论：`saleor/site/models.py:99` `refund_reason_reference_type` FK 与迁移 0042 已就位；`saleor/order/models.py:925` `OrderGrantedRefund.reason_reference` 与迁移 0217 已就位；`saleor/graphql/shop/schema.py` 暴露 `refundSettings`，`saleor/graphql/shop/mutations/` 含 `refundSettingsUpdate`、`refundReasonReferenceTypeClear`（对应 schema 的 `refundSettingsUpdate`、`refundReasonReferenceClear`）；`orderGrantRefundCreate`/`orderGrantRefundUpdate`/`orderRefund`/`fulfillmentRefundProducts`/`transactionRequestAction` 五个 mutation 的 `reasonReference` 输入与 staff/App 差异化校验（staff 必填、App 豁免、清除后传入即报错）在 `saleor/graphql/order/mutations/` 与 `saleor/payment` 侧实现中已存在（`saleor/graphql/order/mutations/order_grant_refund_utils.py` 等）。
  - 无代码改动；承接方式为契约冻结（I04）与回归验证（AC-07-1～AC-07-4）。

### BD08 · TransactionItem.paymentMethodDetails 与 Money 分数字段确认
- 覆盖需求：R08
- 设计说明：
  - 核查结论：`saleor/graphql/payment/types.py:467` `PaymentMethodDetails` 接口与 `:486` `:531` 两个实现类型、`TransactionItem.resolve_payment_method_details`（:646）齐备；`transactionCreate`/`transactionUpdate`/`transactionEventReport` 的 `paymentMethodDetails` 输入（schema 16519/23591/23599 行）与同步 webhook（`TRANSACTION_INITIALIZE_SESSION`/`TRANSACTION_PROCESS_SESSION`）响应写入路径（`saleor/payment/` 与 `saleor/webhook/` 交易处理代码）已存在；`Money` 类型 `fractionalAmount`/`fractionDigits`（schema 3820/3823 行）已实现；`OrderWhereInput` 的 `transactions: PaymentMethodDetailsFilterInput` 过滤（schema 13574 行）已存在。
  - 无代码改动；承接方式为契约冻结（I05）与回归验证（AC-08-1～AC-08-4）。

### BD09 · 构建与依赖声明守护
- 覆盖需求：R10
- 设计说明：
  - core 侧守护项：`pyproject.toml` 依赖约束与 `uv.lock`（环境补丁已对齐）不因本次改动漂移——BD01 仅改 `version` 字段；`setup.cfg` pytest 配置（`--allow-hosts 127.0.0.1,::1,cache`、`--dist loadgroup` 等）不回退。
  - 若实施中确需新增依赖（预期无），只改 `pyproject.toml` 约束并同步 `uv.lock`（离线环境使用已安装版本），不引入网络安装需求。
  - 验证方法：`python -m pytest --collect-only` 可收集；`uv lock --check`（或等价静态比对）声明与锁一致（AC-10-1～AC-10-3）。

### BD10 · 回归行为保持（无测试桩）
- 覆盖需求：R11
- 设计说明：
  - 全部改动限定在 BD01（版本声明）与 BD06（AppExtension 新增字段 + 废弃标注），二者均为纯增量：`mount`/`target`/`options` 保留，`filter` 参数、`attribute`/`attributes`、`Transaction.gatewayResponse`、废弃插件均不触碰。
  - 实施约束（写入工程任务）：新增实现必须为生产代码路径；禁止 `if settings.TESTING` 类环境特判与硬编码假数据；`settings` resolver 的真实推导逻辑对所有环境一致。
  - 验证方法：官方 P2P 套件在改动后全绿；`saleor/graphql/app/tests/` 既有用例不因字段新增而失败（AC-11-1～AC-11-3）。

### BD11 · 交付约束执行
- 覆盖需求：R12
- 设计说明：
  - 交付形态：core 仓库工作树内普通源码编辑，最终导出相对基线 `c864e66` 的 diff；不触碰评估测试、fixtures、verifier、评分配置；全程离线。
  - 本 sprint 改动面小，预期 diff 仅含：`saleor/__init__.py`、`pyproject.toml`、`saleor/graphql/app/types.py`（或 manifest 类型所在文件）、`saleor/graphql/schema.graphql`（重生成）。
  - 验证方法：`/opt/runtime/run-suite.sh <attempt> core-unit core-e2e` 本地执行确认 F2P/P2P 状态；`git diff --stat` 核对改动面（AC-12-1、AC-12-2）。

## 4. 接口清单

完整契约集中写在 interface-contract.md；目标 SDL 见 target-schema.graphql。

| 接口 | 所属设计单元 | 说明 |
| --- | --- | --- |
| I01 | BD03 | `orders` 查询 `where`/`search`/按状态排序契约（现状冻结） |
| I02 | BD04 | `draftOrders` 与 `pages` 查询 `where`/`search` 契约（现状冻结） |
| I03 | BD05 | 属性体系契约：`SINGLE_REFERENCE`、`referenceTypes`、`AssignedAttribute`、`choices` 查询（现状冻结） |
| I04 | BD07 | `RefundSettings` 查询与 `refundSettingsUpdate`/`refundReasonReferenceClear` 及五个退款 mutation 的 `reasonReference` 规则（现状冻结） |
| I05 | BD08 | `TransactionItem.paymentMethodDetails`、交易 mutation/webhook 写入路径、`Money.fractionalAmount`/`fractionDigits`（现状冻结） |
| I06 | BD06 | `AppExtension`/`AppManifestExtension` 新增 `mountName`/`targetName`/`settings` 并废弃 `mount`/`target`/`options`（本轮唯一 schema 变更） |
| I07 | BD01 | 版本声明（`saleor.__version__`/`schema_version`，非 GraphQL 接口，无 I 契约条目，见 backend 设计本文） |

## 5. 工程任务与依赖

### BT01 · 版本声明升级
- 覆盖设计单元：BD01
- 依赖：无
- 工作与验证：修改 `saleor/__init__.py:6` 与 `pyproject.toml:7`；`python -c "import saleor; assert saleor.__version__=='3.23.0' and saleor.schema_version=='3.23'"`；启动服务内省可用。

### BT02 · AppExtension/AppManifestExtension 字段补齐与 schema 重生成
- 覆盖设计单元：BD06
- 依赖：无（可与 BT01 并行）
- 工作与验证：
  - 前置：阅读 `saleor/graphql/app/types.py` 现有 `AppExtension`/`AppManifestExtension` 与 `resolve_options` 实现，复用其 method 回退语义。
  - 变更：`AppExtension` 增 `mountName`/`targetName`/`settings` resolver；`AppManifestExtension` 增同名字段；`mount`/`target`/`options` 及 4 个 options 子字段标注废弃；重生成 `saleor/graphql/schema.graphql`。
  - 完成依据：生成文件与 `target-schema.graphql` 一致（diff 为空）；`saleor/graphql/app/tests/` 新增/调整断言的用例通过；`saleor/graphql/app/tests/` 全量通过。

### BT03 · 迁移链与数据验证
- 覆盖设计单元：BD02
- 依赖：无
- 工作与验证：`manage.py showmigrations` 检查链连续；本地数据库（含预置数据）`migrate` 全量执行成功；抽查订单/页面/属性读写。

### BT04 · 契约域回归验证（orders/draftOrders/pages/attributes/refunds/transactions）
- 覆盖设计单元：BD03、BD04、BD05、BD07、BD08
- 依赖：BT02（schema 重生成后做全量内省对比）
- 工作与验证：运行各域既有单测；内省对比 `saleor/graphql/schema.graphql` 与 `target-schema.graphql`；确认无契约漂移。

### BT05 · 工程约束与套件验证
- 覆盖设计单元：BD09、BD10、BD11
- 依赖：BT01、BT02
- 工作与验证：`pytest --collect-only` 正常；`run-suite.sh` 执行 `core-unit`、`core-e2e`；`git diff --stat` 核对改动面仅限预期文件；确认无评估资产被改动。

## 6. 其他

- **运行约束**：全程离线；`schema.graphql` 重生成使用仓库内既有命令（不联网）；评估数据库为本地预置数据。
- **风险与缓解**：
  - 风险 1：`settings` 的 JSON 结构与 Dashboard 期望不符。缓解：target-schema 已与 Dashboard 基线 `schema.graphql` 对齐，且 Dashboard 端 `src/extensions/` 已有对 `settings` 的消费代码（`extensionList` 查询），实施时以该查询的返回结构为准做联调断言。
  - 风险 2：重生成 `schema.graphql` 时出现与本设计无关的 diff（本地 graphene 版本差异）。缓解：以 target-schema 为基准逆向核对，任何额外 diff 都需定位到具体 graphene 声明并修正，而非手工编辑生成文件。
  - 风险 3：BD06 的 `GenericScalar`（`JSON`）在 codegen/前端类型映射为 `any`（dashboard `types.generated.ts` 第 42 行 `JSON: any`），与现状一致，无类型破坏。
- **待确认事项**：无阻塞项。如官方 F2P 测试揭示了基线未覆盖的 3.23 行为差异（PRD 第 5 节假设情形），在修复阶段以测试期望为准修订本设计，编号沿用、新增顺延。
