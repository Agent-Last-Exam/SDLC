# PRD：Saleor core 与 Dashboard 3.23.0 协同迁移

版本：v1
责任：产品
状态：存在待确认项
输入：instruction.md；现有项目代码
修订：首次交付（v1，2026-10-14），无修订历史

## 1. 业务背景与目标

Saleor 商家平台由两个协同演进的仓库组成：`saleor/`（核心后端，GraphQL API 与业务逻辑）与 `saleor-dashboard/`（商家管理前端）。当前工作区基线为 core 3.22.0（基线 commit `c864e66b8e537d30732ddba62d3a4c47e49e4a3e`，即 Release 3.22.0 叠加 3.23 运行环境补丁）与 dashboard 3.22.9（基线 commit `aebb2401b5079fbbb8c60150289d1896c108feca`，即 Release 3.22 叠加环境补丁）。

业务问题：平台需要完成一次 minor 版本升级，把两个仓库的版本、GraphQL 契约、前端生成工件、数据库迁移与依赖/构建声明统一推进到 3.23.0。两仓库若不协同升级，会出现契约失配：后端 schema 变更后，Dashboard 按 3.22 schema 生成的查询类型与片段可能与新契约不一致，导致商家端功能不可用或行为漂移。

目标（依据 instruction.md 原文）：

1. 在两个仓库完成到 3.23.0 的协同生产代码迁移（"Implement the coordinated production-code migration to 3.23.0 across both repositories"）。
2. 保持后端 API 与 Dashboard 行为一致，包括 GraphQL 契约、生成的客户端工件、数据库迁移和构建/依赖声明（"Keep the backend API and Dashboard behavior consistent…"）。
3. 在实现目标行为的同时，保留回归测试覆盖的既有行为（"Preserve existing behavior covered by regression tests…"）。
4. 接受标准：官方测试选定的 fail-to-pass 用例迁移后全部通过，pass-to-pass 用例保持通过；收集失败或缺少选定结果均视为不通过（"Collection failures and missing selected results are not passes"）。

本 PRD 不编造业务量化指标：升级的业务收益以官方测试的通过结果作为唯一可判定依据。运行时验证使用本地 `​/opt/runtime/run-suite.sh <attempt> <suite>...`（支持 `core-unit`、`core-e2e`、`dash-unit`、`dash-e2e` 等 suite）；运行时测试依赖本地数据库等服务，仅有健康检查通过不等于测试成功。

## 2. 用户与场景

- 商家运营人员（Dashboard 用户）：升级后继续使用订单、产品、模型（Models/原 Pages）、属性、扩展等管理页面；既有操作流程不回归，3.23 新增能力（以官方测试覆盖为准）在界面上可用且与新 API 行为一致。
- 集成开发者 / App 作者：依赖 GraphQL 契约的稳定性——3.23 新增元素有明确标记，已废弃元素保留并可继续使用，契约文件与运行时行为一致。
- 自部署运维人员：升级时数据库迁移可直接执行、依赖与锁文件离线一致、构建不依赖网络。
- 平台研发与 QA：在本地以 `/opt/runtime/run-suite.sh` 运行四类 suite 验证迁移质量；两仓库的改动以普通源码提交呈现，可按基线 commit 导出 diff。

## 3. 需求条目

### 版本与发布标识

#### R01 · 版本标识与变更记录对齐 3.23.0
- 来源：Instruction "the intended target is 3.23.0"、"Implement the coordinated production-code migration to 3.23.0 across both repositories"。
- 优先级：P0
- 需求描述：两仓库对外可见的版本标识统一升级到 3.23.0/3.23：core 的 `saleor/__init__.py` 中 `__version__`（当前 `"3.22.0"`）与 `schema_version`（当前 `"3.22"`）、`pyproject.toml` 的 `version`（当前 `"3.22.0"`）；dashboard 的 `package.json` 中 `version`（当前 `"3.22.9"`）与 `config.saleor.schemaVersion`（当前 `"3.22"`）。两仓库 `CHANGELOG.md` 增补 3.23 版本记录。历史版本记录不改写。`saleor/graphql/core/descriptions.py` 需补充 3.23 对应的描述常量（如 `ADDED_IN_323`，当前止于 `ADDED_IN_322`）。
- 验收条件：
  - AC-01-1：在 core 仓库执行 `python -c "import saleor; print(saleor.__version__, saleor.schema_version)"`，输出 `3.23.0 3.23`。
  - AC-01-2：GraphQL `shop { version schemaVersion }` 分别返回 `3.23.0` 与 `3.23`（`saleor/graphql/shop/types.py` 的 `resolve_version`/`resolve_schema_version` 直接读取上述模块常量）。
  - AC-01-3：dashboard `package.json` 的 `version` 为 `3.23.0`、`config.saleor.schemaVersion` 为 `3.23`；`pyproject.toml` 的 `version` 为 `3.23.0`。
  - AC-01-4：core 与 dashboard 的 `CHANGELOG.md` 均含 3.23 版本段落，且既有 3.22 记录保持不变。

