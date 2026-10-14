# 测试报告：Saleor Core 与 Dashboard 协同迁移至 3.23.0

版本：v1
轮次：1
依据：PRD v1；frontend-design.md / backend-design.md / interface-contract.md v1；冻结 target-schema.graphql；test-cases.v1.csv；test-results.1.csv。执行与结论遵循本轮提供的三个测试模板。
被测版本：sprint1-deploy-r1 / Core 3.23.0、Dashboard 3.23.0。Core 基线 `c864e66b8e537d30732ddba62d3a4c47e49e4a3e` + 工作区差异 SHA-256 `7fcdd8e1e22ee6a7c749cab841e3e7bad832b97c86478a4ad52157028bff77f6`；Dashboard 基线 `aebb2401b5079fbbb8c60150289d1896c108feca` + 差异 SHA-256 `00dbc6921189984723f8e26c360602c73ee94f959c4d642b843f61a4220d13c1`。基线 HEAD 本身不是包含迁移实现的新提交。
测试环境：容器内实际运行的 `/workspace/deployment/repos` 候选；GraphQL `http://127.0.0.1:8000/graphql/`，Dashboard `http://127.0.0.1:9000/`，Mailpit `http://127.0.0.1:8025/`；PostgreSQL15、Valkey、真实 Celery/Uvicorn/nginx。浏览器使用预装 Playwright Chromium。迁移/重建另用授权 scratch 副本及独立 `qa_infra_r1`、`qa_infra_r1_upgrade` 库，不迁移共享 saleor 库。所有入口仅容器 loopback。
上一轮报告：无

## 1. 结论

结论：fail

145 个冻结 TC 各有且仅有一条正式记录：**通过 52、失败 7、阻塞 74、未执行 12**。其中“未执行”包括已执行 API/部分 UI、但本轮未完成全部冻结步骤的场景，不能按整例通过。统计及按需求编号清单见 `evidence/main/integration-summary.json`。

- 失败：**TC063 / D01、TC065 / D02、TC068 / D03、TC098 / D04、TC143 / D05、TC071 / D06、TC120 / D07**。D01—D06 为本轮观察到的产品处理/恢复行为缺口；D07 为审查执行历史确认的离线约束违规，不冒称本轮再次联网安装。
- TC042—TC044、TC118 的声明 pnpm10 工具链无法离线运行；TC124 冻结四 suite 命令启动失败，**四套件均零实际执行**，不能算测试通过。
- 真实安装扩展与 manifest 内容校验受本地获取限制阻塞；真实支付确认、Transaction 付款/退款终态能力缺失；完整目标范围、正式 F2P/P2P 清单及批准发布入口仍未闭合。
- TC005、TC127—TC129 的通过仅说明范围披露/报告判定符合冻结预期，不说明未知目标能力或其引用失败已通过。

**修复/遗留状态：**本轮是首次 QA，没有上一轮缺陷修复计划，也没有源码修复。D01—D07 均未修复，D08—D23 的环境、材料或执行缺口仍存在。开发提测披露的 3 项 metadata Jest 回归失败、全量 ESLint/Knip 未通过仍作为历史已知问题保留；本轮四 suite 未执行，不能宣布这些问题修复或复测通过。实际部署已由 `.readiness.json` 及本轮请求证实可用，取代提测报告在运行器执行前的“待部署”时间点描述，但可用性不替代业务验收。

## 2. 需求验收情况

