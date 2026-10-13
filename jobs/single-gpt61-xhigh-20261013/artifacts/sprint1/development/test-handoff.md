# 提测报告：Saleor Core 与 Dashboard 协同迁移至 3.23.0

版本：v1
轮次：1
依据：PRD v1；前端技术设计 v1；后端技术设计 v1；接口契约 v1；目标 schema 为技术设计封存的完整 `target-schema.graphql`（SHA-256：`7ab4230561a99a672c646aa200834376221a64120e5d21a4cf1b2164dd77cccc`）。测试参考为冻结 `test-cases.v1.csv`，未修改。

本轮结论：已交付已确认范围的生产代码与配套生成产物，可供后续部署和 QA 验证；**不是完整上游 3.23.0 功能迁移或正式验收通过的声明**。尚有测试失败、运行环境阻塞及冻结材料冲突，详见第 3、4 节。没有上一轮 QA 执行报告或修复计划，本轮为首次开发提测。

## 1. 提测版本

| 仓库 / 组件 | 代码版本或构建标识 | 代码位置 |
| --- | --- | --- |
| Saleor Core | 声明版本 `3.23.0`；分支 `sprint1-development`；基线 HEAD `c864e66b8e537d30732ddba62d3a4c47e49e4a3e`；未提交工作区差异 SHA-256 `7fcdd8e1e22ee6a7c749cab841e3e7bad832b97c86478a4ad52157028bff77f6` | `/workspace/repos/saleor` |
| Saleor Dashboard | 声明版本 `3.23.0`，schemaVersion `3.23`；分支 `sprint1-development`；基线 HEAD `aebb2401b5079fbbb8c60150289d1896c108feca`；未提交工作区差异 SHA-256 `00dbc6921189984723f8e26c360602c73ee94f959c4d642b843f61a4220d13c1` | `/workspace/repos/saleor-dashboard` |
| 两端生产 SDL | Core 实际 schema 导出并同步至 Dashboard，文件逐字节相同；SHA-256 `4377b7768999187d64a660f1afccf733d647e3b1e0e1bd89e25e2400eb725bd4` | Core `saleor/graphql/schema.graphql`；Dashboard `schema.graphql` |
| 代码与材料完整性清单 | `code-manifest.json`：包含基线、分支、binary diff hash、所有变更文件内容 hash、schema hash 和冻结材料 hash | `/workspace/artifacts/sprint1/development/code-manifest.json` |

版本标识为基线加未提交差异，不把基线 HEAD 当成包含新实现的提交。未 commit、push 或创建 PR；代码由运行器保存快照。Core 8 个、Dashboard 36 个跟踪文件变更，无未跟踪交付代码。四个客户端产物均经真实 codegen 重生成；其中只有实际内容变化的文件进入 diff。

## 2. 已完成功能

