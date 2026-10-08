# 输入与审计数据契约

本文与 [workflow.md](workflow.md) 配套，定义批量运行的统一交接格式。Markdown 保存产品表达和审计说明；JSON/CSV 保存身份、索引和关联。二者共同交付，不用结构化清单替代 PRD。

## 1. 格式、路径与 ID

- JSON 使用 UTF-8；没有值时用 `null` 或空数组，不使用虚构值。模板占位字符串运行前必须替换。
- CSV 使用 UTF-8、首行字段名和标准 CSV 转义。逗号、引号和换行通过 CSV 引号转义；不要用手工字符串拼接写入。
- CSV 中多 ID 字段使用分号分隔。ID 本身不得含分号；无关联时为空，不填 `N/A` 冒充实体。
- 配置中的输入路径相对 `inputs.json` 所在目录解析；运行输出路径相对 `run_root`。保存物理解析位置与输入指纹，避免符号链接或挂载变化混淆身份。
- 源码中的路径相对对应仓库快照根；patch 的行号相对固定哈希的 patch。证据中必须说明定位类型，不能只填一个不知属于哪个文件的行号。
- `E-000001` 为证据 ID，`C-000001` 为变更单元 ID，`F-000001` 为审计发现 ID；它们在同一个 case 的后续修订中稳定。
- `R01`、`AC-01-1` 为默认需求与验收 ID；两位是最小宽度而非数量上限。指定模板可配置其他语法，但全套产物统一，发布后不重排或复用。
- 多 case 的全局身份为 `case_id + local_id`。一个 case 的不同 run 使用相同实体 ID，并记录版本/继承，不凭不同 run_id 重编全部编号。

## 2. inputs.json

模板：[inputs.json](templates/inputs.json)。

| 字段 | 含义 |
| --- | --- |
| schema_version | 此输入结构版本，当前为 `reverse-extraction-input-v1` |
| case_id / run_id | case 稳定身份和此次运行唯一身份 |
| run_root | 已配置的产物及隔离工作根；不得指向只读输入根 |
| archive | 最终 Harbor 包的证据归档要求、包位置和包内相对路径；第一条执行时包位置可暂未确定，归档要求不可省略 |
| parent_run | 修订/恢复时的明确父运行；首次运行为空 |
| input_scope | 必须为 `full_unpruned`；不将剪枝结果替代完整目标 |
| business_sources | 原始业务说明/明确产品决定及其来源；没有时为空 |
| reference_documents | 已有 PRD/说明的路径、版本与用途；只作为参考 |
| repositories | 每个源码仓库的起点、目标、层与视图信息 |
| repository_links | 已知生产者/消费者、接口与版本配对证据；未知关系在 S1/S2 补充 |
| prd_template | 模板位置与 SHA-256；默认模板也必须冻结 |
| priority_policy | P0/P1/P2 等定义及来源；没有明确规则时记录 null |
| preparation / validation | 能否物化、生成或运行测试，以及配置命令与环境 |
| max_repair_rounds | 非负整数；默认 3，不限制证据分析的覆盖范围 |

每个 `repositories[]` 至少包含：

| 字段 | 含义 |
| --- | --- |
| repo_id | case 内唯一仓库 ID，不依赖目录名 |
| source_root | 已有仓库或快照目录，可为 null；不能为空目录冒充源码 |
| upstream_baseline | 完整 commit/tree 或等效内容身份，实际不可读时标记声明来源 |
| production_baseline | 业务比较起点 B 的身份与已包含层；不同于 upstream 时说明准备方式 |
| full_target | 完整目标的身份及是否包括测试；不得使用剪枝树 |
| layers | E/G/T patch 的路径、SHA-256、职责和顺序；无某层时省略该条 |
| views | 可用静态/物化视图、code/test/combined tree，或等效内容身份 |
| generated_artifacts | 权威输入、生成配置、工具、输出和消费者；S1 可以补全未知项 |
| interface_adapters | 协议类型及合同提取/对比方法；不强制特定协议 |
| test_adapters | 测试框架、ID 规则、静态检索与可选运行方法 |

未拆分 patch 的 `role` 填 `mixed`，在清单中分析其真实内容。E/G/T 只是职责标签，不根据文件名推定。

身份对象包含 `commit`、`tree`、`content_sha256`、`declared_by` 和 `verified`。至少存在一种可核对的内容身份；仅 commit 而有工作树改动时还需有效内容指纹。暂未确认的对象标 `verified=false`，S0 核验后更新，不仅因为输入提供了 SHA 就标 true。

命令以 `argv` 数组、`cwd`、输入、输出和预期检查组成。环境字段登记镜像 digest 或等效运行环境及版本；缺少运行环境时保留静态流程，不制造运行成功。工作流目录不执行模板中的命令。

