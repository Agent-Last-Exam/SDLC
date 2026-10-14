# 后端技术设计：Saleor Core 与 Dashboard 协同升级到 3.23.0（Core 部分）

版本：v1
责任：后端技术设计
依据：PRD v1，artifacts/sprint1/prd/prd.md
修订：首次交付

## 1. 方案概述

本设计只讨论 Core 仓库 `/workspace/repos/saleor`（基线为 3.22.0 + 环境补丁），目标是升级到 3.23.0，并与 Dashboard 的 3.23 消费保持一致。改动分六类：

1. **版本与依赖**：把 `saleor/__init__.py`、`pyproject.toml`、`uv.lock`、`package.json` 切换到 3.23.0 目标清单。这会移除 `pillow-avif-plugin`、`draftjs-sanitizer`、`html-to-draftjs`、`adyen`、`posuto` 五个包，因此需要逐一替换它们在生产代码中的用途：AVIF、HTML 安全 JSON、两条历史迁移、Adyen/NP Atobarai 插件。同时要给新声明的 `nh3`、`orjson`、`idna`、`kombu` 找到真实的生产用途（对应 PRD Q3）。
2. **GraphQL 接口**：
   - `AppManifestExtension`/`AppExtension` 新增 `mountName`、`targetName`、`settings` 三个字段，并给旧字段标注 deprecated。
   - 重新生成 `saleor/graphql/schema.graphql`，生成结果与 `target-schema.graphql` 一致，也与 Dashboard 主 schema 一致。
3. **API 安全**：新增 `GRAPHQL_MUTATION_COUNT_LIMIT` 根 mutation 数量校验。接入方式与现有 query cost 校验相同，在 `saleor/graphql/views.py` 的执行前阶段完成。
4. **客户搜索**：
   - `User` 新增 `search_vector`（PostgreSQL `tsvector` + GIN 索引），写入点与现有 `search_document` 同步。
   - `search_users` 先用 `search_vector` 全文检索，再用原有 `search_document` 子串匹配兜底，保证不出现搜索倒退。
   - 存量数据由 post_migrate 触发的 celery 任务分批回填。
5. **迁移与回归**：迁移链完整，`makemigrations --check` 保持干净，现有测试不受影响。
6. **发布说明**：`CHANGELOG.md` 新增 3.23.0 小节。

主要修改位置如下：

- `saleor/__init__.py`
- `saleor/settings.py`（`GRAPHQL_QUERY_MAX_COMPLEXITY` 附近、`BUILTIN_PLUGINS`、celery broker 配置）
- `saleor/core/utils/json_serializer.py`
- `saleor/product/migrations/0096_raw_html_to_json.py`、`saleor/page/migrations/0008_raw_html_to_json.py`
- `saleor/payment/gateways/{adyen,np_atobarai}/`（删除）
- `saleor/graphql/app/types.py`、`saleor/graphql/core/descriptions.py`
- `saleor/graphql/core/validators/`（新增 `mutation_count.py`）、`saleor/graphql/views.py`
- `saleor/account/{models.py,search.py,migrations/}`，以及所有写 `search_document` 的位置
- `saleor/webhook/transport/synchronous/transport.py`、`saleor/plugins/openid_connect/utils.py`、`saleor/celeryconf.py`
- `CHANGELOG.md`

## 2. 需求覆盖

本轮包含接口变更，目标 SDL `target-schema.graphql` 为必交项，已交付。R10–R16 属于 Dashboard 内部工程，后端没有对应设计单元。其中 R11、R16 只消费现有 Core 接口，Core 不需要改动；R08、R09 的 Dashboard 侧由前端设计承接。

| 需求 | 设计单元 |
| --- | --- |
| R01 | BD01 |
| R02 | BD02、BD03、BD04、BD05 |
| R03 | BD03 |
| R04 | BD04 |
| R05 | BD05 |
| R06 | BD06、BD07 |
| R07 | BD07 |
| R08 | BD08 |
| R09 | BD09 |
| R17 | BD04、BD09、BD10 |
| R18 | BD10 |
| R19 | BD11 |

## 3. 详细设计

### BD01 · 版本号、schema 版本与 3.23 描述常量
- 覆盖需求：R01
- 设计说明：
  - `saleor/__init__.py` 设置 `__version__ = "3.23.0"`。`schema_version` 的计算逻辑保持不变，即按 `__version__` 切出 `major.minor`，得到 `"3.23"`。`shop.version` 与 `shop.schemaVersion` 自动返回新值（I05）。
  - `saleor/graphql/core/descriptions.py` 在 `ADDED_IN_322` 之后新增 `ADDED_IN_323 = "\n\nAdded in Saleor 3.23."`，写法与已有常量一致。
  - `pyproject.toml`、根目录 `package.json` 的 `version` 改为 `3.23.0`，与 BD02 一并完成。
  - 验证：
    - `python -c "import saleor; print(saleor.__version__, saleor.schema_version)"` 输出 `3.23.0 3.23`。
    - 现有 `saleor/graphql/shop/tests` 中的版本相关用例继续通过。

