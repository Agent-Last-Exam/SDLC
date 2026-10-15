# 前端技术设计：Saleor 3.23 Dashboard（saleor-dashboard）技术设计

版本：v1
责任：前端技术设计
依据：PRD v1，artifacts/sprint1/prd/prd.md
修订：首次交付

## 1. 方案概述

本次前端交付以 saleor-dashboard 3.22.9（React + TypeScript + Vite + macaw-ui、Apollo Client、自定义
`src/hooks/useForm`、`src/components/ConditionalFilter/` 表达式筛选、`src/hooks/makeQuery.ts` 查询工厂、
`src/components/RequirePermissions.tsx` 权限门控）为起点，围绕 PRD 的 G1–G6，在同一套既有页面骨架内交付
11 个设计单元（FD01–FD11）。**本文件描述目标设计，不代表任何能力已经实现**；凡基线缺失的能力一律描述为
“需新增”。

整体策略：不新开独立业务模块，主要落在现有页面对应目录内增量修改：

- 商品编辑页：在既有共享组件 `src/components/ChannelsAvailabilityCard/` 之外新增按渠道可售性诊断面板（FD01）。
- 列表与分配入口：在 `src/components/ConditionalFilter/`、`src/utils/filters/filters.ts`、
  `src/hooks/useFilterHandlers.ts` 上引入一等公民的“锁定条件（locked）”模型，贯穿列表/排序/导出/批量操作（FD02）。
- 选择器：在 `src/components/AssignProductDialog/`、`AssignContainerDialog/`、`AssignCategoryDialog/`、
  `ProductStocksAssignWarehouses.tsx` 上统一去重与导航上下文（FD03）。
- 认证：新增密码登录策略设置面，改造 `src/auth/components/LoginPage/` 与 `src/auth/views/Login.tsx` 的入口呈现（FD04）。
- 扩展：适配 `mountName`/`targetName`/`settings`、扩展表单响应契约与自托管扩展目录（FD05）。
- 配置页：以 `src/channels/views/ChannelDetails/`、`src/channels/pages/ChannelDetailsPage/`、`src/siteSettings/`
  为样板建立“加载/编辑/保存上下文保护”（FD06）。
- 展示准确性：重量/媒体/折扣/订单日期与草稿订单动作可用性（FD07）。
- 订单详情：金额分解、交易事件、礼品卡支付方式呈现与配送元数据快照展示（FD08）。
- 搜索：列表/弹窗/筛选器一致的搜索语义与列表状态一致性（FD09）。
- Webhook：投递状态（含 `RETRYING`）展示与单条重试（FD10）。
- 元数据：保留基础行内编辑，不新增独立入口（FD11）。

数据与状态模型统一原则：

- 服务端事实优先；客户端缓存仅在保存成功后更新（Apollo 标准化的 `update` / `refetchQueries`）。
- 所有生成类型由 `codegen.ts` 从 `schema.graphql` 重新生成（`src/graphql/types.generated.ts`、
  `src/graphql/hooks.generated.ts`、`src/graphql/fragmentTypes.generated.ts`）；新增字段/枚举/变更必须先更新
  `schema.graphql` 再 codegen，否则前端无法引用。
- 状态机统一为：`loading`（加载中）/ `loaded-empty`（已加载空数据）/ `permission-denied`（权限错误）/
  `error-retryable`（网络或服务错误，可重试）/ `ready`（就绪）；文案用 `react-intl` 消息文件承载。

## 2. 需求覆盖

| 需求 | 设计单元 |
| --- | --- |
| R01 | 无前端改动（仅按既有界面消费；配送选项重算由 Storefront/集成方调用，Dashboard 不消费） |
| R02 | 无前端改动（仅按既有界面消费；`checkoutDeliveryMethodUpdate`/`checkoutComplete` 由 Storefront 调用，Dashboard 不新增调用点） |
| R03 | 无前端改动（渠道-仓库直连库存语义为 Core 行为；Dashboard 不新增展示，渠道设置页仅为上下文，见 FD06） |
| R04 | FD01 |
| R05 | 无前端改动（自动完成执行由 Core 任务完成，Dashboard 不展示执行结果） |
| R06 | FD06（渠道自动完成延迟/cutoff 的配置承载与保存上下文保护） |
| R07 | FD08 |
| R08 | FD08 |
| R09 | FD08 |
| R10 | FD08 |
| R11 | 无前端改动（根级交易查询由客服/集成方消费；Dashboard 沿用既有订单/结账交易子字段） |
| R12 | FD09 |
| R13 | FD09 |
| R14 | FD02 |
| R15 | FD03 |
| R16 | FD04 |
| R17 | 无前端改动（OIDC 参数与外部身份关联为 Core/插件行为；Dashboard 不新增持久化或参数） |
| R18 | 无前端改动（富文本与外链校验为 Core 保存前校验；Dashboard 仅展示服务端字段错误） |
| R19 | FD05 |
| R20 | FD05 |
| R21 | FD05 |
| R22 | 无前端改动（Webhook 载荷构建边界为 Core 行为；Dashboard 不感知） |
| R23 | FD10 |
| R24 | FD08（配送元数据快照展示） |
| R25 | FD11 |
| R26 | 无前端改动（公开接口输入校验与失败语义为 Core 契约；Dashboard 经由生成类型与既有错误映射消费） |
| R27 | 无前端改动（弃用读取与已退出能力为 Core 契约；Dashboard 依赖生成客户端不再生成不支持的操作） |
| R28 | 无前端改动（权限边界为 Core 执行；Dashboard 沿用既有 `RequirePermissions` 呈现） |
| R29 | FD06 |
| R30 | FD07 |
| R31 | FD11 |

说明：R01、R02、R03、R05、R11、R17、R18、R22、R26、R27、R28 无前端改动，理由如上表；其余需求均落在
FD01–FD11 之一，覆盖完整可审计。R06 不在“无前端改动”范围内，其前端承载点（渠道自动完成开关、延迟与 cutoff）
统一归入 FD06 的配置加载/编辑/保存上下文保护。

## 3. 详细设计

### FD01 · 商品编辑页按渠道可售性诊断展示

- 覆盖需求：R04
- 设计说明：

**位置与关系。** 共享可用性卡片现为 `src/components/ChannelsAvailabilityCard/ChannelsAvailabilityCard.tsx`
（默认导出 `ChannelsAvailability`），在商品编辑页由 `src/products/components/ProductUpdatePage/ProductUpdatePage.tsx:418`
以 `<ChannelsAvailabilityCard {...availabilityCommonProps} channels={listings ?? []} />` 消费。基线**不存在**
`src/products/components/ChannelsAvailabilityCard/`，也不存在任何 `diagnostic` 模块。因此新增一个**独立的诊断面板**，
与既有可用性卡片并列呈现，不改动 `ChannelsAvailabilityCard` 的既有语义：

- 新增 `src/products/components/ProductChannelDiagnostics/`（容器 + 列表 + 详情 + 空/错误/加载态），
  在 `ProductUpdatePage.tsx` 紧随可用性卡片处挂载，仅在商品已保存（存在 `product.id`）时启用。
