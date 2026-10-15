# 提测报告：Saleor 3.23 结账、收款与商户运营一致性（首轮部分交付）

版本：v1（2026-10-14）
轮次：1
依据：PRD v1；前端技术设计 v1；后端技术设计 v1；接口契约 v1；目标 schema v1

> **提测结论：部分交付，整体发布阻断。** 本轮实现并自测了配送显式重算、渠道配置、密码策略、OIDC 安全加固、富文本校验、扩展兼容、配送元数据快照等局部能力，但未完成全部 R01—R31。可对本报告列明的实现进行局部 QA 验证，不可据此认定 Saleor 3.23 完整需求可发布。没有上一轮 QA 报告、QA 执行记录或修复计划输入；本报告记录的是开发自测，不是 QA 已验收。未修改冻结 PRD、技术设计、目标 SDL 或冻结测试用例。

## 1. 提测版本

| 仓库 / 组件 | 代码版本或构建标识 | 代码位置 |
| --- | --- | --- |
| Core（基线 3.22.0） | 基线 HEAD：`c864e66b8e537d30732ddba62d3a4c47e49e4a3e`；当前源码内容 SHA256：`7d1ca600d3d48000ece51183eaca085eecfbf6ffbde9f5cd25cd5f44a25d6228` | `/workspace/repos/saleor` |
| Dashboard（基线 3.22.9） | 基线 HEAD：`aebb2401b5079fbbb8c60150289d1896c108feca`；当前源码内容 SHA256：`706f7f0f09ca0afa4d4ea7259d04cc0aec94ed1d663c168f9c6345163d0e846f` | `/workspace/repos/saleor-dashboard` |
| 当前实际 GraphQL SDL | 最终运行导出、Core SDL、Dashboard SDL 三份字节一致；SHA256：`440e9e87f24dc0f7cb053a287a92d74db730dea2e6e437e3ae777f8050ad58aa` | Core：`saleor/graphql/schema.graphql`；Dashboard：`schema.graphql`；本地导出：`/workspace/scratch/schema-delivery.graphql` |
| 部署版本 | 待部署 | 待部署 |

版本定位与交付说明：

- 两个仓库均存在本轮未提交的变更；Core 变更/新增 89 个文件，Dashboard 变更/新增 46 个文件。未创建 commit、push、PR 或发布；不能仅用基线 HEAD 定位交付代码。
- 当前源码内容标识包含 tracked 与 nonignored-untracked 路径、文件内容、类型和可执行位；缺失的 tracked 文件显式计入。它不包含 `.git`、ignored 依赖、缓存或构建产物，**不是运行器快照 hash**。实际代码快照由运行器保存。
- 内容清单：[`saleor-source-manifest.json`](saleor-source-manifest.json)、[`saleor-dashboard-source-manifest.json`](saleor-dashboard-source-manifest.json)。最终自测后再次核对，两个源码标识及工作区状态均未变化。
- 工作区状态：[`saleor-working-tree-status.txt`](saleor-working-tree-status.txt)、[`saleor-dashboard-working-tree-status.txt`](saleor-dashboard-working-tree-status.txt)。tracked diff 统计：[`saleor-diff-stat.txt`](saleor-diff-stat.txt)、[`saleor-dashboard-diff-stat.txt`](saleor-dashboard-diff-stat.txt)；新增文件以 status 和 manifest 为准。
- 已完成 Dashboard GraphQL codegen、默认文案提取并增加 changeset；没有手工修改生成文件，没有新增依赖或变更 package/lockfile。项目包版本未冒充已发布的 3.23。
- 验证证据已归档至 [`evidence/`](evidence/README.md)，26 份选定日志/结果的长度、来源和摘要见 [`evidence/evidence-files.json`](evidence/evidence-files.json)。

## 2. 已完成功能

下表“完成”仅指所列实现，不代表该需求全部 AC 已验收；剩余范围见第 3 节。

