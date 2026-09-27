# 无关功能剪枝顺序计划

> 本文是剪枝过程的历史执行计划和留痕。阶段记录可以包含已删除需求及其测试处理；当前交付需求只以 `../PRD/prd-golden.md` 为准。

## 1. 计划状态

- 基线：上一轮已验收的 App Problems 剪枝树
- 需求依据：`base-to-target-requirements.md` 及 `requirements-completeness-audit.md`
- 执行模板：`/home/yang/task/templates/feature-pruning-workflow.md`
- 当前状态：阶段 01 R13-A、阶段 02 R11、阶段 03 R07、阶段 04-A R03、阶段 04-B1 R06 Page 搜索、阶段 04-B2 R06 User 搜索均已通过冻结 F2P/P2P 验收；阶段 04 已结束，剩余 R06 Checkout、Gift Card、Product、Order 搜索增强作为业务主线保留，不再继续剪枝
- 验收标准：冻结的 F2P/P2P 全部通过；名单外测试不改变本任务结论

本计划不是“按 R 编号全部删除”。每个 R 先拆成可独立验证的子功能；无法证明与主体无关的部分暂不删除。

## 2. 主体和不可删除边界

主体按以下链路定义：

`Checkout -> 配送与库存 -> 支付 -> 自动生成订单 -> Dashboard 订单操作`

默认保留：

- R01 Checkout delivery、配送过期/不可用校验及相关 API 合同
- R02 礼品卡 Transaction 支付、退款、交易事件和订单展示
- R05 库存可用性及其 checkout/order/fulfillment 调用链
- R09 已支付 checkout 自动完成及必要的重试/截止时间逻辑
- R10 Product Doctor 与库存/可售性关联部分
- R12 Core 支付/订单交易合同；只对明确独立的 Dashboard 展示做拆分判断

以下变化不作为普通无关功能删除目标：

- R04/R16 的密码安全、OIDC、EditorJS 等安全行为
- 并发、死锁、缓存、数据库副本等待、任务重试等可靠性修复
- Adyen/NP Atobarai、旧 digital-content API 等兼容清理
- R14 缺陷修复，除非能证明是独立新增入口且不承担回归保护
- R08-A/B、R15-A、R17-A 的外部安装、Webhook、GraphQL 合同

## 3. 推荐删除顺序

### 阶段 00：基线锁定（已完成）

**App Problems（历史 R06，已排除）**

保留上一轮交付作为本轮父快照。重新计算父树 hash、patch hash 和 F2P/P2P 基线，不重新套用未裁剪 Target。

### 阶段 01：Dashboard 纯叶子 UI

**候选：R13-A metadata dialogs / 独立 metadata 配置 UI**

- 范围：只删除不影响订单、商品和主体流程的 Dashboard 弹窗、路由、hook、文案、组件测试和生成类型。
- 保留：R13-B shipping metadata denormalization、订单持久化字段和主体仍读取的 metadata API。
- 选择理由：入口和调用方集中在 Dashboard，能先验证“共享 Core 合同不能随 UI 一起删除”。
- 风险：中低；共享 metadata 文件不能整文件删除。
- 完成门槛：Dashboard build/typecheck、受影响 F2P/P2P、schema/migration 静态核对。

**执行记录：R13-A（已验收）**

