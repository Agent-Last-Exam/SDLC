# 前端技术设计：Saleor Core 与 Dashboard 协同升级到 3.23.0（Dashboard 部分）

版本：v1
责任：前端技术设计
依据：PRD v1，artifacts/sprint1/prd/prd.md
修订：首次交付

## 1. 方案概述

本设计只涉及 Dashboard 仓库 `/workspace/repos/saleor-dashboard`。基线为 3.22 加上环境补丁，补丁已经把包管理器切换到 pnpm 并调整了 jest 配置。目标是 3.23.0，工作分为以下几类：

1. **版本、依赖与构建声明**：
   - 用 `/opt/environment/dependencies/target/saleor-dashboard/{package.json,pnpm-lock.yaml,pnpm-workspace.yaml,.npmrc}` 覆盖仓库中的同名文件。
   - 依赖层面：移除 `@saleor/sdk`、`@material-ui/icons`；新增声明 `sonner`、`react-transition-group`、`history`、`moment`、`@react-editor-js/core`。后四个包代码中已在使用，此前属于隐式依赖，本次补齐声明。
   - 脚本层面：按目标清单补齐。
   - `Dockerfile` 与 CI workflow 从 npm 迁移到 pnpm，Node 升级到 24。
2. **schema 与生成产物**：
   - 根目录 `schema.graphql` 拆分为 `schema-main.graphql`（与 Core 3.23 一致）和 `schema-staging.graphql`。
   - `codegen.ts` 拆分为 `codegen-main.ts` 和 `codegen-staging.ts`。
   - 修复重复片段名，重新生成并提交 `src/graphql/*.generated.ts`。
3. **替换移除的依赖**：
   - 用本地鉴权模块 `src/auth/client/` 替代 `@saleor/sdk`。
   - 用 `lucide-react` 替代 9 处 `@material-ui/icons`。
   - 通知渲染层改用 `sonner`，`useNotifier` 契约保持不变。
4. **工程脚本与配置**：
   - 新增 lint 规则 `named-effects`，并为 lint 规则提供 ESM 测试。
   - 新增 `scripts/update-payment-assets.cjs`。
   - 新增 storybook vitest 项目。
   - 支持通过 `VITE_DISABLE_STRICT_MODE` 关闭 StrictMode。
5. **到期清理与缺陷修复**：
   - 删除旧版变体路径的重定向。
   - 修复集合分配商品后列表不刷新的问题（SALEOR_113）。
6. **与 Core 对齐**：
   - App 扩展消费 `mountName`、`targetName`、`settings`（I01，代码已经在使用，本次让 schema 与 Core 一致）。
   - 所有 mutation 文档的根 mutation 数不超过 4（I04）。
7. **发布说明**：在 `.changeset/` 中添加条目。

主要修改位置如下：

- 根目录配置：`package.json`、`pnpm-lock.yaml`、`pnpm-workspace.yaml`、`.npmrc`、`Dockerfile`、`codegen-main.ts`、`codegen-staging.ts`、`schema-main.graphql`、`schema-staging.graphql`、`graphql.config.ts`、`apollo.config.js`、`.prettierignore`、`eslint.config.mjs`、`vite.config.js`、`vitest.config.ts`、`.github/workflows/*.yml`
- 脚本与 lint 规则：`scripts/fetch-local-schema.cjs`、`scripts/update-payment-assets.cjs`、`lint/rules/*`
- `src/index.tsx`、`src/graphql/client.ts`
- `src/auth/**`
- `src/components/AppLayout/AppChannelContext.tsx`、`src/components/DevModePanel/utils.ts`
- `src/components/messages/**`
- 9 个使用图标的组件
- `src/products/{index.tsx,urls.ts}`
- `src/collections/components/CollectionProducts/CollectionProducts.tsx`
- `src/fragments/errors.ts`、`src/modelTypes/mutations.ts`
- `.changeset/*.md`

## 2. 需求覆盖

不由前端承接的需求：

- R02、R03、R04、R05、R17：仅涉及 Core。
- R05 的插件列表由 Core 直接过滤，Dashboard 不需要改动；接口依赖登记在 §4 的 I07。
- R09 前端不需要改代码。客户列表仍通过 `customers(filter: {search})` 查询，搜索语义的提升来自 Core（I06）。AC-09-4 中的 Dashboard 场景属于联调验证。

| 需求 | 设计单元 |
| --- | --- |
| R01 | FD01 |
| R06 | FD09 |
| R07 | FD02 |
| R08 | FD10 |
| R10 | FD01、FD03、FD04 |
| R11 | FD03 |
| R12 | FD04 |
| R13 | FD05 |
| R14 | FD06 |
| R15 | FD07 |
| R16 | FD08 |
| R18 | FD12 |
| R19 | FD11 |

