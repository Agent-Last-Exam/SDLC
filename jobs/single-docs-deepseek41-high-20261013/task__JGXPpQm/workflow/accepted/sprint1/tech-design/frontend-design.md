# 前端技术设计：Saleor Core 与 Dashboard 3.23.0 协同迁移（Dashboard）

版本：v1
责任：前端技术设计
依据：PRD v1，artifacts/sprint1/prd/prd.md
修订：首次交付

## 1. 方案概述

本次前端工作的目标是把 `saleor-dashboard` 从 3.22.9 提升到 3.23.0，与 core 3.23.0 的契约保持一致，并完成随版本升级的依赖与工程约定切换。整体方案分四条主线：

1. **契约主线**：把 `package.json` 的 `config.saleor.schemaVersion` 提升到 `3.23`，按新的版本化契约重新生成 `src/graphql/*.generated.ts`；同时按目标工程约定把契约来源拆分为「版本化主契约」与「main 分支 staging 契约」两条独立链路。
2. **去 SDK 主线**：移除 `@saleor/sdk`（17 个引用点），在本仓落地等价的客户端配置、认证状态与 fetch 包装能力。
3. **UI 与基础能力主线**：移除 `@material-ui/icons`（9 个文件）统一到 `lucide-react`；接入 `sonner`、`moment`、`history`、`react-transition-group`、`@react-editor-js/core` 作为直接依赖。
4. **工程约定主线**：补齐契约生成、lint 规则、storybook 测试等脚本，删除标注「Remove in Saleor Dashboard 3.23」的兼容代码。

关键事实与源码依据：

- 契约差距的唯一来源是 `AppExtension` 的三个字段。以 core 的 Base schema 校验本仓全部 GraphQL 文档，只报 3 条错误（`src/extensions/queries.ts:9-11` 的 `mountName`/`targetName`/`settings`）；以本次交付的 `target-schema.graphql` 校验同一批文档为 0 错误（详见 backend-design.md BD03）。
- 前端消费方式已固定：`src/extensions/types.ts` 声明 `mountName: AllAppExtensionMounts`、`targetName: AppExtensionManifestTarget`、`settings`；`src/extensions/hooks/useExtensions.ts:35-49` 用 `ALL_APP_EXTENSION_MOUNTS.parse(mountName)` 与 `appExtensionManifestOptionsSchema.safeParse(settings)` 校验取值。
- 代码内已标注迁移意图：`src/graphql/client.ts:37` 的「TODO: Remove once @saleor/sdk is removed in favor of local implementation for auth」；`src/products/urls.ts:97` 与 `src/products/index.tsx:134` 的「TODO: Remove in Saleor Dashboard 3.23」。
- 仓库内 lint 规则 `lint/rules/no-deprecated-icons.cjs` 已要求「Avoid importing icons from @material-ui/icons. Use lucide-react instead.」，并在 `eslint.config.mjs:189` 以 `local-rules/no-deprecated-icons` 生效（当前为 warn）。

## 2. 需求覆盖

| 需求 | 设计单元 |
| --- | --- |
| R03 | FD01 |
| R10 | FD02 |
| R11 | FD03 |
| R12 | FD04 |
| R13 | FD05 |
| R14 | FD07 |
| R15 | FD06 |
| R16 | FD08 |

R01 中 dashboard 侧的版本标识（`package.json.version`、`config.saleor.schemaVersion`）在 FD07 一并处理；R02、R04–R09 为后端承接，见 backend-design.md。

## 3. 详细设计

### FD01 · 契约版本与客户端产物再生成