- 已删 Target 新增的 order/fulfillment/warehouse metadata dialog 和独立 Ripple/路由入口。
- 已恢复 Base 中 order details inline metadata 与 order-line metadata dialog；保留共享组件中仍被主体使用的能力。
- 未修改 Core、migration、GraphQL schema 或 R13-B shipping metadata denormalization。
- 已通过 Dashboard TypeScript check 和 4 个 metadata Jest suites（36 tests）；ESLint 0 errors、84 warnings。冻结 F2P/P2P 定向运行通过：F2P 5,882/5,882、P2P 7,026/7,026，reward=1。Core GraphQL schema、migration 与 R13-B shipping metadata 合同保留。
- Dashboard E2E 使用干净验证容器完成 fixtures seed 后运行。冻结的 166 个 dash-e2e ID 全部通过；第一次定向运行因 `SALEOR_95` 标题冒号空格格式差异漏选 1 个 ID，修正 selector 后单独运行该 ID 并纳入报告。最初未 seed 的整套尝试作废，不计验收。
- Core unit JUnit 合并保留 10 个 garbage-collection case 的 `@garbage_collection` 身份后重新评分；此前 grader 将其当成缺失 ID，实际测试均通过。该标识修正已加入定向 runner。

**候选：R18 中确认的纯展示/配置叶子**

- 只有在影响面清单证明没有 Core/API/持久化依赖后才进入本阶段。
- 每个叶子单独建立记录，不把 R18 整体一次性删除。

### 阶段 02：独立 Dashboard 业务模块

**R11 Variant Generator 及其 Dashboard 入口**

- 先拆出 required attributes、`hasVariants` 弃用和 Core 必需 schema 合同。
- 只删除 Variant Generator 独立入口、状态、任务、页面、测试、文案和仅供该入口使用的生成符号。
- 若 Core 字段仍被主体或兼容客户端使用，保留字段和 migration，不以 UI 删除为理由删除。
- 风险：中；涉及属性模型、GraphQL 和多语言资源。
- 完成门槛：GraphQL schema 生成、migration graph、Dashboard 生产构建、相关 F2P/P2P。

**执行记录：R11（已验收）**

- 删除 Variant Generator 独立组件、入口、状态、批量处理接入、Ripple、文案、locale、changelog 和专用工具测试。
- 保留普通单变体创建、required attributes、`hasVariants` 兼容行为、Core schema/migration 及普通 datagrid 所需的 bulk-create mutation。
- 阶段增量为 35 个文件、68 行新增和 4,334 行删除；输出 Dashboard tree 为 `584b30aca6f25b0ed44622b3040e782388fe5914`。
- Dashboard generate、message extraction、source typecheck 和 production build 通过。累计 patch 两种应用顺序得到相同 tree。
- 从 F2P 删除 33 个仅验证 Generator 的 ID。最终 F2P `5,849/5,849`、P2P `7,026/7,026`，`reward=1`。
- 完整影响面、失败尝试和报告位置见 `references/stage-02-r11-variant-generator.md`。

### 阶段 03：跨仓库但边界清晰的媒体能力

**R07 外部产品图片异步下载与失败回退**

- 删除前先确认主体商品创建和本地媒体上传不依赖异步外链路径。
- 若删除：同步清理 Core task/provider/503 状态、媒体模型专用字段、Dashboard fallback 组件、测试 fixture、HTTP cassette 和生成 schema。
- 保留商品媒体主链、本地存储和主体商品页面。
- 风险：中高；属于 Core + Dashboard 的用户可见合同，必须做 API/状态码和生成文件审计。

**执行记录：R07（已验收）**

- 确认 `mediaUrl` 和同步外链图片下载在 Base 已存在；保留 `productMediaCreate`、`productBulkCreate`、本地上传、外部视频/oEmbed 和 Dashboard 外链上传入口。
- 删除异步抓取 task/queue、pending IMAGE `external_url` 状态、thumbnail/original 503 与原图 proxy，以及 Dashboard `MediaWithFallback`、Story 和文案。
- 本阶段无 migration 和 GraphQL schema 合同变化。Core/Dashboard 生成、typecheck、build、受影响测试、migration 和服务启动检查均通过。
- 阶段增量：Core 22 个文件（350 additions、1,292 deletions），Dashboard 7 个文件（3 additions、148 deletions）。输出 tree 分别为 `4638d44447beff6a1d57cc2fa7d2997b31f56365` 和 `713d53f9eca6a6084e59b6a56056d2285db260fc`。
- 从 F2P 删除 78 个、从 P2P 删除 5 个仅验证 R07 的 ID。最终 F2P `5,771/5,771`、P2P `7,021/7,021`，`reward=1`。
- Dashboard E2E 首轮仅 `SALEOR_44` 因 loading 按钮 DOM 替换/点击被拦截而超时；该测试与 R07 无关，标准 seed 后定向重跑通过。没有改测试、断言或超时。
- 完整影响面、patch hash 和验证证据见 `references/stage-03-r07-external-media.md`。

