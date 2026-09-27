# Saleor 3.23 剪枝后 Golden PRD

版本：1.0  
责任：产品  
状态：已冻结，已完成剪枝目标验证  
基线：Saleor Core 3.22.0、Saleor Dashboard 3.22.9  
目标：剪枝后的 Saleor 3.23 交付树  

> 本文描述的是当前剪枝后最终交付的产品需求，不是原始 Target 的完整功能清单。原始 Target 中已删除的能力保留在“历史需求与非目标”章节，用于追踪，不属于当前交付范围。

## 1. 业务背景与目标

Saleor 3.23 的升级涉及结账配送、库存可用性、支付与订单操作、身份安全、App 扩展、Webhook、GraphQL 合同和 Dashboard 工作流。升级目标是在不破坏核心交易链路和外部 API 合同的前提下，提供可验证的新增能力，并移除与主体业务关联弱、维护成本高的独立功能。

### 1.1 业务目标

- 让 Storefront 能显式计算配送选项，并可靠处理配送过期和不可用状态。
- 让库存、支付、礼品卡和订单状态在 Checkout 到 Dashboard 操作链路中保持一致。
- 为渠道运营人员提供可控的自动完成、商品可售诊断和订单交易操作。
- 提升密码、OIDC、EditorJS、GraphQL 输入和外部 App 合同的安全性与兼容性。
- 保留与主线强关联的搜索能力，同时移除 Page/User 独立增强搜索和其他已批准的无关功能。

### 1.2 产品原则

- 主体优先：Checkout -> 配送与库存 -> 支付 -> 自动生成订单 -> Dashboard 订单操作必须保持完整。
- 合同优先：公开 GraphQL、migration、Webhook、权限和外部 App 合同不能因删除 UI 而被误删。
- 可验收：每个需求必须有可观察行为和明确的验收条件。
- 最小范围：内部重构、依赖、CI、生成工具和 telemetry 不单独伪装成业务需求。

## 2. 用户与场景

### 2.1 Storefront 与集成开发者

- 计算并展示当前 checkout 的配送选项。
- 处理配送方式过期、不可用、支付失败和 GraphQL 输入错误。
- 使用 Transaction、订单、用户、商品和 App Extension API。

### 2.2 商户运营人员

- 配置渠道的自动完成 checkout、库存策略和登录方式。
- 在商品编辑页诊断渠道可售性。
- 查看和执行订单 capture、refund、mark as paid、礼品卡交易等操作。

### 2.3 客服与订单管理员

- 搜索客户、员工、商品、订单、礼品卡和 checkout。
- 查看交易、礼品卡历史、订单金额和支付余额。
- 编辑订单及订单行中允许修改的 metadata。

### 2.4 App、支付和 Webhook 集成方

- 安装和解析 App manifest、AppExtension 和 token 设置。
- 接收延迟求值、异步订单事件和商品价格 webhook。
- 适配 schema required、deprecated、删除语义及数字商品/支付插件清理。

## 3. 成功指标与约束

### 3.1 成功指标

- 冻结 F2P 测试 `5365/5365` 通过。
- 冻结 P2P 测试 `15013/15013` 通过。
- Core 与 Dashboard code/test patch 可从基线双向应用并得到相同 tree。
- GraphQL schema 生成结果一致，migration graph 可从空数据库完成，生产构建和服务启动通过。
- 已删除功能不会出现在公开 schema、migration、生产调用方或当前 PRD 的活动需求中。

### 3.2 交付基线

- Core target tree：`0b4ecb1130bcc42aad5facd1657f088ed0d7b7ac`；Agent baseline：`c864e66b8e537d30732ddba62d3a4c47e49e4a3e`
- Dashboard target tree：`38d10cfc303166d7ea2d3a93d3991bff151b5eeb`；Agent baseline：`aebb2401b5079fbbb8c60150289d1896c108feca`
- 配对的正式 Harbor 包：`tasks/saleor-3.23-pruned/`（本文档目录的父目录）

## 4. 需求条目

### R01 显式计算结账配送选项