## 3. 详细设计

### FD01 · 版本号、依赖清单、pnpm 构建与 CI
- 覆盖需求：R01、R10
- 设计说明：
  - **清单**：将目标目录中的 `package.json`、`pnpm-lock.yaml`、`pnpm-workspace.yaml`、`.npmrc` 原样复制到仓库根目录。复制后的状态如下：
    - `version` 为 `3.23.0`，`config.saleor.schemaVersion` 为 `3.23`。
    - `engines` 为 `node >=24 <25, pnpm >=10`，`packageManager` 为 `pnpm@10.28.1`。
    - 依赖与脚本和目标清单逐项一致。
  - 版本显示：`src/config.ts:207` 的 `APP_VERSION = CUSTOM_VERSION || v${packageInfo.version}` 不需要改，会自动显示 `v3.23.0`。配置页的 `coreVersion` 来自 `shop.version`（I05）。
  - 不联网。用 `pnpm install --frozen-lockfile --offline` 校验锁文件，`node_modules` 已经预装。
  - **Dockerfile**：
    - 构建阶段：
      - 使用 `FROM node:24-alpine AS builder`，执行 `RUN corepack enable pnpm`。
      - 安装依赖：`COPY package.json pnpm-lock.yaml pnpm-workspace.yaml .npmrc ./`，再 `RUN pnpm install --frozen-lockfile`。
      - 复制构建所需文件：`COPY codegen-main.ts codegen-staging.ts ./`、`COPY schema-main.graphql schema-staging.graphql ./`。
      - 构建：`RUN pnpm run build`。
    - 删除所有 `npm ci`、`package*.json` 和 `--legacy-peer-deps`。
    - 其余 ARG/ENV 和 nginx 运行阶段不变。
  - **CI**（`.github/workflows/*.yml`）：
    - 所有 `npm ci` 改为 `pnpm install --frozen-lockfile`，`npm run X` 改为 `pnpm run X`，并加入 `pnpm/action-setup` 步骤。
    - 仓库中没有 `.nvmrc`，所以 `actions/setup-node` 改为 `node-version: 24`。
    - 缓存 key 中的 `package-lock.json` 改为 `pnpm-lock.yaml`。
    - `main.yml` 中的 lockfile-lint 改为 `--path pnpm-lock.yaml --type npm`。
    - 删除 `.github/workflows/package.json` 和 `package-lock.json` 中残留的 npm 锁文件（若仅供 workflow 脚本使用，则保留 package.json 并改用 pnpm）。
  - **验证**：
    - 用脚本逐键比较 `package.json` 与目标清单。
    - 锁文件校验通过。
    - 执行 `pnpm run build`（vite），确认 nginx :9000 下登录页可以访问。
    - 检索 Dockerfile，确认没有 `npm ci` 和 `package-lock.json`。

### FD02 · schema 文件、codegen 拆分与生成产物一致
- 覆盖需求：R07
- 设计说明：
  - **schema 文件**：
    - `git mv schema.graphql schema-main.graphql`，内容替换为 Core 生成的 `saleor/graphql/schema.graphql`，应与 `target-schema.graphql` 一致，对应 BD07。
    - 新增 `schema-staging.graphql`。离线环境下先复制 main 的内容，以后由 `fetch-schema:staging` 更新。
    - 根目录 `schema.graphql` 删除（Q6：本设计选择完全改名，避免两份主 schema 不一致）。
  - **codegen**：
    - `codegen-main.ts`：基于现有 `codegen.ts`，`schema` 改为 `./schema-main.graphql`，`documents` 和 4 个 `generates` 目标保持不变（`src/graphql/{fragmentTypes,typePolicies,types,hooks}.generated.ts`）。
    - `codegen-staging.ts`：
      - `schema` 指向 `./schema-staging.graphql`，documents 相同。
      - 输出到 `src/graphql/staging/{fragmentTypes,typePolicies,types,hooks}.generated.ts`。hooks 的 `typesPath` 指向同目录，不覆盖 main 的产物。
      - 业务代码不引用 staging 产物。它的作用是提前发现与 Core 主干的不兼容。
    - 删除旧的 `codegen.ts`，避免无参数调用 `graphql-codegen` 时读到过期配置。
  - **引用同步**：
    - `graphql.config.ts`、`apollo.config.js`（`localSchemaFile`）改为 `schema-main.graphql`。
    - `scripts/fetch-local-schema.cjs` 的 `SCHEMA_FILE_PATH` 改为 `schema-main.graphql`。
    - `.prettierignore` 加入 `schema-*.graphql`，以及 `src/graphql/staging/`（如果 prettier 会处理到）。
    - `update-schema.yml` 改为执行 `pnpm run fetch-schema` 和 `pnpm run generate`，PR 描述中的文件名同步修改。
    - knip 配置中如有 `codegen.ts`，也同步修改。
  - **重复片段**：`src/fragments/errors.ts:375` 的 `pageTypeBulkDeleteErrorFragment` 所定义的片段名改为 `PageTypeBulkDeleteErrorFragment`，`src/modelTypes/mutations.ts:72`（批量删除 mutation）的展开改为 `...PageTypeBulkDeleteErrorFragment`。两个片段的字段相同，生成类型中对应的 payload 类型名会随之变化。实现时用 `grep` 确认没有手写代码引用这些类型名。
  - **生成**：执行 `pnpm run generate:main`，提交 `src/graphql/*.generated.ts`。执行 `pnpm run generate:staging`，提交 staging 产物（或将其加入 `.gitignore`，二选一；本设计选择提交，以保证 `tsc` 的输入稳定）。
  - **验证**：
    - AC-07-1：用 `findBreakingChanges` 双向比较 Core 与 `schema-main.graphql`。
    - AC-07-2：用 Core schema 校验 640 个定义，字段错误应为 0，重复片段应为 0。
    - AC-07-3：再次执行 `generate:main` 后 `git status` 无变化。
    - AC-07-4：`pnpm run check-types` 通过。

