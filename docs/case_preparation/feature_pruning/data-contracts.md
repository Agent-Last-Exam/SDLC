# 功能剪枝与 Harbor 交付数据契约

配套 [workflow.md](workflow.md)。本契约描述制作时的统一中间产物，exporter 接收格式由配置适配；不能把本文 JSON 直接假定为所有 Harbor 版本通用的原生 schema。

## 1. 基础格式与引用

- JSON/CSV 使用 UTF-8、真实解析器和标准转义。CSV 首行字段名；多 ID 使用分号分隔。无关联留空，未知使用明确状态，不编造指纹或检查结果。
- 输入路径相对 inputs.json，输出路径相对 run_root；实际执行前展开并记录物理位置。归档路径相对最终 run 根或声明的包根。
- 沿用第一步 R/AC/C/E ID，不重排、不复用。`ST-001` 为阶段 ID，`IM-000001` 为影响项，`TL-000001` 为测试变化项，`PF-000001` 为本步发现。全局身份使用 case_id 和 local_id。
- 证据引用使用 `run_id:local_id` 或冻结文件的路径/哈希/locator；多来源同编号不能省略 run_id。
- 生产、测试和接口路径使用 `repo_id:path`。跨仓库关系不能根据列表位置猜配对。
- canonical 测试 ID 是归一化器生成的稳定不透明键；保留结构化 repo_id/suite_id/raw_id/参数与上下文。不要依靠分隔符拆 canonical_id 或相似标题匹配。
- 本目录只提供流程、契约和空模板，不提供通用 exporter、报告解析器或自动化验收实现。

## 2. inputs.json

模板：[inputs.json](templates/inputs.json)。

| 字段 | 内容 |
| --- | --- |
| case_id / run_id / run_root | case、运行及隔离目录身份 |
| parent_pruning_run | 持续剪枝时的明确父运行，首次为空 |
| extraction_runs | 第一条运行路径、manifest SHA、状态、限制与是否作为本次范围依据 |
| original_package | 完整输入包的路径、manifest 身份，未提供标准包时可 null |
| repositories | 每个仓库的 U/B/F、父 W、E/G/T 和准备方法 |
| scope_policy | 已明确政策文档的位置、哈希和确认来源 |
| apply_order_policy | 默认 require_commutative；ordered 要说明固定顺序及原因 |
| runtime | 镜像/环境身份、工具版本、网络/服务/seed、物化与生成/迁移方法 |
| evaluation | 共同 T 的 C/D 合同、候选全集、适配、排除/重跑政策和验证能力 |
| exporter | 标准工具版本、schema、builder、输出目录及命令 |
| archive | required=true、包内证据位置和保留运行 |
| publication | 是否生成压缩包、提交或外部发布；默认全部 false |
| max_repair_rounds | 非负整数，默认 3；耗尽记录阻塞，不改结果凑通过 |

### 2.1 结构化条目

| 条目 | 字段 |
| --- | --- |
| extraction_runs[] | `run_id, run_root, artifact_manifest_sha256, delivery_status, limitations, used_for_scope`；当前范围来源明确一个，历史父运行可多个 |
| repositories[] | `repo_id, source_root, upstream_identity, baseline_identity, full_target_identity, parent_identity, environment_layers, full_code_patch, full_test_patch, preparation_commands, generated_artifacts, migration_policy` |
| identity | `commit, tree, content_sha256, declared_by, verified`；至少一种有效内容身份，dirty 树还需实际内容身份 |
| patch | `path, sha256, role, from_identity, to_identity`；无该层时 null，混合层先分析拆分 |
| command | `command_id, argv, cwd, input_paths, output_paths, environment_identity, expected_check`；命令 ID 唯一，不拼接不可信文案成 shell |
| generated_artifacts[] | `generator_id, input_paths, config_paths, output_paths, consumer_paths, tool_version, command_id, rebuild_check` |
| migration_policy | `deployment_model, supported_origins, check_commands, evidence`；声明 fresh_from_baseline 或 supports_deployed_full_target 等真实场景 |
| runtime | `environment_identity, tool_versions, network_mode, service_commands, seed_identity, reuse_method, commands` |
| exporter | `tool_path, tool_sha256, version, harbor_schema, builder_root, output_root, source_state_command, export_command, runtime_manifest_path, evidence_attachment_method` |