| 需求 | 完成情况 |
| --- | --- |
| R01 · Storefront 显式重算当前结账配送选项 | 新增 `checkoutShippingRefresh`，返回配送方式、提货点、旧选择及有效性和计算时间；拒绝 inactive channel、不可用变体、缺必要配送地址；同步配送服务错误映射为业务错误。使用 request-local fresh 上下文绕过相关配送缓存，不分配/清除配送选择、不改 checkout 更新时间、不成单；对计算前后 checkout 更新时间及渠道 settings revision 做冲突检查。选定刷新与 Webhook 配送缓存回归通过。不是全部依赖版本/并发闭环。 |
| R03 · 渠道库存策略跨入口一致且保留旧行为 | 新增 `LEGACY` / `CHANNEL_WAREHOUSES` 库存可用策略字段及 GraphQL 配置；部分 Warehouse queryset 在新策略下按渠道直接关联仓库取集合，旧商店迁移默认 LEGACY。未将“有库存”改称“可配送”；统一库存资格服务、所有入口和关系变更锁尚未完成。 |
| R06 · 渠道自动完成开关、延迟与 cutoff 配置 | 增加 delay、cutoff、settingsRevision 和 expectedSettingsRevision；delay 校验 0—10080 分钟、默认 0，cutoff 可清空且要求带时区；omission 保留旧值、delay null 拒绝。渠道更新锁当前行、校验 revision，敏感配置权限限制；Dashboard 表单和校验已接入。**只是配置落库，不代表 worker 已按新参数执行。** |
| R16 · 商店统一密码认证策略 | 增加 ENABLED / CUSTOMERS_ONLY / DISABLED、epoch、revision；服务端在密码登录、注册及相关重置/设置/修改入口校验策略，外部身份关联账户限制本地密码路径。JWT 带认证来源与 epoch，旧本地凭据按保守密码路径校验，策略切换使旧 epoch 不再有效；reserved claims 不允许 additional payload 覆盖。Dashboard 读取策略并控制入口，认证失败/缺 payload 不再显示成功。authentication 选定完整目录回归通过，仍不等于安全矩阵全部完成。 |
| R17 · OIDC 离线授权与旧密码路径处理 | 改为稳定 `(issuer, subject)` 身份关联，支持授权码 state/nonce、PKCE S256、一次性 state、provider 合同下的 `access_type=offline`，不通用强加 `offline_access`。授权码本地登录完成包在 writer/atomic 中；首次关联禁用旧密码并轮换凭据 key。输入增加类型、长度、scope token 边界，网络/provider 错误固定脱敏，私网 IP 防护保留。provider refresh secret 经服务端 Fernet 加密保存，客户端仅持 UUID handle；一次消费时锁行、清除密文，成功刷新产生新 handle；access JWT 不再携带 provider access secret、refresh JWT 不携带 provider refresh secret。OIDC 全目录及两独立数据库连接竞争消费测试通过。生命周期和浏览器会话绑定等仍未闭环。 |
| R18 · 富文本结构、链接与深度在保存前校验 | EditorJS 完整结构白名单、字段与资源预算、列表深度、链接 scheme、HTML 属性、媒体/embed 校验；危险项整项拒绝，不用 `#invalid` 替换后伪装成功，`_blank` 添加 `noopener noreferrer`。SanitizedJSONField、批量商品描述、属性及翻译的相关校验入口接入；输出深拷贝，不原地部分修改输入。本轮追加历史合法未闭合 inline HTML/嵌套 anchor 的安全规范化、旧 list/image/embed 可编辑性和恶意内容负例；新合同 41 项及商品批量 2 项通过，另有跨资源既有回归 391 项通过。旧 EditorJS 文件仍有 9 项失败，详见 3.3，不宣称全部兼容。 |
| R19 · App 安装更新、扩展字段与历史迁移 | 增加扩展规范化及 `mountName` / `targetName` / `settings`，校验 canonical/legacy 字段冲突、target 对应设置及 GET/POST，保留旧读取兼容，manifest 中 tokenTargetUrl 可选。增加 settings 迁移，历史 widget/new-tab 的 GET/POST 映射得到保留，重复执行不覆盖显式 settings；扩展合同及 App 查询选定回归通过。identifier 唯一、安装/升级完整原子性与安全约束仍未完成。 |
| R24 · 创建时配送 public/private 元数据快照 | Order 增加 public/private 配送快照与来源状态，Payment 成单、Transaction 成单、草稿完成三个入口捕获深拷贝；Order 与 Fulfillment 从订单快照读取，不回读当前配送方式；private 查询沿用订单权限。未知历史默认 `{}` + UNAVAILABLE，不捏造历史。两条 checkout 成单快照、源修改/删除、草稿完成、历史状态和客户 private 拒绝等选定回归通过；事件与全主体权限矩阵待补。 |
| R25 · 基础元数据读写保留且不新增独立入口 | 增加 key/value 类型、长度、重复输入的整项校验；writer/atomic、owner 行锁、read-modify-write；业务错误或 ValidationError 回滚，仅实质变化触发额外动作。graphql/meta 目录回归通过。未新增订单、履约、仓库独立元数据弹窗；完整多连接并发与事件回滚矩阵未全验。 |
| R26 · 公开 API 输入类型、失败语义与查询正确性 | 非负时长 scalar 按真实整数和 32-bit 边界校验，UUID 类型防护、Decimal literal 非有限值防护；模型写入与敏感输入部分拒绝未知字段/非法 JSON，富文本错误映射回字段。相关 scalar/input 合同回归通过；没有把该部分视为所有公开入口、分页、federation 的全面正确性证明。 |
| R27 · schema、弃用替代与空库/历史迁移一致 | 导出当前实际 Core SDL、同步 Dashboard 并运行四个 codegen 目标成功；新增 7 个迁移。Django system check、迁移漂移与待执行迁移检查通过。独立空库 1342 个迁移全部 OK；独立合成旧库升级演练通过，订单/资金/库存/关系等选定历史事实摘要不变，扩展 backfill 重跑保留显式配置。**目标 SDL 仍有大量差异，不是目标版本已交付。** |
| R28 · 敏感操作、员工实际删除与对象范围 | staffDelete 在事务中执行实际删除，事件 on_commit；相关既有回归通过；private 配送元数据限制见 R24。商业历史关联、actor 与全部对象权限矩阵未完整验证。 |
| R29 · 配置加载、编辑上下文与成功缓存 | Dashboard 表单增加 dirty-preserving 回填、编辑期间保留基准 revision、pending 防重复提交及卸载保护。配置结果必须具备预期 payload、errors 数组及必需 resource；GraphQL/transport/business/missing-payload 失败不整体提示成功。SiteSettings 两个结果都成功后才通知；Channel update/reorder 结束后统一通知；认证表单类似失败语义修正。77 项选定前端测试通过；后端多 mutation 原子性、receipt/context 和 savebar 状态仍不完整。 |