| 需求 | 通过 / 失败 / 阻塞 / 未执行 | 本轮结论与 TC 依据 |
| --- | --- | --- |
| R01 | 4 / 0 / 1 / 0 | TC001—TC003 版本及真实 staff/App/页面显示一致；TC005 正确保留 Q01/Q02。TC004 无真实已安装扩展前置；不能声称 AC-01-2/完整 3.23 目标功能通过。 |
| R02 | 7 / 0 / 39 / 0 | TC008 全量 620 文档、642 定义对两完整 SDL 校验无错误；TC010、TC020、TC021、TC037、TC099、TC142 权限/输入等已验证。TC006 正常部署导出权限受阻，完整 HTTP introspection 可观测语义一致仅为补充。TC007、TC009、TC011—TC039、TC130—TC139 多项缺真实扩展或 manifest 获取路径，整体未验收。 |
| R03 | 0 / 0 / 4 / 0 | TC042—TC044 声明工具链执行受阻；TC045 无真实两实例扩展缓存场景。已有 bundle、历史直接 codegen、静态全操作验证不能替代这些步骤。 |
| R04 | 35 / 6 / 20 / 12 | TC053—TC062 异常隔离与故障反馈、TC064/TC066/TC067/TC077/TC082、真实 API 授予规则及多项 checkout 回读通过；六项产品失败见 D01—D06。TC069/TC070/TC072—TC075/TC079/TC080/TC083/TC096/TC097/TC100 未完整执行；扩展、支付、精确结算负例等仍阻塞，不能以 API 子检查替代 UI。 |
| R05 | 2 / 0 / 2 / 0 | TC114 空库完整迁移后真实六字段/基本读写、TC115 重复迁移/plan/model 检查通过。TC113 真实 3.22 自有存量升级已知不变量与 method 保留成功，但 Q03 未确认，整例阻塞；TC116 无非法存量样本审计。 |
| R06 | 0 / 1 / 3 / 0 | TC120 历史联网包获取违反 AC-06-3；TC117 两实际安装依赖不等于锁版本；TC118 pnpm10 缺缓存；TC119 Q06 未确认。不能宣称干净锁一致离线交付通过。 |
| R07 | 1 / 0 / 2 / 0 | TC121 两 baseline + 普通 diff 重建，Core API、Dashboard 构建及实际商品 Save/reload 通过。TC122 缺完整评估前置摘要；TC123 缺完整确认契约/正式结果，不能扩称整体保护与行为验收完成。 |
| R08 | 3 / 0 / 3 / 0 | TC127—TC129 报告真实性/完整性审查通过；TC124 四 suite 未执行、TC125/TC126 正式清单未冻结，正式评分保持 disabled。 |

## 3. 缺陷

以下 D 编号为本轮首次发布的稳定编号。产品失败、环境阻塞、材料缺口、执行缺口分别标记；并非每一 D 都是生产代码缺陷。每条的完整请求、响应、截图与实际观察均可从正式 CSV 的“证据”追溯。

### D01 · 变体必要实体缺失时没有失败反馈
- 类型/状态：产品行为缺陷，未修复；关联用例：TC063；关联需求：R04 / AC-04-1、AC-04-2，FD04/FD05。
- 描述与复现：真实部署浏览器填有效变体表单，仅在允许的测试响应层返回 `errors=[] / productVariant=null`。页面保留输入、不空 ID 导航，也无成功 toast，但没有失败/无法核验提示，按钮恢复普通状态；同例草稿分支正确提示错误。违反“结束 pending 并显示失败”。不是后端实际返回该形状或真实持久化成功的证明。
- 证据：`evidence/browser/TC063-variant.json`、`TC063-variant.png`、`TC063-draft.json`。
- 建议：必要实体缺失统一进入可见失败状态，保持输入和无自动重试；按 TC063 两路径复测。

### D02 · 真实写入后的重读失败未明确区分验证状态
- 类型/状态：产品反馈缺陷，未修复；关联用例：TC065；关联需求：R04 / AC-04-1、AC-04-2，FD04。
- 描述与复现：真实 VariantCreate 成功，仅中断后续详情读取；页面同时出现 `Variant created` 与泛化 `Failed to fetch`，没有明确“已提交、验证失败/请刷新”。写入计数 1，恢复刷新只查询并读回原对象，**没有重复创建**。
- 证据：`evidence/browser/TC065.json`、`TC065.png`。
- 建议：明确分离提交成功和回读验证失败，保留已取得身份；不重复写入。

