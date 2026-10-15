# 前端技术设计：Saleor 3.23 结账、资金与商户运营一致性

版本：v1  
责任：前端技术设计（Tech Owner）  
依据：PRD v1，`artifacts/sprint1/prd/prd.md`；两份业务输入；后端设计v1及统一接口契约v1  
修订：首次交付；仅设计，不开发、不修改冻结PRD或仓库生成文件。

## 1. 方案概述

延续 Dashboard React17/TypeScript、Apollo Client、React Router v5、React Intl、Macaw组件与现有功能模块，不引入独立Storefront、支付报表或新架构。GraphQL操作统一从 `interface-contract.md` 引用编号，以交付 `target-schema.graphql` 在实施时本地codegen；不抓取未知目标版本schema。界面围绕“已保存事实 / 当前编辑 / 请求世代 / 异步业务事实”四层分离，不能用HTTP200、配置已保存、任务入队或有事件数组代替实际业务成功。

代码基线 Dashboard `aebb2401b5079fbbb8c60150289d1896c108feca`。主要改造现有渠道、商品、订单、列表、身份及extensions模块，共用hooks只在必要范围增强。路径均相对 `/workspace/repos/saleor-dashboard/`：
- `src/hooks/useForm/index.ts:77-106` 的 merge 比较server props但不检查dirty；需要上下文+dirty保护，不能到处加useEffect重置。
- `src/products/views/ProductList/export.ts`、`src/giftCards/GiftCardExportDialogContent/utils.ts` 导出范围构造未完整消费当前列表筛选；改用同一个effective-filter snapshot。
- `src/orders/components/OrderPaymentSummaryCard/`、`OrderSummaryCard/`、`OrderTransaction*/` 等既有金额/动作展示继续使用，金额改为服务端summary/available额度，不凭客户端重算。
- `src/channels/`、`src/siteSettings/`、`src/auth/`、`src/extensions/` 承载配置、登录和App当前合同；选择器、分配、ConditionalFilter不新增与业务无关的专用入口。

状态约定：查询用loading/ready(empty或data)/permissionError/networkError；表单保存用idle/submitting/saved/validationError/conflict/transportError；资金和后台状态pending/failed/succeeded来自Core而非本地setTimeout。国际化文案沿用React Intl，对金额、单位、日期使用现有国际化基础。

## 2. 需求覆盖

| 需求 | 设计单元 |
| --- | --- |
| R03（配置）、R06、R29 | FD01 |
| R04、R29 | FD02 |
| R08、R09、R10、R11 | FD03 |
| R12、R13、R14 | FD04 |
| R15 | FD05 |
| R16、R17 | FD06 |
| R19、R20、R21 | FD07 |
| R22（仅异步状态）、R23 | FD08 |
| R18、R24、R25 | FD09 |
| R26、R27、R28、R30、R31 | FD10；所有单元遵守 |

不适用边界：R01/R02/R07面向Storefront/API消费者，Dashboard不新增客户checkout页面；R05自动执行、R03库存预留/分配、R17OIDC服务端首次关联、R22载荷构建、R24快照存储与迁移由后端承接。前端承接现有相应配置/订单读取和错误展示，不能模拟自动成单或卡余额。R11基础交易查询用于订单详情关联定位和现有支付入口，不新增日期/事件报表与独立排序页面。

## 3. 详细设计