### BD02 · 依赖声明对齐目标清单，新依赖的生产用途
- 覆盖需求：R02
- 设计说明：
  - **清单**：用 `/opt/environment/dependencies/target/saleor/{pyproject.toml,uv.lock}` 覆盖仓库中的同名文件。`package.json` 中只改 `version`。不联网，不执行 `uv lock`；目标包已经预装在环境中。目标 `pyproject.toml` 自带 deptry 配置：排除 `tests`、`conftest`，DEP002 忽略 azure-*、`django-redis`、`psycopg`、`pyxb`。
  - **移除包的替换**：
    - `pillow_avif` 见 BD03。
    - `draftjs_sanitizer` 与 `html_to_draftjs` 见 BD04。
    - `Adyen` 与 `posuto` 见 BD05。
  - **新依赖的生产用途**（对应 PRD Q3。每个依赖都承担实际功能，不写空导入）：
    - `orjson`：同步 webhook 的响应解析，即 `saleor/webhook/transport/synchronous/transport.py` 中 `json.loads(response.content)` 一处，改为 `orjson.loads(response.content)`。
      - `orjson.JSONDecodeError` 是 `json.JSONDecodeError` 的子类，现有 `except JSONDecodeError` 分支不需要改。
      - orjson 可以直接解析 `bytes`，大整数精度也不会丢失。
      - observability 的 `dump_payload` 依赖 `ensure_ascii` 的字节计数语义，这里不改。
    - `idna`：用于 OpenID Connect 的员工邮箱域名匹配。在 `saleor/plugins/openid_connect/utils.py` 中，`get_domain_from_email` 和 `get_staff_user_domains` 统一把域名规范化为 `idna.encode(domain, uts46=True).decode("ascii")`；出现 `idna.IDNAError` 时回退为 `domain.lower()`。这样国际化域名的 Unicode 写法与 punycode 写法都能匹配，纯 ASCII 域名的结果与现状相同，现有测试断言不受影响。
    - `kombu`：在 `saleor/settings.py` 中用 `kombu.utils.url.url_to_parts(CELERY_BROKER_URL)` 解析 broker 地址。
      - 当 scheme 为 `sqs` 时，设置 `CELERY_BROKER_TRANSPORT_OPTIONS`，其中 `region` 与 `visibility_timeout` 取自环境变量 `CELERY_SQS_REGION`、`CELERY_SQS_VISIBILITY_TIMEOUT`，未设置时使用 kombu 默认值。
      - 启动日志中输出的 broker 地址用 `kombu.utils.url.maybe_sanitize_url` 脱敏。
      - 非 sqs 部署的行为不变。
    - `nh3`：用作 BD04 中两条历史迁移的 HTML→DraftJS 转换器和 sanitizer 实现（`nh3.clean`）。
  - **验证**：
    - 在仓库根目录离线运行 `deptry .`，应输出 "No dependency issues found"。
    - 在生产代码（排除 `tests/`）中检索 `import Adyen|draftjs_sanitizer|html_to_draftjs|pillow_avif|posuto`，结果应为空。
    - `uv.lock` 中不含被移除的包，含 `nh3`、`orjson`。
    - 运行 webhook transport 与 openid_connect 的现有单测。

### BD03 · 去掉 pillow-avif-plugin 后的 AVIF 能力
- 覆盖需求：R03
- 设计说明：
  - 删除 `saleor/__init__.py` 第 1 行的 `import pillow_avif`。环境中的 Pillow 已在补丁中升级，原生支持 AVIF 编解码（`PIL.features.check("avif")` 为真），缩略图生成（`saleor/thumbnail/utils.py`）和上传 MIME 校验不需要改代码。
  - 如果 `saleor/thumbnail` 或 `saleor/core/utils` 中有任何依赖插件副作用的注册代码，一并删除。实现时检索确认。
  - 验证：
    - `import saleor`、`python manage.py check` 成功。
    - 运行 `saleor/thumbnail/tests` 中 AVIF 相关用例，以及 `ProductMediaCreate` 上传 `image/avif` 的用例。