主要实现定位：Core 的 `saleor/graphql/checkout/mutations/checkout_shipping_refresh.py`、`saleor/account/password_policy.py`、`saleor/plugins/openid_connect/`、`saleor/core/utils/editorjs.py`、`saleor/app/extensions.py`、`saleor/order/shipping_snapshot.py`、`saleor/graphql/meta/mutations/`；Dashboard 的 `src/auth/`、`src/channels/`、`src/hooks/useForm/`、`src/siteSettings/`、`src/utils/configurationMutation.ts`。完整文件范围以版本清单为准。

## 3. 未完成项与已知问题

### 3.1 全部需求的剩余范围与影响

以下是本轮实现缺口，不是经批准删除的范围。未交付能力不能交由 QA 用模拟实现替代验收。

| 需求 | 当前未完成项 / 已知影响 |
| --- | --- |
| R01 | refresh 尚未覆盖所有地址/商品/价格/库存/外部服务依赖的统一版本及 writer/replica 并发矩阵；不能保证任意依赖并发修改都检测到。 |
| R02 · 更新配送与完成结账再次校验有效性 | **未完整实现统一 fresh evaluator 和最终提交锁。** `checkout_cleaner.py` 仍存在失效时 clear_delivery_method 的旧行为，配送更新入口没有全量统一新求值与 revision。不能承诺失败保持旧选择、全部最终成单入口均使用新鲜结果。 |
| R03 | 缺统一 eligibility 服务和商品/预留/订单/履约全部入口接入、关系变更锁及真并发验证；不能承诺跨入口库存完全一致。 |
| R04 · 商品编辑页按渠道诊断真实可售问题 | 未实现诊断接口、服务、Dashboard UI；目标 `productAvailabilityDiagnostics` 缺失。未擅自制定未给出的 WARNING 业务阈值。 |
| R05 · 已支付结账批量自动成单与幂等重试 | durable batch/completion、幂等屏障、outbox、reconcile 主链未实现；`checkoutCompletionStatus` 缺失。不能承诺崩溃恢复后不重复成单/资金动作/事件。 |
| R06 | worker 未接入 delay/cutoff，配置已保存不等于后台开始按目标策略执行；严格延迟边界与 cutoff 执行、策略切换下任务重验尚待实现。 |
| R07 · 礼品卡统一初始化、授权与扣款生命周期 | 统一 ledger/transaction 主链未实现；初始化 mutation、authorizedBalance/availableBalance 等缺失。 |
| R08 · 取消礼品卡授权、退款与事件对账 | 取消、退款、事件与账本对账主链未实现；不可将旧余额行为称为统一生命周期。 |
| R09 · 订单金额分解、汇总与剩余待付统一 | 未实现服务端 paymentSummary、mixed Payment/Transaction 逻辑来源去重及 Dashboard 全量投影。净 charged、pending refund、gift-card 子集等冻结金额合同尚未形成统一实现。 |
| R10 · 标记已支付、捕获授权与退款安全执行 | 资金 command 幂等、状态/余额/并发屏障和完整 UI 未实现；不能保证重试不产生重复外部资金动作。DB 回滚不能撤销外部 PSP 已成功的扣款或退款。 |
| R11 · 保留根级交易基础定位与权限分页 | `Query.transactions` 及对应基础定位/权限分页目标未实现。 |
| R12 · 主体增强搜索与 Page/User 基础搜索边界 | 主体增强搜索、参数和基础搜索保留矩阵未完整实现/回归。 |
| R13 · 搜索更新、稳定分页与异常状态 | 增量更新、稳定 cursor、排名/错误状态目标未闭环；材料未给一致性窗口数值，未将 scheduler 周期冒充 SLA。 |
| R14 · 锁定筛选与导出、批量操作范围一致 | locked-filter、只读分页查询导出和对应 bulk 范围目标未实现；productsExport/giftCardsExport/voucherCodesExport 缺失。 |
| R15 · 选择器、层级导航与长搜索输入保留上下文 | 相关 UI 与上下文保留矩阵未完整实现，不能宣称这部分 P1 已通过。 |
| R16 | 完整本地密码策略绕过、active user/权限变化、writer/replica 和并发切换矩阵待补；前端所有表单双击/异常状态未端到端验收。前端隐藏入口不能替代服务端授权。 |
| R17 | 缺浏览器会话级 state 绑定、真实签名 algorithm/issuer/audience/nonce/expiry 负矩阵、身份首次关联真并发、direct JWT/opaque 路径完整原子性及最小权限、refresh 与 active user 并发、logout/revoke、过期/已消费 session 清理、clientId 变更策略和全日志链脱敏证明。真实 provider 联调未做。兼容/密钥要求见 3.4。 |
| R18 | 旧 EditorJS 测试仍 9 failed / 3 passed（见 3.3）；全 serializer 支持集、所有写入/bulk/translation 的危险内容原子性及更广 HTML 边界矩阵未完成。391 项既有资源回归通过不等于所有新安全负例都覆盖。 |
| R19 | identifier 唯一、原子 install/update、issueToken=false 全路径、SSRF、frame/catalog 合同未完整实现。不能以扩展字段及迁移成功代替完整 App 生命周期验收。 |
| R20 · 扩展响应只作用于对应当前表单 | frame 请求/响应关联、当前表单上下文、过期响应/来源校验协议未实现。 |
| R21 · 自托管扩展目录可用且按权限操作 | self-hosted catalog、失败/空/无权限展示与操作主链未实现。 |
| R22 · Webhook 按订阅解析与异步载荷边界 | selection-aware 解析、deferred payload/outbox 主链未实现；本轮 fresh 配送缓存改动不等于本需求完成。 |
| R23 · delivery 失败隔离、准确通知与可见状态 | receiver 隔离、重试状态及 latestError/nextRetryAt/payloadGeneratedAt 等目标未实现，不能承诺一个接收方失败不影响全部其他接收方。 |
| R24 | 事件 payload 与订单事实一致性、staff/App/tax App 全部 private 权限、外部配送/提货端到端、可信旧快照分类审计与源变更/成单真并发未完成。合成旧库未知历史 UNAVAILABLE 不等于所有历史数据已核验。 |
| R25 | metadata 多连接 lost-update、child storage、owner 删除和事件回滚完整矩阵未验收；基础读取权限未做全对象穷举。 |
| R26 | 全入口分页/过滤参数、非法 global ID、federation、查询失败语义和输入类型矩阵未闭环；scalar 局部通过不代表完整公开 API 通过。 |
| R27 | 当前实际 schema 尚不符合目标，详情见 3.2；弃用替代、目标退出能力、生产分布升级审计及发布回退演练未完成。 |
| R28 | 敏感资金/App/私有字段全矩阵、商业历史 FK/actor 在员工真删后的完整一致性未验收；不能把 staffDelete 局部回归当成所有权限范围证明。 |
| R29 | SiteSettings 两个 top-level mutation 不具备后端整体原子性；Channel update/reorder 两步也非整体原子。第一步已保存、第二步失败时仍可能部分落库；savebar 状态仍未完全代表组合结果。mutation receipt、context ownership、迟到响应/StrictMode/cache 隔离完整模型未完成。 |
| R30 · 正确展示重量、媒体、金额和日期并限制草稿动作 | 广泛重量/媒体/金额/日期适配及草稿资格目标未完整实现；`Order.canAddProducts`、`draftOrderProblems` 缺失；无整页/E2E 验收。 |
| R31 · 非目标不回流且基础经营能力保留 | 未新增冻结非目标功能，但基础经营能力未全仓/端到端回归；目标要求退出的字段仍存在，不能称非目标/退出边界全部对齐。 |

