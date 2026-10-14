# 前端技术设计：Saleor Dashboard 3.22.9 → 3.23.0 协调升级（前端部分）

版本：v1
责任：前端技术设计
依据：PRD v1，artifacts/sprint1/prd/prd.md
修订：首次交付

## 1. 方案概述

### 1.1 关键事实核查结论（设计前提）

对 dashboard 基线（`aebb240`，`/workspace/repos/saleor-dashboard`）的源码核查结论：

1. **3.23 功能面在前端基线中已基本就绪**：
   - App Extension：`src/extensions/` 完整实现 NEW_TAB（`new-tab-actions.ts` 的 `openPOSTinNewTab`/GET 打开）、WIDGET（`components/AppWidgets/AppWidgets.tsx` iframe 渲染）、挂载点过滤（`domain/app-extension-manifest.ts`、`app-extension-manifest-available-mounts.ts`），且 `queries.ts` 的 `extensionList` 查询已使用 `mountName`/`targetName`/`settings` 新字段。
   - 退款设置：`src/refundsSettings/`（`route.tsx`、`views/index.tsx`、`components/RefundsSettingsPage`、`mutations.ts`、`queries.ts`）已提供原因引用类型的设置/清除入口；退款表单侧 `OrderGrantRefundPage` 已有 `refundReasonInput` 输入域，`src/orders/mutations.ts` 已传 `refundReason`/`refundReasonReference`。
   - 订单列表：`src/orders/queries.ts` 已使用 `where: OrderWhereInput` + `search` 参数；订单详情新版视图位于 `src/ordersV2/`（ViewModel 架构）。
2. **构建工具链已由环境补丁完成 npm→pnpm 迁移**：`pnpm-workspace.yaml`、`pnpm-lock.yaml`、`.npmrc`（`shamefully-hoist=true`）、`package.json` scripts 已 pnpm 化、`jest.config.js` 的 `transformIgnorePatterns` 已适配 pnpm 目录结构。本设计不回退其中任何一项。
3. **确定的缺失项为版本与 schema 对齐**：
   - `package.json:3` 为 `"version": "3.22.9"`，`:52` 为 `"schemaVersion": "3.22"`；
   - 仓库根 `schema.graphql`（959,353 字节）是后端 3.23 契约的超集对齐版（含 `mountName`/`targetName`/`settings`），在 core 完成 BD06 后与之完全一致；
   - codegen（`codegen.ts`，schema 源为 `./schema.graphql`）需要以最终 schema 重新执行，刷新 `src/graphql/types.generated.ts`、`hooks.generated.ts`、`fragmentTypes.generated.ts`、`typePolicies.generated.ts` 四个产物。

### 1.2 整体方案

dashboard 仓库改动收敛为一个设计单元：

- **FD01（版本与 GraphQL 契约对齐）**：`package.json` 版本升级至 `3.23.0`、`config.saleor.schemaVersion` 升至 `"3.23"`；以 target-schema（= core BD06 完成后的服务端 schema）为输入重跑 `pnpm run generate`，刷新四个生成产物；全仓类型检查与单测回归。

3.23 功能行为（FD02–FD05）经核查已存在于基线代码，本设计以"确认 + 回归验证"方式承接，不引入行为性改动；R11/R12 由 FD06 承接为验证守护。前端不承接的需求：R01、R03（core 侧）、R04–R09 的服务端实现部分（见 backend-design.md）。

数据流依据：Dashboard 为 React 18 + Apollo Client 3 单页应用（`src/index.tsx` 入口，`src/graphql/client.ts` Apollo 装配）；所有后端交互经由 codegen 生成的 hooks（`src/graphql/hooks.generated.ts`）与类型（`types.generated.ts`），因此"schema 副本 + 生成产物"即前后端契约的物理载体，是本次前端改动的核心。

## 2. 需求覆盖

| 需求 | 设计单元 |
| --- | --- |
| R02 | FD01 |
| R07 | FD02 |
| R09 | FD03 |
| R04 | FD04 |
| R08 | FD05 |
| R10 | FD01（pnpm 守护部分） |
| R11 | FD06 |
| R12 | FD06 |

不适用或未覆盖的说明：R01（后端版本声明）、R03（数据库迁移）无前端职责；R05（draftOrders/pages 查询）、R06（属性体系）为纯后端契约，前端无直接消费改动（页面/属性相关界面使用既有查询与 fragments，随 FD01 的 codegen 重生成自动获得类型一致性）。

## 3. 详细设计

