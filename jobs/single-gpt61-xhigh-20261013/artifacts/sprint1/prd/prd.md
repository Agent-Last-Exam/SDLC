# PRD：Saleor Core 与 Dashboard 协同迁移至 3.23.0

版本：v1
责任：产品
状态：存在待确认项
输入：instruction.md；现有项目代码
修订：首次交付（2026-10-13）；定义协同迁移范围、已知约束与验收条件，明确目标行为规格和正式验收清单尚未齐备，不将基线已有能力认定为 3.23 新功能。

## 1. 业务背景与目标

商家管理平台由 Saleor Core 提供业务数据、权限与 GraphQL API，由 Saleor Dashboard 提供商家操作界面。业务输入要求将 Core 3.22.0 和 Dashboard 3.22.9 协同迁移至 3.23.0，而不是分别修改版本号。仅升级一端、仅更新生成类型或依赖声明，会导致管理操作与实际 API、数据结构或运行环境不一致。

依据 `/workspace/instruction.md:4-11`，本次目标是：

1. 两个仓库的生产实现达到 3.23.0 的已确认目标行为，后端 API 与 Dashboard 行为一致。
2. GraphQL 契约、前端生成产物、数据库迁移及构建/依赖声明与生产实现同步。
3. 保持回归测试覆盖的既有行为；目标明确要求变化的行为须有对应变更依据，不能以测试专用桩替代生产功能。
4. 在预装依赖与工具的离线环境完成开发与验证，不获取目标源代码、不从网络安装依赖、不改动评估材料。
5. 正式清单接受并冻结后，所有选定 fail-to-pass（F2P）用例由失败变为通过，所有选定 pass-to-pass（P2P）用例维持通过；收集失败或结果缺失不能计为通过。

输入没有给出商家量、性能或收益数据，本 PRD 不设置无依据的业务增长、响应时延或覆盖率指标。输入也未给出完整的 3.23.0 功能、API 或数据库差异清单；因此本文定义可执行的迁移约束与回归底线，但不声称已穷尽目标版本的功能需求。R01 中目标行为验收以及 R08 中正式评估验收受第 5 节待确认事项阻塞。

## 2. 用户与场景

| 用户类型 | 典型任务 | 本次应保证的结果 |
| --- | --- | --- |
| 有相应权限的商家运营人员 | 在 Dashboard 查询、创建和编辑商品及变体，维护销售渠道信息 | 已有操作不会因两端版本或 GraphQL 字段不匹配而失效；保存结果与重新查询结果一致 |
| 有相应权限的订单/售后人员 | 查看订单、处理履约与退款等已有流程 | 界面显示的订单、金额和处理状态与 Core 一致，不出现仅界面成功但业务未保存的情况 |
| 商家管理员及受限员工 | 登录商家平台，访问权限范围内的数据和操作 | 保持已有权限边界；升级不扩大数据访问或操作权限 |
| 使用 Core API 的既有客户端/App | 按已覆盖的既有契约读取业务数据、执行交易相关操作 | 未被确认目标变更替代的回归行为继续可用，错误与成功结果仍符合对应契约 |
| 研发、部署与验收人员 | 离线构建、同步 schema 与客户端生成产物、升级现有数据库、执行本地与正式测试 | 交付为可导出的源代码差异；数据与构建可验证；候选测试结果和正式验收结论分开记录 |

上述商家流程为既有行为的回归场景，不代表新增需求。权限、渠道、金额等业务结果以现有回归预期和已确认的目标变更为判定依据，不另行重新设计商品、订单、结算或支付规则。

## 3. 需求条目