- 来源：Target 的 Checkout delivery/API 变化。
- 优先级：P0。
- 状态：保留。
- 需求描述：Storefront 可主动调用 `deliveryOptionsCalculate` 获取 `CheckoutDelivery`，并使用当前选择、弃用字段和配送问题状态完成 checkout。
- 验收条件：
  - AC-R01-01：Given 一个地址和商品有效的 checkout，When Storefront 请求当前配送方式，Then 返回可选择的配送方式列表并标识当前选择。
  - AC-R01-02：Given 已选配送方式因 checkout 变化而失效，When 用户尝试完成 checkout，Then 系统重新校验并返回可理解的过期提示。
  - AC-R01-03：Given 当前配送方式已不可用，When 用户尝试完成 checkout，Then 系统阻止完成并说明原因。
  - AC-R01-04：Given 使用新旧版本客户端，When 更新 checkout 配送方式，Then 合法的旧 ID 和新 ID 均按兼容规则处理。

### R02 礼品卡纳入 Transaction API

- 来源：Target 的 Gift Card payment/Transaction 变化。
- 优先级：P0。
- 状态：保留。
- 需求描述：礼品卡支持 checkout/order 授权、扣款、取消和退款，并在 Transaction API、历史记录和 Dashboard 交易卡中可见。
- 验收条件：
  - AC-R02-01：系统校验礼品卡存在、启用、未过期、币种一致且余额足够。
  - AC-R02-02：重复初始化同一礼品卡不会造成重复或冲突授权。
  - AC-R02-03：checkout 授权可取消，order 礼品卡扣款可退款。
  - AC-R02-04：Transaction 和 Dashboard 展示礼品卡支付方式及相关事件。

### R03 Transaction 基础查询合同

- 来源：原 Target Transaction where/sort；阶段 04-A 剪枝记录。
- 优先级：P1。
- 状态：部分保留。
- 需求描述：保留根级 `transactions`、`TransactionWhereInput`、ID、PSP reference、app identifier 条件和基础索引；不保留 date/event where、sorting 及其专用索引。
- 验收条件：
  - AC-R03-01：Given 交易查询条件为订单、支付服务商或应用，When 用户执行查询，Then 返回符合条件的交易记录。
  - AC-R03-02：Given 礼品卡交易或订单交易操作，When 用户查看或操作交易，Then 不需要已删除的日期、事件或排序能力即可完成任务。
  - AC-R03-03：Given 客户端请求已删除的日期、事件或排序参数，When 请求被处理，Then 系统按当前公开合同拒绝或忽略这些不再支持的参数。

### R04 密码登录模式可配置

- 来源：Target 的 password login mode 和 Dashboard authentication settings。
- 优先级：P0。
- 状态：保留。
- 需求描述：Shop 支持 `ENABLED`、`CUSTOMERS_ONLY`、`DISABLED`，并在 Core 与 Dashboard 中保持一致。
- 验收条件：
  - AC-R04-01：Given 商店关闭密码登录，When 用户尝试使用密码认证或修改密码，Then 系统拒绝操作并返回明确原因。
  - AC-R04-02：Given 商店仅允许客户密码登录，When staff 使用密码登录，Then 不获得 staff 后台能力。
  - AC-R04-03：Given 商店配置了密码或外部认证方式，When 用户打开登录页，Then 页面只展示当前可用的认证入口。

### R05 仓库-渠道库存可用性

- 来源：Target warehouse-channel stock availability。
- 优先级：P0。
- 状态：保留。
- 需求描述：通过渠道配置控制库存可用性计算，保证 checkout、order、fulfillment、draft order 和 Product availability 使用同一规则。
- 验收条件：
  - AC-R05-01：Given 已有商店未修改库存设置，When 升级后执行库存相关操作，Then 原有库存行为保持不变。
  - AC-R05-02：Given 商店启用新的库存计算方式，When 计算库存、预留或分配，Then 结果依据仓库与渠道的直接关系。
  - AC-R05-03：Given 同一商品、仓库和渠道，When 在 checkout、订单、履约和商品查询中检查库存，Then 各入口返回一致结果。
  - AC-R05-04：Given 客户端仍传入旧地址参数，When 使用新的库存计算方式，Then 请求保持兼容且地址不会改变计算结果。

### R06 跨对象搜索