- 覆盖需求：R03
- 设计说明：

  - `package.json` 的 `config.saleor.schemaVersion` 由 `"3.22"` 改为 `"3.23"`（版本号本身见 FD07）。
  - 契约文件与生成链路按目标约定拆分：
    - 主契约：`fetch-schema:main` 按 `config.saleor.schemaVersion` 拉取版本化 schema 到 `schema-main.graphql`；`generate:main` 用 `codegen-main.ts` 生成现有产物。
    - staging 契约：`fetch-schema:staging` 拉取 main 分支 schema 到 `schema-staging.graphql`；`generate:staging` 用 `codegen-staging.ts` 生成，产物独立存放，不覆盖主链路产物。
    - 聚合脚本 `fetch-schema` 与 `generate` 依次执行两条链路；现有 `codegen.ts` / `schema.graphql` 由对应的 main 链路配置替代。
  - 生成产物：`src/graphql/types.generated.ts`、`src/graphql/hooks.generated.ts`、`src/graphql/fragmentTypes.generated.ts`、`src/graphql/typePolicies.generated.ts` 必须由新 schema 重新生成并提交；codegen 配置项（`nonOptionalTypename`、`avoidOptionals`、枚举命名转换 `upperCase`、`onlyOperationTypes`、`import-types` preset）保持不变，避免产生与契约无关的 diff。
  - 离线约束：本阶段不联网。主链路 schema 以 core 侧导出的 3.23 SDL（即交付的 `target-schema.graphql`）为准，可在本地用 `scripts/fetch-local-schema.cjs` 的等价方式取得。
  - 消费面校验：`src/extensions/queries.ts` 的 `ExtensionList` 查询在目标 schema 上编译通过，生成类型中 `mountName: string`、`targetName: string`、`settings: any`；`src/extensions/types.ts`、`useExtensions.ts` 的 zod 校验路径保持不变。
- 验证方法：`pnpm run generate`（主链路）后 `git diff` 为空（产物稳定）；`pnpm run check-types` 通过；`pnpm run lint` 无新增错误；`pnpm run test` 通过。

### FD02 · 移除 @saleor/sdk，落地本仓客户端与认证实现

- 覆盖需求：R10
- 设计说明：

  当前引用分为两类，分别处理：

  **a) 仅类型引用**（改为本仓类型，不引入运行时实现）：

  | 现状 | 处理 |
  | --- | --- |
  | `MetadataInput`（`src/utils/handlers/metadataUpdateHelpers.ts`） | 改用 `@dashboard/graphql` 已有的 `MetadataInput` |
  | `AccountError`、`AccountErrorCode`（`src/utils/errors/account.ts`） | 改用 `@dashboard/graphql` 的 `AccountErrorCode` 与本地 `AccountError` 片段类型 |
  | `ChoiceValue`（`src/components/AddressEdit/useAddressValidation.ts`） | 在本地声明 `{ raw: string; verbose: string }` |
  | `ShippingMethodPostalCodeRule`（`src/shipping/views/RateUpdate.tsx`） | 在本地声明（`id`、`inclusionType`、`start`、`end`） |
  | `GetExternalAccessTokenData`、`GetExternalAuthUrlData`、`LoginData`（`src/auth/types.ts`、`src/auth/hooks/useAuthProvider.ts`） | 改为由新增的本地 GraphQL 操作派生类型 |
  | `UserDetailsFragment`（`src/utils/credentialsManagement.ts`） | 改用 `@dashboard/graphql` 的 `UserDetailsFragment` |

  **b) 运行时能力**（新增本仓模块 `src/auth/saleorClient/`，对外暴露与 SDK 同名的能力，替换点保持在原文件）：

  - `createSaleorClient({ apiUrl, channel })`：替换 `src/graphql/client.ts:90` 的调用，返回含 `auth`（`login`、`logout`、`setPassword`、`getExternalAuthUrl`、`getExternalAccessToken`、`refreshToken`）与 `config`（`apiUrl`、`channel`）的对象。
  - `SaleorProvider` / `useAuth` / `useAuthState` / `useSaleorConfig`：替换 `src/index.tsx:18,110` 的 Provider 与 `src/auth/hooks/useAuthProvider.ts:14,38,40`、`src/auth/views/NewPassword.tsx:3,13`、`src/components/AppLayout/AppChannelContext.tsx:6,37` 的 hook 调用，签名与返回值保持现有解构方式不变（`useAuth` → `{ login, logout, setPassword, getExternalAuthUrl, getExternalAccessToken }`；`useAuthState` → `{ authenticated, authenticating, user }`；`useSaleorConfig` → `{ setChannel }`）。
  - `createFetch()`：替换 `src/graphql/client.ts:38` 与 `src/components/DevModePanel/utils.ts:7` 的用法，保持「附加 `Authorization-Bearer` 请求头 + 访问令牌过期时刷新并重试一次」的行为，并继续与 `createUploadLink({ credentials: "include" })` 组合使用。
  - 需要的 GraphQL 操作（新增到 `src/auth/mutations.ts` / `src/auth/queries.ts`）：`tokenCreate`、`setPassword`、`externalAuthenticationUrl`、`externalObtainAccessTokens`、`tokenRefresh`、`tokensDeactivateAll`，以及用于认证状态的 `user` 查询。这些操作在 Base 中不存在（当前由 SDK 内部提供），属于本次新增。
  - 行为等价要求：登录（含凭据管理 API 分支）、外部认证跳转与回跳、登出、密码重置/设置、token 刷新失败时的登出与跳转逻辑均与 3.22 一致；`useAuthProvider` 中依赖 `authenticated`/`authenticating`/`user` 的状态机不改。