### FD01 · 渠道/商店配置的生效值、编辑与CAS
- 覆盖需求：R03、R06、R16（配置基础）、R29。
- 修改 `src/channels/queries.ts`、`mutations.ts`、频道详情表单及 `src/siteSettings/queries.ts`、`mutations.ts`，fragments读取settingsVersion。sourceStrategy与allocationStrategy分别显示“库存来源”和“分配优先顺序”，不得用优先顺序假装已经切换新库存策略。旧策略显示SHIPPING_ZONE，直关联渠道策略在确认中解释地址不再改变库存集合，不自动切换旧店。
- 自动完成区有开关、分钟delay、带timezone的cutoff输入，说明“最近变化严格超过延迟”“创建时间含等于下界”；cutoff为空表示无限下界，不是任务结束。资金释放TTL/cutoff留在原支付设置区，字段状态和提交模型不共用；设置成功提示“配置已保存”，不提示“订单已生成”。可选显示有管理权限的实际自动完成状态，不模拟任务。
- 通用表单 state为`contextKey(objectId+formId)、requestGeneration、loadedBaseline、baselineVersion、draft、dirtyFields、submissionId`。加载未完成不初始化为false/0替代真实值；骨架、权限/网络错误、loaded空对象分别显示。请求取消（能取消则Abort）加generation guard，切对象先隔离旧request，旧查询/保存响应不得写入新表单。
- server新数据仅更新当前context且未dirty字段；dirty字段即使新props不同仍保留draft，冲突提示可重读/对比，不能静默merge。沿用legacy useForm必要适配，新增表单优先RHF `reset(...,{keepDirtyValues:true})`并额外context guard，不全仓库强制重构。嵌套字段dirty按路径记录。
- 保存只传合法changed值及当前baselineVersion；修改checkoutSettings/stockSettings/仓库关系或顺序/passwordMode必须expectedVersion。一次提交捕获快照+submissionId，后续编辑不被本次成功清掉。成功仅以payload无errors且返回有效对象/version更新Apollo已保存事实；将仍未改动的提交字段标clean，提交后改过的字段保留dirty。失败保留baseline/成功缓存和draft；CONFLICT刷新baseline提示重新确认，不自动拿新version重发旧draft覆盖他人。
- 基础权限不足只读；无法确定权限/加载阶段按钮禁用，Core仍校验。验证延迟加载/dirty/切对象/连续保存反序返回、失败缓存不污染、CAS冲突，恰好10分钟解释、cutoff日期含时区、TTL隔离。

### FD02 · 商品按渠道诊断真实可售原因
- 覆盖需求：R04、R29。
- 在 `src/products/views/ProductUpdate/` 与 `components/ProductUpdatePage/` 的现有渠道编辑上下文增加只读诊断区，使用I04，不创建独立诊断路由。可按channel名称/币种筛选、有界分页；channel id作row key，count来自本次issues而非客户端遍历过时库存猜测。
- 用Product.channelAvailability提供blocking/warning/not-applicable。上游发布/可买时间阻断突出，正常依赖不画成错误；数字商品只配送检查“不适用”，库存/价格/发布时间仍显示。数量仅BLOCKING+WARNING，明细标签/可操作建议与后端码对应，无权限渠道不出现行/count。
- 诊断context=`productId+filter+cursor+savedRevision`，dirty商品编辑时明确“基于已保存商品”，不暗示未保存draft已诊断；成功保存后刷新，保存失败不以draft当新事实。刷新可保留旧数据显示但标“旧结果/刷新中”并禁用依据它的判断；错误有重试，不伪装0问题；旧请求迟到丢弃而不覆盖product表单。
- 无MANAGE_PRODUCTS/合法channel读权限不请求诊断；协议范围先于count。mock覆盖未发布/未来日期、部分变体缺货warning、无仓库/无区域、数字not-applicable、币种筛选及翻页/错误/切商品。

