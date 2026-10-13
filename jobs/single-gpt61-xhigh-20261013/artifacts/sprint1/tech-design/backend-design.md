# 后端技术设计：Saleor Core 与 Dashboard 协同迁移至 3.23.0

版本：v1
责任：后端技术设计
依据：PRD v1，artifacts/sprint1/prd/prd.md
修订：首次交付（2026-10-13）；在冻结需求上形成可实施的协同迁移方案，补齐实测的 App 扩展消费契约差异，保留完整 Base SDL；完整目标功能规格仍受 PRD Q01—Q03 阻塞。

## 1. 方案概述

继续采用既有 Django/Graphene Core 单体、PostgreSQL、Celery 与插件/webhook 架构，不新增网关、REST 服务、支付模拟服务或新的业务状态机。材料路径是 `/workspace/repos/saleor`，`/workspace/saleor` 为其别名。当前阶段只写设计及目标协议，不改代码、不执行迁移、不提交仓库。

现有生产链：`saleor/graphql/api.py` 汇总各域 Query/Mutation 并构造 federated schema；`saleor/graphql/management/commands/get_graphql_schema.py` 导出同一运行时 schema；`pyproject.toml:149-157` 提供导出与迁移任务。Mutation 通过 `saleor/graphql/core/mutations.py` 的既有权限、输入清理与错误归一化进入业务服务；域内事务、插件及 webhook 生命周期不搬到 resolver 中重新实现。结算建单路径在 `saleor/graphql/checkout/mutations/checkout_complete.py` → `saleor/checkout/complete_checkout.py`，包含原子建单、库存分配、付款关联及提交后事件。

**已实测而非推测的跨仓问题：**两个 Base SDL 均通过语法/类型校验，但 Dashboard 的 SDL 比 Core 多 `AppExtension` 与 `AppManifestExtension` 各三个字段：`mountName: String!`、`targetName: String!`、`settings: JSON!`。Dashboard 的 `src/extensions/queries.ts` 实际读取已安装扩展的三个字段，直接对 Core Base 校验产生三个未知字段错误。因此本轮明确包含对外接口变更：BD02 用旧模型和已验证 manifest 信息派生六字段，保留旧 API。该适配是 R02/R03 的可追溯一致性修复，**不是声称它们是上游 3.23 新功能**；现有 Dashboard changelog 已将该消费记录在 3.22.9。

`target-schema.graphql` 从给定 Core Base 完整构造，唯一结构新增为上述六字段；对两个类型的旧 `mount/target` 及 `AppExtension.options` 增加弃用提示，不移除旧字段、枚举、filter、输入、订阅或自定义 directive。未变更域完整保留。没有查阅升级后 schema。Shop 版本的变化是返回值语义，SDL 保持 `String!`。目标文件是本设计范围的完整 SDL，不是完整上游 3.23 发布规格的证明。

## 2. 需求覆盖

| 需求 | 设计单元 |
| --- | --- |
| R01 | BD01、BD02、BD06 |
| R02 | BD02、BD03、BD06 |
| R03 | BD02、BD06（Core 提供统一 schema；前端生成见 FD02） |
| R04 | BD03、BD06 |
| R05 | BD04 |
| R06 | BD05 |
| R07 | BD05、BD06 |
| R08 | BD06 |

R01 的已知版本与生产契约可实施，AC-01-2 的完整目标行为尚不能闭合。R05 本轮六字段适配没有新增模型要求；BD04 定义可执行的迁移验证及后续扩展门槛，不凭空添加迁移。接口变更集中 I01—I03，其余 I04—I09 登记为跨端回归边界而非新增/修改业务规则。

## 3. 详细设计