`preparation` 和 `validation` 指定执行能力范围，不替代真实权限。独立目录物化属于本流程准备；正式评分校准、修改原包、发布和推送属于后续任务。

### 2.1 可选数组的条目结构

下面定义的是通用字段，不要求项目提供不存在的接口、生成器或测试框架。空数组表示没有已登记条目；S1/S2 仍需调查它是真正不适用，还是尚未提供。

| 数组 | 每条内容 |
| --- | --- |
| business_sources | `source_id, path, sha256, locator, authority`；authority 说明原始请求、明确决定或背景材料 |
| reference_documents | `path, sha256, version, scope, purpose`；scope 明确 full/pruned/unknown |
| layers | `layer_id, role, path, sha256, from_identity, to_identity, apply_order`；role 为 E/G/T/mixed，顺序从 1 起 |
| views | `view_id, kind, path, identity, included_layers, verified`；kind 为 upstream/baseline/code/test/combined/evaluation_base/evaluation_target，included_layers 按实际顺序列 layer_id |
| generated_artifacts | `generator_id, input_paths, config_paths, output_paths, consumer_paths, tool_version, command_id, verification`；未知字段可 null，不能伪造链路 |
| interface_adapters | `adapter_id, protocol, source_paths, extraction_command_id, comparison_method`；静态人工对比可无命令 |
| test_adapters | `adapter_id, framework, source_paths, id_normalization, collection_command_id, run_command_id`；只做静态分析时命令可 null |
| repository_links | `producer_repo_id, consumer_repo_id, contract, evidence_ids, pairing_status`；pairing_status 为 verified/declared/unknown/conflict |
| preparation.commands / validation.commands | `command_id, argv, cwd, input_paths, output_paths, environment_id, purpose, expected_check`；命令 ID 在本次配置内唯一 |
| validation.existing_reports | `path, sha256, observation, repo_views, test_layer_ids, selection_identity, runner_identity, environment_identity, limitations`；无选择集则 selection_identity 为 null |

视图身份复用上述 identity 对象。命令路径按配置解析，仓库相对路径以相应 repo_id 的快照根解析；运行时在日志中保存展开后的真实位置。shell 脚本作为 argv 中的明确程序参数调用，不能把输入文案直接拼入 shell 命令。

`priority_policy` 非空时使用 `definitions, source_evidence_ids, confirmed`；`validation.environment` 非空时使用 `environment_id, kind, immutable_identity, tool_versions, limitations`。只有相同的环境身份和实际条件，才支持运行结果复用。

### 2.2 状态和 manifest 中的条目

- `run-status.findings[]` 使用 `finding_id, type, status, blocking, affected_ids, report_locator`，与报告中的发现一致。
- `last_checkpoint` 使用 `checkpoint_id, worklog_locator, input_fingerprint`，`remaining_work[]` 列出可操作的剩余项。
- `artifact-manifest.input_files[] / output_files[]` 使用 `path, bytes, sha256, role`；input path 相对配置根，output path 相对 run_root。需要随包审核的输入另外登记归档副本，不依赖输入原路径可访问。
- `artifact-manifest.archived_sources[]` 使用 `source_path, source_sha256, archived_path, archived_sha256, archived_locator, role`；archived_path 相对 run_root，完整副本与片段分别计算哈希，来源定位继续保留。
- `source_snapshots[]` 使用 `repo_id, view_id, identity, included_layers, dirty_state`；dirty_state 为 clean/dirty/unknown，dirty 必须有实际内容身份。
- `parent_manifest` 非空时使用 `path, sha256`，不能仅根据父运行名称推定版本。
- `limitations[]` 使用 `finding_id, description, affected_ids, downstream_effect`，描述对后续剪枝或文档生成的实际影响。

`inputs.archive` 使用 `required, harbor_task_root, relative_path`；required 必须为 true，relative_path 默认 `golden-docs/evidence/reverse-extraction/<run_id>`，实际配置替换 run_id。harbor_task_root 未确定时可为 null，第二条 workflow 从交接和包内索引补充发布绑定，不修改冻结输入配置。

`artifact-manifest.archive` 记录 `required, relative_path, scope`，scope 为 full_unpruned；不包含包根 manifest 哈希。`run-status.archive_status` 为 pending/staged，分别表示尚未冻结、已冻结待随最终包归档。包内 `index.json` 的运行条目使用 `case_id, run_id, scope, run_path, artifact_manifest_sha256, parent_run_id, archive_status, used_for_pruning`；已验证归档填 archived_verified。

## 3. evidence-index.csv

模板：[evidence-index.csv](templates/evidence-index.csv)。一行表示一个可定位证据片段，完整文件可支持多个片段。