- 验证方法：`grep -rn "@saleor/sdk" src/ playwright/` 无输出；`pnpm run test src/auth src/components/AppLayout src/components/DevModePanel src/utils` 通过；`pnpm run check-types` 通过；`dash-e2e` 的 setup（登录）项目通过。

### FD03 · 图标体系迁移到 lucide-react

- 覆盖需求：R11
- 设计说明：把 9 个文件中的 `@material-ui/icons` 导入替换为 `lucide-react` 的等价图标（或 `src/icons/` 下已有的本地图标组件）：

  `src/productTypes/components/ProductTypeVariantAttributes/ProductTypeVariantAttributes.tsx`、`src/products/components/ProductStocks/components/CardAddItemsFooter.tsx`、`src/translations/components/TranslationFields/TranslationFields.tsx`、`src/extensions/components/AppWidgets/AppWidgets.tsx`、`src/components/CountryList/CountryList.tsx`、`src/components/Chip/Chip.tsx`、`src/components/ConfirmButton/ConfirmButton.tsx`、`src/channels/components/ChannelAllocationStrategy/ChannelAllocationStrategy.tsx`、`src/configuration/index.tsx`。

  替换时保持尺寸、颜色、`aria-label` 与布局类名不变；`eslint.config.mjs` 中 `local-rules/no-deprecated-icons` 维持现有级别即可（迁移完成后不再有违规），`@material-ui/icons` 从 `package.json` 移除（FD07）。
- 验证方法：`grep -rn "@material-ui/icons" src/` 无输出；`pnpm run lint` 通过；受影响组件的既有 jest 测试通过；受影响页面（产品类型、产品库存、翻译、App 挂件、国家列表、Chip、确认按钮、渠道分配、配置首页）人工/截图核对无视觉回归。

### FD04 · 前端基础能力依赖接入

- 覆盖需求：R12
- 设计说明：

  - `history@4.10.1`：`src/components/Router/index.tsx` 已 `import { createBrowserHistory } from "history"`，本次仅把 `history` 提升为直接依赖，不改代码。
  - `@react-editor-js/core@2.1.0`：`src/components/RichTextEditor/ReactEditorJS.tsx` 已从该包导入 `EditorCore`、`ReactEditorJS`，本次提升为直接依赖。
  - `moment@2.30.1`：`moment-timezone` 已是直接依赖，`moment` 作为其伴生包被多处间接使用（如 `src/components/DateTimeTimezoneField.tsx`、`src/products/utils/handlers.ts`），本次显式声明，不改变现有日期格式化行为。
  - `react-transition-group@4.4.5`：作为动画基础依赖显式声明；若本次未引入新的动画实现，则仅声明不改造现有动画路径。
  - `sonner@^2.0.7`：作为通知能力的直接依赖引入。现有通知链路为 `src/components/messages/`（`MessageManagerProvider` + `MessageDisplay`）与 `src/hooks/useNotifier`，`sonner` 的接入不得改变 `notify({ text, status, apiMessage })` 的调用契约与提示内容、状态、消失时机。
  - 上述依赖若在本次仅作为声明存在（`history`、`@react-editor-js/core`、`moment`、`react-transition-group`），不得为「用上依赖」而改动无关代码。
