# 接口对齐文档：Saleor Core 与 Dashboard 协同升级到 3.23.0

版本：v1
责任：后端技术设计
依据：后端技术设计 v1，backend-design.md
修订：首次交付

## 1. 通用约定

- **入口**：Core GraphQL API 只有一个入口，即 `POST /graphql/`，Content-Type 为 `application/json`。请求体可以是 `{"query","variables","operationName"}`，也可以是由这类对象组成的数组（批量）。完整的类型定义以同目录的 `target-schema.graphql` 为准，本文的 SDL 片段均摘自该文件。
- **认证**：
  - Staff/客户：使用 JWT access token。请求头为 `Authorization: Bearer <token>`，或使用 `Authorization-Bearer: <token>`（Dashboard 现有 fetch 使用后者）。
  - App：使用 App token，同样放在 `Authorization: Bearer` 头中。
  - 令牌的获取、刷新与吊销沿用现有的 `tokenCreate`、`tokenRefresh`、`tokenVerify`、`tokensDeactivateAll`、`external*` 和 `setPassword` 操作，本次不做改动。
- **错误分层**：
  1. **请求级错误**：语法错误、校验错误、query cost 超限、根 mutation 数量超限（I04）。
     - HTTP 状态码为 400。响应体只含顶层 `errors`，不含 `data`，也不执行任何 resolver。
     - 每个错误项包含 `message` 和 `extensions.exception.code`（即异常类名），并可能附带专用的 extensions 键。
  2. **字段级错误**：权限不足、对象不存在等。
     - HTTP 状态码为 200。`data` 中对应字段为 `null`，顶层 `errors` 带有 `path`。
     - 权限错误的 `extensions.exception.code` 为 `"PermissionDenied"`。
  3. **业务错误**：仅限 mutation。HTTP 状态码为 200，错误写在 payload 的 `errors: [XxxError!]!` 列表中，包含 `field`、`code`、`message`。
- **ID 规则**：对象 ID 使用 Relay 全局 ID，即 base64 编码的 `"<TypeName>:<pk>"`。本次没有新增需要 ID 的输入。
- **成功判定**：
  - query：HTTP 200，顶层没有 `errors`，目标字段非空。
  - mutation：HTTP 200，顶层没有 `errors`，payload 中的 `errors` 为空列表。
- **废弃策略**：被废弃的字段在 3.23 中仍然可以查询，返回值不变，只在 schema 中通过 `@deprecated(reason: ...)` 标注。新消费者应改用替代字段。

## 2. 接口契约

### I01 · AppExtension 新增 `mountName`、`targetName`、`settings`
- 所属设计单元：BD06
- 提供方：saleor/`saleor/graphql/app/types.py` 中的 `AppExtension`（修改：继承并覆盖 `AppManifestExtension` 的新字段，新增 `resolve_mount_name`、`resolve_target_name`、`resolve_settings`）
- 调用方：
  - saleor-dashboard 中的 `src/extensions/queries.ts`（`appExtensions`）、`src/extensions/hooks/useExtensions.ts`、`src/extensions/components/AppWidgets/AppWidgets.tsx`，由 FD09 调用
  - 外部 App（通过 `appExtensions`/`appExtension`/`App.extensions`）
- 目标定义：`target-schema.graphql` 中的 `type AppExtension`、`scalar JSON`，以及查询入口 `Query.appExtensions`、`Query.appExtension` 和 `App.extensions`

```graphql
type AppExtension implements Node @doc(category: "Apps") {
  id: ID!
  permissions: [Permission!]!
  label: String!
  url: String!

  """Place where given extension will be mounted."""
  mount: AppExtensionMountEnum! @deprecated(reason: "Use `mountName` instead.")

  """Type of way how app extension will be opened."""
  target: AppExtensionTargetEnum! @deprecated(reason: "Use `targetName` instead.")

  """
  Name of the extension mount point in the dashboard. Replaces `mount`
  
  Added in Saleor 3.22.
  """
  mountName: String!

  """
  Name of the extension target in the dashboard. Replaces `target`
  
  Added in Saleor 3.22.
  """
  targetName: String!

  """
  App extension settings. Replaces `options` field.
  
  Added in Saleor 3.22.
  """
  settings: JSON!

  app: App!
  accessToken: String

  """
  App extension options.
  
  Added in Saleor 3.22.
  """
  options: AppExtensionPossibleOptions @deprecated(reason: "Use `settings` field instead.")
}

scalar JSON
```