### BD01 · 统一版本与生产发布元数据
- 覆盖需求：R01
- 设计说明：
  - 修改实施落点：`saleor/__init__.py.__version__`、`pyproject.toml [project].version`、`uv.lock` 的项目条目、Core `package.json/package-lock.json` 的本项目版本均为 `3.23.0`。不改变其他包的独立版本。`saleor/__init__.py` 派生的 `schema_version` 为 `3.23`，`user_agent_version` 为 `Saleor/3.23`。
  - `saleor/graphql/shop/types.py` 中 `Shop.version/schema_version` 保持已有 resolver 与权限，只返回真实模块元数据，不硬编码测试输出；I01 不增新参数，不修改类型。
  - 更新 `.release-it.json` 的版本写入目标至真实 `[project].version`；核对发布脚本不再假设已经不存在的 `tool.poetry.version`。发布动作本阶段不执行。
  - 版本修改不是能力开关；必须完成 BD02 和所确认的目标业务任务后，才允许将版本校验作为验收的一部分。涉及目标 manifest 的 `requiredSaleorVersion` 检查使用已有语义版本逻辑，不能无条件满足约束。
  - 验证：静态比对版本来源；实施后正常启动，授权员工/App 读取 I01，断言 `3.23.0/3.23`；匿名访问受保护版本字段保持 Base 的错误和可见性。不要用 health 成功替代 API 验证。

### BD02 · App 扩展六字段的非破坏兼容适配
- 覆盖需求：R01、R02、R03
- 设计说明：
  - 落点：`saleor/graphql/app/types.py.AppExtension`、`saleor/graphql/app/types.py.AppManifestExtension` 增加字段与显式 resolver，JSON 使用 `saleor/graphql/core/scalars.py.JSON`（GenericScalar），不是 `JSONString`。必要时在同域新增纯函数 `normalize_extension_settings`；不得把 manifest/数据库字典直接作为字符串输出。
  - **安装实体来源：**`saleor/app/models.py.AppExtension` 已有 `mount`、`target`、`http_target_method`；安装路径 `saleor/app/installation_utils.py.install_app` 已把 `new_tab_target/widget_target.method` 持久化为 method。`mountName = root.mount.upper()`、`targetName = root.target.upper()`，仅返回现有 Enum 对应的名称。不支持任意新 mount/target，不修改 manifest 输入校验或 GraphQL filter。
  - **settings 映射：**NEW_TAB 且已存 method 时返回 `{"newTabTarget":{"method":"GET"}}` 或 POST；WIDGET 对应 `widgetTarget`；其余 target 或无 method 返回 `{}`，绝不返回 `null`、`"{}"` 或 `{"method":null}`。缺省 method 的前端行为为 GET。已安装扩展没有任意 JSON 配置存储，本设计不暗示它能保存未声明配置。
  - **manifest 来源：**`AppFetchManifest` 使用既有获取/验证/`clean_manifest_data` 链，`AppManifestExtension` root 为清洗后的 dict。把小写 `mount`/`target` 输出成相同名称大写；未指定 target 按既有默认 popup 输出 `POPUP`；清洗后的 `options.new_tab_target/widget_target.method` 转换为上述 camelCase JSON。没有 options 返回 `{}`。避免对已规范化的枚举值重复错误转换；用单元用例覆盖每个枚举、默认值与 snake_case→camelCase 转换。
  - `settings` 与旧 `options` 必须来自同一源值：不新增独立写路径、不双写、不缓存不同配置。旧 options union resolver 和 legacy 输入校验保持原行为。权限、URL检查、extension token 生成不变；设置里不加入 accessToken、私有 metadata 或未授权权限。
  - `AppExtension` 的 `mount/target/options`、`AppManifestExtension` 的 `mount/target` 增弃用描述，与目标 SDL 一致；保留旧 Enum、union、过滤器及参数默认值。旧 options 子类型不在本轮额外弃用，避免扩大差异。
  - 这六个 read-only 字段不新增 Mutation，不改变事务，也不触发 webhook；读取失败按现有 GraphQL 错误处理，不能兜底伪造一个挂载位置。有效 Base 数据必须能提供非空值，异常历史数据需定位修复后才放行，不能因 `String!`/`JSON!` null bubbling 静默丢失列表。
  - I02 是真实 Dashboard 消费，I03 是安装预览协议一致性：当前预览仍读取旧枚举，保留其请求即可，无需强制 UI 重写。
  - 验证：比较新旧字段对相同 root 的值；真实运行 I02 无未知字段；覆盖四 target、所有现有 mount、GET/POST/无 options、带权限/缺权限、旧字段查询。manifest 预览和安装后查询在配置上对应。不得用静态 SDL 测试代替 resolver 测试。

