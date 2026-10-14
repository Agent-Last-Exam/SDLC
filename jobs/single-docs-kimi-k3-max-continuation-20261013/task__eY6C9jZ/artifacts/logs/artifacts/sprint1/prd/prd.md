# PRD：Saleor Core 与 Saleor Dashboard 3.22 → 3.23 协调升级

版本：v1
责任：产品
状态：需求范围与验收条件已定义
输入：instruction.md；现有项目代码
修订：首次交付

## 1. 业务背景与目标

Saleor 商家平台由两部分组成：核心后端（`/workspace/repos/saleor`，当前 3.22.0，`saleor/__init__.py` 中 `__version__ = "3.22.0"`）与商家管理前端 Dashboard（`/workspace/repos/saleor-dashboard`，当前 3.22.9，`package.json` 中 `"version": "3.22.9"`）。本次业务需求（`/workspace/instruction.md`）要求将两个仓库的生产代码协调升级到目标版本 3.23.0：

- 保持后端 API 与 Dashboard 行为一致，包括 GraphQL 契约、生成的客户端产物（generated client artifacts）、数据库迁移和构建/依赖声明。
- 在实现目标行为的同时，保留被回归测试覆盖的现有行为；禁止用测试专用桩（test-specific stubs）替代缺失的生产功能。
- 两个仓库当前处于各自基线提交（core 基线 `c864e66`、dashboard 基线 `aebb240`，均为 3.22 基线加 3.23 环境补丁），环境补丁已预先应用：core 侧更新了 `pyproject.toml`/`setup.cfg`/`uv.lock`（如 `django[bcrypt]~=5.2.13`、`pillow>=12.1.1`），dashboard 侧完成了 npm→pnpm 的构建工具迁移（新增 `pnpm-lock.yaml`、`pnpm-workspace.yaml`，删除 `package-lock.json`，`package.json` 脚本改用 pnpm）。后续工作以这些已就绪的环境为基础，只做 3.23 目标行为所需的生产代码改动。

依据：instruction.md 第 3–22 行（基线与目标版本、协调迁移要求、交付与验收方式）。

## 2. 用户与场景

- **平台运维/部署工程师**：负责部署升级后的 Saleor core 与 Dashboard。典型任务：执行数据库迁移使 3.22 存量数据平滑过渡到 3.23；使用 pnpm 工具链构建 Dashboard；保证后端与前端版本声明一致（3.23.0）。
- **商家运营人员（Dashboard 使用者）**：负责商品、订单、退款等日常经营操作。典型任务：使用订单列表的过滤与搜索定位订单；在订单详情页办理退款（3.23 引入退款原因配置后按商家配置填写退款原因）；正常使用升级前已有的全部页面与流程，不因升级产生中断。
- **店员/客服（staff）**：处理订单与退款。典型任务：在商家启用退款原因要求后，于退款操作中选择结构化退款原因；在未启用时不被额外步骤阻塞。
- **第三方应用开发者（App / App Extension 开发者）**：通过 GraphQL API 与 App Extension 机制扩展平台。典型任务：使用 `orders`/`pages` 等查询的 `where`/`search` 参数；使用 3.23 的 App Extension 挂载点与 `NEW_TAB`/`WIDGET` 目标及其 `options` 配置；读取 `TransactionItem.paymentMethodDetails` 等结构化支付信息。
- **研发工程师（本需求的实施者）**：在两个仓库中完成生产代码迁移，交付可供评估的源码改动。

## 3. 需求条目

### R01 · 后端版本声明与 Schema 版本升级至 3.23
- 来源：Instruction "The baselines are core 3.22.0 and dashboard 3.22.9; the intended target is 3.23.0."；推导依据：当前 `saleor/__init__.py` 为 `__version__ = "3.22.0"` 且 `schema_version` 由主版本号推导（`f"{_major}.{_minor}"`），升级必须同步声明。
- 优先级：P0
- 需求描述：将 core 仓库的版本声明更新到 3.23 目标版本（`saleor/__init__.py` 的 `__version__` 及 `pyproject.toml` 的 `version`），使派生的 schema 版本（如 `schema_version = "3.23"`、GraphQL 服务元信息、webhook/API 版本标识）与目标一致；版本声明改动只更新声明本身，不引入与 3.23 行为无关的变更。
- 验收条件：
  - AC-01-1：在升级后的 core 仓库中读取版本声明，`saleor.__version__` 为 `3.23.0`，派生的 `schema_version` 为 `3.23`。
  - AC-01-2：以升级后的 core 代码启动 GraphQL 服务，服务可正常启动且 schema 内省可用。

