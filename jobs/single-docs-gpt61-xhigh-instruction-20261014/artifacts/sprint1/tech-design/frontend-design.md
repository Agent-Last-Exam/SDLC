# 前端技术设计：Saleor 3.23 商户工作台与服务端事实一致

版本：v1（2026-10-14）
责任：前端技术设计
依据：PRD v1，artifacts/sprint1/prd/prd.md
修订：首次交付；只设计不开发。冻结 PRD/测试不修改，发现的 Base 差异仅在本文件记录。

## 1. 方案概述

Dashboard 3.22.9（给定 commit aebb2401b5079fbbb8c60150289d1896c108feca）继续使用 React17/TypeScript、Apollo3.4、React Router v5、React Intl、Macaw 与既有业务表单/hooks。按 feature 的 queries/mutations/views/components 模式改动，不另建 Storefront、交易报表、元数据管理系统或变体生成器。Storefront 通过 I01/I02/I07/I06 集成公开接口，不在本轮新建第三个前端仓库。

统一四个前端原则：

1. **一份服务端事实**：库存模式/自动完成生效设置、订单金额与可操作额度、扩展字段、草稿资格均读 Core；本地只预校验，不模拟后台完成，不从礼品卡事件重造一份订单总额。
2. **一个有效查询上下文**：锁定条件与可编辑条件分离，列表/分页/选择器/导出/批量由同一快照派生，不以 spread 覆盖同名锁定条件。
3. **加载、编辑、已保存分开**：区分 loading/empty/forbidden/networkError/loaded；保存只在 payload 非空且 errors=[]、必要结果存在时成功。脏字段和晚到响应以 context/revision 保护。
4. **前后端一个合同**：接口编号 I01— I26 取自 `interface-contract.md`，SDL 为 `target-schema.graphql`；重新生成 GraphQL types/hooks/typePolicies/fragmentTypes，不手补生成文件绕过缺字段。退出能力从源 operations移除，再生成，而非让生成客户端继续支持。

### 已确认的实际代码差异

| 落点 | 当前事实与拟改变 |
| --- | --- |
| `src/channels/components/ChannelForm/AutomaticallyCompleteCheckouts.tsx` | 只有checkbox；新增delay/cutoff、明确保存vs执行，修正rel文案 |
| `src/products/components/ProductVariantChannels/ChannelsAvailabilityCard/` | 已有过滤/count/hooks测试；改读Core分页诊断，不前端单独重复库存算法 |
| `src/orders/components/OrderPaymentOrTransaction/OrderTransactionsWrapper.tsx`、`src/ordersV2/OrderDetailsViewModel.ts` | 分别列Transaction/Payment/giftcard且历史事件推金额；适配source去重和server summary |
| `src/orders/components/OrderSummaryCard/utils.ts` | oldCurrentBalance fallback表达式易受优先级影响；新模式不从差额猜支付，旧历史使用显式安全兼容投影 |
| `src/hooks/useFilterHandlers.ts` | reset只保留sort/asc，普通合并可能覆盖context；拆locked/editable有效条件 |
| `src/extensions/queries.ts`、`domain/app-extension-manifest.ts` | 查询已读新字段但manifest still ext.target；统一新命名与旧规范化适配 |
| `src/extensions/views/ViewManifestExtension/components/AppFrame/useAppActions.ts:65` | 只比较origin，未知action抛错，无source/form revision；加强frame鉴别与明确失败 |
| `src/extensions/views/ExploreExtensions/hooks/useAppStoreExtensions.ts`、`src/config.ts` | 依赖appStoreUrl/旧marketplace配置、按英文category name映射；转当前静态来源/按id/运行时shape验证 |
| `src/components/Weight/Weight.tsx` | 当前仅插值unit/value；新增真正单位换算，不仅换标签 |
| `src/orders/components/OrderHistory/OrderHistory.tsx` | 逐event渲染并传date；日期key在Timeline/共享date层统一timezone后归组 |

以上均为 Base 事实，不表示已修复。本设计遵守仓库 CLAUDE 及 ConditionalFilter/CLAUDE、IMPLEMENTATION_GUIDE 的映射/URL/注册一致要求。

