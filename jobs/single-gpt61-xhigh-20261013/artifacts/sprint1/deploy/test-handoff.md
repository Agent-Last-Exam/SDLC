# 提测报告：Saleor Core 与 Dashboard 协同迁移至 3.23.0

版本：v2（部署更新）
轮次：1
依据：PRD v1；前端技术设计 v1；后端技术设计 v1；接口契约 v1；目标 schema 为技术设计封存的完整 `target-schema.graphql`（SHA-256：`7ab4230561a99a672c646aa200834376221a64120e5d21a4cf1b2164dd77cccc`）。测试参考为冻结 `test-cases.v1.csv`，未修改。

本轮结论：以下第 1—3 节继承开发提测 v1 的版本、功能与问题记录；本阶段源码只读，部署验证见第 4 节。已交付已确认范围的生产代码与配套生成产物；**不是完整上游 3.23.0 功能迁移或正式验收通过的声明**。尚有测试失败、运行环境阻塞及冻结材料冲突，详见第 3、4 节。没有上一轮 QA 执行报告或修复计划，本轮为首次开发提测。

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

### 4.1 部署状态与入口

- 部署状态：**待部署（最终部署声明已准备；scratch 隔离彩排通过，阶段结束后由运行器在独立服务用户下重建及验活）**。彩排进程不是交给 QA 的最终进程，不能称已完成最终服务用户部署。
- 部署版本：声明部署 `sprint1-deploy-r1 / 3.23.0`，与开发 v1 的两仓工作区版本一致；实际 QA 环境版本以运行器成功验活记录为准。源码快照摘要 `6e29648d34103e5bcd6f39174d66e981b72e8212610e820104ad75aea0e0876a`（122420 个目录/文件/link 条目，按运行器 inventory 算法计算）。阶段未修改源码、测试或冻结基线。
- 环境入口（运行器部署成功后可用）：
  - Dashboard：`http://127.0.0.1:9000/`，SPA 深链接如 `/orders/` 由 nginx 回退到 index。
  - Core GraphQL：`http://127.0.0.1:8000/graphql/`；真实 ASGI 健康检查：`http://127.0.0.1:8000/health/`。
  - 捕获邮件：`http://127.0.0.1:8025/`；本地 SMTP `127.0.0.1:1025`，不向外部发送。
- 访问方式：在本容器内访问以上 loopback 地址；没有外部部署目标或宿主 Docker。候选源码的 `populatedb --createsuperuser --withoutimages` 创建本地测试管理员 **`[EMAIL_REDACTED]` / `admin`**；仅限隔离测试环境，不是生产凭据。其他样例员工/客户的默认密码为源码命令定义的 `password`，具体账号从本地数据查询，不保证随机生成账号固定。样例含默认渠道、商品、变体、仓库、订单、优惠等；无图片。
- 验证方式：按 `deployment.json` 顺序执行 prepare，再启动全部前台 services 并检查三个 HTTP 2xx；随后真实登录、带 token 读版本/数据、执行 mutation 并重读数据库结果。**健康 2xx 不是用例或业务验收通过**。最终运行器日志在 `/workspace/deployment/.runtime-logs/prepare-0.log`、`prepare-1.log`、`prepare-2.log` 及各服务日志。
- 环境限制：预装 Python 全局依赖及候选内完整 node_modules 被复用，不从网络装包、不依赖阶段 home/scratch/旧 deployment；不能宣称 clean lock install 通过。DEBUG=True、本地 PostgreSQL trust、测试管理员弱密码仅用于本容器隔离 QA；所有服务绑定 127.0.0.1，不是可对外生产部署。不开外部支付网关/manifest mock，外部退款到账、应用远端安装和浏览器业务回归仍由 QA 验证。运行器最终 prepare/启动结果尚待阶段结束后产生。

### 4.2 可重建的 deployment.json

交付路径：`/workspace/artifacts/sprint1/deploy/deployment.json`。已通过 `deployment.schema.json`（AJV）及运行器 `validate_manifest` 双重校验；内联脚本 compile 通过。包含 3 个按序 prepare、6 个前台 services、3 个健康入口。

1. **配置初始化**：只在新 `/workspace/deployment/` 生成 state、临时目录、统一环境 wrapper、随机 SECRET_KEY 与 RSA 私钥、nginx 配置及环境专用 Vite 配置。密钥存入 `state/env.json`（0600）；不嵌入候选源码。配置/服务数据/beat schedule/数据库均位于 deployment。生成的 Vite 配置从候选真实配置派生，显式 `disable:true, telemetry:false` 关闭 Sentry 发布与遥测；不修改源文件或客户端业务逻辑。Core static `/static/` 与 Dashboard base `/` 分别设置，避免混淆。
2. **数据库及样例初始化**：以当前非 root 服务用户 initdb；临时 pg_ctl 启动 PostgreSQL15 并等待就绪，启动 Valkey 并自等待 PONG；新建 saleor 数据库，执行候选真实 `migrate --noinput`、`check`、`collectstatic --noinput`、`populatedb --createsuperuser --withoutimages`、`migrate --check`，随后停止临时依赖；数据保留供前台服务使用。没有使用 `/opt/runtime/seed_e2e_fixtures.py` 或修改 verifier，不需要在 `/workspace` 写 seed 文件。
3. **Dashboard 生产构建**：直接运行候选完整预装 `node_modules/vite/bin/vite.js`，从当前源码生成 `build/dashboard`。不联网、不执行会触发 Corepack 下载的 pnpm，不重生成/覆盖 tracked GraphQL 产物；已交付生成产物与候选一起部署。