### R02 · Dashboard 版本与 GraphQL Schema 对齐升级
- 来源：Instruction "Keep the backend API and Dashboard behavior consistent, including their GraphQL contracts, generated client artifacts"；推导依据：dashboard 当前 `package.json` 为 `"version": "3.22.9"`、`config.saleor.schemaVersion` 为 `"3.22"`，codegen 以仓库根目录 `schema.graphql` 为输入生成 `src/graphql/*.generated.ts`。
- 优先级：P0
- 需求描述：将 Dashboard 的 `package.json` 版本声明升级到 3.23.0，并将 `config.saleor.schemaVersion` 更新为 `3.23`；使仓库内的 GraphQL schema 副本与后端 3.23 schema 一致；重新生成客户端产物（`src/graphql/types.generated.ts`、`hooks.generated.ts`、`fragmentTypes.generated.ts`、`typePolicies.generated.ts`），保证类型与后端契约一致，前端代码按生成类型编译通过。
- 验收条件：
  - AC-02-1：Dashboard `package.json` 中 `"version"` 为 `3.23.0`，`config.saleor.schemaVersion` 为 `"3.23"`。
  - AC-02-2：仓库内 `schema.graphql` 与后端 3.23 schema 一致，且生成产物（`src/graphql/*.generated.ts`）与该 schema 匹配，前端类型检查（`check-types`）通过。
  - AC-02-3：Dashboard 使用 pnpm 工具链执行构建/生成脚本（`generate`、`build`）可正常完成，不回退到 npm 脚本（环境补丁已将 scripts 改为 pnpm）。

### R03 · 数据库迁移与存量数据平滑过渡
- 来源：Instruction "including their GraphQL contracts, generated client artifacts, database migrations, and build/dependency declarations."
- 优先级：P0
- 需求描述：为 3.23 引入的数据模型变更提供完整 Django 迁移（含新增表/字段/索引及必要的数据迁移），保证从 3.22 数据库状态迁移到 3.23 后：存量数据不丢失、语义不变；迁移可重复在干净与已填充数据的环境上执行；迁移与 3.22 基线迁移链连续（无断链、无冲突依赖）。评估使用本地数据库（含 `replica_user.sql` 等预置数据），迁移必须在该数据上成功执行。
- 验收条件：
  - AC-03-1：在包含 3.22 业务数据的数据库上执行全部迁移，迁移成功完成且无数据错误。
  - AC-03-2：迁移完成后，3.22 已存在的订单、商品、页面、属性、退款设置等数据可被 3.23 代码正常读写。
  - AC-03-3：迁移链完整可回溯：`manage.py migrate` 从新库到 3.23 最新迁移一次性通过。