## 2. 需求覆盖

| 需求 | 设计单元 |
| --- | --- |
| R03、R06 | FD01 |
| R04 | FD02 |
| R05 | FD01、FD03（只展示实际状态，不执行批次） |
| R07、R08、R09、R10、R11 | FD03 |
| R12、R13 | FD04 |
| R14、R15 | FD05 |
| R16、R17 | FD06 |
| R18 | FD07 |
| R19、R20 | FD08 |
| R21 | FD09 |
| R22、R23 | FD10（投递可见性；解析/worker在Core） |
| R24、R25 | FD11 |
| R26、R27、R28、R31 | FD13及各页面权限/错误分支 |
| R29 | FD12及FD01/FD02/FD06/FD08 |
| R30 | FD12 |

不直接承接：R01/R02 是 Storefront 的配送调用与 Core 校验，当前 Dashboard 无独立客户结账页面，接口示例/验证在契约；R05 的批次/资金幂等、R07 初始化扣款、R17 provider后端关联、R22 deferred工作与R27迁移由后端实现。Dashboard仍承接对应设置/读数/失败/兼容，不以“不写Storefront”删掉所需API。

## 3. 详细设计

### FD01 · 渠道库存模式、自动完成配置与执行状态
- 覆盖需求：R03、R05、R06、R29。
- 设计说明：在 `channels/views/ChannelDetails/ChannelDetails.tsx`、handlers、`ChannelForm` 和 queries/mutations增加 availabilityStrategy selector（LEGACY/CHANNEL_WAREHOUSES），与 `ChannelAllocationStrategy` 排序控件分开，不将“仓库直连”当分配优先级。旧服务端未读到数据不能显示新模式默认已生效。
- checkbox附带delay分钟整数0..10080和cutoff日期时间，表单明确“最近变化超过延迟”“创建时间不早于cutoff”“不是停止执行时间”；display本地timezone，发送ISO UTC，null显式清除cutoff，未改字段省略。关开关不清时间配置，输入保留服务端currentSettings/expectedSettingsRevision。无MANAGE_CHANNELS只读，不尝试保存。
- 保存按钮pending防二次提交、errors映射field、CONFLICT显示当前版本并允许重新读取/合并，不自动覆盖dirty值。只在成功回执更新生效快照；toast“配置已保存”，不“订单已完成”。可在已有checkout/order业务上下文展示I06 status、order链接和安全错误code，不新造自动化管理系统/轮询全部订单；每次view进入/显式刷新查实际状态，COMPLETED必须含order。
- 仓库关系更改提示会影响新可用库存，既有order allocation不是立即重分配；移除重复selectedwarehouse按ID归一。channel切换使旧异步结果失效。
- 验证：ChannelForm、useSaveChannel/handlers tests；新旧模式、delay/cutoff边界/omit/null、false/true旧数据、迟到response、权限/网络/冲突与保存vs后台状态；Playwright多tab冲突。

### FD02 · 商品按渠道诊断
- 覆盖需求：R04、R29、R28。
- 设计说明：`ProductUpdate` / `ChannelsAvailabilityCard` 读 I04，独立cursor/关键词（名称或币种）/channel过滤状态，不用本地过滤仅已加载channel误充全量。展示blockingCount/warningCount与按severity折叠checks，PASS不堆红告警，NOT_APPLICABLE说明数字商品跳过配送而非全部通过。
- 每份诊断保留evaluatedAt和product/context id。保存商品/库存/渠道成功后只使相关diagnostic query失效/重取；未保存编辑用“诊断依据已保存版本”提示，不向用户许诺当前输入已可售。loading skeleton、合法no channels、forbidden、network错误及retry分开；失败保留上一次结果但加陈旧标记，不能当最新。
- 展开明细只显示服务器已允许的channel/variant字段，不从message猜受限warehouse；商品/员工权限不足禁查询和编辑。请求取消/sequence guard防旧product回包污染新商品。
- 验证：`useFilteredChannelListing.test.ts`、`availabilityCount.test.ts`补服务端count/rank-independentcursor；未发布、future available、digital缺库存、正常依赖不误报、无权与dirty状态。

