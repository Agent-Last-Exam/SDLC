# PRD：Saleor Core 与 Dashboard 3.23.0 协同迁移

版本：v1
责任：产品
状态：需求范围与验收条件已定义
输入：instruction.md；现有项目代码
修订：首次交付

## 1. 业务背景与目标

Saleor 是面向商家的开源电商平台，本次工作范围覆盖两个仓库：`saleor/`（核心后端，Django + Graphene GraphQL）与 `saleor-dashboard/`（商家管理前端，React + TypeScript + Apollo Client）。当前基线为 core 3.22.0（agent-baseline 提交 c864e66 加环境补丁）与 dashboard 3.22.9（提交 aebb240 加环境补丁），目标版本为 3.23.0。

Instruction 明确要求："Implement the coordinated production-code migration to 3.23.0 across both repositories. Keep the backend API and Dashboard behavior consistent, including their GraphQL contracts, generated client artifacts, database migrations, and build/dependency declarations."

对现有代码的核查显示，本次协同迁移的核心缺口是：

1. **AppExtension GraphQL 契约不一致**。Dashboard 3.22.9 已经切换到 3.22 patch 引入的新字段（dashboard `CHANGELOG.md` 3.22.9 条目："Switched to the new AppExtension fields introduced in 3.22 patch (mount -> mountName, target -> targetName, options -> settings)"），`schema.graphql` 与 `src/extensions/queries.ts`、`src/extensions/hooks/useExtensions.ts`、`src/extensions/components/AppWidgets/AppWidgets.tsx` 均已消费 `mountName: String!`、`targetName: String!`、`settings: JSON!`，并对 `mount`/`target`/`options` 标注了 `@deprecated`。但后端 `saleor/graphql/schema.graphql` 与 `saleor/graphql/app/types.py` 尚未提供这三个字段，导致后端 SDL、Dashboard 侧 SDL 与 Dashboard 生成的客户端产物三方不一致，App 扩展（含 NEW_TAB / WIDGET 目标与各页面挂载点）在两端契约上断裂。
2. **版本与构建声明未到达目标版本**。core 的 `pyproject.toml`、`package.json`、`saleor/__init__.py` 的 `__version__` 仍为 3.22.0；dashboard 的 `package.json` `version` 为 3.22.9、`saleor_schemaVersion` 为 "3.22"。
3. **依赖与构建声明差异**。`/opt/environment/dependencies/target/` 下提供了两仓库的目标依赖清单（saleor：`pyproject.toml` + `uv.lock`；saleor-dashboard：`package.json` + `pnpm-lock.yaml` + `pnpm-workspace.yaml`），其中包含新增依赖与脚本（如 dashboard 的 `generate:main` / `generate:staging` 及对应的 codegen 配置），需要在不破坏现有功能的前提下对齐。
4. **数据库迁移需保持一致且可部署**。基线已含 3.22 patch 迁移（如 `saleor/app/migrations/0031_alter_appextension_mount_alter_appextension_target.py`、`0032_appextension_http_target_method_and_more.py`，以及 site、order、payment 相关 patch 迁移），迁移链必须保持完整、可执行，且不产生未声明的模型漂移。

业务目标：

- G1：两仓库以普通源码改动方式完成到 3.23.0 的协同生产代码迁移，版本标识、GraphQL 契约、生成产物、数据库迁移与构建/依赖声明全部一致。
- G2：既有被回归测试覆盖的行为不被破坏；目标行为以真实生产代码实现，不得用测试专用桩替代缺失功能。
- G3：全程离线工作，不联网获取目标源码或安装包；改动以可导出 diff 的形式留在工作树中，供评测方对照固定基线评测。

验收总规则（引自 Instruction）："Evaluation runs the official tests before and after your changes. The intended acceptance rule requires all selected fail-to-pass tests to pass after your changes and all selected pass-to-pass tests to remain passing. Collection failures and missing selected results are not passes."

## 2. 用户与场景