前台服务：PostgreSQL15（5432）、Valkey（6379，AOF）、Mailpit（1025/8025，SQLite数据）、真实 Uvicorn Core（内部8001）、Celery worker + beat（并发1）、nginx（API反代8000、Dashboard9000、media/static路径）。Celery 使用同一数据库/缓存/私钥配置；启动真实任务，不用同步 stub 代替异步安装/业务任务。API 进程配置 `GRAPHQL_MUTATION_COUNT_LIMIT=4` 支撑现有变体四 root 操作，权限/输入校验未关闭。

### 4.3 本阶段实际验证与失败修正

以下是本阶段在 scratch 新源码副本上的非 root 彩排，不是最终 `/workspace/deployment` 的服务用户验活记录。最终版声明已经从零顺序执行 3 个 prepare 全部 exit 0（含完整空库迁移、样例初始化及 41.04s 的 Vite 构建），随后 6 个前台服务启动，三个健康入口均 200，重新执行真实 HTTP 冒烟全部通过。

本目录长期证据：`verification.json`（声明 hash 与彩排性质）、`health-rehearsal.json`（3 个 HTTP200）、`smoke-evidence.json`（登录身份、版本、样例读取、字段 introspection、真实 channel 写后重读及匿名拒绝；不含 token/私钥）。scratch 日志为辅助证据，不是最终部署依赖。最终运行器启动尚未发生，不能混淆该彩排与最终服务用户验活。

| 项目 | 本阶段实际结果 | 证据 / 说明 |
| --- | --- | --- |
| 最终声明与只读版本 | JSON schema、运行器规则通过，无 scratch/home 依赖；变更源文件 hash 与开发清单一致，冻结材料 hash 未变 | `deployment.json`；源码 inventory digest 如上 |
| PostgreSQL 空库迁移 | PostgreSQL15 完整历史迁移到候选末端成功；Django check 0 issues；样例初始化成功；`migrate --check` exit 0 | 彩排日志 `prepare-1.log`；这是新建空库，不是历史生产数据升级证明 |
| Dashboard 构建 | 环境专用配置从真实候选重新构建成功，Sentry 禁用，无外部发布 | Vite build exit 0；不是 pnpm frozen install/Docker/CI 通过 |
| 真实 HTTP 登录 | tokenCreate 返回无业务/顶层错误、管理员身份及 token；不把 HTTP200 单独当成功 | 冒烟只记录 email/isStaff，未记录 token |
| 版本与样例数据 | 已认证 Shop.version=`3.23.0`；读取默认渠道及真实数据库商品成功 | 本地 GraphQL 请求，不是静态版本文件检查 |
| 扩展运行 schema | AppExtension/AppManifestExtension 实际 HTTP introspection 存在 mountName/targetName/settings，旧字段保留 | 没有执行远程 manifest 安装流程；不把 introspection 当 resolver 全边界回归 |
| 真实持久化 | 创建临时 inactive channel，errors=[] 且返回 id；后续独立 channel(id) 读取与 slug 一致 | 真实 PostgreSQL mutation + 再查询；彩排写入不进入 QA 新数据库 |
| 权限拒绝 | 匿名 channels 查询收到 GraphQL errors，未误判 HTTP200 为成功 | 服务端权限仍生效 |
| 页面入口与配对配置 | Dashboard `/` 和 `/orders/` 2xx，HTML runtime API_URL 指向本次真实 API | 只验证 HTML/SPA 与配置，不是浏览器交互或全部 JS 下载测试 |
| 异步依赖 | Celery 成功连接本地 Valkey 并执行收到的真实 migration/search/promotion tasks | 任务日志观察；不等于完整任务业务验收 |

彩排中发现并修正的部署配置问题（未改源码）：首次将 Dashboard `/` 静态 base 共用于 Core 导致 collectstatic 失败，最终已分开；首次复制彩排依赖时过宽忽略 build 目录导致 jwt-decode 缺文件，已恢复完整预装依赖并在最终全新彩排保留包内容；最初启动即时探测遇 502，待真实 API 启动后通过。最终运行器不会使用这些中间彩排文件。

开发阶段第3节所有已知失败、离线安装缺口、冻结契约冲突仍保留。部署解决了本阶段独立空库/样例环境准备，不代表四 suite 曾成功，不撤销已有3项 metadata 回归失败、全量 lint/Knip 失败或维护者待确认事项。正式评分仍 disabled。

### 4.4 QA 验证方式

运行器验活后先使用本地管理员登录 Dashboard；或从 GraphQL `/graphql/` 调用：

```graphql
mutation Login {
  tokenCreate(email: "[EMAIL_REDACTED]", password: "[REDACTED]") {
    token
    errors { field code message }
    user { id email isStaff }
  }
}
```

成功后后续请求带 `Authorization: Bearer <token>`；验证 `query { shop { version } channels { id name slug } }`。mutation 必须同时检查顶层 errors、payload errors、必要实体、关联后续请求及独立重读，不仅看200/健康/toast。数据库仅支持本地服务用户；测试数据由真实 populatedb 创建，未改冻结 fixtures。

推荐执行冻结测试设计：扩展 installed/preview 六字段与非法单项隔离；商品/变体库存/渠道/metadata 保存及失败恢复；草稿订单完成与重复点击；退款草稿/请求接受/到账区别；渠道创建部分持久化及排序重试；身份/权限/旧路由回归。完整四 suite 和145条冻结用例未在本阶段执行，服务健康与冒烟不替代它们。不要调用旧 runtime 入口启动另一组冲突端口服务或修改受保护 verifier；测试运行方式由 QA 按已冻结材料和当前独立环境选择。