### FD03 · 用本地鉴权模块替代 `@saleor/sdk`
- 覆盖需求：R11、R10
- 设计说明：
  - **新增模块 `src/auth/client/`**，按原 SDK 的行为实现：
    - `storage.ts`：
      - refresh token 存在 `localStorage["_saleorRefreshToken"]`，外部登录插件 ID 存在 `localStorage["_saleorAuthPluginId"]`。键名与 SDK 相同，所以升级后已登录用户不需要重新登录。
      - access token 只存在内存中。
      - 提供 `getAccessToken`、`setTokens`、`getRefreshToken`、`getAuthPluginId`、`setAuthPluginId`、`clear` 等方法。
    - `mutations.ts`：在 `src/auth/mutations.ts` 中新增以下文档，纳入 codegen 并生成 hooks 和类型，每个文档只有 1 个根 mutation：
      - `TokenCreate`：`tokenCreate`，返回 `token`、`refreshToken`、`errors{...AccountErrorFragment}`、`user{...UserDetails}`
      - `TokenRefresh`：`tokenRefresh(refreshToken:)`
      - `TokenVerify`
      - `TokensDeactivateAll`
      - `ExternalAuthenticationUrl`
      - `ExternalObtainAccessTokens`
      - `ExternalRefresh`
      - `ExternalLogout`
      - `SetPassword`
    - `fetch.ts`：`createFetch({ refreshOnUnauthorized = true, tokenRefreshTimeSkew = 120 } = {})`，返回一个与 `fetch` 签名相同的函数。处理流程：
      1. `operationName` 为 `TokenRefresh` 或 `ExternalRefresh` 的请求直接透传，不附加令牌，避免递归刷新。
      2. 有 access token 时，用 `jwt-decode` 读取 `exp` 和 `owner`。如果距离过期不足 `tokenRefreshTimeSkew` 秒，先执行刷新：
         - 内部令牌（`owner === "saleor"`）调用 `tokenRefresh`。
         - 外部令牌调用 `externalRefresh(pluginId, input: {refreshToken})`。
         - 刷新使用模块级单例 `refreshPromise`，并发请求共享同一次刷新，结束后置空。
      3. 设置请求头 `authorization-bearer: <token>`，发出请求。
      4. 如果响应 `errors[].extensions.exception.code === "ExpiredSignatureError"`，执行一次刷新，然后带新令牌重试一次。
      5. 刷新失败（返回 errors 或没有 token）时：调用 `storage.clear()`，通知 AuthProvider 进入未登录状态，返回原响应。随后由 `useAuthRedirection` 跳转到登录页。
    - `AuthClientProvider.tsx`：替代 `SaleorProvider` 的 React 上下文，维护 `{ authenticated, authenticating, user }`。
      - 初始化时如果存在 refresh token，执行一次 `tokenRefresh`，成功则恢复会话（对应 SDK 的 autologin），期间 `authenticating=true`。
      - 对外提供 `useAuth()`：
        - `login({email, password})`：调用 `tokenCreate` 并保存令牌。
        - `logout({input})`：
          1. 读取 pluginId，然后清空 storage。
          2. 执行 `apolloClient.resetStore()`。
          3. 如果有 pluginId，调用 `externalLogout(pluginId, input)` 并返回其结果，`logoutData` 由现有逻辑解析后跳转。
          4. 否则，在已登录时调用 `tokensDeactivateAll`，失败时忽略。
        - `getExternalAuthUrl`、`getExternalAccessToken`（保存令牌和 pluginId）。
        - `setPassword({email, password, token})`：成功后保存令牌，实现自动登录。
      - 对外提供 `useAuthState()`。
      - 返回值的结构与 SDK 的 `FetchResult` 相同，即 `{ data, errors }`，因此 `useAuthProvider.ts` 中的现有分支（非 staff 用户登出、`loginAttemptDelay`、`loginError` 映射）不需要改逻辑。
  - **替换调用点**：
    - `src/index.tsx`：删除 `SaleorProvider` 和 `saleorClient`。在 `ApolloProvider` 内、`AuthProvider` 外包一层 `<AuthClientProvider>`，`resetStore` 需要 Apollo 客户端。
    - `src/graphql/client.ts`：
      - `fetch: createFetch() as typeof fetch` 改为从 `@dashboard/auth/client` 导入。
      - 删除 `createSaleorClient`、`saleorClient`，以及关于 SDK 的 TODO 注释。
      - 刷新类 mutation 由同一个 `apolloClient` 发出，并经过同一个 fetch，第 1 步的透传规则保证不会递归。
    - `src/auth/hooks/useAuthProvider.ts`、`src/auth/views/NewPassword.tsx`：`useAuth`/`useAuthState` 改为从本地模块导入。
    - `src/auth/types.ts`：`LoginData`、`GetExternalAuthUrlData`、`GetExternalAccessTokenData` 改为由生成的 mutation 类型别名得到，例如 `TokenCreateMutation`。
    - `src/components/DevModePanel/utils.ts`：`createFetch` 改为从本地模块导入，行为不变。
    - `src/components/AppLayout/AppChannelContext.tsx`：删除 `useSaleorConfig` 和 `setChannel` 的副作用。该 channel 只供 SDK 内部 checkout 等 API 使用，Dashboard 没有消费方。选中的频道仍保存在 `useLocalStorage("channel")` 中。
    - 类型导入：
      - `UserDetailsFragment`：改用本地生成类型。如果没有同名类型，就在 `src/auth/queries.ts` 中使用现有的 `UserDetails` 片段类型（`UserDetailsQuery["me"]`）。
      - `MetadataInput`、`AccountErrorCode`/`AccountError`（使用 `AccountErrorFragment`）：改用本地生成类型。
      - `ProductType`：fixtures 中使用 `ProductTypeFragment` 或对应查询的类型。
      - `ShippingMethodPostalCodeRule`：使用 `ShippingMethodWithPostalCodesFragment["postalCodeRules"][number]` 等生成类型。
      - `ChoiceValue`：使用 `AddressValidationRulesQuery` 中的 choice 类型，或者本地定义 `{ raw: string | null; verbose: string | null }`。
      - 以上全部从 `@dashboard/graphql` 导入。
  - **失败处理**：
    - 登录失败、非 staff 账号、限流：沿用 `useAuthProvider` 中的现有映射。
    - refresh token 失效：清空会话，重定向到登录页。
    - 网络错误：不清空会话，由 Apollo 报错。
  - **权限**：只在客户端维护令牌，不涉及新权限。
  - **验证**：
    - 检索 `src/` 中的 `from "@saleor/sdk`，结果应为空。
    - 执行 `check-types`。
    - 在运行时环境中逐条执行 AC-11-1~6。
    - Playwright `auth.setup.ts` 和 `login.spec.ts`。