### BD03 · 保持商品、订单、退款、渠道和结算生产语义
- 覆盖需求：R02、R04
- 设计说明：
  - 商品：沿用 `saleor/graphql/product/mutations/` 的产品、变体、渠道 listing 和库存写入；I05 中组合操作可能包含多个 Mutation 根和多次请求，不将它们声称为跨请求原子事务。输入类型、externalReference/ID/SKU 选择规则、业务错误码、渠道范围不改变。默认不允许前端失败重试自动重复创建商品/变体。
  - 草稿订单：`saleor/graphql/order/mutations/draft_order_complete.py` 继续验证草稿状态、地址、商品与库存，沿用 order actions；I06 的成功须有返回订单及后续可读状态。不能对非草稿强制完成。事件发布位置遵循现有事务提交边界。
  - 退款：沿用 `saleor/graphql/order/mutations/order_grant_refund_create.py`、`order_grant_refund_update.py`、`order_refund.py` 和 `saleor/graphql/payment/mutations/transaction/transaction_request_refund_for_granted_refund.py` 的额度、状态与权限。授予退款、发出退款请求和支付提供方实际完成是不同步骤。I07 不新增自动重试、不把请求接收当转款成功、不放宽超额限制。
  - 渠道：`saleor/graphql/channel/mutations/` 保留创建、更新、仓库排序/关联、付款设置及字段级特殊权限。I08 更新只有 paymentSettings/orderSettings/checkoutSettings 时按 Base 原权限执行，不一律收紧成 MANAGE_CHANNELS，也不扩大混合更新权限。
  - 结算：`CheckoutComplete.perform_mutation` 和 `saleor/checkout/complete_checkout.py` 保留 email、非空行、商品可用性、地址、库存/预售、支付校验。建单采用既有事务和分配逻辑，异步 order 事件在 commit 后。旧 payment 的 `confirmationNeeded=true` 时无订单属合法中间态；不能为获得 success 生成未付款假订单。
  - 事务策略：只在确实修改域内逻辑时沿用域内原子事务与锁顺序，不能在 GraphQL请求全域包一层事务后同步等待 webhook/付款。外部动作失败由既有插件/任务处理，不把提交后的业务对象删除补偿为“回滚付款”。
  - 验证：I05—I09 正向/负向/权限用例，重新查询验证存储；选定 P2P 保持通过。暂无依据更改这些接口的 SDL、状态机或错误码；未来目标差异需新增稳定 I/BD 编号或明确修订现有单元。

### BD04 · 数据模型与存量迁移门槛
- 覆盖需求：R05
- 设计说明：
  - 本轮 BD02 只从现有字段派生，无新表、新列或必要数据回填，因此**不新增空迁移，不重编号、合并或替换 Base 迁移**。Core 版本号变化也不自动生成 Django migration。`http_target_method` 为可空已有字段，无值在接口侧输出 `{}`，不批量把 null 改成 GET。
  - 实施前检查现有 AppExtension 的 mount/target 是否属于已有 choice、method 是否为 GET/POST/null，确认不存在会破坏新增非空字段的脏数据；若有，只在当前报告记录，修复规则须经确认，不静默改变旧对象。
  - 全量目标模型变化受 Q03 阻塞：确认后在对应 app 创建链尾 migration，依赖现有末端及外键 app；使用历史模型和明确可逆/不可逆规则。不得直接更新冻结 fixture 或生产库来掩盖漏 migration。
  - 验证计划：空库完整 `migrate`；包含商品/订单/用户/渠道/App 的 3.22 数据副本升级；记录对象标识、关联、金额/状态、扩展 method 前后不变量；`makemigrations --check --dry-run` 无差异；重复 `migrate` 无必要待执行项。本阶段未启动服务或数据库，均未运行。
  - 回滚：本设计无数据转换，可撤销代码兼容层但需同步回退前端消费；完整3.23若存在破坏性迁移须另行获批备份/恢复方案，不能承诺所有 migration 自动可逆。