- **商家管理员 / 运营人员**：通过 Dashboard 管理店铺。他们使用 App 扩展功能（页面内挂载的 WIDGET 小部件、NEW_TAB 新标签页跳转），依赖 Dashboard 与后端契约一致才能正常加载已安装 App 提供的扩展；同时也依赖订单/草稿订单筛选（`OrderWhereInput` / `DraftOrderWhereInput` 与搜索）、退款设置（`RefundSettings`）等既有功能在迁移后保持原行为。
- **App 作者 / API 消费者**：通过 GraphQL API 集成 Saleor。他们读取 `appExtensions` 查询结果来渲染自己的扩展入口，迁移后应能在同一份契约下取到 `mountName` / `targetName` / `settings`，且旧的 `mount` / `target` / `options` 字段在弃用期内继续可用。
- **平台运维 / 部署人员**：负责执行数据库迁移与部署。他们要求迁移链完整可执行、`makemigrations` 无漂移，依赖声明与锁文件一致且可离线安装。
- **平台研发与评测流程**：以四套本地回归套件（`core-unit`、`core-e2e`、`dash-unit`、`dash-e2e`，经 `/opt/runtime/run-suite.sh` 运行）和官方评测（fail-to-pass / pass-to-pass）判定迁移质量。

## 3. 需求条目

#### A. 版本与发布一致性

### R01 · 两仓库版本标识升级至 3.23.0
- 来源：Instruction 原文："The baselines are core 3.22.0 and dashboard 3.22.9; the intended target is 3.23.0." 及 "Keep the backend API and Dashboard behavior consistent, including their GraphQL contracts, generated client artifacts, database migrations, and build/dependency declarations."（版本号属于构建/依赖声明的一部分）。
- 优先级：P0
- 需求描述：将 core 仓库的版本声明从 3.22.0 升级为 3.23.0，涉及 `pyproject.toml` 的 `version`、根 `package.json` 的 `version`、`saleor/__init__.py` 的 `__version__`；将 dashboard 仓库 `package.json` 的 `version` 从 3.22.9 升级为 3.23.0，并将 `saleor_schemaVersion` 从 "3.22" 升级为 "3.23"。版本声明在各自仓库内不得出现互相矛盾（例如 `__version__` 与 `pyproject.toml` 不一致）。Dashboard 展示版本处的取值链（如 `src/config.ts` 中 `APP_VERSION` 基于 package.json version）应自然反映新版本，无需为此引入特殊逻辑。
- 验收条件：
  - AC-01-1：在 core 仓库中执行 `python -c "import saleor; print(saleor.__version__)"` 输出 `3.23.0`，且 `pyproject.toml` 与根 `package.json` 中的 `version` 均为 `3.23.0`。
  - AC-01-2：dashboard 仓库 `package.json` 中 `version` 为 `3.23.0` 且 `saleor_schemaVersion` 为 `"3.23"`。

#### B. GraphQL 契约与生成产物

