# 前端技术设计：Saleor 3.23 结账、收款与商户运营一致性交付

版本：v1
责任：前端技术设计
依据：PRD v1，artifacts/sprint1/prd/prd.md
修订：首次交付。

## 1. 方案概述

本轮前端交付以 Dashboard 3.22.9（React + TypeScript + Vite + pnpm，GraphQL 生成类型在 `src/graphql/types.generated.ts`）为基线，覆盖三类工作：

1. **运营可见性**：商品编辑页的渠道可售性诊断、列表与分配弹窗的锁定筛选、选择器与层级导航的上下文保持、搜索范围与异常状态。
2. **资金与配置的正确性**：订单金额摘要、交易与礼品卡的区分、人工资金动作的可用性、渠道自动完成配置、渠道库存模式配置、密码登录模式配置。
3. **状态与展示的准确性**：扩展数据与投递状态、订单配送元数据快照、迟到配置数据不覆盖输入、重量/媒体/金额/日期展示、草稿订单动作可用性、错误映射与生成客户端一致性。

现有代码依据（均为当前基线仓库路径）：

- 商品编辑页：`src/products/views/ProductUpdate/ProductUpdate.tsx`、`src/products/components/ProductUpdatePage/ProductUpdatePage.tsx`（含 `mapByChannel`）、`src/products/components/ProductUpdatePage/ProductChannelsListingsDialog.tsx`、`src/products/components/ProductUpdatePage/formChannels.ts`。
- 渠道可用性组件：`src/components/ChannelsAvailabilityCard/ChannelsAvailabilityCard.tsx`、`src/components/ChannelsAvailabilityDialog/ChannelsAvailabilityDialog.tsx`（当前只支持按渠道名搜索，使用 `hooks/useChannelsSearch`，无币种筛选、无分页）、`src/components/ChannelsAvailabilityDialogChannelsList/ChannelsAvailabilityDialogChannelsList.tsx`。
- 筛选：`src/hooks/useFilterHandlers.ts`、`src/hooks/useFilterPresets/useFilterPresets.ts`、`src/utils/filters/filters.ts`（`createFilterUtils`、`getFilterQueryParams`、`dedupeFilter`）、`src/components/Filter/`、`src/components/ConditionalFilter/`（含 `ValueProvider/useUrlValueProvider.ts`、`FilterElement/Constraint.ts`、`constants.ts` 的 `CONSTRAINTS`）。
- 分配与层级：`src/components/AssignContainerDialog/AssignContainerDialog.tsx`、`src/components/AssignCategoryDialog/AssignCategoryDialog.tsx`（当前为扁平容器列表，非树形）、`src/components/AssignProductDialog/`、`src/products/components/ProductStocks/components/ProductStocksAssignWarehouses.tsx`、`src/channels/views/ChannelDetails/useWarehouses.ts`、`useShippingZones.ts`。
- 设置页：`src/channels/views/ChannelDetails/ChannelDetails.tsx`、`src/channels/components/ChannelForm/ChannelForm.tsx`、`src/siteSettings/views/index.tsx`、`src/siteSettings/components/SiteSettingsPage/SiteSettingsPage.tsx`、`src/hooks/useForm/index.ts`、`src/hooks/useStateFromProps.ts`。
- 扩展：`src/extensions/views/ExploreExtensions/ExploreExtensions.tsx`、`src/extensions/hooks/useExploreExtensions.ts`、`useAppStoreExtensions.ts`、`useExtensions.ts`、`src/extensions/views/ViewManifestExtension/components/AppFrame/`（`AppFrame.tsx`、`usePostToExtension.ts`、`appActionsHandler.ts`、`useAppActions.ts`）。
- Webhook 投递：`src/extensions/views/EditManifestExtension/components/AppWebhooksDisplay/`（`EventDeliveriesList.tsx`、`EventDeliveryItem.tsx`、`EventDeliveriesStatus.tsx`、`AppWebhooksAttemptDetails.tsx`）、`src/extensions/components/AppAlerts/useAppsFailedDeliveries.ts`（当前无重试入口）。
- 认证：`src/auth/views/Login.tsx`、`src/auth/components/LoginPage/`、`src/auth/hooks/useAuthProvider.ts`（`handleLogin`）、`src/auth/utils.ts`（`handleQueryAuthError`、`getExternalAuthenticationMethodName`）、`src/auth/mutations.ts`。
- 订单：`src/orders/views/OrderDetails/`、`src/orders/components/OrderDraftPage/`（`OrderDraftPage.tsx`、`OrderDraftAlert.tsx`）、`src/orders/components/OrderListPage/OrderListPage.tsx`。
- 展示工具：`src/misc.ts`（`weight` 只做 `parseFloat`，无单位换算；`getMutationErrors`、`extractMutationErrors`）、`src/components/Weight/Weight.tsx`、`src/components/Money/index.ts`（`formatMoney`、`formatMoneyRange`、`subtractMoney`）、`src/hooks/useDateLocalize.ts`、`src/components/Timezone/`、`src/utils/intl.ts`。
- 元数据：`src/components/Metadata/MetadataCardTable.tsx`、`src/components/MetadataHookForm/MetadataHookForm.tsx`、`src/utils/metadata/`、`src/utils/handlers/metadataUpdateHandler.ts`。
- 生成与错误映射：`src/graphql/types.generated.ts`、`src/graphql/client.ts`、`src/fragments/errors.ts`、`src/utils/errors/`、`src/utils/api.ts`（`GqlErrors`、`hasError`）。

设计原则：所有页面状态区分加载中、已加载空数据、权限错误、网络错误与可重试五种；保存成功只更新与当前编辑上下文相关的字段；服务端返回的失败不进入缓存。

## 2. 需求覆盖

下表只列前端承接的需求。R18、R23 的前端部分为入口与展示，其余为后端契约（见 `backend-design.md`）。

