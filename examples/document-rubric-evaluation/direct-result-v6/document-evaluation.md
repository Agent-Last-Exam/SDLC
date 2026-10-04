# 文档 Rubric Judge 报告

Rubric：`saleor-standard-docs` · `2026-09-28-v3-direct-docs`
Harbor reward：**0.6250**；全部评分项通过：否

## 分组得分

| 分组 | 通过率 |
| --- | ---: |
| prd | 87.50% |
| tech_design | 62.50% |
| test_design | 66.67% |

## 交付完整性

全部要求文件均已交付。

## 逐项结果

| Rubric | 结果 | 证据 | 判定 |
| --- | --- | --- | --- |
| PRD1 · 目标与范围对齐 | P | /candidate/sprint1/prd/prd.md:§1 业务背景与目标；/candidate/sprint1/prd/prd.md:§5 范围与非目标 | PRD准确承接核心 API、Dashboard、经营连续性、应用接入、资金、账号和迁移目标，并用明确的范围与非目标约束交付边界；同时明确区分需求目标、静态调查和已部署或已验证事实，没有把后续实施或收益写成当前结果。 |
| PRD2 · 用户与接入方覆盖 | P | /candidate/sprint1/prd/prd.md:§2 用户与场景；/candidate/sprint1/prd/prd.md:§2 用户与场景；/candidate/sprint1/prd/prd.md:R10 验收条件 AC-10-4 | 用户表覆盖管理员、内容/仓储/渠道运营、客服、财务、员工、顾客、应用集成方、运维实施和 QA；各需求进一步定义 API、Dashboard、详情页、财务列表、登录和订阅等入口，并给出服务端权限、渠道隔离及数据访问边界。 |
| PRD3 · 核心流程与结果完整 | P | /candidate/sprint1/prd/prd.md:R05 需求描述及验收条件；/candidate/sprint1/prd/prd.md:R08 验收条件 AC-08-1；/candidate/sprint1/prd/prd.md:R17 需求描述 | 公开输入要求的经营资料、内容与图片、搜索、库存、运费、数字权益、资金与退款、交易查询、密码策略、Widget、故障状态及通知订阅均被拆为需求；各条描述触发或适用条件、关键行为及可观察结果，没有静默删减明确义务。 |
| PRD4 · 异常、安全与数据边界完整 | P | /candidate/sprint1/prd/prd.md:R03 验收条件 AC-03-2；/candidate/sprint1/prd/prd.md:R09 验收条件 AC-09-7；/candidate/sprint1/prd/prd.md:R19 验收条件 AC-19-2 | PRD分别处理输入校验、失败结果、SSRF 与资源限制、权限拒绝、渠道隔离、私有字段和凭证披露；读取订单、执行退款和修改礼品卡等权限没有互相替代，通知与搜索也保持最小数据边界。 |
| PRD5 · 兼容与存量连续性完整 | P | /candidate/sprint1/prd/prd.md:R05 验收条件 AC-05-1；/candidate/sprint1/prd/prd.md:R17 验收条件 AC-17-3；/candidate/sprint1/prd/prd.md:R07 验收条件 AC-07-4 | 旧默认库存方式、旧订阅及固定 payload、旧 ID/token、历史 Payment、旧插件售后、历史数字权益和既有扩展入口均有具体保留或迁移规则；并明确了不得自动重置、不得改变默认行为和消费者未迁移时的阻断门槛。 |
| PRD6 · 迁移、恢复与补偿完整 | P | /candidate/sprint1/prd/prd.md:R20 验收条件 AC-20-3；/candidate/sprint1/prd/prd.md:R20 验收条件 AC-20-6；/candidate/sprint1/prd/prd.md:§6 依赖与上线门槛 | 切换前影响盘点、外部路径预检、备份、停写与任务排空、可续跑迁移、资金和权益对账、恢复责任与验证均已明确；开放后新事实不可用旧库直接回退，并将未知规模、外部路径和历史证据保留为显式依赖。 |
| PRD7 · 验收条件可判定 | P | /candidate/sprint1/prd/prd.md:R06 验收条件 AC-06-5—AC-06-7；/candidate/sprint1/prd/prd.md:R09 验收条件 AC-09-3—AC-09-4；/candidate/sprint1/prd/prd.md:R20 验收条件 AC-20-5 | R01—R20均附有直接编号的验收条件，断言可观察的业务状态和错误结果，并按适用性覆盖权限拒绝、兼容默认值、并发与幂等、部分成功、重试、迁移核对及恢复场景，具备明确判定基础。 |
| PRD8 · 优先级与交付决策明确 | F | /candidate/sprint1/prd/prd.md:R15 标题区；/candidate/sprint1/prd/prd.md:R16 标题区；/public/query.md:本阶段任务与输出 | 依赖、风险、维护窗口、外部证据及切换门槛总体充分，且未把计划写成已执行结果；但 R15 的五类 Widget 和 R16 的四类应用故障状态都是公开委托明确要求的本轮主要能力，删除任一项都会使对应目标无法实现，而非仅让使用者增加正常操作。将两项标为 P1 不符合公开的业务影响优先级口径。 |
| TDD1 · 需求追踪与设计归属 | P | /candidate/sprint1/tech-design/frontend-design.md:§2 需求覆盖；/candidate/sprint1/tech-design/backend-design.md:§2 需求覆盖；/candidate/sprint1/tech-design/backend-design.md:§5 BT16；/candidate/sprint1/tech-design/interface-contract.md:§2 I11 | 前端与后端分别提供完整的 R→FD、R→BD 覆盖表，接口契约列出所属 BD、提供方和调用方，工程任务也回指 BD 并声明依赖。经营设置、资金、认证、Widget、Webhook 和迁移等责任可追踪至冻结 PRD，未见明确需求无人承担或前后端对同一权威责任作冲突定义。 |
| TDD2 · 前端行为设计充分 | P | /candidate/sprint1/tech-design/frontend-design.md:§3 FD05；/candidate/sprint1/tech-design/frontend-design.md:§3 FD07；/candidate/sprint1/tech-design/frontend-design.md:§3 FD08；/candidate/sprint1/tech-design/frontend-design.md:§3 FD10 | 前端设计逐域说明了页面入口、加载和终态、分区保存、权限下的隐藏或只读反馈、局部错误隔离、未知状态、草稿保留、部分成功及重试行为，并给出实际限制和组件落点，不是仅列需求编号或复述 PRD。 |
| TDD3 · 后端状态与数据设计充分 | P | /candidate/sprint1/tech-design/backend-design.md:§3 BD05；/candidate/sprint1/tech-design/backend-design.md:§3 BD11；/candidate/sprint1/tech-design/backend-design.md:§3 BD04；/candidate/sprint1/tech-design/backend-design.md:§3 BD12 | 后端设计覆盖模型身份、唯一约束、事务和锁顺序、持久状态、异步 outbox、任务检查点及恢复结果。礼品卡扣款、历史数字权益、搜索、退款、会话失效、通知和迁移等主流程均能收敛到可查询的成功、部分成功、失败或阻断状态。 |
| TDD4 · 接口契约消除歧义 | F | /candidate/sprint1/tech-design/interface-contract.md:§1 通用约定；/candidate/sprint1/tech-design/interface-contract.md:§2 I07；/candidate/sprint1/tech-design/interface-contract.md:§3 其他 | 文档将未包含在固定证据包中的 target-schema.graphql 指定为完整字段和可空性的权威来源，同时明确正文片段不能替代它。可见契约例如 I07 引用了 TransactionRefundAllocationInput，却未给出该输入的完整字段、字段可空性和错误载体结构。因此无法仅凭证据核验所有提供方与调用方在字段、nullable、枚举、错误及兼容删除上的一致性；虽有业务完成判定说明，仍未满足契约整体消歧要求。 |
| TDD5 · 失败、并发与恢复机制闭环 | F | /candidate/sprint1/tech-design/backend-design.md:§3 BD05；/candidate/sprint1/tech-design/interface-contract.md:§2 I07；/candidate/sprint1/prd/prd.md:R09 AC-09-4 | 多数重复、并发和任务恢复机制已有具体设计，但外部退款的未知结果未闭环。设计只说明先置 pending/processing、调用外部应用以及回报后落账，没有定义调用超时、响应或回调丢失、外部已成功但本地落账失败时由谁探测，进入何种持久补偿或人工状态，如何凭外部幂等标识避免再次退款，以及 processing 的终止条件。工程任务中的“本地落账补偿”验证词不能替代机制设计。 |
| TDD6 · 安全与隐私边界可落实 | F | /candidate/sprint1/tech-design/backend-design.md:§3 BD11；/candidate/sprint1/tech-design/interface-contract.md:§2 I12 权限；/candidate/sprint1/prd/prd.md:R19 AC-19-2 | 候选对身份、渠道隔离、SSRF、token、卡码和日志脱敏提供了多项具体机制，但通知中的私有 metadata 边界与冻结 PRD 冲突。PRD 明确要求通知 payload 不包含私有 metadata；候选却允许具备领域权限且显式选择的应用接收它。该设计扩大了冻结要求下的敏感数据披露范围，因此安全与隐私边界不能判定为可落实。 |
| TDD7 · 性能与容量假设明确 | P | /candidate/sprint1/tech-design/interface-contract.md:§1 通用约定；/candidate/sprint1/tech-design/backend-design.md:§3 BD02；/candidate/sprint1/tech-design/backend-design.md:§3 BD02；/candidate/sprint1/tech-design/backend-design.md:§6 其他 | 文档给出分页、图片字节/像素/时限、运费 TTL、通知渠道数量和搜索本地时限等明确口径，并针对潜在大表采用并发索引、分批回填和 checkpoint。真实存量、维护窗口及外部路径被列为待确认条件，且本地目标没有被伪称为生产 SLA 或运行结论。 |
| TDD8 · 开发依赖与联调可执行 | P | /candidate/sprint1/tech-design/frontend-design.md:§4 依赖与联调；/candidate/sprint1/tech-design/frontend-design.md:§4 依赖与联调；/candidate/sprint1/tech-design/backend-design.md:§5 BT16；/candidate/sprint1/tech-design/backend-design.md:§5 BT17 | 接口清单和前端依赖表标明生产设计单元、消费设计单元及等待条件；联调顺序从 schema/codegen、mock 到 API、权限异常和 E2E，与契约成熟度一致。BT01—BT17 给出单向前置依赖，最终切换任务依赖关键领域任务，未见循环；目标 schema、外部路径和存量证据等阻塞条件也有明确标注。 |
| TEST1 · 需求追踪完整 | P | /candidate/sprint1/test-design/test-cases.v1.csv:TC001，覆盖列；/candidate/sprint1/test-design/test-cases.v1.csv:TC121，覆盖列 | 候选测试集按 R01 至 R20 的验收条件组织，覆盖列逐条关联 PRD AC，并在适用处关联 FD、BD 和接口编号；证据中的用例从 AC-01-1 连续承接至 AC-20-7，未见无 AC 来源的用例或关键验收条件完全没有测试承接。 |
| TEST2 · 核心业务结果覆盖 | P | /candidate/sprint1/test-design/test-cases.v1.csv:TC044，预期结果；/candidate/sprint1/test-design/test-cases.v1.csv:TC029，预期结果；/candidate/sprint1/test-design/test-cases.v1.csv:TC053，预期结果 | 核心经营、库存、运费、交易、退款、认证、订阅通知和迁移开放流程均有正常或关键交互场景。断言落到交易及事件、余额、真实库存、订单状态、部分成功事实和用户可见反馈，并联合核对 Dashboard、GraphQL/HTTP、持久数据和受控外部端，不是仅检查请求成功或字段存在。 |
| TEST3 · 权限与安全场景覆盖 | P | /candidate/sprint1/test-design/test-cases.v1.csv:TC031，预期结果；/candidate/sprint1/test-design/test-cases.v1.csv:TC060，预期结果；/candidate/sprint1/test-design/test-cases.v1.csv:TC109，预期结果 | 测试覆盖匿名、员工、管理员、App、对象深链权限、渠道范围及支付、礼品卡、应用管理等权限组合，并检查 private metadata、完整卡码、密码、凭证等敏感数据边界。拒绝场景包含值不变、无局部写入、无事件或按不可见处理等业务状态断言。 |
| TEST4 · 异常与连续性场景覆盖 | P | /candidate/sprint1/test-design/test-cases.v1.csv:TC053，预期结果；/candidate/sprint1/test-design/test-cases.v1.csv:TC111，操作步骤与预期结果；/candidate/sprint1/test-design/test-cases.v1.csv:TC115，预期结果 | 设计覆盖失败、超时、边界、并发、兼容、迁移续跑、幂等、部分成功、补偿、worker 崩溃、耗尽重试和恢复等连续性场景。TC115 还明确把未知规模及未验证外部路径标为未满足依赖，TC084、TC043 等通过预检阻断缺少验证的登录或履约路径，满足对尚不可执行外部条件的显式标注要求。 |
| TEST5 · 步骤与断言对应 | F | /candidate/sprint1/test-design/test-cases.v1.csv:TC033，操作步骤；/candidate/sprint1/test-design/test-cases.v1.csv:TC001，操作步骤；/candidate/sprint1/test-design/test-cases.v1.csv:TC107，操作步骤 | 大量用例复用泛化的“逐项改变”“执行矩阵”和跨多层“核对结果”步骤，没有列明各子场景的具体输入值、GraphQL operation 或 HTTP 路径、调用顺序以及对应的持久数据或外部端观察点。部分用例仅称“13个新增事件”等集合而未逐项展开，因此测试者仍需推断操作与断言如何对应，不满足无需猜测隐含状态的要求。 |
| TEST6 · 可执行性与独立性 | F | /candidate/sprint1/test-design/test-cases.v1.csv:TC019，前置条件；/candidate/sprint1/test-design/test-cases.v1.csv:TC014，前置条件；/candidate/sprint1/test-design/test-cases.v1.csv:TC111，前置条件 | 虽然各行通常有独立前置条件，且 TC115 会标记真实外部依赖未满足，但测试设计未定义所谓标准环境的版本和配置值，也未说明受控 DNS/公网端/PSP、状态源、故障注入设施的搭建与控制方法、测试数据构造和清理复位方式。仅声明环境“明确配置”或“可注入”不足以让执行者据文档独立准备并重复执行，整体可复现性证据不足。 |

## 口径

- 每个冻结评分项只有 P/F，不给半分。
- 缺少任一要求交付文件时，继续执行文档 Rubric Judge，但最终 Harbor reward 为 0。
- `reward` 只负责 Harbor 数值传输；分组分数、关键项和逐项证据必须同时保留。
- Judge 或基础设施失败会使评测报错，不会记为候选 0 分。