- 验证方法：`pnpm run test` 中通知、日期时间、路由、富文本编辑器相关用例通过；`pnpm run check-types` 通过。

### FD05 · 删除 3.23 计划移除的兼容代码

- 覆盖需求：R13
- 设计说明：删除 `src/products/urls.ts:97` 的 `productVariantLegacyEditPath` 及其 `@deprecated` 注释；删除 `src/products/index.tsx:134` 附近把旧路径 `/products/:productId/variant/:variantId` 重定向到 `/products/variant/:variantId` 的 `<Route>` 与相关注释。保留新路径 `productVariantEditPath`/`productVariantEditUrl` 及其页面。旧路径命中后按 404 处理（不再重定向）。
- 验证方法：`grep -rn "productVariantLegacyEditPath\|Remove in Saleor Dashboard 3.23" src/` 无输出；`pnpm run test src/products` 通过；产品变体编辑页在新路径下可用。

### FD06 · 工程脚本与 lint 规则

- 覆盖需求：R15
- 设计说明：`package.json` 的 `scripts` 按目标约定补齐/调整：

  - `generate:main` / `generate:staging`、`fetch-schema:main` / `fetch-schema:staging`，并让 `generate`、`fetch-schema` 聚合两条链路（见 FD01）。
  - `graphql-lint-unused`（未使用 GraphQL 字段检查）。
  - `test:lint-rules`：运行 `lint/rules/` 下的规则自测，至少包含 `named-styles` 与新增的命名副作用规则 `named-effects`；`test` 与 `test:ci` 在 jest 之后串联该脚本。
  - `test-storybook` / `test-storybook:coverage`（vitest storybook 项目）、`update-payment-assets`、`dev:no-strict`、`e2e:clean-auth`、`chromatic`。
  - 新增 lint 规则 `lint/rules/named-effects`：约束副作用写法需具名，与既有 `named-styles`（要求 `makeStyles`/`withStyles` 带 `name`）同构，注册进 `lint/rules/index.mjs` 与 `eslint.config.mjs`；规则自测文件按目标约定使用 `.mjs`。
  - 注意：现有 `lint/rules/named-styles.test.cjs` 中期望的报错文案（`"makeStyles hook should be named."`）与规则实现中的文案（`"makeStyles hook should be named property."`）不一致，规则自测在 Base 下无法通过；迁移到 `.mjs` 时需使期望文案与规则实现一致。
- 验证方法：`pnpm run test:lint-rules` 通过；`pnpm run test`、`pnpm run lint`、`pnpm run check-types` 通过。

### FD07 · 依赖与构建声明对齐

- 覆盖需求：R14、R01（dashboard 侧版本标识）
- 设计说明：

  - `package.json` 的 `version` 改为 `"3.23.0"`，`config.saleor.schemaVersion` 改为 `"3.23"`。
  - 依赖增删：移除 `@material-ui/icons`、`@saleor/sdk`；新增 `@react-editor-js/core@2.1.0`、`history@4.10.1`、`moment@2.30.1`、`react-transition-group@4.4.5`、`sonner@^2.0.7`。其余版本提升由环境补丁先行落地，本次不重复改动。
  - 包管理器与工作区声明（`.npmrc` 的 `shamefully-hoist=true`、`pnpm-workspace.yaml`、`pnpm-lock.yaml`）与目标一致；`.nvmrc` 已按目标移除。
  - 依赖声明必须与代码实际使用一致：不得保留已无引用的依赖，也不得使用未声明的隐式依赖（`history`、`@react-editor-js/core` 即为典型）。
