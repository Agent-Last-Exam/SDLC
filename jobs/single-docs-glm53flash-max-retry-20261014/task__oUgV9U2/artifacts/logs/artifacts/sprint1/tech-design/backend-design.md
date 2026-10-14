# 后端技术设计：Saleor core 3.23.0 迁移

版本：v1
责任：后端技术设计
依据：PRD v1，artifacts/sprint1/prd/prd.md
修订：首次交付；修订时记录版本、内容及原因

## 1. 方案概述

本次迁移的 core 侧工作是把基线 `c864e66`（Release 3.22.0 + 环境补丁）推进到 3.23.0：版本与描述常量、GraphQL 契约（AppExtension 域字段补齐 + 批量请求 mutation 数量上限）、依赖与构建声明对齐、以及少量随依赖调整的代码适配。全部改动为普通源码编辑，落在 `saleor/` 仓库。

与 3.22→3.23 实际行为差距的勘察结论：

- **AppExtension 契约缺口（核心 F2P）**：dashboard 3.22.9 已按新字段消费（`CHANGELOG.md` 3.22.9 段："Switched to the new AppExtension fields introduced in 3.22 patch (mount -> mountName, target -> targetName, options -> settings)"），`src/extensions/queries.ts` 的 `ExtensionList` 查询选择 `mountName/targetName/settings`，`src/extensions/hooks/useExtensions.ts` 用 zod 校验 `settings`；而 core 3.22.0 的 `AppExtension`/`AppManifestExtension`（`saleor/graphql/app/types.py:108-288`）仍只暴露 `mount`/`target`/`options`。core 须补齐这三个新字段并给旧字段加废弃标记，`saleor/graphql/schema.graphql` 重新生成。
- **批量请求 mutation 数量上限（F2P）**：运行时以 `GRAPHQL_MUTATION_COUNT_LIMIT=4` 启动 API（`/opt/runtime/services.sh:84`，注释指明针对 Dashboard `VariantUpdate` 的四根字段变更文档、并说明 pytest 保留上游默认设置）。基线代码无此设置与校验，须新增：默认关闭（0），仅当环境变量配置时在 HTTP 层拒绝超限请求。
- **依赖对齐（R08）**：目标清单（允许输入 `/opt/environment/dependencies/target/saleor/{pyproject.toml,uv.lock}`，策略见 `/opt/runtime/dependency-union.json`"base dependencies upgraded by target lockfiles; base-only packages retained"）要求：移除 `Adyen`、`draftjs-sanitizer`、`html-to-draftjs`、`pillow-avif-plugin`、`posuto` 的声明；新增 `kombu[sqs]>=4.6.11,<6.0.0`、`nh3>=0.2.20`、`idna>=3.10`、`orjson>=3.11.4`；`version = "3.23.0"`。移除的包在运行环境中仍保留（`import Adyen, posuto, draftjs_sanitizer, html_to_draftjs` 均可导入），因此生产行为不变。
- **目标 uv.lock 与基线差异极小**：包集合仅 +`nh3 0.3.2`、+`orjson 3.11.7`、-`adyen/draftjs-sanitizer/html-to-draftjs/pillow-avif-plugin/posuto/beautifulsoup4/soupsieve`（后两者为 Adyen 的传递依赖），`saleor` 自身 3.22.0→3.23.0；`kombu 5.5.4`、`idna 3.10` 不变（仅在 pyproject 补充约束声明）。
- **数据库迁移**：AppExtension 新字段全部由既有列派生（`mount`/`target`/`http_target_method`），manifest 级字段由 manifest dict 派生，均无需模型/迁移变更；交付前以 `makemigrations --check --dry-run` 验证无遗漏（R04）。

模块落点（均在现有行为链上小步修改）：

| 关注点 | 模块/文件 |
| --- | --- |
| 版本常量 | `saleor/__init__.py`（`__version__`，`schema_version`/`user_agent_version` 自动派生）、`pyproject.toml` |
| 描述常量 | `saleor/graphql/core/descriptions.py`（新增 `ADDED_IN_323`） |
| AppExtension 契约 | `saleor/graphql/app/types.py`（`AppManifestExtension`、`AppExtension`、`AppExtensionOptionsWidget/NewTab`、`WidgetTargetOptions/NewTabTargetOptions`） |
| mutation 数量上限 | 新文件 `saleor/graphql/core/validators/mutation_count.py` + `saleor/graphql/views.py` + `saleor/settings.py` |
| 依赖声明 | `pyproject.toml`、`uv.lock` |
| 代码适配 | `saleor/__init__.py`（去 `import pillow_avif`）、`saleor/core/utils/json_serializer.py`（去 `draftjs_sanitizer` 导入） |
| 契约文件 | `saleor/graphql/schema.graphql`（`python manage.py get_graphql_schema` 重新生成） |
| 变更记录 | `CHANGELOG.md` |