| 需求 | 设计单元 |
| --- | --- |
| R01 | FD12 |
| R02 | FD12 |
| R03 | FD12 |
| R04 | FD13 |
| R06 | FD11 |
| R07 | FD01、FD02 |
| R08 | FD26 |
| R09 | FD26 |
| R10 | FD15 |
| R11 | FD15 |
| R12 | FD14 |
| R13 | FD16 |
| R14 | FD15 |
| R15 | FD03、FD04 |
| R16 | FD05 |
| R17 | FD08、FD09 |
| R18 | FD10 |
| R19 | FD17 |
| R20 | FD18 |
| R21 | FD06 |
| R22 | FD07 |
| R24 | FD19 |
| R25 | FD20 |
| R26 | FD21 |
| R27 | FD25 |
| R28 | FD25 |
| R29 | FD25 |
| R30 | FD22 |
| R31 | FD23、FD24 |
| R32 | FD27 |

未由前端承接的需求：

- **R05**（自动完成的执行与幂等）：纯后端任务行为，前端只在 FD11 展示状态与阻断原因，不模拟后台执行结果。
- **R23**（Webhook 载荷构建边界）：载荷构建发生在 Core，前端无对应界面；前端只承接其可观测结果（FD19 的投递状态）。
- **R18** 的协议部分由 `interfaces/oidc-offline-access.md` 定义，前端只承接登录入口与失败展示（FD10）。

## 3. 详细设计

### FD01 · 商品编辑页渠道可售性诊断
- 覆盖需求：R07
- 设计说明：
  - **页面与路径**：`src/products/views/ProductUpdate/ProductUpdate.tsx` 引入新的诊断区块，展示在「渠道可用性」区域附近；组件落在 `src/products/components/ProductUpdatePage/` 下新增目录（如 `ProductChannelDiagnostics/`），复用 `src/components/ChannelsAvailabilityCard` 的视觉语言。
  - **交互**：分区列出每个渠道的诊断结果，显示渠道名、币种、`isAvailable`、错误/警告/不适用三个计数与可展开的明细。明细按严重度分组并用不同视觉权重（ERROR 高权重、WARNING 次之、NOT_APPLICABLE 灰置），避免「正常依赖」与「真正阻断」在视觉上等权（AC-07-2、AC-07-3）。
  - **筛选与分页**：支持按渠道名与币种筛选、游标翻页；筛选输入受控，翻页保留筛选值（AC-07-1）。空结果给出明确空态而不是错误。
  - **数据流**：用生成的 `ProductChannelDiagnostics` 查询（I07）按 `productId` + `filter` + `first/after` 拉取；每次筛选或翻页都发起新请求，不复用上一次结论。切换到别的商品时清空旧结果，避免把旧诊断当最新结论（AC-07-6）。
  - **状态**：加载中显示骨架/加载态；失败显示错误态与重试入口；无权限显示权限错误态（AC-07-5）；商品正在编辑时诊断区独立渲染，不因诊断数据到达而覆盖表单字段（AC-07-6 的前端部分）。
  - **权限与失败处理**：无权限不渲染明细（错误态而非空态），不根据错误内容推断受限信息。
  - **验证方法**：构造多渠道路径差异的商品断言筛选与计数；数字类商品断言配送区域类明细落在「不适用」分组；断开网络断言错误态与重试；编辑表单输入后触发诊断刷新，断言输入未被覆盖。

### FD02 · 商品渠道清单的筛选与分页
- 覆盖需求：R07
- 设计说明：
  - **页面与路径**：`src/components/ChannelsAvailabilityDialog/ChannelsAvailabilityDialog.tsx` 与 `ChannelsAvailabilityDialogChannelsList.tsx`。现有实现只用 `hooks/useChannelsSearch` 按渠道名过滤且一次性渲染全部渠道。
  - **交互**：在弹窗内增加币种筛选与分页入口。渠道名搜索保留；币种筛选与渠道名筛选以「与」的关系组合；分页使用游标并在弹窗内保留滚动位置。
  - **数据流**：筛选条件进入弹窗的本地状态与查询变量；翻页只追加，不重置筛选。提交选择时使用当前可见的渠道集合。
  - **状态**：加载中禁用提交；空结果给出空态；网络错误给出可重试错误态，不清空已选渠道（AC-16-3 的弹窗侧）。
  - **验证方法**：按渠道名与币种组合筛选断言结果交集；翻页断言无重复项且筛选保留；断网断言已选渠道不丢失。

### FD03 · 锁定筛选与普通筛选的合并
- 覆盖需求：R15
- 设计说明：
  - **页面与路径**：列表页的筛选状态统一收敛到 `src/hooks/useFilterHandlers.ts`、`src/hooks/useFilterPresets/useFilterPresets.ts`、`src/utils/filters/filters.ts` 与 `src/components/ConditionalFilter/`（含 `ValueProvider/useUrlValueProvider.ts`）。**基线中不存在锁定筛选机制**（无 `locked`/`preselected`/固定筛选的实现，`FilterElement/Constraint.ts` 描述的是字段间条件依赖而非固定条件），因此需要新增一层。
  - **设计**：在筛选模型中区分两组条件——`lockedFilters`（来自 URL、分配弹窗或页面上下文，例如「某渠道」「某仓库」）与 `userFilters`（用户在筛选器中设置）。两者合并时 `lockedFilters` 优先且不可被 `userFilters` 覆盖；清除普通条件、搜索、翻页、切换预设都不清除 `lockedFilters`（AC-15-1、AC-15-2）。在筛选栏中以只读标签展示锁定条件并提供移除入口（只有在进入上下文允许时才可移除）。
  - **数据流**：所有列表查询、排序、导出与批量操作从同一个「当前有效条件」派生对象读取条件，不使用组件内缓存的旧副本；`lockedFilters` 通过 URL 与页面上下文传递，进入不同入口时由入口注入（AC-15-3）。
  - **权限**：锁定条件只收窄范围，不放宽权限；换入口后权限判定仍由服务端执行（AC-15-5）。
  - **验证方法**：从渠道/仓库分配页进入列表后设置普通筛选，断言两者同时生效；清除普通条件与翻页断言锁定条件仍在；对同一列表连续操作断言发出的查询变量与当前条件一致。