### D03 · 缺少必需 productType 且带顶层错误仍允许变体提交
- 类型/状态：产品提交门禁缺陷，未修复；关联用例：TC068；关联需求：R04 / AC-04-1、AC-04-2，FD04。
- 描述与复现：有效商品部分数据保留，测试层将必需 productType 置 null 并附顶层 GraphQL 错误；错误可见，但填写有效 name/SKU 后仍捕获一次 VariantCreate。为避免写入，该请求再次被测试层拦截；没有声称服务器创建了实体。
- 证据：`evidence/browser/TC068-injection.json`、`TC068-complete-input.json`、`TC068-complete-input.png`。
- 建议：缺关键依赖数据时禁用提交，不用 partial data 构造成功前提。

### D04 · 渠道排序失败缺少明确部分保存反馈
- 类型/状态：产品部分失败反馈缺陷，未修复；关联用例：TC098；关联需求：R04 / AC-04-1、AC-04-3，FD08。
- 描述与复现：真实 channelUpdate 成功，第一次 reorder 注入合法 ChannelError。页面显示泛型 Invalid value/QA reorder failure，没有明确“渠道已保存、排序失败”；保留 channel.id，未整体报成功。恢复 Save 再发 update + reorder，最终真实顺序正确，无重建或伪回滚。**失败依据为冻结预期的部分保存提示缺失**；重复 update 作为额外观察，不扩称发生重复渠道或数据丢失。
- 证据：`evidence/browser/TC098.json`、`TC098-failure.png`、`TC098.png`。
- 建议：显示已保存步骤与失败排序，恢复时优先只处理未完成部分。

### D05 · 公共 bulk 判定缺少失败行定位与 partial-failure
- 类型/状态：公共函数范围缺陷，未修复；关联用例：TC143；关联需求：R04 / AC-04-1、AC-04-2，FD04。
- 描述与复现：真实 ProductVariantBulkUpdate IGNORE_FAILED 返回一项成功、一项 UNIQUE，root errors=[]；精确部署公共函数经自有 VM 执行捕获项级错误，但状态只有 `error`，扁平错误无失败行身份（path=null），不满足冻结的 partial-failure/可定位失败项。全成功样本为 success，独立读保留已成功部分。
- 证据：`evidence/browser/TC143.json`、`TC143-requests.jsonl`、`TC143-state.json`、`bulk-helper.cjs`。
- 边界：完整逐项浏览器 UI **未执行**；不据公共函数结果断言所有页面展示均错误，也不把此测试当完整 UI 通过。
- 建议：保留 bulk 行身份/成功部分和部分失败状态，在实际调用页面补全冻结逐项展示复测。

### D06 · 库存部分失败恢复重发已成功变体 root
- 类型/状态：产品恢复流程缺陷，未修复；关联用例：TC071；关联需求：R04 / AC-04-1，FD05/I05。
- 描述与复现：真实表单仅向 stock 输入注入重复 warehouse，真实 Core stock root 返回 `UNIQUE / Duplicated warehouse ID`，variant root 成功且名称持久化。UI 正确显示 Some changes could not be saved，无整体成功；恢复 Save 却重新发送整个四-root VariantUpdate，包括已成功的 productVariantUpdate，不符合冻结步骤“只重试失败步骤”。同 ID 库存最终为 9，无重复创建/数据丢失证据。
- 证据：`evidence/business/TC071-real-injected-response.json`、`ui-11-VariantUpdate.json`、`ui-13-VariantUpdate.json`、`TC071-partial-read.json`、`TC071-recovered-read.json`。
- 边界：早期负库存探索被服务端接受，未作为此例故障或另行确认缺陷；正式故障以真实 UNIQUE 响应为准。
- 建议：追踪各已保存 root，恢复仅提交失败部分，重读确认不变量。

### D07 · 历史记录确认未经许可联网获取包
- 类型/状态：离线合规失败，不可由本轮通过覆盖；关联用例：TC120；关联需求：R06 / AC-06-3。
- 描述与复现：部署提测 §3.3 明确披露开发阶段 Corepack 在查 pnpm 版本时从 npm registry 下载 pnpm12.11.2，违反冻结离线安装约束。本轮包管理调用显式禁网络，未再次在线补装；日志中的 Sentry telemetry 提示不是成功外发证明，也不能证明无网络尝试。
- 证据：`/workspace/artifacts/sprint1/deploy/test-handoff.md` §3.3；`evidence/main/governance-review.json`、`TC124-dashboard-build.log`。
- 建议：保留偏差，由维护者决定合规处置；后续只使用获准本地工具，不宣称整个迁移全程离线。