- 数据源为 I04 的 `Product.channelAvailabilityDiagnostics(filter, sortBy, before, after, first, last)`
  与其返回类型 `ProductChannelAvailabilityDiagnostics*`、枚举 `ProductChannelAvailabilityProblemTypeEnum`、
  `ProductChannelAvailabilityProblemSeverityEnum`。查询用 `makeQuery` 工厂（`src/hooks/makeQuery.ts`）或
  codegen 生成的 `useChannelAvailabilityDiagnosticsQuery` 承载，`fetchPolicy: "cache-and-network"`，
  不写入全局缓存以外的状态。

**交互与状态。**
- 筛选：按渠道名与币种两个输入（受控），走既有 URL/本地状态二选一；分页用游标（`before`/`after`/`first`）
  与 `src/hooks/usePaginator.ts` 一致的翻页模式，保证“问题数量 == 明细条目数”。
- 明细按三类分组：阻断错误（blocker）/ 警告（warning）/ 不适用（not-applicable）；数字（非配送）商品的配送区域
  检查归入“不适用”而不报错；未发布/不可购买时把发布状态或可购买时间列为阻断项，**不**把由此产生的库存/配送依赖
  重复报为错误（避免重复计数）。
- 权限：受限字段仅对有权限者展开；“问题数量”在无权限时仍可展示汇总，但明细条目不泄露受限数据。沿用
  `src/components/RequirePermissions.tsx` 的 `hasPermissions`/`hasOneOfPermissions` 判定，权限取自
  `useUserPermissions`。
- 状态机：`loading`（骨架/加载态，不清空旧列表）、`ready`、`loaded-empty`（“无问题”正向空态）、
  `permission-denied`（受限汇总态）、`error-retryable`（显式“重试”按钮，可重试，**不显示为空结果**）。
- 陈旧结果保护：为每次查询生成请求序号 `requestId`；仅当回调的 `requestId` 等于当前序号且商品/频道编辑上下文
  未变化时才写入展示状态，“编辑中的旧诊断结果不得覆盖正在编辑的内容，也不得标记为最新”。此约束与 FD06 的
  上下文保护共用同一实现（见 FD06）。

**GraphQL 文档。** 在 `src/products/queries.ts`（或新增 `src/products/components/ProductChannelDiagnostics/queries.ts`）
新增查询文档，节点取 `channelAvailabilityDiagnostics` 的 `edges { node { channel { id name slug currencyCode }
severity type message field } }`、`totalCount`、`pageInfo`，供 codegen 生成
`useChannelAvailabilityDiagnosticsQuery`；排序/筛选入参对齐 I04 的 `filter`/`sortBy`。

**验证方法。** 组件级用例覆盖：筛选/分页一致性、三类分组、数字商品跳过配送区域、无权限不泄露、失败显示可重试
而非空结果、晚到旧结果被丢弃；查询参数断言指向 `channelAvailabilityDiagnostics`。对应验收 AC-04-1…AC-04-6。

### FD02 · 列表与分配弹窗的锁定筛选与作用范围一致

- 覆盖需求：R14
- 设计说明：

**问题与目标。** 现有表达式筛选在 `src/components/ConditionalFilter/`（`ConditionalFilters.tsx`、
`FiltersArea.tsx`、`ValueProvider/UrlToken.ts`、`ValueProvider/useUrlValueProvider.ts`、`FilterElement/`、
`FilterValueProvider.ts`）。基线**没有**任何 `locked` 概念：全仓 grep `lockedFilters`/`staticFilters`/`lockedFilter`
为空；`ValueProvider/UrlToken.ts` 中的 `"static"` 指非属性筛选项（`STATIC_CONDITIONS`），与“锁定”无关。因此需
**新增一等公民的“锁定条件（locked）”模型**，把 URL/弹窗/页面上下文带入的条件与用户普通条件分开合并。

**新增与改动点。**
- 新增 `src/components/ConditionalFilter/lockedFilters.ts`（或等价命名模块），导出把锁定条件与普通条件合并为
  “当前有效条件（effective conditions）”的纯函数，并保证合并顺序为“锁定优先、普通不覆盖同维度锁定”。
- 修改 `src/components/ConditionalFilter/ValueProvider/FilterValueProvider.ts` 的接口（当前
  `value/loading/persist/isPersisted/clear/getTokenByName/count`）与 `useUrlValueProvider.ts`：把 URL token 拆分为
  `lockedTokens`（来自 `UrlToken.isStatic()`/`isAttribute()` 中由入口注入的部分）与 `userTokens`，`pending` 状态合并两者。
- 修改 `FilterElement/FilterElement.ts`、`FilterElement/Condition.ts`、`ConditionOptions.ts` 的 `Constraint` 处理：
  锁定元素的 `Constraint` 标记为不可移除，UI 不出现“删除/清除该条件”入口。
- 修改 `src/hooks/useFilterHandlers.ts`（现签名返回 `[changeFilters, resetFilters, handleSearchChange]`）：`resetFilters`
  与 `changeFilters` 只作用于普通条件，`resetFilters` 需按 `cleanupFn` 之外保留锁定条件，避免“清除普通条件时把锁定条件一并清掉”。
- 修改各列表的 `filters.ts`（如 `src/products/views/ProductList/filters.ts`、`src/orders/views/OrderList/filters.ts`、
  `src/giftCards/GiftCardsList/filters.ts` 等）与 `src/utils/filters/filters.ts`：`getFilterQueryParams`/`getFilterVariables`
  等入口统一读取“有效条件”，保证列表查询、排序、导出与批量操作共用同一来源。
- 导出：`src/products/views/ProductList/export.ts`（现 `ProductsExportParameters`，`asExportProductsInput()`）改为从
  “有效条件”构造 `ExportProductsInput`；`src/products/views/ProductList/ProductList.tsx` 的
  `useProductExportMutation` 与 `useProductCountQuery` 均读取同一有效条件，避免导出范围与页面所见不一致。
- 批量操作：`src/hooks/useBulkActions.ts`/`useListSelectedItems.ts` 与各列表批量删除/分配在提交前以有效条件校验
  选中项属于当前范围（不因换入口放宽权限）。

**Token 模型。** 锁定条件与普通条件都复用 `ValueProvider/UrlToken.ts` 的 `UrlEntry`/`UrlToken`
（`TokenType.STATIC`/`ATTRIBUTE_*`、`isStatic()`/`isAttribute()`/`isLoadable()`）序列化到 URL；区别仅在于“锁定”由入口
标记为不可移除，`UrlEntry.forStatic`/`fromConditionSelected` 的生成路径不变，从而不改变既有 URL 兼容性。

**入口与作用范围。** 从特定渠道/仓库分配入口进入列表时（如 `src/channels/views/ChannelDetails/ChannelDetails.tsx`
的分配动作、`src/products/components/ProductUpdatePage/ProductChannelsListingsDialog.tsx` 的弹窗入口），
锁定条件以 URL 参数（如 `channel`）或弹窗上下文注入；`ListFilters`（`src/components/AppLayout/ListFilters/ListFilters.tsx`，
其 `type: "expression-filter" | "old-filter-select"` 分支是锁定条件 UI 的自然插入点）对锁定条件渲染为
只读 chip，用户设置同维度普通条件时不替换锁定条件。