| 字段 | 要求 |
| --- | --- |
| evidence_id | 唯一 `E-*` |
| repo_id | 仓库内证据必填；全局业务说明可空 |
| kind | `production / test / interface / migration / generator / generated / environment / resource / business / git / runtime / document` |
| view | `upstream / baseline / target / evaluation_base / evaluation_target / global` |
| source_path | 冻结文件、patch 或报告的真实位置 |
| source_sha256 | 该源文件哈希；目录或源码快照另在 snapshot_identity 记录内容身份 |
| archived_path / archived_sha256 | 随包证据副本或所引用包内文件的相对位置和哈希；路径以最终 `<run_id>/` 为解析根，不能指向 scratch 或宿主机绝对路径 |
| archived_locator | 副本中的位置；片段副本的行号不冒充原来源行号 |
| snapshot_identity | commit/tree、等效内容身份或报告所绑定的被测身份 |
| locator | `source:...`、`patch:...`、`schema:...` 等定位，包含符号/行号/hunk/测试 ID |
| excerpt_or_summary | 保留条件、否定、例外和结果的短证据；避免仅贴文件名 |
| observation | `static / historical_run / current_run / statement` |
| verification | `verified / declared / inaccessible / conflict` |
| limitations | 未读上下文、未运行、版本不明、环境约束等；没有则空 |

`verified` 说明该证据来源与陈述已核对，不表示系统行为已经运行验证。Git 背景或声明单独不足以证明生产行为。

## 4. change-inventory.csv

模板：[change-inventory.csv](templates/change-inventory.csv)。一行表示一个内聚变更单元；S1 的路径母集及原始 diff 保存在 sources 并作为索引证据引用，随最终 Harbor 包归档。可在 scratch 计算，再将作为证据的结果转存。

| 字段 | 要求 |
| --- | --- |
| change_id | 唯一 `C-*` |
| repo_ids / paths | 涉及仓库/相对路径；混合单元可多值，paths 用 `repo_id:path` 避免多仓歧义 |
| locators | 对变化范围的明确定位，带 repo_id 和来源 diff 身份；不能依赖列表位置猜配对 |
| change_kind | `add / modify / remove / rename / mixed`；权限、链接、二进制变化在描述中明确 |
| classification | 使用下表分类 |
| base_behavior / target_behavior | 前后行为；非产品项填前后技术目的，未知明确标未确认 |
| rationale | 产品意义或不作为产品需求的理由，不能只复述分类名称 |
| evidence_ids | 至少一个有效 E ID；涉及前后判断须两侧证据或确切 absence 依据 |
| dependency_change_ids | 输入、配置、消费者等关联 C ID；派生项应能沿此链定位输入 |
| requirement_ids | 产品项必填实际 R ID，非产品项可关联受支撑需求 |
| analysis_status | `pending / analyzed / blocked` |

分类定义：

| 值 | 含义与审计要求 |
| --- | --- |
| product | 有使用者可观察的行为变化，必须映射 R |
| internal | 内部重构/环境/基础设施；说明为何未形成独立产品行为 |
| derived | 从明确输入派生的输出；登记输入、配置与合同分析，未知入口不能算链路完整 |
| resource | 导入/随仓库存储资源；分析消费者和产品影响，不能以“资源”略过行为变化 |
| no_semantic_change | 排版、机械重排等；必须有判断依据 |
| unresolved | 尚未确认产品意义或无法分析，不算完成覆盖 |

一个条目不能同时把“产品变化”和“纯机械输出”混写；必要时拆分，或者在派生链中单独登记产品合同变化。

## 5. requirement-catalog.csv

模板：[requirement-catalog.csv](templates/requirement-catalog.csv)。一行一条 R，AC 具体文本保存在 PRD。

| 字段 | 要求 |
| --- | --- |
| requirement_id / title / domain | 稳定 ID、标题和业务域，与 PRD 一致 |
| change_type | `new / behavior_change / bug_fix / deprecation_removal / compatibility / mixed` |
| actors / user_goal | 受影响角色及有依据的目标；推导明确标注 |
| source_type | `business_statement / reverse_extracted / mixed` |
| source_evidence_ids | 有效 E ID，不引用不存在的 Instruction |
| change_ids | 对应 C ID；没有行为变化的既有能力不能作为新增 R |
| depends_on / related_to | R ID；空列表不表示已经证明不存在关系 |
| priority / priority_basis | 模板优先级、已明确来源或暂定理由 |
| ac_ids | 正文中的全部 AC ID，不直接承载 AC 自然语言 |
| evidence_status | `supported / inferred / conflict / missing` |
| status | `draft / confirmed / superseded` |
| supersedes_ids | 修订中的拆分/合并关系；不重用历史 ID |
| unresolved_findings | 尚需处理的 F ID |

