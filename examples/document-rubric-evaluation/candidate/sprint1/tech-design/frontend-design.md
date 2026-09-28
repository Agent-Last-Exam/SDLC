# 前端技术设计：Saleor 商家经营与应用接入升级

版本：v1
责任：前端技术设计
依据：PRD 1.0，artifacts/sprint1/prd/prd.md
修订：首次交付

## 1. 方案概述

在现有 React 17、Apollo Client、React Router v5 和 Macaw UI 架构内按业务域增量实施，不引入第二套状态管理或页面搭建框架。GraphQL 权威契约来自 `interface-contract.md` 与 `target-schema.graphql`；先同步目标 schema，再运行既有 codegen，禁止手改 `src/graphql/*.generated.ts`。

主要落点：

- 扩展 `src/siteSettings/`，把经营资料、地址、sender 和 metadata 拆为独立保存区。
- 扩展 `src/channels/`，新增库存来源模式和外部运费设置卡片。
- 新增 `src/transactions/` 财务列表/详情，复用订单交易时间线并替换礼品卡伪交易操作。
- 扩展 `src/auth/`，在匿名启动查询后按只读密码策略决定登录、找回和设置密码入口。
- 在五类既有详情页接入统一 Widget registry 和逐 Widget 故障隔离。
- 扩展 `src/extensions/` 的应用状态和 Webhook 编辑器，明确安装、停用、投递和熔断状态。
- 在维护设置中提供搜索索引任务可观测视图；迁移与对账命令本身不由 Dashboard 发起。

数据请求遵循既有 Apollo cache/type policy。分页筛选写入 URL，mutation 成功按最小范围 `refetchQueries` 或 cache update；资金 mutation 提交期间禁用重复操作，但服务端幂等键仍是最终保障。

## 2. 需求覆盖

| 需求 | 设计单元 |
| --- | --- |
| R01 | FD01 |
| R02、R03 | FD02 |
| R04 | FD03 |
| R05、R06 | FD04 |
| R07、R11、R12 | FD06 |
| R08、R09、R10 | FD05 |
| R13、R14 | FD07 |
| R15 | FD08 |
| R16 | FD09 |
| R17、R18、R19 | FD10 |
| R20 | FD11 |

## 3. 详细设计

### FD01 · 经营资料分区保存
- 覆盖需求：R01
- 设计说明：扩展 `src/siteSettings/views/index.tsx` 的 Shop fragment，读取 `id/name/description/headerText/defaultMailSenderName/defaultMailSenderAddress/companyAddress/metadata/privateMetadata`。将 `SiteSettingsPage.tsx` 拆为“展示资料”“邮件发件人”“公司地址”“Metadata”四个 section，各自维护 dirty、loading、errors 和成功反馈；复用 `components/Metadata/Metadata.tsx` 与 `utils/metadata/mutations.ts` 的表单结构，但 metadata 与普通设置一起提交 I01，避免再调用通用 metadata mutation造成双写。展示名称用 `shopDomainUpdate` 仅提交 `name`，不得把当前 domain 当作可编辑字段回传。地址清空使用独立确认对话框；保存地址只调用 `shopAddressUpdate`。Apollo mutation 结果按 section 聚合，允许资料成功/地址失败并保留失败输入。权限通过现有 permission hook 控制编辑，服务端错误仍可显示；无权时不请求 `privateMetadata`。验证包括字段映射、null/省略、分区部分成功、重复保存不新增地址及单权限 Playwright。

### FD02 · 富内容与安全图片反馈
- 覆盖需求：R02、R03
- 设计说明：保持现有 EditorJS JSON GraphQL 字段，不在前端发明新结构。抽取共享 `normalizeEditorJsDocument`/schema guard 供商品、分类、集合、Page/Model、属性及翻译表单使用；只做结构提示和预览隔离，服务端 sanitizer 是安全权威。列表 renderer 递归支持 string item 与对象 item，稳定 key 使用文档路径，空节点不提前终止后续渲染。预览容器禁止 `dangerouslySetInnerHTML` 执行未清理内容；链接统一协议检查。提交收到字段路径错误时定位 block/item，保留 draft，不覆盖服务端旧值。商品媒体导入继续使用现有 mutation，新增 I02 错误映射、进行中状态和可编辑 URL；3xx 提示最终直链，失败不清空既有 media。现有商品、分类、modeling 和 translation 测试分别增加旧/新列表、空节点、危险 URL、字段错误与图片失败场景。