### D08 · pnpm10 本地材料缺失阻塞声明工作流
- 类型/状态：环境阻塞；关联用例：TC042、TC043、TC044、TC118；关联需求：R03 / AC-03-1—3、R06 / AC-06-2。
- 描述与复现：声明 pnpm10.28.1，当前缓存缺失，COREPACK_ENABLE_NETWORK=0 下 generate、两个 types、build 分别 exit1。TC043 前置生成不成立。旧产物/直接工具历史成功不替代本轮 pnpm 流程。
- 证据：`evidence/main/pnpm-version.log`、`TC042.log`、`TC044-src.log`、`TC044-playwright.log`、`TC044-build.log`、`toolchain-config-review.json`。
- 建议：环境负责人提供授权离线 pnpm10 缓存与可写测试副本，不联网安装，按冻结命令重跑。

### D09 · 冻结四 suite 入口写只读 build 输出失败
- 类型/状态：运行器环境阻塞；关联用例：TC124；关联需求：R08 / AC-08-1、AC-08-5。
- 描述与复现：执行 `/opt/runtime/run-suite.sh qa-v1-01 core-unit core-e2e dash-unit dash-e2e` exit1；Vite prepare-out-dir 删除只读 `build/dashboard/Geist-Black-DyTs4Xsi.woff2` 触发 EACCES。未进入套件收集，四 suite 均无本轮用例结果。现有部署继续健康，不能补成 suite pass。
- 证据：`evidence/main/TC124-run-suite.log`、`TC124-dashboard-build.log`。
- 建议：运行器负责人提供符合权限范围的测试输出/副本。QA 不修改 verifier、源码权限或借服务用户绕过。

### D10 · 本地 manifest 获取阶段被拒绝
- 类型/状态：网络/环境阻塞，非已证实 manifest 校验产品缺陷；关联用例：TC025—TC036、TC038—TC041、TC132—TC139、TC141，以及依赖真实安装的 TC004、TC007、TC009、TC011—TC019、TC022—TC024、TC045—TC052、TC130。
- 关联需求：R01—R04 / AC-01-2、AC-02-3、AC-03-3、AC-04-1/3。
- 描述与复现：自有 loopback manifest 服务返回完整 JSON/200，真实 API 返回 manifestUrl/INVALID，未访问内容；appInstall 只受理 PENDING，worker 后续 FAILED。表现与现有 loopback 安全过滤一致，未越权读取生效私有环境，因此不把具体运行值当已证事实。未知 Enum、PATCH、options 等均未到业务验证分支，不能因同样 INVALID 判负例通过。
- 证据：`evidence/extensions/006-TC025-fetch-valid-query.json`、`TC025-local-service.json`、`manifest-server-requests.jsonl`、`060-TC039-install.json`、各 TC preview 响应。
- 建议：部署/安全负责人提供获准且可达的离线 manifest 测试拓扑，不要求 QA 关闭安全过滤或访问外网。

### D11 · 正常部署 schema 导出入口无读取私有 env 权限
- 类型/状态：权限阻塞；关联用例：TC006；关联需求：R02 / AC-02-1。
- 描述与复现：部署 run.py 的 get_graphql_schema 入口读取 `state/env.json` PermissionError。完整 HTTP introspection 与四 SDL 可观测语义一致已验证，但输入弃用等不可观测信息及冻结命令导出仍未完成。
- 证据：`evidence/extensions/TC006-export-command.txt`、`TC006-schema-comparison.json`、`014-TC006-full-runtime-introspection.json`。
- 建议：服务负责人提供脱敏且授权的生产导出产物/执行方式，不泄露私钥或扩大 QA 读取权限。独立 scratch schema 成功不追记成原部署命令成功。

