# Opus 5.5 high · v5 文档评测

候选：single-docs-gpt61-xhigh-instruction-20261014。

每组两次独立判定；技术设计另有一次分歧裁决，共 7 次有效 Judge 调用。

- PRD：两次均 7/8，最终 87.5%。
- 技术设计：两次 7/8、8/8；裁决 7/8，最终 87.5%。
- 测试设计：两次均 6/6，最终 100%。
- 最终 reward：0.875；总体 20/22 通过；关键项全部通过；document_acceptance=0。

模型请求显式设置 output_config.effort=high、thinking=adaptive，API 返回模型为 anthropic/claude-opus-5.5。网关对 JSON 外层代码块的兼容处理已记录在 events 文件中；仍执行逐项 Schema 校验。

本次正式运行无 exception、无协议重试；启动调试失败保留在单独的历史目录，不计入两次有效判定。原始封存产物全部哈希复核一致。仅评价文档，未验证代码、部署或 GraphQL GT。

## 未通过项

### PRD8 优先级与交付决策明确

31 条需求中 30 条标为 P0，仅 R15 为 P1。商品诊断、搜索、扩展目录、重量与日期展示等体验或运营类需求也被列为 P0，与资金、库存、安全类需求同级，无法支撑取舍与排期。文档也没有集中的依赖关系、风险评估、发布门槛或切换窗口说明，待确认项只要求在实现前落实，缺乏交付决策所需的门槛与风险分析。

### TDD7 性能与容量假设明确

多数约束已有明确口径：分页 1..100、默认 20；搜索 ≤256 字符、≤32 词；EditorJS 1MiB/1000 blocks/深度 8；delay 0..10080。Q01 搜索窗口已列为待确认，扫描周期和批量明确交给部署配置，webhook 沿用既有上限，也未伪造运行结论。但设计本身把导出改为浏览器内逐页读取，由此引入容量约束，而这部分口径含糊。第一，“分页循环上限100”没有说明是页数还是条数，也没有说明超限后的行为。第二，“较大数据”降级到 legacy job 的阈值未定义。第三，可导出数据规模既没有假设，也没有列为待确认条件，只在风险中笼统提及。按“含糊即 F”的规则判为 F，与第一份意见一致。

---

# 文档 Rubric Judge 报告

Rubric：`saleor-pruned-docs` · `2026-10-14-v5-pruned-business-inputs`
Harbor reward：**0.8750**；全部评分项通过：否

## 分组得分

| 分组 | 通过率 |
| --- | ---: |
| prd | 87.50% |
| tech_design | 87.50% |
| test_design | 100.00% |

## 交付完整性

全部要求文件均已交付。

## 逐项结果