### R04 · 订单（orders）查询 `where`/`search` 过滤与全文搜索
- 来源：Instruction "implementing the target behavior"（目标为 3.23.0）；推导依据：core 仓库 3.22 CHANGELOG（`saleor/CHANGELOG.md` "Enhanced Filtering & Search" 节）已描述 3.22 引入的 orders `where`/`search` 契约，schema 中 `filter` 参数标记 `DEPRECATED_IN_3X_INPUT + Use \`where\` and \`search\` instead.`，3.23 需保持并完整实现该契约（含排序扩展）。
- 优先级：P0
- 需求描述：`orders` 查询支持 `where`（AND/OR 逻辑，`eq`/`oneOf`/`range` 操作符）与独立 `search` 参数；`where` 覆盖既有 filter 字段（`ids`、`channel_id`、`customer`、`created_at`、`updated_at`、`status`、`authorize_status`、`charge_status`、`payment_status`、`is_click_and_collect`、`is_preorder`、`checkout_token`、`checkout_id`、`is_gift_card_used`、`is_gift_card_bought`、`number`、`metadata`）及扩展字段（`user`、`user_email`、`voucher_code`、`has_invoices`、`invoices`、`has_fulfillments`、`fulfillments`、`lines`、`lines_count`、`transactions`、`total_gross`、`total_net`、`product_type_id`、`events`、`billing_address`、`shipping_address`）；`search` 使用 PostgreSQL 全文检索（websearch 模式），按权重 A（订单号、ID、邮箱、姓名）→ B（客户备注、外部引用、账单/收货地址字段）→ C（订单行字段，受 `SEARCH_ORDERS_MAX_INDEXED_LINES` 限制）→ D（折扣名、支付/交易/发票 ID、订单事件消息，受相应 `SEARCH_ORDERS_MAX_INDEXED_*` 限制）排序；支持按订单状态排序。废弃的 `filter` 参数保留向后兼容。
- 验收条件：
  - AC-04-1：对 `orders` 查询使用 `where` 组合条件（含 AND/OR 与 `eq`/`oneOf`/`range`），返回结果与条件语义一致；覆盖列表中每个过滤字段的查询均可执行且结果正确。
  - AC-04-2：使用 `search` 参数查询时，命中权重高的字段（如订单号）的结果排在权重低的字段命中结果之前；检索覆盖 CHANGELOG 列出的各权重字段。
  - AC-04-3：使用废弃 `filter` 参数的既有查询在 3.23 上仍返回与 3.22 相同的结果（向后兼容，不产生 schema 错误）。
  - AC-04-4：按订单状态排序的 `orders` 查询返回符合排序规则的结果。

### R05 · 草稿订单（draftOrders）与 Models/Pages（pages）查询 `where`/`search`
- 来源：Instruction "implementing the target behavior"；推导依据：CHANGELOG 3.22 "Data Modeling" 与 "Enhanced Filtering & Search" 节对 `draftOrders` 与 `pages` 查询的描述；`saleor/graphql/page/schema.py` 已含 `where=PageWhereInput` 且 `filter` 标记废弃。
- 优先级：P0
- 需求描述：`draftOrders` 查询支持 `where`/`search`，`where` 覆盖 CHANGELOG 列出的草稿订单过滤字段（`ids`、`number`、`updated_at`、`user`、`user_email`、`authorize_status`、`charge_status`、`is_click_and_collect`、`voucher_code`、`lines`、`lines_count`、`transactions`、`total_gross`、`total_net`、`product_type_id`、`events`、`billing_address`、`shipping_address`、`channel_id`、`customer`、`created_at`、`metadata`），且不支持 `orders` 特有的 `status`、`checkout_token`、`checkout_id`、`is_gift_card_used`、`is_gift_card_bought`、`has_invoices`、`invoices`、`has_fulfillments`、`fulfillments`；`search` 与 orders 一致。`pages`（Dashboard 中呈现为 Models）查询支持 `where`（`ids`、`page_type`、`slug`、`metadata`、按属性过滤含数值/布尔/日期/引用属性及 `contains_all`/`contains_any`）与独立 `search`（标题、slug、内容），支持 AND/OR 与 `eq`/`oneOf`/`range`。废弃 `filter` 参数继续可用。
- 验收条件：
  - AC-05-1：`draftOrders` 使用 `where`/`search` 的查询结果正确，且不支持的字段在 schema 中不存在（查询即报 schema 校验错误而非静默忽略）。
  - AC-05-2：`pages` 使用 `where` 按属性过滤（数值 `eq`/`range`、布尔、日期、引用属性按 ID/slug、`contains_all`/`contains_any`）返回符合语义的页面集合。
  - AC-05-3：`pages` 使用独立 `search` 参数在标题、slug、内容上的检索行为与 3.22 的 `filter.search` 一致；废弃 `filter` 参数继续可用。