### BD05 · 离线工具链与可导出生产交付
- 覆盖需求：R06、R07
- 设计说明：
  - 后端继续 Python 3.12、uv/Hatchling；Graphene <3、graphql-core 2.x 等保持与既有实现匹配。`/opt/environment/dependencies/target/saleor/pyproject.toml`/`uv.lock` 仅用于核对允许的本地依赖和目标版本，不把其中包差异反推业务功能，不读取目标源码/schema。
  - 使用精确本地依赖声明/锁版本，保留实施必须的 Base-only 依赖（如当前入口 `pillow_avif` import），或经正常代码重构后移除，不直接覆盖整个 target manifest 导致原生产导入缺包。修改声明后用离线锁一致性检查；缺离线包则记录阻塞，不能联网 `uv sync`/安装解决。
  - 核对 Dockerfile 的 Python、`uv sync --locked`、静态资源和 Uvicorn入口；发布配置与 BD01 统一。镜像/CI运行是否纳入最终批准入口见 Q06，离线环境没有基础镜像时不可宣称已验证容器构建。
  - 研发变更仅为两个仓库的生产普通 diff，纳入 schema、migrations（若有）、代码生成及锁文件，不改预装环境/评估脚本/测试 fixture。当前阶段不开发，不以设计文件外的临时补丁作为交付。

### BD06 · 契约与运行验证分离
- 覆盖需求：R01、R02、R03、R04、R07、R08
- 设计说明：
  - 第一道门：检查目标 SDL parse/build/validateSchema、全部类型引用、Base→target breaking/dangerous diff、前端实际操作校验，结果见接口契约 §3；本轮已执行。
  - 第二道门（实施后）：从 Core 生产 schema 导出到允许的本地位置，与本设计及仓库 schema 做规范化语义比较；同步 Dashboard schema 再生成。若生产返回值无法满足六字段，第一道门不能代替第二道门通过。
  - 第三道门：生产 resolver/unit/API权限和错误路径，空库/存量升级验证，再按指定入口执行 `core-unit/core-e2e/dash-unit/dash-e2e`。输出按用例标识核对而不只检查退出码；收集失败、缺失、跳过均不替代 required pass。健康检查只确认环境。
  - 完整目标变化须映射已确认 Q01—Q03；正式 F2P/P2P 清单接受、冻结前仅报告候选验证，不宣称正式评分或3.23业务完整性。冻结 PRD/测试材料只读。

## 4. 接口清单

完整、权威语义见 `interface-contract.md`；类型/参数以 `target-schema.graphql` 为准。

| 接口 | 所属设计单元 | 说明 |
| --- | --- | --- |
| I01 | BD01 | Query.shop 的版本返回值统一为3.23.0/3.23 |
| I02 | BD02 | Query.appExtensions 的 AppExtension 新三字段及旧字段兼容 |
| I03 | BD02 | Mutation.appFetchManifest 的 Manifest.extensions 新三字段 |
| I04 | BD02 | App安装/重试与状态查询生命周期，结构不变 |
| I05 | BD03 | 商品/变体/渠道 listing 写入与重读，结构不变 |
| I06 | BD03 | 草稿订单创建/完成，结构不变 |
| I07 | BD03 | granted refund、旧Payment退款及Transaction退款请求，结构不变 |
| I08 | BD03 | 渠道创建/更新及重读，结构不变 |
| I09 | BD03 | checkoutComplete 的既有支付、建单与重入语义，结构不变 |