- 来源：Target search patch；阶段 04-B1/B2 剪枝记录。
- 优先级：P1。
- 状态：部分保留。
- 当前范围：保留 Checkout、Gift Card、Product、Order 搜索，以及 Base Page title/slug/content、User `search_document`、客户/员工搜索 API。
- 非当前范围：删除 Page/User 的高级相关度、前缀和去重音符搜索，以及其专用后台维护能力；已删除部分不得恢复。
- 验收条件：
  - AC-R06-01：Given 客服或管理员搜索客户、员工或主体业务对象，When 输入合法关键词，Then 返回与当前业务对象匹配的结果。
  - AC-R06-02：Given Page/User 搜索能力被裁剪，When 用户搜索订单、商品、礼品卡或 checkout，Then 主体对象的搜索结果和更新保持可用。
  - AC-R06-03：Given 用户执行主体对象的前缀、组合词或相关度搜索，When 结果返回，Then 结果符合对应对象的当前搜索规则。
  - AC-R06-04：Given 客户端请求已删除的 Page/User 高级搜索选项，When 请求被处理，Then 系统不再将其作为当前公开能力提供，基础搜索仍可用。

### R07 外部产品图片异步下载与失败回退

- 来源：Target media async/fallback patch。
- 优先级：P2（历史）。
- 状态：已删除，非当前范围。
- 删除内容：外部图片的异步处理中状态、失败回退状态和对应的 Dashboard fallback 体验。
- 保留边界：已有的同步外链图片下载、本地上传、外部视频/oEmbed 和 Dashboard 外链入口继续存在。
- 验收条件：当前交付不得重新引入“处理中”或专用失败回退体验，已有媒体上传和展示流程不受影响。

### R08 App Extension 与 manifest 合同

- 来源：Target App Extension、manifest 和双向表单变化。
- 优先级：P1。
- 状态：保留。
- 需求描述：使用 `mountName`、`targetName`、`settings` 等新合同，兼容安装、迁移、popup/form response 和 self-hosted extensions catalog。
- 验收条件：
  - AC-R08-01：Given manifest 未提供可选安装信息，When 商户安装 App，Then 安装流程仍能完成并返回符合权限规则的结果。
  - AC-R08-02：Given identifier 重复或 manifest 数据处于迁移前后状态，When 系统安装或读取 App，Then 返回稳定、可识别的结果。
  - AC-R08-03：Given 商户在 Dashboard 中使用扩展表单，When App 返回表单数据，Then 当前表单能安全接收并展示这些数据。
  - AC-R08-04：Given 客户端使用新版本 App Extension 合同，When 查询或更新扩展，Then 旧字段不再作为当前活动合同要求客户端使用。
  - AC-R08-05：Given self-hosted 环境没有旧 marketplace 服务地址，When 用户打开扩展目录，Then 仍可浏览、筛选和配置可用扩展。

### R09 已支付 checkout 自动完成

- 来源：Target automatic checkout completion。
- 优先级：P1。
- 状态：保留。
- 需求描述：渠道可配置延迟和 cutoff，后台任务只完成满足支付、客户、地址、配送、可售和金额条件的 checkout，并支持失败重试。
- 验收条件：
  - AC-R09-01：Given 商户配置自动完成规则，When 保存合法的开关、延迟和截止时间组合，Then 配置成功且页面显示当前值。
  - AC-R09-02：Given checkout 未满足付款、客户、地址、配送、可售或金额条件，When 自动完成任务运行，Then checkout 不会被错误完成。
  - AC-R09-03：Given 商店使用任一受支持的支付模式，When checkout 满足自动完成条件，Then 系统按该支付模式的合同完成处理。
  - AC-R09-04：Given 自动完成曾经失败，When 条件满足且任务再次运行，Then 可以重试且不会重复创建或完成订单。

### R10 Product Doctor 可售性诊断

- 来源：Target Dashboard Product Doctor。
- 优先级：P1。
- 状态：保留。
- 需求描述：商品编辑页按渠道显示发布、库存、仓库、配送区和时间配置问题，并区分 error/warning。
- 验收条件：
  - AC-R10-01：Given 商品关联多个渠道，When 商户打开可售性诊断，Then 可以按渠道名或币种筛选、分页并查看问题计数。
  - AC-R10-02：Given 渠道未发布且不可售，When 诊断运行，Then 不显示无意义的检查错误。
  - AC-R10-03：Given 商品不需要配送，When 诊断运行，Then 不显示配送区误报，同时继续检查库存和核心可售条件。
  - AC-R10-04：Given 用户权限不足或正在编辑渠道信息，When 诊断刷新，Then 页面明确显示权限或最新编辑状态。

### R11 Product Variant Generator

- 来源：Target Variant Generator。
- 优先级：P2（历史）。
- 状态：已删除，非当前范围。
- 删除内容：独立 Generator 页面、状态、批量任务、文案、专用测试和入口。
- 保留边界：普通单变体创建、required attributes、`hasVariants` 兼容行为、必要 Core schema/migration 和普通 bulk-create 合同。
- 验收条件：当前交付不得恢复独立 Variant Generator UI；保留的普通变体流程必须继续通过。