### D12 · 原部署缺真实扩展及非法存量审计样本
- 类型/状态：数据准备能力阻塞；关联用例：TC004、TC007、TC009、TC011—TC019、TC022—TC024、TC045—TC052、TC116、TC130、TC131；关联需求：R02/R03/R04/R05。
- 描述与复现：原部署 extensions=[]，GraphQL 无扩展直接写接口，合法安装依赖 D10，非法 choice 不能经合法 API 创建；未写受保护部署 DB/fixture 或编造节点。独立空库已知六字段测试在 TC114 通过，但不替代原环境各枚举/权限/缓存/非法数据等完整步骤。
- 证据：`evidence/extensions/008-setup-existing-extensions.json`、`introspection.json`；`evidence/browser/real-extensions-prerequisite.json`。
- 建议：提供获准的自有数据准备机制与审计样本，不批量猜默认或修改官方 fixtures。

### D13 · 安装终态及旧配置边界材料冲突未裁定
- 类型/状态：冻结契约阻塞；关联用例：TC039—TC041、TC130、TC139；关联需求：R02/R04，I02—I04。
- 描述与复现：I04 SUCCESS 与 Base 成功删除 installation 冲突；NEW_TAB/WIDGET null method 新 settings={} 与旧 options 深层非空传播的兼容边界；未知 options key 忽略还是拒绝仍未明确。本轮前两类还缺成功/存量对象，不能凭文案裁定或发明 GET。
- 证据：冻结 CSV 对应条目、部署提测 §3.2、`evidence/extensions/temporary-issues.json`。
- 建议：维护者书面裁定，由 Workflow 处理后续范围；本轮不改冻结预期。

### D14 · 完整目标规格和批准发布入口仍未确认
- 类型/状态：材料阻塞；关联用例：TC113、TC119、TC123；关联需求：R01 / AC-01-2、R05 / AC-05-1、R06、R07 / AC-07-3。
- 描述与复现：Q01—Q03/Q06 未闭合。TC113 实际 3.22 自有数据库升级的所有已记录 ID/FK/金额/状态/库存/method 不变量相同，null 未改 GET，仍不能宣称未知转换通过。发布配置审阅不等于 Docker/CI 全入口批准验证。
- 证据：PRD §5；`evidence/main/governance-review.json`、`toolchain-config-review.json`；`evidence/infrastructure/TC113-invariants.json`、`TC113-upgraded-extension-read.json`。
- 建议：维护者确认完整行为/模型/发布范围；已知范围通过与完整验收分开。

### D15 · 正式 F2P/P2P 清单未接受冻结
- 类型/状态：正式验收材料阻塞；关联用例：TC125、TC126；关联需求：R08 / AC-08-2/3。
- 描述与复现：instruction.md 明确候选清单尚未接受冻结、formal grading disabled；无正式选定 ID 与等条件前后结果。历史大量 Jest pass 不替代正式集合逐项通过。
- 证据：instruction.md；`evidence/main/governance-review.json`。
- 建议：评估维护者接受并冻结清单，提供等条件前后真实结果；此前保持 candidate/local 性质。

### D16 · HTTP API 无法完成精确清 email/地址步骤
- 类型/状态：冻结步骤执行前提阻塞；关联用例：TC102、TC104；关联需求：R04 / AC-04-4。
- 描述与复现：有效 paid checkout 仅清 email 的空字符串被 REQUIRED 拒绝；shippingAddress 更新输入非空且无删除入口。另建缺字段 checkout 的辅助负例拒绝且无新订单/分配，但不能替代“其余条件有效、仅清除字段”的精确步骤。
- 证据：`evidence/checkout/http.jsonl`（TC102/TC104 标签）、`findings.json`。
- 建议：提供不修改生产逻辑/冻结 fixtures 的授权自有状态准备能力，按原步骤复测，不以近似负例补 pass。

### D17 · 现有本地 legacy 插件不支持二次支付确认
- 类型/状态：支付能力阻塞；关联用例：TC107；关联需求：R04 / AC-04-4，I09。
- 描述与复现：已有生产 dummy/dummy_credit_card 返回 action_required=false，无获准 confirmationNeeded=true 两阶段工具；未 monkey patch 或伪造 confirmationData。
- 证据：`evidence/checkout/findings.json`、`http.jsonl`。
- 建议：提供授权本地确认支付能力，不更改冻结期望。

