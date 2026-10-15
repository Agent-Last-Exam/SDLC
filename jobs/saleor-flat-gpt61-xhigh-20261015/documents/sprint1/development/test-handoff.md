# 提测报告：Saleor 3.23 结账、资金与商户运营一致性

版本：v1  
轮次：1  
依据：PRD v1；前端技术设计 v1；后端技术设计 v1；接口契约 v1；目标 schema v1  
阶段：sprint1/development；日期：2026-10-15

> **提测结论：交付开发代码及本地自测结果，存在未完成的 P0 业务闭环和失败门禁，不具备全量验收通过或直接生产发布条件。** 下表中的“已实现”指代码已落地及注明范围的本地验证，不表示所有冻结验收条件、真实外部集成和历史生产数据均已通过。没有提供上一轮 QA 报告、执行记录或修复计划，本轮不是对上一轮 QA 缺陷的关闭确认。

## 1. 提测版本

| 仓库 / 组件 | 代码版本或构建标识 | 代码位置 |
| --- | --- | --- |
| Saleor Core | 基线 `c864e66b8e537d30732ddba62d3a4c47e49e4a3e` + 本轮未提交工作树；工作树内容 SHA256 `0b374b02d19c08b7894c27133bd568f761323e697a18932fe5fe7239620d84c4`；277 个变更路径 | `/workspace/repos/saleor` |
| Saleor Dashboard | 基线 `aebb2401b5079fbbb8c60150289d1896c108feca` + 本轮未提交工作树；工作树内容 SHA256 `4601f5d52063a83302a191b027d515dd0cf5889d5b14fd107419e1a61b4c9228`；403 个变更路径 | `/workspace/repos/saleor-dashboard` |
| 代码定位清单 | `code-snapshot-manifest.json`：按仓库记录基线、所有变更/删除/新增路径、文件内容摘要及可执行标记；工作树 SHA256 基于该清单的规范 JSON，不是 Git commit 或部署版本 | `/workspace/artifacts/sprint1/development/code-snapshot-manifest.json` |
| Dashboard 本地生产构建 | 最终源码重新执行 generate → check-types → build；构建成功。仅本地构建，未发布、未部署；未创建 Sentry release 或上传 sourcemap | `/workspace/scratch/dashboard-build-delivery`；日志 `/workspace/scratch/dashboard-build-delivery.log` |
| GraphQL 合同 | Core runtime SDL 已生成到仓库；Dashboard 本地 schema 与 generated 客户端已更新。1,427 个命名类型/定义，字段/类型/参数/默认值/枚举基础比较 0 差异；包含 directive 的全量比较仍有 14 个定义差异，见 §3 | Core `saleor/graphql/schema.graphql`；Dashboard `schema.graphql`、`src/graphql/*.generated.ts` |

- 未创建新 commit、未 push、未创建 PR；由运行器保存代码快照。两个仓库 HEAD 仍为上列基线，不能只 checkout 基线而忽略工作树。
- 包版本仍为 Core **3.22.0**、Dashboard **3.22.9**。Saleor 3.23 是本次需求目标，不代表包版本或已运行环境已升级为 3.23。
- 依赖变更：Dashboard 显式依赖 `decimal.js@10.6.0`；离线 pnpm 规范化后的锁文件仅新增对应 importer 3 行，未整体升级依赖。使用既有 node_modules 加本地离线工具，没有做全新联网安装验证；没有新增 npm package-lock。
- 本次临时验证脚本、虚拟环境、安装缓存、测试数据库、测试缓存及构建产物均在 `/workspace/scratch/`；正式交付目录只保留选定验证证据副本及其索引。自动生成的本地 JWT 私钥已移出仓库，未输出其内容；生成缓存及旧 build 已移至 scratch。源代码和既有依赖目录链接检查未发现指向仓库外的符号链接；改动文件的私钥/AWS/GitHub token 模式检查无命中。这是有限模式检查，不是全面凭据审计。

## 2. 已完成功能