- 字段说明：
  - `mountName: String!`：非空，取值为 `AppExtensionMountEnum` 的枚举名，等于数据库中 `mount` 值的大写形式，例如 `PRODUCT_OVERVIEW_CREATE`。与 `mount` 字段返回的枚举名一致。
  - `targetName: String!`：非空，取值为 `AppExtensionTargetEnum` 的枚举名，即 `POPUP`、`APP_PAGE`、`NEW_TAB`、`WIDGET` 之一，与 `target` 一致。
  - `settings: JSON!`：非空的 JSON 对象，键名使用 camelCase：
    - `target=NEW_TAB` 且已配置 HTTP 方法时，返回 `{"newTabTarget": {"method": "GET" | "POST"}}`。
    - `target=WIDGET` 且已配置 HTTP 方法时，返回 `{"widgetTarget": {"method": "GET" | "POST"}}`。
    - 其余情况（包括 `POPUP`、`APP_PAGE` 以及未配置方法）返回空对象 `{}`，不返回 `null`。
  - 旧字段 `mount`、`target`、`options` 的返回值与 3.22 相同。
  - 示例：扩展的 `mount=product_overview_create`、`target=new_tab`、`http_target_method=POST`，则返回 `mountName="PRODUCT_OVERVIEW_CREATE"`、`targetName="NEW_TAB"`、`settings={"newTabTarget":{"method":"POST"}}`、`mount=PRODUCT_OVERVIEW_CREATE`、`target=NEW_TAB`。
- 权限：
  - 与 `AppExtension` 类型现有的可见性一致，新字段不额外设置权限。
  - `appExtensions` 要求 `AUTHENTICATED_STAFF_USER` 或 `AUTHENTICATED_APP`。
  - 作为 App 访问时，只返回该 App 自己的扩展。
- 错误：
  - 未认证访问 `appExtensions`：字段级 `PermissionDenied`。
  - 新字段在解析时不会产生业务错误。
  - 在旧版 schema（3.22 Base）上查询这些字段会得到请求级校验错误，例如 `Cannot query field "mountName" on type "AppExtension"`。因此 Dashboard 必须与 3.23 Core 配套部署。
- 完成判定：纯读取接口，没有持久化或异步行为。返回值由 `models.AppExtension` 的 `mount`、`target`、`http_target_method` 实时计算，App 安装或更新后立即可见。
- 变更与兼容：
  - 与 Base 相比新增 3 个字段，属于非破坏性变更；`mount`、`target`、`options` 增加 `@deprecated` 标注。
  - 旧消费者可以继续使用旧字段。新消费者应读取 `mountName`、`targetName`、`settings`。

### I02 · AppManifestExtension 新增 `mountName`、`targetName`、`settings`
- 所属设计单元：BD06
- 提供方：saleor/`saleor/graphql/app/types.py` 中的 `AppManifestExtension`（修改：新增字段与 resolver）
- 调用方：
  - saleor-dashboard 通过 `src/fragments/apps.ts` 中的 manifest 片段，经 `appFetchManifest` 使用。本次 Dashboard 的片段继续读取 `mount`、`target`，不读取新字段（FD09 已确认）。
  - 外部 App 安装工具，通过 `appFetchManifest` 使用
- 目标定义：`target-schema.graphql` 中的 `type AppManifestExtension`、`Manifest.extensions`，以及 `Mutation.appFetchManifest`