### FD04 · 用 lucide-react 替换 `@material-ui/icons`
- 覆盖需求：R12、R10
- 设计说明：
  - 9 处替换使用已依赖的 `lucide-react@0.555.0`，按语义对应：

    | 文件 | 原图标 | 新图标 |
    | --- | --- | --- |
    | `src/productTypes/components/ProductTypeVariantAttributes/ProductTypeVariantAttributes.tsx` | `HelpOutline` | `CircleHelp` |
    | `src/channels/components/ChannelAllocationStrategy/ChannelAllocationStrategy.tsx` | `HelpOutline` | `CircleHelp` |
    | `src/products/components/ProductStocks/components/CardAddItemsFooter.tsx` | `Add` | `Plus` |
    | `src/translations/components/TranslationFields/TranslationFields.tsx` | `ArrowDropDown` | `ChevronDown` |
    | `src/components/CountryList/CountryList.tsx` | `ArrowDropDown` | `ChevronDown` |
    | `src/extensions/components/AppWidgets/AppWidgets.tsx` | `Launch` | `ExternalLink` |
    | `src/components/Chip/Chip.tsx` | `Close` | `X` |
    | `src/components/ConfirmButton/ConfirmButton.tsx` | `Check` | `Check` |
    | `src/configuration/index.tsx` | `PaymentOutlined` | `CreditCard` |

  - **尺寸与样式**：
    - Material 图标默认 24px，`fontSize="small"` 时为 20px。lucide 图标需要显式设置 `size`，与原尺寸保持一致。
    - 已有的 `style`、`className`、`sprinkles` 属性原样传入，例如 AppWidgets 中的 16px 和 `verticalAlign`。
    - 原来通过 CSS 旋转的箭头，`className` 保持不变。
  - **测试选择器**：`data-test-id`（例如 ConfirmButton 的 `button-success`）、`aria-*`、`onClick` 原样放到 lucide 组件或其包裹元素上。lucide 组件会把多余属性透传给 `<svg>`。
  - **lint**：`eslint.config.mjs` 中的 `local-rules/no-deprecated-icons` 保持现有级别。替换后不应再有命中。
  - **验证**：
    - AC-10-3/12-1：检索 `@material-ui/icons`，结果应为空。
    - 运行 ESLint。
    - 运行 `ConfirmButton.test.tsx` 等 dash-unit。
    - 在运行时环境中手工检查配置页、库存卡片“添加”和 Chip 关闭（AC-12-2~4）。
    - `jest.config.js` 中 `^@material-ui/icons$` 的 `moduleNameMapper` 由环境补丁维护，属于测试基础设施，本次不改。源码不再引用该包后，这条映射不会被命中，不影响测试。