| 需求 | 完成情况 |
| --- | --- |
| R01 · 主动重算当前结账的配送选项 | 已实现显式配送重算入口及共享服务；读取当前结账、地址、商品、渠道与服务结果，成功确认选择失效后清除、不自动代选，计算失败保留原选择。Storefront 通过 API 使用，不另建前台产品；真实配送服务联调未执行。 |
| R02 · 更新选择与完成结账重新验证配送 | 部分完成。新旧配送标识及自提沿用适用类型，更新/人工与自动完成接入共享验证，失效拒绝；**实际 expiry 判断及部分完成错误的目标 enum 映射尚未闭环**。 |
| R03 · 渠道库存策略在查询、预留、订单和履约一致 | 已实现 `SHIPPING_ZONE`/`CHANNEL` 库存来源，与 allocationStrategy 分离；新策略只用当前渠道直接关联仓库，旧策略保留地址/配送区域行为。修复仓库解绑后仅允许履约该订单行自身已有 allocation，不借额外库存或 sibling allocation。真实 DB 正向/负向测试通过；全量历史履约批准/取消回归未覆盖。 |
| R04 · 商品编辑页按渠道诊断真实可售原因 | 部分完成。新增 Core 诊断及 Dashboard 商品上下文面板，包含渠道筛选、分页、错误/警告/不适用和当前结果保护；**active preorder 容量诊断尚未扣除完整 threshold/allocation/reservation**。 |
| R05 · 已支付结账按完整资格自动成单 | 部分完成。增加共享 completion record、人工/自动竞争保护、当前成功支付资格、逐结账执行及历史重复 token 阻断；两条成单路径同事务登记 ORDER_CREATED 事实。**lease 续租、所有资格变化入口、外部成功后的 reconciliation 及全部完成通知的耐久性未闭环**，不能承诺完整故障恢复与一次通知。 |
| R06 · 按渠道保存自动完成开关、延迟与 cutoff | 已实现配置和 CAS，默认关闭；延迟按严格超过判断，cutoff 按创建时间 inclusive 判断，与过期资金释放设置分离；Dashboard 展示单位/时间语义、冲突保留编辑、确认版本后更新缓存。设置生效不展示为订单已生成。 |
| R07 · 礼品卡统一初始化、授权与扣款 | 已实现内置礼品卡 TransactionItem 路径、持久动作账、余额/占用及币种/状态校验；同卡并发和 same-key 重放有真实双连接测试；历史扣卡生成可追溯审计映射，不再扣历史余额。外部 provider session 的 unknown 缺口见 §3。 |
| R08 · 礼品卡取消、退款、余额和事件对账 | 已实现新礼品卡路径取消/退款、额度约束、幂等及方式/事件展示，空 events 不误判请求失败。历史 synthetic gift-card transaction 是审计事实，**不支持用该 synthetic 对象执行退款**；历史资金对账需沿历史业务流程处理。 |
| R09 · 金额摘要和剩余待付统一口径 | 已实现 Core 权威摘要和 Dashboard 接入；当前 authorized/charged/captured 净额不再重复扣退款或已消耗授权，欠款按 `max(-totalBalance, 0)`，Transaction/Payment 分开处理，历史已扣卡与新卡支付区分。支持币种精度，不以客户端浮点重算覆盖 Core。旧计算回归仍有语义断言失败，未宣称兼容全绿。 |
| R10 · 人工收款、捕获和退款受状态及余额限制 | 部分完成。订单/交易动作按各自权限及当前余额校验，显式零拒绝、超额不裁剪；持久 key 绑定 actor/source/provider/action，same key 不同输入冲突，外部调用移出本地锁事务；Dashboard 区分受理/pending/最终成功。**session 无响应/非法响应及 failed-confirm 生命周期仍有真实缺陷**，见 D01/D02。 |
| R11 · 根级交易基础定位与受限分页 | 已实现单条及列表基础定位，订单/结账/transaction ID、PSP reference、App 标识及组合过滤，writer/object/App scope 校验和稳定有界分页；保留成功空结果/空事件。没有增加交易日期/事件筛选或专用排序。 |
| R12 · 主体增强搜索与 Page/User 基础搜索 | 已实现 Product/Order/GiftCard/Checkout 四主体 NFKC/casefold、AND/去重、带引号短语及未引号末词 prefix；短语不跨独立字段。Page/User 仍为基础搜索，未新增其高级向量、prefix、RANK 或专用维护能力。 |
| R13 · 搜索更新、分页和错误稳定 | 部分完成。四主体 dirty/revision、有界更新及 writer 快照，量化 rank key + PK 同用于排序/cursor/seek；原始长度和控制字符在 forms strip 之前校验。**cursor 只绑定搜索词 hash，不是完整 effective-scope fingerprint**；变更筛选/身份等上下文后复用游标的严格绑定未实现。 |
| R14 · 锁定条件、导出及批量使用同一范围 | 部分完成。新增范围合并/冲突工具、当前请求结果 guard、选择清理、显式 no-cache Query 导出、最新筛选快照及幂等 key；服务端 domain AND export 权限、worker/下载再授权、私有 no-store 文件和 Bearer blob 下载。**trusted-lock 的生产 caller 未接通，legacy FILTER/scalar 及部分 category ready 防线未完全收敛**，不能以工具单测代替入口验收。 |
| R15 · 选择器、层级导航与长搜索词 | 已实现候选 ID 去重、搜索/渠道/分配上下文失配时隐藏旧结果、分页防线和分类导航上下文；长词稳定布局、完整词查看及清除。新增 nullable search 保护避免合法 null 结果崩溃。部分 category 入口及浏览器层级往返还需 E2E。 |
| R16 · 密码认证三态统一生效 | 已实现 ENABLED/CUSTOMERS_ONLY/DISABLED、writer 读取、配置 CAS、generation/source guard，登录/重置/设置/修改及旧 token 相关路径限制；Dashboard 登录和配置读取同一策略。修复无默认渠道时 reset 的用户可枚举差异。最终新增整合测试通过；实际管理员/外部方式部署验证未执行。 |
| R17 · OIDC 合同与首次关联关闭旧密码旁路 | 已实现 Google offline 参数差异、稳定 issuer/subject 唯一关联、首次关联禁旧密码、refresh 返回后锁 User 重验撤销，避免 token/sensitive 日志。新增合同测试通过；**既有 BaseOIDC 116 项回归仍为 78 通过/38 失败**，没有真实 Google/其他 provider 联调。 |
| R18 · 富文本结构与链接安全 | 已实现 EditorJS 先结构验证再清理，固定 http/https/mailto/tel 与安全相对 URL，最大深度 10；未知/多余字段、危险 URL、超深整份拒绝。修复 `{}`/`[]`/空字符串被 blank/truthy 跳过的问题；五类真实 GraphQL mutation 非法输入后原文保持。Dashboard 同步校验并保留 dirty，不静默清理后假成功。 |
| R19 · App 当前合同与历史扩展 | 已实现 mountName/targetName/settings、settingsVersion CAS、identifier 活跃唯一性、安装必填和可选 tokenTargetUrl、新客户端与旧读取弃用标记；历史设置兼容迁移路径及授权检查已有代码/定点测试。未执行真实网络安装升级及生产历史扩展迁移演练。 |
| R20 · App 回应只更新当前表单 | 已实现 origin/source/frameId/requestId/contextVersion/ready/type 校验、同步 current guard、多 frame/过期/重复消息拒绝，商品/翻译 draft 合法写回。SUCCESS 不是 Core 保存成功；VALIDATION_ERROR 保留未保存预览和字段错误。协议与组件测试通过，浏览器跨 iframe E2E 未执行。 |
| R21 · 自托管扩展目录 | 已实现可配置目录、加载/合法空/网络或格式错误分态、只读与安装权限区分；安装状态以 Core 为准，不信任目录 installed 标志。App 列表分页合并，plugin 列表超过 100 时保守 unknown；目录 retry 不独立重试 Core installed 查询，仍需完善恢复体验。 |
| R22 · 按订阅解析与异步构建 | 部分完成。增加 BusinessEvent snapshot/outbox、选中字段规划、订单/草稿/履约后台构建边界及未构建状态；未捕获关系 fail closed，不回读当前关系伪装历史事实。**顶层 FragmentSpread、完整派生/特殊 payload shape、所有事件钩子和崩溃恢复尚未全覆盖**。 |
| R23 · delivery 独立失败与单条重试 | 部分完成。各 receiver 独立状态/载荷，失败不重发成功 receiver，成功审计保留，unsupported scheme 不误重试；折扣实质变化事件及源身份唯一约束已实现；Dashboard 保留失败告警和单条重试。**publication lost/PROCESSING lease 恢复缺失，另有旧 MessageGroupId 派发兼容回归失败**。 |
| R24 · 成单时配送 public/private 元数据快照 | 已实现结账及草稿完成两路径、订单/履约投影、deepcopy、私有权限和源修改/删除后历史不变；空历史保持稳定空，不用当前源值伪造。新增数据库测试覆盖快照与删除源场景；任意 Webhook 订阅关系快照仍受 D08 限制。 |
| R25 · 元数据基础读写和订单行内编辑 | 已实现 metadataBundle、单/批原子 CAS、public/private upsert/delete、父后子稳定锁序及订单行/变体当前编辑；保留必要基础 API，不新增订单/履约/仓库独立管理入口。**旧多 mutation metadata 保存路径没有统一成整体事务**，不能承诺这些 legacy 保存全部符合 AC-25-3。 |
| R26 · 公开输入及业务失败语义 | 已实现时长/时间/分页/cursor/Federation/null 项/属性输入及错误 ID 类型等边界、敏感错误收敛；通用保存确认 payload/errors/返回对象，不以 HTTP 200 判成功。205 项公开输入及跨模块回归通过。**部分 form/auth 缺结果路径仍返回空数组、部分完成错误 enum 映射未统一**，不能声明全公开入口已审计。 |
| R27 · 弃用、退出及当前客户端 | 已退出 Payment.partial、native DigitalContent 公开 API/HTTP 下载/自动数字配送及 Adyen、NP Atobarai 新调用注册；draft 旧 voucher 输入返回 MIGRATION_REQUIRED，当前 voucherCode 保留；Query 导出及旧 mutation 弃用、属性部分更新、App 安装必填、生成客户端已更新。空库和历史迁移验证范围见 §4；全量生产数据兼容及 exact SDL 仍有差异。 |
| R28 · 权限、员工真删除及敏感字段 | 已实现合法员工真删除、NOWAIT 争用拒绝重试，历史订单/资金保留；资金、导出、metadata、税务相关读取按各自权限与对象/channel/App scope 校验，不机械套统一权限。新增权限/并发用例通过；旧无 channel grant 的成功预期回归仍失败，未为变绿放宽权限。 |
| R29 · 当前上下文加载/保存/缓存 | 已实现 context/generation/editRevision、A→B→A 新 revision、精确提交快照、富文本同步 dirty 与 markSaved、迟到查询/保存保护；配置 CAS 成功版本确认才更新缓存，多步骤商品/媒体/metadata/translation 操作 await 并核验。严格类型与相关整合集通过，少数 legacy 返回合同未完全统一。 |
| R30 · 重量、媒体、金额日期与草稿资格 | 已实现 Decimal 来源单位换算、普通媒体错误语义、Core 金额、locale/timezone 日期分组、draft canFinalize 及当前渠道/可售/库存 gating；当前无交易权限/数据时不开放资金动作。单元/组件测试通过，普通媒体真实网络、浏览器草稿和库存全链路未实测。 |
| R31 · 排除独立增强但保留基础能力 | 未新增 App Problems、Page/User 高级搜索、交易日期/事件查询增强、异步抓图专用状态、独立变体生成器或独立元数据管理入口。保留 Apps 数字商品、普通变体/批量、上传/同步外链/oEmbed、基础搜索/交易定位、行内 metadata 与 Webhook 告警。基础能力的抽样回归不代表普通业务全量回归已通过。 |