### R06 · 属性体系扩展：SINGLE_REFERENCE 类型、referenceTypes 限定、AssignedAttribute 接口、属性 choices 查询
- 来源：Instruction "implementing the target behavior"；推导依据：CHANGELOG 3.22 "Data Modeling" 节（`SINGLE_REFERENCE`、`AttributeEntityType` 扩展 `CATEGORY`/`COLLECTION`、`referenceTypes`、`AssignedAttribute`、`attribute.choices` 的 `where`/`search`）。
- 优先级：P0
- 需求描述：实现 3.23 属性体系的完整契约：(a) 新增 `SINGLE_REFERENCE` 属性类型，指向 `AttributeEntityTypeEnum` 定义的各类实体，与 `REFERENCE`（多引用）并存；(b) `Attribute` 增加 `referenceTypes` 字段，可对 `PRODUCT`/`PRODUCT_VARIANT` 实体限定 `ProductType` 列表、对 `PAGE` 实体限定 `PageType` 列表，可通过 `attributeCreate`、`attributeUpdate`、`attributeBulkCreate`、`attributeBulkUpdate` 设置，未设置时全量可选；(c) `Page`、`Product`、`ProductVariant` 提供 `AssignedAttribute` 接口及 `assignedAttribute`/`assignedAttributes` 字段，废弃原有 `attribute`/`attributes` 字段（保留可用）；(d) `attribute.choices` 查询支持 `where`（`ids`、`slug`、`name`，操作符 `eq`/`oneOf`）与独立 `search`（名称、slug）；(e) `AttributeEntityType` 支持 `CATEGORY` 与 `COLLECTION` 引用。
- 验收条件：
  - AC-06-1：创建 `SINGLE_REFERENCE` 属性并赋值，只能保存单个引用对象，接口返回符合类型定义；各类实体类型（含 `CATEGORY`、`COLLECTION`）均可作为引用目标。
  - AC-06-2：设置 `referenceTypes` 后，取值范围被限定在指定 ProductType/PageType 内；通过四个属性变更 mutation 均可读写该字段；未设置时不做限定。
  - AC-06-3：`Page`/`Product`/`ProductVariant` 上的 `assignedAttribute`/`assignedAttributes` 返回正确的属性与值结构；废弃的 `attribute`/`attributes` 字段返回与 3.22 相同的数据。
  - AC-06-4：`attribute.choices` 使用 `where`（含 `name`）与 `search` 查询返回符合语义的结果；废弃 `filter` 参数继续可用。

### R07 · 退款设置（RefundSettings）与结构化退款原因
- 来源：Instruction "implementing the target behavior"；推导依据：CHANGELOG 3.22 "Data Modeling" 节对 `RefundSettings` 的描述；当前 schema 已含 `refundSettings`、`refundSettingsUpdate`、`refundReasonReferenceClear`（schema.graphql 第 267、15418、15430 行）；dashboard 已有 `src/refundsSettings/` 目录（mutations、queries、route、views）需与 3.23 行为对齐。
- 优先级：P0
- 需求描述：提供全局退款设置：通过 `refundSettingsUpdate` 将某个 `PageType`（Dashboard 呈现为 Model Type）设为退款原因引用类型；设置后，staff 用户在 `orderGrantRefundCreate`、`orderGrantRefundUpdate`、`orderRefund`、`fulfillmentRefundProducts`、`transactionRequestAction` 变更中必须提供该类型的 `reasonReference`（Page ID），未提供或类型不符时操作被拒绝并给出明确错误；通过 `refundReasonReferenceTypeClear` 清除设置后，退款不再要求原因，且再传入原因引用将报错；App 调用方不受强制要求。Dashboard 提供对应配置入口与退款表单中的原因选择能力，与后端行为一致。
- 验收条件：
  - AC-07-1：未配置退款原因类型时，staff 创建/更新退款（上述五个 mutation）无需提供原因即可成功。
  - AC-07-2：配置退款原因类型后，staff 的上述操作缺少 `reasonReference` 或引用类型不符时被拒绝并返回明确错误；提供正确引用时操作成功且原因被记录。
  - AC-07-3：执行 `refundReasonReferenceTypeClear` 后，staff 退款恢复为无需原因；此时再传入 `reasonReference` 被拒绝并报错。
  - AC-07-4：以 App 身份执行退款操作时，不强制要求提供退款原因。
  - AC-07-5：Dashboard 退款配置页面可设置/清除原因引用类型；退款操作界面在启用配置后提供原因选择并正确提交 `reasonReference`。