| 需求 | 完成情况 |
| --- | --- |
| R01 · 两端统一目标版本并实现已确认的目标行为 | Core/Python 项目、Node 元数据和锁文件自身版本统一 `3.23.0`，既有派生 schema version/user agent 跟随变化。Dashboard 版本及 schemaVersion 同步，直接调用 Vite 时 release name 读取真实 package 版本。已实现确认的扩展六字段及提交状态修复；完整目标行为仍受 Q01—Q03 阻塞。 |
| R02 · GraphQL 契约与实际后端行为一致 | `AppExtension`、`AppManifestExtension` 各新增非空 `mountName`、`targetName`、`settings`。已安装模型与清理后 manifest 字典使用各自 resolver；settings 为原生 JSON 对象，NEW_TAB/WIDGET 根据持久化 GET/POST 映射，无 method 返回 `{}`。旧 mount/target/options 保留并按设计标记弃用。完整实际 SDL 与目标语义比对通过；未改既有权限、manifest 安装规则或业务生命周期。 |
| R03 · Dashboard schema、生成客户端产物与生产界面同步 | 采用本地 Core 实际导出 SDL；schema 拉取脚本不再引用远程目标源。codegen 重生成四产物，连续两次内容稳定，620 个源文档/642 个去重后定义全部通过完整 schema 验证。商品更新和退款草稿更新操作补选必要实体 ID。扩展逐项 safeParse、校验 URL 和协议，非法项隔离而非整组崩溃；保留既有 GET/POST、widget 专用渲染、popup/App page、token 和旧预览边界。默认国际化消息已重新提取且幂等。 |
| R04 · 保持商家日常操作与已有业务规则的回归行为 | 修复共享错误判定，涵盖 transport/Apollo、顶层 GraphQL、空结果、null root、多 root 和 bulk row 错误；必要实体缺失不能成功。商品/变体创建、库存/渠道/metadata 更新、草稿订单创建/完成、退款草稿与退款请求、渠道创建/更新/仓库排序等待必要请求完成后才提示成功。创建部分持久化保留身份，避免重复创建或偷偷删除；已有渠道创建后只恢复排序。退款文案区分草稿保存/请求接受与实际到账。保留旧路由、查询参数、功能开关和服务端业务权限。自测及大量回归通过，但仍有 3 项已有 metadata 用例失败；真实保存回读和浏览器联调未完成，不能称 R04 全量验收通过。 |
| R05 · 数据库迁移支撑目标模型且保留既有业务数据 | 新增字段为已有数据派生，无模型变更，不生成空迁移或虚构转换。Django 检查及 scratch SQLite 的 `makemigrations --check --dry-run` 无新增迁移。未执行真实 PostgreSQL 空库/有数据升级、迁移计划与前后数据校验；完整目标模型清单未提供，该项只完成当前已知派生字段所需代码。 |
| R06 · 依赖、锁文件和构建声明形成一致的离线交付 | Core 更新必要本地依赖声明/uv 锁定项，保留 Base 依赖；`uv lock --offline --check` 通过。修正 release-it 的项目版本路径。Dashboard Docker/主要 CI 改为 Node24/pnpm 与 frozen lock，修正 ESLint9 flat config、TS bundler resolution/公开声明和 codegen loader 兼容。最终直接使用预装二进制的 types/codegen/Vite 通过；不能据此证明 pnpm10 全流程、干净离线安装、Docker/CI 已通过。另有一次 Corepack 非预期联网违规，见下文。 |
| R07 · 交付真实源代码差异并保护评估与冻结材料 | 已交付真实生产源修改，而非仅改版本、生成类型或添加测试 stub。未改官方 tests、fixtures、verifier、评分配置及冻结 PRD/测试设计/技术设计。材料最终 hash 与本轮开始记录一致，跟踪文件无仓库外符号链接，无未跟踪交付代码；运行时生成的本地私钥已从仓库清理。依赖未纳入代码变更。各 subagent 已结束本 Stage 工作。 |
| R08 · 分层验证并按冻结清单判定最终验收 | 已执行生产 resolver/schema 检查、全量 Dashboard Jest、三项类型检查、操作校验、生成幂等、限定/全量只读 lint、Knip 和构建，并保留失败记录。四 suite 启动被权限错误阻塞，不能算执行或通过；145 条冻结用例未完成整套运行。维护者接受和正式评分清单尚未冻结，不运行或宣称正式评分通过。 |

## 3. 未完成项与已知问题

### 3.1 必须保留的失败与环境阻塞

1. **Dashboard metadata 既有回归失败：**`src/utils/handlers/metadataUpdateHandler.test.ts` 的 `should call only updateMetadata mutation`、`should call only updatePrivateMetadata mutation`、`should return updatePrivateMetadata errors if exists` 共 3 项失败。用例将 `data:{}` 作为 metadata 成功响应；FD04 要求完成请求的空 payload 不得判成功，实际操作还必须有 update/delete 两个 root 的必要 item。现返回客户端 `GRAPHQL_ERROR`，第三项在不完整 public metadata 响应后停止，未继续 private 步骤。未修改用例、未加测试专属旁路；需维护者裁定回归与冻结目标语义的冲突。带真实双-root 成功/失败形状的自有 42 项验证通过，不替代官方回归验收。
2. **四 suite 均未执行：**调用 `/opt/runtime/run-suite.sh sprint1-dev-r1 core-unit core-e2e dash-unit dash-e2e` 在服务准备阶段遇到 `cp: cannot create regular file '/workspace/seed_e2e_fixtures.py': Permission denied`，exit 1。未修改受保护运行器或权限绕过。构建成功或健康检查不代表测试成功。Core 全量 unit/e2e、Dashboard 浏览器 e2e、真实配对 API 及持久化回读未验证。
3. **干净离线安装未通过：**Core clean scratch venv 的 `uv sync --offline --locked` 因缺失 `botocore==1.40.35` 本地 wheel 失败；本轮 Python resolver/Django 检查使用 scratch venv + 预装 system-site-packages，并非干净锁定安装。Dashboard 声明的 pnpm10.28.1 未缓存，禁止网络时 Corepack 查找失败；直接预装二进制验证不等于 `pnpm install --frozen-lockfile` 或 package scripts 全流程通过。
4. **全量质量门禁未通过：**全仓只读 ESLint exit 1，190 errors/2471 warnings；限定变更生产文件检查无 errors（仍有 warnings），未为清零而修改冻结测试或关闭规则。Knip exit 1，存在 unused files/devDependencies/exports/types、unlisted dependency 等，未通过批量删除功能/依赖掩盖结果。不能称全仓 lint/Knip 通过，也未完成所有失败项的基线归因。
5. **数据库与部署未完成：**尚未验证 PostgreSQL 空库及已有数据升级、历史安装与订单数据、权限及真实支付/退款外部状态。Docker、GitHub CI、发布工具没有实际执行，Q06 批准入口范围尚待明确。新增消息未补齐所有语言人工翻译，沿用默认消息 fallback。