### FD04 · 导出与批量操作的作用范围
- 覆盖需求：R15
- 设计说明：
  - **页面与路径**：各列表页的导出与批量操作入口（如 `src/products/views/ProductList/`、`src/orders/views/OrderList/`、`src/discounts/` 的 voucher/gift card 列表）与筛选条件共享 FD03 的「当前有效条件」。
  - **设计**：导出与批量操作的请求参数由当前有效条件（含 `lockedFilters`）构造，不使用页面初始化时的条件副本；操作完成后以服务端事实刷新列表，不就地推测结果（AC-15-4）。
  - **失败处理**：导出提交失败显示可区分错误并保留筛选；无权限时入口禁用或提交被拒绝并解释原因，不静默降级为全量。
  - **验证方法**：带锁定条件与普通条件各执行一次导出，断言请求参数与页面可见范围一致；无导出权限断言被拒绝且提示明确。

### FD05 · 选择器与层级导航的上下文保持
- 覆盖需求：R16
- 设计说明：
  - **页面与路径**：`src/components/AssignContainerDialog/`（`AssignContainerDialog.tsx`、`AssignContainerDialogSingle.tsx`、`AssignContainerDialogMulti.tsx`）、`src/components/AssignCategoryDialog/AssignCategoryDialog.tsx`、`src/products/components/ProductStocks/components/ProductStocksAssignWarehouses.tsx`、`src/channels/views/ChannelDetails/useWarehouses.ts`、`useShippingZones.ts`、`src/shipping/components/ShippingZoneCountriesAssignDialog/`。
  - **设计**：选择结果以 `Map<id, item>` 存储，选中/取消/重复选中按 id 去重，取消即删除条目，不保留残留值（AC-16-1）。分类层级需要新增真正的父子关系组织：当前 `AssignCategoryDialog` 是扁平列表，本轮在其上补层级导航（进入子级、返回上级、面包屑），并保证父子关系与当前位置一致（AC-16-2）。返回列表时通过 URL 或路由状态保留筛选、页码与滚动位置（AC-16-3）。
  - **状态**：加载中、空结果、权限错误、网络错误各有独立呈现；从弹窗返回列表时导航上下文不变。
  - **长值处理**：输入框与列表容器使用固定宽度与溢出截断，长关键词提供完整值查看（title 或悬浮提示），清除输入后恢复列表宽度且不跳动（AC-16-4）。
  - **验证方法**：反复选中再取消断言无重复与残留；切换分类层级断言面包屑与父级正确；模拟加载/空/权限/网络错误后返回断言上下文保留；输入超长关键词断言布局稳定且可确认完整值。

### FD06 · 扩展回应与表单状态
- 覆盖需求：R21
- 设计说明：
  - **页面与路径**：`src/extensions/views/ViewManifestExtension/components/AppFrame/`（`AppFrame.tsx`、`AppIFrame.tsx`、`usePostToExtension.ts`）、`AppFrame/appActionsHandler.ts`（`AppActionsHandler` 与各 `useHandle*Action`）、`AppFrame/useAppActions.ts`。基线的 action 协议只覆盖 notification/redirect/updateRouting/requestPermissions/notifyReady，**没有表单回传处理器**，需要新增。
  - **设计**：在 action 分发处新增表单回传动作的处理：接收扩展返回的表单内容并交给当前打开弹窗的表单实例回填；同时接收字段级校验失败信息并在对应字段上标出错误（AC-21-1）。按响应类型区分缺省值、成功、字段校验失败、权限错误与 App 关闭状态；错误状态绝不当作保存成功（AC-21-2）。
  - **有效性防护**：以「当前激活的扩展上下文」为唯一接收者；多 frame、重复响应、未加载 frame、未知 action 一律拒绝或明确忽略，不写入当前编辑状态（AC-21-3）。响应带请求标识，重复标识的响应只应用一次。
  - **数据流**：回填只写入当前编辑上下文仍有效的字段，不覆盖用户在其他字段的输入。
  - **验证方法**：模拟五种响应类型断言表单状态正确；模拟多 frame 与重复响应断言编辑状态未被污染；模拟未知 action 断言被忽略且有日志。

### FD07 · 自托管商店的扩展目录
- 覆盖需求：R22
- 设计说明：
  - **页面与路径**：`src/extensions/views/ExploreExtensions/ExploreExtensions.tsx`、`src/extensions/hooks/useExploreExtensions.ts`、`useAppStoreExtensions.ts`、`useExtenstionsFilter.ts`、`src/extensions/components/ExtensionsList/`。
  - **设计**：目录数据来源不依赖不可用的旧 marketplace 地址；在自托管部署下使用可用的目录来源，加载成功时展示可用扩展并支持筛选（AC-22-1）；加载失败时区分「空目录」与「加载失败」两种状态并给出原因（AC-22-2）。
  - **权限**：没有配置权限的用户保持只读，安装入口不可用；目录加载失败不呈现为安装成功（AC-22-3）。
  - **验证方法**：在无旧 marketplace 地址的配置下打开目录断言可浏览筛选；模拟加载失败断言错误态与空态可区分；只读用户断言安装入口不可用。

### FD08 · 密码登录模式配置
- 覆盖需求：R17
- 设计说明：
  - **页面与路径**：`src/siteSettings/views/index.tsx`、`src/siteSettings/components/SiteSettingsPage/SiteSettingsPage.tsx`、`src/siteSettings/mutations.ts`（`shopSettingsUpdate`）。
  - **设计**：新增「密码登录模式」表单项，三选一（ENABLED / CUSTOMERS_ONLY / DISABLED），读取 `Shop.passwordLoginMode` 的当前生效值；页面同时展示权限限制说明与当前模式的影响（AC-17-5）。
  - **数据流**：提交走既有 `shopSettingsUpdate`，成功后以服务端返回的 `shop.passwordLoginMode` 更新表单与缓存；失败保留上一次生效值，不把未保存值当作生效值（AC-17-6）。
  - **权限**：无商店设置权限时控件只读并显示原因；提交被拒绝时展示错误。
  - **验证方法**：保存后重新读取断言一致；模拟保存失败断言表单回到生效值；无权限断言只读。

