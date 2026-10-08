# Golden 文档输入、追踪与交付契约

配套 [workflow.md](workflow.md)。JSON/CSV 是统一中间格式，项目原生协议及指定文档模板保持其自身格式；本目录没有实现通用 schema 导出器、测试解析器或自动审核器。

## 1. 格式、路径与 ID

- UTF-8 JSON/CSV，使用真实解析器和标准 CSV 转义。多 ID 用分号分隔，无关联留空；未知值使用 null 或明确状态，不能填零冒充已运行。
- 配置路径相对 inputs.json，运行产物相对 run_root，包内文档/归档路径相对明确的 package_root。证据保留来源 path/SHA/locator 和归档副本 path/SHA/locator，不混用片段与原文件哈希。
- 沿用第一/第二条 R/AC 和决定 ID，不重排、不复用。默认设计 FD/BD、工程任务 BT、接口 I、产品用例 TC；配置的其他模块可以指定独立前缀。
- `DU-000001` 为行为单元，`TU-000001` 为自动测试单元，`GU-000001` 为独立守卫边界，`DF-000001` 为文档发现，`DOC-001` 为文档计划项。case_id+local_id 为全局身份。
- 发布后新编号递增；分拆/合并保存父关系。历史 R/AC 不作为活动 ID 使用；非目标 GU 与活动 AC 分开。
- 自动测试 canonical_id 是上游的精确不透明键，参数/文件/suite/重名上下文与 raw_id 保留；不要重新按相似标题发明对应关系。
- `evidence_refs` 使用 `run_id:local_id` 或固定文件的包内 path/SHA/locator；引用跨运行同名 ID 时必须带 run_id。

## 2. inputs.json

模板：[inputs.json](templates/inputs.json)。

| 字段 | 内容 |
| --- | --- |
| case_id / run_id / run_root | 独立 case、文档运行与隔离目录 |
| parent_document_run | 修订时的明确旧运行，首次 null |
| source_release | 包位置、发布绑定、runtime/evidence manifest 的实际 path/SHA 与状态 |
| active_prd / scope_decisions | 第二条最终文件及身份；活动 PRD 不从旧历史 PRD选择 |
| repositories | 生产起点 B、目标 D、G/T、生成输入/消费方及可用源码视图 |
| evaluation_refs | C/D、selection、calibration、原报告、invariant 和已接受限制 |
| document_profile | 适用模块、模板、输出文件、目标协议及检查方法 |
| preparation / validation | 实际能力、环境和可执行命令；默认只静态检查 |
| audit_policy | 必需覆盖/检查、允许的非阻塞限制及依据；不自动接受 gap |
| archive | required=true、最终 run_path 及保留历史 |
| publication / max_repair_rounds | 默认不压缩/提交/推送/外部发布，修复轮数默认 3 |

### 2.1 条目结构

| 对象/数组 | 字段 |
| --- | --- |
| file_identity | `path, sha256, bytes, role`；来源 locator 可附加 |
| source_release | `package_root, release_id, release_binding, runtime_manifest, evidence_manifest, status`；三份清单用 file_identity |
| repositories[] | `repo_id, source_root, baseline_identity, target_identity, code_patch, test_patch, generated_artifacts, consumer_views` |
| snapshot_identity | `commit, tree, content_sha256, verified`；至少一种有效内容身份，未核验不标 true |
| evaluation_refs | `composition, selection, calibration, reports, invariants, limitations`；composition 固定共同 T；文件引用用身份对象 |
| document_profile.modules[] | `module_id, role, design_id_prefix, task_id_prefix, repo_ids, template, output_path, required, applicability_basis` |
| document_profile.interfaces[] | `boundary_id, protocol, provider_repo_id, consumer_repo_ids, authoritative_inputs, source_identity, output_path, required, extraction_command_id, validation_command_ids` |
| command | `command_id, argv, cwd, input_paths, output_paths, environment_identity, expected_check`；不拼接不可信文本成 shell |
| generated_artifacts[] | 权威输入/配置/工具、输出/消费者及原运行身份，沿用第二条记录 |
| audit_policy | `required_checks, required_automatic_coverage, allowed_limits, decision_source`；必需自动覆盖可列 AC/GU/合同或明确规则 |

模板身份保留原 path/SHA 与归档副本。document_profile 还指定 `interface_contract_template, test_cases_template, test_cases_output, test_cases_columns, document_manifest_path`。既有模板不适用的字段保留理由，不改变模板的硬性要求。