## 2. 需求覆盖

后端承接：R01、R02、R03、R04、R05、R08、R10；R06/R07 主体由前端承接（R07 依赖的后端行为即本设计的契约与目标行为）；R09 为约束性需求（零改动评估资产），不设设计单元，融入 BD 全部任务的边界条件。无 REST/gRPC 接口；对外接口变更集中在 I01/I02/I03，权威契约见 `interface-contract.md` 与 `target-schema.graphql`。

| 需求 | 设计单元 |
| --- | --- |
| R01 | BD01 |
| R02 | BD02、BD03 |
| R03 | BD02、BD03 |
| R04 | BD05 |
| R05 | BD02、BD03 |
| R08 | BD04 |
| R10 | BD01～BD05（提交纪律） |

## 3. 详细设计

### BD01 · 版本标识与描述常量升级（R01）
- 覆盖需求：R01
- 设计说明：
  - `saleor/__init__.py`：`__version__ = "3.23.0"`；同文件第 24-25 行的 `schema_version = f"{_major}.{_minor}"` 与 `user_agent_version` 由 `__version__` 派生，改值后自动变为 `3.23`，无需单独编辑。`shop` 查询的 `resolve_version`/`resolve_schema_version`（`saleor/graphql/shop/types.py:603-608`）直接读取模块常量，`shop { version schemaVersion }` 随之输出 `3.23.0`/`3.23`（I03）。
  - `pyproject.toml:7`：`version = "3.23.0"`（与目标清单一致）。
  - `saleor/graphql/core/descriptions.py`：在 `ADDED_IN_322`（第 17 行）后追加 `ADDED_IN_323 = "\n\nAdded in Saleor 3.23."`，供后续描述引用；不改动既有常量。
  - `CHANGELOG.md`：在文件头部（`# Changelog` 引言之后、`# 3.22.0` 之前）新增 `# 3.23.0` 段落，按上游格式分小节（GraphQL API / Bug fixes 等），记录 AppExtension 新字段与废弃、批量请求 mutation 数量上限；3.22 及更早记录一字不改。
  - 验证：`python -c "import saleor; print(saleor.__version__, saleor.schema_version)"` 输出 `3.23.0 3.23`；`uv lock --check` 通过（`uv.lock` 中 `saleor` 包版本同步为 3.23.0）。