### FD09 · 登录入口与禁用空态
- 覆盖需求：R17
- 设计说明：
  - **页面与路径**：`src/auth/views/Login.tsx`、`src/auth/components/LoginPage/LoginPage.tsx` 与其 `form.tsx`（`useLoginForm`）、`src/auth/hooks/useAuthProvider.ts`（`handleLogin`）、`src/auth/views/ResetPassword.tsx`、`NewPassword.tsx`。
  - **设计**：登录页读取 `Shop.passwordLoginMode`；`DISABLED` 时不渲染密码登录入口，也不渲染密码重置入口；`CUSTOMERS_ONLY` 时保留客户可用路径但对员工会话的失败给出明确说明（AC-17-2、AC-17-3 的前端部分）。当没有任何可用外部方式时显示稳定空态而不是空白或报错（AC-17-5）。
  - **数据流**：模式在页面加载时读取；读取失败时不显示任何误导性的可用入口，按「未知」保守呈现并提供重试。
  - **验证方法**：三种模式下渲染断言入口可见性；无外部方式时断言空态；服务端拒绝密码登录时断言错误文案对应错误码。

### FD10 · 外部认证入口与失败展示
- 覆盖需求：R18
- 设计说明：
  - **页面与路径**：`src/auth/`（`AuthRouter`、`AuthProvider.tsx`）、`src/auth/utils.ts`（`getExternalAuthenticationMethodName`、`handleQueryAuthError`）。
  - **设计**：外部认证入口沿用既有实现；失败时展示可识别的错误信息，**不显示也不持久化令牌或敏感身份信息**（AC-18-2 的前端部分）。
  - **验证方法**：模拟授权失败断言错误可识别且 localStorage/会话存储中无 token 与身份字段。

### FD11 · 渠道自动完成配置
- 覆盖需求：R06（并展示 R05 的可观察结果，不模拟后台执行）
- 设计说明：
  - **页面与路径**：`src/channels/views/ChannelDetails/ChannelDetails.tsx`、`src/channels/components/ChannelForm/ChannelForm.tsx`、`src/channels/pages/ChannelDetailsPage/ChannelDetailsPage.tsx`。
  - **设计**：在渠道设置中展示并编辑「自动完成」开关（既有 `automaticallyCompleteFullyPaidCheckouts`）、延迟（分钟）与 cutoff（日期时间）。延迟输入不接受负值；cutoff 的文案明确说明它是结账创建时间的下界而不是任务停止时间（AC-06-4 的前端说明）。
  - **设置与执行分离**：保存成功只提示「设置已保存」，**不显示任何订单已生成的结论**；订单是否完成以结账与订单状态为准（AC-06-6）。
  - **结账侧状态展示**：在结账详情读取 `Checkout.automaticCompletion`（I05），展示 `status`、`blockers` 与 `eligibleAt`，用于解释「为何还没成单」（AC-05-6 的前端部分）；该状态只读，前端不据此推断订单已生成。
  - **校验与失败**：范围或组合非法、无权限、保存冲突都展示明确错误并保留上次生效值（AC-06-5）；保存中禁用重复提交。
  - **验证方法**：保存后重读断言一致；输入负延迟断言提交前校验失败；模拟保存冲突断言错误展示且表单保留旧值；断言成功提示文案不含订单已生成。

### FD12 · 结账配送选项展示与重校验（Storefront 与 Dashboard 结账详情）
- 覆盖需求：R01、R02、R03
- 设计说明：
  - **页面与路径**：Storefront 侧不在本仓库内，前端消费约定由 I01–I03 定义；Dashboard 侧为结账详情视图（`src/checkouts/`，配送选择复用 `ShippingMethod` 相关选择器）。本轮 Dashboard 侧的改动是：配送选择展示改用结账为主体的选项查询结果，并在提交前接受服务端的重校验结果。
  - **设计**：展示「可用选项 + 当前选择」两组信息；当返回的 `selectedDeliveryOption.status` 为 `UNAVAILABLE` 时，明确提示当前选择已失效并要求重新选择，不静默替换（AC-01-2、AC-01-3）。更新配送选择或提交完成时，若服务端返回 `DELIVERY_METHOD_INVALIDATED`/`DELIVERY_METHOD_OUT_OF_SCOPE`/`SHIPPING_ADDRESS_NOT_SET`/`SHIPPING_METHOD_NOT_SET`，分别展示可区分的失效原因，且不改变原有的配送选择（AC-02-1 至 AC-02-3）。
  - **旧字段兼容**：Dashboard 不新提交旧字段；仅在读取路径上兼容旧字段（FD25 保证生成客户端与错误映射一致）（AC-03-1）。
  - **失败处理**：查询失败展示错误态并保留上一次有效选择，不写入半成品选择（AC-01-4）；无权限或结账不属于调用方展示权限/不存在错误，不泄露配送信息（AC-01-5、AC-02-5）。
  - **验证方法**：模拟选项列表变化断言旧选项消失；模拟 `status: UNAVAILABLE` 断言提示；模拟四类失效错误码断言文案与状态；失败后断言原选择未被改写。

### FD13 · 渠道库存模式配置与展示
- 覆盖需求：R04
- 设计说明：
  - **页面与路径**：`src/channels/components/ChannelForm/` 或渠道设置页的库存设置区（现有 `allocationStrategy` 表单位置附近）、`src/products/components/ProductStocks/`。
  - **设计**：新增库存可用性模式选择（`SHIPPING_ZONES` / `CHANNEL_WAREHOUSES`），默认显示当前值；切换前给出影响说明（新模式下由渠道直接关联的仓库决定可售计算）。切换到新模式后，商品库存与渠道仓库分配视图展示一致的结果（AC-04-2 的前端部分）。
  - **数据流**：保存走 `channelUpdate` 的库存设置输入（I04）；成功后刷新渠道与相关商品数据；失败保留原值。
  - **验证方法**：保存后重读断言一致；切换模式后对比商品库存视图与渠道设置页的仓库集合，断言基于同一事实。