`scope_policy` 包含 `path, sha256, confirmed, decision_source`；confirmed 不能仅由执行者偏好填 true。政策模板见 [scope-policy.md](templates/scope-policy.md)。

### 2.2 evaluation 的能力与政策

| 字段 | 内容 |
| --- | --- |
| composition | 固定 c=baseline+final_test_patch，d=baseline+final_code_patch+final_test_patch，same_test_patch=true；baseline 始终指生产起点 B |
| candidate_universe | `definition, source_paths, source_sha256, collection_commands, eligible_suites, excluded_categories`；原选择是参考，不替代候选全集 |
| existing_selection | 旧选择的路径、哈希、组合及适用性证据；没有则 null |
| adapters[] | `adapter_id, repo_id, suite_id, framework, version, collection_command, run_command, parser_identity, normalization_identity, id_mapping_method, status_mapping` |
| exclusion_policy | `path, sha256, confirmed, auto_exclude_target_failures`；auto_exclude_target_failures 必须为 false，逐项按政策审核 |
| rerun_policy | `path, sha256, max_attempts, triggers, reset_method, merge_rule`；不提供时不默认选择最佳结果 |
| missing_policy | `allow_classifiable_missing, required_evidence`；允许 missing 仍需逐 node 归属，不接受 collection 失败批量推定 |
| target_invariants | 独立守卫的身份、运行命令和要求；不强制存在这种类型 |
| case_validity | 有明确依据的最低可用性或评测条件；不凭流程编造最低 F2P 数量 |

框架 status_mapping 至少解释 pass/fail/skip/missing/error/not_run；raw 状态 retained，不覆盖原报告。归一化器须保留参数及区分重名测试的上下文，语义重命名需单独映射证据。

## 3. scope-decisions.csv

模板：[scope-decisions.csv](templates/scope-decisions.csv)。每行是一条需求或可独立删除子行为的决定，相关 R 可以多行。

| 字段 | 要求 |
| --- | --- |
| decision_id | case 内稳定唯一 ID |
| requirement_id / ac_ids | 第一条稳定 ID；需求级决定 ac_ids 可空，partial 必须列明子行为 |
| decision | retain/remove/partial/pending |
| mainline_relation | 与主体的具体关系或独立性说明 |
| protected_attributes | 安全、可靠性、数据、兼容、外部合同等实际保护属性 |
| dependency_ids | 必需的 R/AC/decision ID，指明类型避免歧义 |
| retained_behavior / removed_behavior | 行为边界，不能只填目录名；不适用可空 |
| rationale / evidence_refs | 判断理由与事实证据 |
| decision_source / approval_status | 明确来源及 confirmed/pending；范围内授权可引用同一政策，不逐条重复请求 |
| stage_id | 执行批次，不实施项可空 |

所有活跃 R 都有决定；只有已确认 remove 或 partial 的删除子行为进入实施。pending 不算默认授权。活动 PRD 的删除与保留必须能从这张表恢复。

同一 R 可用需求级默认决定加 AC 级细分，但每个活动 AC 必须有唯一有效决定。细分覆盖需求级默认时明确登记依据；同层重叠或互相矛盾的决定阻止冻结，不能按 CSV 行序覆盖。

## 4. impact-inventory.csv

模板：[impact-inventory.csv](templates/impact-inventory.csv)。一行是一项实际影响面。