基础输入配对、母集完整性、双向语义、模板/引用、归档/清单及可见性检查由 workflow 强制要求，不能因为 required_checks 空数组而省略。配置只补充项目必需检查；模块/协议不适用需明确依据，不删除共同审计要求。

非网页/服务端模块可使用 [module-design.md](templates/module-design.md) 或指定原生模板。TDD 和 Test 的交付说明模板分别为 [design-readme.md](templates/design-readme.md) 与 [test-readme.md](templates/test-readme.md)，记录版本、适用文件、来源与实际验证范围。

## 3. document-plan.csv

模板：[document-plan.csv](templates/document-plan.csv)，一行一个文档/协议交付项。

| 字段 | 要求 |
| --- | --- |
| document_id / module_id / document_type | DOC ID、承接模块和 design/contract/native_interface/test_design/summary |
| required / applicable | true/false 与 true/false/unknown；必交不可擅自判 false |
| applicability_basis | 实际架构与模板要求证据 |
| template_path / template_sha256 | 指定模板身份，原生生成协议可无模板但需生成方法 |
| output_path | 相对 run_root；manifest 另映射包内位置 |
| requirement_ids / check_refs | 活动范围及适用结构/语义/协议检查 |
| status | pending/written/verified/not_applicable/blocked |

not_applicable 需要理由和明确政策；unknown 不算完成。

## 4. behavior-inventory.csv

模板：[behavior-inventory.csv](templates/behavior-inventory.csv)。一行一个实际内聚行为/实现目的，人工生产变化、公开合同和其他相关变化必须有归属。

| 字段 | 要求 |
| --- | --- |
| behavior_id | DU ID |
| repo_ids / source_locators | 仓库和 B/目标/patch 固定定位，跨仓带 repo_id |
| classification | active_behavior/baseline_context/internal_support/derived/removed_boundary/unresolved |
| baseline_behavior / target_behavior | 前后事实，未知明示，不凭删除/新增行孤立推定 |
| requirement_ids / ac_ids | 当前活动 ID；removed_boundary 不引用历史 ID 为活动 AC |
| design_ids / interface_ids / guard_ids | 具体承接与边界，确不适用可以空 |
| evidence_refs / rationale | 来源及分类/归属理由 |
| analysis_status | pending/analyzed/blocked |

internal_support/derived 说明所支撑输入/模块/消费者，不能通过分类隐藏未审公开合同。unresolved 不计覆盖完成。

## 5. boundary-register.csv

模板：[boundary-register.csv](templates/boundary-register.csv)，一行一个接口或独立守卫边界。

| 字段 | 内容 |
| --- | --- |
| boundary_id / kind | I 或 GU；kind 为 interface/pruning_guard/other_invariant |
| protocol / change_type | 实际原生格式与 add/change/deprecate/remove/unchanged_guard |
| provider / consumers | repo/path/symbol 或外部调用方，不能只写“前后端” |
| design_ids / active_ac_ids | 活动承接，没有活动 AC 的独立守卫明确留空 |
| scope_decision_refs | 删除/部分保留边界的明确决定 |
| source_definition / target_definition | 固定来源与完整目标定义的位置/身份 |
| compatibility_basis | 相同、合法超集/快照、过渡或未确认的证据 |
| test_unit_ids / evidence_refs | 真实断言和合同/源码证据 |
| status | pending/verified/gap/conflict/not_applicable |

接口无变化但模板必交时输出章节说明；没有边界不能编造 I。GU 的独立用例在 guard-cases 设计，不能用已删除 AC 填产品 CSV。

## 6. test-inventory.csv

模板：[test-inventory.csv](templates/test-inventory.csv)。母集为最终 T 的全部变化，加冻结 selected/invariant 引用的现有测试；一行一个语义一致的测试或参数族及执行依赖。