### FD05 · 通知渲染改用 sonner
- 覆盖需求：R13
- 设计说明：
  - **保持不变的 API**：
    - `useNotifier()`、`MessageContext`、`IMessage` 的字段（`status`、`title`、`text`、`apiMessage`、`actionBtn`、`autohide`）。
    - `useMessageState` 的计时逻辑，包括 `show`、`remove`、`clearErrorNotifications`、`pauseTimer`、`resumeTimer`，以及 `DEFAULT_NOTIFICATION_SHOW_TIME`。
    - 现有的 `useMessageState.test.tsx`、`MessageManagerProvider.test.tsx` 对应的行为也保持不变。
  - **渲染层**（`src/components/messages/MessageDisplay.tsx`）：
    - 删除 `TransitionGroup`、`Transition`、`Container` 和 radix `Portal`。改为渲染一次 `<Toaster position="top-right" expand visibleToasts={...} />`。
    - 用 `useEffect` 比较 `notifications` 的增减：
      - 新增的通知调用 `toast.custom(id => <NotificationItem .../>, { id: n.id, duration: Infinity })`。
      - 已移除的通知调用 `toast.dismiss(n.id)`。
    - `duration: Infinity` 表示自动隐藏仍由现有的 `useMessageState` 定时器决定，从而保留悬停暂停（`onMouseEnter` → `pauseTimer`，`onMouseLeave` → `resumeTimer`）和剩余时间的语义。
  - **`NotificationItem`**：
    - 继续使用 macaw-ui 的 `Notification` 组件渲染内容，把现有 props 原样迁移过来（`type`、`title`、`content`、`apiMessage` 的展开/收起、`action`、`onClose`）。
    - 该组件自带 `data-test-type={status}` 和 `data-test-id="notification"`，E2E 选择器不变。
    - 外层 `div` 也显式设置 `data-test-type`，防止组件内部结构变化。不过这样同一个值会出现两次，Playwright 的 `locator.first()` 不受影响。实现时检查 `commonLocators` 的用法；如果严格模式下会命中多个元素，就只保留组件自带的那一个。
    - 关闭按钮调用 `notification.close()`，由状态移除后统一 dismiss。
  - **样式**：迁移 `styles.ts` 中的 `notification` 类名，sonner 默认样式通过 `unstyled` 或 `toastOptions.className` 关闭，外观保持一致。
  - `Transition.tsx` 和 `Container.tsx` 不再使用，予以删除。`react-transition-group` 仍被其他代码使用，并已在目标清单中声明。
  - **验证**：
    - 运行 dash-unit 中 messages 目录的测试。
    - 按 AC-13-1~5 手工检查。
    - Playwright 中所有依赖 `successBanner` 的场景。