### FD03 · 订单资金摘要、礼品卡、基础交易和安全动作
- 覆盖需求：R08、R09、R10、R11。
- 扩展 `src/orders/queries.ts`、`src/fragments/orders.ts`、transactions fragments，现有OrderSummaryCard、OrderPaymentSummaryCard/PaymentsSummary、OrderTransactionTile/OrderTransactionPayment/OrderTransactionGiftCard消费I09。商品/配送TaxedMoney的gross/net按现有税展示；tax和discount为解释项，不再加/减一次。Money用API精度和Intl，不固定两位、不JS浮点复算服务端余额。
- 直接显示summary.outstanding（非负）及balance/超付解释；authorized/charged是当前净额，refunded单列历史，不对charged再减；pending独立label。giftCardAmountBasis区分历史“总额已含礼品卡抵扣”与当前“礼品卡支付”；giftCardCharged是已收组成项而非再次优惠。混Payment/Transaction只按paymentFlow选主计算、分别展历史来源，不把两套净额相加。100/卡20/普通30剩50、charged80/refund20仍80、Payment退款回归作为固定mock。
- 交易列表/详情可用I11按当前orderIds、transactionID/PSP/App基础定位，订单关联锁定不可清；events=[]是正常空态。GiftCardPaymentMethodDetails以typename分支显示遮罩卡尾号、金额、成功/待确认/失败事件，绝不用完整code或当前card balance倒推历史。受限字段没有permission不请求（可拆安全fragment），顶层error和无事件分开。
- 动作沿用OrderMarkAsPaidDialog、OrderPaymentDialog、OrderRefundDialog、OrderTransactionActionDialog等。按钮由Core.order.actions/transaction.actions、availableChargeAmount/availableRefundAmount、当前对象/权限决定；不能仅能看订单就显示全部payment动作。有记录不得mark paid；打开/提交前可refresh最新额度但最终由Core锁检查。
- amount用decimal字符串组件，负值/显式0本地拒绝，超过available解释但不裁剪。orderCapture/orderRefund必填，transactionRequestAction仅用户明确“全部当前额度”时省amount。每次确认生成operation UUID，存于当前dialog/request state，双击/网络重试同key，用户修正金额产生新key；取消/换对象不把pending旧请求当新对象结果。mutation transport/payload验证失败保留真实状态，明确provider失败/未知pending则显示请求追踪，不模拟成功；只有成功事件/刷新事实确认后toast业务完成。
- 同时读取处理方式和余额改变不可用时更新禁用原因；App/员工权限从认证profile+动作权限，Core最终scope。模拟response反序、额度被其他请求消耗、退款pending占用、多笔支付、无事件、零币种/三位币种及unauthorized field。

### FD04 · 主体搜索、锁定筛选和导出/批量同范围
- 覆盖需求：R12、R13、R14。
- 修改既有 `src/components/ConditionalFilter/`、列表filter变量构造、`src/components/ConditionalFilter/FiltersQueryBuilder/`及其`queryVarsBuilders/`、products/orders/giftCards/customer/staff/pages搜索和分配入口，不在客户端实现另一套匹配。四主体遵守I12关键词/末词prefix/引号短语/组合/相关度，Page/User只基础搜索，不生成高级RANK/vector操作。最长256字符技术边界统一输入校验，空词回有界默认列表，错误/无匹配/加载分别显示。
- 有效筛选采用`lockedContext`（来自当前授权页面/分配上下文）+`userFilter`+`search`+`sort`，AND合并；锁定维度从可信page context重建而非允许普通URL改写覆盖。普通清除只清userFilter/search，锁定chip只读。where的AND组合保留原锁定仓库/渠道，不能last-spread-wins；没有表达AND的scalar锁定值必须保留并将冲突显示为空范围/解释，不允许替换。
- 每次filter变化生成`scopeFingerprint`并重置游标/选择集（或用户明确重新确认保留的范围内选择）；列表请求generation按该fingerprint，旧请求可缓存但不可成为当前可操作结果。列表失败、显示旧范围、加载新范围时禁用导出/批量，避免把旧数据当当前事实。
- 改 `src/products/views/ProductList/export.ts`、`src/giftCards/GiftCardExportDialogContent/utils.ts` 及voucher导出hook，用**提交当刻**effective snapshot构造I13，不读过时闭包；Query导出仅用户按钮请求Apollo no-cache，不用常规页面watchQuery自动重取。FILTER携带当前where/filter/search/channel/sort，全集是所有匹配而非当前页；选中行IDS携带同scope+当前选中IDs，ALL仅真无任何范围限制。ExportFile.id表示job受理，Job.status SUCCESS且url可用才展示下载完成；失败有状态，重试同key/同input。
- 批量确认明确“本次n个选中”或“全部筛选结果”，禁止范围外旧IDs；直接API仍受Core检查。锁定URL不是权限来源，对象scope以后端为准。cursor按最新search/sort/filter恢复，数据变动不能承诺无限稳定翻页。
- 测试条件清除/冲突、礼品卡改filter立即导出、列表/导出集合一致、筛选失败和迟到响应、selection变更、same-key重试、客户/staff隐私scope和search服务error。不新增交易日期/事件筛选或Page/User高级索引。