### BD04 · HTMLSafeJSON 本地实现与历史迁移去依赖
- 覆盖需求：R04、R17
- 设计说明：
  - **HTMLSafeJSON**：在 `saleor/core/utils/json_serializer.py` 中改为 `class HTMLSafeJSON(DjangoJSONEncoder)`，类名和用途不变，删除对 `draftjs_sanitizer.SafeJSONEncoder` 的导入。
    - 模块级常量 `HTML_UNSAFE_CHARS = re.compile(r'[\x00-\x1f\\"\b\f\n\r\t<>\'&]')`。
    - 重写 `encode`：遇到 `str` 时直接返回安全字符串。
    - 重写 `iterencode`：沿用 `json.encoder._make_iterencode`，把 `encoder` 设为本类的安全字符串函数，并保留 `check_circular`、`allow_nan`、`default`、`indent`、`separators`、`sort_keys` 等语义。
    - 安全字符串规则：`\b \f \n \r \t \" \\` 使用标准短转义；其余匹配字符（`< > ' &` 和控制字符）一律输出为 `\uXXXX`。
    - 与旧实现相比，新增了对 `&` 的转义（AC-04-1 的要求）。JSON 解析后的值不变。
    - `Decimal`/`datetime`/`UUID` 仍由 `DjangoJSONEncoder.default` 处理，值的表示与 3.22 相同。
  - **历史迁移**：涉及 `product/0096_raw_html_to_json.py` 与 `page/0008_raw_html_to_json.py`。两条迁移都删除对第三方包的导入，改为在迁移文件内定义本地函数：
    - `clean_draft_js(content)`：返回去除危险 HTML 后的 DraftJS 结构。只对 block 的 `text` 执行 `nh3.clean(text, tags=set())`，结构保持原样；输入为空或非 dict 时原样返回。
    - `html_to_draftjs(html)`：先用 `nh3.clean(html, tags={"p","br","div","li","h1",…})` 规范化，再按块级标签和换行拆成段落。每段文本做 `nh3.clean(..., tags=set())` 去除标签并反转义实体，最后生成 `{"blocks":[{"key":<5位随机>,"text":…,"type":"unstyled","depth":0,"inlineStyleRanges":[],"entityRanges":[],"data":{}}],"entityMap":{}}`。空 HTML 生成单个空块。
    - `AlterField(..., sanitizer=clean_draft_js)` 改为引用本地函数。后续迁移已经替换这些字段，最终模型状态不受影响。sanitizer 只是 `SanitizedJSONField` 的 deconstruct 参数，所以 `makemigrations --check` 仍为 "No changes detected"。
  - **兼容**：这两条迁移是 2019 年的数据迁移，3.22 存量库早已执行过，不会重新执行。新空库执行时没有数据，转换函数实际上不会处理行数据，但模块必须能正常导入并运行。
  - **验证**：
    - 空库 `migrate` 成功。
    - `makemigrations --check --dry-run` 无变化。
    - 新增的 HTMLSafeJSON 行为由现有 `saleor/core/tests` 覆盖；另外在 scratch 中做 dumps/loads 往返检查。

### BD05 · 移除 Adyen 与 NP Atobarai 内置支付插件
- 覆盖需求：R05、R02
- 设计说明：
  - 从 `saleor/settings.py` 的 `BUILTIN_PLUGINS` 中删除 `saleor.payment.gateways.adyen.plugin.AdyenGatewayPlugin`（约第 861 行）和 `saleor.payment.gateways.np_atobarai.plugin.NPAtobaraiGatewayPlugin`（约第 863 行）。
  - 删除整个 `saleor/payment/gateways/adyen/` 与 `saleor/payment/gateways/np_atobarai/` 目录，包括目录内的测试。
  - 已检索确认：在两个目录之外，只有 `settings.py` 引用了这两个包（`grep -rn "gateways.adyen\|gateways.np_atobarai\|import Adyen\|posuto" saleor`），不存在其他模块依赖。
  - 保留以下内容，不做删除：
    - `Payment`/`TransactionItem` 上的 legacy Adyen 字段和已有迁移（例如 payment `0056`）
    - `Payment.gateway` 字段中存储的 `mirumee.payments.adyen` 字符串
    - `PluginConfiguration` 表中残留的 adyen/np-atobarai 行
  - 运行时行为：
    - `PluginsManager` 只实例化 `settings.PLUGINS` 中的类，残留配置行不会被加载，`plugins(...)` 查询结果中自然不包含它们（I07）。
    - 订单的 `payments { gateway }` 原样返回存储值。
    - 结算流程只涉及当前启用的插件，与 3.22 一致。
  - 不做数据迁移来删除残留的 `PluginConfiguration` 行，以避免不可逆的数据删除。
  - 验证：
    - 屏蔽 `Adyen`、`posuto` 后，`manage.py check` 成功。
    - 运行 plugin 列表查询、checkoutComplete、订单 payments 相关的现有测试。
    - 在 scratch 中构造一条残留的 `PluginConfiguration` 行，然后执行 `plugins(first:100)`。