```graphql
type AppManifestExtension @doc(category: "Apps") {
  permissions: [Permission!]!
  label: String!
  url: String!

  """Place where given extension will be mounted."""
  mount: AppExtensionMountEnum! @deprecated(reason: "Use `mountName` instead.")

  """Type of way how app extension will be opened."""
  target: AppExtensionTargetEnum! @deprecated(reason: "Use `targetName` instead.")

  """
  Name of the extension mount point in the dashboard. Replaces `mount`
  
  Added in Saleor 3.22.
  """
  mountName: String!

  """
  Name of the extension target in the dashboard. Replaces `target`
  
  Added in Saleor 3.22.
  """
  targetName: String!

  """
  JSON object with settings for this extension.
  
  Added in Saleor 3.22.
  """
  settings: JSON!
}
```

- 字段说明：
  - `mountName`：manifest 中 `mount` 的大写形式。
  - `targetName`：manifest 中 `target` 的大写形式；manifest 未声明 target 时为 `"POPUP"`，与 `target` 的默认值规则一致。
  - `settings`：取 manifest 中扩展 `options` 清洗后的结果，键名转为 camelCase，例如 `{"newTabTarget":{"method":"POST"}}`、`{"widgetTarget":{"method":"GET"}}`；未声明时返回 `{}`。
  - `Manifest.extensions` 列表本身为非空列表 `[AppManifestExtension!]!`，列表项同样非空。
- 权限：沿用 `appFetchManifest` 的要求，即 `MANAGE_APPS`。
- 错误：manifest 格式错误或拉取失败的错误形式不变，仍为 `appFetchManifest.errors`（`AppError`）。新字段不新增错误。
- 完成判定：`appFetchManifest` 只校验和解析 manifest，不做持久化。返回的 `manifest.extensions[*]` 中每一项都可以查询这三个字段，值与 manifest 声明一致。
- 变更与兼容：新增字段为非破坏性变更。`mount`、`target` 增加 deprecated 标注，旧消费者不受影响。

### I03 · AppExtensionPossibleOptions 成员字段标注 deprecated
- 所属设计单元：BD06
- 提供方：saleor/`saleor/graphql/app/types.py` 中的 `AppExtensionOptionsWidget`、`WidgetTargetOptions`、`AppExtensionOptionsNewTab`、`NewTabTargetOptions`（修改：添加 `deprecation_reason`）
- 调用方：外部 App（读取 `AppExtension.options`）。Dashboard 已改为读取 `settings`，不调用这些字段。
- 目标定义：`target-schema.graphql` 中的 `union AppExtensionPossibleOptions` 及其成员类型

```graphql
union AppExtensionPossibleOptions = AppExtensionOptionsWidget | AppExtensionOptionsNewTab

type AppExtensionOptionsWidget @doc(category: "Apps") {
  widgetTarget: WidgetTargetOptions @deprecated(reason: "Use `settings` field directly.")
}

type WidgetTargetOptions @doc(category: "Apps") {
  method: HttpMethod! @deprecated(reason: "Use `settings` field directly.")
}

type AppExtensionOptionsNewTab @doc(category: "Apps") {
  newTabTarget: NewTabTargetOptions @deprecated(reason: "Use `settings` field directly.")
}

type NewTabTargetOptions @doc(category: "Apps") {
  method: HttpMethod! @deprecated(reason: "Use `settings` field directly.")
}
```

- 字段说明：字段类型和可空性不变，返回值与 3.22 相同。
- 权限：与 `AppExtension.options` 相同。
- 错误：无变化。
- 完成判定：生成的 Core schema 中，这 4 个字段都带有上述 `@deprecated`，原因文本逐字一致。
- 变更与兼容：只增加 deprecated 标注，不影响任何已有查询。

### I04 · 根 mutation 数量上限（`GRAPHQL_MUTATION_COUNT_LIMIT`）
- 所属设计单元：BD08
- 提供方：
  - saleor/`saleor/graphql/core/validators/mutation_count.py`（拟新增：`validate_mutation_count`、`MutationCountLimitError`）
  - saleor/`saleor/graphql/views.py` 中的 `GraphQLView.execute_graphql_request`（修改：接入校验）
  - saleor/`saleor/settings.py` 中的 `GRAPHQL_MUTATION_COUNT_LIMIT`（拟新增）