### 阶段 04：独立查询增强

**R03 Transaction where/sort**

- 先确认主体支付查询只需要基础 transaction 查询；若订单支付操作依赖筛选字段，则拆分保留。
- 可删除范围为新增过滤/排序入口、resolver 分支、索引/测试和 Dashboard 专用调用方。
- 风险：中；主要是 GraphQL 合同和查询过滤，不能误删 R02 的支付详情。

**执行记录：R03（阶段 04-A，已验收）**

- 删除 `createdAt`、`modifiedAt`、transaction event type/date where、`sortBy`、对应 sorter、四个专用索引和叶子 migration `payment.0072`。
- 保留根级 `transactions`、`TransactionWhereInput`、ID/PSP/app 条件和基础索引；R02/R12 支付及 Dashboard 订单交易能力不变。
- Core 增量 10 个文件、4 行新增、1,181 行删除；输出 tree 为 `f3bef3f74c0a614c24a94d575a3dca6f55174d03`。Dashboard 无源码变化，tree 仍为 `713d53f9eca6a6084e59b6a56056d2285db260fc`。
- 从 F2P 删除 18 个 R03 专用 ID，P2P 不变。最终 F2P `5,753/5,753`、P2P `7,021/7,021`，`reward=1`。
- schema、空库 migration、生产构建、保留的 24 个基础 transaction where 测试和全部冻结套件通过。完整记录见 `references/stage-04-r03-transaction-query.md`。

**R06 跨对象增强搜索**

- 这是高工作量模块，已按对象域完成 Page/User 边界拆分；剩余对象域与主体链路直接相连。
- 先拆 search vector、dirty flag、后台任务和数据库 migration；主体仍用到的订单/商品搜索能力不能整包删除。
- 风险：高；跨多个模型、任务、索引和 GraphQL API，必须按对象域分轮。
- 状态：阶段 04-B1 Page、阶段 04-B2 User 子域已完成；经边界复核，Checkout、Gift Card、Product、Order 搜索增强批准保留，阶段 04 在当前验收树关闭，不再建立 04-B3。

**执行记录：R06 Page 搜索（阶段 04-B1，已验收）**

- 删除 Page vector/dirty/task、属性与 PageType dirty 传播、`RANK`、四个尾部 migrations 和专用测试；恢复 Base title/slug/content 搜索。
- 保留 `pages(search:)`、Page CRUD/EditorJS，以及 Product 搜索对 Page reference title 的索引与四个相关 F2P。
- Core 增量 43 个文件、133 additions、1,498 deletions；输出 tree `ea83176de24d437bbd11df0abbbb985d98849052`。Dashboard tree 不变。
- 从 F2P 删除 39 个，P2P 不变；最终 F2P `5,714/5,714`、P2P `7,021/7,021`、`reward=1`。
- schema、空库 migration、246 个 focused tests 和全部冻结套件通过。完整记录见 `references/stage-04-b1-r06-page-search.md`。

**执行记录：R06 User 搜索（阶段 04-B2，已验收）**