- 验证方法：离线环境下 `pnpm run build` 成功；`pnpm run lint`、`pnpm run check-types`、`pnpm run test` 通过；`grep` 确认已移除依赖在 `src/`、`playwright/` 中无引用。

### FD08 · 前端回归与质量门禁

- 覆盖需求：R16
- 设计说明：本次前端改动不得改变既有回归行为，不得引入测试专用桩。回归范围为 `dash-unit`（jest）与 `dash-e2e`（Playwright `#e2e`，含 setup 登录项目）。本地执行：`/opt/runtime/run-suite.sh <attempt> dash-unit dash-e2e`。e2e 依赖本地 runtime 与种子数据，仅健康检查通过不算测试通过。
- 验证方法：改动前后失败集合的差集为空；评测阶段 fail-to-pass 用例全部通过、pass-to-pass 用例保持通过；未修改评测测试、夹具、verifier 与评分配置。

## 4. 依赖与联调

| 接口 | 消费方设计单元 | 对应需求 | 开发依赖 |
| --- | --- | --- | --- |
| I01 | FD01 | R02、R03 | 需等待（后端 BT02 提供字段、BT03 导出 schema） |
| I02 | FD01 | R02、R03 | 需等待（同上） |
| I03 | FD01 | R02、R03 | 需等待（后端 BT02 落地废弃标记） |
| I04 | FD01 | R02、R03 | 需等待（后端 BT02 落地废弃标记） |

联调安排与可独立开发的前提：

- **可独立开发**：FD02（去 SDK）、FD03（图标）、FD04（基础依赖）、FD05（兼容代码清理）、FD06（脚本与 lint）、FD07（依赖与版本）均不依赖后端进度，可立即开工。
- **需等待后端**：FD01 的产物再生成必须在 BT02/BT03 完成后执行，否则生成结果与后端契约不一致。等待期间可先用本阶段交付的 `target-schema.graphql` 作为 schema 输入完成本地验证——本次已用该文件对 dashboard 全部 GraphQL 文档做过校验（0 错误），说明契约已冻结、可据此并行开发。
- **需要的 mock**：无。契约以 SDL 文件形式提供，不需要 mock server；e2e 仍走本地 runtime。
- **待解决依赖**：staging 链路（`schema-staging.graphql` / `codegen-staging.ts`）在离线环境无法真正拉取 main 分支 schema，本次只落地脚本与配置，实际拉取留待联网环境验证。

## 5. 其他

### 5.1 风险与未决项

- **去 SDK 是本次改动面最大的部分**：`@saleor/sdk` 同时承担 Apollo 客户端构造、token 存取与刷新、外部认证流程，行为细节（cookie 名称、401 重试、登出清理）需要以现有测试与本地 runtime 的实际行为为准逐项对齐；建议按 FD02 的顺序先做类型替换、再做运行时替换，并保持每个替换点可独立回归。
- **`settings` 的消费方式已确定**：`useExtensions.ts` 用 `appExtensionManifestOptionsSchema.safeParse(settings)`，解析失败只记录错误并回退 `GET`，因此后端返回 `{}` 或 `{ newTabTarget: { method } }` 均安全；FD01 不需要为此增加兜底逻辑。
- **`mountName` 为 UPPER_CASE 成员名**：`ALL_APP_EXTENSION_MOUNTS.parse(mountName)` 不接受小写值，若后端返回小写会抛错并使扩展不可用；这是前后端联调时必须优先验证的点（已在 backend-design.md BD02 明确）。
- **未决项**：staging 链路的产物命名与目录结构未确证，FD01 只约束「两条链路互不覆盖、主链路使用 3.23 契约」；`sonner` 的接入范围（仅替换现有提示还是同时引入新交互）未确证，本次按「不改变现有通知契约」处理。
- 本阶段未执行前端构建与测试（无代码改动），验证项均属实施阶段任务。