| 字段 | 要求 |
| --- | --- |
| impact_id / decision_id / stage_id | 稳定 ID 及所属决定、阶段 |
| repo_id / path / symbol_or_contract | 固定仓库相对位置与行为定位 |
| layer | production/test/migration/interface/generator/generated/config/resource/document/environment |
| ownership | exclusive_remove/shared_keep/shared_split/derived_update/unresolved |
| consumers | 实际消费者，跨仓库带 repo_id；未知明确登记 |
| proposed_action / retained_contract | 要执行的变化与必须保留的行为 |
| evidence_refs | 来源指纹、E/C/定位 |
| verification_method / status | 对应命令/审核和 pending/verified/blocked/not_applicable |

每个生成结果关联输入、配置与消费者；每个共享项有保留验证。unresolved 删除项不能进入 P3。

## 5. stage-plan.csv 与阶段记录

模板：[stage-plan.csv](templates/stage-plan.csv)、[stage-record.md](templates/stage-record.md)。

| 字段 | 内容 |
| --- | --- |
| stage_id / decision_ids | 批次及覆盖决定 |
| depends_on | 必须先完成的 ST ID，循环需合并或明确中间兼容状态 |
| repo_ids / risk | 实际仓库及有依据的风险说明 |
| parent_snapshot / output_snapshot | 固定父/子身份引用；未完成输出为空 |
| required_checks / rollback_method | 检查命令/合同和隔离回退方法 |
| status | pending/running/accepted/blocked/abandoned；accepted 必须有实际验收报告 |

`snapshots.json` 保存每仓库父/子 commit/tree 或内容身份、增量/cumulative patch 的 SHA、检查和报告引用；可用项目已有快照格式，但不能只记 commit 标题。阶段记录包含完整尝试历史。

## 6. test-ledger.csv

模板：[test-ledger.csv](templates/test-ledger.csv)。用于各轮及最终校准；一行一项测试变化/分类，不用总量解释替代逐 ID 审计。

| 字段 | 内容 |
| --- | --- |
| ledger_id / stage_id | 稳定 TL ID，最终校准 stage_id 可填 calibration |
| repo_id / suite_id | 明确运行器与仓库 |
| old_canonical_id / new_canonical_id | 精确旧/新 ID，新增/删除一侧为空 |
| raw_id | 原框架 ID、参数和区分上下文；需要时引用完整结构化映射 |
| action | retained/removed_for_scope/shared_rewritten/renamed/reclassified/added/added_guard/policy_excluded/unresolved |
| old_class / new_class | f2p/p2p/invariant/excluded/unclassified；不存在的一侧为空 |
| c_status / d_status | pass/fail/skip/missing/error/not_run，不能用模糊成功词 |
| decision_id | 删除/改写必有范围决定；环境排除指政策决定，不冒充功能删除 |
| reason / evidence_refs | 具体语义、改动和运行证据 |
| policy_ref / resolution | 使用的政策和 pending/verified/blocked |

比较旧新 selection 时记录是否相同 B/T/ID/环境口径。不相同时，变化表描述重新分类，不能宣称这些 ID 均被剪枝删除。所有旧候选与新候选的并集都要有去向。

## 7. patch-manifest.json

模板：[patch-manifest.json](templates/patch-manifest.json)，这是中间身份格式，exporter 的原生 patch manifest 另生成并逐项核对。

每条 repo 包含：

- `repo_id, upstream_identity, baseline_identity, full_target_identity, pruned_identity`。
- `environment_layers[]`：固定 E path/SHA 和 B 已包含状态。
- `code_patch, test_patch`：`path, bytes, sha256, changed_paths, additions, deletions`。
- `views`：code_only、test_only、evaluation_base_c、evaluation_target_d 和每个已声明视图的身份。
- `apply_checks[]`：`order, actual_identity, expected_identity, status, report_ref`；status 为 passed/failed/not_run。
- `generated_artifacts` 和迁移检查引用。

stage increment 相对父 W，cumulative 相对固定 B，不能混用。文件数/行数统计说明原始 diff、去重最终差异或人工/生成内容口径；不能把累计 B→W 规模当成剪枝删除规模。

若补生成配置或环境适配，单独登记；比较未剪枝/剪枝量时说明两侧配置差异或一致化依据，不把工具修复计成产品功能增减。

