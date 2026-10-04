# 文档 Rubric Judge 报告

Rubric：`saleor-standard-docs` · `2026-09-28-v4-direct-docs`
Harbor reward：**0.5000**；全部评分项通过：否

## 分组得分

| 分组 | 通过率 |
| --- | ---: |
| prd | 87.50% |
| tech_design | 50.00% |
| test_design | 83.33% |

## 交付完整性

全部要求文件均已交付。

## 逐项结果

| Rubric | 结果 | 证据 | 判定 |
| --- | --- | --- | --- |
| PRD1 · 目标与范围对齐 | P | /candidate/sprint1/prd/prd.md:§1 业务背景与目标；/candidate/sprint1/prd/prd.md:§5 范围与非目标；/candidate/sprint1/prd/prd.md:§1 业务背景与目标 | 目标覆盖经营资料、库存与运费、资金、登录、应用接入和受控升级，与公开委托一致；范围及非目标清楚，且明确区分需求、静态调查与已部署或已验证事实。 |
| PRD2 · 用户与接入方覆盖 | P | /candidate/sprint1/prd/prd.md:§2 用户与场景；/candidate/sprint1/prd/prd.md:R10 AC-10-4；/candidate/sprint1/prd/prd.md:R15 AC-15-4 | 受影响的商家角色、员工、顾客、集成方、实施和 QA 均被识别；各需求进一步给出 Dashboard/API/详情页等入口以及服务端权限、渠道隔离、员工与应用双重授权等边界。 |
| PRD3 · 核心流程与结果完整 | P | /candidate/sprint1/prd/prd.md:§4 需求条目 R01—R20；/candidate/sprint1/prd/prd.md:R08 需求描述；/candidate/sprint1/prd/prd.md:R17 需求描述 | 公开输入要求的经营资料、内容、图片、搜索、库存、运费、数字权益、交易退款、插件退出、密码策略、Widget、故障状态、订阅通知及升级流程均有独立需求；各项说明触发条件、业务行为和可观察结果，未发现静默删除明确义务。 |
| PRD4 · 异常、安全与数据边界完整 | P | /candidate/sprint1/prd/prd.md:R03 AC-03-2；/candidate/sprint1/prd/prd.md:R09 AC-09-7；/candidate/sprint1/prd/prd.md:R19 AC-19-2 | 失败路径、服务端写权限、读取与渠道隔离、敏感信息披露、SSRF、危险内容、资金幂等及通知数据最小化均被分别转化为需求和验收条件，没有用隐藏界面或读取限制替代写入授权。 |
| PRD5 · 兼容与存量连续性完整 | P | /candidate/sprint1/prd/prd.md:R05 AC-05-1；/candidate/sprint1/prd/prd.md:R17 AC-17-3；/candidate/sprint1/prd/prd.md:R07 AC-07-4 | 旧入口、默认值、存量渠道、旧订阅、历史账务、旧 Payment、数字文件与已购权益均有具体保留或迁移规则；明确退出项也配置消费者清单和删除门槛，而非仅作概括性兼容声明。 |
| PRD6 · 迁移、恢复与补偿完整 | P | /candidate/sprint1/prd/prd.md:R20 AC-20-3；/candidate/sprint1/prd/prd.md:R20 AC-20-6；/candidate/sprint1/prd/prd.md:§6 依赖与上线门槛 | 切换前影响报告和外部路径预检、备份、停写与在途保护、可续跑迁移、历史权益核对、按币种对账、恢复演练和开放后增量恢复均明确；同时标注了不可直接回滚资金事实及尚待外部补齐的条件。 |
| PRD7 · 验收条件可判定 | P | /candidate/sprint1/prd/prd.md:R08 AC-08-1—AC-08-6；/candidate/sprint1/prd/prd.md:R13 AC-13-1—AC-13-6；/candidate/sprint1/prd/prd.md:R20 AC-20-1—AC-20-7 | R01—R20 均配置直接对应的编号化验收条件，断言可观察业务结果，并覆盖字段错误、权限拒绝、安全、默认兼容、并发幂等、部分成功、迁移续跑和恢复等适用场景。 |
| PRD8 · 优先级与交付决策明确 | F | /candidate/sprint1/prd/prd.md:R15 优先级；/candidate/sprint1/prd/prd.md:R16 优先级；/public/query.md:本阶段任务与输出 | 依赖、风险、维护窗口、版本固定和切换门槛总体充分，也未把计划写成已执行结果；但 R15 的五类首版 Widget 和 R16 的应用故障状态均是公开委托明确要求的本轮核心结果。删除任一项会使“补齐五类详情 Widget”或“区分安装失败、主动停用、投递失败及熔断”的目标无法实现，而非仅让用户增加正常操作，因此按公开优先级口径应为 P0，标成 P1 与业务影响规则不一致。 |
| TDD1 · 需求追踪与设计归属 | P | /candidate/sprint1/tech-design/frontend-design.md:§2 需求覆盖；/candidate/sprint1/tech-design/backend-design.md:§2 需求覆盖、§4 接口清单；/candidate/sprint1/tech-design/backend-design.md:§5 工程任务与依赖 | R01—R20 均在前后端覆盖表中指向明确 FD/BD；I01—I12 均标注所属后端设计单元，并在契约中列明调用方；BT01—BT17 也标注覆盖的 BD。前端负责界面与交互消费，后端负责业务状态、持久化及接口提供，迁移和切换明确归后端/部署编排，引用目标存在且总体归属一致。具体设计是否充分分别由后续评分项判断，不影响本项的追踪关系成立。 |
| TDD2 · 前端行为设计充分 | F | /candidate/sprint1/tech-design/frontend-design.md:§2 需求覆盖；/candidate/sprint1/tech-design/frontend-design.md:FD06 · 退出旧数字入口与旧账结果登记；/candidate/sprint1/prd/prd.md:R11 · AC-11-5 | FD06 明确认领 R11，但其实际交互只覆盖四类退出插件的“外部已发生结果”登记。对于历史账务归一产生的 REQUIRES_REVIEW，前端没有设计待核对状态反馈、审核证据查看、经审核人工映射入口、成功或拒绝结果及失败恢复，也没有明确说明该操作不由 Dashboard 承担并给出替代路径。因此其已承担的用户入口、状态和恢复行为覆盖不充分。 |
| TDD3 · 后端状态与数据设计充分 | F | /candidate/sprint1/tech-design/backend-design.md:BD07 · 历史资金归一与四插件退出；/candidate/sprint1/tech-design/backend-design.md:BD07 · 历史资金归一与四插件退出；/candidate/sprint1/tech-design/interface-contract.md:I08 · 旧支付外部结果登记 | BD07 定义了可信证据的自动归一以及证据不足时进入 REQUIRES_REVIEW，但没有定义经审核人工映射的服务操作、授权主体、状态转换、审计字段写入规则或最终业务结果。I08 明确只登记已经在外部发生的支付事实，不能替代证据不足旧账的审核映射。因此 R11 后端状态机会进入待核对状态，却没有可设计执行的收敛路径。 |
| TDD4 · 接口叙述契约内部一致 | P | /candidate/sprint1/tech-design/interface-contract.md:§1 通用约定；/candidate/sprint1/tech-design/interface-contract.md:I03 · 搜索索引任务可观测接口；/candidate/sprint1/tech-design/interface-contract.md:I07 · 按来源幂等退款；/candidate/sprint1/tech-design/interfaces/digital-download.md:§3 判定与响应 | I01—I12 的叙述均列出提供方、调用方、权限、错误、完成判定及兼容方式。搜索任务、外部退款和异步投递明确区分请求可靠登记与最终业务完成；旧数字下载补充协议的身份、错误和完成语义与 I05 一致。固定证据中未发现这些叙述之间存在提供方、权限、完成判定或兼容过渡冲突。 |
| TDD5 · 失败、并发与恢复机制闭环 | F | /candidate/sprint1/tech-design/backend-design.md:BD05 · 礼品卡交易账本与来源退款；/candidate/sprint1/tech-design/backend-design.md:BD05 · 礼品卡交易账本与来源退款；/candidate/sprint1/prd/prd.md:R09 · AC-09-4 | 设计覆盖了幂等键、锁、部分成功和 FAILED 项重试，但外部退款只描述“写 pending—调用应用—等待回报”。没有规定调用超时或回报丢失时由谁核对并推进，也没有规定外部已成功而本地落账失败时进入何种补偿/人工状态、如何确认外部事实、防止再次请求资金及何时终止。BT10 仅把“本地落账补偿”列为验证内容，不能替代具体责任、状态变化和恢复机制，关键资金失败窗口仍未闭环。 |
| TDD6 · 安全与隐私边界可落实 | P | /candidate/sprint1/tech-design/interface-contract.md:§1 通用约定；/candidate/sprint1/tech-design/backend-design.md:BD06 · Transaction 精确查询与渠道权限；/candidate/sprint1/tech-design/backend-design.md:BD10 · 应用状态聚合而不改变熔断策略；/candidate/sprint1/tech-design/interfaces/digital-download.md:§4 并发与恢复 | 设计具体落实了领域权限、员工与应用双重权限、Channel queryset 隔离、私有 metadata 裁剪、卡码掩码、下载能力 token、短期 Widget claim 和图片 SSRF 边界。接口响应、通知、状态摘要及日志均规定过滤 URL 参数、header、payload、卡码、密码和 token，未扩大敏感数据可见范围。 |
| TDD7 · 性能与容量假设明确 | P | /candidate/sprint1/tech-design/interface-contract.md:§1 通用约定；/candidate/sprint1/tech-design/backend-design.md:BD02 · 内容、远程图片与可恢复索引；/candidate/sprint1/tech-design/backend-design.md:§6 其他；/candidate/sprint1/tech-design/backend-design.md:§6 其他 | 文档给出分页上限、图片字节/像素/时间预算、通知 Channel 上限、搜索本地时限口径以及大表并发建索引和分批回填策略。真实存量、验收负载和维护窗口被保留为待确认依赖，60 秒被明确限定为后续测量的本地验收目标而非生产 SLA，满足容量与未知条件表达要求。 |
| TDD8 · 开发依赖与联调可执行 | F | /candidate/sprint1/tech-design/backend-design.md:BT17 · 受控切换工具与演练；/candidate/sprint1/tech-design/backend-design.md:BT03 · EditorJS 兼容 sanitizer；/candidate/sprint1/tech-design/backend-design.md:BT06 · Channel 配置与库存路径统一；/candidate/sprint1/tech-design/backend-design.md:BT17 · 受控切换工具与演练 | 前后端接口联调顺序和既有 BT 图未见循环，但最终切换任务 BT17 的显式依赖没有包含 BT03/BT04 的内容与图片能力、BT06/BT07 的渠道库存与运费能力，且这些 P0 任务也不能从已列依赖传递到 BT17。BT17 同时声明所有 P0 必须有结果才允许切换，导致正式依赖清单与切换门槛不一致，无法从任务图保证完整交付顺序。 |
| TEST1 · 需求追踪完整 | P | /candidate/sprint1/test-design/test-cases.v1.csv:TC001 覆盖列；/candidate/sprint1/test-design/test-cases.v1.csv:TC121 覆盖列；/candidate/sprint1/test-design/test-cases.v1.csv:TC107 覆盖列及标题 | 测试集按 R01 至 R20 逐条承接全部 PRD 验收条件，覆盖列明确关联 AC，并在适用处继续关联 FD、BD 和接口编号；用例范围从 AC-01-1 连续覆盖至 AC-20-7，未见关键 AC 缺失或无来源用例。 |
| TEST2 · 核心业务结果覆盖 | P | /candidate/sprint1/test-design/test-cases.v1.csv:TC044 预期结果；/candidate/sprint1/test-design/test-cases.v1.csv:TC029 预期结果；/candidate/sprint1/test-design/test-cases.v1.csv:TC111 预期结果 | 核心正常流程覆盖经营资料、库存与运费、数字权益、资金、认证、应用及迁移；用例同时核对 Dashboard、GraphQL/HTTP、持久状态和受控外部端。断言落到交易事件、余额、库存、订单快照、投递状态等真实业务结果，而非只检查请求成功或字段存在。 |
| TEST3 · 权限与安全场景覆盖 | P | /candidate/sprint1/test-design/test-cases.v1.csv:TC060 预期结果；/candidate/sprint1/test-design/test-cases.v1.csv:TC109 预期结果；/candidate/sprint1/test-design/test-cases.v1.csv:TC025 预期结果 | 测试覆盖匿名、员工、管理员、应用及不同权限组合，验证对象权限、渠道隔离、私有 metadata、完整卡码、密码、凭证和令牌等敏感边界；拒绝场景还检查值不变、无事件、无邮件或按不可见处理等拒绝后的业务状态。 |
| TEST4 · 异常与连续性场景覆盖 | P | /candidate/sprint1/test-design/test-cases.v1.csv:TC053 预期结果；/candidate/sprint1/test-design/test-cases.v1.csv:TC111 操作步骤；/candidate/sprint1/test-design/test-cases.v1.csv:TC120 预期结果；/candidate/sprint1/test-design/test-cases.v1.csv:TC115 预期结果 | 失败、边界、兼容、迁移、幂等、并发、部分成功、补偿、任务续跑、崩溃恢复和开放后前向恢复均有可判定场景；未知规模及未验证外部路径被明确判为未满足依赖，而非推定可执行或通过。 |
| TEST5 · 步骤与断言对应 | P | /candidate/sprint1/test-design/test-cases.v1.csv:TC003 前置条件、步骤及预期结果；/candidate/sprint1/test-design/test-cases.v1.csv:TC003 预期结果；/candidate/sprint1/test-design/test-cases.v1.csv:TC052 步骤及预期结果 | 各用例均设有前置条件、操作步骤和编号对应的预期结果。成功、失败、部分成功、并发及重试的判定通常同时给出 UI、接口和持久业务状态，测试者无需自行推断整体成功、资金是否重复或旧值是否保留。 |
| TEST6 · 可执行性与独立性 | F | /candidate/sprint1/test-design/test-cases.v1.csv:TC019 前置条件；/candidate/sprint1/test-design/test-cases.v1.csv:TC111 前置条件；/candidate/sprint1/test-design/test-cases.v1.csv:TC115 前置条件 | 用例虽普遍列出概括性前置条件，但未给出统一验收环境的实际配置、数据夹具/重置方式、受控外部端接入参数，或 worker 崩溃、网络失败、数据库落账失败等故障注入机制。大量前置条件仅写“准备”“可控制”或“明确配置”，无法据文档独立复现；同时没有逐项标注哪些真实外部登录、支付、履约或生产依赖当前不可执行。因此不满足可执行性、独立性及外部执行边界全部成立的要求。 |

## 口径

- 每个冻结评分项只有 P/F，不给半分。
- 缺少任一要求交付文件时，继续执行文档 Rubric Judge，但最终 Harbor reward 为 0。
- `reward` 只负责 Harbor 数值传输；分组分数、关键项和逐项证据必须同时保留。
- Judge 或基础设施失败会使评测报错，不会记为候选 0 分。
