# 前端技术设计：Saleor Dashboard 3.23.0 迁移

版本：v1
责任：前端技术设计
依据：PRD v1，artifacts/sprint1/prd/prd.md
修订：首次交付；修订时记录版本、内容及原因

## 1. 方案概述

Dashboard 侧的 3.23.0 迁移以"生成工件同步 + 版本/构建声明对齐"为主体：基线 `aebb240`（Release 3.22 + 环境补丁，pnpm 工作区）在业务代码上已经按新契约消费——`CHANGELOG.md` 3.22.9 段明确"Switched to the new AppExtension fields introduced in 3.22 patch (mount -> mountName, target -> targetName, options -> settings)"，`src/extensions/queries.ts` 的 `ExtensionList` 查询已选择 `mountName/targetName/settings`，`src/extensions/hooks/useExtensions.ts` 已按 `settings`（zod schema `appExtensionManifestOptionsSchema`）驱动 NEW_TAB/WIDGET 行为。真正的缺口是：**core 3.22.0 尚未提供这三个字段**，dashboard 本地 `schema.graphql`（来自上游 3.22.9 补丁线）与 core 实际导出不一致，`src/graphql/*.generated.ts` 的类型建立在该 schema 之上。

因此前端方案是：

1. 以 core 3.23.0 导出 schema（后端 BD02/BT02 产物，等同本设计交付的 `target-schema.graphql`）重新生成 `schema.graphql` 与 4 个 `*.generated.ts` 工件——由于 dashboard 期望 schema 与 core 3.23.0 导出逐字符一致（已在设计期 diff 验证），生成结果与仓库现有 `schema.graphql` 无差异，`types.generated.ts` 等仅随 codegen 确定性输出校准。
2. 业务代码无需改写扩展逻辑：`useExtensions`/`AppWidgets`/`getExtensionsItems`/manifest 校验（`src/extensions/domain/app-extension-manifest.ts` 用 `mount`+`options` 校验 manifest JSON，为安装前本地校验，与 API 契约字段解耦）全部维持。
3. 版本与构建声明对齐目标清单：`package.json` `version: 3.23.0`、`config.saleor.schemaVersion: "3.23"`、scripts 与依赖按 `/opt/environment/dependencies/target/saleor-dashboard/package.json`（允许输入）更新，`pnpm-workspace.yaml` 采用目标版本，`pnpm-lock.yaml` 以目标 lock 为解析基准；补齐目标 scripts 引用而仓库缺失的少量源文件（`codegen-main.ts`、`codegen-staging.ts`、`lint/rules/named-styles.test.mjs`、`lint/rules/named-effects.test.mjs`、`scripts/fetch-local-schema.cjs` 已存在）。
4. `CHANGELOG.md` 增补 3.23.0 段。

涉及页面/模块：扩展列表与挂载点渲染（`src/extensions/`）、Apps 安装流（`src/apps/`、`src/extensions/views/InstallCustomExtension/`）、变体编辑（`src/products/views/ProductVariant/`，验证 4 根字段变更在限值 4 下正常）、全局版本展示（`src/config.ts` `APP_VERSION`）。

## 2. 需求覆盖

前端承接：R01（dashboard 侧版本标识）、R06（生成工件）、R07（行为与回归）、R08（pnpm 声明离线一致）、R10（提交纪律）；R02/R03/R04/R05 由后端承接（R07 是其消费面）；R09 为约束性需求，融入各 FD 边界。与后端的接口依赖为 I01/I03（I02 为 HTTP 层行为，dashboard 侧只需在 BT/FD 验证中覆盖）。

| 需求 | 设计单元 |
| --- | --- |
| R01 | FD02 |
| R06 | FD01 |
| R07 | FD01、FD03 |
| R08 | FD02 |
| R10 | FD01～FD03（提交纪律） |

## 3. 详细设计