### FD01 · 版本声明与 GraphQL Schema/生成产物对齐
- 覆盖需求：R02、R10（pnpm 守护）
- 设计说明：
  - **改动点 1（版本声明）**：`package.json` `"version": "3.22.9"` → `"3.23.0"`；`config.saleor.schemaVersion` `"3.22"` → `"3.23"`（该值被 `fetch-schema` 脚本用于按版本拉取 schema，是前后端版本一致性的声明锚点）。
  - **改动点 2（schema 副本）**：仓库根 `schema.graphql` 与 core 完成 BD06 后的 `saleor/graphql/schema.graphql` 保持一致。核查结论：dashboard 基线的副本已含 `mountName`/`targetName`/`settings` 目标形态，与 target-schema.graphql 逐字节一致，因此预期**无需改动**；实施时以 `diff` 复核，若 core 端 BD06 产出任何额外差异，以 target-schema 为准同步本文件。
  - **改动点 3（生成产物）**：执行 `pnpm run generate`（graphql-codegen，输入 `./schema.graphql` + `src/**/{queries,mutations,fragments,searches}.ts`），刷新四个产物文件；随后 `pnpm run check-types`（`tsc --noEmit && tsc-strict`）必须零错误。若重生成导致既有调用点类型漂移（预期无——基线代码已按 `mountName`/`targetName`/`settings` 编写），在对应 `.ts/.tsx` 消费文件做最小适配。
  - **pnpm 守护**：不新增 `package-lock.json`、不修改 `pnpm-workspace.yaml`/`.npmrc`/`jest.config.js` 的 pnpm 适配；如 3.23 需要依赖调整（预期无），只改 `package.json` + `pnpm-lock.yaml`。
  - **状态与失败处理**：codegen 失败（文档语法/schema 校验）即构建失败，属预期快速失败；不做容错降级。
  - 验证方法：`pnpm run generate && pnpm run check-types` 通过；`node -e "const p=require('./package.json'); console.log(p.version, p.config.saleor.schemaVersion)"` 输出 `3.23.0 3.23`；`diff schema.graphql <core 侧生成文件>` 为空（AC-02-1～AC-02-3、AC-10-1～AC-10-2）。

### FD02 · 退款设置与退款原因交互确认
- 覆盖需求：R07（前端部分：AC-07-5）
- 设计说明：
  - 现有代码路径：配置页 `src/refundsSettings/route.tsx`（挂载到配置区路由）→ `views/index.tsx` → `components/RefundsSettingsPage`；数据流 `queries.ts`（读取 `shop.refundSettings`）/`mutations.ts`（`refundSettingsUpdate`、`refundReasonReferenceClear`）。退款操作侧：`src/orders/components/OrderGrantRefundPage/OrderGrantRefundPage.tsx` 的 `refundReasonInput`（第 200 行附近）与 `src/orders/mutations.ts` 中携带 `reasonReference` 的变量。
  - 交互语义（现状确认项）：商家在配置页选择某个 Model Type（PageType）作为退款原因引用类型并可清除；staff 在退款表单中选择该类型的 Model 作为原因并提交 `reasonReference`；未配置时不展示必填阻塞。
  - 本轮**无代码改动**；验证方法：`src/refundsSettings` 与退款相关组件的既有单测通过；dash-e2e 中退款流程用例通过（AC-07-5）。

### FD03 · App Extension NEW_TAB / WIDGET 交互确认
- 覆盖需求：R09（前端部分：AC-09-1、AC-09-2）
- 设计说明：
  - 现有代码路径：扩展数据 `src/extensions/queries.ts`（`extensionList` 使用 `mountName`/`targetName`/`settings`）→ 按挂载点分发 `getExtensionsItems.ts` → 动作类入口 `components/ExtensionsButtonSelector`、详情页 widget 渲染 `components/AppWidgets/AppWidgets.tsx`；NEW_TAB 打开逻辑 `new-tab-actions.ts`（GET 直接 `window.open`，POST 构造隐藏 `<form target="_blank">` 提交，附带 `accessToken`/`appId`/`saleorApiUrl` 与页面上下文参数）；安装期校验 `domain/app-extension-manifest.ts`（WIDGET 仅限 widget 挂载点、options 与 target 一致性）与 `domain/extension-manifest-validator.ts`。
  - 依赖前提：FD03 的运行依赖 core 完成 BD06（`mountName`/`targetName`/`settings` 在服务端可解析）——在此之前 `extensionList` 查询对 3.22 服务端会报错，属于本轮必须消除的跨端不一致。
  - 本轮**无代码改动**；验证方法：`src/extensions/**/*.test.ts(x)`（含 `new-tab-actions.test.ts`、`getExtensionsItems.test.ts`、`app-extension-manifest-options.test.ts` 等）通过；联调环境下 NEW_TAB 扩展按 GET/POST 正确打开、WIDGET 扩展在详情页 iframe 渲染（AC-09-1、AC-09-2）。