### 3.2 接口合同阻断

静态 AST 对比：缺失类型 **32**、实际额外类型 **11**、缺失字段 **23**、实际额外字段 **15**、字段签名/参数/默认值/弃用标记差异 **33**、枚举差异 **15**、kind 差异 **0**。缺失类型不再展开重复统计其字段；比较忽略描述和声明顺序，不是 resolver 或完整 directive 语义验收。完整结果：[`evidence/schema-target-diff.json`](evidence/schema-target-diff.json)。

主要缺失根入口：

- `Mutation.giftCardTransactionInitialize`
- `Query.checkoutCompletionStatus`
- `Query.productAvailabilityDiagnostics`
- `Query.transactions`
- `Query.productsExport` / `giftCardsExport` / `voucherCodesExport`

其他主要缺口：`Order.paymentSummary`、草稿资格字段、礼品卡余额/事件、TransactionItem 的 appIdentifier/availableCaptureAmount/availableRefundAmount、EventDelivery 新状态字段、AppExtensionFilterInput 的 canonical 过滤字段。多个资金 mutation、bulk、Query 参数与目标签名也不一致。

目标退出而实际仍保留的 15 个字段包括 DigitalContent 的读写及关联字段、Shop 数字内容设置及对应 input、`Payment.partial`。当前 Core 与 Dashboard SDL 一致，只证明双方仍使用同一**当前实际**接口，不能用它替代冻结目标 SDL，也未修改冻结目标来消除差异。