### 后端 API 与数据

#### R02 · GraphQL 契约升级至 3.23 且与实现一致
- 来源：Instruction "Keep the backend API and Dashboard behavior consistent, including their GraphQL contracts"；推导依据：core 的权威契约文件为 `saleor/graphql/schema.graphql`，与 graphene 定义（`saleor/graphql/**` 的 types/schema/mutations/filters/sorters）须同步生成、保持一致。
- 优先级：P0
- 需求描述：按 3.23 目标契约调整 graphene 类型、输入、枚举、字段描述与废弃标记，并重新生成 `saleor/graphql/schema.graphql`。新增元素带 "Added in Saleor 3.23." 描述；新增废弃带 deprecated 理由。契约变更不破坏 3.22 既有消费者（兼容要求并入 R05）。
- 验收条件：
  - AC-02-1：从代码运行时导出的 schema 与仓库内 `saleor/graphql/schema.graphql` 内容一致（无 diff，或仅有评审接受的注释级差异）。
  - AC-02-2：3.23 新增的 schema 元素描述含 "Added in Saleor 3.23."；新增废弃元素带 deprecated 理由。
  - AC-02-3：官方 core 测试收集无错误（无 collection error；收集失败按 Instruction 视为不通过）。

#### R03 · 3.23 目标行为的生产实现
- 来源：Instruction "…while implementing the target behavior. Do not replace missing production features with test-specific stubs."；"The intended acceptance rule requires all selected fail-to-pass tests to pass after your changes…"。
- 优先级：P0
- 需求描述：官方测试所选 fail-to-pass 用例对应的 3.23 业务行为，以生产代码实现落地（涉及 resolver、service 层、models、查询优化、权限校验等 core 全部相关业务域）。适用边界：仅覆盖官方测试定义的 3.23 目标范围；不实现与测试无关的自创功能；不得出现仅在测试上下文生效的桩实现（如按测试名分支、测试专用配置短路）。评估树不要求与上游 3.23 目标树逐字节一致（官方测试允许维护者提供的兼容助手），验收以测试行为为准。
- 验收条件：
  - AC-03-1：迁移后，官方选定的 fail-to-pass 测试全部通过（含结果完整、无收集失败）。
  - AC-03-2：两仓库 diff 中不存在仅服务测试的桩逻辑（代码评审判定：无按测试名/环境切换的实现分支）。
  - AC-03-3：本地可复验：`/opt/runtime/run-suite.sh <attempt> core-unit core-e2e` 中相关用例通过。

#### R04 · 数据库迁移完整可执行
- 来源：Instruction "…including their GraphQL contracts, generated client artifacts, database migrations, and build/dependency declarations"。
- 优先级：P0
- 需求描述：3.23 涉及的模型变更须附带新增 Django migrations；不改写既有历史迁移；迁移在空库与已升级库上均可执行。
- 验收条件：
  - AC-04-1：core 仓库 `python manage.py makemigrations --check --dry-run` 报告 "No changes detected"（退出码 0）。
  - AC-04-2：`python manage.py migrate` 在本地运行时数据库上成功完成；涉及迁移的官方 core 测试通过。

#### R05 · 废弃能力保留与 API 兼容
- 来源：Instruction "Preserve existing behavior covered by regression tests"；推导依据：上游 minor 版本惯例为仅标记废弃、不物理移除，3.22 契约中已废弃元素（如 `products`/`orders` 等查询的 `filter` 参数、`Transaction.gatewayResponse`、deprecated 支付/通知插件）仍被 3.22 消费者使用。
- 优先级：P1
- 需求描述：迁移不物理移除 3.22 已废弃的 API 元素、字段或内置插件；3.23 契约在 3.22 基础上以新增与标记方式演进，保证既有集成与回归用例不受影响。
- 验收条件：
  - AC-05-1：3.22 契约中已废弃元素（如 `products(filter:)`、`Transaction.gatewayResponse` 及 deprecated 插件注册项）在 3.23 契约与运行时中仍存在且保留废弃标记。
  - AC-05-2：依赖上述废弃入口的官方 pass-to-pass 用例迁移后继续通过。

### Dashboard 一致性