### FD05 · 选择器、分类层级和返回上下文
- 覆盖需求：R15。
- 仓库与category/assignment选择器继续使用现有queries和components，以对象ID set规范化候选+选中；反复选/取消不append重复，取消从提交集合移除，保留允许的未加载已选对象但以ID一次显示。
- 分类navigation state含parentId、breadcrumb、filter、cursor、lockedContext；钻入子级更新父子路径，不用label作id，查询去重不把祖先混入子候选。返回详情/弹窗前保留list route state/URL有效过滤及可恢复cursor，当前数据变动使cursor非法时提示后有界重置，不能悄悄清锁定范围。
- 加载/空/permission/network都有独立render，不因错误清breadcrumb/已选；权限变化后提交受限值提示并停留当前上下文。search框固定flex容器/宽度，长词ellipsis且tooltip或可滚动输入查看完整值，真实提交仍全词，清除及键盘focus正常。
- 对仓库反复取消、父子切换/搜索、详情返回、错误恢复、长关键词视图及实际值写RTL/Playwright用例；不新建导航服务或独立元数据selector。

### FD06 · 密码三态、登录入口与OIDC
- 覆盖需求：R16、R17、R29。
- `src/auth/`登录query同时取公开Shop.passwordAuthenticationMode及现有external authentication providers；模式未知/loading不闪出员工密码表单。ENABLED按原账户条件展示；CUSTOMERS_ONLY与DISABLED后台隐藏员工password/login/reset入口；外部方式仍可用，无provider显示稳定“没有可用后台登录方式”及支持说明，不构造虚假成功fallback。
- `src/siteSettings/`设置区只有MANAGE_SETTINGS可改，mode+CAs沿FD01；显示effective值，未保存draft不写auth policy缓存。成功后重读相关shop/login策略缓存；失败保留生效模式，冲突提示。登录mutation收到PASSWORD_AUTHENTICATION_DISABLED/PASSWORD_AUTHENTICATION_CUSTOMERS_ONLY/EXTERNAL_AUTHENTICATION_REQUIRED明确映射，不在toast泄露账号存在性。
- OIDC请求参数交Core plugin产生，前端不自行加offline_access或将所有provider当Google；回调/refresh/error只用现有必要auth管理，token不进入console/query string错误/扩展消息/不必要localStorage。对首关联行为提供可理解失败，不前端set password绕过。
- 测试三态×provider有无、加载/error、Core拒旧token/policy的UI退出与提示、密码reset入口、mode保存立即生效、外部token不得误禁。服务端policy及首次关联由BD10权威。

### FD07 · App当前字段、表单回应与自托管目录
- 覆盖需求：R19、R20、R21、R27、R29。
- `src/extensions/queries.ts`、fragments/extensions、App安装/详情组件统一使用mountName/targetName/settings，替代mount/target/options提交，不手改generated文件。settings按target-specificschema校验；历史读取投影可渲染已知method，无法恢复部分不编造。安装appName/manifestUrl不能为空，tokenTargetUrl可选，预览/目录载入不代表安装成功；AppInstallation结果才更新installed state。
- 在现有 `src/extensions` App iframe/action处理hook实施I19：打开popup生成frameId/requestId/contextVersion，注册允许origin与`contentWindow`，加载握手后才接收；同时验event.origin、event.source、message结构、frameId、requestId、action和当前上下文。未知action明确reject/ignore不throw导致整个page崩溃；每request最多一次apply，重复重放只回ack，跨frame不应用。
- form result遵循I19的PRODUCT/TRANSLATION固定字段并按打开时allowedFields/nullableFields进一步收窄。omitted字段保持，null只在该字段本次nullable时清除；VALIDATION_ERROR的安全previewValues仅展示和定位，不自动合并draft，不显示保存完成；permission error/App关闭不改已保存事实。响应到达前用户又编辑：contextVersion不匹配丢弃或提示重新打开，不用App结果覆盖新dirty输入。合法response只是draft更新，仍经当前form校验和Core mutation手工保存。
- 扩展目录沿用 `useAppStoreExtensions` 的可配置读取模式：部署提供同源/HTTPS静态目录，契约I20及JSONschema；不依赖不可用legacy marketplace作唯一地址。默认可用本地空目录[]（明确未配置，不伪装网络失败），配置URL可用则加载；Fetch有AbortController、generation/schema验证、成功清旧error，网络/invalid schema为error不是空目录。
- 自托管允许有MANAGE_APPS用户按Core正常安装，移除AppInstallButton额外Cloud-only禁用门槛；只读用户可浏览筛选但不安装配置。目录数据缺省权限/setting值按schema处理，不发自建REST安装请求；只有实际I18成功确认改变installed列表。
- 测试mount/target/settings生成兼容、token URL缺省、安装job pending/failed、多frame/错误origin-source/重复/未加载/未知action、app close/迟到编辑、目录空/坏JSON/网络/恢复/自托管安装权限。协议文件是JSON验证而非新网络服务。