### BD02 · AppExtension 契约补齐与废弃标记（R02、R03、R05）
- 覆盖需求：R02、R03、R05
- 设计说明：
  - **语义定义**：`mountName` 是扩展挂载点名称字符串（取值集合与 `AppExtensionMountEnum` 成员名一致，UPPER_CASE，如 `PRODUCT_OVERVIEW_MORE_ACTIONS`）；`targetName` 是扩展打开方式名称字符串（与 `AppExtensionTargetEnum` 成员名一致：`POPUP/APP_PAGE/NEW_TAB/WIDGET`）；`settings` 是 JSON 对象，承载原 `options` 的信息：`{"newTabTarget": {"method": "GET"|"POST"}}` 或 `{"widgetTarget": {"method": "GET"|"POST"}}`，无配置时为 `{}`。
  - **`AppManifestExtension`（manifest dict 根，`saleor/graphql/app/types.py:108`）**：
    - `mount`/`target` 增加 `deprecation_reason="Use \`mountName\` instead."`，字段保留、解析行为不变（兼容 R05）。
    - 新增 `mount_name = graphene.String(required=True, description="Name of the extension mount point in the dashboard. Replaces `mount`" + ADDED_IN_322)`；解析器返回 `AppExtensionMountEnum` 成员名：`getattr(AppExtensionMountEnum, root.get("mount") or AppExtensionTarget.POPUP 形态的成员).name`——即把清洗后的小写枚举值（`_clean_extension_enum_field` 将 `extension["mount"]` 归一为枚举值）转回 UPPER 名。实现上取 `root["mount"]`（经清洗后必为合法枚举值）并 `str_to_enum`/查表得成员名，避免依赖 graphene 自动解析；缺省时与 `target` 同理由 `resolve_target` 的 POPUP 缺省语义兜底。
    - 新增 `target_name = graphene.String(required=True, description="Name of the extension target in the dashboard. Replaces `target`" + ADDED_IN_322)`；复用 `resolve_target` 的结果（POPUP 缺省规则不变）转成员名。
    - 新增 `settings = graphene.JSONString(required=True, ...)` 形态的字段——注意：目标 SDL 中该字段类型为 `JSON`。基线 core 的 `JSON` 标量即 graphene `generic.GenericScalar`（见 schema.graphql 中 `scalar JSON` 的既有使用：`data: JSON` 等）。实现时以 `graphene.Field(lambda: GenericScalar, required=True)` 或项目内既有的 JSON 标量类型声明，保证生成 `settings: JSON!`。描述为 `"JSON object with settings for this extension." + ADDED_IN_322`。解析器从 manifest extension dict 的 `options`（camelCase：`options.get("newTabTarget", {}).get("method")` / `options.get("widgetTarget", ...)`，见 `saleor/app/manifest_validations.py:80-86` 的读取方式）构造 `{"newTabTarget": {"method": ...}}` 或 `{"widgetTarget": {"method": ...}}`，无 options 时返回 `{}`。
    - `AppManifest`（`Manifest` 类型，`types.py:494`）的 `extensions` 列表元素即此类型，无需改 `App.manifest`/`AppFetchManifest` 链路。
  - **`AppExtension`（DB 根，`types.py:199`，继承 `AppManifestExtension`）**：
    - 继承得到 `mount_name`/`target_name`/`settings` 字段，按 DB 根覆盖解析器：`resolve_mount_name` 返回 `root.mount`（`AppExtensionMount.CHOICES` 小写值）对应的 UPPER 成员名（`root.mount.upper()`，二者一一对应）；`resolve_target_name` 同理 `root.target.upper()`（模型有 `default=POPUP`，不会为空）。
    - `resolve_settings`：复用 `resolve_options`（`types.py:275-288`）的分支逻辑产生 dict 而非对象：`target == WIDGET` → `{"widgetTarget": {"method": root.http_target_method}}`；`target == NEW_TAB` → `{"newTabTarget": {"method": root.http_target_method}}`；否则 `{}`（`http_target_method` 可为 NULL，与 `resolve_options` 的入参语义一致）。
    - `resolve_url` 的 URL 拼接（`resolvers.py:85-97`：`url.startswith("/") and appUrl and target == POPUP`）不变；`useExtensions` 端 `targetName === "NEW_TAB"` 分支依赖的语义与 `target == NEW_TAB` 一致。
  - **options 对象组废弃标记（字段保留，解析器不动）**：`AppExtensionOptionsWidget.widgetTarget`、`WidgetTargetOptions.method`、`AppExtensionOptionsNewTab.newTabTarget`、`NewTabTargetOptions.method` 增加 `deprecation_reason="Use \`settings\` field directly."`；`AppExtension.options` 增加 `deprecation_reason="Use \`settings\` field instead."`。SDL 输出与 dashboard 3.22.9 期望逐行一致（详见 I01）。
  - **既有 P2P 兼容**：`saleor/graphql/app/tests/queries/test_app_extensions.py:20-84` 等既有用例查询 `mount/target/options`——字段未删、解析器未改，行为保持。描述文本（"Added in Saleor 3.22."）维持不变（这些字段在 3.22 期即为该描述），新字段描述沿用 dashboard 期望的 "Added in Saleor 3.22."（与目标 SDL 逐字符一致；此为上游对该补丁集的既有标记方式，`ADDED_IN_323` 供 3.23 期真正新增的元素使用）。
  - **schema 再生成**：`python manage.py get_graphql_schema > saleor/graphql/schema.graphql`，diff 应仅含 AppExtension 域上述行（含 `scalar JSON` 相对位置随 print 顺序的变化）；输出即 `target-schema.graphql`（已随设计交付，diff 验证与 dashboard 3.22.9 `schema.graphql` 完全一致）。