### BD06 · App 扩展 `mountName`、`targetName`、`settings` 字段
- 覆盖需求：R06
- 设计说明：
  - **类型定义**（`saleor/graphql/app/types.py`）：
    - 在 `AppManifestExtension(BaseObjectType)` 上新增：
      - `mount_name = graphene.String(required=True, description="Name of the extension mount point in the dashboard. Replaces `mount`" + ADDED_IN_322)`
      - `target_name = graphene.String(required=True, description="Name of the extension target in the dashboard. Replaces `target`" + ADDED_IN_322)`
      - `settings = JSON(required=True, description="JSON object with settings for this extension." + ADDED_IN_322)`
      - `JSON` 标量复用 `saleor.graphql.core.scalars.JSON`，与 SDL 的 `scalar JSON` 对应。
    - `AppExtension` 继承以上三个字段，但 `settings` 需要覆盖定义，描述为 "App extension settings. Replaces `options` field." + ADDED_IN_322。
    - 给 `mount`、`target` 设置 `deprecation_reason="Use \`mountName\` instead."` 与 `"Use \`targetName\` instead."`。
    - 给 `AppExtension.options` 设置 `deprecation_reason="Use \`settings\` field instead."`。
    - 给 `AppExtensionOptionsWidget.widget_target`、`WidgetTargetOptions.method`、`AppExtensionOptionsNewTab.new_tab_target`、`NewTabTargetOptions.method` 设置 `deprecation_reason="Use \`settings\` field directly."`。
    - 描述文本和 deprecated 原因与 `target-schema.graphql` 逐字一致。描述中的 "Added in Saleor 3.22." 沿用 Dashboard 已有 schema 的写法，以保证 R07 的两端一致。
  - **解析规则**：
    - `AppManifestExtension`（root 是 manifest 清洗后的 dict）：
      - `resolve_mount_name`：`root["mount"]` 的值转大写，例如 `product_overview_create` → `PRODUCT_OVERVIEW_CREATE`，等同于 `AppExtensionMountEnum` 的枚举名。
      - `resolve_target_name`：`(root.get("target") or AppExtensionTarget.POPUP)` 转大写。
      - `resolve_settings`：读取 `root.get("options") or {}`，把 snake_case 键转成 camelCase（`new_tab_target` → `newTabTarget`，`widget_target` → `widgetTarget`），值中的 `method` 保持 `GET`/`POST`。没有 options 时返回 `{}`。
    - `AppExtension`（root 是 `models.AppExtension`）：
      - `resolve_mount_name`：`root.mount.upper()`。
      - `resolve_target_name`：`root.target.upper()`。
      - `resolve_settings`：
        - `target == NEW_TAB` 且 `http_target_method` 非空时，返回 `{"newTabTarget": {"method": m}}`。
        - `target == WIDGET` 且 `http_target_method` 非空时，返回 `{"widgetTarget": {"method": m}}`。
        - 其余情况返回 `{}`。
      - 旧的 `resolve_options` 保持原样。
  - **一致性**：Dashboard 的 zod 校验（`src/extensions` 中的扩展配置 schema）要求键名为 camelCase、`method` 为 `GET|POST`。以上输出满足这一要求，因此不会出现 "Invalid extension configuration"。
  - **权限**：新增字段继承所在类型的可见性，不另外设置权限（I01/I02）。
  - **验证**：
    - 运行 `saleor/graphql/app/tests` 中现有的 appExtensions、appFetchManifest、appExtension 查询测试。
    - 在 scratch 中按 AC-06-1/2/3 的数据构造查询。

### BD07 · 重新生成 Core GraphQL schema
- 覆盖需求：R06、R07
- 设计说明：
  - BD06 完成后，执行 `python manage.py get_graphql_schema > saleor/graphql/schema.graphql` 重新生成 schema。
  - 预期结果与 `artifacts/sprint1/tech-design/target-schema.graphql` 一致，类型的排列顺序以打印器为准。
  - 与 Base 相比的变化只有以下几项：
    - `AppExtension`/`AppManifestExtension` 各新增 3 个字段（共 6 个 FIELD_ADDED）。
    - 9 处字段新增 deprecated 标注。
    - `scalar JSON` 的位置变化。
  - 不应出现 breaking change 或 dangerous change。
  - 验证：
    - 用 `graphql` 的 `buildSchema` 加载生成文件，再执行 `findBreakingChanges(base, new)`，结果应为空。
    - 与 Dashboard 主 schema（`schema-main.graphql`）双向比较，两边既无 breaking change，也没有单向新增。
    - Core 内 `saleor/graphql/tests` 中的 schema 快照或打印测试（若有）同步更新。注意：生成的 schema 是生产产物，不属于测试文件。