### R01 · 两端统一目标版本并实现已确认的目标行为
- 来源：Instruction 原文：“The baselines are core 3.22.0 and dashboard 3.22.9; the intended target is 3.23.0.”；“Implement the coordinated production-code migration to 3.23.0 across both repositories.”（`instruction.md:4-7`）。目标行为清单要求为推导需求：仅凭版本号无法判定是否实现生产迁移，且输入要求“implementing the target behavior”（`:10`）。
- 优先级：P0
- 需求描述：Core 与 Dashboard 均以 3.23.0 为本次发布目标，版本元数据、实际实现与声明契约不得互相矛盾。迁移须修改真实生产路径，不能将环境补丁、已有 3.22 功能或单纯版本号变化视为目标功能完成。对目标新增、修改或移除的每个业务行为，须由维护者提供或确认变更依据，记录输入、操作、输出、异常与权限边界及受影响的前后端契约；不明事项列入第 5 节，禁止推测目标行为。
- 验收条件：
  - AC-01-1：给定升级后的两端源代码，检查版本声明并启动配对运行实例，Core 和 Dashboard 的发布版本均为 3.23.0，所使用的 Core schema 版本为 3.23；不存在仍将实际目标声明为 3.22 的生效配置。
  - AC-01-2：给定维护者确认的一个目标新增或变更场景，通过正常生产 API 或 Dashboard 执行规定操作，实际结果、权限限制和错误行为与该场景的确认规格一致；凡影响两端的场景，两端结果一致。当前缺少目标行为清单，本条不能以修改版本号或已有功能演示代替通过。
  - AC-01-3：给定不加载评估测试专用模块的正常运行环境，执行一个目标场景，功能由生产服务完成；不存在依靠测试标识、固定测试数据或测试专用桩才返回目标结果的分支。

### R02 · GraphQL 契约与实际后端行为一致
- 来源：Instruction 原文：“Keep the backend API and Dashboard behavior consistent, including their GraphQL contracts”（`instruction.md:7-8`）；“Preserve existing behavior covered by regression tests”（`:9-10`）。输入/输出类型、权限及错误行为的检查为推导需求，依据 GraphQL 契约承载商家操作且必须与生产服务一致。
- 优先级：P0
- 需求描述：本次涉及的 Query、Mutation、输入对象、返回对象、枚举、可空性与错误信息须与已确认目标保持一致。Core 实际运行 schema 与仓库中的 schema 产物须一致。Dashboard 所使用的操作和 fragments 必须能通过配对后端 schema 验证。没有明确目标变更依据时，不得借迁移随意移除既有 API 或改变回归覆盖的权限和异常规则；本要求不承诺未经输入要求的所有历史版本兼容。
- 验收条件：
  - AC-02-1：给定迁移后的 Core，使用本地生产定义导出 schema，与交付的 `saleor/graphql/schema.graphql` 做语义比较，类型、字段、参数、枚举及可空性不存在未解释的差异。
  - AC-02-2：给定迁移后的配对 Core schema，对 Dashboard 在用的 GraphQL 操作和 fragments 执行校验，不出现未知字段、未知类型、无效变量类型或无效枚举等契约错误。
  - AC-02-3：给定一项已确认目标 API 变更，分别提交有效输入与该规格定义的无效输入，成功结果和错误结果均与已确认契约一致，不能以一律成功或一律返回空值规避业务校验。
  - AC-02-4：给定无相关权限的用户，对一项回归覆盖的受保护读取或写入发起请求，响应保持对应回归预期，不能读取受保护数据或完成受限写入；失败写入后业务数据未发生该项变更。

### R03 · Dashboard schema、生成客户端产物与生产界面同步
- 来源：Instruction 原文：“including their GraphQL contracts, generated client artifacts”（`instruction.md:8`）；“Do not replace missing production features with test-specific stubs.”（`:10-11`）。以本地 schema 生成客户端为推导约束，依据离线要求（`:15-16`）及现有 Dashboard 的 schema/codegen 工作流。
- 优先级：P0
- 需求描述：Dashboard 的 schema 输入须来自本地配对 Core 的最终生产契约，GraphQL 源操作、fragments 与生成的 types、hooks、fragmentTypes、typePolicies 等产物同步。界面真正调用这些生产操作；不能仅手改生成类型来掩盖后端未实现字段，不能继续将 3.22 远程 schema 当作 3.23 的权威输入。生成工作流必须离线可运行。
- 验收条件：
  - AC-03-1：给定本地 Core 最终 schema 及 Dashboard 源操作，离线执行现有 `generate` 工作流，所有配置要求的客户端产物成功生成，不需要从网络下载 schema。
  - AC-03-2：给定已交付的 schema、源操作和生成产物，在相同输入下再次生成，生成产物没有语义差异；不能出现手写字段在再次生成后消失的情况。
  - AC-03-3：给定同步后的客户端产物，执行 Dashboard 类型检查及生产构建，均成功；实际连接迁移后的 Core 执行涉及目标变更的界面操作时，不出现因陈旧生成产物导致的契约错误。