- 调用方：
  - saleor-dashboard 中所有 mutation 文档（`src/**/mutations.ts`），由 FD10 保证每个文档不超过 4 个根 mutation
  - 外部 API 消费者
- 目标定义：适用于 `target-schema.graphql` 中 `type Mutation` 下的全部根字段。这是请求校验行为，不改变 SDL。

```graphql
# 示例：在 GRAPHQL_MUTATION_COUNT_LIMIT=2 时会被拒绝（3 个根 mutation 字段）
mutation UpdateThree($a: ID!, $b: ID!, $c: ID!, $input: [MetadataInput!]!) {
  a: updateMetadata(id: $a, input: $input) { errors { field code } }
  b: updateMetadata(id: $b, input: $input) { errors { field code } }
  c: updateMetadata(id: $c, input: $input) { errors { field code } }
}
```

- 字段说明：
  - **配置**：环境变量 `GRAPHQL_MUTATION_COUNT_LIMIT`，取值为整数。
    - 未设置时默认为 `3`（假设，待 PRD Q4 确认）。
    - `0` 表示关闭限制。
    - 运行时 API 进程中设为 `4`。
  - **计数对象**：本次实际执行的那个操作。有 `operationName` 时按名称选取；文档中只有一个操作时直接取该操作。
    - 只有 `mutation` 类型的操作参与计数，`query` 与 `subscription` 不计数。
    - 计入根选择集中的每个字段节点。同一字段使用不同 alias 时各计一次。
    - 通过片段展开（`...F`）或内联片段（`... on Mutation`）到达根级的字段同样计入。
    - `__typename` 不计入。
  - **判定**：`limit > 0 且 count > limit` 时拒绝请求；`count == limit` 时放行。
  - **批量请求**：数组中的每个操作单独判定。
- 权限：与身份无关，对匿名用户、staff 和 App 同样生效。
- 错误：超限时返回请求级错误，HTTP 状态码为 400，响应体如下：

```json
{
  "errors": [
    {
      "message": "Number of root mutations (3) exceeds the limit of 2.",
      "extensions": {
        "mutationCount": { "requested": 3, "maximumAvailable": 2 },
        "exception": { "code": "MutationCountLimitError" }
      }
    }
  ],
  "extensions": { "cost": { "requestedQueryCost": 0, "maximumAvailable": 50000 } }
}
```

  - 响应中不含 `data` 键。
  - 顶层 `extensions.cost` 沿用现有的 `set_query_cost_on_result` 行为，具体数值以实际 cost 为准。
  - 消息文本中的数字为实际计数和上限。
- 完成判定：
  - 被拒绝的请求不执行任何 resolver，不写数据库，不触发 webhook 或异步任务。
  - 未超限的请求按原流程执行，结果与 3.22 一致。
  - 可观测性方面记录 `error.type="MutationCountLimitError"`，span 状态为 ERROR。
- 变更与兼容：
  - 与 Base 相比是新增的拒绝条件，SDL 不变。
  - 根 mutation 超过默认值 3 的旧消费者需要拆分请求，或由部署方调高限值。Dashboard 3.23 的最大值为 4（`VariantUpdate`），部署时必须设置为 ≥4。

### I05 · 店铺版本信息返回 3.23
- 所属设计单元：BD01
- 提供方：saleor/`saleor/__init__.py` 中的 `__version__`、`schema_version`，以及 `saleor/graphql/shop/types.py` 中的 `Shop.resolve_version`、`resolve_schema_version`（不改代码，返回值随版本号变化）
- 调用方：
  - saleor-dashboard 中的 `src/components/Shop/queries.ts`（`shop { version }`），经 `useShop()` 由 `src/configuration/index.tsx` 显示为 `coreVersion`，由 FD01 关联
  - App 的 `requiredSaleorVersion` 校验（`AppManifestRequiredSaleorVersion.satisfied`）
- 目标定义：`target-schema.graphql` 中的 `Shop.version` 和 `Shop.schemaVersion`