### FD14 · 订单金额摘要
- 覆盖需求：R12
- 设计说明：
  - **页面与路径**：`src/orders/views/OrderDetails/` 下的金额摘要区与 `src/components/Money/index.ts`（`formatMoney`、`subtractMoney`）。
  - **设计**：摘要按固定口径分行展示：商品（`subtotal`）、折扣（`discounts`）、税费（`total.tax`）、配送（`shippingPrice`）、礼品卡（新增 `totalGiftCard`）、已授权（`totalAuthorized`）、已扣款（`totalCharged`）、已退款（`totalRefunded`）、剩余待付（`totalBalance`）。**不在前端做二次汇总或覆盖服务端数值**，各行直接来自服务端；礼品卡行单独呈现，不与普通支付行合并（AC-12-1、AC-12-4）。
  - **一致性提示**：当各行组合与服务端 `total` 不一致时（例如服务端数据在加载中变化），以服务端数值为准并提示需要刷新，不就地修正金额。
  - **数据流**：所有金额来自同一次订单查询的结果，不混用列表页缓存数据。
  - **验证方法**：构造含折扣/税费/配送/礼品卡/多笔支付的订单断言各行与服务端一致；断言礼品卡行不重复计入支付行；断言前端不产生额外加减。

### FD15 · 交易与礼品卡区分、交易定位
- 覆盖需求：R10、R11、R14
- 设计说明：
  - **页面与路径**：订单详情的交易区与结账详情的支付区；新增或改造交易列表视图，数据来自根级 `transactions` 查询（I14）。礼品卡展示复用 `src/components/` 下的金额与状态展示组件。
  - **设计**：交易卡按 `paymentMethodDetails.__typename` 区分支付方式——`GiftCardPaymentMethodDetails` 显示为礼品卡并展示卡号尾号与礼品卡链接，`CardPaymentMethodDetails` 显示卡品牌与尾号，`OtherPaymentMethodDetails` 显示名称（AC-11-4）。礼品卡交易与普通交易在同一列表中但以类型标识区分，金额不合并（AC-10-1）。
  - **查账与定位**：交易列表支持按订单/结账关联、交易 ID、服务商参考号、App 标识筛选与游标翻页（AC-14-1 至 AC-14-3）。**不提供**按日期或事件类型的筛选，也不提供该列表的专用排序入口（AC-14-5、AC-32-2）。
  - **事件展示**：交易事件为空时显示空事件列表而不是整卡错误（AC-11-5）；请求失败显示可识别原因与重试（AC-11-4）。
  - **可见范围**：列表只渲染服务端返回的交易；无权限时不渲染入口或展示权限错误，不显示其他对象的交易详情（AC-14-4）。
  - **验证方法**：混合礼品卡与普通支付的订单断言区分与不合并；按四类条件各筛选一次；断言无日期/事件筛选入口与排序控件；空事件断言空列表；无权限断言错误态。

### FD16 · 人工资金动作可用性与错误
- 覆盖需求：R13
- 设计说明：
  - **页面与路径**：订单详情的操作区（`OrderAction` 相关按钮：标记已支付、捕获、退款、作废）与 `src/orders/components/OrderDraftPage/OrderDraftPage.tsx` 之外的订单详情页。
  - **设计**：只渲染服务端 `Order.actions` 返回的动作；未返回的动作不显示为可用（AC-13-1）。金额输入使用正数校验，负数在提交前被阻止；捕获输入的上限提示为当前可捕获授权，退款输入的上限提示为可退余额（AC-13-3、AC-13-4）。
  - **错误处理**：按错误码分别展示——超授权/超可退余额（`AMOUNT_GREATER_THAN_AVAILABLE`）、已有支付记录（`PAYMENT_ALREADY_EXISTS`）、无授权可捕获（`CAPTURE_INACTIVE_PAYMENT`）、无可退余额（`CANNOT_REFUND`）；失败保留原状态并允许重试（AC-13-6）。
  - **幂等**：提交期间禁用按钮，避免重复点击；失败重试沿用同一表单状态（AC-13-5 的前端部分）。
  - **权限**：无权限不渲染入口或展示权限错误，不显示受限金额（AC-13-7）。
  - **验证方法**：对不同订单状态断言动作集合；输入负金额断言阻止；模拟各错误码断言文案；连续点击断言只发出一次请求；成功后断言重新读取到刷新后的金额与事件。

### FD17 · 富文本编辑与校验错误定位
- 覆盖需求：R19
- 设计说明：
  - **页面与路径**：富文本字段的编辑组件（商品描述、页面内容、RICH_TEXT 属性）与其错误展示；错误映射复用 `src/fragments/errors.ts` 的对应 fragment 与 `src/utils/errors/product.ts`、`src/utils/errors/page.ts`（若存在）。
  - **设计**：保存失败时把 `RICH_TEXT_INVALID`、`RICH_TEXT_UNSAFE_LINK`、`RICH_TEXT_TOO_DEEP` 三个错误码映射为可读文案，并把错误定位到具体富文本字段；`message` 中的链接或深度信息直接展示，帮助用户知道改哪里（AC-19-5）。错误不表现为保存成功（AC-19-5）。
  - **正常路径**：合法富文本（含嵌套列表与常用链接）保存成功且不改变现有编辑体验（AC-19-1）。链接的 `rel` 安全行为由渲染层与服务端共同保证，前端渲染富文本外链时按既有安全规则处理（AC-19-3）。
  - **验证方法**：提交非法内容断言错误定位与文案；提交合法内容断言成功；断言失败后编辑内容未被清空。

### FD18 · 扩展数据展示迁移
- 覆盖需求：R20
- 设计说明：
  - **页面与路径**：`src/extensions/hooks/useExtensions.ts`、`src/extensions/views/InstalledExtensions/`、`src/extensions/components/AppWidgets/AppWidgets.tsx`、`src/extensions/components/AppExtensionContext/`。
  - **设计**：扩展查询改用 `mountName`/`targetName`/`settings`（I18）选择与渲染扩展；`mount`/`target` 仅作为迁移期兜底读取，新代码不提交旧字段（AC-20-5）。对 `mountName`/`targetName` 为 `null` 的历史数据提供稳定的兜底展示（不因空值崩溃或隐藏扩展）（AC-20-2、AC-20-1）。
  - **数据流**：扩展列表与 widget 挂载按 `mountName`/`targetName` 匹配当前约定的挂载点；未知取值不渲染 widget 但保留扩展条目可见。
  - **验证方法**：对 `mountName` 为 `null` 的历史扩展断言可见可渲染；断言发出的查询不含旧字段；断言筛选按新字段生效。