### R08 · TransactionItem 结构化支付方式明细（paymentMethodDetails）与 Money 分数字段
- 来源：Instruction "implementing the target behavior"；推导依据：CHANGELOG 3.22 "Payments & Transactions" 与 "Webhooks" 节（`paymentMethodDetails`、`CARD`/`OTHER` 类型、`transactionEventReport`/`transactionCreate`/`transactionUpdate`、交易同步 webhook 响应、`Money.fractionalAmount`/`fractionDigits`）。
- 优先级：P0
- 需求描述：`TransactionItem` 支持存储并查询 `paymentMethodDetails`，支持 `CARD`（名称、品牌、首尾四位、有效期月/年）与 `OTHER`（支付方式名称）两种类型；数据可由 `transactionEventReport`、`transactionCreate`、`transactionUpdate` 变更写入，也可由 `TRANSACTION_INITIALIZE_SESSION`、`TRANSACTION_PROCESS_SESSION` 同步 webhook 的响应写入；`Money` 类型提供 `fractionalAmount`（最小货币单位整数）与 `fractionDigits`（货币小数位）字段。订单/草稿订单按 `transactions` 过滤时可按支付方式名称与类型过滤（仅对升级后写入明细的交易生效）。
- 验收条件：
  - AC-08-1：通过三个交易 mutation 写入 `paymentMethodDetails`（`CARD` 与 `OTHER` 各至少一例），可通过 `TransactionItem.paymentMethodDetails` 查询回一致数据。
  - AC-08-2：交易同步 webhook 响应中返回 `paymentMethodDetails` 时，明细被写入对应 `TransactionItem`。
  - AC-08-3：`Money` 类型查询返回正确的 `fractionalAmount` 与 `fractionDigits`（如 USD 金额 12.95 → 1295 与 2；JPY → 0 位小数）。
  - AC-08-4：`orders`/`draftOrders` 的 `transactions` 过滤可按支付方式名称与类型命中升级后写入明细的交易。

### R09 · App Extension 目标与挂载点扩展（NEW_TAB / WIDGET / options）
- 来源：Instruction "implementing the target behavior"；推导依据：CHANGELOG 3.22 "App Extensions" 节（`AppExtensionTargetEnum.NEW_TAB`、`WIDGET`、新增挂载点、`AppExtension.options`）；当前 `saleor/app/types.py` 已含 `NEW_TAB` 与 widget 挂载点枚举，schema 含 `AppExtensionPossibleOptions = AppExtensionOptionsWidget | AppExtensionOptionsNewTab`；dashboard `src/extensions/`（`new-tab-actions.ts`、`AppWidgets`、`InstalledExtensions` 等）为对应实现载体。
- 优先级：P0
- 需求描述：后端支持 `NEW_TAB` 与 `WIDGET` 扩展目标及 `options`（`newTabTarget.method`、`widgetTarget.method`，支持 GET/POST），支持 CHANGELOG 列出的全部列表页/详情页动作挂载点（CATEGORY、COLLECTION、GIFT_CARD、DRAFT_ORDER、DISCOUNT、VOUCHER、PAGE、PAGE_TYPE、MENU 的 `*_OVERVIEW_CREATE`/`*_OVERVIEW_MORE_ACTIONS`/`*_DETAILS_MORE_ACTIONS`，以及 PRODUCT、CUSTOMER、ORDER 的 `*_DETAILS_MORE_ACTIONS`）和 widget 挂载点（`*_DETAILS_WIDGETS`，仅 `WIDGET` 目标）；目标与挂载点的组合校验符合规则（如 widget 挂载点仅允许 `WIDGET` 目标）。Dashboard 在对应页面渲染扩展入口：`NEW_TAB` 扩展以新标签页打开（支持 GET/POST），`WIDGET` 扩展以内嵌 iframe 渲染于详情页。
- 验收条件：
  - AC-09-1：创建 `NEW_TAB` 目标扩展（含 `options.newTabTarget.method` GET/POST）并挂载到列表/详情动作挂载点，API 校验通过；Dashboard 对应页面出现入口，触发后按 method 以新标签页打开目标 URL。
  - AC-09-2：创建 `WIDGET` 目标扩展并挂载到 `*_DETAILS_WIDGETS` 挂载点，Dashboard 详情页以内嵌 iframe 渲染该扩展；将 `WIDGET` 目标挂载到非 widget 挂载点（或反之）被 API 校验拒绝。
  - AC-09-3：查询 `AppExtension.options` 时，按目标类型返回 `AppExtensionOptionsNewTab` 或 `AppExtensionOptionsWidget` 及对应 `method` 字段。
  - AC-09-4：3.22 已存在的扩展挂载点与目标（`APP_PAGE`、`POPUP` 等）行为保持不变。