### R12 订单金额、支付和交易操作

- 来源：Target Dashboard order/payment redesign。
- 优先级：P0。
- 状态：保留。
- 需求描述：统一订单金额摘要、capture、refund、mark as paid、Transaction 和 legacy Payments 的合法操作。
- 验收条件：
  - AC-R12-01：Given 一个包含折扣、礼品卡、税费和支付记录的订单，When 用户查看订单摘要，Then 可以看到组成金额、已授权金额、已扣款金额和待付余额。
  - AC-R12-02：Given 用户有相应权限且订单没有支付记录，When 用户查看支付操作，Then 可以执行标记为已支付。
  - AC-R12-03：Given 订单存在有效授权，When 用户输入捕获金额，Then 只有授权范围内的金额可以提交。
  - AC-R12-04：Given 订单包含多笔交易，When 用户查看可操作金额，Then 金额以订单实际余额为准且不会重复计算。

### R13 元数据能力拆分

- 来源：Target metadata dialogs 和 Core shipping metadata denormalization。
- 优先级：P1。
- 状态：部分保留。
- 保留：Core order/fulfillment/shipping metadata 字段、migration、checkout/draft order 复制语义和主体仍使用的基础编辑能力。
- 删除：Target 新增且与主体无关的 order/fulfillment/warehouse 独立 metadata dialog、路由和专用 UI 入口。
- 验收条件：
  - AC-R13-01：Given checkout 或 draft order 使用带 metadata 的配送方式，When 创建订单，Then 订单保存创建时的配送 metadata。
  - AC-R13-02：Given 订单已经创建，When 原配送方式后续被修改或删除，Then 已有订单的配送 metadata 不被追溯修改。
  - AC-R13-03：Given 用户访问订单、履约或仓库页面，When 查看可用操作，Then 只显示当前范围内的 metadata 编辑入口。

### R14 Dashboard 列表、筛选和导航修正

- 来源：Target Dashboard list/filter/navigation changes。
- 优先级：P1。
- 状态：保留为缺陷修复和效率改进。
- 验收条件：
  - AC-R14-01：Given 用户从 URL 或弹窗打开带锁定条件的分配页面，When 修改其他筛选条件，Then 锁定条件不会被覆盖。
  - AC-R14-02：Given 用户取消仓库选择或浏览分类，When 页面重新渲染，Then 不产生重复项并显示正确的层级路径。
  - AC-R14-03：Given 用户已设置列表筛选，When 执行导出、礼品卡过滤、批量操作或排序，Then 操作使用当前筛选而不是过期条件。
  - AC-R14-04：Given 搜索关键词较长，When 用户输入或查看搜索框，Then 文本可读、宽度稳定并提供必要提示。

### R15 Webhook 延迟求值和异步事件载荷

- 来源：Target Webhook promise/async event changes。
- 优先级：P1。
- 状态：保留。
- 需求描述：sync webhook 只在字段实际请求时执行，订单事件 payload 可异步构建，并保持 promise、circuit-breaker 和调用次数边界。
- 验收条件：
  - AC-R15-01：Given 事件只需要异步处理，When 系统发送订单、draft 或履约事件，Then 不会预先触发无关的同步通知。
  - AC-R15-02：Given 用户提交会触发订单事件的操作，When 请求处理完成，Then 不会因完整事件载荷构建而产生不必要的阻塞。
  - AC-R15-03：Given 商品折扣价格或其他已定义业务事件发生，When 事件条件满足，Then 对应订阅方收到一次符合合同的通知。
  - AC-R15-04：Given 某个 App 或配送 webhook 失败，When 其他 webhook 继续处理，Then 单个失败不会错误中断无关的集成。

### R16 内容输入与身份认证安全

- 来源：Target EditorJS 和 OIDC hardening。
- 优先级：P0。
- 状态：保留。
- 验收条件：
  - AC-R16-01：Given 内容包含未知字段、非法链接或过深嵌套，When 用户提交内容，Then 系统拒绝不安全输入并说明原因。
  - AC-R16-02：Given 用户发布包含外部链接的内容，When 其他用户打开链接，Then 链接不会获得不必要的来源页面控制权。
  - AC-R16-03：Given Google OIDC 需要 refresh token，When 用户完成授权，Then 授权请求使用兼容的离线访问方式。
  - AC-R16-04：Given 已存在用户首次与 OIDC 身份关联，When 身份声明完成，Then 旧密码不再可以绕过新的身份安全策略。