### FD03 · 订单资金、礼品卡与安全动作
- 覆盖需求：R05、R07、R08、R09、R10、R11、R26、R28。
- 设计说明：共同金额adapter接收 I08 `Order.paymentSummary`、Transaction method details/actions/available金额和兼容Payment，驱动 `OrderPaymentSummaryCard`、`OrderTransactionsWrapper`、`OrderSummaryCard` 与 `ordersV2/OrderDetailsViewModel`。不用所有event金额相加，不以authorization当cash，不将giftcard付款再当discount。
- 显示商品subtotal/discounts/tax/shipping及冻结total；支付摘要分授权、成功扣款、净可用款、已退、pending charge/refund、grantedRefund、remainingDue。giftCardCharged作为netCharged子项，以GIFT_CARD标识/last4和events呈现，不重复支付卡。历史legacyGiftCardDiscount单列“历史礼品卡抵扣（已计入总额）”，不加回order.total；totalCaptured只在旧服务兼容读取，不新写/生成Payment.partial。positive totalBalance显示credit，不显示负待付。
- I09 basic lookup嵌入订单/checkout/客服现有查询区，条件仅订单/checkout/transactionId/PSP/App标识；没有日期、事件过滤或特殊sort/report页面。paymentMethodDetails __typename discriminated rendering：giftcard/card/other；unknown method稳定通用只读卡，不发不支持动作。events=[]为无事件，不代表请求失败。
- 可操作按钮须MANAGE_ORDERS与HANDLE_PAYMENTS、相关channel/object权限，并且服务端actions含动作；上限来自availableCaptureAmount/availableRefundAmount，不用原始授权或charged累计。金额本地finite/正值/币种quantization预校验，等合法边界允许，提交前服务器再核对。mark-paid仅服务端action可用且无记录，不能在页面移除记录伪造资格。
- 每次用户意图产生idempotencyKey，固定于该pending操作，double-click/网络重试复用；修改amount/target/action才新意图。成功/明确failure后再开启下一意图；状态未知先刷新transaction/events/command结果，不换key重扣。mutation errors非空或结果null无成功toast/缓存写；external action已受理但pending只显示“处理中”，pending→真实event成功才显示完成。gift card内置动作可即时terminal，取消授权与订单refund分支不同。
- 操作success只invalidate相关order/transaction/giftcard或merge服务器confirmed实体；失败保留输入/旧余额，不optimistic扣钱。App关闭/换order旧响应不改变当前对象。敏感错误不打印token/code/全余额对象。
- 验证：旧Payment、Transaction、多笔/mapped去重、30gift+50normal/total100、auth100cap40、退款pending/grant、历史discount、emptyevents、并发amount超限/重试、仅一个permission、实际order动作变化。测试落点 `OrderPaymentSummaryCard`、`OrderDetailsViewModel`、`OrderSendRefund`/`OrderManualTransactionRefund` 与相应view tests。

### FD04 · 搜索语义、分页和异常
- 覆盖需求：R12、R13、R31。
- 设计说明：checkout/giftcard/product/order复用Core主体query语义；不在不同弹窗另造前缀或搜法。`useFilterHandlers` 的hasSortWithRank仅四主体启用，search清空恢复普通sort，分页重置；query长度≤256/词≤32本地提示，输入raw完整保留，发送规范化词，不能因为显示截断发送截断值。
- customers/staff维持basic文档按空格组合词，pages标题/slug/content基础搜索，没有RANK/高级prefix UI。不能因为主体RANK新增把generic field options散播到Page/User。subject关联字段保存success使必要查询失效；搜索最终一致窗口未给数值，显示刷新/已保存状态，不承诺20秒或即刻所有结果更新。
- Apollo query variables包括有效filter/search/sort/cursor/context，并有fetchPolicy/networkStatus标识；新的search清cursor与selection，旧请求回包仅进入其query cache不覆盖当前列表。loading与合法0count/forbidden/invalid/search服务error分开；可恢复error允许retry，不吞errors为[]。固定数据翻页结果用server游标，invalid/过期cursor提示从第一页恢复，不自动跳全部。
- 长输入用稳定minWidth:0/ellipsis且tooltip完整词、aria-label，clear按钮不重叠。键盘和composition事件不在中文输入未完成时过早trim；沿用现有debounce，不新许诺数值SLA。
- 验证：各list filters/sort tests、大小写重复词短语prefix、rank tie-break、空超长非法词、旧响应、Page/User无RANK；关联Page名称变化后Product重新可搜。