实现对应 BD01—BD15、FD01—FD10、I01—I27；当前覆盖不是“全部合同完成”的声明。后续 QA 应以冻结 PRD/合同逐 AC 验收，尤其优先验证下列缺口。

## 3. 未完成项与已知问题

### 3.1 阻断发布的业务闭环与实现缺口

| 编号 | 关联需求 | 问题、影响及当前边界 |
| --- | --- | --- |
| D01 · 外部 session unknown 被误归失败 | R07/R10/R26 | `payment/session_actions.py` 调用的旧 `create_transaction_event_for_transaction_session` 在无响应/非法解析响应时仍可生成确定 FAILURE，随后释放 initialize 容量；这不满足“可能远端已发生”的 unknown 应保留占用。**真实未修复生产缺陷**；legacy process/generic action timeout 测试通过不覆盖此分支。不得在此状态自动重发或认定一定未扣款，需 reconciliation。 |
| D02 · failed confirm 及跨对象资金生命周期 | R05/R10 | failed confirm 目前只 settle 当前记录，旧 ACTION_REQUIRED process 占用清理不完整；正常非 action_required return 又可能将 prior 无差别标 succeeded。Checkout→Order source 转换竞争、完整异步 settlement 和审计通知幂等未全验。provider 远端去重仍依赖 provider 实际履约其 idempotency 合同。外部已成功但业务随后变化，仍可能留下成功款待人工/后台对账，不是完整回滚。 |
| D03 · 自动完成恢复与副作用不全耐久 | R05/R06/R23 | completion 固定 10 分钟 lease，无续租；资格 signature/version 尚未审计所有 discount/giftcard/listing/bulk/address 写入口。ORDER_CREATED 已同事务持久化，但本地 OrderEvent、用户计数、paid/confirmed、confirmation notification 等仍依赖 on_commit，不能保证进程崩溃后自动恢复或一次完成通知。 |
| D04 · 配送过期与错误码 | R02/R05/R26 | DELIVERY_METHOD_EXPIRED 尚无实际 expiry 判定；`orderCreateFromCheckout` 部分新增错误与目标错误 enum 的兼容映射待完善。不能用重新检查 availability 冒充服务有效期验证。 |
| D05 · preorder 诊断容量 | R04 | active preorder 诊断未完整扣除 threshold/allocation/reservation，可能将没有剩余预售容量的商品诊断为可售；诊断不得替代实际成交检查。 |
| D06 · trusted lock 与完整 cursor scope | R13/R14/R15 | trusted-lock 工具/Context 尚无生产 caller 接入，部分 legacy FILTER/scalar 重复语义与 category ready 防线未收敛。Core cursor 仅有搜索词 hash，未绑定完整 filter/where/channel/warehouse/actor/sort；不能宣称在变更 scope 后复用 cursor 仍有设计要求的拒绝语义。 |
| D07 · outbox 作业丢失/崩溃恢复 | R05/R22/R23 | 缺少“提交成功但 on_commit publication 丢失”的扫描补发，以及 PROCESSING worker 崩溃后的 lease/恢复；delivery 可停留等待/执行中。持久 BusinessEvent 和成功 receiver 不重发不等于完整恢复闭环。 |
| D08 · 订阅规划与快照覆盖 | R22/R23/R24 | subscription 顶层 FragmentSpread 未展开；nested event fragments 已有测试，但不替代顶层。selected relation、派生字段和 legacy 特殊 shape 覆盖不全，未捕获关系 fail closed，可能构建失败，不能保证任意合法订阅都成功。其他事件钩子的同事务捕获、删除前 capture 尚未全部审计。 |
| D09 · legacy 原子保存与返回合同 | R25/R26/R29 | 新 metadata bundle/bulk 是原子的；旧多 mutation 保存不能宣称整体原子。少数 form/auth 缺结果路径仍返回 `[]`，虽已有不清 dirty/不导航保护，严格可分支错误合同未全部统一。 |
| D10 · 历史资金及目录限制 | R08/R19/R21/R27 | 历史 synthetic 礼品卡只用于审计，不能用其执行新退款；生产历史异常数据需对账。plugin 目录超过 100 时保守 unknown；catalog retry 不独立 retry Core installed query。真实 provider/OIDC/Google/安装服务尚未联调。 |
| D11 · 私有导出部署前置 | R14/R27/R28 | csv0006 已让旧公共导出数据库引用失效，但不能撤回既有物理对象/旧 URL/CDN 缓存；**部署方必须清理旧 public export_files 对象和 CDN 并确认私有存储配置**。新签名 URL 仍需当前身份授权，不应配置成公开文件目录。 |
| D12 · 端到端及迁移验收不足 | 全局，尤其 R03/R05/R10/R17/R27 | 无已部署环境、浏览器 E2E、真实 Redis/Celery worker、真实资金/外部认证/配送服务验证；历史迁移仅隔离测试数据及定点函数测试，没有生产备份恢复、完整基线业务数据升级和回滚演练。不能直接上线后再默认这些闭环成立。 |