### D18 · 缺真实支付 App/退款事件处理与终态推进
- 类型/状态：支付环境阻塞；关联用例：TC090、TC091、TC092、TC094、TC144；关联需求：R04 / AC-04-2/3/4，I07/I09。
- 描述与复现：实际支付请求返回 MISSING_TRANSACTION_ACTION_REQUEST_WEBHOOK；无真实 Payment App 事件处理，不能推进 PENDING/SUCCESS/FAILURE 或验证 Transaction 建单。TC094 两路径前端 timeout 不重发已观察，但 API 前拦截不是“已受理而响应丢失”。授予测试的 charged100 是 API 账本准备，不是真实扣款。
- 证据：`evidence/business/771-TC092-payments-request.json`、`evidence/browser/TC094-legacy.json`、`TC094-transaction.json`；`evidence/checkout/findings.json`。
- 建议：提供获准本地资金动作/事件对端，分别验证请求接受、最终状态和不确定结果恢复；不手填成功冒充外部资金。

### D19 · 独立通知观察未见本单邮件
- 类型/状态：通知环境限制/观察项，非 TC101 整例失败；关联用例：TC101；关联需求：R04 / AC-04-4。
- 描述与复现：自有 main 渠道 user_email inactive，Mailpit 未见 qa-checkout 单通知；订单与付款事件独立持久化，已执行冻结要求的独立通知观察，未声明实际邮件送达成功。
- 证据：`evidence/checkout/mailpit-read.json`、`findings.json`、`checks.json`。
- 建议：需要通知投递验收时提供对应插件/配置及事件观察，不由同步建单成功推断投递。

### D20 · 实际后端依赖与锁版本不完全一致
- 类型/状态：锁一致/离线可复现环境阻塞；关联用例：TC117；关联需求：R06 / AC-06-1。
- 描述与复现：76 项活跃直接依赖满足声明，生产导入/启动/schema 成功；pillow-avif-plugin 实装1.5.2而锁1.6.0，posuto 实装2025.9.0而锁2025.12.0。不能宣称锁一致生产环境；未在线补装或改依赖路径。
- 证据：`evidence/infrastructure/TC117-installed-lock-comparison.json`、`TC117-imports.log`、`TC117-schema-export.log`。
- 建议：环境负责人提供匹配锁的获准离线材料，重跑一致性/生产启动，不把范围满足等同精确锁一致。

### D21 · 缺实施前完整官方评估材料摘要清单
- 类型/状态：审计材料阻塞；关联用例：TC122；关联需求：R07 / AC-07-2。
- 描述与复现：可取得的七份冻结材料及44个变更文件均与交付清单一致，仓库差异未见官方测试修改；但没有实施前完整 tests/fixtures/verifier/scoring 路径/摘要/删除重命名清单，不能以当前摘要证明不存在的基线审计。QA 未修改这些材料。
- 证据：`evidence/main/source-integrity.json`；`evidence/infrastructure/TC122-material-audit.json`、`baseline-reconstruction.json`。
- 建议：提供受保护材料基线 inventory 供只读比较，不要求 QA 编辑 verifier。

### D22 · 本轮部分商家 UI/独立故障步骤未完整执行
- 类型/状态：**测试执行缺口，不是环境阻塞或已证实代码失败**；关联用例：TC069、TC070、TC072—TC075、TC079、TC080、TC083、TC096、TC097、TC100；关联需求：R04 / AC-04-1/2/3。
- 描述：这些 TC 的 API/部分 UI 成功证据已保留，但完整创建多步、属性/media/metadata 编辑、独立渠道/metadata 故障恢复、错误页面/退款草稿文案、渠道排序配送/删除 UI 等要求尚未完成。原子检查或其他 TC 的成功不能补足整例。
- 证据：正式 CSV 对应证据；`evidence/business/partial-results.csv`、`TC070-UI-independent-read.json`、`TC097-UI-read.json`、`ui_execute.cjs`。
- 建议：后续轮次按冻结步骤补全独立执行；这些结果最终标“未执行（未完整执行）”，不伪装受环境阻塞。

