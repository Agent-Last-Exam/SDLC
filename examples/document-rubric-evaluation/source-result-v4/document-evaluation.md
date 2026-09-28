# 文档 Rubric Judge 报告

Rubric：`saleor-standard-docs` · `2026-09-26-v1`
Harbor reward：**0.1250**；全部评分项通过：否

## 分组得分

| 分组 | 通过率 |
| --- | ---: |
| prd | 33.33% |
| tdd_schema | 50.00% |
| tdd_quality | 12.50% |
| test_design | 75.00% |

## 逐项结果

| Rubric | 结果 | 证据 | 判定 |
| --- | --- | --- | --- |
| PRD1 · 目标与范围对齐 | P | /opt/document-eval/candidate/sprint1/prd/prd.md:第1节，第9-18行；/opt/document-eval/candidate/sprint1/prd/prd.md:第5节，第292-302行 | 目标、用户、核心范围及非目标与公开委托一致，并明确区分目标行为与已部署或已验证结果。 |
| PRD2 · 需求完整性 | F | /workspace/public/query.md:经营资料与检索，第13行；/opt/document-eval/candidate/sprint1/prd/prd.md:R01，第41行；/workspace/public/business-conversations.md:扩展体验，第119行 | 覆盖面虽广，但遗漏明确义务：R01只限制私有 metadata 的读取暴露，没有禁止敏感信息写入公共 metadata；R15也未明确保持已有列表入口传递选中 ID。固定输入中的已明确义务不能以概括性兼容表述替代。 |
| PRD3 · 清晰性与确定性 | F | /opt/document-eval/candidate/sprint1/prd/prd.md:R16，第221-227行；/workspace/repos/saleor/saleor/webhook/circuit_breaker/breaker_board.py:第20-39行 | 应用熔断需求及验收条件仅引用“Base 默认阈值与自动恢复语义”，未写明可核实的统计窗、失败阈值、冷却时间和恢复条件。Base 中这些值可以静态确定，但PRD读者仍需自行调查才能知道关键状态转换规则，不满足确定性要求。 |
| PRD4 · 一致性与正确性 | P | /opt/document-eval/candidate/sprint1/prd/prd.md:第1节，第18行；/opt/document-eval/candidate/sprint1/prd/prd.md:Base 调查依据与限制，第312行 | 业务规则内部一致，与公开决定及核查到的静态 Base 相容；文档明确区分静态现状、目标能力、外部依赖和运行结果，没有把源码存在冒充部署或测试成功。 |
| PRD5 · 可验收性 | F | /opt/document-eval/candidate/sprint1/prd/prd.md:R15，第209行；/opt/document-eval/candidate/sprint1/prd/prd.md:AC-15-5，第215行；/opt/document-eval/candidate/sprint1/prd/prd.md:R13，第185行 | 多数需求有细致AC，但并非每项规则都有直接对应的可判定场景。R15要求保留全部既有挂载点、目标及默认POPUP，AC只笼统要求新旧入口体验一致；R13规定新装和升级未配置默认ALL，却没有直接验收未配置默认值及存量密码连续性。这些兼容和默认行为无法由现有AC完整判定。 |
| PRD6 · 优先级与可交付性 | F | /workspace/public/query.md:本阶段任务与输出，第55行；/opt/document-eval/candidate/sprint1/prd/prd.md:R15，第208行；/opt/document-eval/candidate/sprint1/prd/prd.md:R16，第220行 | 依赖、维护窗口和切换门槛总体充分，但五类详情Widget和应用故障状态均是公开目标中的明确首版能力；移除后相应目标不能实现，按公开优先级口径应为P0而非P1。 |
| TDD-A1 · 产物、章节与字段完整 | F | /workspace/templates/target-interface.md:第12行；/opt/document-eval/candidate/sprint1/tech-design/interfaces/digital-download.md:第13-15行 | 前端设计、后端设计、接口契约和完整目标 SDL 均存在，但 I05 登记的历史下载 HTTP 边界仅有叙述性 Markdown，未给出实际路径模板，也未按目标接口交付规范提供完整 OpenAPI。因而完整目标接口描述条件不成立。 |
| TDD-A2 · 编号引用与归属有效 | F | /opt/document-eval/candidate/sprint1/tech-design/frontend-design.md:第97行；/opt/document-eval/candidate/sprint1/tech-design/backend-design.md:第120行；/opt/document-eval/candidate/sprint1/tech-design/backend-design.md:第77-78行 | I06 的前端归属链把 FD06 和 R11列为消费者及对应需求，但后端接口清单和权威契约仅将 I06 归属 BD05、BD06；承接 R11 的 BD07 未列为 I06 所属设计单元。因此前端 I→FD→R 与 I→BD→R 的归属不一致。 |
| TDD-A3 · 责任、版本与名称一致 | P | /opt/document-eval/candidate/sprint1/tech-design/frontend-design.md:第1-5行；/opt/document-eval/candidate/sprint1/tech-design/interface-contract.md:第3-5行 | 前端、后端及接口契约的版本、责任和依据链符合对应 Schema；标题及 Shop、TransactionItem、Page/PageType、Channel 等业务名称与 PRD 保持一致，未发现含义漂移。 |
| TDD-A4 · 编号历史与修订合规 | P | /opt/document-eval/candidate/sprint1/tech-design/frontend-design.md:第3-6行；/opt/document-eval/candidate/sprint1/tech-design/backend-design.md:第3-6行；/opt/document-eval/candidate/sprint1/tech-design/interface-contract.md:第3-6行 | 三项主要设计产物均声明 v1 首次交付，没有虚构历史修订；现有编号集合未显示重排、复用或与修订版本矛盾。 |
| TDD-B1 · 各端完整承接需求 | F | /opt/document-eval/candidate/sprint1/tech-design/interface-contract.md:I07，第142-152行；/opt/document-eval/candidate/sprint1/prd/prd.md:AC-09-1，第140行 | 退款目标接口要求每个来源分配都显式提供正金额，Dashboard 也只是预填剩余可退额，没有承接服务端“省略金额取剩余可退”的行为。调用方无法表达该验收场景，因此需求未被各端完整覆盖。 |
| TDD-B2 · 适配现有系统并遵守约束 | F | /opt/document-eval/candidate/sprint1/tech-design/frontend-design.md:方案概述，第10行；/workspace/repos/saleor-dashboard/package.json:dependencies，第114-115行 | 设计错误识别 Dashboard 的核心运行时版本。固定 Base 使用 React 18.3.1，而候选以 React 17 作为现有架构前提，不能证明前端方案已准确适配指定 Base。 |
| TDD-B3 · 关键行为足以实施 | F | /opt/document-eval/candidate/sprint1/tech-design/backend-design.md:BD05，第71行；/workspace/public/business-conversations.md:收款退款，第71行 | 设计只说明请求前置 pending、正常回报和失败项重试，没有定义外部已成功但响应丢失或本地落账失败时的识别依据、持久状态、责任模块及补偿或人工收敛流程。BT10 提到验证补偿不能替代可实施的行为设计。 |
| TDD-B4 · 接口契约消除歧义 | F | /opt/document-eval/candidate/sprint1/tech-design/interface-contract.md:I04，第93行；/opt/document-eval/candidate/sprint1/tech-design/target-schema.graphql:StockSettingsInput，第28404-28409行；/opt/document-eval/candidate/sprint1/tech-design/frontend-design.md:FD04，第56行 | 契约宣称配置字段可独立省略，前端也只发送变化字段，但更新 inventoryMode 所在的 StockSettingsInput 仍强制 allocationStrategy。调用方不能按文档只提交库存模式，目标定义、调用策略和省略语义相互冲突。 |
| TDD-B5 · 数据与异常保持业务不变量 | F | /opt/document-eval/candidate/sprint1/tech-design/backend-design.md:BD05，第71行；/opt/document-eval/candidate/sprint1/prd/prd.md:AC-09-4，第143行 | 设计未规定发送给外部提供方的稳定幂等标识、结果收件箱或主动对账机制，也没有外部成功而本地失败的专用状态。响应丢失或落账失败后既无法可靠收敛，也无法证明后续处理不会重复请求外部退款，资金不变量缺少保障。 |
| TDD-B6 · 非功能约束得到支撑 | P | /opt/document-eval/candidate/sprint1/tech-design/backend-design.md:BD02，第51行；/opt/document-eval/candidate/sprint1/tech-design/interface-contract.md:通用约定，第16行 | 图片下载具有协议、SSRF、容量、像素和时间边界；查询、索引、大表迁移及聚合接口具有分页、索引、批处理和 N+1 控制。权限、渠道、私有 metadata、卡码、凭证及日志脱敏边界也有具体落实机制。 |
| TDD-B7 · 开发依赖与联调可执行 | F | /opt/document-eval/candidate/sprint1/tech-design/frontend-design.md:FD04，第56行；/opt/document-eval/candidate/sprint1/tech-design/target-schema.graphql:StockSettingsInput，第28404-28409行及第34917-34920行；/opt/document-eval/candidate/sprint1/tech-design/frontend-design.md:依赖与联调，第104行 | BT 依赖链本身无明显循环，但 I04 的生产方 SDL与消费方提交策略尚未对齐。前端仅发送 inventoryMode 时会缺少必填 allocationStrategy，导致 schema/codegen 后仍不能按文档直接联调，接口成熟度不足。 |
| TDD-B8 · 目标接口完整且一致 | F | /opt/document-eval/candidate/sprint1/tech-design/target-schema.graphql:WebhookSampleEventTypeEnum，第3324-3467行；/opt/document-eval/candidate/sprint1/tech-design/target-schema.graphql:WebhookEventTypeEnum 扩展，第35257-35270行；/opt/document-eval/candidate/sprint1/prd/prd.md:AC-18-5，第251行 | 新增事件已进入 Webhook 事件枚举和 Subscription，却未加入 WebhookSampleEventTypeEnum，无法在既有样例入口一致选择。目标 SDL还存在退款金额不可省略及 StockSettingsInput 必填兄弟字段与省略约定冲突，因而目标接口不完整一致。 |
| TEST1 · 需求与风险覆盖 | P | /opt/document-eval/candidate/sprint1/test-design/test-cases.v1.csv:TC001，行 2-6；/opt/document-eval/candidate/sprint1/test-design/test-cases.v1.csv:TC121，行 602-606 | TC001 至 TC121 连续覆盖 PRD 的 AC-01-1 至 AC-20-7，包括核心业务、权限、安全、失败、边界、兼容、并发幂等、迁移恢复及跨前后端契约；P0 资金、库存、认证和通知风险均有专项用例。 |
| TEST2 · 用例内容与断言质量 | P | /opt/document-eval/candidate/sprint1/test-design/test-cases.v1.csv:TC053，行 262-266；/opt/document-eval/candidate/sprint1/test-design/test-cases.v1.csv:TC111，行 552-556 | 用例普遍将前置数据、操作和编号预期对应起来，并断言余额、交易、索引、权限、事件、持久记录及外部调用次数等真实业务结果，而非仅检查请求成功、字段存在或页面显示。 |
| TEST3 · 可执行性与独立性 | F | /opt/document-eval/candidate/sprint1/test-design/test-cases.v1.csv:TC019，行 92；/opt/document-eval/candidate/sprint1/test-design/test-cases.v1.csv:TC014，行 67 | 未定义所谓“标准本地验收环境”的具体版本、配置、负载和观察工具，也未给出受控 DNS、公网图片端、PSP、Webhook、故障注入及持久数据检查能力的准备方式或不可用标记。大量用例仅把这些能力写成抽象前置条件，因此不同执行者无法稳定复现，外部条件是否满足也不可判定。 |
| TEST4 · 追踪与跨产物一致性 | P | /workspace/templates/test-cases.md:行 10-18；/opt/document-eval/candidate/sprint1/test-design/test-cases.v1.csv:表头及 TC097，行 1、482 | CSV 表头、编号、模块名称和优先级符合模板；每条用例至少关联一个有效 AC，并在适用处关联 FD、BD、I。接口名称、枚举、错误语义和预期结果与冻结 PRD及已接受技术设计保持一致。 |

## 口径

- 每个冻结评分项只有 P/F，不给半分。
- `reward` 只负责 Harbor 数值传输；分组分数、关键项和逐项证据必须同时保留。
- Judge 或基础设施失败会使评测报错，不会记为候选 0 分。