### FD05 · 锁定条件、导出、批量及层级选择器
- 覆盖需求：R14、R15、R27、R28。
- 设计说明：按 `ConditionalFilter` 架构 UI→URL/valueProvider→API→queryBuilder 保留域映射；拟新增 `EffectiveQueryContext`（contextId、lockedFilter/lockedWhere、editableFilter/where、search/channel/sort）。锁来自合法路由/弹窗参数，readonly chip显示，clear/reset只清editable不清context。不能用 `{...locked,...editable}` 合并；独立传I12两个AND范围，where/filter映射按域分别，不把order customer误映userEmail。
- 列表、giftcardfilter、导出、批量snapshot同一builder；URL同步/浏览器返回携带层级path/breadcrumb/filter/page/sort，解析不了的非法条件报错，不能静默扩大范围。权限不是URL锁，只由Core判定。
- I11为read-only query exports；按钮捕获当前context，传完整有效filter/where/search/channel/sort/ids和ExportInfo。分页循环上限100、可取消，切context则停并提示重新发起；逐页按I11 `interfaces/query-export-row-data.md`明确字段/缺省组成正确CSV/XLSX，商品variants需显式flatten、JSON十进制字符串不得转浮点累计；formulaescape、金额保留currency、不导受限column。ALL仍受当前filter/lock限，IDS为空禁导出而非all。下载只在所有页合法成功后产生，不partial错误文件假成功；导出期间数据变化提示基于查询时事实，不承诺跨请求永久snapshot。较大数据可继续明确使用deprecated legacy异步job，但其旧input不支持完整where/lock时必须先枚举当前有效交集，再用scope=IDS及非空ids提交，不能回退成ALL；voucher同样提交显式code ids且与voucherId相交。job权限、执行时资格重验和等待/失败/完成状态仍生效，不恢复隐式Query job。
- selected IDs按id set去重，取消值删除；filter/context变化清selection或重新取intersection。bulk显式ids与当前锁、普通filter/where/search/channel一并传I12，再受latest资格；“当前筛选全部”有界枚举当前有效结果后分批提交，每批重新核对，部分错误明确报告，不宣称跨批原子。其他旧bulk缺scope参数时只用重新确认的交集ids，不能将旧选择当全量范围。逐项错误逐项展示，不全toast成功。仓库/category分层selector规范实体map+selectedSet，父子tree/breadcrumb正确、不把分页重复node放两次；加载/empty/forbidden/network/返回保持导航上下文。
- 验证：已有 `filters.test.ts`、queryVarsBuilder与UrlToken multi-digit测试；同名locked/editable冲突、clear/return/filterlate、list全集=export集合、bulk=selected intersection；仓库反复select/unselect与分类上下级；非法url不放大scope、无权不能download。

### FD06 · 统一密码策略与OIDC前端
- 覆盖需求：R16、R17、R29、R28。
- 设计说明：`auth/queries.ts`、`auth/views/Login.tsx`、ResetPassword/NewPassword及hooks/useAuthProvider读取shop.passwordAuthenticationMode+availableExternalAuthentications。ENABLED允许原密码入口；CUSTOMERS_ONLY后台员工登录不显示密码/重置入口；DISABLED隐藏全部password入口（直接route仍读policy显示禁用）。没有external方式时稳定“未配置可用登录方式”空态+管理说明，不用本地密码回退。server错误仍显示PASSWORD_AUTHENTICATION_*而非一般无数据。
- `siteSettings/views`/`SiteSettingsPage`增加3模式selector，仅MANAGE_SETTINGS可保存expectedSettingsRevision。加载和pending期间不把默认ENABLED误当当前值；success更新policycache并触发auth策略读/失效，failure/conflict保留旧生效值与dirty输入。现有密码会话被新policy拒绝时清当前认证cache并退出到安全入口，不重试tokenCreate绕回。
- OIDC授权URL来自I14，前端不自行添加offline_access或存refreshtoken；Google access_type参数由Core。callback state/code不进长久URL/日志/通知，处理后清URL敏感部分；错误脱敏且明确可重试。首次关联按Core合法身份确认，不仅邮箱匹配提示成功；同issuer/sub后续稳定登录。
- token只遵守当前受支持安全会话机制，本轮不新增localStorage/sessionStorage保存provider令牌。App token与external tokens不混用。权限不可由隐藏按钮放宽。
- 验证：三mode×login/reset/set/change/直接route/旧refresh会话、无externalempty、设置late/conflict、Google与其他provider、badstate、log/persistence无敏感token。