以上 D01—D09 涉及金额、成交、权限范围或历史/事件一致性，不能因新增测试全绿而作为已解决事项。本轮报告不承诺修复日期，也未授权降低冻结验收标准。

### 3.2 保留的失败门禁与旧回归

没有修改冻结 PRD、设计或测试基线，也没有以跳过/改旧业务断言方式将失败报告为通过。

| 检查/回归 | 实际结果 | 分类及说明 |
| --- | --- | --- |
| 资金混合回归 156 项 | **129 passed / 27 failed**；新增 50 项全部通过 | 旧 106 项中 79 通过/27 失败。9 项净额/pending 旧语义断言；1 项重复 live-App identifier fixture 触发唯一约束；4 项 capture/refund Decimal 字符串量化格式；2 项 markPaid 既有付款错误 code/field；10 项 markPaid 查询嵌套 transactions 缺独立 HANDLE_PAYMENTS（mutation 仍按 MANAGE_ORDERS）；1 项 Webhook 新 outbox 派发未保留旧 MessageGroupId。不是缺迁移列；未将全部失败认定为“测试过时”。日志 `financial-final.log`。 |
| BaseOIDC 116 项 | **78 passed / 38 failed** | 3 项旧 refresh wrapper 缺稳定身份、5 项 audience、15 项旧 raw-token/userinfo mock 身份不一致、13 项缺 issuer、1 项旧全局 JWKS cache key、1 项敏感日志断言。新增身份合同测试通过不抵消这些失败；未放宽 issuer/subject/audience 安全要求。日志 `identity-base-oidc-tests.log`。 |
| 既有 metadata/order 扩展回归 158 项（修复前批次） | **120 passed / 38 failed**；未整批重跑为全绿 | 其中 2 个 TransactionItem UUID token 查找及 1 个 deferred callback 身份上下文真实问题已修，后续新/旧定点通过；剩余分类为 28 项旧无 channel grant 成功预期、1 项退出 DigitalContent、4 项 draft 失败后仍写税价的旧预期、2 项 Redis 6379 不可用。最终新增整合集中的 metadata/order 用例通过，不等同于该旧批次全绿。 |
| Webhook 扩展 88 项（修复前批次） | **86 passed / 2 failed**；修后定点 **54 passed** | 原批次未整批重跑；后续新增整合集通过，不回写成“88 全部通过”。资金旧回归仍保留 MessageGroupId 兼容失败。 |
| Identity 扩展 152 项（修复前批次） | **149 passed / 3 failed**；修后原失败定点 **3 passed** | 2 项是 reset 无默认渠道隐私差异，1 项是 orderSettings 测试缺 channel grant fixture；修后定点通过，最终新增 551 整合集也覆盖对应新增模块。不是原单次 152 全绿。 |
| Dashboard 全仓 `npm run lint` | **退出 1：156 errors / 2,524 warnings** | 当时 156 errors 均定位于本轮未改文件（例如 onboarding refs/render/effect 规则）；未另建干净 baseline 运行同一门禁，所以不声称全部已证明为基线。未做无关全仓重构或配置豁免。最新改动文件单独 ESLint 为 **0 errors / 387 warnings**，退出 0。 |
| Dashboard `npm run knip` | **退出 1** | 7 个 unused files、9 个 unused devDependencies；另有 1 个 unlisted dependency、23 个 unused exports、14 个 unused exported types、26 组 duplicate exports 等告警。未运行破坏性 knip:fix 大删代码。 |
| runtime vs target full SDL | **仍有 14 个定义差异，全量比较退出 1** | 仅 `@doc`/`@webhookEventsInfo` 文档性 directive 差异；严格保留其他 directive 后比较，剩余 0。字段/类型/参数/默认值/枚举基础比较 0。已修复 AppExtensionFilterInput.mount/target 与 DraftOrderInput/CreateInput.voucher 输入弃用标记。**不是字节级或 full exact SDL 通过**。 |