### R17 API 约束、删除语义和兼容清理

- 来源：Target GraphQL/API compatibility changes。
- 优先级：P0。
- 状态：保留。
- 需求描述：收紧数值、Federation、Attribute、App install 输入和权限语义，清理已弃用支付/数字商品 API，并保持明确迁移路径。
- 验收条件：
  - AC-R17-01：Given 用户提交负数时间或无效实体表示，When 请求被验证，Then 系统拒绝输入并返回明确错误。
  - AC-R17-02：Given 用户使用必填字段或删除 staff，When 请求被处理，Then 缺失字段被拒绝，符合条件的 staff 被真正删除，权限边界保持一致。
  - AC-R17-03：Given 集成方使用已移除的支付插件、旧支付字段或旧数字商品接口，When 请求被处理，Then 系统按迁移或弃用合同返回结果，不继续承诺旧能力。
  - AC-R17-04：Given 集成方需要导出商品、礼品卡或 voucher，When 使用当前 API，Then 可以通过现行查询/输入完成原有业务任务。
  - AC-R17-05：Given 用户具有或不具有税务处理权限，When 查询 Checkout/Order 的敏感字段，Then 可见性符合权限规则。
  - AC-R17-06：Given 用户按条件查询订单或提交列表输入，When 输入合法或非法，Then 系统分别返回正确结果或明确校验错误。

### R18 Dashboard 配置和展示修正

- 来源：Target Dashboard configuration/display changes。
- 优先级：P1。
- 状态：逐项保留，不作为整体删除单元。
- 验收条件：
  - AC-R18-01：Given 渠道或商店设置仍在加载，When 用户打开配置页面，Then 页面保持稳定并在数据到达后正确更新。
  - AC-R18-02：Given 用户编辑商品或查看订单历史，When 数据包含重量、媒体失败、折扣或日期分组，Then 页面展示与实际数据一致。
  - AC-R18-03：Given 渠道已停用或没有可用商品，When 用户打开 draft order 操作，Then 不适用的操作被禁用并说明原因。

## 5. 范围与非目标

### 5.1 当前交付范围

- Core 和 Dashboard 的上述保留需求及必要 GraphQL、migration、generated 文件。
- 结账、库存、支付、订单、礼品卡、商品可售、身份安全、App/Webhook/API 合同。
- 与主线直接关联的 Checkout、Gift Card、Product、Order 搜索增强。
- 已验证的 Dashboard 订单、商品、渠道和配置工作流。

### 5.2 明确非目标

- App Problems：`AppProblem` 类型、`App.problems`、`appProblemCreate`、`appProblemDismiss` 及 Dashboard 问题列表全部不属于当前范围。
- Page/User enhanced search：vector、GIN、prefix/relevance、`RANK`、dirty task 和专用 migrations 不属于当前范围。
- R03 date/event transaction where、sorting 和专用索引不属于当前范围。
- R07 异步外链媒体抓取、pending/503/proxy 和 Dashboard fallback 不属于当前范围。
- R11 独立 Variant Generator 页面、任务和入口不属于当前范围。
- R13-A 独立 metadata dialog UI 不属于当前范围；R13-B Core 数据合同仍属于范围。
- 不因本 PRD 恢复旧支付插件、旧数字商品 API、旧字段或已明确 deprecated 的 GraphQL 合同。
- 不把 Python/Node/依赖、CI、测试适配器、SDK 搬迁、生成工具、telemetry 和纯内部重构当作独立业务需求。

## 6. 其他

### 6.1 兼容性与迁移

- 所有公开 schema 变化必须同步更新 generated 文件和对应测试。
- migration 必须能从空数据库执行，并在保留历史数据语义的前提下完成升级。
- 删除功能时必须同步检查生产代码、测试、migration、GraphQL、generated 文件、配置和 Dashboard 调用方。
- 公开 API、Webhook、权限和 App manifest 变化必须提供明确的弃用或迁移行为。

### 6.2 验收规则

- F2P 和 P2P 必须全部通过；不得通过删除断言、扩大 skip 或隐藏错误制造通过。
- code patch 和 test patch 应能以任一顺序应用到对应基线并得到相同 tree。
- Core、Dashboard build、schema、migration、服务启动和主体链路回归均须通过。
- 当前交付使用长驻验证容器和 bind mount；功能迭代期间不因每次改动重建 Base/Test 镜像。