```graphql
type Shop implements ObjectWithMetadata {
  """
  Saleor API version.
  
  Requires one of the following permissions: AUTHENTICATED_STAFF_USER, AUTHENTICATED_APP.
  """
  version: String!

  """Minor Saleor API version."""
  schemaVersion: String!
}
```

- 字段说明：`version` 为 `"3.23.0"`，`schemaVersion` 为 `"3.23"`，两者均非空。
- 权限：
  - `version` 要求 `AUTHENTICATED_STAFF_USER` 或 `AUTHENTICATED_APP`。
  - `schemaVersion` 匿名可读。
- 错误：匿名查询 `version` 时返回字段级 `PermissionDenied`，行为不变。
- 完成判定：部署 3.23 后立即生效。
- 变更与兼容：只是取值变化，类型不变。依赖 `requiredSaleorVersion` 的 App 将按 3.23.0 判定 `satisfied`。

### I06 · 客户与员工搜索语义（`search_vector`）
- 所属设计单元：BD09
- 提供方：
  - saleor/`saleor/account/search.py` 中的 `search_users`（修改）
  - `prepare_user_search_vector_value`、`update_user_search_vector`（拟新增）
  - `saleor/graphql/account/schema.py` 中的 `resolve_customers`，以及 `saleor/graphql/account/filters.py` 中的 `filter_user_search`（不改代码，直接受益）
- 调用方：
  - saleor-dashboard 客户列表的 `src/customers/queries.ts`（`customers(filter: $filter)`，即 `CustomerFilterInput.search`）、员工列表的 `src/staff/queries.ts`（`staffUsers(filter: $filter)`，即 `StaffUserInput.search`）。前端不需要改动，FD 中只登记依赖。
  - E2E 播种脚本直接调用 `update_user_search_vector(user)`
- 目标定义：`target-schema.graphql` 中的 `Query.customers(search: String, filter: CustomerFilterInput, where: CustomerWhereInput, ...)`、`Query.staffUsers(filter: StaffUserInput, ...)`、`CustomerFilterInput.search`、`StaffUserInput.search`

```graphql
type Query {
  customers(
    filter: CustomerFilterInput @deprecated(reason: "Use `where` filter instead.")
    where: CustomerWhereInput
    sortBy: UserSortingInput
    """
    Search customers.
    
    Added in Saleor 3.22.
    """
    search: String
    before: String
    after: String
    first: Int
    last: Int
  ): UserCountableConnection @doc(category: "Users")
}
```

- 字段说明：
  - 参数签名不变。`search` 为可空字符串，为空或 `null` 时不过滤。
  - 匹配规则：一个用户满足以下任一条件即命中。
    1. `search_vector` 与 `websearch_to_tsquery('simple', search)` 匹配。检索范围包括邮箱、名、姓，以及默认地址和全部地址的姓名、公司、街道、城市、邮编、国家、电话。
    2. 将 `search` 按空白拆成多个词，每个词都以不区分大小写的子串形式出现在 `search_document` 中（与 3.22 规则相同）。
  - 结果集是 3.22 结果集的超集，不会出现搜索倒退。
  - 分页与排序语义不变，返回类型仍为 `UserCountableConnection`。
- 权限：
  - `customers` 要求 `MANAGE_ORDERS` 或 `MANAGE_USERS`。
  - `staffUsers` 要求 `MANAGE_STAFF`、`MANAGE_USERS` 或 `MANAGE_ORDERS`。
  - 与 Base 相同。
- 错误：不新增错误。权限不足时返回字段级 `PermissionDenied`。
- 完成判定：
  - 通过 API 新建或更新用户、地址后，同一事务内同步更新 `search_vector`，随后的搜索立即可以找到。
  - 存量用户的数据由迁移后的异步回填任务补齐。回填完成前，这些用户依靠 `search_document` 命中。
  - 回填任务幂等，可以重复执行。
- 变更与兼容：SDL 无变化。数据库新增 `account_user.search_vector` 列与 GIN 索引，`search_document` 继续维护。