SDL 14 个定义为：CheckoutAutomaticCompletionStatusEnum、CheckoutDeliveryRecalculate、DeliverySelectionStatusEnum、EventPayloadStateEnum、ExportVouchers、GiftCardsExportInput、Mutation、ProductsExportInput、Query、StockSourceStrategyEnum、TransactionCountableConnection、TransactionCountableEdge、VoucherCodesExportInput、VouchersExportInput。

knip 的 7 个 unused files（相对 Dashboard 根目录）：`src/components/MetadataHookForm/index.ts`、`src/extensions/components/ExtensionsButtonSelector/ExtensionsButtonSelector.tsx`、`src/extensions/domain/permission.ts`、`src/extensions/isUrlAbsolute.ts`、`src/orders/components/OrderPayment/styles.ts`、`src/orders/components/OrderTransactionGiftCard/messages.ts`、`src/orders/components/OrderUsedGiftCards/index.ts`。它们不是全部基线问题的已验证结论。

### 3.3 材料与执行边界

- 冻结用例 `/workspace/artifacts/sprint1/test-design/test-cases.v1.csv` 读取遇到 EACCES，未绕过、未修改或替换；**没有声明已读取或执行全部冻结测试用例**。本轮自测以可读 PRD/技术设计/契约及新增仓库测试为依据。
- 新增测试主要验证确定性局部合同和 mock 边界，真实 PostgreSQL 测试及少量双连接并发不能替代真实 provider、worker 故障注入与浏览器全链路。
- 安装复现使用既有依赖，未执行从空 node_modules 的全新联网安装。临时 pnpm/venv/cache 留在 scratch，不纳入源码。