- 删除 User vector/GIN/migrations `0096`-`0098`、prefix/relevance 和 `RANK`；恢复 Base `search_document`。
- 保留客户/员工 search API、Dashboard 调用方、账户/OIDC/客户属性，以及 Order 仍使用的 email vector helper。
- Core 增量 46 个文件、332 additions、487 deletions；输出 tree `479dacdbcd96e4864e692eb572104c70aefb65c8`。Dashboard tree 不变。
- 从 F2P 删除 56 个，P2P 不变；最终 F2P `5,658/5,658`、P2P `7,021/7,021`、`reward=1`。
- schema、空库 migration、429 个 focused tests 和全部冻结套件通过。完整记录见 `references/stage-04-b2-r06-user-search.md`。

**阶段 04 冻结决定**

- 已删除的 R03 Transaction 增强查询、R06 Page 搜索和 R06 User 搜索保持删除，不恢复。
- R06 Checkout、Gift Card、Product、Order 搜索分别关联结账、礼品卡支付、商品可售和订单操作，按“主体及强关联功能保留”标准不再剪枝。
- “保留”表示本次 PRD 范围内风险和关联性不足以支持继续删除，不主张每一行实现均具有绝对技术必要性。
- 最终冻结 Core commit/tree 为 `8d07e9510959f12d0a6e7ebf292a88caf14912c8` / `479dacdbcd96e4864e692eb572104c70aefb65c8`；Dashboard commit/tree 为 `05dea6f0fc8cbc8e4800ec25dff8bcfb3ae57d9f` / `713d53f9eca6a6084e59b6a56056d2285db260fc`。

### 阶段 05：跨仓库扩展生态

**R08 App Extension（仅在明确决定删除扩展生态时执行）**

- 必须同时审查 R08-A 安装/manifest 兼容和 R08-B self-hosted Explore Extensions 目录。
- 不能只删 Dashboard 双向表单，而把 Core manifest、migration 或旧字段残留在 schema 中。
- 删除顺序：Dashboard 入口/表单 -> Core runtime/manifest -> migration/schema/generated files -> 测试和目录资源。
- 风险：高；外部 App 合同和历史数据兼容，需单独冻结反向兼容测试。

### 阶段 06：Webhook 与 API 合同（默认保留）

**R15-A Webhook、R17-A GraphQL/API**

不建议作为普通无关功能剪枝。只有用户明确决定移除对应外部合同，才建立独立的 breaking-change 方案、迁移说明和反向契约测试；不得因为实现跨文件或测试数量多而删除。

## 4. 每阶段固定执行顺序

1. 从上一阶段已验收树创建只读父快照和本阶段工作树。
2. 生成候选功能影响面：生产、测试、migration、schema、生成文件、配置、跨仓库调用方。
3. 输出“保留/删除/拆分”结论；发现未映射项立即暂停并新增 `UNMAPPED-*`。
4. 修改生产代码，再同步处理测试、fixture、migration、schema 和生成文件。
5. 更新本轮 F2P/P2P 名单及 dropped 审计；不通过删断言、隐藏错误或扩大跳过范围制造通过。
6. 在长驻验证容器中执行完整性检查和冻结 F2P/P2P；功能迭代期间不重建 Base/Test 镜像。
7. 导出阶段增量 patch，并从原始 Base 重新导出累计 patch；验证两种 patch 应用顺序和 tree hash。
8. 只有 F2P/P2P 全通过后，固化父快照并进入下一阶段。

## 5. 每轮停止条件

出现以下任一情况，停止本轮并回退到父快照，不进入下一阶段：

- 主体链路测试失败，或共享 API/schema 被误删。
- migration graph、生成 GraphQL 或 production build 不一致。
- F2P/P2P 选中 ID 缺失、失败或非预期跳过。
- 发现功能实际属于安全、可靠性、兼容清理或主体依赖。
- patch 无法从父快照或原始 Base 稳定还原。

## 6. 预计交付记录

每个阶段都必须新增：

- 阶段影响面和保留边界记录
- 增量 code/test patch、累计 patch 及 SHA-256
- F2P/P2P 执行结果和 dropped 审计
- tree hash、schema/migration/build 检查结果
- `workflow.md` 中的实际操作、失败尝试和镜像复用/重建原因