### FD07 · EditorJS提交与安全错误
- 覆盖需求：R18、R26、R29。
- 设计说明：`RichTextEditor/consts.ts`、hooks、产品description与`translations/components/TranslationFields/useRichTextSubmit.ts`使用I15支持集序列化。支持paragraph/header1..3/list嵌套/quote以及历史image/embed读写，inline bold/italic/strike/link；不发未知tunes/meta。前端相同size/depth/link规则提示，不替代Core终校验。
- `description.blocks[n]...`错误聚焦block/字段，保持用户当前内容可改；一个坏block不把其余内容保存成“成功”。新窗口link显示安全rel，渲染历史内容同允许集，不能注入未校验HTML；不新增customscheme配置。网络error/permission与内容validation分开。
- extension合法SUCCESS响应只进dirty表单，经同序列化和Core保存，translation locale/source context一致；空blocks可清空，missing字段不等于清空。未支持历史block提示迁移/只读，不静默drop再保存。
- 验证：`RichTextEditor`、`useRichTextSubmit.test.ts`，L=8/L+1、已知字段、非法scheme/HTML attrs、noopener noreferrer、合法nested/links、保存失败dirty保持、source/locale切换。

### FD08 · 扩展安装规范与跨frame表单响应
- 覆盖需求：R19、R20、R29、R28。
- 设计说明：`extensions/domain/app-manifest.ts`、app-extension-manifest.ts与目标I16统一使用mountName/targetName/settings，只有受约束compat适配入口处理old mount/target/options，不让新form发旧名。installation页面必填appName/manifestUrl，manifest标识/permissions/target/settings预校验与Core一致，tokenTargetUrl缺省合法，不新显示secret/token。已有App升级通过I16 `appUpdate(id,input,manifestUrl)`显式提交待更新URL，省略URL时仅更新基础资料、不清扩展；新manifest的isActive/customHeaders保留并验证。仅成功回执替换对应App配置缓存，失败保留旧设置、输入和可渲染扩展，不以重新安装代替更新。
- `AppExtensionContextProvider`/Jotai popup state加入frameId/formContextId/revision/action去重（字段为拟新增），`AppFrame/useAppActions`与appActionsHandler遵循I17 `interfaces/extension-form-response.md`：origin+source+registered frame+handshake+activeapp校验，再dispatch对应商品/翻译formhandler。对sameorigin不同frame不能只看origin放行。关闭/导航/src变更注销旧frame。`AppFrame.tsx::handleLoad` 的旧直接token handshake改为只更新加载状态，只有通过source/origin鉴别的notifyReady才能发送token；formProtocolHello/Ready协商v1后才发允许的formContext，旧SDK仍保留非form动作但不能回填表单。
- 缺fields不清空；SUCCESS全部本地验证后原子应用且markdirty，不自动Core保存，不提示已保存；validation/permission/AppClosed显示正确状态且不应用fields。revision不符STALE_CONTEXT，重复action replay ACK，冲突拒绝，unknown action可处理失败而非throw拆全局监听。appToken只在通过鉴别的握手内存传递，非必要issueToken=false，禁止消息debug日志打印token和完整form。
- 验证：已有`AppExtensionContextProvider.test.tsx`/`appActionsHandler.test.ts`、manifest zod tests；两个frame/旧product/locale/late response/repeat/error/unloaded/Appclosed/permissions/default；安装缺name/URL、optionaltoken、oldsettings全保留。