### 3.3 已执行但未通过的检查

| 检查 | 实际结果 | 说明与影响 |
| --- | --- | --- |
| 旧 `saleor/core/utils/tests/test_editorjs.py` | **9 failed、3 passed、1 warning** | 六项是历史合法未闭合/嵌套 anchor 等内容被规范化，旧断言要求原字符串/文档字节不变；本轮已由“合法旧内容被拒绝”修为“合法内容可安全规范化”。另三项为 `{}` 缺 blocks 的旧保留预期一项，以及两项 mock 已移除 `parse_url`、期待危险链接替换为 `#invalid` 的旧实现预期。冻结内容合同要求 blocks 必填及危险项整项拒绝。未修改旧测试以消除失败；也不将全部失败豁免成无影响，完整兼容验收仍待补。 |
| Dashboard 全量 ESLint | **192 errors、2469 warnings** | 全量门禁未通过。errors 与当前变更/新增文件交集为 0；由于配置修正启用了正确 flat recommended 形态，未对所有错误完成基线归因，**不能断言 192 项全是已证实的基线问题**。明细在 `evidence/dashboard-eslint-summary.json`。 |
| Dashboard 增量 ESLint | **0 errors、28 warnings** | 仅选定变更源码检查无 error；仍有 effect dependencies、导出/UI 等 warning，不替代全量 lint。 |
| Dashboard Knip | **未通过** | unused devDependencies 9 项为 error；另有 unused files 2、unlisted dependency 1、unused exports 5、unused types 3、duplicate exports 26。未为消除结果盲删依赖，未完成全量基线归因。 |