### BD03 · 批量请求 mutation 数量上限（R03、R02）
- 覆盖需求：R03、R02
- 设计说明：
  - **目标行为**：运行时部署以 `GRAPHQL_MUTATION_COUNT_LIMIT=4` 启动（`/opt/runtime/services.sh:84`）。Dashboard `VariantUpdate`（`saleor-dashboard/src/products/mutations.ts:110-175`）是单个文档 4 个根字段（`productVariantStocksDelete/Create/Update/productVariantUpdate`）的一次 POST，因此限值 4 时正常放行；超出即拒绝，且 **pytest 保留上游默认**（环境变量缺省 → 关闭），不改变既有测试语义。
  - **设置**（`saleor/settings.py`，紧跟 `GRAPHQL_QUERY_MAX_COMPLEXITY` 块，约 :842-845 之后）：
    ```python
    # Max number of mutation root fields allowed in a single (possibly batched)
    # GraphQL request. Set GRAPHQL_MUTATION_COUNT_LIMIT=0 to disable (default).
    GRAPHQL_MUTATION_COUNT_LIMIT = int(os.environ.get("GRAPHQL_MUTATION_COUNT_LIMIT", 0))
    ```
    默认 0 = 关闭（与 `FEDERATED_QUERY_MAX_ENTITIES` 的"0 禁用"惯例一致），保证基线/测试行为零变化。
  - **校验器**（新文件 `saleor/graphql/core/validators/mutation_count.py`）：HTTP 层校验而非 graphql-core ValidationRule——原因：需按整个请求（含批量数组）聚合判定并直接以 400 状态码拒绝，`views.py` 现有 cost 校验（:353-381）已提供同位置先例。函数形态参照 `validate_query_cost`：
    ```python
    def validate_mutation_count(document, limit: int) -> tuple[int, list[GraphQLError]]
    ```
    实现要点：graphql-core 2（graphql-core 2.3.2）AST 上遍历 `document_ast.definitions`（通过 `GraphQLDocument.document_ast`，`views.py` 已持解析后的 document），对 `OperationDefinition(operation == "mutation")` 统计其 `selection_set.selections` 中 `Field` 节点数（别名不改计数，单文档多 mutation 操作分别计数后求和；原型已验证 `mutation A { f g } mutation B { h }` 计 3）。query/subscription 操作计 0。返回 `(count, errors)`，超限时 errors 为单条 `GraphQLError`，消息形如 `"GraphQL request exceeded the maximum number of mutation fields (N > limit)."`，`extensions` 携带 `{"code": "GRAPHQL_MUTATION_COUNT_LIMIT_EXCEEDED", "mutationCount": N, "limit": limit}`（错误分层沿用现有 `format_error` 输出）。
  - **接线**（`saleor/graphql/views.py` `execute_graphql_request`，紧跟 cost 校验块 :353 之后、`extra_options` 之前）：
    ```python
    mutation_count, mutation_count_errors = validate_mutation_count(document, settings.GRAPHQL_MUTATION_COUNT_LIMIT)
    if settings.GRAPHQL_MUTATION_COUNT_LIMIT and mutation_count_errors:
        # 与 cost 超限同一返回路径：ExecutionResult(errors=..., invalid=True)
        # → get_response 转 400；批量请求中该条目 400，整体状态码 max(...)=400（_handle_query :129-133）
    ```
    观测：沿用 span 属性与 `record_graphql_query_count(error_type=...)` 的既有模式（错误类型 `GraphQLError`），不新增指标维度。
  - **不实现测试专用分支**：校验器只读 `settings.GRAPHQL_MUTATION_COUNT_LIMIT`，与运行/测试环境无关；pytest 进程不设置该变量即保持关闭，符合"生产实现 + 部署配置限幅"的边界。
  - **验证**：本地以 `GRAPHQL_MUTATION_COUNT_LIMIT=4` 启动 uvicorn，POST 5 根字段 mutation 文档得到 400 与上述错误体；4 根字段文档 200；`GRAPHQL_MUTATION_COUNT_LIMIT` 未设置时行为与基线一致。