### BD08 · 根 mutation 数量上限 `GRAPHQL_MUTATION_COUNT_LIMIT`
- 覆盖需求：R08
- 设计说明：
  - **设置**：`saleor/settings.py` 在 `GRAPHQL_QUERY_MAX_COMPLEXITY` 之后新增以下内容，并加注释说明 `0` 表示关闭：
    ```python
    # Maximum number of root mutation fields in a single operation.
    # Set GRAPHQL_MUTATION_COUNT_LIMIT=0 in env to disable.
    GRAPHQL_MUTATION_COUNT_LIMIT = int(os.environ.get("GRAPHQL_MUTATION_COUNT_LIMIT", 3))
    ```
    - 默认值 `3` 是本设计的假设（PRD Q4，待确认）。依据如下：
      - 运行时脚本特意把 API 进程的限值设为 4，并注明 "Dashboard VariantUpdate sends four root mutations"，说明上游默认值小于 4。
      - Core 测试中单个请求最多包含 2 个根 mutation，默认值不能低于 2。
      - Dashboard 中除 `VariantUpdate`（4）外，最大的是 `MenuUpdate`（3）。
      - 取 3 时，现有测试全部可用，部署时只需为 Dashboard 放宽到 4。
    - 运行时通过环境变量设为 4。
    - 如果官方测试要求其他默认值，只需要改这一处常量。
  - **校验器**：新增 `saleor/graphql/core/validators/mutation_count.py`：
    - `class MutationCountLimitError(GraphQLError)`。
    - `def validate_mutation_count(document: GraphQLDocument, operation_name: str | None, limit: int) -> tuple[int, list[GraphQLError]]`，处理步骤如下：
      1. 从 `document.document_ast` 中找出本次实际执行的操作：
         - 按 `operation_name` 匹配。
         - 未给 `operation_name` 且只有一个操作时，取该操作。
         - 找不到操作时返回 `(0, [])`，交给执行器报原有错误。
      2. 操作类型不是 `mutation` 时返回 `(0, [])`。
      3. 递归展开根选择集，统计 `Field` 节点数：
         - `FragmentSpread` 根据文档中的 `FragmentDefinition` 展开。
         - `InlineFragment` 直接展开。
         - 每个 `Field`（包括带不同 alias 的同名字段）计 1 次。
         - `__typename` 不计数。
         - 已访问过的片段名不再重复展开，防止循环。
      4. 当 `limit > 0 and count > limit` 时，返回一个 `MutationCountLimitError`：
         - 消息为 `f"Number of root mutations ({count}) exceeds the limit of {limit}."`
         - `extensions={"mutationCount": {"requested": count, "maximumAvailable": limit}}`
  - **接入**（`saleor/graphql/views.py` 的 `execute_graphql_request`）：在 query cost 校验分支之后、构造 `extra_options` 和执行之前，调用 `validate_mutation_count(document, operation_name, settings.GRAPHQL_MUTATION_COUNT_LIMIT)`。有错误时的处理方式与 cost 分支相同：
    - 返回 `ExecutionResult(errors=errors, invalid=True)`。`invalid` 结果的 HTTP 状态码为 400，响应中不含 `data`。
    - `span.set_status(StatusCode.ERROR, ...)`。
    - `record_graphql_query_count(..., error_type="MutationCountLimitError")`，并在 `query_duration_attrs` 中写入 `error.type`。
    - 结果同样经过 `set_query_cost_on_result`，与 cost 分支保持一致。
    - 校验失败的请求不执行任何 resolver，也不写数据库。
    - 错误经 `format_error` 输出时，`extensions.exception.code` 为 `"MutationCountLimitError"`（I04）。
    - `MutationCountLimitError` 继承自 `GraphQLError`，已被 `saleor/graphql/utils/__init__.py` 的 `ALLOWED_ERRORS` 覆盖，因此非 DEBUG 模式下也会返回原始消息。为了显式表达，与 `QueryCostError` 并列登记到 `ALLOWED_ERRORS`；同时把它加入视图的 `HANDLED_EXCEPTIONS`，只记 debug 日志，不当作未处理错误上报。
  - **范围**：
    - 只统计实际执行的操作；query 与 subscription 直接放行。
    - 批量请求（列表形式的 body）中每个操作单独校验。
    - 内部 webhook 订阅载荷的生成走的不是该视图入口，不受影响。
  - **验证**：
    - 新增的单元用例在 PR 中与校验器一同提交，覆盖：alias 计数、片段展开、query 放行、limit=0 关闭、超限时数据库无变化、HTTP 400。这些是新增测试，不改动已有测试。
    - 用 AC-08-1~4 的请求做手工或 scratch 验证。
    - 在默认值下运行现有 Core 测试，确认通过。