| 字段 | 内容 |
| --- | --- |
| test_unit_id / repo_id / suite_id | TU 与框架上下文 |
| source_kind | patch_change/selected_existing/invariant_existing/mixed |
| canonical_ids / source_locators | 全部精确成员或固定成员映射路径，含 patch 增删两侧定位 |
| classification | active_behavior/baseline_regression/execution_support/pruning_guard/removed_history/unresolved |
| assertion_summary | 输入、前提、断言与行为边界；fixture 写消费者/目的 |
| requirement_ids / ac_ids / guard_ids / tc_ids | 合适关系，非产品项不强填 AC |
| necessity_basis | 需求、保留合同、共享风险、数据或执行消费者依据；P2P 名称单独不足 |
| evidence_refs | patch/现有测试/消费者/原始报告身份 |
| execution_status | current_pass/historical_pass/nonpass/not_run/not_applicable；原始状态另保留，不把全文读取当执行 |
| analysis_status | pending/analyzed/blocked |

removed_history 仅用于 T 中已删除的测试；目标仍收集的删除功能正向测试是 conflict，不能归入 removed_history。测试族可聚合但成员必须完整、断言语义相同。

## 7. traceability.csv

模板：[traceability.csv](templates/traceability.csv)。一行是一种具体关系，每个活动 AC、DU/TU 和文档单元都应能复核去向。

| 字段 | 要求 |
| --- | --- |
| trace_id | 唯一稳定关系 ID |
| requirement_id / ac_id | 当前活动范围，独立 GU/内部/回归关系可空 |
| design_id / boundary_id / tc_id | 具体技术/接口/测试设计单元，不适用留空并给理由 |
| behavior_id / test_unit_id | 具体 DU/TU，非双方均有不强填 |
| relation | implements/describes/designs_test/automatically_checks/regression_support/execution_support/guard_checks/contradicts |
| coverage | full/partial/gap/conflict/not_applicable，针对这一关系而非总体 |
| verified_conditions / uncovered_conditions | 明确前提、断言、结果和缺少的边界 |
| evidence_refs / finding_id | 固定证据/实际发现，没有问题可空 |

full 自动覆盖要求断言确实支持引用场景，不以测试名/路径/总分推定。TC 设计覆盖、自动覆盖和运行状态分别登记；不能一列“通过”混写三者。

## 8. 产品 TC 与独立 GU 用例

产品模板：[test-cases.v1.csv](templates/test-cases.v1.csv)，列为：

`用例编号,一级模块,二级模块,用例标题,覆盖,优先级,前置条件,操作步骤,预期结果`

TC 编号默认 TC001，至少一个活动 AC；覆盖多个 AC 时步骤/预期分别对应。模块/需求名称与 PRD 相同，版本写 Test/README。优先级遵守原模板规则。CSV 用标准引号处理多行、逗号和双引号，不在首行前加 Markdown。

独立模板：[guard-cases.csv](templates/guard-cases.csv)，字段为 `guard_case_id,guard_id,title,preconditions,steps,expected_results,test_unit_ids,coverage,evidence_refs`。它设计 GU 的可观察条件，至少一个真实 GU；其设计不等于自动守卫已实现或已执行。

默认测试设计不产生 test-results、QA verdict 或部署结论。引用已有自动化报告不等于执行了 CSV TC。

## 9. 审核、状态与 manifest

模板：[audit-report.md](templates/audit-report.md)、[run-status.json](templates/run-status.json)、[artifact-manifest.json](templates/artifact-manifest.json)、[golden-manifest.json](templates/golden-manifest.json)、[worklog.md](templates/worklog.md)。

阶段状态 pending/running/completed/blocked/not_run，检查 not_run/passed/failed/blocked；不适用检查单独记录理由并按配置移出 required_checks，不冒充 passed。

document_status 为 ready/ready_with_limits/blocked/incomplete，delivery_status 为 incomplete/blocked/staged，archive_status 为 pending/staged。staged 只说明可归档，DOC8 包级结果在外层索引/绑定，不回写冻结 run。

计数：active_requirements/active_acs/design_units/interface_boundaries/product_cases/guard_cases 是去重活动实体数；behavior_units/test_units 保留完整母集；unresolved_units 包含未分析与阻塞；automation_full_acs/automation_partial_acs/automation_gap_acs/automation_conflict_acs 按每个 AC 的汇总语义互斥分类。inactive/历史项不进入 active 分母。计数不是质量评分。

全部 AC 汇总后，四种 automation_*_acs 之和必须等于 active_acs；同一 AC 的多条关系先按实际场景汇总，存在关键矛盾则归 conflict、没有自动断言则 gap、覆盖不足为 partial，不能因某条关系 full 就把整体归 full。产品 TC 设计覆盖独立核对，不使用此自动化计数替代。