### R02 · 后端 AppExtension API 补齐 3.22 patch 新字段并弃用旧字段
- 来源：Instruction 原文："Implement the coordinated production-code migration to 3.23.0 across both repositories. Keep the backend API and Dashboard behavior consistent, including their GraphQL contracts..."。推导依据：dashboard `schema.graphql` 已定义 `mountName: String!`、`targetName: String!`、`settings: JSON!` 并在 `mount`/`target`/`options` 上标注 `@deprecated(reason: "Use `mountName` instead.")` 等；dashboard `CHANGELOG.md` 3.22.9 说明已切换到新字段；而后端 `saleor/graphql/schema.graphql` 的 `type AppExtension` 与 `saleor/graphql/app/types.py` 的 `AppExtension` 类型尚无这三个字段——该差异为本迁移必须补齐的生产行为。
- 优先级：P0
- 需求描述：在后端 GraphQL 的 `AppExtension` 类型上新增 `mountName: String!`、`targetName: String!`、`settings: JSON!` 三个字段，以真实生产代码（resolver/类型定义）实现，语义与 Dashboard 现有消费方式一致：`mountName` 为扩展挂载点名称字符串（对应现有 `mount` 的取值），`targetName` 为目标名称字符串（对应现有 `target` 的取值），`settings` 为 JSON 对象，承载原 `options` 所表达的目标配置（包括 NEW_TAB 与 WIDGET 目标的 `method`，其来源为 `AppExtension` 模型的 `http_target_method` 字段）。同时将 `mount`、`target`、`options` 标记为弃用（deprecation 说明指向对应新字段），但三者继续按 3.22 现有行为返回数据，不得移除或改变其现有取值。`settings` 的 JSON 结构需与 Dashboard 侧解析器（`useExtensions.ts` / `AppWidgets.tsx` 中经 `appExtensionManifestOptionsSchema` 校验 `newTabTarget` / `widgetTarget`）兼容。实现不得依赖仅服务于测试的桩代码。
- 验收条件：
  - AC-02-1：后端 `saleor/graphql/schema.graphql` 中 `type AppExtension` 包含 `mountName: String!`、`targetName: String!`、`settings: JSON!`，且 `mount`、`target`、`options` 三者均带指向新字段的 `@deprecated` 指令。
  - AC-02-2：给定一个已安装且配置了扩展的 App（前置：通过现有 app 安装/扩展创建流程建立数据），执行 `appExtensions` 查询时返回的每条扩展记录中 `mountName` 与其 `mount` 取值对应、`targetName` 与其 `target` 取值对应、`settings` 为包含目标配置的 JSON 对象（NEW_TAB / WIDGET 场景下含目标 `method`，取自 `http_target_method`）。
  - AC-02-3：同一查询中 `mount`、`target`、`options` 字段仍返回与迁移前一致的值（弃用不改变行为）；对 `AppExtension` 模型已有数据执行查询不报错。

### R03 · GraphQL 契约与 Dashboard 生成产物对齐
- 来源：Instruction 原文："Keep the backend API and Dashboard behavior consistent, including their GraphQL contracts, generated client artifacts..."。
- 优先级：P0
- 需求描述：R02 完成后，Dashboard 仓库的 `schema.graphql` 与 core 仓库的 `saleor/graphql/schema.graphql` 在 AppExtension 相关契约（`type AppExtension`、相关 enum、`scalar JSON`）上保持一致，消除当前两份 SDL 之间的字段级差异。Dashboard 依据 schema 由 graphql-codegen 生成的客户端产物（`src/graphql/types.generated.ts`、`src/graphql/hooks.generated.ts`、`src/graphql/typePolicies.generated.ts`、`src/graphql/fragmentTypes.generated.ts`）须与最终 schema 同步再生成并提交，保证现有查询（如 `src/extensions/queries.ts` 的 `extensionList` 对 `mountName`/`targetName`/`settings` 的选择）在生成类型中可解析。生成过程须可离线完成（依赖已预装）。
- 验收条件：
  - AC-03-1：对两份 `schema.graphql` 做 diff，`AppExtension` 类型定义、其字段与弃用标注、以及 `AppExtension` 相关 enum 与 `scalar JSON` 声明不再存在字段级差异（允许与契约无关的差异，如文件内声明位置）。
  - AC-03-2：dashboard 中以仓库内 codegen 配置重新执行 graphql-codegen，生成的 `src/graphql/*.generated.ts` 与工作树中已提交内容一致（无未提交 diff），且 `AppExtension` 相关生成类型包含 `mountName`、`targetName`、`settings`。

#### C. 数据迁移与构建/依赖声明

### R04 · 数据库迁移一致性
- 来源：Instruction 原文："Keep the backend API and Dashboard behavior consistent, including ... database migrations, and build/dependency declarations." 及 "Preserve existing behavior covered by regression tests while implementing the target behavior."
- 优先级：P0
- 需求描述：保持 core 仓库现有迁移链完整且可执行，包括基线已有的 3.22 patch 迁移（如 `saleor/app/migrations/0031_alter_appextension_mount_alter_appextension_target.py`、`0032_appextension_http_target_method_and_more.py`，以及 site、order、payment 等 app 的对应 patch 迁移）。若本次改动产生新的模型状态变化，必须以正常新增迁移（`makemigrations` 产物）表达，不得手改既有迁移历史，也不得让模型与迁移出现未声明漂移。迁移需能在评测运行时的数据库上顺序执行成功。
- 验收条件：
  - AC-04-1：在 core 仓库执行 `python manage.py makemigrations --check --dry-run` 退出码为 0（无未生成的模型变更）。
  - AC-04-2：在评测运行时提供的数据库上执行 `python manage.py migrate` 成功完成，基线既有迁移（含 app/0031、app/0032 等）全部可应用，无报错。