### FD03 · 搜索索引任务状态
- 覆盖需求：R04
- 设计说明：在 Configuration/维护入口新增 `src/searchIndexJobs/`，包含 route、query、list、detail drawer 和 retry mutation。I03 connection 默认显示运行中和最近任务，状态区分 queued/running/succeeded/succeeded-with-failures/failed/canceled；失败列表只展示对象 ID、脱敏 code 和 retryable。轮询只对非终态 job 启用，页面离开即停止，采用递增间隔并在网络错误时显示“状态未知”而非失败；刷新页面可由 URL job ID 恢复。重试按钮只对终态且有 retryable failure 显示，mutation 成功后跳转新 job。普通对象搜索 UI 和查询保持原样，不把索引 job 当作用户搜索任务。单测覆盖乱序轮询、重试、零失败、权限和网络未知；本地验收另测提交后 60 秒检索目标。

### FD04 · 渠道库存与运费设置
- 覆盖需求：R05、R06
- 设计说明：在 `ChannelDetailsPage` 新增 `ChannelInventoryModeSection` 与 `ExternalShippingSettingsSection`，扩展 `src/fragments/channels.ts`、create/update form mapping。库存模式使用 I04 enum；兼容模式说明 Shipping Zone 仍影响库存来源，仅渠道仓库模式说明可售区域可能扩大。切换到 `CHANNEL_WAREHOUSES` 前弹窗展示当前关联仓库、排序、无仓库风险和影响摘要，确认后才修改 form。仓库、allocation strategy 和库存模式同时显示，避免把“模式”误作“分配排序”。运费 TTL 使用整数输入，前端校验 0..86400，0 明示“不缓存”；过滤开关关闭前提示候选方式可能扩大。保存只发送 changed fields，错误按 `stockSettings`/`externalShippingSettings` 分区；成功后 refetch Channel。权限沿用 `MANAGE_CHANNELS`，无权时只读。测试覆盖默认值、模式确认、TTL 边界、部分字段省略和 server rejection。

### FD05 · 交易财务入口与按来源退款
- 覆盖需求：R08、R09、R10
- 设计说明：新增 `src/transactions/`，路由 `/transactions` 和 `/transactions/:id`，导航仅对 `HANDLE_PAYMENTS` 可见。列表消费 I06，URL 持久化 ID/token、PSP、订单/结账、Channel、时间、App、礼品卡来源筛选，Relay 游标分页，默认时间倒序；金额按币种分行，不做跨币种总计。详情将 `src/orders/components/OrderTransaction/` 的 summary/timeline 抽为可复用组件，显示 sourceType、掩码卡号、实付/已退/处理中/可退及事件。订单链接在有订单权限时可点击；无权限仅显示安全引用。

  退款 drawer 消费 I07：默认按各 TransactionItem 剩余可退额形成来源分配，用户可在总额内调整；礼品卡项明确“退回原卡”，外部项明确目标应用。首次打开生成 UUID 幂等键，网络重试和重复点击复用，关闭后仅在没有已登记 request 时废弃。响应按 allocation 展示 processing/succeeded/failed，部分成功不显示整体成功；重试只带失败项的新请求键并引用原结果。移除 `OrderTransactionGiftCard` 的 fake action，礼品卡真实 TransactionItem 走统一组件；绝不调用 `giftCardUpdate` 代替退款。测试覆盖分页稳定、筛选、权限、重复提交、部分成功、原卡不可用及敏感码不渲染。