发现 DF 条目至少含 `finding_id, type, affected_ids, evidence_refs, blocking, action, decision_source, status, closure_evidence`。type 区分 input_mismatch/template_gap/unmapped_behavior/unsupported_design/contract_conflict/test_gap/unsupported_test/incomplete_analysis/reference_error/validation_limit；status 为 open/resolved/accepted_limit，接受限制需依据及下游影响。

### 9.1 运行 manifest

`workflow_identity` 保存方法/契约/模板指纹；`source_release_identity` 保存输入旧绑定副本哈希；`input_files/output_files` 项为 path/bytes/SHA/role；`archived_sources` 保存原来源和归档片段身份；`archive` required=true、run_path、scope=golden_documents；`parent_manifest` 为固定父版本或 null。

run 不包含自身哈希、外层当前清单/绑定/最终包副本。input_files 指向冻结的来源副本，不能引用随后会被本流程重写的当前发布绑定。

### 9.2 Golden 文档 manifest

文档清单管理文档与输入配对；包含：

- document_set_id、case_id、版本、document_status、active_prd 的包内 path/SHA。
- source_release 的旧 release_id/绑定副本身份，以及原 runtime/patch/selection/目标身份。
- documents[]：document_id、type、module、package-relative path、bytes、SHA、模板身份、required/applicable。
- coverage_summary、validation_summary：范围、语义、自动化与实际运行分别说明。
- limitations：发现编号、影响、依据与处理。

不包含自身、当前 evidence manifest、当前 binding 或本 run manifest 哈希。活动 PRD作为已存在输入和交付文件都核对指纹，不在第三条原地修订。

## 10. 包级交付与发布扩展

模板：[documentation-audit.md](templates/documentation-audit.md)、[evidence-index.json](templates/evidence-index.json)、[release-update.json](templates/release-update.json)。

golden-documents/index.json 条目为 `case_id, run_id, run_path, scope, artifact_manifest_sha256, parent_run_id, archive_status, document_status, document_set_id, used_for_delivery`；scope=golden_documents，实际归档后 archived_verified。

沿用第二条 release-binding 的所有运行、范围和评测字段，新增 `documentation` 对象：golden_manifest path/SHA、document_set_id、document_status、run identity、包级审核和限制。新版 evidence manifest 覆盖三条 workflow 的记录、索引、TDD/Test、活动 PRD、Golden 文档清单及包级审核。

`release-update.json` 是本流程的更新契约模板，不是可替代完整 binding 的独立发布答案。记录 `parent_release, documentation, preserved_runtime, new_evidence_manifest, checks, status, limitations`；据此生成完整新 binding，不能删除旧 implementation/evaluation/visibility。

父发布绑定保存为 sources 的普通证据文件，可以被新清单哈希；当前 binding 不参与指向自身的哈希关系。外部归档/Git/发布系统核验当前绑定本身。旧 evidence manifest 已在 sources 保存，新的运行证据清单不用回指当前 run 的外层 manifest。

包级 ready 要求原运行包仍有效、必需文档检查通过且文档状态 ready 或明确非阻塞的 ready_with_limits，全部三步归档/引用/可见性/清单检查通过。运行包验证与文档限制分别报告，不能让文档状态掩盖关键合同冲突。

## 11. 冻结前核对

1. JSON/CSV 可解析，所有字段、枚举、ID 和路径符合契约，模板占位符已填。
2. 活动 R/AC 全部有技术/测试设计去向，文档必交与适用性不冲突，历史 R 不冒充活动 AC。
3. DU/TU 母集完整且无未分析项，所有内部/派生/回归/执行/守卫分类有事实依据。
4. 设计、I/GU、TC、原生完整定义与源实现/消费者一致，无无依据方案。
5. 自动覆盖 full 有真实断言，partial/gap/conflict 有具体说明及政策，不把运行总分变成 AC 覆盖证明。
6. 原生格式可解析且完整边界可追溯，快照差异和兼容依据明确，生成入口和结果配对。
7. 输入 PRD/G/T/选择没有被静默改动，引用的运行报告绑定同一版本/环境。
8. 输出和三步证据实际归档，哈希、相对路径和父版本有效，清单依赖无环。
9. 全部 required_checks 通过，document_status、计数、限制、外层发布状态与事实一致。
10. Agent 输入不含 Golden 和制作证据；结构检查之后执行真实语义审核。