### R04 · 保持商家日常操作与已有业务规则的回归行为
- 来源：Instruction 原文：“Preserve existing behavior covered by regression tests while implementing the target behavior.”（`instruction.md:9-10`）。商家回归场景为推导需求，依据现有 Dashboard 商品、订单、权限等模块以及 Core 的商品、结算和订单业务实现；不是推定的 3.23 新功能。
- 优先级：P0
- 需求描述：凡选定 P2P 覆盖的商家流程和业务规则必须保留。回归操作在真实配对服务上检查读取、提交、持久化及重新读取，不能仅用按钮可点击、页面可打开或成功提示代替业务成功。输入、金额、状态、渠道范围和权限等结果遵循对应回归用例。经确认的目标变化与基线预期发生冲突时须由维护者明确归类，不能为使结果通过而修改评估测试或静默放宽规则。
- 验收条件：
  - AC-04-1：给定有商品管理权限的员工及既有商品/变体回归场景，按场景完成查询、创建或修改并保存后重新打开对象，展示结果与 Core 查询及持久化结果一致，场景所覆盖的名称、属性、渠道等值符合预期。
  - AC-04-2：给定有相应订单权限的员工及已有订单处理回归场景，在 Dashboard 完成该场景操作后重新查询订单，处理结果、金额和状态与 Core 及回归预期一致；失败操作不得被界面当作已保存成功。
  - AC-04-3：给定现有登录和权限回归场景，使用受限员工执行该场景的访问或操作，允许/拒绝结果与基线预期一致，不因迁移越权显示数据或执行操作。
  - AC-04-4：给定 Core 已覆盖的结算转订单回归场景，在正常生产服务执行该场景，订单与库存、付款等该场景检查的业务结果仍满足原预期；不得通过仅调整 Dashboard 显示来掩盖 Core 结果偏差。

### R05 · 数据库迁移支撑目标模型且保留既有业务数据
- 来源：Instruction 原文：“including ... database migrations”（`instruction.md:8-9`）；“Preserve existing behavior covered by regression tests”（`:9-10`）。既有数据保留与全新部署校验为推导需求，依据生产版本迁移必须同时服务现有商家数据库与新部署环境。
- 优先级：P0
- 需求描述：已确认目标涉及数据模型或数据结构变化时，须提供完整可执行的 Django migrations，覆盖必要的结构与数据转换。迁移后模型定义和数据库状态一致；保留既有商品、订单、用户、渠道及其关系，不得以清空数据库、重新填充演示数据替代升级。不预设目标必然需要特定新表或字段；如目标没有模型变化，应说明依据，不为满足形式新增空迁移。数据回滚方案是否需要可逆迁移见第 5 节，不自行承诺跨版本回退。
- 验收条件：
  - AC-05-1：给定一个包含相关既有业务数据的 3.22 数据库副本，执行本次升级迁移，迁移成功；对照迁移前记录，原有业务对象标识和关联仍可读取，字段值按已确认转换规则保留或转换，没有非预期丢失。
  - AC-05-2：给定空数据库，应用完整迁移链后启动 Core，数据库满足目标模型要求，相关目标及回归操作可执行，不依赖人工补表或补列。
  - AC-05-3：给定已完成迁移的数据库，再次执行迁移检查，无待执行的必要迁移；对模型执行迁移差异检查，不出现生产模型变化未被迁移记录覆盖的情况。

### R06 · 依赖、锁文件和构建声明形成一致的离线交付
- 来源：Instruction 原文：“including ... build/dependency declarations”（`instruction.md:9`）；“Required dependencies and development tools are preinstalled. Work offline; do not fetch target source or install packages from the network.”（`:14-16`）。锁文件与脚本一致为推导需求，依据生产构建可复现且两仓库均有依赖声明及锁定机制。
- 优先级：P0
- 需求描述：两端依赖声明、实际使用的锁文件、包管理器配置及构建/生成脚本与目标生产代码配套。不得仅利用预装环境中“恰好存在”的依赖而漏写生产声明；也不得把预装的基线兼容依赖集合视为目标功能规格。可利用本地已有依赖材料，但禁止联网安装、获取目标源码或目标镜像。保留必要的基线兼容声明须说明用途，不要求字节级复制上游文件。
- 验收条件：
  - AC-06-1：给定本次后端依赖声明、锁文件与预装离线环境，完成依赖一致性检查并启动 Core，所需生产依赖均有对应声明和锁定依据，不发生缺失导入或声明相互冲突。
  - AC-06-2：给定前端依赖声明、锁文件和包管理器配置，使用声明的离线工具链完成 codegen、类型检查与生产构建，不需要临时在线补装依赖或借用未声明的生产依赖。
  - AC-06-3：给定整个迁移执行记录，检查依赖获取和 schema 同步方式，没有网络获取目标源代码、目标镜像或安装包的操作；若离线缺少所需材料，记录阻塞而非绕过约束。