### 3.2 冻结材料冲突与范围缺口（未修改材料）

- **安装终态冲突：**I04 要求后续可观察 `AppInstallation.status=SUCCESS`，但现有成功任务会删除 AppInstallation 并将 App 标记 installed；BD02 又要求保留生命周期。本轮保留 Base，不创造新安装状态机。QA 应结合 App 持久化状态验证，不能把缺失 SUCCESS 记录写成已满足冻结要求。
- **旧 options 非空传播：**合法 NEW_TAB/WIDGET 的 method=null，新 settings 为 `{}`；旧 options 嵌套 method 是非空，现有 resolver 查询仍触发 GraphQL error/null bubbling。已确认并保留旧行为，不能承诺新旧字段在该边界同时成功。
- **未知 manifest options：**I03 的“不接受任意新 key”表述与 Base 忽略未知 options key 的清理行为存在歧义。本轮未扩大服务端 manifest 校验规则，待维护者明确。
- **Q01—Q06 未闭合：**缺少完整 3.23 功能/API/模型转换清单、正式接受与冻结评分列表、旧能力移除授权和认可发布入口。不根据版本号猜测业务能力，不把保留的 Base 能力当成 3.23 新增。
- **超时不确定结果：**已获得实体 ID 的部分创建可恢复；未获得 ID 的创建/金额操作超时，只能提示先刷新确认，不自动重试、不虚构服务端幂等保证。多 root/多请求不具有整体事务原子性。

### 3.3 本轮执行偏差披露

本轮早期在 `/workspace` 查询 `pnpm --version` 时，Corepack 默认选择 pnpm12.11.2 并输出下载 npm registry 包的记录；发生了一次**非预期网络包管理器下载**，且 Corepack 缓存落在用户缓存目录而非指定 scratch。该行为违反离线和缓存目录约束，不能报告为全程离线合规。它不是目标源码下载，但仍是网络包获取。此后未继续联网安装，Corepack 检查显式禁止网络，生成/类型/Jest/构建使用预装直接二进制；未用该 pnpm12 下载结果声称 pnpm10 验证通过。

既有 Sentry Vite 插件构建日志还显示 telemetry 提示；无 auth token，未创建 release 或上传 sourcemap。该提示不证明遥测成功发送，也不能用来证明完全没有网络尝试。本轮没有修改该既有集成，也不把本地 bundle 成功当成外部发布成功。

## 4. 测试环境与验证方式

- 部署状态：待部署
- 部署版本：待部署
- 环境入口：待部署
- 访问方式：待部署；部署阶段由运行器/部署负责人提供账号与数据获取方式，本报告不嵌入凭据。
- 验证方式：本轮在 `/workspace/repos` 对真实生产代码自测，日志、临时脚本、缓存及虚拟环境主要放在 `/workspace/scratch`；后续应在同一实际 Core/Dashboard 配对环境执行冻结用例并重读持久化结果。
- 环境限制：Node v24.21.0、Python3.12.14、现有依赖可用；声明 pnpm10 无离线缓存、Core 部分 wheel 缺失；运行器 seed 文件目标无写权限；没有可据此认定已部署的完整联调环境；评分保持 disabled。

### 4.1 实际自测记录