#### R06 · Dashboard 生成工件同步
- 来源：Instruction "…generated client artifacts…"；推导依据：dashboard 由 `codegen.ts` 定义生成物：`schema.graphql` 与 `src/graphql/types.generated.ts`、`hooks.generated.ts`、`fragmentTypes.generated.ts`、`typePolicies.generated.ts`。
- 优先级：P0
- 需求描述：使用升级后 core 的 schema 重新生成 dashboard 的 `schema.graphql` 与全部 `*.generated.ts` 工件；受契约变化影响的 queries/mutations/fragments（`src/**/queries.ts`、`mutations.ts`、`fragments/`）同步更新；codegen 可离线运行。
- 验收条件：
  - AC-06-1：`pnpm generate`（graphql-codegen）离线运行成功，生成文件与仓库内容无 diff。
  - AC-06-2：dashboard `schema.graphql` 与 core 导出的 3.23 schema 一致。
  - AC-06-3：`pnpm check-types`（`tsc --noEmit` 与 `tsc-strict`）通过。

#### R07 · Dashboard 行为与升级后 API 一致且回归保持
- 来源：Instruction "Keep the backend API and Dashboard behavior consistent"、"Preserve existing behavior covered by regression tests"。
- 优先级：P0
- 需求描述：受 3.23 契约变化影响的 Dashboard 页面与流程（列表/筛选/排序、详情、扩展挂载等）按新 API 正常工作；既有 UI 行为不回归。官方 dashboard 测试（单元与 e2e）全部通过；e2e 运行需真实完成（依赖运行时数据库与 seeding，健康检查通过不视为测试成功）。
- 验收条件：
  - AC-07-1：官方 dash-unit 测试全部通过。
  - AC-07-2：官方 dash-e2e（`#e2e` 选定集）测试全部通过。
  - AC-07-3：dash-setup seeding 成功、`/health/` 可用，且测试结果完整无缺失（缺结果视为不通过）。

### 工程与交付保障

#### R08 · 依赖与构建声明离线一致
- 来源：Instruction "…build/dependency declarations…"、"Work offline; do not fetch target source or install packages from the network."
- 优先级：P1
- 需求描述：迁移涉及的依赖与构建声明保持一致且可离线解析：core 的 `pyproject.toml` 与 `uv.lock`；dashboard 的 `package.json` 与 `pnpm-lock.yaml`/`pnpm-workspace.yaml`（基线环境补丁已从 npm 切换至 pnpm，须沿用）。不引入需要联网安装的新依赖；全程不访问网络获取目标源码或安装包。
- 验收条件：
  - AC-08-1：`uv lock --check` 通过（`uv.lock` 与 `pyproject.toml` 一致）。
  - AC-08-2：`pnpm install --frozen-lockfile --offline` 成功（node_modules 已预装，lockfile 与 `package.json` 一致）。
  - AC-08-3：迁移过程无网络访问（离线约束遵守，评审与环境记录判定）。

#### R09 · 评估资产零改动与回归全保持
- 来源：Instruction "Do not modify evaluation tests, fixtures, the verifier, or scoring configuration."；"all selected pass-to-pass tests to remain passing. Collection failures and missing selected results are not passes."
- 优先级：P0
- 需求描述：评估测试、fixtures、verifier、评分配置在两仓库中零改动（官方测试在评估时另行提供）；官方 pass-to-pass 用例迁移后全部保持通过；任何收集失败或缺失结果均视为不满足。
- 验收条件：
  - AC-09-1：两仓库相对基线 commit 的 diff 不包含评估测试、fixtures、verifier、评分配置路径的任何改动。
  - AC-09-2：官方选定的 pass-to-pass 测试迁移后全部通过。

#### R10 · 迁移改动以普通源码提交落入两仓库
- 来源：Instruction "Commit changes to the working trees as ordinary source edits; the evaluator exports each repository's diff against its fixed agent baseline."
- 优先级：P1
- 需求描述：全部迁移改动以普通源码编辑提交到两仓库工作树（分别基于基线 commit `c864e66` 与 `aebb240` 继续演进）；不以外置补丁文件、子模块或生成物压缩包方式交付。
- 验收条件：
  - AC-10-1：两仓库 `git status` 干净（改动均已提交），`git diff <baseline>` 能完整展示迁移改动。
  - AC-10-2：导出的 diff 仅包含生产源码、契约文件、生成工件、迁移与构建/依赖声明的常规编辑，可直接应用。

## 4. 范围与非目标

本次包含：