**缓存与一致性。** 查询变量由“有效条件 + 分页 + 排序”派生（见 `ProductList.tsx` 中 `queryVariables` 的
`useMemo([params, settings.rowNumber, valueProvider.value])`），锁定条件变化后依赖数组随之变化，`useMemo` 重新计算，
不使用上一次缓存；导出与批量操作同样以最新有效条件构造请求。权限只沿用既有对象可见范围，不因入口变化放宽。

**验证方法。** 用例覆盖：锁定条件下搜索/翻页/清除普通条件后锁定仍生效；同维度普通筛选不清除锁定；
导出/批量操作范围与当前有效筛选一致；筛选变更立即反映到列表与导出（无旧缓存）；越权对象不因筛选出现。
对应 AC-14-1…AC-14-6。

### FD03 · 选择器去重与层级导航上下文

- 覆盖需求：R15
- 设计说明：

**现状。** 相关选择器：`src/components/AssignProductDialog/`（`AssignProductDialog.tsx` 及
`AssignProductDialogMulti.tsx`/`AssignProductDialogSingle.tsx`）、`src/components/AssignContainerDialog/`
（`AssignContainerDialog.tsx` 及 Multi/Single）、`src/components/AssignCategoryDialog/AssignCategoryDialog.tsx`、
`src/products/components/ProductStocks/components/ProductStocksAssignWarehouses.tsx`（`ProductStocksAssignWarehouses`，
内部维护 `useState<Option[]>` 与 `useSearchQuery`）。基线**不存在** `AssignWarehouseDialog`，也**不存在** `CategoryTree`；
仓库分配目前仅内联于 `ProductStocksAssignWarehouses.tsx`。仓库/分类的层级选择需按目标设计新增去重与层级导航逻辑，
不得声称这些模块已存在。

**去重与残留清理。** 在上述选择器的“选中集合”上引入统一去重函数（可置于
`src/utils/filters/filters.ts` 已有的 `dedupeFilter` 旁或新增 `src/utils/collections.ts` 助手）：按对象 `id` 归并，
`ProductStocksAssignWarehouses` 的 `warehouses: Option[]`、各 Dialog 的选中列表在“反复选中再取消”后不出现重复项；
取消选中即从选中集合与查询条件中移除，`onWarehouseSelect`/`onAssign` 的清理路径确保取消值不残留在筛选或选择状态。

**层级与面包屑。** 分类/层级选择需要新增父子关系与面包屑显示：目标设计在 `AssignCategoryDialog` 与
`ProductStocksAssignWarehouses` 内增加层级视图（如面包屑 + 当前节点子列表），切换层级时更新面包屑路径，
父节点与子节点关系保持一致（新增模块，命名不与不存在的 `CategoryTree` 混淆）。

**导航上下文保持。** 加载、空结果、权限错误、网络错误与返回列表四类情形均保留原导航上下文：
- 返回用 `useNavigator`（`src/hooks/useNavigator.ts`）的 `preserveQs`/`state` 携带来源 URL 与选中状态。
- 弹窗关闭不清空已选；重新打开沿用上次上下文。
- 空结果与权限错误展示为可区分文案（复用 FD06 的状态机文案），但导航参数不变。

**宽度稳定性。** 搜索输入框与结果列表使用固定/最小宽度与截断显示（`text-overflow: ellipsis` + `title` 完整值），
长搜索词不导致重叠或跳动；清除输入用 `useSearchQuery` 的 `queryReset` 恢复默认宽度与列表。

**数据源。** 沿用既有搜索钩子：`src/searches/useProductSearch.ts`、`useCategorySearch.ts`、
`useWarehouseSearch.ts`、`useCollectionSearch.ts` 等（均经 `makeSearch` 生成），以及
`ProductStocksAssignWarehouses` 的无限滚动加载；不新增接口，仅统一去重与上下文。

**验证方法。** 用例覆盖：反复选/取消不重复；取消后不残留；切换层级面包屑正确；四类状态下返回保留上下文；
长词宽度稳定且可确认完整关键词、清除恢复正常。对应 AC-15-1…AC-15-5。

### FD04 · 密码登录策略设置页与登录入口

- 覆盖需求：R16
- 设计说明：

**现状。** `src/auth/components/LoginPage/LoginPage.tsx` 同时渲染邮箱/密码表单与外部认证按钮，两者并存；
`src/auth/views/Login.tsx` 通过 `useAvailableExternalAuthenticationsLazyQuery` 拉取
`shop.availableExternalAuthentications` 并传给 `LoginPage`。全仓**不存在** `passwordLoginMode`。因此
“密码登录入口是否展示/是否可用”需要新增判定与展示，而 `Shop.passwordLoginMode`（I09）目前也不在
`src/fragments/shop.ts` 的 `fragment Shop on Shop` 中。

**设置页（新增）。** 在 `src/siteSettings/` 下新增密码登录策略卡片并挂到既有 `SiteSettingsPage`
（`src/siteSettings/components/SiteSettingsPage/SiteSettingsPage.tsx`）：
- 读取：扩展 `src/siteSettings/queries.ts` 的 `siteSettings` 查询（`shop { ...Shop }`）或新增字段，读取
  `Shop.passwordLoginMode`（`PasswordLoginModeEnum`：`ENABLED`/`CUSTOMERS_ONLY`/`DISABLED`）。需先在
  `src/fragments/shop.ts` 加入该字段并 codegen。
- 写入：扩展 `src/siteSettings/mutations.ts` 的 `shopSettingsUpdate`（`ShopSettingsInput`）携带
  `passwordLoginMode`（I09）。保存后返回 `shop` 覆盖缓存。
- 展示：显示当前生效模式，并逐项说明权限限制（`ENABLED` 客户与员工可密码登录；`CUSTOMERS_ONLY` 仅客户；
  `DISABLED` 关闭密码登录/重置/设置/修改）。
- 权限：仅 `MANAGE_SETTINGS`（或对应商店设置权限）可编辑；无权限者只读，并以
  `RequirePermissions`/`hasPermissions` 控制保存按钮与字段。
- 错误映射：`AccountErrorCode.PASSWORD_LOGIN_DISABLED`、`PASSWORD_LOGIN_CUSTOMERS_ONLY` 及权限错误经
  `src/utils/errors/account.ts` 提示；加载/保存失败保留上次生效值（与 FD06 状态机一致），失败值不进缓存。

**登录页（改动）。** `src/auth/views/Login.tsx` 与 `src/auth/components/LoginPage/LoginPage.tsx`：
- 读取 `Shop.passwordLoginMode`（可在 `Shop` 查询或登录页初始化时获取）：`DISABLED` 时隐藏密码表单、
  “Forgot password?”链接与提交按钮；`CUSTOMERS_ONLY` 时对员工登录入口隐藏密码能力（依据账号身份/权限判定）。
- 外部认证按钮仅在存在 `availableExternalAuthentications` 时展示；当密码入口被禁用且**无任何外部认证方式**时，
  展示稳定空态（明确说明无可用登录方式），而非空白页面。
- 登录失败（含策略拒绝）展示服务端可识别原因；不在前端持久化 token 或敏感信息。
- 加载态：策略/外部认证加载中保持既有 `loading` 呈现，不闪烁错误默认值。

**验证方法。** 三种模式下入口可见性与可用性；无外部方式空态；保存后立即按新值处理；无权限只读；
加载/保存失败保留原值。对应 AC-16-1…AC-16-10。