`inferred` 用于背景、角色或意图推导，必须说明边界。关键行为不能仅凭推导标 confirmed。`superseded` 保留历史记录，审计当前活跃需求时按明确继承关系判断，不计重复。

## 6. traceability.csv

模板：[traceability.csv](templates/traceability.csv)。一行表示 C/R/AC 与一个证据的具体关系，不把多个场景都压成“此文件覆盖 R01”。

| 字段 | 要求 |
| --- | --- |
| requirement_id | 活跃或明确历史 R ID |
| ac_id | 行为级映射填 AC ID；需求背景/依赖级可空 |
| change_id | 对应变化；明确业务决定或上下文证据可以空，但不能替代 R 的变化依据 |
| evidence_id | 一个有效 E ID |
| relation | `baseline / supports / test_expectation / runtime_observation / context / contradicts` |
| coverage | `full / partial / gap`；仅针对这一条关系，不等于整个需求完成 |
| rationale | 证据具体支持或反驳的条件、结果及限制 |
| finding_id | 缺口/冲突的发现编号，没有则空 |

每个 AC 至少有生产/公开合同/数据行为的支持证据；测试存在时登记它实际验证的范围。`context`、Git 标题或测试文件名单独不能成为 AC 的充分支持。非产品 C 通过变更清单解释，不必为了填追踪表虚构 R。

## 7. 审计、状态与交付身份

报告模板：[audit-report.md](templates/audit-report.md)。每个发现含 ID、类型、影响、来源定位、处理、证据、状态和是否阻塞。

发现类型至少区分 `input_mismatch / unmapped_change / unsupported_requirement / semantic_conflict / duplicate / test_gap / generator_gap / priority_pending / validation_limit / format_reference_error`。解决需附修正证据；接受非阻塞限制需写理由、影响和明确的审计处理主体。声明“已知”不能替代解决。

状态模板：[run-status.json](templates/run-status.json)。阶段状态使用 `pending / running / completed / blocked / not_run`，完成检查使用 `not_run / passed / failed / blocked`。交付状态使用 workflow 中定义的四种值；`completed` 不等于审核通过。

统计定义：

- `changed_paths_total`：按仓库和路径去重的来源路径数，重命名两侧可定位并注明计数约定。
- `change_units_total`：全部 C 单元数；不能把处理失败的单元删出分母。
- `unresolved_units`：分类 unresolved、分析未完成或阻塞的单元数。
- `active_requirements`：未被明确取代的 R 数。
- `active_acs`：当前 PRD 中独立 AC ID 数。
- `blocking_findings`：未解决阻塞发现数。
- `test_gaps`：尚未被自动测试充分支持的 AC 数；不能用测试文件数代替。

以上计数用于查漏，不是语义质量得分。

产物 manifest 模板：[artifact-manifest.json](templates/artifact-manifest.json)。登记流程与模板身份、父版本、实际输入/输出文件路径、字节数和哈希；大型源码身份引用冻结快照。manifest 和运行日志不得证明自己未做过的验证。manifest 不自包含自身哈希，避免循环。

`ready/ready_with_limits` 都要求完整盘点和语义审核通过、无 unresolved 单元、无未解决阻塞；差别是约定验证和非阻塞缺口的实际完成程度。覆盖母集不完整时必须是 incomplete 或 draft_blocked。

## 8. 冻结前结构核对

使用可用 JSON/CSV 解析器和文件哈希工具核对以下规则；当前提供的是契约与模板，没有附带自动验证器：

1. JSON/CSV 可解析，字段、枚举和计数符合本文件定义。
2. E/C/R/AC/F ID 唯一、引用存在；ID 多值按分号解析，不模糊匹配。
3. product C 对应活跃 R；每个活跃 R 对应产品变化，每个 AC 有支持关系。
4. PRD 的 R/AC 与目录一致；依赖与 supersedes 不自指，不引用无解释的历史项。
5. 证据定位对应固定来源，文件哈希一致；运行证据与被测身份和条件匹配。
6. ready 状态与发现、未完成单元和实际检查结果一致。
7. 输出清单文件确实存在；所有输入未被修改；无字面占位符残留。
8. 所有结论证据、原始差异与必要修订有归档副本或固定包内引用；相对路径可从最终 run 根解析，副本哈希正确，不依赖临时工作区。
9. 第二条 workflow 完成打包时，包内运行索引与实际 run manifest 一致，归档状态为 archived_verified；未剪枝证据范围与活动 Golden 范围明确区分。

结构核对后仍需执行 workflow S5 的语义审核；字段齐全不证明行为忠实。