- core：版本与描述常量、graphene 契约与 `saleor/graphql/schema.graphql` 重新生成、3.23 目标行为生产实现、新增数据库迁移、`CHANGELOG.md`。
- dashboard：`schema.graphql` 与 `src/graphql/*.generated.ts` 重新生成、受契约影响的查询/变更/片段更新、行为适配、版本与 `CHANGELOG.md`。
- 两仓库依赖与构建声明的一致性维护（在既有环境补丁之上）。
- 本地验证：通过 `/opt/runtime/run-suite.sh` 运行 `core-unit`、`core-e2e`、`dash-unit`、`dash-e2e` 复验。

明确不做（非目标）：

- 不修改评估测试、fixtures、verifier、评分配置（R09 单独约束）。
- 不联网获取 3.23 上游源码，不从网络安装任何包（R08 约束）。
- 不物理移除 3.22 已废弃的 API/字段/插件——其移除属上游未来版本，本次延期（R05 约束）。
- 不要求评估树与上游 3.23 目标树逐字节一致；验收以官方测试行为为准（Instruction 明示测试可含维护者兼容助手）。
- 不以测试专用桩替代缺失的生产功能（R03 约束）。
- 不升级至 3.23.0 之后的版本，不实现与官方测试无关的自创功能。

## 5. 其他

事实依据（勘察记录，2026-10-14）：

- 基线与提交：core `c864e66`（父提交 `6cfb774` Release 3.22.0）；dashboard `aebb240`（父提交 `e934ff0` Release 3.22）。两基线均已叠加 "Apply Saleor 3.23 environment patch"：core 调整 `pyproject.toml` 依赖（authlib、cryptography、django ~5.2.13、pillow 12.x）与 `setup.cfg` pytest 参数（`--allow-hosts 127.0.0.1,::1,cache`、`--dist loadgroup`）；dashboard 从 npm 切换 pnpm（`pnpm-lock.yaml`、`pnpm-workspace.yaml`、`.npmrc` `shamefully-hoist=true`、移除 `.nvmrc`）、引入 vitest、钉 playwright 1.58.2、jest `transformIgnorePatterns` 适配 pnpm。环境补丁属基线，不重复交付。
- 版本锚点：`saleor/__init__.py:6` `__version__ = "3.22.0"`，`schema_version` 由其派生；`pyproject.toml:7` `version = "3.22.0"`；dashboard `package.json` `version: "3.22.9"`、`config.saleor.schemaVersion: "3.22"`；`shop` 查询的 `version`/`schemaVersion` 直接输出这些常量；`saleor/graphql/core/descriptions.py:17` 版本描述常量止于 `ADDED_IN_322`。
- 测试入口：`/opt/runtime/run-suite.sh` 的 suite 分支为 `core-smoke|core-unit|core-e2e`（pytest，`-m 'not e2e'` / `-m e2e`）、`dash-unit`（jest）、`dash-setup|dash-e2e`（playwright，先 seed 再 `--grep '#e2e'`）；core 测试标记见 `setup.cfg` `markers = integration, e2e`。
- 3.22 基线已具备的能力（迁移中属"保持"而非"新增"，依据 core `CHANGELOG.md` 3.22.0 段落与现有代码/生成类型核对一致）：order 全文检索与 `STATUS` 排序、`draftOrders`/`customers` 的 `where`+`search`、Transaction API 的 `paymentMethodDetails`、`Money.fractionalAmount`/`fractionDigits`、`AppExtension` 的 `NEW_TAB`/`WIDGET` 目标与扩展挂载点、`SINGLE_REFERENCE` 与 `referenceTypes`、`AssignedAttribute` 接口、`saleor/json_schemas/` 同步 webhook 校验、deprecated 插件类（`DeprecatedAvataxPlugin` 等，注册于 `saleor/settings.py` 的 `BUILTIN_PLUGINS`）。

产品决策：

- 3.23 目标行为的最终裁定以评估时提供的官方测试为准；R03 的需求边界即"官方测试选定范围"，后续技术设计（backend-design/frontend-design/interface-contract）应据此细化，不得超出或缩减。
- 版本号遵循上游 semver 惯例：core 与 dashboard 均为 3.23.0；`schemaVersion` 为 `3.23`。

假设与待确认项（本 PRD 状态因此为"存在待确认项"）：

- 官方测试及 fail-to-pass/pass-to-pass 名单在评估阶段才提供。Instruction 载明：候选名单已产出，但 maintainer acceptance 与 scoring-list freeze 尚未完成，formal grading 在接受并冻结前保持禁用。名单冻结后若与 R03 边界理解有出入，以冻结名单为准并按模板规则修订本 PRD（新增条目顺延编号，不重排）。
- 离线约束下无法核对上游 3.23.0 的完整特性清单；对特性的任何理解偏差，以官方测试行为为唯一裁决依据。