### FD08 · Webhook真实delivery状态与单条重试
- 覆盖需求：R22（状态）、R23。
- 扩展现有extensions App详情/Webhook事件查看与attempt列表，读取I21 payloadState/lastError及PROCESSING/RETRYING。WAITING payload显示“等待构建”，READY+PENDING显示“待投递”，PROCESSING执行中，RETRYING重试中，FAILED显示脱敏原因，确认SUCCESS才成功；无payload不显示已发送。
- 有MANAGE_APPS且相关App/对象范围获准才提供目标单条retry；点击锁定该delivery的loading，不把其他success行退回pending。retry payload无errors表示排队，后续刷新目标delivery/attempts看真实结果，不toast“通知已成功”。目标已成功/重复点击按契约拒绝或回同状态，旧列表响应不能覆盖新attempt。
- 保留现有失败告警/查看能力，不新增App Problems类型、问题页、创建/关闭动作。payload敏感字段按权限，错误不打印token。测试A失败B/C成功、payload构建失败重建、无权限、retry pending、保留导航筛选。

### FD09 · 富文本、历史配送快照和原子基础metadata
- 覆盖需求：R18、R24、R25。
- 富文本编辑器保留正常block/嵌套列表，结构按补充EditorJS schema，停止旧`convertEditorJSListBlocks`只取顶层content而丢失子项的转换；前端按I17提供结构/URL/depth提示（支持depth10、scheme固定），最终以Core码为权威；全表单mixed非法不提示成功，字段/blocks索引message定位改正。渲染外链target=_blank使用noopener noreferrer，不允许编辑UI配置扩展协议。
- Order详情与fulfillment必要业务显示I22 public snapshot，private只获准查询；标为“创建时配送资料”，不读取当前shippingMethod.metadata代替。空快照正常空数据，tax class与order自身metadata不混。历史snapshot没有编辑按钮。
- 现有订单详情行内metadata及订单行/variant编辑交互继续保留，不能按Dialog名称一刀删掉。一次metadata业务保存统一I23 metadataBundle.version→metadataUpdate，提交public/private upserts及删除同一次；全部成功后更新bundle缓存，否则baseline原值+draft仍可修正；不并行多次update/delete然后partial成功假装整体成功。
- 基础对象权限/public-private分别判断，snapshot不可通过metadataUpdate键名覆盖。无独立Order/Fulfillment/Warehouse metadata菜单/route/dialog/隐藏入口。本轮只保留现有必要行内/业务编辑，不新增独立管理产品。
- 测试editor结构/合法scheme/混淆/9-10-11深度、安全rel、inline metadata同请求失败无部分更新、CAS冲突、source shipping变化历史仍不变、无private权不请求/展示。