EditorJS 新合同 41 项 + product bulk 2 项均通过；它们已包含在 1377 项主回归中，不累计为额外独立通过数。归档的旧测试日志是最新失败结果，不隐去失败退出状态。

### 3.4 身份、安全与兼容注意事项

- **部署必须配置稳定 SECRET_KEY 及明确的 SECRET_KEY_FALLBACKS 轮换窗口。** 当前测试设置出现“SECRET_KEY not configured, using a random temporary key”警告；这是本地隔离测试环境限制，不能用于部署。refresh secret 加密 key 由 SECRET_KEY 经独立 HKDF info 派生，旧 key 无 fallback 会使相关 session 无法解密。
- 旧含 provider secret 的 refresh JWT 按 fail-closed 拒绝，需要重新登录；超时后旧 handle 已消费，不自动重用未知状态的 provider refresh secret，需要重新认证。尚需完整 UI/错误合同与升级告知验收。
- 两连接竞争测试证明单个 refresh handle 恰好一个消费者可得到 secret，不证明整个 OIDC 登录/刷新/logout/revoke 生命周期已经完全并发安全。客户端不新增 refresh secret 的持久化存储。
- 本轮未使用真实 PSP、OIDC provider 或业务 Webhook 做外部联调；pytest VCR 使用 `--record-mode=none`，没有新录制真实交互。所有资金/身份升级样本为合成数据，不含真实 token、client secret 或生产私钥。
- 有限快照检查见 [`snapshot-audit.json`](snapshot-audit.json)：两个仓库均未发现指向仓库外的符号链接；非依赖凭据形状路径、非依赖工具缓存路径为空；两个 `git diff --check` 均通过。扫描包括 ignored 依赖中的符号链接，但内容标识不包含 ignored 依赖。
- source 正则的两个 private-key-header 命中均为原有合成测试 fixture，位于 `saleor/tests/settings.py` 和 OIDC `tests/conftest.py`；已与基线逐块比较相同，分类结果见 [`evidence/test-fixture-key-classification.json`](evidence/test-fixture-key-classification.json)，不含 key 正文，不能用于部署。原 ignored `.jwt_key.pem` 已隔离到 scratch，仓库根无该文件，未放回快照。
- 上述仅为有限文件名/正则/符号链接检查，**不是完整凭据扫描、安全审计或生产数据脱敏验收**。归档未复制隔离密钥、provider 响应录制或真实敏感载荷。

### 3.5 尚未执行与材料限制

- 未执行全仓后端测试、全量 Dashboard 单测、Playwright E2E、真实浏览器全链路、生产规模并发/性能、真实 provider/PSP/Webhook、部署/回退验收。
- 冻结 `test-cases.v1.csv` 的 TC001—TC260、31/31 需求与 191/191 AC 是**测试设计覆盖**，不是本轮逐条执行通过数字；本轮没有把仓库单测冒充冻结 CSV 执行记录。
- PRD 有待确认项；没有自行添加业务阈值、搜索一致性 SLA 或未授权外部服务配置。前端设计文本写 React17，而实际依赖为 React18.3.1；本轮沿用当前依赖、不改冻结设计，并据实记录。
- 没有上一轮真实 QA 缺陷输入；本轮调试修复记录（历史 HTML 规范化、OIDC 安全边界、表单失败语义等）不包装成 QA 复测通过。

## 4. 测试环境与验证方式