### BD09 · 用户 `search_vector` 全文检索
- 覆盖需求：R09、R17
- 设计说明：
  - **模型**（`saleor/account/models.py` 的 `User`）：
    - 新增 `search_vector = SearchVectorField(blank=True, null=True)`。
    - 在 `Meta.indexes` 中新增 `GinIndex(name="user_search_vector_idx", fields=["search_vector"])`，与 product/order 现有写法一致。
    - 保留 `search_document`（PRD Q5，默认保留）。
  - **迁移**：
    - `account/migrations/0096_user_search_vector.py`：执行 `AddField`。字段可空，不会重写表。
    - `account/migrations/0097_user_search_vector_idx.py`：设置 `atomic = False`，使用 `AddIndexConcurrently` 创建 GIN 索引，写法参考 `0093` 等既有的并发索引迁移。
    - 回填由 0097 迁移注册的 `post_migrate` 信号触发，执行 celery 任务 `populate_user_search_vector_task`。
      - 任务放在新文件 `saleor/account/migrations/tasks/saleor3_23.py` 中。
      - 在 `saleor/celeryconf.py` 中为 `saleor.account.migrations.tasks` 新增 `related_name="saleor3_23"` 的 autodiscover，与现有 `saleor3_22` 并列。
    - 任务的执行方式：
      - 每批 500 条，按 `search_vector__isnull=True` 和 pk 顺序取数。
      - 预取 `addresses` 和 `default_billing_address`/`default_shipping_address`。
      - 调用 `set_search_vector_values(...)` 计算并 `bulk_update(["search_vector"])`。
      - 还有剩余数据时，`apply_async` 递归调度下一批。
      - 任务幂等：已有值的用户不会被重复计算。
  - **计算与写入**（`saleor/account/search.py`）：
    - `prepare_user_search_vector_value(user, *, already_prefetched=False) -> list[NoValidationSearchVector]`：
      - 权重 A：email、first_name、last_name。
      - 权重 B：默认地址与所有地址的 `generate_address_search_vector_value(...)`（该函数已存在），覆盖姓名、公司、街道、城市、邮编、国家、电话。
      - 统一使用 `config="simple"`。
    - `update_user_search_vector(user, *, save=True)`：
      - 设置 `user.search_vector = FlatConcatSearchVector(*prepare_user_search_vector_value(user))`。
      - `save=True` 时执行 `user.save(update_fields=["search_vector", "updated_at"])`。
      - 这个签名供 E2E 播种脚本以 `update_user_search_vector(user)` 形式调用。
    - 写入点：凡是更新 `search_document` 的位置，都同步调用 `update_user_search_vector(user, save=False)`，并把 `"search_vector"` 加入对应的 `update_fields` 或 `bulk_update` 字段列表。已知位置如下：
      - `saleor/account/tasks.py`
      - `graphql/account/mutations/base.py`（两处）
      - `staff/customer_create.py`、`staff/customer_update.py`、`staff/staff_create.py`、`staff/address_create.py`
      - `account/account_address_create.py`、`account/confirm_email_change.py`
      - `bulk_mutations/customer_bulk_update.py`
      - `plugins/openid_connect/utils.py`
      - `core/utils/random_data.py`
      - 实现时用 `grep -rn "prepare_user_search_document_value"` 补全。
    - 现有维护命令 `update_search_indexes`（以及 `set_user_search_document_values` 任务）扩展为同时补齐 `search_vector`。
  - **查询**：`search_users(qs, value)` 改为：
    ```python
    if value:
        lookup = Q()
        for val in value.split():
            lookup &= Q(search_document__ilike=val.lower())
        vector_lookup = Q(search_vector=SearchQuery(value, search_type="websearch", config="simple"))
        qs = qs.filter(vector_lookup | lookup)
    ```
    - `customers(search:)`、`staffUsers(search:)` 等使用 `search_users` 的入口自动获得新语义（I06）。
    - 用 OR 兜底，保证之前能搜到的结果（例如邮箱片段 `doe@example`）仍然能搜到。
    - 回填尚未完成的用户依靠 `search_document` 命中。
  - **验证**：
    - 运行现有的 account search 与 customers/staffUsers 搜索测试。
    - `migrate` 后检查 `\d account_user` 的列与索引。
    - 按 AC-09-2/3 的数据在 scratch 中查询。