## 8. selection.json 与 calibration.json

模板：[selection.json](templates/selection.json)、[calibration.json](templates/calibration.json)。

### 8.1 selection

- `identity` 绑定 B/G/T、C/D、环境、universe、normalization、parser 及范围哈希，不只存 case_id。
- `f2p[] / p2p[]` 每项为 `canonical_id, repo_id, suite_id, raw_id, context, result_refs`。context 保留参数/重名定位，result_refs 引用实际 C/D 记录。
- `counts` 与数组长度一致，canonical_id 唯一且两类互斥。
- `target_invariants[]` 单独记录，同样关联报告，不混入 F2P/P2P 分母。
- ID 排序按明确 normalization 规则固定；selection 自身 SHA 记录在外层 calibration/manifest，不写在自身内容中。

### 8.2 calibration

- `composition` 固定共同 T；`identity` 保存实际准备树及输入文件/工具身份。
- `universe` 保存候选定义、文件/collection 指纹、总数及所有候选去向。
- `policies` 保存排除、missing、重跑和 case 有效性政策指纹。
- `reports[]` 保存 phase、path/SHA、被测身份、环境、观察方式 current/historical、覆盖范围、原始/解析报告和合并来源。
- `excluded[]` 保存 node、C/D 原状态、政策、事实、影响、处理主体和证据；非通过不自动进入此数组。
- `unresolved[]` 未归属或不可靠的结果，非空阻止校准冻结。
- `selection_identity` 保存源 selection 及 exporter 转换版本的 path/SHA、逐项等价检查。
- `verification` 保存 C P2P、C F2P 非通过、D F2P/P2P、守卫、grader、缺失/skip/解析错误和声明检查结果。

counts 初始为 null，不把未运行当成零失败。`result_refs` 真实对应 node 和条件，不能仅引用一个总体通过报告。

最终共同测试候选必须满足 `candidate_count = classified_count + excluded_count + unresolved_count`，classified_count 等于 F2P+P2P；Target-only invariant 在独立集合中计数。历史被删测试仍留在 ledger，不移入最终候选分母；排除项不能从分母和审计中一起消失。

## 9. 状态与运行 manifest

模板：[run-status.json](templates/run-status.json)、[artifact-manifest.json](templates/artifact-manifest.json)、[final-audit.md](templates/final-audit.md)、[worklog.md](templates/worklog.md)。

阶段状态为 pending/running/completed/blocked/not_run；检查为 not_run/passed/failed/blocked。`completed` 不等于实际包已发布。

冻结 run 的 delivery_status 为 incomplete/blocked/staged；staged 表示制作、校准和导出检查完成，材料可随包归档。archive_status 也是 pending/staged。归档之后的 archived_verified 和最终 ready 记录在包外层索引与 release-binding，不回写冻结运行，避免哈希失效。

P8 包级复核尚未执行时，冻结运行的 P8 阶段保留 running；包外层 packaging-audit/index/binding 记录实际完成结果。这不使已完成的 P0–P7 失效，也不能据 run 的 staged 状态直接宣布整个包 ready。

运行 manifest 字段：

| 字段 | 内容 |
| --- | --- |
| workflow_identity | 工作流与数据契约 path/SHA |
| extraction_refs | 第一条 manifest 的 run_id/path/SHA 和实际归档位置 |
| input_files / output_files | `path, bytes, sha256, role`；不包含自身哈希，全部约定产物均登记 |
| archived_sources | 原来源、source_sha256、归档相对位置、archive_sha256 和片段定位 |
| source_snapshots | 各输入和阶段视图内容身份与恢复方法 |
| archive | required=true、包内 run_path、scope=pruned_delivery，原始方法/模板及修订历史归档 |
| limitations / parent_manifest | 影响与明确版本继承 |

冻结顺序：完成结果与审核 → 写最后状态/检查点 → 写 run manifest → 只读复核 → 逐字节归档。包级终检发生在外层，报告存为 `golden-docs/evidence/packaging-audit.md` 并由证据 manifest 管理，不能回写已冻结 run。