### FD10 · 当前客户端、校验权限与准确日常操作
- 覆盖需求：R26、R27、R28、R30、R31。
- operation成功判定统一adapter：先network/GraphQL errors，再payload errors，再资金/异步event/status；业务返回无匹配/空events可成功，不用`data != null`统一toast。field/code映射新增枚举，unknown code显示保守失败+可重试，不默认为成功；顶层INPUT/PERMISSION_DENIED不映成空列表。
- 移除生成操作中Payment.partial、旧DigitalContent API和旧数字下载设置；数字商品/Apps、普通variant单个/批量、hasVariants、required属性、同步外链图片/上传/oEmbed继续。draft mutation用voucherCode，不发送旧voucher；attribute创建省slug可自动生成，部分更新只发变化字段，不发undefined→null；name/slug显式空值错误、App必填执行前拦截。
- staff删除按真实删除响应+重新读列表，不以is_staff=false当删除完成；自删/权限范围禁用且Core验证。新export permissions与domain范围用于入口/按钮，不能仅MANAGE_PRODUCTS或MANAGE_GIFT_CARD推断全部导出权；既有迁移等价授予由Core执行。
- weight保存前将API返回值的来源unit转换到Shop.defaultWeightUnit，十进制处理且只quantize一次；原parseFloat不等于单位转换，1kg/1000g一致，不能读取后用另一单位裸值提交。折扣与tax/媒体只使用API实际状态；不新增async media pending/503/proxy/fallback。
- OrderHistory用统一locale/timezone函数同时format label与group key（日历日期，不UTC字符串截断），跨日/月/DST测试；金额formatter按币种minor precision。
- `src/orders/components/OrderDraftPage/`及添加产品/完成handler以最新channel active、可售商品/价格/配置、配送/库存状态gating，禁用理由明确；未加载先禁用，满足条件恢复，切渠道不使用旧可售结果，Core直接请求仍校验。不因前端known-invalid发送mutate再toast失败。
- 排除清单同时审查schema consumer、生成文件、路由菜单、任务/flag：不加入AppProblems、Page/User RANK/高级搜索、transaction日期/事件filter/sortBy、generator独立入口、独立metadata、async抓图fallback。

- Base Dashboard `src/extensions/queries.ts:109-138` 已读取mountName/targetName/settings，而Base Core仍旧字段，是实际基线接缝；不能笼统称所有frontend全用旧字段。现有extension domain manifest validator及filters仍需与新合同对齐，unknown mount/target不得直接parse throw崩page。
- `src/hooks/makeQuery.ts:97-105` 默认cache-and-network且errorPolicy=all，Apollo也可能自动写迟到数据；配置编辑和保存改用no-cache获取候选snapshot并仅在版本/generation校验后cache.writeFragment，或version-aware typePolicy拒旧version，不能只保护组件state。`src/misc.ts:257-297` missing data返回空errors的成功误判一起修；richText `getValue`不得在editor.save前清dirty，仅已提交snapshot业务成功后清。
- channel原页面update后独立reorder会部分成功，新保存用I03 warehouseOrder一次CAS；如仅旧独立reorder场景明确独立动作结果，不伪称整体设置保存。新增AppInput.extensions/expectedVersion使用App.settingsVersion，安装/升级扩展完整替换和保留已有id；从生成client到新manifest validators均一致。
- 订单行/variant联合metadata编辑用I23 metadataBulkUpdate一次事务，不能用现有多请求handler做伪原子补偿；将订单confirm与metadata保存分成用户可辨识动作，不在metadata保存前暗中confirm。
- 目录响应沿用APIExtensionsResponse分组数组、id作稳定category key，不以name.en转换推导id；installed Apps需完整分页/明确未知状态，未获MANAGE_APPS或查询失败不能一律当未安装。目录success清旧error，移除整个Explore页面error throw，提供局部retry。
- 消息旧actionId/响应status和具体targetOrigin保留，新form action添加frame/source/runtime schema/去重context，不声称旧代码完全无关联ID。新协议拒非法字段的整条form patch；合法只更新draft。

## 4. 依赖与联调