### BD10 · 迁移链完整性与回归保障
- 覆盖需求：R17、R18
- 设计说明：
  - 新增的迁移只有 account `0096`、`0097`。product/page 的历史迁移只修改了导入，不新增迁移。删除 adyen/np_atobarai 不涉及模型（这两个插件没有自有模型），因此迁移图中没有新的叶子冲突。
  - 回归要求：
    - 不修改任何已有测试、fixtures、`/opt/runtime` 和 verifier。
    - 随 adyen/np_atobarai 目录一起删除的测试，属于被移除功能的测试，在交付说明中单独列出。
  - 验证命令（研发阶段执行）：
    - `python manage.py makemigrations --check --dry-run`
    - `python manage.py migrate --plan`
    - 空库 `migrate` 后执行 `populatedb --createsuperuser`
    - 在 3.22 样例库上 `migrate`，比较前后计数
    - `pytest --collect-only -q`，收集错误应为 0
    - `run-suite.sh <attempt> core-unit`、`core-e2e`

### BD11 · CHANGELOG 3.23.0
- 覆盖需求：R19
- 设计说明：在 `CHANGELOG.md` 的 `# 3.22.0` 之上新增 `# 3.23.0` 小节，内容如下：
  - **Breaking changes**：移除 Adyen 与 NP Atobarai 内置插件；新增 `GRAPHQL_MUTATION_COUNT_LIMIT`（默认 3），超限请求会被拒绝，使用 Dashboard 的部署需设置为至少 4；移除 `pillow-avif-plugin`、`draftjs-sanitizer`、`html-to-draftjs` 依赖。
  - **GraphQL API**：`AppExtension`/`AppManifestExtension` 新增 `mountName`、`targetName`、`settings` 字段。
  - **Deprecations**：`mount`、`target`、`options` 及选项子字段标注为 deprecated。
  - **Other changes**：客户搜索使用 `search_vector`；新增 orjson/idna/kombu SQS 的用途说明。

## 4. 接口清单

| 接口 | 所属设计单元 | 说明 |
| --- | --- | --- |
| I01 | BD06、BD07 | `AppExtension` 新增 `mountName`/`targetName`/`settings`，`mount`/`target`/`options` 标注 deprecated |
| I02 | BD06、BD07 | `AppManifestExtension` 新增 `mountName`/`targetName`/`settings`，`mount`/`target` 标注 deprecated |
| I03 | BD06、BD07 | `AppExtensionPossibleOptions` 成员类型的子字段标注 deprecated |
| I04 | BD08 | 所有 mutation 操作受 `GRAPHQL_MUTATION_COUNT_LIMIT` 约束，超限时返回顶层错误 |
| I05 | BD01 | `shop.version`/`shop.schemaVersion` 返回 3.23.0/3.23 |
| I06 | BD09 | `customers(search:)`/`staffUsers(search:)` 的搜索语义：search_vector 全文检索 + 原子串匹配 |
| I07 | BD05 | `plugins`/`plugin` 查询不再返回 Adyen、NP Atobarai |

## 5. 工程任务与依赖

### BT01 · 版本、依赖清单与描述常量
- 覆盖设计单元：BD01、BD02
- 依赖：无
- 工作与验证：
  - 替换 `pyproject.toml`、`uv.lock`，修改 `package.json` 和 `saleor/__init__.py` 中的版本，新增 `ADDED_IN_323`。
  - 验证 `import saleor` 的版本值和 `shop` 版本查询测试。

### BT02 · 移除 AVIF 插件导入
- 覆盖设计单元：BD03
- 依赖：BT01
- 工作与验证：删除导入后，运行 `manage.py check` 和 thumbnail/AVIF 测试。

### BT03 · HTMLSafeJSON 与历史迁移本地化
- 覆盖设计单元：BD04
- 依赖：BT01
- 工作与验证：
  - 修改 `json_serializer.py`、product `0096`、page `0008`。
  - 验证空库 `migrate`、`makemigrations --check`，以及 HTMLSafeJSON 的往返检查。

### BT04 · 移除 Adyen/NP Atobarai
- 覆盖设计单元：BD05
- 依赖：BT01
- 工作与验证：
  - 修改 `BUILTIN_PLUGINS`，删除两个网关目录，清理引用。
  - 验证 `manage.py check`、plugins 查询、checkout 和支付相关测试。