### I07 · 插件列表不再包含 Adyen 与 NP Atobarai
- 所属设计单元：BD05
- 提供方：saleor/`saleor/settings.py` 中的 `BUILTIN_PLUGINS`（修改），以及 `saleor/graphql/plugins/resolvers.py` 中的 `resolve_plugins`、`resolve_plugin`（不改代码）
- 调用方：saleor-dashboard 插件列表与详情（`src/extensions/queries.ts` 中的 `plugins`/`plugin` 查询，以及 `src/extensions/views/EditPluginExtension`），外部 API 消费者
- 目标定义：`target-schema.graphql` 中的 `Query.plugins`、`Query.plugin`、`Mutation.pluginUpdate`

```graphql
type Query {
  """
  Look up a plugin by ID.
  
  Requires one of the following permissions: MANAGE_PLUGINS.
  """
  plugin(
    """ID of the plugin."""
    id: ID!
  ): Plugin

  """
  List of plugins.
  
  Requires one of the following permissions: MANAGE_PLUGINS.
  """
  plugins(
    filter: PluginFilterInput
    sortBy: PluginSortingInput
    before: String
    after: String
    first: Int
    last: Int
  ): PluginCountableConnection
}
```

- 字段说明：
  - `plugins` 的结果中不再出现 `mirumee.payments.adyen` 和 `mirumee.payments.np-atobarai`，即使数据库中仍保留它们的 `PluginConfiguration` 记录。
  - `plugin(id: "mirumee.payments.adyen")` 返回 `null`。
  - 其他插件的返回内容不变。
  - 已有支付记录上的 `Payment.gateway` 字符串原样返回。
- 权限：`MANAGE_PLUGINS`，不变。
- 错误：
  - 查询时不会因为残留的配置行报错。
  - 对已移除插件执行 `pluginUpdate(id: "mirumee.payments.adyen")`，返回 `errors[].code = NOT_FOUND`（`PluginError`，沿用 `saleor/graphql/plugins/mutations.py` 中 "Plugin doesn't exist." 分支）。
- 完成判定：部署后立即生效。不删除残留的配置数据，回滚版本后配置仍然可用。
- 变更与兼容：SDL 无变化，属于数据层面的移除。依赖这两个网关的商户需要改用 App 形式的支付集成。

## 3. 其他

- **未变更但被前端新实现依赖的接口**：FD03 用本地实现替代 `@saleor/sdk` 后，直接调用 `tokenCreate`、`tokenRefresh`、`tokenVerify`、`tokensDeactivateAll`、`externalAuthenticationUrl`、`externalObtainAccessTokens`、`externalRefresh`、`externalLogout`、`requestPasswordReset`、`setPassword`。这些操作在 `target-schema.graphql` 中的签名与 Base 完全相同，本次不登记为变更接口。
  - `tokenRefresh(csrfToken, refreshToken)` 在 Dashboard 中通过请求参数传入 `refreshToken`。
  - access token 过期时，`extensions.exception.code` 为 `ExpiredSignatureError`。前端据此触发刷新。
- **集合分配商品**（R16）：继续使用 `collectionAddProducts`，接口不变。即时刷新由前端在 mutation 完成后重新查询来实现（FD08）。
- **SDL 检查记录**：
  - 已执行：
    - `buildSchema` 语法检查和类型引用检查，均通过，共 1418 个类型。
    - `findBreakingChanges`（Base → Target）结果为空；dangerous changes 为 0。
    - Target 与 Dashboard 现有 `schema.graphql` 一致，只有 `scalar JSON` 的位置不同。
    - 用 Target 校验 Dashboard 的 640 个定义，字段错误为 0，重复片段为 1，该问题由 FD02 处理。
    - Dashboard mutation 文档的根 mutation 数最大为 4。
  - 未执行：
    - 用 Python 打印器重新生成 schema 并与 Target 比较
    - Dashboard codegen、tsc
    - 运行时联调（这些在研发阶段执行）
- **未决项**：
  - Q4：`GRAPHQL_MUTATION_COUNT_LIMIT` 的默认值（本契约暂定为 3）。
  - 描述文本中的 "Added in Saleor 3.22." 与 Dashboard 现有 schema 保持一致，以满足 R07 的双向一致要求，未改为 3.23。