### FD19 · Webhook 投递状态与单条重试
- 覆盖需求：R24
- 设计说明：
  - **页面与路径**：`src/extensions/views/EditManifestExtension/components/AppWebhooksDisplay/`（`EventDeliveriesList.tsx`、`EventDeliveryItem.tsx`、`EventDeliveriesStatus.tsx`、`AppWebhooksAttemptDetails.tsx`）与 `src/extensions/components/AppAlerts/useAppsFailedDeliveries.ts`。基线**没有重试入口**，需要新增。
  - **设计**：投递状态展示 `PENDING`（等待）、`RETRYING`（重试中）、`SUCCESS`、`FAILED` 四态，并展示错误信息与尝试次数；`PENDING` 明确标注「内容尚未生成/尚未投递」，绝不显示为成功（AC-24-4）。对未知状态值按非终态保守展示，避免新状态导致界面误判。
  - **单条重试**：对 `FAILED` 的投递提供单条重试入口，调用 `eventDeliveryRetry`（I21）；重试中禁用按钮并展示进行中状态（AC-24-5）。
  - **告警**：既有 Webhook 失败告警保留，不改造为 App Problems 类型的问题列表（AC-24-6、AC-32-1）。
  - **验证方法**：构造四种状态的投递断言展示；触发单条重试断言只有该条进入重试中；断言告警入口仍在且不含 App Problems 结构。

### FD20 · 订单与履约的配送元数据快照展示
- 覆盖需求：R25
- 设计说明：
  - **页面与路径**：订单详情的配送信息区与履约详情区（`src/orders/views/OrderDetails/`、履约详情页）。
  - **设计**：展示 `deliveryMethodSnapshot`（I22）中的名称与 public 元数据；有权限时展示 private 元数据，无权限时不渲染该部分（AC-25-4）。快照为空（历史订单无快照）时展示稳定空值而不报错（AC-25-5）。
  - **设计意图提示**：以「创建时快照」的标签说明这是历史事实，避免与当前配送方式混淆（AC-25-3）。
  - **验证方法**：断言快照展示；修改/删除配送方式后重新加载断言内容不变；无权限断言不渲染 private 部分；快照为空的订单断言空态。

### FD21 · 基础元数据编辑边界
- 覆盖需求：R26
- 设计说明：
  - **页面与路径**：`src/components/Metadata/MetadataCardTable.tsx`、`src/components/MetadataHookForm/MetadataHookForm.tsx`、`src/utils/metadata/`、`src/utils/handlers/metadataUpdateHandler.ts`。
  - **设计**：结账、草稿订单、订单与履约继续使用既有基础元数据编辑（公共与私有），订单详情的行内编辑与订单行元数据保留（AC-26-1、AC-26-2）。**不新增**订单、履约、仓库的独立元数据弹窗、专用路由或独立入口，也不通过隐藏路由恢复（AC-26-4、AC-32-1 的元数据部分）。
  - **失败处理**：非法值、权限不足、保存失败时保留原值、不出现部分写入（AC-26-3）；失败提示可区分。
  - **验证方法**：对四类对象执行基础读写断言成功；提交非法值断言原值不变；枚举路由与菜单断言无独立元数据入口。

### FD22 · 迟到配置数据与编辑上下文
- 覆盖需求：R30
- 设计说明：
  - **页面与路径**：`src/hooks/useForm/index.ts`、`src/hooks/useStateFromProps.ts`、`src/channels/views/ChannelDetails/ChannelDetails.tsx`、`src/siteSettings/views/index.tsx`、商品编辑页表单。
  - **设计**：把表单初始化改为「仅在字段未被用户修改过时回填」。为每个受控字段记录脏标记；迟到的数据到达时只回填未触碰的字段，用户正在输入的值不被覆盖（AC-30-3）。页面状态机区分：加载中、已加载但空数据、权限错误、网络错误、可重试；加载期间不渲染误导性默认值，不闪烁错误值（AC-30-1、AC-30-2）。
  - **保存与缓存**：保存成功后才更新相关缓存或重新读取服务端事实；失败保留原状态、失败值不进入缓存、修正后可重试（AC-30-4）。
  - **验证方法**：延迟注入查询响应，断言用户已输入字段未被覆盖；断言四种状态互不混淆；模拟保存失败断言缓存未变、重试成功。

### FD23 · 重量、金额、媒体与订单时间展示准确性
- 覆盖需求：R31
- 设计说明：
  - **页面与路径**：`src/misc.ts` 的 `weight`（当前只有 `parseFloat`，**没有单位换算**）、`src/components/Weight/Weight.tsx`、`src/components/WeightRange/WeightRange.tsx`、`src/components/Money/index.ts`、`src/products/components/ProductMedia/`、`src/hooks/useDateLocalize.ts`、`src/components/Timezone/`。
  - **设计**：新增重量单位换算工具（按 `shop.defaultWeightUnit` 与商品类型自身的 `weight.unit` 换算后展示），替换只做 `parseFloat` 的现状（AC-31-1）。金额展示统一走 `formatMoney`/`formatMoneyRange`，折扣金额与 API 一致。媒体错误状态按既有正常状态展示，不引入异步抓取或专用 fallback（AC-31-3、AC-32-4）。订单日期分组按用户 locale 与 timezone 计算（新增分组工具，基线无此实现），跨日期边界的订单不归错组（AC-31-2）。
  - **验证方法**：用不同源单位与目标单位的重量断言换算结果；断言折扣金额与 API 一致；用非 UTC timezone 穿越日期边界的订单断言分组正确；断言媒体错误状态展示且无异步抓取状态。