### FD06 · 工程脚本、lint 规则、严格模式与 storybook 测试
- 覆盖需求：R14
- 设计说明：
  - **`lint/rules/named-effects.cjs`**：
    - 规则检查 `useEffect`、`useLayoutEffect`、`useInsertionEffect` 调用的第一个参数（包括 `React.useEffect` 写法）。如果是 `ArrowFunctionExpression` 或匿名 `FunctionExpression`，就报告 `"Effect callback should be a named function."`。
    - 合法写法：`useEffect(function syncChannel() {...}, deps)`，或传入已命名的函数标识符。
    - 不提供 autofix。
    - 在 `lint/rules/index.mjs` 中以 `"named-effects"` 名称注册。
    - `eslint.config.mjs` 中设为 `"local-rules/named-effects": "off"`。现有代码中约有 335 处匿名 effect，启用会导致 lint 失败。规则以可用状态交付，后续逐步开启。
  - **lint 规则测试**：
    - 新增 `lint/rules/named-styles.test.mjs`，内容由现有 `.cjs` 测试转为 ESM：
      - 通过 `createRequire(import.meta.url)` 加载 `.cjs` 规则和 `@typescript-eslint/parser`。
      - ESLint 9 的 `RuleTester` 使用 flat 配置：`new RuleTester({ languageOptions: { parser } })`。
    - 新增 `named-effects.test.mjs`，覆盖以下用例：
      - 合法：具名 function、标识符引用。
      - 非法：箭头函数、匿名 function、`React.useEffect(() => {})`。
    - 旧的 `named-styles.test.cjs` 删除，以 `.mjs` 版本为准。
    - `RuleTester.run` 失败时抛出异常，使退出码非 0。
  - **`scripts/update-payment-assets.cjs`**：
    - 维护者手动运行的脚本，不接入构建。它从 `--source <dir|url>` 参数读取支付方式图标（SVG），用于更新 `assets/images/payment-methods/`。
    - 处理步骤：校验文件名白名单；去掉 SVG 中的 `<script>` 和事件属性；写出 `index.json` 清单。
    - 没有参数时打印用法并以 0 退出。
    - 只依赖 Node 内置模块，确保 `node --check` 通过且离线可执行。
  - **严格模式**：
    - `vite.config.js` 解构 `VITE_DISABLE_STRICT_MODE`，加入 `define` 的 `process.env`，与现有写法一致。
    - `src/index.tsx:335` 改为：
      ```tsx
      const disableStrictMode = process.env.VITE_DISABLE_STRICT_MODE === "true";
      root.render(disableStrictMode ? <App /> : <StrictMode><App /></StrictMode>);
      ```
    - 当前根组件没有包裹 StrictMode，改动后默认会启用 StrictMode。StrictMode 下开发模式会双重执行 effect，生产构建不受影响。上线前需要在开发模式下回归登录和通知等依赖 effect 的流程。如果出现问题，可以用 `dev:no-strict` 绕过。
  - **storybook vitest**：
    - 新增 `vitest.config.ts`，定义 `test.projects: [{ extends: true, plugins: [storybookTest({ configDir: ".storybook" })], test: { name: "storybook", browser: { enabled: true, provider: playwright(), instances: [{ browser: "chromium" }], headless: true } } }]`，供 `test-storybook` 和 `test-storybook:coverage` 使用。
    - 新增 `.storybook/vitest.setup.ts`。
    - jest 的 `roots: ["src"]` 与 `testRegex` 不会匹配到 vitest 的配置文件。
  - **其他脚本**：`e2e:clean-auth`、`dev:no-strict`、`graphql-lint-unused`、`chromatic` 只调用已安装的命令或已有文件，不需要额外创建文件。
  - **验证**：
    - AC-14-1：`pnpm run test:lint-rules`。
    - AC-14-2：`pnpm run lint:eslint` 不新增错误。
    - AC-14-3：`node --check scripts/update-payment-assets.cjs`。
    - AC-14-4：`dev:no-strict` 下检查根组件是否包裹 StrictMode。

### FD07 · 删除旧版变体路径重定向
- 覆盖需求：R15
- 设计说明：
  - 删除 `src/products/index.tsx:25` 中 `productVariantLegacyEditPath` 的导入，以及第 132–150 行的注释和 `<Route ... render={Redirect}>` 整块代码。如果 `Redirect` 不再有其他用途，同时删除其导入。
  - 删除 `src/products/urls.ts:97-99` 中 `productVariantLegacyEditPath` 的定义。
  - 其他商品路由的顺序保持不变。旧格式路径 `/products/:productId/variant/:variantId` 此后会被 `productPath(":id")` 前缀匹配，进入商品详情路由。
  - 验证：检索 `productVariantLegacyEditPath`，结果应为空；手工检查 `/products/variant/<id>` 和从商品详情页进入变体的流程（AC-15-2）。