### FD05 · 扩展安装、扩展目录与扩展表单响应

- 覆盖需求：R19、R20、R21
- 设计说明：

**R19 安装、查询与迁移适配（字段对齐）。** 基线 `src/extensions/hooks/useExtensions.ts` 已经在
`extensionList` 查询（`src/extensions/queries.ts:109` 起 `ExtensionList`）中请求并消费 `mountName`/`targetName`/`settings`，
通过 `ALL_APP_EXTENSION_MOUNTS.parse(mountName)`、`AppExtensionManifestTarget.parse(targetName)` 与
`appExtensionManifestOptionsSchema.safeParse(settings)` 解析；历史扩展因 Core 侧提供迁移适配（I10）而继续可渲染。
前端需补齐的改动：
- `src/extensions/domain/app-extension-manifest*.ts`：`app-extension-manifest.ts` 当前 schema 使用 `mount`/`target`/`options`；
  目标设计以 `mountName`/`targetName`/`settings` 为准，`settings` 解析走 `appExtensionManifestOptionsSchema`
  （`newTabTarget`/`widgetTarget` 的 `method`）；保留对旧字段的读取适配（历史数据），但**新客户端不继续提交旧字段**。
- 安装表单与校验：`src/extensions/views/InstallCustomExtension/`（`InstallCustomExtension.tsx`、
  `ExtensionInstallFormData`）与 `src/extensions/views/AddCustomExtension/`：安装输入对齐 I11
  （`AppInstallInput{appName: String!, manifestUrl: String!, ...}`；`tokenTargetUrl` 可选，缺省不导致安装失败，
  不需要时不返回/展示 token）。安装前校验 identifier 重复、无效权限、非法 target 与无法解析的 settings，
  拒绝且不产生部分安装数据。
- 权限：安装/更新需 App 管理权限（`MANAGE_APPS`，沿用 `useHasManagedAppsPermission`）；读取只返回调用方允许的扩展。

**R20 扩展表单响应契约（前端契约，Core 无新接口）。** Spine §2 已说明 R20 无新接口变化；因此这是**纯客户端契约**：
`src/extensions/views/ViewManifestExtension/components/AppFrame/` 内：
- `useAppActions.ts` 与 `appActionsHandler.ts`（导出 `AppActionsHandler`，含
  `useHandleNotificationAction`/`useHandleUpdateRoutingAction`/`useHandleRedirectAction`/`useNotifyReadyAction`/
  `createResponseStatus`/`useHandlePermissionRequest`）当前处理的 action 为
  `notification | redirect | updateRouting | notifyReady | requestPermissions`，**没有**表单响应动作。
- 目标设计新增对弹窗扩展返回的表单内容处理：定义明确的响应入参（默认值/成功/字段级校验失败/权限错误/App 关闭）
  与接收侧表单（翻译/商品等）的挂载点；`AppDialog/` 只把响应投递给**当前编辑上下文**的表单。
- 防御规则：多 frame、重复响应、未加载 frame 或未知 action **一律拒绝或显式忽略**，不污染当前编辑状态；
  App 处于关闭状态时忽略其响应；权限错误与字段校验失败不得保存为成功；缺省字段按默认值处理，不覆盖正在编辑的内容。

**R21 自托管扩展目录。** 基线 `useAppStoreExtensions` 位于
`src/extensions/views/ExploreExtensions/hooks/useAppStoreExtensions.ts`（**不是** `src/extensions/hooks/`），
且 `useExploreExtensions` 使用 `getExtensionsConfig().extensionsApiUri`（`src/config.ts:28`）；`config.ts:19`
的 `getAppsConfig().marketplaceApiUri` 已定义但在 `src` 内无消费者。目标设计：
- 目录不再依赖不可用的旧 marketplace 地址；`src/extensions/views/ExploreExtensions/`（`ExploreExtensions.tsx`、
  `ExtensionsList/`、`ExtenionItem/`、`hooks/useExploreExtensions.ts`、`useExtenstionsFilter.ts`）在加载成功时展示
  可用数据，支持筛选；
- 明确区分空态与错误：`useAppStoreExtensions` 返回 `{ error, loading, data }`，需在其上区分“无数据空态”与
  “加载失败错误原因”（基线在未配置 URL 时把错误与数据混同，需拆分）；
- 无配置权限用户保持只读（`AppInstallButton`/`AppActions` 依 `MANAGE_APPS` 只读化）；
- 目录加载失败不得显示为安装成功。

**验证方法。** 用例覆盖：安装后查询到 `mountName`/`targetName`/`settings` 一致；历史扩展仍渲染；重复 identifier/
无效权限/非法 target/设置不可解析被拒；缺省可选字段不失败且不返回 token；无权限只读；表单响应五类结果与防御规则；
目录空态/错误可区分、只读与不误报成功。对应 AC-19-1…AC-19-8、AC-20-1…AC-20-6、AC-21-1…AC-21-5。

### FD06 · 配置加载、编辑、保存的上下文保护

- 覆盖需求：R29、R06
- 设计说明：

**适用面。** 渠道设置（`src/channels/views/ChannelDetails/ChannelDetails.tsx`、
`src/channels/pages/ChannelDetailsPage/ChannelDetailsPage.tsx`，后者第 33 行已使用 `useStateFromProps`）、
商店设置（`src/siteSettings/`、`src/siteSettings/views/index.tsx`、`src/siteSettings/components/SiteSettingsPage/`）
与依赖商品数据的表单。渠道自动完成延迟/cutoff（I05，`CheckoutSettings.automaticCompletionDelay`/
`automaticCompletionCutoffDate`、`ChannelErrorCode.CHECKOUT_SETTINGS_OUTDATED`）与既有
`src/channels/components/ChannelForm/AutomaticallyCompleteCheckouts.tsx` 一并纳入本单元的加载/保存上下文保护。

**状态模型（可区分）。**
- `loading`：数据未到，表单字段以 `disabled`/骨架呈现，**不显示错误的默认值**，页面不崩溃或闪烁错误内容。
- `loaded-empty`：已加载但字段为空（如未配置自动完成沿用关闭/既有默认），展示稳定空/默认语义。
- `permission-denied`：区分“无权限”与“无数据”，返回权限错误而非空结果。
- `error-retryable`：网络/服务错误，提供显式“重试”。
- `ready`：就绪可编辑。

实现上用 `makeQuery`（`src/hooks/makeQuery.ts`）的分级结果（`loading`/`error`/`data`）驱动状态机，并以
新增的 `src/hooks/useFormContextGuard.ts`（或等价）统一“迟到数据回填”策略；`useStateFromProps`
（`src/hooks/useStateFromProps.ts`）已标记 `@deprecated`，其替代为 `src/hooks/useStateUpdate.ts`，二者均按“只在
与当前编辑上下文相关时回填”的原则使用。

**迟到数据回填与覆盖保护。**
- 每个编辑上下文维护 `contextId`（渠道 id / 商店设置 / 商品 id）与 `dirtyFields` 集合。
- 服务端数据到达时，仅回填 `contextId` 仍匹配且字段**未被用户修改**（不在 `dirtyFields`）的字段；
  正在输入的值不被覆盖。
- 不使用未保存的失败值作为默认值。