### FD24 · 草稿订单动作可用性与原因
- 覆盖需求：R31
- 设计说明：
  - **页面与路径**：`src/orders/views/OrderDetails/OrderDraftDetails/index.tsx`、`src/orders/components/OrderDraftPage/OrderDraftPage.tsx`、`OrderDraftAlert.tsx`。
  - **设计**：根据渠道 `isActive`、渠道是否有可售商品、是否缺少必要配置（如配送/仓库配置）判定「添加商品」「完成」等动作是否可用；不可用时禁用并给出原因（通过 `OrderDraftAlert` 的告警结构或按钮旁的说明展示，基线只有零散 tooltip，需要在草稿页统一封装一个原因提示）（AC-31-4）。禁用时不发送请求。切换到满足条件的正常渠道后动作恢复可用（AC-31-5）。
  - **验证方法**：构造停用渠道、无可售商品、缺配置三种情况断言动作禁用与原因；断言未发出请求；切换渠道断言恢复可用。

### FD25 · 生成客户端、错误映射与权限一致性
- 覆盖需求：R27、R28、R29
- 设计说明：
  - **页面与路径**：`src/graphql/types.generated.ts`（由 codegen 从 Core schema 生成）、`src/graphql/client.ts`、`src/misc.ts`（`getMutationErrors`、`extractMutationErrors`、`getMutationState`）、`src/fragments/errors.ts`、`src/utils/errors/`、`src/utils/api.ts`（`GqlErrors`、`hasError`）。
  - **设计**：重新生成客户端类型，使生成文件与 `target-schema.graphql` 一致；弃用字段的使用点改用替代路径（FD18 扩展字段、FD15 交易字段、`voucherCode` 替代 `voucher`），不在生成文件中保留不支持的操作（AC-28-6、AC-32-2）。
  - **失败语义**：不把 HTTP 200 当作业务成功。统一的提交判定为「无顶层 `errors` 且 `payload.errors` 为空」（AC-27-1、AC-27-5）。错误展示按 `code` 分支映射到文案；未知错误码回退到 `message` 并标记为未分类，不显示为成功（AC-27-5）。为新增错误码补齐映射：`CheckoutErrorCode` 的 `DELIVERY_METHOD_INVALIDATED`、`DELIVERY_METHOD_OUT_OF_SCOPE`、`DELIVERY_SERVICE_ERROR`、`GIFT_CARD_*`；`OrderErrorCode` 的 `AMOUNT_GREATER_THAN_AVAILABLE`、`PAYMENT_ALREADY_EXISTS`；`AccountErrorCode` 的 `PASSWORD_LOGIN_DISABLED`、`PASSWORD_LOGIN_CUSTOMERS_ONLY`；`AppErrorCode` 的 `INVALID_MOUNT_NAME`、`INVALID_TARGET_NAME`、`INVALID_SETTINGS`；`AttributeErrorCode`/`PageErrorCode`/`ProductErrorCode` 的三个富文本码；新增枚举值 `PaymentMethodTypeEnum.GIFT_CARD`、`EventDeliveryStatusEnum.RETRYING`、`CheckoutAutomaticCompletionStatusEnum`、`CheckoutAutomaticCompletionBlockerEnum`、`ProductChannelDiagnosticSeverityEnum`、`StockAvailabilityModeEnum`、`PasswordLoginModeEnum`、`DeliveryOptionStatusEnum` 也需在展示层有归类，未知值走保守分支。
  - **权限**：列表、弹窗、导出、批量操作与错误信息使用同一可见范围；无权限展示权限错误而不是空列表，失败不展示为成功（AC-29-5）。
  - **验证方法**：运行 codegen 断言无错误且生成文件不含被排除操作；对每个新增错误码断言有文案映射；构造无权限响应断言展示权限态；构造业务失败断言不展示成功。

### FD26 · 搜索范围与状态可辨
- 覆盖需求：R08、R09
- 设计说明：
  - **页面与路径**：各列表页的搜索框与筛选器（商品、订单、结账、礼品卡、客户、员工、页面），复用 `src/utils/filters/filters.ts` 与 `src/components/Filter/`。
  - **设计**：主体对象的搜索框保留关键词、前缀、组合词与短语的行为，不整体关闭（AC-08-1）。客户与员工使用按空格组合词匹配的搜索；页面使用标题/slug/内容搜索（AC-08-2）。**不提供**页面与用户的高级搜索、相关度增强或 RANK 排序入口（AC-08-3、AC-32-2）：排序控件只列出服务端提供的排序项，`GiftCardSortField`、`CheckoutSortField`、`PageSortField`、`UserSortField` 无 RANK，前端不为它们构造本地排序。
  - **状态**：加载态、空结果空态、校验错误、搜索服务错误分别呈现；空关键词不触发查询；过长输入给出校验提示且不阻塞其他列表操作（AC-09-3、AC-09-4）。翻页保留关键词与排序，游标稳定，不出现重复或漏项（AC-09-2）。弹窗、列表与筛选器使用与服务端一致的搜索语义（AC-09-5 的前端部分）。
  - **验证方法**：对每个列表输入组合词与短语断言结果；断言排序控件不含 RANK；空关键词断言不发请求；模拟服务异常断言错误态与重试且其他列表可用；连续翻页断言无重复项。

### FD27 · 交付范围边界
- 覆盖需求：R32
- 设计说明：
  - **设计**：前端不新增以下能力，也不通过别名、隐藏路由或生成文件重新暴露：App Problems 的类型、页面与入口（Webhook 失败告警保留，见 FD19）；页面与用户的高级搜索、交易日期或事件过滤及专用排序（见 FD26、FD15）；异步外链图片抓取与 pending/503/proxy 状态及专用 Dashboard fallback（见 FD23）；独立变体生成器页面、菜单、任务、状态与专用入口；订单、履约与仓库的独立元数据弹窗、专用路由与独立入口（见 FD21）。
  - **保留的能力**：普通单变体创建、必填属性、`hasVariants` 兼容行为与普通批量创建；同步外链图片、本地上传与外部视频/oEmbed；基础搜索；基础交易查询；基础元数据编辑；Webhook 失败告警。
  - **验证方法**：对照路由表、菜单配置与生成文件逐条核对被排除能力不存在；对被保留能力做一次回归确认可用。

## 4. 依赖与联调