### FD06 · 退出旧数字入口与旧账结果登记
- 覆盖需求：R07、R11、R12
- 设计说明：当前 `src` 无手写 DigitalContent 页面或 operation；后端切到目标 schema 后运行 codegen，确认 generated 文件不再含 `DigitalContent`，清理失效错误文案，做 Product/Variant smoke test。不得增加历史下载管理或新分发 UI。交易详情对 `sourceType=LEGACY` 且存在待处理义务时，向有 `HANDLE_PAYMENTS` 用户提供“登记外部结果”对话框，消费 I08；表单明确“不会发起资金动作”，要求 action、金额/币种、PSP reference、执行时间、证据引用和幂等键。提交成功刷新交易/订单，重复结果显示原事实，不允许编辑已确认金额。四个退出插件不在 Extensions/plugin 配置中显示为可安装/启用；历史 Payment 详情仍可读。测试覆盖 schema/codegen 无旧引用、只读历史页、结果登记权限与重复登记。

### FD07 · 密码策略一致执行
- 覆盖需求：R13、R14
- 设计说明：认证启动 query 同时读取 I01 `passwordLoginPolicy` 和现有 `availableExternalAuthentications`。`LoginPage` 按当前策略与未知状态渲染：`ALL` 显示密码；`CUSTOMERS_ONLY` 在匿名阶段不能判断邮箱所属账号，因此保留统一邮箱入口，由提交后服务端安全错误决定是否转外部登录，响应不暴露账号存在性；`DISABLED` 隐藏密码/找回并只显示外部方式。策略 query 失败按最严格状态处理，不回退开放密码。`NewPasswordPage`、reset/invite route 和员工密码入口同样消费策略及服务端错误。Dashboard Configuration 增加只读策略卡，说明配置来源和恢复路径，不提供 mutation。策略收紧导致 token 失效时，AuthProvider 清除本地会话并返回登录页；放宽不恢复旧 token。测试覆盖三态、未知、无外部方式、旧链接、员工安全错误和外部回调。

### FD08 · 五类 Widget 宿主
- 覆盖需求：R15
- 设计说明：在 `extensions/extensionMountPoints.ts` 与 `domain/app-extension-manifest-available-mounts.ts` 增加 I09 五值，并建立单一 `widgetMountRegistry` 描述 mount、required context 和宿主。分别在 `CategoryUpdatePage`、`PageDetailsPage`、`PageTypeDetailsPage`、`MenuDetailsPage`、Promotion/Discount details 的既有 more-actions 附近挂载 `AppWidgets`，不替换旧入口。上下文只构造 object ID 和当前 Channel；无 Channel 不传空伪值。每个 Widget 使用独立 error boundary、加载超时和重试，来源校验或 iframe 错误只替换自身卡片，不触发页面 error boundary、不阻断 Savebar。无合法 extension 不渲染容器。沿用 iframe sandbox 和 POST token 传递方式，URL/日志不放长期 token。测试覆盖五个 registry、权限过滤、无扩展、重复去重、故障隔离和 context。

### FD09 · 应用故障状态解释
- 覆盖需求：R16
- 设计说明：扩展 Installed Extensions query/fragment 消费 I10，并保留 pending installation、`isActive`、breaker 和 failed delivery 的独立来源。实现纯函数 `deriveAppStatusPresentation`，优先显示安装失败（未安装项）、主动停用、熔断 OPEN/HALF_OPEN、投递 EXHAUSTED/FAILED，再显示监控模式；同一应用可在详情同时展示多个问题，列表只显示最高影响并附计数。状态 query 出错或 monitoring unknown 显示“未知/刷新”，不能显示绿色健康。详情继续复用 `AppWebhooksDisplay`，全局提醒链接到有权详情；无日志权限只显示影响摘要。界面不提供阈值编辑、强制 reset 或资金重放；现有 re-enable 能力若保留，仅在契约允许和 `MANAGE_APPS` 下显示，并明确不是资金重试。测试覆盖状态矩阵、时间、未知、权限和脱敏文本。