## 4. 测试环境与验证方式

- 部署状态：**待部署**。
- 部署版本：**待部署**。
- 环境入口：**待部署**。
- 访问方式：**待部署**；没有已部署测试账号或外部入口。测试使用 pytest fixture 和本地隔离测试数据，不提供或写入生产凭据。
- 验证方式：本地 Core pytest/API/数据库/并发、Django 检查/迁移、SDL 比较；Dashboard Jest/Testing Library、codegen、tsc/strict、ESLint/Prettier、knip、message extract 和 Vite build。具体结果如下。
- 环境限制：本地 PostgreSQL 15 位于 scratch、端口 55432；memory broker/LocMem 替代 Redis，非真实 Celery worker；未执行 Playwright 浏览器 E2E、真实 OIDC/Google、资金 provider、外部配送及真实 App 安装服务联调；无生产历史数据升级与回滚演练。SECRET_KEY 使用测试/临时值，日志含预期临时 key warning，不是可部署安全配置。

### 4.1 环境与测试结果

Core：Python 3.12.14、Django 5.2.13、Graphene 2/graphql-core 2.3.2、pytest 8.4.2；虚拟环境 `/workspace/scratch/venv`。Dashboard：Node v24.21.0、pnpm10.28.1、React18.3.1、TypeScript/Apollo、Vite7.3.1；未按 CLAUDE.md 中旧 React17 描述误报运行版本。