### R05 · 依赖与构建/脚本声明对齐目标清单
- 来源：Instruction 原文："Keep the backend API and Dashboard behavior consistent, including ... build/dependency declarations." 及 "Required dependencies and development tools are preinstalled. Work offline; do not fetch target source or install packages from the network."。推导依据：`/opt/environment/dependencies/target/` 提供两仓库的目标依赖清单（saleor 的 `pyproject.toml`/`uv.lock`；saleor-dashboard 的 `package.json`/`pnpm-lock.yaml`/`pnpm-workspace.yaml`），需按既定策略对齐：目标清单声明的版本与新增依赖落入仓库声明，仅存在于基线而目标清单未包含的包（base-only，如 saleor 侧 Adyen、posuto，dashboard 侧 `@material-ui/icons`、`@saleor/sdk`）保留，不因对齐而移除其声明与功能代码。
- 优先级：P0
- 需求描述：将 core 的 `pyproject.toml` 依赖声明与 `uv.lock` 按 target 清单对齐（含目标新增依赖，如 `kombu[sqs]`、`nh3`、`idna`、`orjson` 等），保留 base-only 依赖；将 dashboard 的 `package.json` 与 `pnpm-lock.yaml` 按 target 清单对齐（含目标新增依赖，如 `@react-editor-js/core`、`history`、`moment`、`react-transition-group`、`sonner` 等），保留 base-only 依赖。对齐 dashboard 的构建/脚本声明：target 清单中的脚本差异（如 `generate:main` / `generate:staging` 指向的 `codegen-main.ts` / `codegen-staging.ts` 配置文件、`test` 聚合 `test:lint-rules` 等）应落到仓库中，缺失的配置文件一并补齐。所有依赖解析与安装校验均须离线完成，不得联网。
- 验收条件：
  - AC-05-1：core 仓库 `pyproject.toml` 的依赖声明包含 target 清单相对当前基线新增的依赖及其版本约束，`uv.lock` 与之一致可解析；base-only 依赖（如 Adyen、posuto）仍被声明，对应既有功能代码未被删除。
  - AC-05-2：dashboard 仓库 `package.json` 的依赖包含 target 清单新增依赖，`pnpm-lock.yaml` 与之一致；base-only 依赖（如 `@material-ui/icons`、`@saleor/sdk`）仍被声明；target 清单中的脚本差异已落到 `package.json`，引用的 codegen 配置文件存在于仓库中。
  - AC-05-3：离线校验通过：在预装依赖缓存下以离线方式完成安装/锁文件校验（如 dashboard `pnpm install --offline`、core `uv sync --offline` 或等效命令）全程无网络访问且成功结束。

#### D. 行为保持与交付约束