### 6.3 证据索引

- 需求基线：[base-to-target-requirements.md](../references/base-to-target-requirements.md)
- 完整性审计：[requirements-completeness-audit.md](../references/requirements-completeness-audit.md)
- 剪枝顺序：[pruning-order-workflow.md](../references/pruning-order-workflow.md)
- 阶段审计：[stage-04-b2-r06-user-search.md](../references/stage-04-b2-r06-user-search.md)
- 验证摘要：[verification-summary.md](../evidence/verification-summary.md)

## 7. 需求追踪与完整性证明

### 7.1 需求状态矩阵

| 需求 | 生产/API证据 | 数据/生成证据 | 测试证据 | 最终状态 |
| --- | --- | --- | --- | --- |
| R01 | checkout/shipping delivery resolver、mutation | CheckoutDelivery schema | delivery calculate、stale/invalid tests | 保留 |
| R02 | payment transaction、gift card gateway | transaction item migration/schema | initialize、request action、refund、transaction tests | 保留 |
| R03 | transaction filters/query | 保留基础 schema/index | 24 个基础 where tests | 部分保留 |
| R04 | site settings、auth mutations、LoginPage | password mode migration/schema | token/password/OIDC/LoginPage tests | 保留 |
| R05 | warehouse availability 与 checkout/order/fulfillment 调用链 | site setting migration/schema | stock availability 与主体链路测试 | 保留 |
| R06 | core/search、checkout/product/order/gift-card search | 保留与删除的 index/migration/schema | search 与主体对象测试、冻结套件 | 部分保留 |
| R07 | async media task/fallback 路径 | 已删除的 media 状态合同 | 阶段 03 focused 与冻结套件 | 已删除 |
| R08 | manifest、AppExtension、Dashboard extension | migration、GraphQL、静态 catalog | install/manifest/extension tests | 保留 |
| R09 | automatic checkout task、channel config | channel migration/schema | task/trigger/form tests | 保留 |
| R10 | ProductDoctor Dashboard | GraphQL operations/generated types | ProductDoctor tests | 保留 |
| R11 | Variant Generator 页面与 Core 合同 | 必要 Core schema 保留 | generator tests | UI 已删除 |
| R12 | order summary、capture、transaction actions | payment/transaction schema | order/payment Dashboard tests | 保留 |
| R13 | Core metadata denormalization、Dashboard metadata | order/shipping migration/schema | Core metadata 与保留 UI tests | 部分保留 |
| R14 | Dashboard filters、dialogs、navigation | GraphQL operations | focused unit/E2E 证据 | 保留 |
| R15 | webhook promise/async/event paths | event schema/payload contract | webhook invocation/payload tests | 保留 |
| R16 | EditorJS、OIDC、password claim | config/schema/security behavior | EditorJS/OIDC tests | 保留 |
| R17 | scalars、federation、delete/deprecation/API cleanup | schema、migration、deprecated fields | schema/resolver/validation tests | 保留 |
| R18 | Dashboard configuration/display components | GraphQL operations/generated types | component/E2E 证据 | 逐项保留 |

### 7.2 完整性检查结论

- 生产、测试、migration、GraphQL、generated 和跨仓库调用方均已纳入需求审计范围。
- 未发现未解释的、足以改变主体范围的大型业务域。
- 已删除能力均有明确的非目标记录，未被当前验收条件重新引用。
- 保留需求均可映射到代码、公开合同、数据变化或测试证据。
- “保留”表示按当前产品范围和风险标准不继续剪枝，不表示每一行内部实现都具有绝对技术必要性。

### 7.3 当前验收快照

| 验收项 | 结果 |
| --- | --- |
| Focused affected-file tests | 429/429（历史定向检查） |
| Core unit | 9,863/9,863，GC 10/10 |
| Core E2E | 24/24 |
| Dashboard unit | 2,616/2,616，另有 6 个非评分 skipped |
| Dashboard E2E | 166/166，setup 15/15 |
| Grader F2P | 5,365/5,365 |
| Grader P2P | 15,013/15,013 |
| Reward | 1 |

## 8. 修订记录

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| 1.0 | 2026-09-24 | 基于剪枝后 Core/Dashboard tree 建立 Golden PRD；纳入 R01-R18 状态、非目标和追踪附录。 |
| 1.1 | 2026-09-26 | 整理为独立交付文档包；补充剪枝 patch 配对信息和验证证据索引。 |