### FD09 · 自托管扩展目录
- 覆盖需求：R21、R19、R28。
- 设计说明：`useAppStoreExtensions`优先EXTENSIONS_CATALOG_URL，否则同源`extensions/catalog.json`；旧APPS_MARKETPLACE_API_URL仅明确配置兼容（不使用旧模板URL默认回退），详情见I18完整OpenAPI。该静态文件由部署方提供，当前不宣称已上线，frontend构建不联网旧marketplace。
- fetch使用AbortController+source sequence，运行时schema校验；loading/loadedempty/404未配置/503服务error/shapeinvalid各态独立。category按id payments/taxes/cms/automation归组，不用英文name强制类型；未知类别拒绝或明确schemaerror，duplicateentry按(type,id,manifestUrl)归一不隐藏冲突。保留当前有效data作陈旧态但不能当新成功。
- 目录请求不发送Saleor bearer；HTTPS跨域需CORS且部署allowlist，默认同源满足自托管无第三方。浏览/搜索保留；无MANAGE_APPS/相关plugin权限只读，install/configure按钮依Core权限，manifestUrl null不提供install，installed事实来自Core不是catalog自报。App安装Job成功才installed，目录loadsuccess不代表安装成功。
- 验证：`useAppStoreExtensions.test.ts`、`useExtension.test.tsx`、Explore目录；同源离线于旧服务、合法空、404/503/invalid、late源切换、只读、logo基本失败态（不引入async fallback）。

### FD10 · delivery状态与单条重试
- 覆盖需求：R22、R23、R28、R31。
- 设计说明：`AppWebhooksDisplay/EventDeliveriesStatus/EventDeliveryItem/EventDeliveriesList`与`AppAlerts/useAppsFailedDeliveries`使用I19/I20目标状态。PENDING+payloadGeneratedAt=null显示“等待生成内容”，RETRYING显示处理中及nextRetryAt，SUCCESS是真实已投递，FAILED显示latestError/attempt信息。缺payload不能当成功，错误脱敏，不显示signature/敏感body给无权者。
- 单条retry按server相关App/域权限启用；pending状态防doubleclick，回执仅排队成功，不能toast投递成功。成功invalidate该delivery而不整个App其他成功delivery重试；相同queued请求不重复。查询error与合法无deliveries区别，未知status稳定error而非绿色成功。
- 保留现有失败告警，不创建AppProblems type/query/UI。订阅选择只请求展示必需字段，不为了状态展示拉取完整payload/secret；后端worker/字段解析是Core责任。
- 验证：一个recipientfail一个success、payload未生成、retryqueued/fail/success、两次click、权限、events no-op不新增通知、AppAlerts回归。

### FD11 · 创建时配送metadata与基础编辑
- 覆盖需求：R24、R25、R28、R31。
- 设计说明：订单详情/履约现有inline展示I21 shippingMethodMetadata/private/snapshotStatus，不以deliveryMethod.metadata live lookup显示历史，不混shippingTaxClassMetadata。UNAVAILABLE明示历史快照不可恢复，数组[]本身稳定空值不是queryerror；private字段仅有合法权限才请求/render，不靠DOM隐藏。
- 既有通用metadata与orderline行内编辑继续I22；client检查key空/重复/非法value，mutationerrors保持旧生效值和当前输入，不分块保存假成功。成功invalidate相应entity；snapshot是readonly历史事实，不允许普通编辑改它。所有业务字段scope受Core约束。
- 不新增order/fulfillment/warehouse独立metadata弹窗、菜单、route，包括hiddenroute。取消独立入口不删除基础form组件和元数据mutation。
- 验证：source改/删历史仍同值、checkout/draft来源、fulfillment相同snapshot、private权限、legacyempty、keys非法整体不更新、普通inline和orderline仍保存。