### R07 · 交付真实源代码差异并保护评估与冻结材料
- 来源：Instruction 原文：“the evaluator exports each repository's diff against its fixed agent baseline”（`instruction.md:16-17`）；“Do not modify evaluation tests, fixtures, the verifier, or scoring configuration.”（`:19`）；“the evaluated tree is not required to be byte-for-byte identical to the upstream target tree.”（`:21-22`）。本阶段另受冻结 PRD/测试用例不可修改的约束。
- 优先级：P0
- 需求描述：研发交付应为 Core 和 Dashboard 相对各自固定 agent baseline 的普通源代码差异，包含必要生产逻辑、迁移、契约、生成产物和构建声明，不能只存在于运行时 monkey patch、临时目录或预装环境变动中。本阶段只写当前 PRD，不执行代码修改、提交或实现任务。评估测试、fixtures、verifier、评分配置及已封存 PRD/测试用例保持不变；发现材料问题记录在当前报告，不替换冻结基线。
- 验收条件：
  - AC-07-1：给定研发阶段两个仓库的最终差异，对固定 baseline 导出后，影响目标功能的生产实现和声明均在差异中；仅应用这些差异并使用允许的预装环境即可复现相同功能，不依赖未交付的仓外补丁。
  - AC-07-2：给定迁移前后评估材料和冻结材料，比较文件内容及路径，没有修改、删除、替换或通过运行时覆盖改变这些材料；发现的问题仅出现在允许写入的当前报告中。
  - AC-07-3：给定一个与上游目标文件内容不同但满足确认契约、生产运行及全部选定测试的实现，不因非字节级一致判为失败；不得以此为由豁免缺失目标行为或回归失败。

### R08 · 分层验证并按冻结清单判定最终验收
- 来源：Instruction 原文：“`/opt/runtime/run-suite.sh <attempt> <suite>...` ... `core-unit`, `core-e2e`, `dash-unit`, or `dash-e2e`”（`instruction.md:24-26`）；“a successful health check alone is not test success”（`:27`）；“all selected fail-to-pass tests ... all selected pass-to-pass tests ... Collection failures and missing selected results are not passes.”（`:29-32`）；“maintainer acceptance and scoring-list freeze are pending ... Formal grading remains disabled”（`:34-37`）。
- 优先级：P0
- 需求描述：验证覆盖 Core 单元/API及端到端、Dashboard 单元及端到端四个套件，运行时具备本地数据库及其他服务。记录实际运行套件、命令、结果文件、失败/收集错误/缺失结果及执行环境，区分环境失败与业务失败，但二者都不能算通过。正式测试由评估方另行提供；候选 F2P/P2P 清单须经维护者接受并冻结后才可用于正式判定。当前 PRD 阶段未执行这些测试，不报告实现或测试已通过。
- 验收条件：
  - AC-08-1：给定可用的本地依赖服务，使用规定入口运行 `core-unit`、`core-e2e`、`dash-unit`、`dash-e2e`，每个请求套件均有实际执行结果及可追溯日志，不能用健康检查或服务启动成功代替用例执行。
  - AC-08-2：给定已接受并冻结的正式 F2P 清单及相同评估条件下的迁移前后结果，每个选定用例在迁移前失败、迁移后通过；缺失、收集失败、未运行、跳过或预期失败记录不能替代所需的通过结果。
  - AC-08-3：给定已接受并冻结的正式 P2P 清单及迁移前后结果，每个选定用例均保持通过；不存在为了修复 F2P 而引入的选定回归失败。
  - AC-08-4：给定当前清单仍为候选、未获接受或未冻结的状态，交付报告明确写明正式评分关闭及候选验证性质，不宣称 benchmark 已发布或正式评估验收完成。
  - AC-08-5：给定任一选定结果缺失或发生收集失败，汇总报告指出具体缺口并判定相关验收未通过/受阻，不将退出码、部分通过数量或健康检查据此解释为全部通过。