| 接口 | 消费方设计单元 | 对应需求 | 开发依赖 |
| --- | --- | --- | --- |
| I01、I02 | 无新增Dashboard消费 | R01、R02 | Storefront外部联调；后端完成后验证兼容 |
| I03、I06 | FD01、FD10 | R03、R06、R29、R30 | mock可并行；真实CAS/库存需BT01/BT02/BT04 |
| I04 | FD02 | R04 | UI可mock；诊断Core需BT02 |
| I05 | FD01（必要状态读取） | R05、R06 | 真实任务结果需BT04；不得模拟订单 |
| I07、I08 | FD03（方式/事件展示） | R07、R08 | 真实礼品卡需BT03，不造Storefront支付页 |
| I09、I10、I11 | FD03 | R08—R11 | mock字段/错误先行；真实净额/幂等需BT03 |
| I12、I13、I14 | FD04、FD05 | R12—R15 | filter snapshot可独立；搜索/导出权限需BT05 |
| I15、I16 | FD01、FD06 | R16、R17、R29 | 模式加载mock先行，生效/外部provider需BT06 |
| I17 | FD09 | R18 | depth/scheme mock；权威校验需BT06 |
| I18、I19、I20 | FD07 | R19—R21 | message/目录可本地fixture；安装/生成需BT07 |
| I21 | FD08 | R22、R23 | 状态mock；真实worker/retry需BT08 |
| I22、I23 | FD09 | R24、R25 | mock原子bundle；快照/权限需BT08 |
| I24、I25、I26、I27 | FD01—FD10 | R26—R31 | 以本地target codegen；退出/权限全联调需BT09 |

联调顺序：①按target和附加JSON协议构造typed mocks（不可从未知在线schema抓取）；②完成context/dirty/scopeFingerprint与金额formatter组件测试；③Core runtime schema对齐后更新本地Dashboard schema并run generate、验证所有operation；④在实际payment/worker环境验证pending→确认、自动完成与delivery隔离；⑤Playwright回归正常基础功能和非目标排除。

必要mock：加载延迟、permission/network/payload错误、CAS冲突、反序query/save、delivery WAITING/PROCESSING/RETRYING、无events、多交易净额、legacy giftcard basis、0/3位币种、长搜索词、目录空/坏数据、跨frame+过期message。所有mock仅测试材料，不代替后端业务确认。

## 5. 其他

- 验证计划：Jest/Testing Library针对useForm/filters/export/amount/unit/date/message reducers；Playwright针对配置成功/失败重试、login策略、商品诊断、筛选导出/批量、订单capture/refund、metadata行内保存、draft切渠道、目录自托管。与现有test文件就近增补，不更改冻结PRD/验收基线。
- 本阶段只读核对代码/测试位置，未运行Jest/Playwright/typecheck/lint/build/codegen或app；仓库只读且这些可能写生成/缓存。实施时采用项目既有 `npm run test:quiet <file>`、`npm run check-types`、`npm run generate` 和Playwright命令，结果真实记录，不能把设计mock覆盖当测试已通过。
- codegen须指向本地接受target，不执行fetch-schema获取升级版本。Base未改的operation需回归，退出字段必须删consumer后才生成；GraphQL HTTP200不代表业务success是所有mutation统一要求。
- 风险：legacy金额不可直接套新公式、config合并影响旧form、导出Query若进自动cache会重复受理、App消息source校验缺失会跨frame污染、self-hosted Cloud-only门槛和目录部署配置、timezone环境差异。方案分别用server权威summary、逐模块dirty护栏、no-cache+幂等、frame握手/世代、可配置目录/按权限安装及统一date工具解决。
- 本阶段额外实际执行了本地target SDL及39个拟消费operation的GraphQL验证、文档编号/覆盖、JSON Schema与HTTP结构/引用/示例检查，均通过；完整记录见接口契约§3。这不是全量Dashboard codegen或浏览器/授权/资金集成测试，未运行项目Jest/Playwright/typecheck/lint/build/codegen或app。
- 不声明目录生产服务、真实自动化/支付/升级部署已经可用；没有实际部署信息。FD/I编号本轮首次发布，后续修订保持编号，不靠新增隐藏入口恢复明确非目标。