### BT05 · 新依赖落地（orjson/idna/kombu/nh3）
- 覆盖设计单元：BD02
- 依赖：BT01、BT03
- 工作与验证：
  - 修改 webhook transport、openid_connect 域名规范化、settings 中的 SQS broker 选项。
  - 运行相关单测，最后执行 `deptry .`，应无问题。

### BT06 · App 扩展字段与 schema 重新生成
- 覆盖设计单元：BD06、BD07
- 依赖：BT01
- 工作与验证：
  - 修改 `app/types.py`，重新生成 `schema.graphql`。
  - 与 `target-schema.graphql` 及 Dashboard 主 schema 做 diff 和 findBreakingChanges 检查。
  - 运行 app 相关测试。
  - 提前交付给前端 FD02/FD09 联调。

### BT07 · 根 mutation 数量限制
- 覆盖设计单元：BD08
- 依赖：无
- 工作与验证：
  - 新增 setting、校验器、views 接入，以及校验器的新增单测。
  - 用 AC-08-1~4 的请求验证。
  - 在默认值下运行 `saleor/graphql` 全量测试。

### BT08 · 用户 search_vector
- 覆盖设计单元：BD09
- 依赖：无
- 工作与验证：
  - 修改模型，新增迁移 0096/0097、回填任务、celery autodiscover、计算与写入点、`search_users`。
  - 验证 migrate、account 测试，以及 E2E 播种 `tier_user_search` 分支。

### BT09 · 迁移与回归总验收
- 覆盖设计单元：BD10
- 依赖：BT02、BT03、BT04、BT05、BT06、BT07、BT08
- 工作与验证：执行 BD10 中列出的全部命令；在 3.22 存量库上升级，并比较数据计数。

### BT10 · CHANGELOG
- 覆盖设计单元：BD11
- 依赖：BT04、BT06、BT07、BT08
- 工作与验证：撰写 3.23.0 小节，确认其中包含插件移除、mutation 数量限制和 App 扩展字段三项。

## 6. 其他

**目标 SDL 已执行的检查**

脚本位于 `/workspace/scratch/check.cjs`、`docs.cjs`，使用 Dashboard `node_modules` 中的 `graphql`。

- `buildSchema(target-schema.graphql)` 成功，共 1418 个类型，类型引用全部可解析。
- `findBreakingChanges(Base, Target)` 为空；`findDangerousChanges` 为 0。差异只有 6 个新增字段和 9 处新增 deprecated。
- Target 与 Dashboard 现有 `schema.graphql` 比较：除 `scalar JSON` 的位置外，内容一致。
- Dashboard codegen 覆盖的 121 个文件、640 个定义，用 Target 校验：
  - 字段错误为 0。
  - 重复片段名为 1（`PageTypeDeleteErrorFragment`），由前端 FD02 处理。
  - 根 mutation 最大值为 4（`VariantUpdate`）。
  - 用 Base 校验时有 3 个字段错误，即 `mountName`/`targetName`/`settings`。
- Core 的 Python 测试中，单个请求最多包含 2 个根 mutation。这是 BD08 默认值的依据之一。

**未执行的检查**（本阶段只做设计，研发阶段执行）：

- 用 Python 打印器生成 schema 并与 Target 比较
- pytest
- migrate/makemigrations
- deptry
- codegen、tsc
- E2E

**风险与待确认**

- Q4：`GRAPHQL_MUTATION_COUNT_LIMIT` 默认值暂定为 3。在默认值下，Dashboard 的 `VariantUpdate` 会被拒绝，部署时必须设置为 ≥4（运行时已设为 4）；这一点写入 CHANGELOG 的 Breaking changes。如果官方用例要求其他值，以官方为准，只需改一处常量。
- Q3：新依赖的用途是本设计的推断，不代表上游实现。每项都有真实的生产功能，不属于空导入。
- AC-04-1 要求转义 `&`，比旧的 `SafeJSONEncoder` 更严格。解析后的语义不变，但序列化的字符串表示会发生变化。如果有测试对字面输出做字节级比较，可能受到影响，需要在研发阶段运行 `core-unit` 确认。
- `search_users` 采用 OR 兜底以避免搜索倒退，代价是保留了 ilike 扫描的开销。等 `search_document` 退役（PRD 已将其延期）时再收敛。
- 被删除插件目录中的测试会随功能一同删除，这不违反"不修改评估测试"的约束，但需要在交付说明中列明，供维护者确认。