**缓存与保存。**
- 仅保存成功才更新缓存：mutation 成功后以返回对象 `update`/写入 Apollo 缓存或 `refetchQueries` 重新读取
  服务端事实，界面显示新值。
- 保存失败保留原状态，失败值不进缓存，修正后可重试。
- 保存冲突（`CHECKOUT_SETTINGS_OUTDATED` 等）明确报错并保留上次生效值。

**验证方法。** 用例覆盖：五类状态可区分；加载期不显示错误默认值；迟到数据只回填相关字段且不覆盖输入；
保存成功更新缓存并显示新值；保存失败保留原状态且可重试。对应 AC-29-1…AC-29-5、AC-06-1…AC-06-8（前端可见部分）。

### FD07 · 展示准确性与草稿订单动作可用性

- 覆盖需求：R30
- 设计说明：

**重量换算。** 基线无量/单位换算工具，`src/fragments/weight.ts` 仅提供 `Weight{unit,value}`，
`src/components/Weight/Weight.tsx` 仅按 `"{value} {unit}"` 展示，`src/products/components/ProductShipping/ProductShipping.tsx`
直接使用 `weightUnit`。目标设计新增单位换算助手（如 `src/utils/weight.ts`，将服务端返回的 `unit` 与真实数值按
实际单位换算展示），`ProductShipping`、`Weight`/`WeightRange` 与订单重量组件改为经助手展示，保证“按实际单位转换”。
（PRD 未给出换算常量数值，按既有单位语义实现，不臆造阈值。）

**媒体状态与折扣金额。** 媒体保持现有正常状态展示（`src/products/components/ProductMedia/ProductMedia.tsx`、
`ProductExternalMediaDialog`），**不**引入异步外链抓取或专用失败回退。折扣金额显示以 API 返回为准：
`src/orders/components/OrderPayment/utils.ts` 的 `getDiscountAmount`/`extractRefundedAmount` 与
`src/orders/components/OrderSummaryCard/utils.ts` 的 `extractOrderGiftCardUsedAmount` 等保持与 API 一致，不做额外
本地推断。

**订单日期分组。** 基线 `src/components/Datagrid/customCells/DateCell.tsx`（`dateCellRenderer(locale)`）与
`src/hooks/useDateLocalize.ts`（默认 `"ll"`）都只按 locale，订单列表（`src/orders/components/OrderListDatagrid/`、
`src/orders/components/OrderListPage/`）**没有**日期分组。目标设计新增按 locale 与 timezone 的分组逻辑
（如 `src/orders/utils/dateGrouping.ts`），在列表渲染时对 `created` 分组；跨日期边界不归错组；是否新增分组
展示需与列表既有结构一致，不破坏排序与分页。

**草稿订单动作可用性。** 基线 `src/orders/components/OrderDraftDetails/OrderDraftDetails.tsx:45,59` 在
`isChannelActive && areProductsInChannel` 不满足时**隐藏**“Add products”按钮，`OrderDraftAlert` 展示警告，
`src/orders/components/OrderDraftPage/OrderDraftPage.tsx:191` 的 `onDraftFinalize` 按钮只受通用 `disabled` 影响。
目标设计：
- 在渠道停用、渠道内无可售商品、或缺少必要配置时，**禁用**（而非隐藏）“Add products”与“Finalize/完成”动作，
  并给出不可用原因文案；不发明知不合法的请求。
- 复用既有 `useChannelUsabilityDataQuery`（`src/orders/views/OrderDetails/OrderDraftDetails/index.tsx:101`）
  判定商品条件；渠道 `isActive` 来自订单 `order.channel.isActive`。
- 切换到满足条件的正常渠道后，动作恢复可用（依赖数据更新后重算判定）。

**数据源。** 订单列表沿用 `src/orders/views/OrderList/OrderList.tsx` 的查询与
`src/orders/components/OrderListDatagrid/datagrid.ts` 的列适配；重量字段来自 `src/fragments/weight.ts`
与商品/变体片段；折扣金额来自 `src/fragments/orders.ts` 的订单金额字段。日期分组为客户端展示逻辑，
不新增查询字段。

**验证方法。** 用例覆盖：重量按单位换算、媒体/折扣与 API 一致、日期分组跨边界正确、草稿动作禁用并说明原因、
切换渠道恢复、无异步媒体回退。对应 AC-30-1…AC-30-6。

### FD08 · 订单详情：金额分解、交易事件与配送元数据

- 覆盖需求：R07、R08、R09、R10、R24
- 设计说明：

**容器与分支。** `src/orders/components/OrderPaymentOrTransaction/OrderPaymentOrTransaction.tsx` 按
`orderShouldUseTransactions(order)`（`src/orders/types.ts:17`）在 `OrderTransactionsWrapper` 与旧 `OrderPayment`
之间分支；`OrderTransactionsWrapper.tsx` 组合 `OrderSummaryCard`、`OrderPaymentSummaryCard`、
`OrderDetailsRefundTable` 与逐笔 `OrderTransaction`/`OrderTransactionPayment`/`OrderTransactionGiftCard`。

**金额分解。** 摘要需分别呈现商品、折扣、税费、配送、礼品卡、已授权、已扣款、已退款与剩余待付，与服务端一致：
- 礼品卡金额纳入统一来源：I07 的 `Order.totalGiftCard` 新增后，`OrderPaymentSummaryCard`
  （`src/orders/components/OrderPaymentSummaryCard/OrderPaymentSummaryCard.tsx`，现用 `extractOrderGiftCardUsedAmount`）
  与 `src/ordersV2/OrderDetailsViewModel.ts`（`getGiftCardsAmountUsed`/`getGiftCardsAmountUsed`、
  `getShouldDisplayAmounts`）改为读取服务端字段，避免本地重复计算与重复计入普通支付。
- 已授权/已扣款/已退款/剩余待付直接取自 `src/fragments/orders.ts` 的 `OrderDetails` 片段
  （`totalAuthorized`/`totalCharged`/`totalRefunded`/`totalBalance`，见 `src/fragments/orders.ts:362-388`），保证与服务端逐一一致；
  多交易汇总不重复计入同一事件或已使用额度；剩余待付为零显示“已结清”。
- `PaymentsSummary`（`OrderPaymentSummaryCard/components/PaymentsSummary/PaymentsSummary.tsx`）呈现
  `totalAuthorized`/`totalAuthorizePending`/`totalCharged`/`totalChargePending`/`totalCanceled`/`totalCancelPending`。

**礼品卡作为支付方式与事件。** I06 新增 `GiftCardPaymentMethodDetails implements PaymentMethodDetails`、
`TransactionItem.giftCard`、`GiftCard.reservedBalance/availableBalance` 与 `GiftCardEventsEnum` 新事件
（`AUTHORIZED`/`AUTHORIZATION_RELEASED`/`REFUNDED`）。`src/orders/components/OrderTransactionGiftCard/`
（现构造合成 `FakeTransaction`、`actions: []`）改为以真实礼品卡支付方式呈现其金额与关联事件，而非无法解释的减项；
`OrderTransaction`（`src/orders/components/OrderTransaction/OrderTransaction.tsx`）展示交易事件。
- 空事件列表是正常空态，页面正常渲染，**不**判定为请求失败（`TransactionEvents` 空态处理）。
- 礼品卡操作（结账取消授权 `checkoutGiftCardPaymentCancel`、退款）失败显示可识别原因，不显示为成功。
- 展示与根级交易查询一致（I08；R11 本身无前端新增，但订单内交易展示需与之一致）。

