# Instruction 到技术评审：当前落地与剩余工作

更新：2026-09-18。依据：[飞书设计稿](https://rcnmkynuc7as.feishu.cn/wiki/GsuKwp9JJiTLPckayTwctTjxnic)，读取 revision 1132 及内嵌技术产物表。当前已实现配置、模板、角色约束、输入准备、分阶段 Controller、Codex 后端与公开产物门禁。Single/Flat 已通过容器内合成联调；真实 Single rollout 的结果以 [运行证据](../reports/checks/workflow-runtime-verification.json) 为准。

## 本轮范围

Single：一个主原生会话，Instruction → PM/PRD → 架构师/技术设计 → 同阶段技术自审 → 交付后停止。共两个 stage；自审是技术设计 stage 内的活动。默认同一 Agent 自审，新增独立评审角色需另行变更角色配置；不能将自审称作独立审核。

前端、后端分开写技术设计，但本次由一个架构师角色负责成套设计与接口一致性。不提前启动开发角色。无 Code、QA Test、Deploy。

## 输入输出契约

权威配置：[design-delivery.yaml](../tasks/saleor-prd-tdd/workflows/design-delivery.yaml)。Agent 可见规范：[organization-delivery.md](../tasks/saleor-prd-tdd/organization-delivery.md)。业务输入：[instruction.md](../tasks/saleor-prd-tdd/instruction.md)。

| 阶段 | 角色 | 输入 | 必交输出，路径相对 /workspace |
| --- | --- | --- | --- |
| sprint1/prd | PM | instruction、公开规范、PRD 模板、Base 源码和 SHA | artifacts/sprint1/prd/prd.md |
| sprint1/tech-design | 架构师 | 上述业务/源码输入、已封存 prd.md、技术模板 | artifacts/sprint1/tech-design/ 下的 frontend-design.md、backend-design.md、interface-contract.md、target-schema.graphql、review.md |

第一阶段输出与第二阶段输入在解析后是同一个绝对路径，以 `artifact:sprint1/prd/prd` 引用，不通过相似文件名猜测、不使用 latest、不回写上游文件。每个 run 使用全新 workspace。

PRD 使用 R/AC，设计使用 FD/BD，工程任务使用 BT，接口使用 I。新规范取代早期 REQ/C 编号与单文件 TDD.md 约定。叙述文档统一 Markdown，完整接口描述保持原生协议格式。PRD 不增加兼容性专章，按任务要求写入相应需求。

模板保留设计稿的粗粒度内容槽位。已将 PRD 的章节跳号改为 1–5；补齐后端模板缺失的“5. 工程任务与依赖”标题。review.md 是为本次截止点新增的交付模板；pass/blocked 不代表人工批准或已执行功能验证。

## 三种模式共用契约

| 模式配置 | 调度语义 | 当前状态 |
| --- | --- | --- |
| [single.yaml](../tasks/saleor-prd-tdd/workflows/single.yaml) | 固定向前；同一原生主会话；按 stage 激活角色 | Codex 真实文档交付已完成；自审 blocked 后停止 |
| [flat.yaml](../tasks/saleor-prd-tdd/workflows/flat.yaml) | 固定向前；每阶段全新 Agent；仅文件交接 | Codex 执行后端已接入；合成联调通过 |
| [hierarchical.yaml](../tasks/saleor-prd-tdd/workflows/hierarchical.yaml) | Lead 自主组织，允许返修；最终版本相容 | 共用产物契约；Lead/Skill/团队工具未实现 |

Hierarchical 中 stages 表示可用工作类别及输入输出依赖，不能将其直接套用成 Single 的固定游标。它的修订需要产物 revision 与引用闭包；同一最终路径只代表选中的交付版本，历史 revision 在运行器控制面保留。

未来 sprint2 可单独声明 Code → QA → Deploy；本次配置没有这些 stage，准备器没有声称支持它们的执行。docs/examples 的完整生命周期 YAML 继续作为历史草案，新范围以 tasks/saleor-prd-tdd/workflows/ 为准。

## 已实现的无模型准备

`prepare_workflow.py` 校验三种模式的 session/调度组合、角色和模板文件、重复 YAML key、阶段 ID、显式产物引用、向前依赖、输出目录归属、最终交付与停止点，并核对本地 Base SHA 和源码干净状态。

带 `--output` 时创建完整公开工作区：Instruction、规范、模板、角色、三个仓库的精确 Git archive 快照和空的产物目录。不会复制参考答案、rubric、宿主机 .git 配置或历史任务产物；源码 snapshot 不携带 Git 历史。外层保存 resolved-workflow.json 和输入文件哈希清单。准备快照本身不是运行时强制只读隔离。

```bash
# 使用已有 Harbor Python；依赖 PyYAML，不使用模型。
/Users/zhihu/.local/share/uv/tools/harbor/bin/python -m harbor_local.runtime.prepare_workflow

# 创建全新准备包，目录存在时拒绝覆盖。
/Users/zhihu/.local/share/uv/tools/harbor/bin/python -m harbor_local.runtime.prepare_workflow \
  --output harbor_local/.prepared/my-design-review

/Users/zhihu/.local/share/uv/tools/harbor/bin/python -m unittest harbor_local.runtime.tests.test_workflow_preparation -v
```

本次已生成 `.prepared/design-review-20260918/workspace/`；这不是运行结果，artifacts 目录仍为空。

## 运行入口

```bash
# 新 workflow：用本机 Codex 登录凭证与配置模型。
/Users/zhihu/.local/share/uv/tools/harbor/bin/python -m harbor_local --use-local-codex-auth

# 明确的无模型合成联调，产物标有 SYNTHETIC，不是实际 PRD/TDD。
/Users/zhihu/.local/share/uv/tools/harbor/bin/python -m harbor_local --smoke

# Flat 使用同一契约，每个 stage 新原生会话。
/Users/zhihu/.local/share/uv/tools/harbor/bin/python -m harbor_local \
  --task harbor_local/tasks/saleor-prd-tdd --mode flat --use-local-codex-auth
```

运行依赖已有 Harbor，并在同一 Python 环境安装 requirements.txt 中的 graphql-core。首次接入已安装该依赖。也可以继续使用 `.env` 的 CODEX_MODEL 与 OPENAI_API_KEY / CODEX_AUTH_JSON_PATH；密钥不写入 recipe 或准备包。本机凭证只在显式选择上述 flag 时使用。

Controller 位于 Harbor trial 的 workflow/，不挂载给 Agent；accepted/ 保存接受的文件，attempts/ 保存每次提交、公开门禁结果和 native session 证据，state.json 与 events.jsonl 记录流程。workspace 中的正式产物也由 Harbor 回收。

## 已实现的执行约束

- 两阶段固定向前，结构错误最多在当前 stage 补交一次；已接受阶段不能回退。Controller 已存在状态时拒绝原地重放。`--continue-from <failed-trial>` 可以在新的记录目录接续已接受 PRD 后的失败阶段：校验公开输入和已接受文件哈希，恢复同一个原生 session，保留原失败记录，不重跑 PM、不回退阶段；业务评审 blocked 不能用这个入口绕过。
- Single 使用 Codex App Server 的 thread/start / thread/resume 保持主 session，通过 thread/inject_items 追加当前 developer Role Blueprint，再 turn/start。核对 thread.started 和最新原生 developer 消息。实测 0.154.0 的 exec resume 配置覆盖及 thread/resume.developerInstructions 均保留旧角色，不能作为角色切换依据；已用同 session 的 PM_READY → ARCHITECT_READY 两个真实回合验证新接入。thread/inject_items 是开启 experimentalApi 后使用的原生接口，升级 Codex 时应重新跑 --role-probe。Flat 清理原生 sessions、临时目录与前一阶段日志，只传正式文件。
- 每次执行分配独立非 root UID，输入与源码由 root 持有；仅当前产物目录、scratch 与 Agent 日志可写。容器启用 no-new-privileges，不挂载 Docker socket。阶段结束终止该 UID 全部残留进程，接受产物改为 root 只读，并与容器内文件核对哈希。这是操作系统文件权限隔离，不声称所有目录都是 read-only bind mount。
- Markdown 门禁检查固定标题、必交文件、R/AC 对应、优先级、FD/BD/I/BT 引用、工程任务依赖环、评审覆盖与结论。SDL 使用 graphql-core 检查语法和类型；Base 中被删除的类型必须在设计文字中逐项有说明，以识别误交片段。
- 门禁是公开结构校验。接口业务语义、技术取舍和需求质量仍依赖 Agent 自审，不能称为独立质量评审或隐藏评分。
- review=blocked 时保存完整产物且 run=blocked；不进入 Code。Agent/工具失败或格式重试耗尽时保留日志和未接受草稿，run=failed。

## 当前边界

Codex 是本次实现的执行后端；Claude Code 保留原有单轮入口，新 workflow 后端尚未接入。Hierarchical 配置可以解析，但缺少 Lead 后端，启动器会明确拒绝，不静默按 Single 执行。

业务数据库、前后端依赖安装和服务部署不阻塞源码分析与文档交付；Oracle/Noop 与隐藏评分不属于本次范围。当前只支持这两类文档 stage，未来 Code/QA/Deploy 需要对应执行权限与门禁，不能直接套用本控制器。

## 运行器验收要求

- 接受 PRD 前，不执行技术设计；接受后不能由架构师改写。
- PM 与架构师收到不同的活动 Role Blueprint，但 Single 的原生主 session ID 连续。
- Flat 使用新 session；Hierarchical 不被静默降级为 Flat/Single；未实现模式直接拒绝执行。
- 结构错误可在当前未接受阶段内补交；不能倒退到已接受阶段。
- review=blocked 时产物仍被保留，run 状态为 blocked；不得自动返回 PRD 或进入 Code。
- schema 可解析只是结构证据；不得据此宣称技术设计正确或业务测试通过。
- 第一个 stage 的 PRD 字节哈希等于第二个 stage 记录的输入哈希；最终包绑定所有实际文件版本。
- 隐藏参考文档、评分 rubric、旧 jobs 与宿主机凭据不进入公开工作区。

## 接口依据与证据

原生线程与注入接口依据 [Codex App Server 官方文档](https://developers.openai.com/zh-Hans/docs/app-server)，参数同时按本机固定版本 `codex app-server generate-json-schema --experimental` 核验。保持原生会话，不编辑 JSONL 来伪造角色消息。

`--role-probe --use-local-codex-auth` 会运行两个很短的真实模型回合，检查同 session 的角色切换，不生成业务文档。首次真实 rollout 暴露的旧角色保留问题和多行需求描述解析问题均保留在原运行记录中；后者已修正为接受模板槽位中的多行正文。

## 2026-09-18 真实交付结果

使用本机 Codex 登录与 gpt-6-astra，完成 PRD 的16条需求、16个前端设计单元、16个后端设计单元、17组接口、完整 GraphQL SDL、3份 JSON 接口描述和同 Agent 自审报告。两个阶段均已接受，PRD 输出哈希与技术阶段输入哈希一致。最终 state=blocked、cursor=2，停在本轮规定的技术评审交付点；没有进入代码、QA 或部署。

业务自审阻塞项：过期/停用礼品卡退款后的权益规则需要产品确认；旧身份插件和扩展令牌的来源、TTL 与迁移清单缺失。结构校验已通过，包含 graphql-core schema 验证；这不代表业务独立评审通过。

正式文件位于 [accepted/sprint1](../jobs/workflow-single-20260918-b/task__bVyhiV4/workflow/accepted/sprint1/)，[运行状态](../jobs/workflow-single-20260918-b/task__bVyhiV4/workflow/state.json) 和 [汇总证据](../reports/checks/workflow-runtime-verification.json) 保留逐次提交与哈希。此次真实流程先在 a 运行生成并接受 PRD，修复角色切换后以 b 运行续接同一原生 session；不是一次无中断首跑。旧失败证据保留。运行摘要见 [report.md](../jobs/workflow-single-20260918-b/report.md)。

技术阶段的首次提交还暴露了 GraphQL 代码块内 # 注释被误当 Markdown 标题的问题。Agent 在同阶段补交后通过；校验器现已正确忽略 fenced code 中的标题标记，并有回归测试。最终27项准备器/运行器测试通过。PM Blueprint 的调查笔记位置也统一为 scratch；历史运行的冻结输入不随该文字修正变化。