### FD12 · 加载、编辑、保存快照及真实显示/草稿资格
- 覆盖需求：R29、R30。
- 设计说明：共同表单状态保持contextKey(objectId,channelId,locale)、requestSequence、editRevision、dirtyFieldSet、serverSnapshot、submittedSnapshot。初始loaded首次填未脏字段，刷新只fill同context未脏字段，旧context response丢弃；不以任意useEffect reset整个form。save response更新已保存snapshot（服务器canonical值），若user继续edit，仅清与submitted相同且未再改的dirty字段，不覆盖新的输入。
- channel/shop/product加载期间禁save并skeleton；loadedempty有独立说明，403与networkretry分开；failure不optimistic cache写入。Apollo keyFields ID+querycontext；scope/channel派生查询含variables，不能复用上个channel eligibility。mutation response虽晚也仅更新对应保存entitycache，不污染当前form；避免用“data到达”作为保存成功。
- `components/Weight/Weight.tsx`与商品/配送weight输入共享换算工具：G/KG/OZ/LB/TONNE，先转标准g（1kg=1000g、1oz=28.349523125g、1lb=453.59237g、1tonne=1000000g），再转显示单位；使用Decimal-safe arithmetic和domainprecision，display rounding不用于覆盖model，不能数值不变仅换unit。金额用currencyprecision/ReactIntl而不按百分比与fixed discount混算。media普通状态与API一致，保留同步图片/上传/video，不增加pending/503/proxy/fallback。
- OrderHistory/Timeline在共享date工具使用UTC instant+明确display timezone生成YYYY-MM-DD日期key，然后用相同timezone/locale格式化；不得按toLocaleString不同format字串或UTC截日归组，DST/月年边界测试。无明确用户timezone按当前会话浏览器zone显示并在页面一致，不修改eventdate。
- `OrderDetails/OrderDraftDetails`读取I26 canAddProducts/canFinalize/problems；分别映ADD_PRODUCTS与COMPLETE reason。inactive/无可售商品禁相应action，缺billing/shipping完成条件不误禁合法编辑或加商品。切channelclear旧资格，latestQuerypending期间禁依赖动作；提交再以Coreerror解释。不本地生成虚构normal资格。
- 验证：异步初始/刷新/save延迟下dirty保留，A→B旧response，conflict/failure和retry；weightunit往返、moneycurrency、DST跨日locale/timezone、media状态、draft各前提/切channel恢复与server拒绝。

### FD13 · 统一错误、生成客户端、权限与非目标守门
- 覆盖需求：R26、R27、R28、R31。
- 设计说明：`src/graphql/`、`src/fragments/`、各feature queries/mutations建立一次目标schema消费迁移。首选current字段；显式保留的deprecated read仅compat adapter内使用。源operations删除Payment.partial/旧DigitalContent/旧Shopdigitalsettings，新draft用voucherCode；attribute creation包含非空name/slug/type，update不发送未改null；Appinstall必填。旧导出mutation只在明确legacy大数据job分支，仍检查errors。
- 通用成功判定：transport/GraphQLerrors无误 + mutationpayload存在 + errors=[] + 所需结果；accepted/pending与completed分开。schema/parse/coercion错用extensions.code/path，业务错用field/code/message；unknownexception不兜底[]/success。页面权限、field选择、actions gate与Corescope一致；actualstaffdelete成功后移除entity/回列表，历史order保留，不把is_staff=false当已删除。
- `npm run generate`从本次完整目标（或实施Core打印等价SDL）生成hooks/types/typePolicies/fragmentTypes，禁止抓远端未来schema；生成后check-types/operationvalidation发现旧引用逐源修复，不人工cast掉类型错误。条件filterdomain映射/错误enum与Core同版发布。
- 排除守门：没有AppProblems、Page/UserRANK/advancedvectorprefix、交易date/eventsort、独立variantgenerator、asyncimage专用状态、独立metadata入口；普通variant单/批量、hasVariants、media基础、metadatainline、Webhookfailedalerts都要回归。不能利用新generic组件隐藏route绕回非目标。
- 验证：所有operationsagainstSDL、生成文件无退出项、errorenumexhaustive、无权节点/列表/export/subscription；Playwright关键主链。源码审计菜单/routes/tasks以及必需ordinary功能，不能仅看UI截图。

## 4. 依赖与联调