## 4. 范围与非目标

**本次包含：**

- Core 3.22.0 与 Dashboard 3.22.9 到 3.23.0 的协同生产迁移需求；经维护者确认的目标行为及其前后端契约、必要模型迁移、生成产物、依赖与构建声明。
- 回归覆盖的既有商家流程、Core API 行为、权限和数据完整性保障。
- 离线开发边界、普通源代码差异交付、四类本地套件验证、F2P/P2P 正式验收前置条件。
- 当前阶段的唯一交付为 `/workspace/artifacts/sprint1/prd/prd.md`；本阶段不改生产仓库、不运行代码迁移、不执行 git 提交。

**明确不做：**

- 根据版本名臆造新功能、重新设计商品/订单/结算/退款规则，或把 3.22 已有能力包装为 3.23 新增能力。
- 在线获取上游目标源码、在线安装依赖、用测试专用桩替代生产实现、修改评估测试/fixtures/verifier/评分配置。
- 替换已封存的 PRD 或测试用例；未经确认，不能仅凭代码 TODO 移除旧 API、旧链接或兼容逻辑。
- 强制与上游目标树逐字节一致，或承诺本输入未要求的所有旧客户端版本兼容。
- 生产环境实际发布、网络服务部署、全新数据导入能力、独立的商家培训功能或商业增长指标。

**暂不能闭合的事项：**完整 3.23 行为、API 和模型变更范围，以及正式 F2P/P2P 清单，需要维护者确认后补充或校验。它们不是被排除的目标能力，而是材料缺口造成的规格/验收阻塞；本 PRD 不把“缺少规格”解释为无需实现目标变化。

## 5. 其他

**事实依据与材料边界**

- `/workspace/repos/saleor/saleor/__init__.py:6` 的 Core 版本为 `3.22.0`，`:23-25` 由版本导出 `schema_version` 与 `user_agent_version`。`/workspace/repos/saleor-dashboard/package.json:3` 为 `3.22.9`，`:50-53` 的 `config.saleor.schemaVersion` 为 `3.22`，与输入基线相符。
- Dashboard `package.json:12-13` 的构建前置为生成客户端，`:28-31` 定义本地 schema 获取、远程 schema 获取和 `graphql-codegen`。其中 `fetch-schema` 访问网络，本次不能执行该在线路径作为 schema 同步方式；应使用本地最终 Core 契约。
- Core `/workspace/repos/saleor/CONTRIBUTING.md:105-124` 记载 `poe migrate` 和 `poe build-schema`，`:132-153` 说明 `pyproject.toml`/`uv.lock` 依赖管理及 Django app 的迁移结构；`pyproject.toml:149-157` 给出实际 schema 导出及迁移任务。这些是现有工作流依据，不等于目标功能已实现。
- Dashboard `/workspace/repos/saleor-dashboard/codegen.ts:4-48` 规定 schema、源操作输入与四类生成输出；`src/graphql/client.ts:8-9,43-47,85` 消费生成的 fragment 信息和 cache policies，说明 R03 涉及实际生产客户端，而不只是静态类型文件。
- R04 的具体基线证据：Dashboard `playwright/tests/product.spec.ts:46-95` 覆盖变体、价格与库存，`playwright/tests/orders.spec.ts:237-325` 覆盖草稿完成及退款；Core `saleor/tests/e2e/product/test_create_simple_product.py:17-109` 覆盖商品/渠道/库存，`saleor/tests/e2e/checkout/test_unlogged_customer_should_be_able_to_order_physical_product.py:53-105` 覆盖配送、支付与下单。这些测试文件只读，未执行；结算测试使用 dummy payment 不能视为生产支付集成的完整验收。
- Dashboard `src/products/urls.ts:94-99` 与 `src/products/index.tsx:133-152` 有标记 3.23 删除旧变体 URL 的 TODO，当前仍保留兼容重定向。本文将其记录为 Q05 线索，不据此确定删除后的行为。
- 静态构建/发布风险：Dashboard `package.json:235-238` 声明 pnpm/Node 24，但 `Dockerfile:1-6` 使用 Node 20/`npm ci`，`.github/workflows/main.yml:21-34,51-58` 仍引用 npm 路径；Core `.release-it.json:14-23` 仍指向 `tool.poetry.version`，而版本字段实际位于 `pyproject.toml:5-7` 的 `[project].version`。这些是尚未运行验证的配置不一致，纳入 R06 检查与 Q06 澄清，不宣称对应构建已经失败。
- `/workspace/base-revisions.json` 记录固定 agent baseline：Core `c864e66b8e537d30732ddba62d3a4c47e49e4a3e`，Dashboard `aebb2401b5079fbbb8c60150289d1896c108feca`。业务版本与 baseline commit 是不同概念，不能混用。
- `/workspace/saleor` 与 `/workspace/saleor-dashboard` 是指向 `/workspace/repos/` 对应仓库的路径别名。输入中的开发路径与本阶段指定的材料路径不构成两套仓库。
- 现有版本记录和源代码只能证明基线行为。没有取得完整 3.23 发布行为规格，未取得单独提供的正式测试，不以代码覆盖范围或环境补丁名称反推目标行为。
- 补充环境事实：本地 `/opt/environment/dependencies/manifest.json:2` 明示 target 输入仅为依赖 manifests，不包含 target image 或 source checkout；`:4-18` 列出后端 `pyproject.toml`/`uv.lock` 与前端 `package.json`/`pnpm-lock.yaml`/`pnpm-workspace.yaml`/`.npmrc`。这些材料最多用于研发阶段核实构建依赖，不填补产品行为、API 或数据迁移规格缺口。
- 本地 `/opt/runtime/run-suite.sh:22-53` 具有指定套件入口，`:66-76` 汇总实际套件运行状态。当前只读取验证入口，没有运行测试、构建或迁移，因而没有可宣称的通过结果。