- 部署状态：**待部署**。
- 部署版本：**待部署**。
- 环境入口：**待部署**；未提供可外部访问的 Dashboard/API 链接。本地测试和 bundle 验证不是部署，也未承诺存在监听中的 `127.0.0.1:8000/graphql/` 服务。
- 访问方式：**待部署**；没有创建或提供部署测试账号。当前通过仓库 pytest fixtures、Jest mocks 和独立合成数据库样本验证，不使用真实商户/客户数据；测试数据定义见相应测试文件，升级样本见 scratch 演练脚本，不能把合成账号当生产访问凭据。
- 验证方式：本地 isolated Python venv + PostgreSQL 的选定 pytest、Django/迁移检查；Dashboard 选定 Jest、类型检查、codegen、文案提取、ESLint/Knip 和隔离 Vite bundle；详细命令、scope 和证据索引见 [`evidence/README.md`](evidence/README.md)。
- 环境限制：没有部署环境、真实外部集成或 E2E；LocMemCache 代替 Redis；writer/replica URL 指向同一本地 PostgreSQL，不能证明真实读写延迟行为；Celery durable 任务链及真实资金动作不在本轮验证范围。临时 SECRET_KEY 不满足部署要求；全量 lint/Knip 和整体业务需求未达发布条件。

### 4.1 环境明细

| 项目 | 本轮实际环境 |
| --- | --- |
| Core | Python 3.12.14、Django 5.2.13、Graphene 2/graphql-core 2、PostgreSQL 15、psycopg 3 |
| Python 依赖环境 | `/workspace/scratch/venv`；先 activate，再 `python -m pytest`，使用 `--reuse-db`、`--record-mode=none` |
| 测试设置 | `/workspace/scratch/stage_test_settings.py`，继承 `saleor.tests.settings`；媒体、私有媒体、文件邮件输出到 scratch，缓存 LocMemCache |
| 本地 PostgreSQL | `127.0.0.1:55432`；开发库 `saleor_development`，pytest 库 `test_saleor_development`；仅隔离本地用途 |
| 迁移演练 | 空库 `saleor_sprint1_empty`；旧库升级 `saleor_sprint1_upgrade_rehearsal`；均为独立本地合成库 |
| Dashboard | Node 24.21.0、npm 11.19.0、React 18.3.1、TypeScript 5.8.3；现有本地依赖，不新增依赖 |
| 缓存与临时文件 | npm/corepack、pytest、Ruff、Jest、Vite、Node compile/Jiti、虚拟环境、数据库、构建产物和临时验证脚本均使用 `/workspace/scratch/`；仓库不使用指向 scratch 的符号链接替代依赖 |

### 4.2 本轮最终自测结果

| 验证项 | 最终结果 | 证据 / 范围 |
| --- | --- | --- |
| 后端主要选定回归 | **1377 passed、1 warning，167.56s** | `evidence/backend-handoff-regression.log`；EditorJS 合同、渠道配置、authentication 全目录、staffDelete、graphql/meta、App 扩展/查询、OIDC 全目录、scalars/input、配送 refresh/缓存、product bulk、shop settings、snapshot、两个既有完整 checkout 成单文件 |
| 后端跨内容资源既有回归 | **391 passed、1 warning，52.46s** | `evidence/backend-content-entrypoints.log`；Page create/update（含 deprecated）、translations（含 deprecated）、Category/Collection/ProductType create/update、Attribute create/update；与主 scope 不重复 |
| EditorJS 新合同子集 | **43 passed、1 warning，3.17s** | 41 合同 + 2 product bulk；包含在 1377，不重复累计 |
| 旧 EditorJS | **9 failed、3 passed、1 warning，3.00s** | `evidence/backend-legacy-editorjs-final.log`；原因见 3.3 |
| changed/new Python Ruff | **check 通过；88 files already formatted** | `evidence/backend-handoff-ruff-check.log` / `backend-handoff-ruff-format-check.log` |
| Django 最后系统检查 | **0 issues** | `evidence/backend-handoff-system-check.log` |
| 迁移漂移检查 | **No changes detected** | `evidence/backend-handoff-migration-drift.log` |
| 本地待执行迁移检查 | **通过，无 pending migration** | `evidence/backend-handoff-migration-check.log`；最终 set-e 检查序列 exit 0 |
| 独立空库初始化 | **1342 个 Applying 步骤、1342 个 OK** | `evidence/backend-empty-db-migrate-psycopg3.log`；包括本轮全部 7 个新增迁移，随后 system/migrate check 通过 |
| 独立合成旧库升级 | **通过** | `evidence/migration-upgrade-result.json`；详情见 4.3 |
| 实际 SDL 一致性 | **三份 SHA256 相同** | 本报告第 1 节；目标差异仍存在，不算目标验收通过 |
| Dashboard 类型检查 | **通过** | Playwright TS、src TS、**2832 strict files** 全通过；只编译，未运行 E2E |
| Dashboard 选定单测 | **12 suites、77 tests 通过，5.706s** | 登录/新密码/重置/策略 gate、配置 dirty/pending/回填与提交、渠道重排、组合结果、datagrid row anchor hooks |
| Dashboard GraphQL codegen | **四个输出目标成功** | fragmentTypes、typePolicies、types、hooks；生成结果以实际 SDL 为基础，不声称 target 已实现 |
| 默认文案提取 | **通过** | `evidence/dashboard-messages-delivery.log` |
| Dashboard 增量 ESLint | **0 errors、28 warnings** | 不是无 warning，不替代全量结果 |
| Dashboard 全量 ESLint | **未通过：192 errors、2469 warnings** | error 明细已归档；归因限制见 3.3 |
| Dashboard Knip | **未通过** | 9 unused devDependencies 为 error，其他警告见 3.3 |
| Dashboard 隔离生产模式 bundle | **成功，42.91s** | 输出 `/workspace/scratch/dashboard-build`；基于实际 Vite config，排除 Sentry 上传、copy-og-image/copy-noop-sw、code-inspector 插件；无外部 release/上传。**不是完整标准发布包或部署通过** |
| 两仓 `git diff --check` | **通过** | 见 `snapshot-audit.json`；无 commit/push |