### BD04 · 依赖与构建声明对齐（R08、R01）
- 覆盖需求：R08、R01
- 设计说明：
  - **`pyproject.toml`**：按目标清单（允许输入）编辑 `[project].dependencies`：删除 `Adyen>=4.0.0,<5`、`draftjs-sanitizer>=1.0.0,<2`、`html-to-draftjs>=1.0.1,<2`、`pillow-avif-plugin>=1.5.2,<2`、`posuto>=2025.1.0,<2026`；新增 `kombu[sqs]>=4.6.11,<6.0.0`、`nh3>=0.2.20`、`idna>=3.10`、`orjson>=3.11.4`；其余依赖行（含环境补丁的 django ~5.2.13、pillow 12.x、authlib、cryptography）保持不变；`version = "3.23.0"`（BD01）。
  - **`uv.lock`**：目标 lock（允许输入）与基线 lock 的解析差异仅 +`nh3 0.3.2`/+`orjson 3.11.7`、-`adyen`/`draftjs-sanitizer`/`html-to-draftjs`/`pillow-avif-plugin`/`posuto` 及其传递依赖 `beautifulsoup4`/`soupsieve`、`saleor` 版本号变化。交付路径：优先 `uv lock --offline` 基于新 pyproject 重解析（uv 0.8.24 可用；`nh3`/`orjson` 已安装于环境，`requires-python ==3.12.*` 不变）；如离线重解析因缺少缓存元数据不可行，则以目标 `uv.lock` 内容为 3.23.0 依赖解析的权威结果落库（属允许输入的使用，非联网获取），并核对 `uv lock --check` 通过与 `[[package]] saleor version = "3.23.0"`。
  - **行为保持论证（删除声明 ≠ 删除能力）**：`dependency-union.json` 策略为"base-only packages retained"，已实测 `import Adyen, posuto, draftjs_sanitizer, html_to_draftjs` 在环境内可导入：
    - `saleor/payment/gateways/np_atobarai/api_helpers.py:9` 的 `from posuto import Posuto` 与 `format_address` 的 `pp.get(...)`（`test_api_helpers.py:113` 覆盖）继续工作；`settings.py:853-871` 的 `BUILTIN_PLUGINS` 中 `AdyenGatewayPlugin`、`DeprecatedAvataxPlugin` 等注册不动（R05）。
    - `saleor/core/utils/json_serializer.py:3` 的 `from draftjs_sanitizer import SafeJSONEncoder` 仍可导入，但为对齐"已声明移除"的方向：`HTMLSafeJSON`（:26）在仓库内无消费者（唯一 `SafeJSONEncoder` 引用点，`grep` 验证），将其删除并把 `CustomJsonEncoder`/`Serializer` 保留原样；历史迁移 `product/migrations/0096_raw_html_to_json.py`、`page/migrations/0008_raw_html_to_json.py` 对 `draftjs_sanitizer.clean_draft_js` 的导入是历史迁移的合法依赖，运行环境保留该包，不改写历史迁移（R04/R05）。
    - `saleor/__init__.py:1` 的 `import pillow_avif  # noqa: F401` 删除：Pillow 12.x 原生支持 AVIF（已验证 `PIL.Image.SAVE` 含 `'AVIF'`），删 side-effect 导入不改变 AVIF 能力。
  - **离线约束**：全程不执行网络安装；`uv lock --check`、`pnpm install --frozen-lockfile --offline` 为完成判据。
- 验证：`uv lock --check` 退出码 0；`uv run python -c "import saleor"` 不报缺依赖。

### BD05 · 迁移与契约一致性收口（R04、R02）
- 覆盖需求：R04、R02
- 设计说明：
  - **无新迁移的论证与检查**：AppExtension 新字段全部派生自既有列（`mount`/`target`/`http_target_method`，`saleor/app/models.py`），manifest 级字段派生自 manifest dict；依赖调整不涉及模型字段。交付前执行 `python manage.py makemigrations --check --dry-run`（应输出 "No changes detected"）与 `python manage.py migrate`（本地库成功），证明无遗漏模型变更且既有迁移链完整（含 `0031`/`0032` 等 3.22 历史，不改写）。
  - **契约一致性**：`python manage.py get_graphql_schema` 导出与仓库内 `saleor/graphql/schema.graphql` diff 为空（AC-02-1）；与交付物 `target-schema.graphql` diff 为空；与 `saleor-dashboard/schema.graphql` 期望一致（已预验证逐字符相同）。
  - **JSON 标量位置**：graphene print_schema 按"被引用即打印"规则，`settings: JSON!` 使 `scalar JSON` 打印顺序可能与基线文件不同（本设计目标 SDL 中位于 `AppExtensionTargetEnum` 之后）；以再生成输出为准，不做手工排版（AC-02-1 允许评审接受的注释级差异，此处为确定性生成结果）。

## 4. 接口清单

| 接口 | 所属设计单元 | 说明 |
| --- | --- | --- |
| I01 | BD02 | AppExtension/AppManifestExtension 新增 mountName/targetName/settings 并废弃旧字段 |
| I02 | BD03 | 批量请求 mutation 数量上限（HTTP 400 契约，无 SDL 变化） |
| I03 | BD01 | shop.version/schemaVersion 输出 3.23.0/3.23 |