**资金动作边界与集中化。** 基线对 `order.actions`/`transaction.actions` 的门控是**内联且分散**的：
`OrderPayment.tsx:29-32`、`OrderPaymentSummaryCard.tsx:27`、`OrderTransaction/components/CardTitle/CardTitle.tsx:70`
（过滤 `REFUND`）、`OrderTransactionRefundPage/formDefaults.ts:77` 等处。目标设计**集中化**为单一判定模块
（如 `src/orders/utils/paymentActions.ts`，输出每种动作的可用性 + 原因），用于：
- 只展示当前支付方式与订单状态允许的动作（I07 的 `Order.actions`/`TransactionItem.actions` 语义）。
- 金额校验：输入不能为负；`orderCapture` 不超过当前可捕获授权（等于边界可成功）；`orderRefund` 不超过可退余额；
  多交易不重复占用额度；`orderMarkAsPaid` 考虑已有支付记录（无记录且符合条件才可用）。
- 幂等：点击两次或失败重试不重复扣款/退款/写冲突事件。
- 成功展示刷新后的订单、交易事件与余额；失败保留原状态并给可区分错误；无权限不泄露受限金额。
对应 mutation 见 `src/orders/mutations.ts`（`orderTransactionRequestActionMutation` 等）与
`orderMarkAsPaid`/`orderCapture`/`orderRefund`。

**配送元数据快照（R24）。** I13 新增 `Order.shippingMethodMetadata`/`Order.shippingMethodPrivateMetadata`；
在 `src/fragments/orders.ts` 增加字段后，订单详情/履约展示**来自订单的快照**（而非实时 `shippingMethod`），
源配送方式被修改/停用/删除不影响历史快照；public/private 按权限可见（私有不向未授权泄露）；
无元数据历史记录展示稳定空值。落点：订单详情摘要（`OrderSummaryCard`/`OrderTransactionsWrapper` 周边）与履约信息区。

**GraphQL 文档与字段。** `src/fragments/orders.ts` 的 `OrderDetails` 片段补充
`totalGiftCard`、`shippingMethodMetadata`/`shippingMethodPrivateMetadata` 与 `TransactionItem.giftCard`
（I06/I07/I13）；`src/orders/mutations.ts` 复用 `orderMarkAsPaid`/`orderCapture`/`orderRefund`/
`orderTransactionRequestActionMutation`，礼品卡取消授权使用 I06 的 `checkoutGiftCardPaymentCancel`（结账阶段）。
所有变更经 `useNotifier` 展示成功/失败，失败时经 `src/utils/errors/transaction.ts`、`order.ts` 映射可区分原因。

**验证方法。** 用例覆盖：金额分解与 API 一致、多交易不重复计入、礼品卡只计一次、Payment 与 Transaction 两路
都正确、部分支付剩余待付正确；礼品卡金额与事件呈现、空事件不报失败、失败有原因；动作仅按支付方式与状态展示、
金额边界、幂等、刷新后展示；配送元数据来自快照且权限正确。对应 AC-07-1…AC-07-7、AC-08-1…AC-08-7、
AC-09-1…AC-09-6、AC-10-1…AC-10-9、AC-24-1…AC-24-6。

### FD09 · 搜索与列表状态一致性

- 覆盖需求：R12、R13
- 设计说明：

**入口与语义一致性。** 列表搜索复用 `src/components/AppLayout/ListFilters/components/SearchInput.tsx`
（`SearchInput`，内建 500ms `Debounce`，`data-test-id="search-input"`）、`src/hooks/useSearchQuery.ts`
（`useSearchQuery(onFetch, initial)` 返回 `[query, onChange, reset]`）与 `src/hooks/makeSearch.ts`
（`makeSearch<TData,TVariables>(query, loadMoreFn)`，含 `SearchVariables{after,first,query}`、`UseSearchResult`）。
目标设计保证弹窗、列表与筛选器使用**一致搜索语义**（同一关键字、前缀/组合词/短语与相关度行为）：
- 各 `src/searches/*` 钩子（`useProductSearch`、`useOrderVariantSearch`、`useCustomerSearch`、
  `useStaffMemberSearch`、`useGiftCardTagsSearch`、`usePageSearch` 等）与列表筛选的 `query` 参数保持一致；
- 全局搜索 `src/search/`（`index.tsx`、`form.tsx`、`useSearchCriteria.ts`、`useInclusionVariables.ts`、
  `resultsTable/`）与 `src/components/NavigatorSearch/`（`NavigatorSearch.tsx`、`queries.ts`、`useActionItems.ts`）
  使用一致的主体过滤与权限范围。

**保留每次搜索条目的对象类型。** 结账、礼品卡、商品、订单、客户与员工均保留搜索入口；页面按标题、slug 或内容查找。
不改动 Core 搜索语义（spine §2：R12/R13 无接口变化）。

**空关键词与异常。**
- 空关键词**不**触发不可控全量查询：`useSearchQuery` 在空串时清空/短路（沿用既有
  `DEFAULT_INITIAL_SEARCH_DATA.query = ""` 约定，由调用方决定是否跳过），行为明确可预期。
- 过长或非法输入返回校验错误或明确空态，不阻塞其他列表操作。
- 搜索服务异常返回错误或空态，**不**把异常转成成功空结果（避免与 `src/components/ErrorPage/ErrorPage.tsx`
  的错误页语义冲突：列表内错误用行内错误态而非整页）。

**分页与稳定性。** 结果、数量、顺序与游标稳定：重复关键词、大小写变化、组合词与翻页不产生重复项或漏项；
游标分页沿用 `pageInfo` 与 `usePaginator`，翻页不叠加旧结果。

**权限。** 客户与员工的隐私、地址与身份信息受权限保护：无权限身份在列表/弹窗/筛选器均不可见敏感字段，
与 Core 权限一致（沿用既有对象范围与 `RequirePermissions`）。

**无高级搜索 UI。** 不新增 Page/User 的向量高级搜索、前缀/相关度增强、RANK 排序等 UI（属非目标，见 §5 与 FD11）。

**GraphQL 文档。** 沿用既有搜索文档：`src/search/queries.ts`、`src/searches/*`（如 `useProductSearch`）、
`src/components/NavigatorSearch/queries.ts` 与各列表查询中携带的 `search`/`query` 变量；不改 Core 搜索语义，
仅在客户端统一入参（空串短路、长度/格式校验）与异常处理，避免新增接口。

**验证方法。** 用例覆盖：多主体可检索；弹窗/列表/筛选器语义一致；空关键词不触发全量；非法/过长输入有空态或
校验错误且不阻塞其他列表；服务异常不转成功空列表；无权限不泄露隐私；分页不重复不漏项。对应 AC-12-1…AC-12-5、
AC-13-1…AC-13-7。

### FD10 · Webhook 投递状态展示与单条重试

- 覆盖需求：R23
- 设计说明：