## 10. 证据索引、清单与发布绑定

最终包中的 reverse-extraction/index.json 沿用第一步契约。feature-pruning/index.json 的条目包含 `case_id, run_id, scope, run_path, artifact_manifest_sha256, parent_run_id, archive_status, used_for_delivery`，scope 为 pruned_delivery，archive_status 为 archived_verified。

索引空模板：[evidence-index.json](templates/evidence-index.json)。按 workflow_id 分别生成两份索引，entries 使用各阶段契约的字段；未验证的 run 不填 archived_verified。

证据 manifest 登记 `schema_version, case_id, release_id, files[]`，每项有 package-relative path、bytes、SHA、role。覆盖两条 workflow 的所有保留记录、索引、最终活动 PRD和包级审核；不包含自己或发布绑定的哈希。原 run 内 manifest 可以被外层清单引用。

证据清单空模板：[evidence-manifest.json](templates/evidence-manifest.json)。files 中的路径均相对包根；明确 excluded_files 的哈希排除，活动 PRD 在文件清单中实际登记，不只声明在文字中。

发布模板：[release-binding.json](templates/release-binding.json)，包级报告模板：[packaging-audit.md](templates/packaging-audit.md)。

| 字段 | 要求 |
| --- | --- |
| case_id / release_id / status | 唯一发布与 ready/blocked/incomplete，ready 需要所有必需检查通过 |
| manifests | runtime 和 evidence path/SHA，各自 coverage 与排除项 |
| active_prd | 最终 PRD path/SHA，不能指向第一条历史 PRD |
| scope_decisions | 配对范围表的包内位置和哈希 |
| runs | 第一/第二条 run、manifest 身份与包内 index |
| implementation | B、每仓库 G/T/C/D、environment 与 patch manifest 的实际身份 |
| evaluation | selection 源/转换身份、composition、counts、验证/grader/守卫及政策证据 |
| checks | 必需检查结果和报告位置，不凭 hash 配对推定测试通过 |
| visibility | Agent/Verifier 可见范围和准备脚本检查 |
| limitations | 非选中排除、运行约束和已知缺口；ready 不表示全仓库全绿 |

root/evidence/run/binding 的哈希关系必须无环。根 exporter 不支持附件时，用 sidecar 证据清单和绑定登记；要求 exporter 管理附件时，通过其正式输入实现，不手工改已发布根清单。发布绑定自身由外部包哈希/Git/发布系统核验，不能假称被不包含它的根 manifest 覆盖。

第三条按 active_prd 与 implementation 定位输入；补充 Golden 文档会产生新证据清单与新发布绑定，保留原运行，不改变 G/T/selection 就不虚构新测试执行。

## 11. 结构与语义检查

1. JSON/CSV 可解析，字段、枚举、唯一 ID 和引用有效，所有占位符已替换。
2. 全部 R/AC 决定完整；范围来源明确；实际删除项有 confirmed 决定及无 unresolved 影响项。
3. 每阶段 accepted 有父/子/增量/累计身份和实际报告，依赖顺序与回退明确。
4. B/C/D 与 E/G/T 一致，所有声明顺序实际测试，applier 能处理 patch 特性。
5. canonical ID 精确唯一，原/新并集去向完整，重命名有证据，F2P/P2P 互斥。
6. 候选全集、排除/重跑/missing 政策、原始报告和解析分类可复核；selected 缺失或非通过不算 pass。
7. 最终 PRD 与保留/删除合同双向一致，生成入口和消费者完整，测试没有注入参考业务实现。
8. exporter 管理文件由正式工具产生，源/转换选择逐项一致，导出 verifier 实际行为匹配。
9. 归档含两步全部必需证据，路径可移植、指纹一致，Agent 输入无参考答案泄漏。
10. 清单覆盖范围明确、哈希无环、状态与检查相符；仅 ready 才交付为标准验证包。

结构检查后还要审核产品边界、测试语义与回归原因，不能只根据这些字段齐全宣布完成。