权威契约集中定义于 `interface-contract.md`；完整目标 SDL 见 `target-schema.graphql`。

## 5. 工程任务与依赖

### BT01 · 版本与描述常量升级
- 覆盖设计单元：BD01
- 依赖：无
- 工作与验证：改 `saleor/__init__.py` `__version__`、`pyproject.toml` version、`descriptions.py` 追加 `ADDED_IN_323`、`CHANGELOG.md` 加 3.23.0 段。验证：`python -c "import saleor; print(saleor.__version__, saleor.schema_version)"` 输出 `3.23.0 3.23`；CHANGELOG 历史段 diff 为零。

### BT02 · AppExtension 契约实现
- 覆盖设计单元：BD02
- 依赖：BT01（`ADDED_IN_322` 已存在可直接用；若引用 `ADDED_IN_323` 需 BT01 先行——本设计新字段沿用既有 3.22 描述，故实际无强依赖，仅逻辑上先做 BT01 保持提交粒度清晰）
- 工作与验证：改 `saleor/graphql/app/types.py`（两类型三字段 + 六处 deprecation_reason + `settings` 解析器），跑 `python manage.py get_graphql_schema` 再生成 `schema.graphql`。验证：导出与 `target-schema.graphql` 无 diff；`pytest saleor/graphql/app/tests/queries/ -m 'not e2e'` 全绿（既有 mount/target/options 用例不回归）；用 dashboard `ExtensionList` 查询文档对本地下发，返回 `mountName/targetName/settings`。

### BT03 · mutation 数量上限实现
- 覆盖设计单元：BD03
- 依赖：无（与 BT02 并行）
- 工作与验证：新建 `saleor/graphql/core/validators/mutation_count.py`，`settings.py` 加 `GRAPHQL_MUTATION_COUNT_LIMIT`（默认 0），`views.py` 接线。验证：`GRAPHQL_MUTATION_COUNT_LIMIT=4 uvicorn saleor.asgi:application` 下 5 根字段 mutation → HTTP 400 + `GRAPHQL_MUTATION_COUNT_LIMIT_EXCEEDED`，4 根字段 → 200；不设变量时 `pytest saleor/graphql/tests -m 'not e2e'` 与基线一致。

### BT04 · 依赖声明与代码适配
- 覆盖设计单元：BD04
- 依赖：BT01（version 行同文件）
- 工作与验证：编辑 `pyproject.toml` 依赖块；落定 `uv.lock`（离线重解析或采用目标 lock）；删 `import pillow_avif` 与 `HTMLSafeJSON`。验证：`uv lock --check` 0；`python -c "import saleor"`（在 uv 环境内）成功；`pytest saleor/payment/gateways/np_atobarai/tests -m 'not e2e'` 与 `pytest saleor/product/tests -m 'not e2e'`（覆盖 JSON 序列化与 posuto 路径）全绿。

### BT05 · 迁移检查与端到端复验
- 覆盖设计单元：BD05
- 依赖：BT02、BT03、BT04
- 工作与验证：`makemigrations --check --dry-run`（No changes detected）；`migrate` 成功；`/opt/runtime/run-suite.sh <attempt> core-smoke core-unit core-e2e` 全绿；核对仓库 diff 无评估资产路径改动（R09）。

## 6. 其他
- 运行约束：本地验证一律走 `/opt/runtime/run-suite.sh`；suite 依赖数据库/valkey/mailpit 等服务，健康检查通过不等于测试成功。pytest 进程不注入 `GRAPHQL_MUTATION_COUNT_LIMIT`（`services.sh` 注释明示），BD03 的默认关闭设计保证这一点由运行时而非测试代码承担。
- 风险：`uv lock --offline` 若因本地缓存缺元数据失败，回退为采用目标 `uv.lock`（允许输入），已在 BD04 说明；两者验收判据相同（`uv lock --check`）。
- 待确认项：官方 fail-to-pass/pass-to-pass 冻结名单未发布。若冻结名单覆盖本设计之外的 3.23 特性域，按模板规则增补 BD/I/BT 编号（顺延，不重排）；本设计不预设名单内容。
- 评估资产零改动（R09）为全部 BT 的硬边界：diff 导出前逐路径核对，不含测试/fixture/verifier/scoring 路径。