**现状。** `src/extensions/views/EditManifestExtension/components/AppWebhooksDisplay/`：
`AppWebhooksDisplay.tsx`（`useAppWebhookDeliveriesQuery`，`pollInterval: 5000`，受 `useHasManagedAppsPermission` 门控）、
`EventDeliveriesList.tsx`、`EventDeliveryItem.tsx`（`MAX_ATTEMPTS = 6`）、`EventDeliveriesStatus.tsx`
（`EventDeliveryStatusChip` 仅处理 `FAILED`/`PENDING`/`SUCCESS`，其他值 `throw`）。基线
`EventDeliveryStatusEnum` 仅 `{ PENDING, SUCCESS, FAILED }`（`schema.graphql:3286`），**不存在** `RETRYING`；
`eventDeliveryRetry(id: ID!)`（`schema.graphql:15133`，需 `MANAGE_APPS`）已存在但**未被 `src` 使用**。
`src/extensions/components/AppAlerts/useAppsFailedDeliveries.ts`（`useAppsFailedDeliveries`，含
`useAppFailedPendingWebhooksLazyQuery`）提供既有失败告警。

**状态展示。** I12 新增 `EventDeliveryStatusEnum` 的 `RETRYING`。`EventDeliveriesStatus.tsx` 扩展
`mapDeliveryStatusToTextColor`/`BorderColor`/`BackgroundColor` 与 `DeliveryStatusDisplay` 以消费 `RETRYING`，
去掉对未知值的 `throw`（改为安全兜底，避免新枚举导致崩溃）。状态语义：
- 等待（`PENDING`）/ 成功（`SUCCESS`）/ 失败（`FAILED`）/ 重试中（`RETRYING`），并显示错误信息；
- 异步内容尚未生成时**不**显示为成功（区分“待生成”与“成功”）；
- `EventDeliveryItem` 展示尝试次数与 `MAX_ATTEMPTS`、事件时间与尝试明细（`AppWebhooksAttemptDetails`）。

**单条重试。** 新增 mutation 文档（如 `src/extensions/mutations.ts` 增加 `eventDeliveryRetry` 的 gql 与
`useEventDeliveryRetryMutation`），在 `EventDeliveryItem` 上为失败/重试中条目提供“重试”动作；动作受
App/业务域权限门控（`MANAGE_APPS`，并遵守 App 可见字段边界），无权限不展示/被拒绝；成功后通过
`refetch`/`refetchQueries` 刷新投递状态与尝试列表。

**既有告警保留。** 保留 `useAppsFailedDeliveries` 的失败告警，**不**扩展为 App Problems（不新增类型/字段/操作/列表）。

**GraphQL 文档。** `src/extensions/queries.ts` 的 `AppWebhookDeliveries` 查询在投递节点上已取 `status`
与 `attempts`，需扩展以承载 `RETRYING` 语义；`src/extensions/mutations.ts` 新增
`eventDeliveryRetry(id: ID!)` 的 gql 文档并 codegen 出 `useEventDeliveryRetryMutation`（基线 schema 已有该 mutation，
前端未使用）。

**验证方法。** 用例覆盖：四类状态可区分并显示错误；未生成内容不显示成功；单条重试受权限门控、成功后刷新；
失败告警仍可用且未引入 App Problems；展示与重试内容不超出 App 可见边界。对应 AC-23-1…AC-23-8。

### FD11 · 元数据基础编辑保留与范围边界

- 覆盖需求：R25、R31
- 设计说明：

**保留的基础编辑。** 保留订单详情行内编辑与订单行元数据：`src/orders/components/OrderMetadataDialog/`
（`OrderMetadataDialog.tsx`，含 `useMetadataValues.tsx`、`useHandleSubmit.ts`、`useOrderMetadataFormControls.ts`、
`OrderLineDetails/`）继续可用，被 `src/orders/views/OrderDetails/OrderNormalDetails/index.tsx:316`、
`OrderUnconfirmedDetails/index.tsx:378`、`OrderDraftDetails/index.tsx:301` 消费；底层复用
`src/components/Metadata/`（`MetadataCard`/`MetadataCardTable`/`MetadataLoadingCard`）与
`src/components/MetadataHookForm/MetadataHookForm.tsx`（react-hook-form 版编辑器）。合法键值按权限保存/读回；
非法值、权限不足或保存失败不改变原值、不部分写入（沿用 `updateMetadata`/`updatePrivateMetadata` 与
`createMetadataUpdateHandler`）。

**范围边界（不新增）。** 不交付订单、履约、仓库的独立元数据弹窗、专用路由或可绕过的隐藏入口；不得以别名、
隐藏路由或生成文件重新暴露。基线的 `OrderMetadataDialog` 属订单**行**元数据（业务允许），不扩展为订单/履约/仓库的
独立管理入口。

**不重新引入的能力（与 R31 一致）。** 前端不新增：
- App Problems 的类型/字段/操作/问题列表（保留 `useAppsFailedDeliveries` 失败告警）；
- Page/User 高级搜索、前缀/相关度增强与 RANK 排序 UI（`src/search/`、`src/components/NavigatorSearch/` 不新增）；
- 交易日期/事件筛选与专用排序（`src/orders` 交易列表不新增日期/事件筛选与专用排序）；
- 异步外链图片抓取与 pending/503/proxy 状态及专用 fallback（保持同步外链图片、本地上传与外部视频/oEmbed）；
- 独立变体生成器的页面/菜单/任务/状态/专用入口（`src/products/` 变体相关不新增生成器）。

**必须保持可用的能力（与 R31 一致）。** 普通单变体创建（`src/products/views/ProductVariantCreate.tsx`、
`ProductVariantCreatePage`）、必填属性、`hasVariants` 兼容行为、普通批量创建、同步外链图片
（`ProductExternalMediaDialog`）、本地上传（`multiFileUploadHandler`、`src/files/mutations.ts`）与外部视频/oEmbed
继续可用。

**GraphQL 文档。** 沿用既有 `updateMetadata`/`updatePrivateMetadata`（`src/components/Metadata`、
`src/orders/components/OrderMetadataDialog/useHandleSubmit.ts`）与 `OrderLinesMetadata` 查询；本轮不新增元数据
mutation/查询，也不新增专用路由或入口。

**验证方法。** 用例覆盖：订单行元数据行内编辑仍可用；非法值/无权限失败不改原值；不出现订单/履约/仓库独立
元数据入口；不出现 App Problems、高级搜索、交易筛选/专用排序、异步媒体、变体生成器入口；基础能力回归通过。
对应 AC-25-1…AC-25-5、AC-31-1…AC-31-7。

## 4. 依赖与联调