### R10 · 构建与依赖声明的一致性
- 来源：Instruction "including their GraphQL contracts, generated client artifacts, database migrations, and build/dependency declarations"；基线环境补丁提交（core：pyproject/setup.cfg/uv.lock 调整；dashboard：pnpm 迁移）。
- 优先级：P0
- 需求描述：两个仓库的构建与依赖声明与其运行环境保持一致且自洽：core 侧 `pyproject.toml` 依赖约束与环境补丁后的锁文件（`uv.lock`）一致，测试配置（`setup.cfg` 中 pytest addopts，含 `--allow-hosts` 与 `--dist loadgroup`）不被回退；dashboard 侧维持 pnpm 工具链（`pnpm-workspace.yaml`、`pnpm-lock.yaml`、`.npmrc` 的 `shamefully-hoist=true`、`jest.config.js` 适配 pnpm 的 `transformIgnorePatterns`），3.23 所需依赖调整（如有）只落在 pnpm 声明中，不重新引入 npm lock 文件；离线环境下不新增无法安装的依赖。
- 验收条件：
  - AC-10-1：在离线环境使用已安装依赖，core 测试可按 `setup.cfg` 配置收集并运行，Dashboard 可用 pnpm 执行 `generate`、`test`、`build` 等脚本。
  - AC-10-2：两个仓库中不存在与声明不一致的锁文件（如 dashboard 不重新出现 `package-lock.json`），依赖声明与实际锁文件一致。
  - AC-10-3：3.23 新增功能所需的依赖（若需新增）声明完整且与已安装环境匹配，不引入网络安装需求。

### R11 · 回归行为保持（升级兼容）
- 来源：Instruction "Preserve existing behavior covered by regression tests while implementing the target behavior. Do not replace missing production features with test-specific stubs."
- 优先级：P0
- 需求描述：3.22 基线上已存在且被回归测试覆盖的全部行为，在升级到 3.23 后保持不变，包括但不限于：GraphQL schema 中未被 3.23 明确废弃/变更的字段与 mutation、订单/结账/支付/商品/属性等核心流程、Dashboard 各页面既有交互；废弃项（`filter` 参数、`attribute`/`attributes` 字段、`Transaction.gatewayResponse`、被标记废弃的插件）以"废弃但仍可用"方式保留，不提前移除；实现 3.23 缺失功能时必须为生产级实现，不得以测试专用桩（如仅在测试环境生效的假实现、硬编码测试数据）替代。
- 验收条件：
  - AC-11-1：评估选定的全部 pass-to-pass 回归测试在升级后通过，无因本次改动引入的失败。
  - AC-11-2：3.23 schema 中标记废弃的字段/参数仍可正常查询使用，行为与 3.22 一致。
  - AC-11-3：代码评审确认新增 3.23 功能为真实生产实现（正常代码路径、无测试环境特判、无硬编码 stub 数据）。