| 层级 / 验证 | 实际结果 | 证据 |
| --- | --- | --- |
| Core 生产 resolver 与 GraphQL 对象执行 | 588 个 installed/preview 映射组合、588 个对象查询通过；49 mounts × 4 targets × GET/POST/null；原生 JSON、默认值、非法值及清理后 root 检查通过。生产 schema 版本权限/匿名拒绝检查通过。无 DB 写入，不是完整 HTTP/DB e2e。 | `/workspace/scratch/core-resolver-results.txt`、`validate-core-resolvers.py` |
| 完整 Core SDL 与冻结目标比较 | 完整 AST 含 directives/defaults/deprecations，排除描述、源码位置和排序后语义相同；schema errors 0、breaking/dangerous 0。 | `/workspace/scratch/core-schema-results.txt`、`check-core-schema.cjs` |
| Django / 迁移检测 | check 无问题；scratch SQLite `makemigrations --check --dry-run` 为 No changes detected。未作 PostgreSQL migrate 或数据升级。 | `/workspace/scratch/core-django-check.txt`、`core-migration-results.txt` |
| Core lock 与干净安装 | offline lock check 通过（240 packages）；dry-run 通过；clean locked sync 失败，不能算安装通过。 | `/workspace/scratch/core-lock-check.txt`、`core-sync-dry-run.txt`、`core-clean-sync.txt` |
| Dashboard 四生成产物与完整操作校验 | 默认 codegen 连续两次稳定；4 artifacts hash 相同；620 documents、642 definitions、1 个相同 fragment 去重，schema/operation errors 均 0。 | `/workspace/scratch/dashboard-codegen-delivery-a.log`、`dashboard-codegen-delivery-b.log`、`codegen-delivery-hashes.json`、`final-contract-validation.log` |
| Dashboard 源码、strict、Playwright 类型 | `tsc --noEmit`、`tsc-strict`、Playwright tsc 均 exit 0。 | `/workspace/scratch/dashboard-types-delivery-src.log`、`dashboard-types-delivery-strict.log`、`dashboard-types-delivery-playwright.log` |
| 扩展与 metadata 自有验证 | 最后整合后 2 suites / 69 tests 全通过（扩展27、metadata42）；生产合法响应与非法单项隔离，非官方评分。此前扩展已有 6 suites/104 tests 也通过。 | `/workspace/scratch/dashboard-scratch-delivery.log`、`fd03-isolation.test.ts`、`fd04-metadata-gate.test.ts` |
| 共享 mutation 结果矩阵 | 21/21 通过；已有 misc/channel 3 suites、5 tests 通过。 | `/workspace/scratch/dashboard-mutation-delivery.log`、`dashboard-owned-tests-final.log` |
| Dashboard 全量直接 Jest | 最终交付代码复跑结束，exit 1：338 suites 中 336 passed、1 failed、1 skipped；2165 tests 中 2154 passed、3 failed、8 skipped；56 snapshots 通过。失败仅为 3.1 所列 metadataUpdateHandler 用例，与前一次结果相同。不是运行器四 suite 成功。 | `/workspace/scratch/dashboard-unit-delivery-results.json`、`dashboard-unit-delivery.log` |
| 默认消息提取 | 源码重新提取后与 `locale/defaultMessages.json` 逐字节一致。 | `/workspace/scratch/dashboard-extract-delivery.log`、`defaultMessages-delivery.json` |
| 生产构建 | 最后整合版本直接 Vite build exit 0，输出 scratch；未运行声明 pnpm 全流程、Docker/CI 或部署。Sentry 无 token / bundle size 警告保留。 | `/workspace/scratch/dashboard-delivery-build.log`；输出 `/workspace/scratch/dashboard-delivery-build` |
| 静态质量 | 主/域/最后整合限定变更文件 ESLint exit 0、有 warnings；全量 ESLint 和 Knip 失败，详见 3.1。diff --check 两仓通过。 | `/workspace/scratch/dashboard-final-changed-lint.log`、`dashboard-domain-lint-readonly-final.log`、`dashboard-full-lint-readonly.log`、`dashboard-knip.log` |
| 运行器 core-unit/core-e2e/dash-unit/dash-e2e | 服务准备 exit 1，全部未执行，不记通过。 | `/workspace/scratch/sprint1-dev-r1-suites.log` |
| 冻结与快照核对 | 冻结材料最终 hash 未变，tests/fixtures/verifier 无修改；未新增仓库外链接/凭据，临时本地私钥已清理。 | 本目录 `code-manifest.json` |

### 4.2 复现入口与后续验证顺序

Dashboard 在仓库内直接调用预装工具（不要让 Corepack 联网补齐工具）：

```bash
node_modules/.bin/graphql-codegen
node_modules/.bin/tsc --noEmit
node_modules/.bin/tsc-strict
node_modules/.bin/tsc --noEmit --project playwright/tsconfig.json
TMPDIR=/workspace/scratch node_modules/.bin/jest --runInBand --silent \
  --cacheDirectory=/workspace/scratch/jest-cache \
  --json --outputFile=/workspace/scratch/dashboard-unit-delivery-results.json
TMPDIR=/workspace/scratch NODE_OPTIONS=--max-old-space-size=8192 \
  node_modules/.bin/vite build --outDir /workspace/scratch/dashboard-delivery-build
```

Python 自有 resolver/迁移检测脚本与具体环境设置位于 scratch，不是生产 stub。运行器命令仅在部署负责人修复 seed 写入环境后重试；不要修改 verifier 或绕过权限。应随后执行：真实 PostgreSQL 空库/有数据升级、两端身份与权限回归、扩展 installed/preview、商品库存/渠道/metadata 保存后重读、草稿完成与重复点击、退款草稿/请求/支付状态区分、渠道排序失败恢复、冻结145条用例。所有缺失、跳过、收集失败均保留为未验证，不由静态检查或成功 toast 替代。