| 接口 | 消费方设计单元 | 对应需求 | 开发依赖 |
| --- | --- | --- | --- |
| I01 | 无（Storefront/集成方消费） | R01 | 需等待：`schema.graphql` 更新后重新 codegen，`src/graphql/types.generated.ts` 出现 `CheckoutDeliveryOptionsRecalculate` 等类型；Dashboard 不新增调用点，仅保证生成客户端可编译 |
| I02 | 无（Storefront 消费；错误码经通用错误展示复用） | R02 | 需等待：`CheckoutErrorCode` 新增 `DELIVERY_METHOD_NOT_FOUND`、`DELIVERY_OPTIONS_SERVICE_ERROR` 后重新 codegen；前端错误映射（`src/utils/errors/`）需与新枚举保持一致，不新增 Dashboard 调用点 |
| I03 | FD06（渠道设置页承载；R03 本轮无前端强制改动） | R03 | 可独立开发：`StockSettings.useChannelWarehousesForStock` 生成类型可用后，渠道设置页可选暴露该开关；若暴露需重新 codegen |
| I04 | FD01 | R04 | 需等待：`Product.channelAvailabilityDiagnostics`、`ProductChannelAvailabilityDiagnostics*`、`ProductChannelAvailabilityProblemTypeEnum`/`SeverityEnum` 落地后重新 codegen，FD01 查询与分组枚举才能编译 |
| I05 | FD06 | R05、R06 | 需等待：`CheckoutSettings.automaticCompletionDelay`/`automaticCompletionCutoffDate`、`CheckoutSettingsInput.expectedUpdatedAt` 与 `ChannelErrorCode.CHECKOUT_SETTINGS_OUTDATED` 落地后 codegen；FD06 依赖该冲突错误码做“保留上次生效值” |
| I06 | FD08 | R07、R08 | 需等待：`GiftCardPaymentMethodDetails`、`TransactionItem.giftCard`、`GiftCard.reservedBalance/availableBalance`、`GiftCardEventsEnum` 新事件落地后 codegen；FD08 的礼品卡呈现与事件依赖这些字段 |
| I07 | FD08 | R09、R10 | 需等待：`Order.totalGiftCard` 与 `Order.actions`/`TransactionItem.actions` 语义落地后 codegen；FD08 金额分解与动作集中化依赖这些字段 |
| I08 | 无（客服/集成方消费） | R11 | 需等待：`Query.transactions(where,...)` 等类型落地后 codegen；Dashboard 不新增调用点，仅保证生成客户端一致 |
| I09 | FD04 | R16 | 需等待：`Shop.passwordLoginMode`、`ShopSettingsInput.passwordLoginMode`、`PasswordLoginModeEnum` 落地后 codegen；`src/fragments/shop.ts` 需加入字段 |
| I10 | FD05 | R19 | 需等待：`AppExtension`/`AppManifestExtension` 的 `mountName`/`targetName`/`settings` 在 Core 端稳定（Dashboard `schema.graphql` 已含该三字段），迁移适配就绪后历史扩展可渲染 |
| I11 | FD05 | R19、R27 | 需等待：`AppInstallInput{appName: String!, manifestUrl: String!}` 必填与 `tokenTargetUrl` 可选语义确认后，安装表单校验与提交字段对齐；无 `tokenTargetUrl` 时不展示 token |
| I12 | FD10 | R23 | 需等待：`EventDeliveryStatusEnum.RETRYING` 与 `eventDeliveryRetry` 语义确认后 codegen；FD10 需新增 `eventDeliveryRetry` gql 文档与 `useEventDeliveryRetryMutation` |
| I13 | FD08 | R24 | 需等待：`Order.shippingMethodMetadata`/`Order.shippingMethodPrivateMetadata` 落地后 codegen；`src/fragments/orders.ts` 需加入字段后订单/履约展示快照 |
| I14 | 无 | R26 | 需等待：Federation representations 校验为 Core 契约；Dashboard 不消费，重新 codegen 保证类型一致 |
| I15 | 无 | R27 | 需等待：`Payment.partial` 等弃用/移除后重新 codegen，确保生成客户端不再含不支持的操作；前端删除对已退出 mutation 的引用（若有残留） |

**联调安排与前提。**
- 所有 GraphQL 依赖以 `schema.graphql`（由 Core 目标 schema 覆盖）为准，前端在 codegen 通过后才可编译依赖新
  字段的单元；因此 FD01、FD04、FD05、FD06、FD08、FD10 可独立开发的部分（骨架、状态机、去重/上下文逻辑）
  先落地，待生成类型就绪后再接数据。
- 需要 mock 的部分：FD01 诊断查询、FD05 扩展表单响应与自托管目录、FD10 `RETRYING` 与 `eventDeliveryRetry`、
  FD08 礼品卡/金额字段，均可先以本地 fixture（参考既有 `src/**/fixtures.ts`）驱动组件测试。
- 错误码映射（I02、I05、I09）需与后端统一；FD06 的 `CHECKOUT_SETTINGS_OUTDATED` 与 FD04 的
  `PASSWORD_LOGIN_DISABLED`/`PASSWORD_LOGIN_CUSTOMERS_ONLY` 需在 `src/utils/errors/` 对应模块补文案映射。
- 待解决依赖：Core 端 `AppExtension` 契约与 Dashboard `schema.graphql` 的差异需在 codegen 前对齐；未对齐前
  FD05 的字段解析以 Dashboard 现有 `schema.graphql` 为准。

## 5. 其他

**非目标（spine §6，前端显式遵守）。** 前端不新增：App Problems 的类型/字段/操作/列表；Page/User 向量高级搜索、
RANK 排序与专用索引、后台维护任务与迁移；交易日期/事件筛选与专用排序索引；异步外链图片抓取与 pending/503/proxy
状态；独立变体生成器页面/菜单/任务/状态；订单、履约、仓库的独立元数据弹窗/专用路由/隐藏入口。不通过别名、
隐藏路由或生成文件重新暴露。上述排除不删除基础搜索、普通媒体与变体操作、基础交易查询、元数据编辑或
Webhook 失败告警（见 FD11）。依赖升级、CI、运行器、生成工具、遥测与内部重构不另立业务需求。

**前端相关风险与假设。**
1. **生成客户端重生成**：`src/graphql/types.generated.ts` 与 `src/graphql/hooks.generated.ts` 由 `codegen.ts` 生成，
   新增枚举值（如 `RETRYING`、`DELIVERY_METHOD_NOT_FOUND`）会让既有 `switch` 命中 `default` 分支。基线
   `EventDeliveriesStatus.tsx` 对未知值 `throw`，需在 FD10 改为安全兜底，否则新枚举会导致页面崩溃。
2. **错误码映射**：所有新错误码必须在 `src/utils/errors/` 有对应文案与分支，否则界面会把可定位错误显示为通用错误。
3. **不新增隐藏路由**：FD04/FD05/FD11 均不得新增隐藏入口或专用路由；所有入口沿用既有导航（`src/hooks/useNavigator.ts`）。
4. **配置上下文**：FD06 需替换/收敛对 `useStateFromProps`（已 `@deprecated`）的使用，避免迟到数据覆盖输入；
   新逻辑以 `useStateUpdate` 与 `contextId`/`dirtyFields` 为基础。
5. **PRD 未定量的项**：搜索最终一致性窗口、重试次数、超时与富文本深度上限均无具体数值；前端一律**沿用既有行为**，
   仅需保证在 UI 上呈现**可区分**的状态（加载/空/失败/重试中），不臆造数值。
6. **接口来源**：本文件的接口编号取自 `interface-contract.md`（I01–I15），权威契约以该文件为准；此处不重复定义。
7. **无前端改动需求的审计**：R01、R02、R03、R05、R11、R17、R18、R22、R26、R27、R28 已在 §2 显式标注，
   前端仅按既有界面消费生成类型与既有错误映射，不作为独立设计单元。

<!-- FD 编号发布后不重排、不复用。接口编号取自 interface-contract.md；此处不重复定义权威契约。沿用 PRD 的业务名称。 -->