### FD01 · 生成工件同步与扩展消费面校准（R06、R07）
- 覆盖需求：R06、R07
- 设计说明：
  - **前置**：core 仓库完成 BT02 并导出 3.23.0 schema。将 core `python manage.py get_graphql_schema` 的输出写入 dashboard `schema.graphql`（或 `pnpm fetch-local-schema` 从本地 API 拉取——`scripts/fetch-local-schema.cjs` 已存在；离线约束下不得使用 `fetch-schema` 的 GitHub curl 路径）。验证：dashboard `schema.graphql` 与 core 导出 diff 为空（AC-06-2），且与本设计交付的 `target-schema.graphql` 逐字符一致。
  - **再生成**：`pnpm generate`（graphql-codegen，`codegen.ts`：`schema: "./schema.graphql"`，documents 扫 `src/**/queries.ts|mutations.ts|fragments/*.ts|src/searches/*.ts`）产出 `src/graphql/fragmentTypes.generated.ts`、`typePolicies.generated.ts`、`types.generated.ts`、`hooks.generated.ts`（AC-06-1）。codegen 离线可跑：输入全在仓库内，无远程 introspection。
  - **消费面核对（预期零改动）**：
    - `ExtensionList`（`src/extensions/queries.ts:109-138`）已选择 `mountName/targetName/settings`，新契约下类型成立；`useExtensions.ts:32-54` 的解构与 zod 校验（`settingsValidation.data?.newTabTarget?.method ?? "GET"`）语义不变——`settings` 现在由 core 真实提供：DB 根解析为 `{"widgetTarget":{"method":...}}`/`{"newTabTarget":{"method":...}}`/`{}`（backend BD02）。
    - `AppWidgets.tsx` 的 WIDGET POST 渲染、`getExtensionsItems` 的挂载点分发、`AppExtensionContextProvider` 的 active-extension 状态均按 `ExtensionWithParams`（`src/extensions/types.ts`，基于 `ExtensionListQuery`）类型推导，随生成类型自动对齐。
    - manifest 本地校验（`src/extensions/domain/app-extension-manifest.ts`：`mount`+`options`）与 `src/fragments/apps.ts` 的 `AppManifest` 片段（仍用旧 `mount/target`）不需要改：`AppManifestExtension` 的旧字段在 3.23 契约中保留（仅标 deprecated），查询仍合法（I01 兼容面）。
  - **失败处理**：若 codegen 因类型不匹配报错（不应发生，因 schema 与 dashboard 期望一致），按报错的 documents 位置回查是否引入了对已删字段的引用——本设计不删除任何字段，预期不触发。
  - **验证**：`pnpm generate` 后 `git status` 仅 4 个 generated 文件与 `schema.graphql`；`pnpm check-types`（`tsc --noEmit && tsc-strict` + playwright tsconfig）通过（AC-06-3）。

### FD02 · 版本、脚本与依赖声明对齐（R01、R08）
- 覆盖需求：R01、R08
- 设计说明：
  - **`package.json`**（对齐允许输入的目标清单）：
    - `version: "3.23.0"`；`config.saleor.schemaVersion: "3.23"`（`APP_VERSION`（`src/config.ts:207`）读 `packageInfo.version`，UI 显示随动）。
    - scripts 按目标更新：`generate` 拆为 `generate:main`/`generate:staging`（`graphql-codegen --config codegen-main.ts|codegen-staging.ts`）、`fetch-schema` 拆 main/staging、新增 `e2e:clean-auth`、`test:lint-rules`、`graphql-lint-unused`、`update-payment-assets`、`dev:no-strict`、`chromatic`、`test-storybook*`；`test`/`test:ci` 追加 `test:lint-rules`。
    - dependencies：移除直接依赖 `@material-ui/icons` 与 `@saleor/sdk`（代码中仍有导入：`src/graphql/client.ts` 用 `@saleor/sdk` 的 `createFetch/createSaleorClient`、多个组件用 `@material-ui/icons/*`；依赖联合策略下二者作为 base-only 包保留在 node_modules 可解析——`dependency-union.json` 与已装环境均验证）；新增 `@react-editor-js/core@2.1.0`、`history@4.10.1`、`moment@2.30.1`、`react-transition-group@4.4.5`、`sonner@^2.0.7`。
  - **缺失源文件补齐**：目标 scripts 引用而基线缺失的文件需以最小实现落库（属本次普通源码编辑）：`codegen-main.ts`（schema `./schema-main.graphql`，generates 同 `codegen.ts`）、`codegen-staging.ts`（schema `./schema-staging.graphql`）、`lint/rules/named-styles.test.mjs`、`lint/rules/named-effects.test.mjs`（基于既有 `lint/rules/named-styles.cjs`、`no-deprecated-icons.cjs` 的规则断言）。`scripts/update-payment-assets.cjs`、`fetch-local-schema.cjs`、`build-flags.cjs`、`release.cjs`、`count-strict-null-check-errors.cjs`、`formatter.cjs` 已存在。
  - **`pnpm-workspace.yaml`**：采用目标版本（允许输入）：新增 `blockExoticSubdeps`、`minimumReleaseAge(Exclude)`、`trustPolicy`、`recursiveInstall/sharedWorkspaceLockfile`、扩展 `onlyBuiltDependencies`、`overrides`、`auditConfig`。
  - **`pnpm-lock.yaml`**：以目标 lock（允许输入，`lockfileVersion: "9.0"`，importers 的 specifier 与目标 `package.json` 完全一致——已程序化核对零偏差）为解析基准落库；`@material-ui/icons`/`@saleor/sdk` 从 importers 移除但包保留在 node_modules（base-only，运行时导入不受影响）。`pnpm install --frozen-lockfile --offline` 为完成判据；`package.json` version 字段不参与 lock（importers 不记录根版本），改版本号不破坏 frozen-lockfile。
  - **`CHANGELOG.md`**：头部新增 `## 3.23.0` 段（changesets 格式与 3.22.9 段一致），记录版本对齐与依赖声明变更；历史段不改。