### R12 · 评估交付与工程约束
- 来源：Instruction "Work offline; do not fetch target source or install packages from the network. Commit changes to the working trees as ordinary source edits；评估导出各仓库相对固定 agent 基线的 diff"；"Do not modify evaluation tests, fixtures, the verifier, or scoring configuration."
- 优先级：P0
- 需求描述：实施过程遵守工程约束：全程离线，不拉取目标源码、不联网安装依赖；改动作为普通源码编辑提交到两个仓库的工作树，最终交付为各仓库相对其固定基线（core `c864e66`、dashboard `aebb240`）的 diff；不修改评估测试、fixtures、校验器与评分配置；本地验证使用 `/opt/runtime/run-suite.sh <attempt> <suite>...`（`core-unit`、`core-e2e`、`dash-unit`、`dash-e2e`），运行时测试依赖本地数据库等服务，健康检查通过不等于测试通过；验收以官方测试为准：选定的 fail-to-pass 测试全部转为通过，pass-to-pass 测试保持通过，收集失败或缺失结果不计为通过。
- 验收条件：
  - AC-12-1：交付的 diff 仅包含生产代码改动（含迁移、生成产物、构建/依赖声明），未触碰评估测试、fixtures、verifier 与评分配置。
  - AC-12-2：在本地通过 `run-suite.sh` 执行相关套件完成验证；官方评估中选定的 F2P 测试全部通过、P2P 测试保持通过，无收集失败。

## 4. 范围与非目标

**本次包含**：
- Saleor core（3.22.0→3.23.0）与 Saleor Dashboard（3.22.9→3.23.0）的协调生产代码迁移，覆盖：版本声明、GraphQL schema 与契约、生成的客户端产物、数据库迁移、构建/依赖声明，以及 R04–R09 所列 3.23 目标功能行为。
- 保持被回归测试覆盖的既有行为不变（R11），按 R12 的工程约束交付两个仓库的 diff。

**明确不做**：
- 不实现 instruction 未要求、且不属于 3.23 目标版本的功能（例如仅存在于更晚版本的能力）。
- 不修改评估测试、fixtures、verifier 或评分配置；不承诺被评估树的字节级一致性（instruction 明确允许 maintainer 兼容性辅助存在）。
- 不联网获取目标源码或安装依赖；不将缺失的生产功能以测试专用桩替代。
- 不处理"Package release status"中提及的基准发布状态事项（候选 F2P/P2P 列表的维护者验收与冻结属于评测流程，非本次产品交付范围）；本 PRD 仅定义迁移本身的需求与验收。

**延期事项及原因**：无产品功能延期；3.22 已标记废弃的插件与字段仅保持废弃状态，移除工作按上游计划属于未来版本，不在本次范围。

## 5. 其他

- **基线事实**：core 基线提交 `c864e66`（"Apply Saleor 3.23 environment patch"，基于 Release 3.22.0），dashboard 基线提交 `aebb240`（同名环境补丁，基于 Release 3.22），记录在 `/workspace/base-revisions.json`；环境补丁已完成依赖与工具链预调整（core：`django[bcrypt]~=5.2.13`、`pillow>=12.1.1,<13`、`authlib>=1.6.9`、`cryptography<47` 等；dashboard：npm→pnpm），PRD 需求不重复要求这些已完成项，但要求其成果不被回退（R10）。
- **目标行为的主要来源**：3.23 官方发布说明不可联网获取；本 PRD 以 instruction 的目标版本声明（3.23.0）、仓库内 CHANGELOG 对相邻版本契约的描述、当前代码/schema 状态及"评估以官方测试为准"作为目标行为的判定依据。研发实施时应以通过官方 fail-to-pass 测试作为目标行为的最终校准。
- **假设**：3.22→3.23 的功能面与仓库 CHANGELOG 描述的契约族（where/search 过滤、属性体系、退款设置、交易明细、App Extension 扩展）一致；若官方测试揭示了 CHANGELOG 未覆盖的 3.23 行为差异，以实现官方测试期望为准，并在修订记录中说明。
- **待确认项**：无阻塞性待确认项；评分清单冻结（scoring-list freeze）为评测流程事项，不影响本 PRD 需求定义。