### FD04 · 订单列表过滤/搜索消费确认
- 覆盖需求：R04（前端消费部分）
- 设计说明：
  - 现有代码路径：`src/orders/queries.ts` 第 9–19 行已声明 `$where: OrderWhereInput`、`$search: String` 并传入 `orders` 查询；列表 UI 的过滤构造在 `src/orders/` 过滤栏组件内，URL 参数序列化沿用既有 `useSearchQuery`/qs 机制。
  - 本轮**无代码改动**；验证方法：订单列表相关单测与 dash-e2e 订单过滤/搜索用例通过（配合 AC-04-1～AC-04-4 的后端判定）。

### FD05 · 交易明细（paymentMethodDetails）展示确认
- 覆盖需求：R08（前端消费部分）
- 设计说明：
  - 现有代码路径：订单详情的交易区块位于 `src/ordersV2/OrderDetailPage.tsx` 及 `src/orders/components/` 交易相关组件；`paymentMethodDetails` 的类型在 FD01 重生成后进入 `types.generated.ts`。
  - 本轮**无代码改动**（基线未展示新字段时不新增 UI，避免引入未经 PRD 要求的界面变更）；如官方 dash 测试要求展示支付方式明细，在修复阶段以最小组件适配补入并修订本条目。验证方法：交易区块既有测试通过；类型检查通过（AC-08-1～AC-08-4 的后端判定不受影响）。

### FD06 · 回归守护与交付约束
- 覆盖需求：R11、R12
- 设计说明：
  - 回归守护：改动仅限 FD01 的声明与生成产物；禁止测试环境特判与硬编码 stub；废弃字段（`mount`/`target`/`options` 等）在生成类型中标记 `@deprecated` 但保持可用，前端不主动迁移既有旧消费点（既有消费点已在新字段上，见 FD03）。
  - 交付约束：改动作为普通源码编辑提交至 dashboard 工作树（相对基线 `aebb240` 的 diff）；不触碰 `playwright/` 评估资产、fixtures、评分配置；全程离线（generate/build 使用本地 `node_modules`，不联网装包）。
  - 验证方法：`pnpm run test`（jest）与 `run-suite.sh <attempt> dash-unit dash-e2e` 通过；`git diff --stat` 预期仅含 `package.json`、`schema.graphql`（如有同步）、`src/graphql/*.generated.ts`（及可能的消费点微调）（AC-11-1～AC-11-3、AC-12-1、AC-12-2）。

## 4. 依赖与联调

| 接口 | 消费方设计单元 | 对应需求 | 开发依赖 |
| --- | --- | --- | --- |
| I06 | FD01、FD03 | R02、R09 | 需等待（core BD06 提供 `mountName`/`targetName`/`settings` 后，codegen 与运行时方可对齐） |
| I04 | FD02 | R07 | 可独立开发（后端已就绪，前端仅验证） |
| I01 | FD04 | R04 | 可独立开发（后端已就绪，前端仅验证） |
| I05 | FD05 | R08 | 可独立开发（后端已就绪，前端仅验证） |

联调安排：
- **顺序**：core 侧 BT02（BD06 schema 补齐）完成并导出服务端 schema → FD01 对齐 `schema.graphql` 并跑 codegen → 启动 core+dashboard 联调，验证 `extensionList`（FD03）、退款设置（FD02）、订单过滤（FD04）。
- **可独立开发的前提**：FD01 的版本声明改动、FD02/FD04/FD05 的验证工作不依赖 core；仅 codegen 重生成与运行时联调需等待 I06。
- **需要的 mock**：jest 单测沿用仓库既有 mock 体系（`__mocks__/`、`src/fixtures.ts`、各域 fixtures），无需新增；dash-e2e 依赖 `run-suite.sh` 启动的真实 core 运行时，不使用 mock。
- **待解决依赖**：core BD06 完成前，Dashboard 对基线 core 发起 `extensionList` 查询会因 `mountName` 缺失报错——这是本轮升级要消除的现状，联调时作为首个验证点。

## 5. 其他

- **风险与缓解**：
  - 风险 1：codegen 重生成产物与现有调用点出现类型漂移。缓解：基线代码已按目标 schema 编写，预期零漂移；如出现，按"最小适配消费点"原则处理并在修订中记录。
  - 风险 2：`check-types` 在严格模式（`tsc-strict`）下暴露历史存量错误被误判为本次回归。缓解：以基线首次运行为对照，只处理本次改动引入的新增错误。
  - 风险 3：dash-e2e 依赖本地 core 运行时与数据库，环境未就绪时健康检查通过但用例失败。缓解：严格按 `run-suite.sh` 流程执行，区分环境问题与代码问题。
- **验证计划**：`pnpm run generate` → `pnpm run check-types` → `pnpm run test`（jest 单测）→ `run-suite.sh <attempt> dash-unit dash-e2e`；联调阶段对照 interface-contract.md 的 I01/I04/I05/I06 逐项走查。
- **未决项**：FD05 是否需要为 `paymentMethodDetails` 增加展示 UI，待官方 dash 测试清单明确后决定（当前按"无界面变更"设计）。