**产品决策与假设**

- 需求均为 P0：去掉任一项会使输入中的目标生产迁移、两端一致性、数据/权限安全或验收约束无法成立。本次不增加无明确任务价值的 P1/P2 功能。
- 目标明确变更优先于不适用于目标的旧行为，但必须有维护者确认的范围和新的判定依据；对被选定为 P2P 的行为不能自行改变预期。
- 验收以最终配对的 Core 3.23.0 与 Dashboard 3.23.0 为准，不据此承诺不同版本任意混搭。运行环境具备输入所述预装依赖和本地服务；若实际不具备，应记录环境阻塞。
- R04 的场景是回归检查维度，具体数据和结果采用对应回归用例；不把概括性场景当作完整官方测试目录。

**待确认项及影响**

| 编号 | 待确认内容 | 建议确认责任方 | 影响与处理 |
| --- | --- | --- | --- |
| Q01 | 完整的 3.23.0 新增/修改/移除业务行为清单，以及商家可见流程、输入、输出、异常和权限变化 | 业务提出方、Core/Dashboard 维护者 | 阻塞 AC-01-2 和目标功能完整性结论；确认后追加细化需求，不重排/复用既有编号 |
| Q02 | 与 Q01 对应的目标 GraphQL 字段、类型、参数、枚举、错误及弃用/移除边界，Dashboard 操作与功能开关变化 | Core/Dashboard 维护者 | 阻塞目标契约差异的完整验收；当前先定义 R02/R03 一致性约束，不编造目标 schema |
| Q03 | 目标数据模型和数据转换清单；生产数据约束；是否要求可逆迁移或特定回滚方式 | Core 维护者、部署负责人 | 阻塞目标迁移方案闭合；仍须满足 R05 的既有数据保护及迁移链校验 |
| Q04 | 维护者是否接受候选 F2P/P2P 清单、冻结版本、官方测试提供方式及最终选定范围 | 评估/维护方 | 输入明确正式评分关闭；冻结前仅能报告本地或候选验证，不得宣称正式验收通过 |
| Q05 | 旧路由、旧 API 与兼容入口中计划移除的项目，是否确实纳入本次目标 | Dashboard/Core 维护者 | TODO、注释或历史计划不单独构成移除授权；未经确认保留回归覆盖的行为，并记录冲突 |
| Q06 | 本次认可的生产构建/发布入口及 Node、包管理器、锁文件支持范围；Docker/CI/发布工具是否均须修复至同一声明 | 两端维护者、部署负责人 | 已发现静态配置不一致；按 R06 验证批准入口，范围内入口不得依赖与声明矛盾的工具链，不能将本地构建成功泛化为所有发布入口可用 |

没有发现或改动已封存材料。本次仅交付当前 PRD，待确认项保留在本报告中，不以修改冻结基线消除问题。