## 5. 工程任务与依赖

### BT01 · 确认目标范围和冻结基线
- 覆盖设计单元：BD01、BD03、BD04、BD06
- 依赖：无
- 工作与验证：记录两仓固定baseline与只读材料摘要；建立Q01—Q06追踪，区分本轮可实施六字段/工具链任务与未确认目标差异。完整目标功能、迁移与正式验收受阻，但不阻塞已知兼容层实现。不得修改PRD/官方用例以消除未决项。

### BT02 · 实现扩展派生字段并保护旧消费者
- 覆盖设计单元：BD02
- 依赖：BT01
- 工作与验证：修改两个Graphene类型、纯映射函数、弃用描述；不新增模型；实现I02/I03矩阵测试和旧schema消费回归；确认权限/token/URL路径不变。输出的settings必须是JSON对象；安装前后配置对应。完成依据是生产resolver运行通过，不是仅有目标SDL。

### BT03 · 统一版本、依赖和发布配置
- 覆盖设计单元：BD01、BD05
- 依赖：BT01
- 工作与验证：更新准确版本位置、核对Python/uv/锁文件及发布写入路径；离线启动和元数据校验。不执行对外发布、不拉取镜像，不盲覆盖目标依赖清单。

### BT04 · 完成模型及迁移验证
- 覆盖设计单元：BD04
- 依赖：BT02、BT03
- 工作与验证：确认六字段无需迁移；执行空库/存量库/无遗漏migration检查。Q03确认后另追加必要模型与迁移任务，不把未知变更标记为完成。

### BT05 · 导出统一SDL并交接前端生成
- 覆盖设计单元：BD02、BD06
- 依赖：BT02、BT03
- 工作与验证：由正常运行Core导出schema并与目标做语义diff；每个差异有I编号；移交同份schema给FD02，保持全部Base定义。前端当前操作通过校验，旧操作仍合法；双方不得各自改出不同schema。

### BT06 · 联调与回归验收
- 覆盖设计单元：BD03、BD04、BD06
- 依赖：BT04、BT05；前端FD02—FD06对应实施完成
- 工作与验证：执行真实配对API/UI流程，核对持久化与支付中间态；四套件收集完整结果。BT06可进行本地回归，但正式通过必须等待Q04冻结；缺少Q01—Q03时只报告已知范围，不声称全部3.23目标已实现。

## 6. 其他

- 设计推导边界：本轮只解决可证明的两端App扩展差异、版本与工程一致性；不实现任意未知mount/target、不新增退款业务规则、不扩充feature flags。Q01/Q02仍阻塞完整3.23范围，Q03阻塞目标数据迁移清单，Q04阻塞正式评分，Q05阻塞旧入口删除，Q06阻塞所有容器/CI入口的统一验收结论。冻结基线不修改。
- 风险：非空字段 resolver 的异常会导致GraphQL列表/对象null bubbling；method转换拼写错误会导致前端Zod拒绝挂载；manifest预览与安装后映射若来自不同源会产生配置漂移。用BD02映射矩阵及正常安装重读验证。
- 本轮完成的检查是离线SDL及操作静态校验，未运行Core生产导出、resolver测试、数据库、依赖同步、构建和四类运行套件；详细实际结果在接口契约§3。静态通过不等于生产运行/正式验收通过。
- GraphQL是本轮唯一发生变化的远程协议。既有manifest下载/iframe访问仍沿用现有JSON/HTTP协议且未改变输入格式，因此不新增REST/gRPC或独立OpenAPI。没有生成目标源代码、没有使用测试专用桩。