后端上述 warning 为临时 SECRET_KEY 提示；不能因此声称部署配置正确。中间重跑的 1365/1269 等历史通过数不作为额外数量累计。旧使用 psycopg2 的环境准备脚本曾失败且出现误导性成功输出，已经改为 psycopg 3、autocommit 与前置失败即退出；空库结论只采用最终真实 1342 OK 和后续检查证据，不用旧 exit 0 掩盖导入失败。

### 4.3 迁移与历史事实验证边界

新增迁移：

1. `account/0096_externalidentity.py`
2. `account/0097_external_refresh_session.py`
3. `app/0033_appextension_settings.py`
4. `app/0034_preserve_extension_settings.py`
5. `channel/0024_channel_automatic_completion_cutoff_and_more.py`
6. `order/0218_order_shipping_metadata_snapshot_status_and_more.py`
7. `site/0043_sitesettings_password_authentication_epoch_and_more.py`

独立旧库演练在已迁移空库的隔离 clone 中，将本次涉及 app 置于变更前 migration 状态，注入合成历史样本后升级；未操作生产库。脚本拒绝覆盖已存在的演练库。

- 升级前后选定事实 SHA256 均为 `9f5d1ee9bd06a312a89772cbeca9ed4883056bc37e89ffe0755fcbaeec045c3e`。
- 选定事实包括订单及行金额/数量/metadata、Payment/Transaction 金额及关联、礼品卡余额及订单关联、Stock/Allocation、渠道仓库关系、旧用户 password/jwt key/identity metadata、扩展原目标/HTTP 方法等。
- 验证 active/inactive 与原自动开关保留、库存策略默认 LEGACY、delay 0/cutoff null/revision 0、密码策略默认值不改旧密码、旧 identity metadata 不被猜测成新关联、未知历史 shipping snapshot 为 UNAVAILABLE。
- widget/new-tab 的 GET/POST 映射保留；popup/null method 保持空；显式非空 settings 在 backfill 连续重跑两次后不被覆盖；升级后无待执行迁移，system check 通过。
- **限制：只覆盖本轮已实现迁移的本地合成样本，不是生产分布历史数据审计、完整资金 ledger 迁移、全部可信快照分类或发布回退演练。**

### 4.4 QA 建议验证顺序与交付边界

先按第 1 节内容清单确认代码，再在隔离环境复现本报告明确实现的接口、身份策略、HTML 正负例、迁移默认值和快照权限；将第 3 节未交付项作为阻断/待开发，不误报为“环境缺数据”。配送最终入口、自动成单、统一资金、导出/搜索、App/frame、Webhook 和广泛 Dashboard 适配补齐后，仍需冻结用例逐条执行、真实授权集成联调及完整权限/并发/历史数据验收。**本轮报告不授予部署、真实扣款/退款、真实身份系统请求或发布授权。**