### FD08 · 集合分配商品后即时刷新
- 覆盖需求：R16
- 设计说明：
  - **问题**：`CollectionAssignProduct` 由 `collectionAddProducts` 和 `collectionReorderProducts` 组成。当 `moves` 中的商品此前不在集合内时，reorder 返回的 `collection.products` 不能稳定反映新增的商品；而 `collectionAddProducts` 只返回 `errors`，所以 Apollo 缓存不会更新 `CollectionProducts` 查询。
  - **方案**：在 `src/collections/components/CollectionProducts/CollectionProducts.tsx:67` 中，为 `useCollectionAssignProductMutation` 增加以下配置：
    ```ts
    refetchQueries: ["CollectionProducts"],
    awaitRefetchQueries: true,
    ```
    - 这样会按当前 `{ id, ...paginationState }` 变量重新获取列表，`handleAssignationChange` 会等列表刷新完成后再关闭对话框。
    - 成功通知（`onCompleted`）不变。
    - 解除分配（`useUnassignCollectionProductMutation`）同样加上 `refetchQueries: ["CollectionProducts"]`，保证两个方向一致。
  - **约束**：不修改 mutation 文档，根 mutation 数仍为 2，满足 I04 的限制。
  - **失败处理**：mutation 返回 errors 时，`onCompleted` 不发送成功通知，沿用现有的错误通知逻辑。refetch 失败时由 Apollo 的错误链路提示。
  - **验证**：在运行时环境中执行 SALEOR_113 场景（AC-16-1/2）。

### FD09 · App 扩展字段消费与 Core 对齐
- 覆盖需求：R06
- 设计说明：
  - 现有代码已经读取新字段：
    - `src/extensions/queries.ts:111-119` 中的 `appExtensions` 查询读取 `mountName`、`targetName`、`settings`。
    - `src/extensions/hooks/useExtensions.ts` 使用 `appExtensionManifestOptionsSchema`（zod，位于 `src/extensions/domain/app-extension-manifest-options.ts`）校验 `settings`，并按 `targetName` 判断 NEW_TAB 或 WIDGET。
    - `src/extensions/components/AppWidgets/AppWidgets.tsx` 读取 `settings.widgetTarget.method`。
  - 前端不需要修改代码。正确性取决于 Core 按 I01 返回大写枚举名，以及 camelCase 的 `settings`（`{newTabTarget|widgetTarget:{method:GET|POST}}`）或 `{}`。zod 中这两个键都是 optional，所以 `{}` 能通过校验。
  - manifest 片段 `src/fragments/apps.ts` 继续读取 `mount`、`target`（I02 中仍可用，但已标注 deprecated），本次不改，以免影响现有 fixtures 和测试。
  - 失败处理沿用现有逻辑：`settings` 校验失败时，`open()` 输出 `console.error("Invalid extension configuration")` 并且不打开扩展。
  - 验证：FD02 完成后，codegen 和 tsc 通过；在运行时环境中按 AC-06-5 检查商品列表的“创建”扩展（NEW_TAB+POST）和订单详情 WIDGET，确认控制台没有 "Invalid extension configuration"。

### FD10 · mutation 文档的根 mutation 数量不超过 4
- 覆盖需求：R08
- 设计说明：
  - 现状统计：最大为 `VariantUpdate`（4），其次是 `MenuUpdate`（3），另有 5 个文档为 2。都在运行时限值 4 以内。
  - 本次新增或修改的 mutation 文档都只有 1 个根 mutation，即 FD03 中的鉴权 mutation；FD08 没有修改文档。
  - 增加一个静态检查脚本 `scripts/check-mutation-count.cjs`，在 CI 的 `main.yml` 中运行：
    - 用 `graphql` 解析 codegen 覆盖的所有文档，统计每个 mutation 操作的根字段数（展开片段，alias 各计一次），超过 4 时退出码为 1。
    - 统计口径与 BD08 / I04 一致。
  - 超限时的用户体验：Core 返回 HTTP 400 和 `MutationCountLimitError`，Apollo 抛出网络错误，由现有的错误通知链路显示错误通知（`[data-test-type="error"]`），不会静默失败。
  - 验证：运行该脚本，最大值应为 4。在运行时环境中按 AC-08-5 编辑并保存一个变体，确认出现成功通知。

### FD11 · 发布说明
- 覆盖需求：R19
- 设计说明：在 `.changeset/` 下按 changesets 格式新增 4 个文件。frontmatter 为 `"saleor-dashboard": minor` 或 `patch`，正文用英文描述变更：
  - 用本地实现替代 `@saleor/sdk`
  - 用 lucide 替换 `@material-ui/icons`，通知改用 sonner
  - 删除旧版变体路径重定向，修复集合分配商品后的刷新
  - pnpm/Node 24、schema 3.23、codegen-main/staging、`named-effects` 规则

  验证：`pnpm run change:status` 能识别这些条目。