| Rubric | 结果 | 证据 | 判定 |
| --- | --- | --- | --- |
| PRD1 · 目标与范围对齐 | P | /candidate/sprint1/prd/prd.md:修订说明；/candidate/sprint1/prd/prd.md:§1 交付目标后段；/candidate/sprint1/prd/prd.md:§4 排除项表 | PRD 承接了 Instruction 的链路目标与五项交付目标。第 4 节完整列出范围，并逐项给出非目标与保留边界，与 Instruction 和 BC-031 一致。文中明确不虚构收益、SLA 或部署结果，并把基线代码事实与目标需求分开，没有把计划写成已实现事实。 |
| PRD2 · 用户与接入方覆盖 | P | /candidate/sprint1/prd/prd.md:§2 用户表；/candidate/sprint1/prd/prd.md:§2 用户表；/candidate/sprint1/prd/prd.md:§2 表后说明 | PRD 识别了八类公开输入涉及的角色：客户/Storefront、商户/渠道管理员、商品内容运营、客服售后、库存履约、商店身份管理员、支付/App/Webhook 集成方、自托管与只读人员。每类均写明典型任务（目标与入口）以及必须遵守的事实，并统一说明权限、归属与范围边界。 |
| PRD3 · 核心流程与结果完整 | P | /candidate/sprint1/prd/prd.md:§3 开头；/candidate/sprint1/prd/prd.md:R05 需求描述；/candidate/sprint1/prd/prd.md:R23 需求描述 | 31 条需求逐一对应 BC 片段，均说明触发条件、业务行为与可观察结果。抽查以下细项均未遗漏：配送重算、更新与完成重校验、库存模式、诊断、批量自动成单、cutoff/延迟、礼品卡授权/取消/扣款/退款、金额摘要、资金动作、基础交易查询、搜索、锁定筛选、认证策略、OIDC、富文本、扩展、Webhook、配送快照、员工实际删除、草稿动作限制等。voucherCode、tokenTargetUrl、变体折扣价事件等细项也已覆盖。 |
| PRD4 · 异常、安全与数据边界完整 | P | /candidate/sprint1/prd/prd.md:AC-11-5；/candidate/sprint1/prd/prd.md:AC-07-6；/candidate/sprint1/prd/prd.md:R18 需求描述 | 各需求分别写出了失败路径、权限限制、安全约束与数据边界。读取范围（R11、R28）、写入拒绝且原值不变（R25、R10）、错误中不泄露信息（R17、R28）、失败不伪装成功或空结果（R26）被分别表述，没有相互替代。 |
| PRD5 · 兼容与存量连续性完整 | P | /candidate/sprint1/prd/prd.md:R03 需求描述；/candidate/sprint1/prd/prd.md:R02 需求描述；/candidate/sprint1/prd/prd.md:R27 需求描述 | 以下兼容义务均有具体保留或迁移条款与验收：旧配送标识与弃用字段、未切换库存模式商店的旧行为、旧渠道自动完成默认关闭、升级商店的密码行为、历史扩展无需重装、历史礼品卡订单不重算、旧导出 mutation 弃用、已退出插件与 Payment.partial 返回迁移错误、voucherCode 替代、历史配送元数据迁移。没有用概括性兼容表述代替具体义务。 |
| PRD6 · 迁移、恢复与补偿完整 | P | /candidate/sprint1/prd/prd.md:R27 需求描述；/candidate/sprint1/prd/prd.md:AC-08-4；/candidate/sprint1/prd/prd.md:§5 待确认项说明 | 各类适用要求均已明确：库存模式需显式切换；空库与旧库迁移且重跑无副作用；自动成单与 delivery 失败后可重试；礼品卡取消与退款构成资金补偿；已扣款不可经取消回退、历史快照不回写等不可回退边界。延迟单位、目录来源、支付支持矩阵等未知外部条件以 Q01～Q06 标注，未被删除。 |
| PRD7 · 验收条件可判定 | P | /candidate/sprint1/prd/prd.md:AC-06-3；/candidate/sprint1/prd/prd.md:AC-09-2；/candidate/sprint1/prd/prd.md:AC-10-3 | 每条需求都有编号 AC，采用给定/操作/结果形式，断言可观察的业务结果。AC 覆盖适用的权限、失败、边界值、兼容、幂等、并发与迁移场景。L 深度、一致性窗口等缺数值的部分已作为参数化边界与待确认项处理，不影响可判定性。 |
| PRD8 · 优先级与交付决策明确 | F | /candidate/sprint1/prd/prd.md:§3 优先级说明；/candidate/sprint1/prd/prd.md:R15；/candidate/sprint1/prd/prd.md:R21 | 31 条需求中 30 条标为 P0，仅 R15 为 P1。商品诊断、搜索、扩展目录、重量与日期展示等体验或运营类需求也被列为 P0，与资金、库存、安全类需求同级，无法支撑取舍与排期。文档也没有集中的依赖关系、风险评估、发布门槛或切换窗口说明，待确认项只要求在实现前落实，缺乏交付决策所需的门槛与风险分析。 |
| TDD1 · 需求追踪与设计归属 | P | /candidate/sprint1/tech-design/frontend-design.md:§2 需求覆盖；/candidate/sprint1/tech-design/backend-design.md:§2 需求覆盖；/candidate/sprint1/tech-design/interface-contract.md:I17 | 后端将 R01–R31 全部映射到 BD01–BD17。前端将 R03–R31 映射到 FD01–FD13，并说明了不直接承接的需求及原因。I01–I26 各自归属一个 BD，前端依赖表将 I 映射到 FD，BT01–BT10 标明各自覆盖的 BD。共享职责有明确划分，例如 R15、R29、R30 的前后端分工，以及 I17 由 Dashboard 提供、BD13 共管协议。未发现无人承担或重复定义的情况。两份意见一致，复核后维持 P。 |
| TDD2 · 前端行为设计充分 | P | /candidate/sprint1/tech-design/frontend-design.md:FD01；/candidate/sprint1/tech-design/frontend-design.md:FD03；/candidate/sprint1/tech-design/frontend-design.md:FD12 | 各 FD 都给出了具体组件落点、入口，以及 loading/empty/forbidden/network/stale/conflict 等状态。交互规则（脏字段保护、迟到响应丢弃、防双击、幂等键）、权限门控、失败保留输入与重试也都有说明。限制同样写明，例如不模拟后台完成、不本地重算库存、不新增 async fallback。内容是实际行为设计，不是复述 PRD。 |
| TDD3 · 后端状态与数据设计充分 | P | /candidate/sprint1/tech-design/backend-design.md:BD05；/candidate/sprint1/tech-design/backend-design.md:BD06；/candidate/sprint1/tech-design/backend-design.md:BD14 | 后端明确了服务职责和新增模型：CheckoutCompletion、GiftCardLedgerEntry、PaymentCommand、DomainEventOutbox、配送快照。数据身份已定义，例如 checkout_token unique、scope/key unique、logical_key。状态转换和持久化结果清楚，异步边界也明确：PSP 调用在事务外，on_commit 后由 worker 构建 payload。主流程收敛到唯一订单、唯一账本结果和唯一逻辑事件。 |
| TDD4 · 接口叙述契约内部一致 | P | /candidate/sprint1/tech-design/interface-contract.md:§1 通用约定；/candidate/sprint1/tech-design/interface-contract.md:I08 完成判定；/candidate/sprint1/tech-design/interface-contract.md:I20 完成判定 | 各接口叙述都写明了提供方、调用方、权限、错误分层（标准 GraphQL 层与业务 field/code/message）、完成判定和兼容过渡。这些内容与前后端设计一致：I08 权限与 BD07、FD03 相符，I05 的 delay/cutoff 边界与 BD04 相符，I16 的 issueToken 与 appUpdate.manifestUrl 与 BD13 相符。接收请求与业务完成被统一区分，覆盖异步 action、安装 Job、retry 排队、设置保存与执行。schema 字段与可空性按评分项规定不作判断。 |
| TDD5 · 失败、并发与恢复机制闭环 | P | /candidate/sprint1/tech-design/backend-design.md:BD02；/candidate/sprint1/tech-design/backend-design.md:BD05；/candidate/sprint1/tech-design/backend-design.md:BD07 | 重复、并发、超时、部分失败、重试、幂等和补偿都有具体机制：全局锁序、lease、scope/key 加 input hash、额度预占与释放、outbox 与 delivery 唯一键、PSP 三步流程与补偿退款。每种机制都写明负责方、状态变化（PENDING/RETRYING/BLOCKED/COMPLETED/FAILED）和终止条件，例如沿用既有重试上限、COMPLETED 后不再变更。 |
| TDD6 · 安全与隐私边界可落实 | P | /candidate/sprint1/tech-design/backend-design.md:BD11；/candidate/sprint1/tech-design/backend-design.md:BD14；/candidate/sprint1/tech-design/interfaces/extension-form-response.md:端点与鉴别 | 身份与权限都有具体机制：JWT 记录认证来源和 credential epoch，OIDC 按 issuer/sub 绑定，list/node/export/subscription 共用统一 scope。HANDLE_TAXES 仅限特定字段，EditorJS 采用白名单，frame 做 origin/source 鉴别，token 只在内存中传递且 issueToken 默认 false。礼品卡只返回 last4，CheckoutCompletion 不存敏感 message，错误脱敏，webhook payload 按权限重新过滤。日志、事件和响应均未扩大可见范围。 |
| TDD7 · 性能与容量假设明确 | F | /candidate/sprint1/tech-design/frontend-design.md:FD05；/candidate/sprint1/tech-design/frontend-design.md:FD05；/candidate/sprint1/tech-design/frontend-design.md:§5 其他 | 多数约束已有明确口径：分页 1..100、默认 20；搜索 ≤256 字符、≤32 词；EditorJS 1MiB/1000 blocks/深度 8；delay 0..10080。Q01 搜索窗口已列为待确认，扫描周期和批量明确交给部署配置，webhook 沿用既有上限，也未伪造运行结论。但设计本身把导出改为浏览器内逐页读取，由此引入容量约束，而这部分口径含糊。第一，“分页循环上限100”没有说明是页数还是条数，也没有说明超限后的行为。第二，“较大数据”降级到 legacy job 的阈值未定义。第三，可导出数据规模既没有假设，也没有列为待确认条件，只在风险中笼统提及。按“含糊即 F”的规则判为 F，与第一份意见一致。 |
| TDD8 · 开发依赖与联调可执行 | P | /candidate/sprint1/tech-design/backend-design.md:§5 BT09；/candidate/sprint1/tech-design/frontend-design.md:§4 依赖与联调；/candidate/sprint1/tech-design/frontend-design.md:§4 联调顺序 | BT01–BT10 的依赖构成无环图（BT01→BT02→BT03/BT04→BT05→BT09→BT10，BT06/BT07/BT08 分支汇入 BT10），每个 BT 都标明覆盖的 BD。前端按接口列出消费方 FD、可独立 mock 的部分和需等待的 BT，阻塞条件明确，并要求 fixture 覆盖多种状态。联调顺序和发布顺序与接口成熟度一致。 |
| TEST1 · 需求追踪完整 | P | /candidate/sprint1/test-design/test-cases.v1.csv:TC001 覆盖列；/candidate/sprint1/test-design/test-cases.v1.csv:TC245 覆盖列；/candidate/sprint1/test-design/test-cases.v1.csv:TC124 覆盖列 | 所有用例的覆盖列都指向有效的 PRD AC，并按需关联 FD、BD 和 I。逐条比对 R01～R31 的验收条件，AC-01-1 至 AC-31-5 均至少有一条用例承接。补充用例 TC246～TC260 同样标明了 AC 来源，未发现无来源用例或关键 AC 遗漏。 |
| TEST2 · 核心业务结果覆盖 | P | /candidate/sprint1/test-design/test-cases.v1.csv:TC072 预期结果；/candidate/sprint1/test-design/test-cases.v1.csv:TC021 预期结果；/candidate/sprint1/test-design/test-cases.v1.csv:TC042 预期结果 | 核心链路均有用例覆盖，包括配送重算、成单、库存、自动完成、礼品卡、金额摘要、资金动作、导出和快照。断言针对具体余额、可用库存、订单数量、事件次数及 Dashboard 与 API 的一致性，而非仅检查请求成功或字段存在。跨前后端契约同样有用例，例如 TC072 的两个订单视图、TC115 的导出集合以及 TC160 的扩展表单。 |
| TEST3 · 权限与安全场景覆盖 | P | /candidate/sprint1/test-design/test-cases.v1.csv:TC089 预期结果；/candidate/sprint1/test-design/test-cases.v1.csv:TC223 预期结果；/candidate/sprint1/test-design/test-cases.v1.csv:TC220 预期结果 | 以下场景均有可判定用例：客户、员工、App 等不同身份；对象与渠道/仓库范围；HANDLE_TAXES 及私有快照；密码策略与 OIDC 接管；富文本危险链接；扩展 frame 鉴别；delivery 重试权限。用例普遍验证拒绝后原值、余额和关联历史保持不变，并区分权限错误与合法空结果。 |
| TEST4 · 异常与连续性场景覆盖 | P | /candidate/sprint1/test-design/test-cases.v1.csv:TC045 预期结果；/candidate/sprint1/test-design/test-cases.v1.csv:TC046 预期结果；/candidate/sprint1/test-design/test-cases.v1.csv:TC104 预期结果 | 失败、边界值（如 L/L+1、延迟和 cutoff 等值）、兼容、空库与旧库迁移及重跑、回退、幂等重放、并发、部分成功（混合批次、bulk 逐项结果）、PSP 崩溃对账、补偿和恢复均有可判定场景。尚不能执行的外部条件已显式标注，例如 Q01 一致性窗口、TC031 中缺少 Core WARNING 触发规则时记为阻塞，以及仅在测试 gateway 能力通过验证时才执行后台捕获。 |
| TEST5 · 步骤与断言对应 | P | /candidate/sprint1/test-design/test-cases.v1.csv:TC050 操作步骤/预期结果；/candidate/sprint1/test-design/test-cases.v1.csv:TC083 前置与预期 | 每条用例都给出本例测试数据，操作步骤与预期结果按 1、2 编号逐项对应，成功和失败判定包含具体数值、错误码类别及状态核对。参数化变体在同一步骤内列出，并给出对应的期望。 |
| TEST6 · 可执行性与独立性 | P | /candidate/sprint1/test-design/test-cases.v1.csv:各用例前置条件；/candidate/sprint1/test-design/test-cases.v1.csv:TC031 前置条件；/candidate/sprint1/test-design/test-cases.v1.csv:TC209 前置条件 | 每条用例都声明了隔离验收环境、所需身份权限和可控测试服务，测试数据在前置条件中自行准备。各用例使用独立可重置的 fixture，不依赖隐含执行顺序。尚未具备的外部条件已显式标注为阻塞或待提供，包括尚未实现的系统、Q01 窗口、WARNING 规则、gateway 能力及迁移产物。 |

## 口径

- 每个冻结评分项只有 P/F，不给半分。
- 缺少任一要求交付文件时，继续执行文档 Rubric Judge，但最终 Harbor reward 为 0。
- `reward` 只负责 Harbor 数值传输；分组分数、关键项和逐项证据必须同时保留。
- Judge 或基础设施失败会使评测报错，不会记为候选 0 分。