- 验证：`pnpm install --frozen-lockfile --offline` 成功；`pnpm exec graphql-codegen --config codegen.ts`（等价 generate）离线成功；`node lint/rules/named-styles.test.mjs && node lint/rules/named-effects.test.mjs` 通过。

### FD03 · 行为回归与 e2e 复验（R07）
- 覆盖需求：R07
- 设计说明：
  - **dash-unit**：`node_modules/.bin/jest --maxWorkers=2`（`run-suite.sh` 直接调 jest，不经过 `pnpm test`，故 `test:lint-rules` 不影响 suite 结果）。重点关注 `src/extensions/hooks/useExtensions.test.ts`、`src/extensions/getExtensionsItems.test.ts`、`src/extensions/domain/app-extension-manifest*.test.ts`——全部为纯前端逻辑（zod 校验/挂载点映射），不依赖 mock server 的 schema 演进，预期全绿。
  - **dash-e2e**：`run-suite.sh` 先以 `/workspace/seed_e2e_fixtures.py` 播种（PK 与 `playwright/data/e2eTestData.ts` 对齐），再 `playwright test --grep '#e2e'`。扩展相关场景：`playwright/tests/apps.spec.ts`（SALEOR_119 从 manifest 安装 app：触发 core 的 `appInstall` + manifest 清洗链路；安装后扩展列表经 `ExtensionList` 消费 `mountName/targetName/settings`）、`playwright/tests/singlePermissions/extensions.spec.ts`（SALEOR_10/SALEOR_131 扩展列表导航与权限）。变体场景 `product.spec.ts`（SALEOR_3/SALEOR_26）覆盖 `VariantUpdate` 四根字段文档在后端限值 4（I02）下的正常提交——这是 dashboard 与 I02 的关键联调点。
  - **失败处理**：e2e 失败先分诊：core 契约缺字段（回 BD02）→ seeding 缺数据（检查 seed 日志）→ 前端类型漂移（回 FD01）。不以修改 e2e 断言的方式"修复"。
- 验证：`/opt/runtime/run-suite.sh <attempt> dash-setup dash-e2e` 与 `dash-unit` 全绿；结果 JSON 完整无缺失。

## 4. 依赖与联调

| 接口 | 消费方设计单元 | 对应需求 | 开发依赖 |
| --- | --- | --- | --- |
| I01 | FD01 | R06、R07 | 需等待（core BT02 导出新 schema 后生成工件） |
| I02 | FD03 | R07 | 可独立开发（FD01 完成后联调验证） |
| I03 | FD03 | R01 | 可独立开发（值断言仅联调时核对） |

联调安排：FD02（版本/依赖/脚本）可先行，不依赖后端；FD01 的 schema 同步是前后端汇合点，以 `target-schema.graphql` 为共同基准（后端实现与前端生成各自向它对齐，可并行开发、汇合时以 diff 为零验收）。mock：FD01 开发期可用本设计交付的 `target-schema.graphql` 直接作为 codegen 输入（临时替换 `codegen.ts` 的 schema 路径或先行落 `schema.graphql`），无需自建 mock server。待解决依赖：无——`@saleor/sdk`、`@material-ui/icons` 运行时解析已验证。

## 5. 其他
- 风险：`codegen-main.ts`/`codegen-staging.ts` 与 `schema-main.graphql`/`schema-staging.graphql` 双文件体系是为在线双分支（main/staging）设计；离线迁移环境只有单一权威 schema，实现时让两个 config 指向各自 schema 文件（内容均为 3.23.0 导出，`generate` 串联执行产物一致），`pnpm generate` 即可离线通过；若评审认为冗余，回退为保留单一 `codegen.ts` 的方案需同步回退 scripts（与目标清单偏离，需在报告中说明）。
- `sonner` 等新增依赖在业务代码中暂无导入点（为上游 3.23 后续组件预置），仅落清单与 lock，不新造使用点（R03 边界：不实现与测试无关的自创功能）。
- 验证计划：FD02 → `pnpm install --frozen-lockfile --offline`；FD01 → `pnpm generate` + `pnpm check-types`；FD03 → run-suite 全套。未决项：官方测试冻结名单发布后如涉及 dashboard 新增页面断言，按编号顺延增补 FD，不重排。