### D23 · legacy 退款/履约数据前置未准备齐全
- 类型/状态：本例前置数据/链路未覆盖；关联用例：TC093、TC145；关联需求：R04 / AC-04-2，I07。
- 描述：TC093 无付款零金额/20 CNY 拒绝已回读，合法 legacy 可退/不可退及 TC145 Dashboard 履约退款链未执行。**容器存在生产 legacy dummy 插件，checkout 组在自有 main 已验证建单**；因此不把业务组未具备可退 Payment/履约前置误说成全环境完全没有 legacy 网关。dummy 建单也不证明这些退款步骤完成。
- 证据：`evidence/business/792-TC093-0-before-read.json`、`793-TC093-no-payment-0.json`、`796-TC093-no-payment-20.00.json`、`order-ui.png`；`evidence/checkout/findings.json`。
- 建议：协调现有获准本地工具与自有可退款/履约数据，按 TC093/TC145 原完整链路执行，不用授予账本替代商品/legacy 退款。

## 4. 其他

### 4.1 证据与执行边界
- 原始证据统一在 `/workspace/artifacts/sprint1/qa/evidence/`，分 main / extensions / browser / business / checkout / infrastructure；正式 CSV 保留可访问绝对文件路径。同一 TC 的探索、测试脚本修正、恢复重读均属于该条执行记录，不增加重复 TC 行。
- 浏览器响应注入仅验证前端故障处理；真实 API 写入与独立重读另行标识。TC143 是精确公共函数测试，不声称完整逐项 UI。所有 pending、HTTP200、errors=[]、有效 mutation ID 均未单独当最终业务成功。
- checkout 使用冻结前提允许的现有生产本地 dummy 插件，证明本地建单/付款账本/库存/事件，不证明外部真实资金到账。退款授予账本与资金请求/到账严格分开。
- 首次完整操作验证脚本曾错误合并 operation 与 fragment 的独立名称空间，修正测试脚本后再验证0冲突；初始输出保留为 `TC008-harness-namespace-error.json`，不作为产品缺陷。迁移/浏览器准备脚本的配置错误也保留，未隐藏为通过。
- 提测历史失败、本轮环境阻塞及业务失败分开记录；报告样本 TC128 明确是完整性规则审查，不是假官方运行结果。TC129 对本轮四 suite 零执行与 TC063 失败证据分离，不能用健康 200 替代任何一项。

### 4.2 冻结完整性与清理
- 冻结 CSV SHA-256：`3e0eaee98c790c293e3c1ea8a05ea55450126a2971c0216899e42222a5693e18`；PRD SHA-256：`02a77a745d70336edac9b301a6ddbc87104167eba2c2c12c277ba3d4bf86f123`。七份冻结输入、两端原始及部署候选44个变更文件共88个文件摘要均与开发清单相同，见 `source-integrity.json`。未修改冻结用例、预期或生产源码。
- 全部五个子 Agent 已完成本轮，未进入下一 Stage。自启8765、8766、8012、8013、9012服务/浏览器已停止；对应 `extensions/service-shutdown.json`、`infrastructure/cleanup.json`、`checkout/closeout.json` 等保留。共享部署服务未停止，测试自有数据保留供证据/回读，不清理官方 fixtures。
- 服务私钥/私有 env 未越权读取，token/密码在证据脱敏；本轮未从网络安装包。既有 Sentry 插件在部分测试构建日志提示 telemetry，未获得其成功发送证明，也不声称完全无网络尝试。

### 4.3 下一轮建议
先处理 D01—D06 的生产反馈/门禁/恢复缺口，由环境负责人解决 D08—D12、D16—D20 的授权测试能力，由维护者裁定 D13—D15、D21 材料；补齐 D22/D23 执行。所有后续复测继续使用本轮冻结 CSV，不修改预期，不将未执行或 collection 缺失补为 pass。是否结束或进入修复 Sprint 由 Workflow 决定。