### FD10 · Webhook 订阅、Channel 与事件迁移
- 覆盖需求：R17、R18、R19
- 设计说明：扩展 `WebhookDetailsPage` fragment/form 消费 I11/I12。`WebhookChannelSelector` 明确“全部渠道”和多选，内部存 Global ID；update 中未触碰时省略 `channelIds`，选择全部发送空列表。query 编辑器继续使用 GraphiQL/Explorer，但 fetcher 改用 runtime API URL；提交前 parse 并将 syntax、missing event、field/permission 错误定位 editor，失败保持有效服务端值和本地 draft。事件选择器加入新增事件，并对其强制 subscription-query 模式，不能切 fixed payload；旧事件保留原模式。投递列表显示 stable eventId、attemptCount、PENDING/SUCCESS/FAILED/EXHAUSTED，retry 明示至少一次和消费者幂等。提供 migration callout、样例预览和逐 Webhook 切换，不以真实资金事件 dry run。测试覆盖 null/empty Channel 语义、query 保存失败、撤权、事件列表、重试 eventId 不变和旧订阅不被自动改写。

### FD11 · 切换状态与版本可追溯
- 覆盖需求：R20
- 设计说明：Dashboard 不执行数据库迁移、备份或流量切换。构建时记录 commit/image/schema 摘要并在现有版本信息区可查；GraphQL codegen 固定使用交付 `target-schema.graphql`。维护窗口由部署层关闭写入口时，Dashboard 显示全局维护 banner 并禁用相关保存/资金操作，查询和历史核对保持；即使前端未禁用，后端仍必须拒绝。开放后 smoke 覆盖登录、Channel、交易、历史订单和应用状态。前端发布清单记录 API/schema 匹配、关键路由、外部 Widget 来源和回滚条件，不把本地 mock 成功当作生产路径验证。

## 4. 依赖与联调

| 接口 | 消费方设计单元 | 对应需求 | 开发依赖 |
| --- | --- | --- | --- |
| I01 | FD01、FD07 | R01、R13、R14 | Shop 现有部分可独立；策略需等待 |
| I02 | FD02 | R03 | 错误 UI 可 mock，联调需等待 |
| I03 | FD03 | R04 | 需等待 |
| I04 | FD04 | R05、R06 | 需等待 |
| I05 | FD06 | R07 | 需等待目标 schema 后 codegen |
| I06 | FD05、FD06 | R08、R10、R11 | 需等待 |
| I07 | FD05 | R09 | 需等待 |
| I08 | FD06 | R12 | 需等待 |
| I09 | FD08 | R15 | registry 可独立，联调需等待 enum |
| I10 | FD09 | R16 | 部分可用 Base breaker mock，聚合需等待 |
| I11、I12 | FD10 | R17、R18、R19 | query editor 可独立，Channel/事件需等待 |

联调按“schema/codegen -> mock contract -> API integration -> 权限/异常 -> E2E”推进。资金、密码和 Webhook mock 必须包含部分成功、未知、重复投递和撤权，不只覆盖 happy path。前后端共同锁定 enum、error code 和 null/omitted 语义后再生成类型。

## 5. 其他

- Base 静态调查显示：站点页已有地址但缺完整资料/sender/metadata；交易只在订单内，礼品卡为 fake transaction；登录/找回总是显示；五类冻结 Widget 尚无挂载；Webhook query editor 已有但无显式 Channel。路径详见各 FD。
- 风险：目标改动跨度大，单次 codegen 会产生大量 generated diff；评审只审手写 operation 与 schema，不手工修改 generated 文件。
- 风险：PRD 要求 `CUSTOMERS_ONLY` 且匿名登录不能枚举员工身份，前端不能仅凭邮箱预判；权威拒绝必须在服务端，界面使用统一错误文案。
- 未决项：真实维护只读信号在 Base schema 中未定义，本设计不擅自加入产品 API；部署可通过现有网关/环境注入 banner，后续若要求 API 化需新增接口编号。
- 验证计划包含组件/表单单测、Apollo operation mock、单权限 Playwright、关键路由 E2E、目标 schema codegen/typecheck；本阶段未执行这些验证。