| 接口 | 消费方设计单元 | 对应需求 | 开发依赖 |
| --- | --- | --- | --- |
| I03、I05 | FD01 | R03、R06、R29 | mock可独立；Core BT02 后真实配置/冲突 |
| I06 | FD01、FD03 | R05、R06 | 等BT05实际状态，不mock后台完成成功 |
| I04 | FD02 | R04、R29 | mock独立；BT03诊断count/filter |
| I07、I08、I09 | FD03 | R07—R11 | 等BT04账本/amount/status；rootlookupfieldmock |
| I10 | FD04 | R12、R13 | mock输入状态；BT06subjectquery/index，Q01时延门槛 |
| I11、I12 | FD05 | R14、R15、R27、R28 | scopebuilder可独立；BT06集合同验 |
| I13、I14 | FD06 | R16、R17 | BT07即时policy/identity；mode/错误mock |
| I15 | FD07、FD08 | R18、R20 | 内容协议本地可独立；BT07所有保存入口 |
| I16、I17 | FD08 | R19、R20 | static schema/frame本地可独立；BT08安装与token |
| I18 | FD09 | R21 | 同源静态fixture可独立；部署须真实提供目录/CORS |
| I19、I20 | FD10 | R22、R23 | 状态mock可独立；BT05/BT09worker与retry |
| I21、I22 | FD11 | R24、R25 | BT09snapshot/migration/permission |
| I23、I24、I25 | FD13、全部 | R26—R29、R31 | 目标SDL先codegen；BT01/10全矩阵 |
| I26 | FD12 | R30 | actionmock可独立；BT03最新资格 |

Storefront消费者 I01/I02 和 giftcard初始动作由外部接口合同与Core集成测试联调，非Dashboard页面任务。不等待问业务再开设计；mock必须与目标SDL和上述附加协议相同。每个接口至少提供valid/empty/forbidden/invalid/conflict/pending/error fixture，不能只happy path；errorfield映射和权限分支一起验。

联调顺序：先目标SDL生成与commonerror/context工具→配置/诊断/搜索/目录可独立页→资金/identity/extension→snapshot/delivery/draft→跨入口集合作用范围与历史compat。先Core新增与迁移安全默认，后Dashboard切current消费，再停用退出操作；若同时破坏schema需停窗口/消费者审计，不能假设所有旧Storefront立即支持。

## 5. 其他

### 验证计划与实际执行区分

本阶段只读仓库并保存设计。已执行 SDL 语法/类型/基线保留、26份代表性新消费、18份预期拒绝负例及现行源 operation 审计，具体结果在接口契约§3。静态抽取122个生产源码文件（排除generated/tests/fixtures），402个operation以241个fragment递归依赖闭包校验：Base 401通过，目标402通过，ExtensionList新字段漂移已由目标SDL补齐。此结果不等于旧调用已满足运行合同：资金源operation仍须新增稳定idempotencyKey，App升级须显式URL、客户端需重新codegen，generated类型中的旧DigitalContent/Shopdigitalsetting必须清除。未把新schema注入运行Dashboard，未执行codegen、npm lint（会autofix材料）、Jest、check-types、knip、Playwright或部署目录；前述各单元测试名称均为研发计划。

前端测试按仓库要求使用Jest/RTL与`npm run test:quiet <file>`，补Arrange/Act/Assert；端到端Playwright覆盖资金doubleclick/失败刷新、锁定export集合、mode立即生效、跨frame、lateedit、draft与timezone。生成后跑check-types/knip，lint只能在实施授权可写源代码阶段运行，不在本设计阶段触发。

Q01最终搜索窗口仍未有数字，发布前确定，UI不提供虚构实时成功。Q02/03已按技术设计分钟/默认0/上限及EditorJS有限支持集落地，Q04SDL已固化，Q05目录同源来源已选但未部署；Q06真实provider能力测试决定后台capture开放，资金显示使用明确pending/grant适配不凭gatewayname猜。

不扩展独立功能。风险主要是两套order view需共adapter以免一页正确另一页重复计款；老manifest/SDK能力协商；policy旧会话被拒需要清楚空态；大数据read-only导出浏览器内存（分页可取消/大数据legacy明确降级）、动态数据改变cursor需重启；历史无法证明metadata/source映射只读解释而非伪造。任何冻结基线差异只说明，不修改PRD/测试。