| 验证 | 结果与覆盖 | 证据（除特别说明均位于 `/workspace/scratch/`） |
| --- | --- | --- |
| Core 最终新增整合集 | **24 模块、551 passed，1 warning，96.98 秒**。密码策略/员工删除/OIDC、checkout/channel、搜索、导出、富文本、metadata/历史快照、资金/根交易、App/outbox/配送；包括真实数据库与双连接并发。 | `core-sprint1-tests-delivery.log`；执行路径清单 `core-sprint1-test-paths.txt` |
| Core 公开输入与跨模块合并回归 | **205 passed，1 warning，82.01 秒**。scalar、分页、Federation、cost map、原始 search、富文本 mutation 原文保持及历史 allocation 履约边界。 | `core-public-integration-final.log` |
| Core 最新 SDL 输入弃用补丁后定点 | **118 passed，1 warning，6.09 秒**。与 205/551 有重叠，不相加。 | `core-contract-post-schema.log` |
| 库存/成单与配置领域回归 | **45 passed**，其后纳入最终新增整合集；只表示该组范围。 | `checkout-sprint1-tests-final-rerun.log` |
| 搜索/导出扩展回归 | **122 passed**（51 新增+71 既有），包括既有产品/订单搜索及 CSV 数据/关系/header；与最终新增集重叠。 | `pytest-search-final.log` |
| Django 配置、迁移漂移与重复 migrate | `check` 0 issues；`makemigrations --check --dry-run` No changes detected；已迁移本地 main 再次 migrate 无待执行迁移。 | `core-check-release.log`、`core-migrations-check-release.log`、`core-migrate-release.log` |
| 模板测试库追平 | checkout0082、csv0006、giftcard0025、webhook0014 已实际应用，退出 0。 | `core-template-migrate-final.log` |
| 空库迁移 | **成功，退出 0**。先确认目标不存在，再从 PostgreSQL `template0` 创建独立库 `sprint1_empty_delivery`，完整执行 `manage.py migrate --noinput`；最终应用到 webhook0014。使用 memory broker、LocMem、`POPULATE_DEFAULTS=False`，含 `saleor.tests` 测试迁移；不等于生产默认初始化或历史生产数据升级完成。 | `core-empty-migrate-delivery.log` |
| 查询成本映射 | runtime 遍历 COST_MAP，缺失类型/字段 **0**。 | `core-cost-map-release.log` |
| Core Ruff | 改动 Python **276 文件**，check 通过、format --check 全部已格式化。 | `core-ruff-delivery.log` |
| SDL 对齐 | 基础语义 1,427/1,427、0 差异；full14 差异，仅文档性 directive；不忽略实际弃用或其他 directive。 | `schema-check-final.log`、`schema-full-check-final.log`、`schema-full-diff.json`、`schema-doc-classification.log` |
| Dashboard 改动测试整合集 | **77 suites / 741 tests passed，1 snapshot passed，90.41 秒**；另最新 ref/格式补丁后相关 **5 suites / 47 tests passed**。两组重叠，不相加；没有运行全仓所有 Jest。 | `dashboard-changed-tests-release.log`、`dashboard-last-fixes-tests.log`；`dashboard-final-test-paths.txt` |
| Dashboard 最终生成 | `npm run generate` 成功，使用本地接受的 target 副本；没有 fetch 在线升级 schema，generated 文件由工具生成。 | `dashboard-generate-delivery.log` |
| Dashboard 最终类型 | `npm run check-types` **退出0**：Playwright tsc、普通源码 tsc、**2,918 strict 文件全部通过**。未放宽 tsconfig、未新增忽略以绕过该检查。 | `dashboard-check-types-delivery.log` |
| Dashboard 最终构建 | generate → check-types → build 串行成功；**12,062 modules transformed，1m19s**。输出在 scratch；Sentry telemetry 显式关闭且无 auth token，未上传。 | `dashboard-build-delivery.log`；`dashboard-build-delivery/` |
| Dashboard 改动文件规范 | Prettier 388 个改动源码文件通过；最新 scoped ESLint **0 errors / 387 warnings**，退出0。全仓 lint 仍失败，见 §3。 | `dashboard-format-final.log`、`dashboard-changed-eslint-release.log` |
| 消息提取 | `npm run extract-messages` 退出0，locale/defaultMessages 已更新。 | `dashboard-extract-final.log` |
| 全仓 lint / knip | 均实际执行，均失败，不算通过。 | `dashboard-lint-final.log`、`dashboard-knip-final.log` |
| Git 差异 | 两仓 `git diff --check` 通过；runtime SDL 生成后只规范尾空格，没有修改冻结 target。 | `core-diff-check-delivery.log`、`dashboard-diff-check-delivery.log` |

上述集合有重复覆盖，**不汇总为一个相加的总通过数**。旧回归失败和未实现分支不因新增 551/741 项通过被关闭。

正式保留的验证证据位于 `/workspace/artifacts/sprint1/development/validation-evidence/`，`index.json` 记录原始路径、字节数、SHA256、实际退出码及覆盖限制。保留了最终 Core/前端测试、空库迁移、类型/构建、改动 ESLint、SDL 及 knip 等 25 个证据文件；Financial/BaseOIDC/全仓 lint 的冗长旧失败日志仅在索引保留结果行和原始摘要，完整原件仍在 scratch。代码快照不包含 scratch，因此表格中未保留副本的原始日志不是持久交付承诺。证据复制前做了私钥、AWS/GitHub token 和 Bearer JWT 有限模式扫描，无命中；不包含本地私钥或虚拟环境。