### R06 · 既有回归行为保持，目标行为以生产代码实现
- 来源：Instruction 原文："Preserve existing behavior covered by regression tests while implementing the target behavior. Do not replace missing production features with test-specific stubs." 及 "The intended acceptance rule requires all selected fail-to-pass tests to pass after your changes and all selected pass-to-pass tests to remain passing. Collection failures and missing selected results are not passes."
- 优先级：P0
- 需求描述：迁移过程中，所有被现有回归测试覆盖的行为保持不变，包括：core 的单元与 e2e 覆盖面（订单/草稿订单 where 与搜索过滤、`RefundSettings` 与 `reasonReference`、TransactionItem 支付方式详情（`PaymentMethodDetails`、`cc_*` 字段与 `update_payment_method_details`）、`Money.fractionalAmount`/`fractionDigits`、同步 webhook JSON schema（`saleor/json_schemas/` 及 `generate_json_schemas.py`）、App 扩展 NEW_TAB / WIDGET 行为等）与 dashboard 的 jest 单测、playwright e2e（含各页面挂载点 `extensionMountPoints.ts`、`ALL_APP_EXTENSION_MOUNTS`、`WIDGET_AVAILABLE_MOUNTS` 的现有语义）。目标行为（如 R02 新字段）必须以真实生产代码实现，禁止为通过测试而添加仅测试可用的桩、开关或特判。本地四套套件（`core-unit`、`core-e2e`、`dash-unit`、`dash-e2e`）不得因本次改动出现新增失败；官方评测的 fail-to-pass / pass-to-pass 规则以 Instruction 为准。
- 验收条件：
  - AC-06-1：使用 `/opt/runtime/run-suite.sh` 运行 `core-unit` 与 `dash-unit`，与基线相比不出现新增失败用例（改动前失败且未被本次要求修复的用例除外，需逐例可解释）。
  - AC-06-2：使用 `/opt/runtime/run-suite.sh` 运行 `core-e2e` 与 `dash-e2e`，与基线相比不出现新增失败场景。
  - AC-06-3：对最终 diff 审查确认：不存在仅服务于评测测试、无生产调用方的桩实现或特判逻辑；R02 的新字段由真实 resolver/类型定义支撑。
  - AC-06-4：官方评测语义下，选定的 fail-to-pass 测试在改动后全部通过，选定的 pass-to-pass 测试全部保持通过，无收集失败、无缺失结果。

## 4. 范围与非目标

本次包含：

- core 与 dashboard 两仓库内、为达成 R01–R06 所需的全部生产代码改动：GraphQL 类型与 resolver、`schema.graphql` 再生成、dashboard 生成产物再生成、数据库新增迁移、版本号与 `saleor_schemaVersion`、依赖声明与锁文件、构建脚本与 codegen 配置。
- 为使契约一致所需的代码内弃用标注（deprecation）与描述文案（含 `ADDED_IN_*` 版本标注的沿用风格）。

明确不做（非目标）：

- 不修改评测测试、fixtures、verifier 或评分配置；官方测试由评测方另行提供。
- 不从网络获取目标源码、不联网安装任何包；全部工作离线完成。
- 不删除或削弱 base-only 依赖对应的既有功能（如 Adyen 支付相关代码、`@saleor/sdk` 的使用），依赖对齐策略为"目标清单升级 + base-only 保留"。
- 不追求与 upstream 3.23.0 上游树逐字节一致；Instruction 明确测试代码可含 maintainer 提供的兼容 helper，评测树不要求逐字节等同。
- 不新增与迁移目标无关的新业务功能，不做顺带重构。
- 正式评分冻结（"maintainer acceptance and scoring-list freeze are pending"）属评测方事项，不在本迁移范围内。

## 5. 其他

- 事实依据：dashboard 3.22.9 的 `schema.graphql`、`src/extensions/queries.ts`、`useExtensions.ts`、`AppWidgets.tsx` 已消费 `mountName`/`targetName`/`settings`，且其 `CHANGELOG.md` 明确记载切换原因；core 基线已含多数 3.23 时代特性（`RefundSettings`、NEW_TAB/WIDGET、`PaymentMethodDetails`、`fractionalAmount`、`OrderWhereInput` 等），故 R02 是契约一致性的主要缺口，而非全面补功能。
- 版本取值事实：core 目标版本号以 `/opt/environment/dependencies/target/saleor/pyproject.toml` 的 `version = "3.23.0"` 为准；dashboard 以 `/opt/environment/dependencies/target/saleor-dashboard/package.json` 的 `version = "3.23.0"`、`saleor_schemaVersion = "3.23"` 为准。
- 依赖对齐策略依据：环境提供的 target 清单即"目标锁定版本"的权威来源；base-only 保留原则来自环境对依赖清单的说明（"base dependencies upgraded by target lockfiles; base-only packages retained"）。
- 假设：评测运行时会提供本地数据库与所需服务（`/opt/runtime/run-suite.sh` 已内置启停与健康检查）；官方测试可能包含 maintainer 兼容 helper，本迁移的实现不得依赖这些 helper 才能工作。
- 待确认项：无阻塞项。评测的 F2P/P2P 名单尚在维护方冻结流程中（Instruction 已声明），本 PRD 的验收条件以 Instruction 记载的总规则为准，不预设具体用例名单。