### FD12 · 回归保护与测试收集
- 覆盖需求：R18
- 设计说明：
  - 不修改任何 `*.test.ts(x)`、`playwright/**`、`testUtils` fixtures 或 `/opt/runtime` 中的文件。
  - **已知风险**（PRD Q1）：
    - `src/auth/AuthProvider.test.tsx`、`src/auth/hooks/useAuthProvider.test.ts`、`src/components/DevModePanel/utils.test.ts` 中有 `jest.mock("@saleor/sdk")`。
    - 包从清单中移除后，`node_modules` 中仍有预装的副本，jest 能够解析，因此这些测试不会出现收集失败。
    - 但这些 mock 不再作用于生产代码。依赖 mock 返回值的断言可能失败，例如 `useAuthProvider.test.ts` 通过 mock 控制 `useAuth`、`useAuthState`。
    - 处理原则：不修改测试，以官方测试为准。生产代码的模块路径与导出名尽量贴近原 SDK 的使用方式，具体是 `useAuthProvider` 内调用 `useAuth()`、`useAuthState()`，便于官方测试改为 mock `@dashboard/auth/client`。
    - 交付时在报告中列出受影响的测试。
  - **收集验证**：执行 `pnpm exec jest --listTests` 和 `dash-unit`，确认没有 "Test suite failed to run"；dash-e2e 的健康检查通过后，测试能实际执行。

## 4. 依赖与联调

| 接口 | 消费方设计单元 | 对应需求 | 开发依赖 |
| --- | --- | --- | --- |
| I01 | FD09、FD02 | R06、R07 | 可独立开发 |
| I02 | FD02 | R06、R07 | 可独立开发 |
| I03 | FD02 | R07 | 可独立开发 |
| I04 | FD10、FD08 | R08、R16 | 可独立开发 |
| I05 | FD01 | R01 | 需等待 |
| I06 | FD12 | R09 | 需等待 |
| I07 | FD12 | R05 | 需等待 |

- **可独立开发的前提**：
  - I01–I03 的 SDL 已固定在 `target-schema.graphql`，与 Dashboard 现有 schema 一致。FD02 直接用它生成产物，不需要等 Core 实现。
  - I04 是纯静态约束，FD10 的脚本可以单独完成。
  - FD03–FD08、FD11 只依赖 Base 已有的接口，可以立即开工。
- **需要等待的联调**：
  - I05：版本显示需要 Core 的 BT01。
  - I06：客户搜索 E2E 需要 Core 的 BT08 和播种脚本。
  - I07：插件列表需要 Core 的 BT04。
  - I01 的运行时行为（AC-06-5）需要 Core 的 BT06。
  - 以上项目都在两端部署到运行时环境（API :8000、Dashboard :9000，`GRAPHQL_MUTATION_COUNT_LIMIT=4`）后联调。
- **mock**：
  - 不新增测试专用的 mock 或桩代码。
  - 开发期间如需本地验证 I01，可以用已有的 `src/extensions` 单测 fixtures（其中已经使用 `mountName` 和 `settings`）。
- **待解决的依赖**：Q6 schema 文件命名（本设计选择删除 `schema.graphql`）。如果维护者要求保留，只需恢复一个与 `schema-main.graphql` 相同的副本，并且不被任何配置引用。

## 5. 其他

- **风险**：
  - FD03 替换 SDK 后，`jest.mock("@saleor/sdk")` 不再生效，相关单测可能失败（PRD Q1），以官方测试为准。
  - FD06 启用 StrictMode 后，开发模式下 effect 会双重执行，需要回归。
  - FD05 中，sonner 的堆叠动画与 macaw 的过渡效果有细微差异，不影响 E2E 选择器。
- **验证计划**（研发阶段执行）：
  1. `pnpm install --frozen-lockfile --offline`
  2. `pnpm run generate:main`，然后检查 `git status` 无变化
  3. `pnpm run check-types`
  4. `pnpm run lint:eslint` 和 `test:lint-rules`
  5. `pnpm exec jest`（dash-unit）
  6. `pnpm run build`
  7. 在运行时环境中执行 Playwright（dash-e2e），重点覆盖 `auth.setup.ts`、`login.spec.ts`、customers、collections（SALEOR_113）、变体保存
  8. 运行 `scripts/check-mutation-count.cjs`
- **本阶段已完成的检查**：
  - 用目标 SDL 校验 Dashboard 文档：字段错误为 0，重复片段为 1（由 FD02 处理），根 mutation 最大为 4。
  - 目标 `package.json` 与当前文件的差异仅包括依赖增删和新增脚本，与本设计的覆盖范围一致。
- **本阶段未运行**：codegen、tsc、jest、构建、E2E。
- **未决项**：Q1（受 SDK mock 影响的测试）、Q6（schema 文件命名）。`named-effects` 本次以 `off` 级别交付，由研发和维护者决定后续启用节奏。