### 4.2 复现方式

以下仅使用本次独占 scratch 测试库；不得对共享或生产库执行 flush/drop。pytest 复用库需先追平迁移，避免把缺列误作业务缺陷；不要同时对同一库 migrate/flush。

```bash
# Core，工作目录 /workspace/repos/saleor
# 先激活 /workspace/scratch/venv，并将实际隔离测试库 URL 配在环境中。
# 本轮 local 数据库 sprint1_main，数据库文件位于 scratch，未接生产。
export DATABASE_URL=postgresql://stage1231@localhost:55432/sprint1_main
export DATABASE_URL_REPLICA="$DATABASE_URL"
export PYTEST_DB_URL="$DATABASE_URL"
export CELERY_BROKER_URL=memory://
export CACHE_URL=locmem://sprint1-delivery
export PYTHONPYCACHEPREFIX=/workspace/scratch/pycache
python /workspace/scratch/run_core_sprint1_delivery.py
# 路径清单：/workspace/scratch/core-sprint1-test-paths.txt
# 公开输入/基础回归：
python -m pytest -n0 --reuse-db \
  --basetemp=/workspace/scratch/pytest-public-recheck \
  -o cache_dir=/workspace/scratch/pytest-cache-public-recheck \
  saleor/graphql/core/tests/test_sprint1_input_contract.py \
  saleor/graphql/core/tests/test_sprint1_integration_boundaries.py \
  saleor/graphql/core/tests/test_scalars.py \
  saleor/graphql/core/tests/test_pagination.py \
  saleor/graphql/core/tests/test_federation.py \
  saleor/graphql/core/tests/test_query_cost_validation.py
```

```bash
# Dashboard，工作目录 /workspace/repos/saleor-dashboard
export PATH=/workspace/scratch/bin:$PATH
export npm_config_cache=/workspace/scratch/npm-cache
npm run generate
npm run check-types
# 以最终测试路径清单重跑（使用 Node 读取，不把占位符当 shell 重定向）。
node <<'JS'
const fs = require("node:fs");
const { spawnSync } = require("node:child_process");
const files = fs.readFileSync("/workspace/scratch/dashboard-final-test-paths.txt", "utf8")
  .trim().split(/\r?\n/);
const result = spawnSync("npm", ["run", "test:quiet", "--", "--runInBand",
  "--cacheDirectory=/workspace/scratch/jest-cache", "--runTestsByPath", ...files],
  { stdio: "inherit" });
if (result.error) throw result.error;
process.exit(result.status ?? 1);
JS
# 使用本轮相同的无上传配置构建，仍输出至 scratch。
SENTRY_AUTH_TOKEN= SENTRY_DSN= SENTRY_ORG= SENTRY_PROJECT= \
  npm --ignore-scripts run build -- --outDir /workspace/scratch/dashboard-build-recheck
npm run extract-messages
npm run lint   # 本轮全仓结果失败，含 auto-fix；不要与其他写任务并发
npm run knip   # 本轮结果失败；不运行 knip:fix 大删保留代码
```

### 4.3 迁移说明与部署前验证重点

- 新增 29 个迁移，覆盖密码/OIDC、CAS/metadata revision、渠道库存/自动完成、completion 历史、礼品卡动作/审计、搜索、私有导出及 BusinessEvent/delivery 状态。正式部署应按 Django migration graph 执行，不手工改历史金额。
- checkout0082 对唯一历史 token 建完成事实；重复历史 token 标 blocked/conflict、order 为空，不任意选择首条或删除历史订单。giftcard0024 只根据可靠历史事件差额建审计映射，不改卡余额/订单总额；无可靠证据的历史不伪造。order0218 不以当前配送 metadata 冒充历史快照。相关幂等/重复历史/余额不变定点测试已通过。
- 曾有较早空库尝试因未隔离 Redis 回调失败；保留该执行事实，不以其日志宣称成功。**本轮重验成功，退出 0**：使用独立 `template0` 新库 `sprint1_empty_delivery`、memory broker、`POPULATE_DEFAULTS=False`，完整执行所有迁移。默认商店初始化、生产历史完整数据和外部 worker 不在这一验证范围。
- 必须补验 D01—D09，并回归既有失败批次；确认 provider 去重/unknown 对账、成单竞争、worker 崩溃恢复、private snapshot/税务权限、范围改变的导出/批量、真实 OIDC 和浏览器上下文切换后，方可判断是否满足冻结验收。
- 部署前必须清理旧 public 导出对象/CDN，配置私有存储、真实 broker/worker、RSA/SECRET_KEY、外部服务与自托管目录。任何配置保存/任务排队/文件作业受理均不能报告为订单/资金/投递最终成功。