| 接口 | 消费方设计单元 | 对应需求 | 开发依赖 |
| --- | --- | --- | --- |
| I01 | FD12 | R01 | 需等待 |
| I02 | FD12 | R02 | 需等待 |
| I03 | FD12 | R03 | 可独立开发 |
| I04 | FD13 | R04 | 需等待 |
| I05 | FD11 | R06 | 需等待 |
| I06 | FD11 | R06 | 需等待 |
| I07 | FD01、FD02 | R07 | 需等待 |
| I08 | FD26 | R08 | 可独立开发 |
| I09 | FD26 | R09 | 可独立开发 |
| I10 | FD15 | R10 | 需等待 |
| I11 | FD15 | R11 | 需等待 |
| I12 | FD14 | R12 | 需等待 |
| I13 | FD16 | R13 | 可独立开发 |
| I14 | FD15 | R14 | 需等待 |
| I15 | FD08、FD09 | R17 | 需等待 |
| I16 | FD10 | R18 | 可独立开发 |
| I17 | FD17 | R19 | 需等待 |
| I18 | FD18 | R20 | 需等待 |
| I19 | FD07、FD18 | R20、R22 | 需等待 |
| I20 | FD19 | R24 | 需等待 |
| I21 | FD19 | R24 | 可独立开发 |
| I22 | FD20 | R25 | 需等待 |
| I23 | FD21 | R26 | 可独立开发 |
| I24 | FD25 | R27 | 可独立开发 |
| I25 | FD25 | R28 | 需等待 |
| I26 | FD25 | R29 | 可独立开发 |

**可独立开发的前提**：`可独立开发` 表示前端可基于基线既有契约先完成布局、交互与错误分支，只在与服务端联调时校对文案与边界。具体为：

- I03、I08、I09、I23、I26 在基线中已存在，前端改动不依赖新字段。
- I13 的四个变更签名不变，前端可先按现有 `Order.actions` 与既有错误码实现动作可用性与错误分支，仅新增两个错误码的文案映射需要与 I24 一起校对。
- I16 为非 GraphQL 协议，前端只做入口与失败展示。
- I21 的变更在基线中已存在（`eventDeliveryRetry`），前端可先行接入；`RETRYING` 状态的展示配合 I20。
- I24 的校验行为由服务端保证，前端可先按「只要不返回成功即不显示成功」的通用规则实现。

**需等待的接口**：FD01/FD02（I07 是新查询）、FD12（I01 是新查询）、FD11（I05/I06 是新字段）、FD13（I04 是新字段）、FD14/FD15（I10–I12、I14 含新字段与新查询）、FD17（I17 是新错误码）、FD18（I18 是新字段）、FD19（I20 的 `RETRYING` 是新枚举值）、FD20（I22 是新字段）。这些单元的界面框架可以先搭，但字段绑定与文案需在 Core 提供对应契约后联调。

**需要的 mock**：在 Core 未就绪前，前端用本地 mock 覆盖五类场景——配送选项列表与失效状态（I01/I02）、渠道诊断的多严重度明细（I07）、礼品卡与普通交易混合列表（I10/I14）、投递四态（I20）、自动完成状态与阻断原因（I05）。

**联调安排**：按依赖分组联调——先 I03/I08/I09/I23/I26（无新契约），再 I01/I02/I05/I06/I07（结账与渠道），再 I10–I14（资金与交易），最后 I17/I18/I20/I22/I25（内容、扩展与历史数据）。每组以 `interface-contract.md` 对应条目的「完成判定」作为联调通过标准。

## 5. 其他

### 风险

- **锁定筛选（FD03）是新增机制**，基线无对应实现（无 `useListQueryParameters`，无 locked/preselected 筛选）。风险是与既有 `useFilterHandlers`、`useFilterPresets` 与条件筛选的 `Constraint` 机制产生职责重叠。缓解：把锁定条件建模为独立于用户条件的一组参数，在条件合并的唯一入口处注入，避免在各页面分别实现。
- **分类层级选择器（FD05）目前是扁平列表**，需要新增层级导航。风险是改动 `AssignCategoryDialog` 会影响所有使用它的页面。缓解：保持 `AssignContainerDialog` 的接口不变，只在分类场景注入层级数据与面包屑。
- **重量单位换算（FD23）目前不存在**，`misc.ts` 的 `weight` 只做 `parseFloat`。风险是替换后影响所有展示重量的页面。缓解：新增换算工具并逐处替换，保留原函数签名兼容。
- **订单日期分组（FD23）目前不存在**。风险是 locale 与 timezone 组合多，边界容易出现归组错误。缓解：以 `useDateLocalize` 与 `Timezone` 上下文的现有值为唯一输入，覆盖跨日、跨月与夏令时边界用例。
- **生成客户端（FD25）会在 schema 变更后产生大量 diff**。缓解：按 I 编号分批重生成并逐批核对，弃用字段的使用点在同一批内迁移。
- **新增枚举值（`GIFT_CARD`、`RETRYING` 等）会让既有 `switch` 落入默认分支**。缓解：在展示层为未知值建立保守分支（非终态、非成功），并以 FD25 的错误与状态映射清单逐条覆盖。

### 验证计划

| 范围 | 方法 |
| --- | --- |
| 组件与页面逻辑 | 单元测试与组件测试，覆盖 FD01–FD27 的交互与状态分支 |
| 权限与可见范围 | 以无权限/只读身份跑关键页面，断言错误态而非空态、失败不显示成功 |
| 错误映射 | 对每个新增错误码与新增枚举值构造响应，断言文案与保守分支 |
| 生成一致性 | 运行 codegen，断言生成文件与 `target-schema.graphql` 一致且不含被排除操作 |
| 范围边界 | 对照路由、菜单与生成文件核对被排除能力不存在（FD27） |

### 未决项

- 渠道诊断明细的展示层级（是否折叠、默认展开哪一级）需与商品运营确认。
- 锁定条件的移除入口在哪些入口允许开放，需与商户运营确认。
- 重量换算的取整与小数位规则沿用商店单位设置还是固定精度，需与商户运营确认。
- 交易列表在订单详情内的呈现方式（内嵌列表还是跳转独立视图）需与客服确认，但不影响契约。

<!-- FD 编号发布后不重排、不复用。接口编号取自 interface-contract.md；此处不重复定义权威契约。沿用 PRD 的业务名称。 -->
