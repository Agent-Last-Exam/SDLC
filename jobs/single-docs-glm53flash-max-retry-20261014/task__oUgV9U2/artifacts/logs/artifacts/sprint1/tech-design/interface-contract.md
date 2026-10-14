# 接口对齐文档：Saleor core 与 Dashboard 3.23.0 迁移

版本：v1
责任：后端技术设计
依据：后端技术设计 v1，backend-design.md
修订：首次交付；修订时记录版本、内容及原因

## 1. 通用约定

- **入口与协议**：唯一 API 入口 `POST /graphql/`（`saleor/graphql/urls.py` → `GraphQLView`，`saleor/graphql/views.py`），支持单请求与 JSON 数组批量请求（`_handle_query`，:129-136：批量时逐条 `get_response`，整体状态码取各条最大值）。schema 浏览：GET `/graphql/`（Playwright/GQL playground，`PLAYGROUND_ENABLED`）。健康检查 `GET /health/`。无 REST/gRPC 新边界；完整 GraphQL 目标契约见 `target-schema.graphql`（与 core 3.23.0 运行时导出及 dashboard `schema.graphql` 三者一致）。
- **认证**：沿用 3.22——JWT Bearer（staff/app token）、app 请求头（`X-Saleor-App-*`）、`JWT_THIRDPARTY_ACCESS_TYPE` 三方令牌；权限模型不变（`PermissionEnum`、`AppPermission.MANAGE_APPS` 等）。
- **错误分层**：参数/语法错误 → 请求级 400（`errors` 数组，`format_error` 归一：message + `extensions.code`）；权限不足 → 字段级 `PermissionDenied`（`extensions.code = "PermissionDenied"`）；业务校验 → 字段级 `errors` 列表（如 `ProductError`）。本次新增的 I02 属请求级 400。
- **ID 规则**：全局 ID（`base64(type:pk)`）不变；`mountName`/`targetName` 为字符串枚举名（UPPER_CASE），不是全局 ID。
- **成功判定**：GraphQL 层 `data` 非空且无 `errors`；HTTP 层 200。批量请求中单条失败按上述分层体现于对应条目。
- **废弃策略（R05）**：仅新增与标记废弃（`@deprecated(reason: ...)`），不物理移除；3.22 已废弃元素（`products(filter:)`、`Transaction.gatewayResponse`、deprecated 插件等）原样保留。

## 2. 接口契约

### I01 · AppExtension/AppManifestExtension 新字段与废弃标记
- 所属设计单元：BD02（backend）；FD01 消费（frontend）
- 提供方：`saleor/` 仓库 `saleor/graphql/app/types.py` 的 `AppManifestExtension`（manifest dict 根，`Manifest.extensions` 元素）与 `AppExtension`（`models.AppExtension` 根，`appExtensions` 连接元素）；拟新增（基线无）
- 调用方：`saleor-dashboard/` `src/extensions/queries.ts` `ExtensionList` 查询（DB 根，本次由 FD01 经再生成工件消费）；`src/fragments/apps.ts` `AppManifest` 片段（manifest 根，既有消费者，字段不变仍合法）；外部 App 作者经 `app { manifest }` 读取
- 目标定义：`target-schema.graphql` 中 `type AppExtension`、`type AppManifestExtension`、`type AppExtensionOptionsWidget`、`type WidgetTargetOptions`、`type AppExtensionOptionsNewTab`、`type NewTabTargetOptions`、`scalar JSON`

```graphql
type AppManifestExtension @doc(category: "Apps") {
  permissions: [Permission!]!
  label: String!
  url: String!
  mount: AppExtensionMountEnum! @deprecated(reason: "Use `mountName` instead.")
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

type AppExtension implements Node @doc(category: "Apps") {
  # ……（id/permissions/label/url 同上，另有）:
  mount: AppExtensionMountEnum! @deprecated(reason: "Use `mountName` instead.")
  target: AppExtensionTargetEnum! @deprecated(reason: "Use `targetName` instead.")
  mountName: String!          # 描述同 AppManifestExtension.mountName
  targetName: String!         # 描述同 AppManifestExtension.targetName
  """
  App extension settings. Replaces `options` field.

  Added in Saleor 3.22.
  """
  settings: JSON!
  app: App!
  accessToken: String
  options: AppExtensionPossibleOptions @deprecated(reason: "Use `settings` field instead.")
}

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

（权威全文见 `target-schema.graphql`；以上为字段清单的摘录，描述文本与目标 SDL 逐字符一致。）

- 字段说明：
  - `mountName: String!`（非空）：挂载点名称，取值集合与 `AppExtensionMountEnum` 成员名一致（如 `PRODUCT_OVERVIEW_MORE_ACTIONS`、`ORDER_DETAILS_WIDGETS`）。manifest 根：由 manifest `mount` 字段（经 `_clean_extension_enum_field` 归一）映射成员名；DB 根：`AppExtension.mount`（小写值）→ `.upper()` 成员名。
  - `targetName: String!`（非空）：打开方式名称，取值 `POPUP | APP_PAGE | NEW_TAB | WIDGET`。manifest 根缺省 target 时按既有 `resolve_target` 的 POPUP 缺省语义输出 `POPUP`。
  - `settings: JSON!`（非空 JSON 对象）：原 `options` 的 JSON 形态，键为 `newTabTarget` 或 `widgetTarget`（互斥，均可缺省），值为 `{"method": "GET" | "POST"}`；无任何配置时为 `{}`。DB 根：`target == WIDGET` → `{"widgetTarget": {"method": http_target_method}}`；`target == NEW_TAB` → `{"newTabTarget": {"method": http_target_method}}`；其余 `{}`。manifest 根：读 manifest extension 的 `options.newTabTarget.method` / `options.widgetTarget.method`（camelCase，清洗后仍保留在 dict 中）。
  - 列表语义：`Manifest.extensions: [AppManifestExtension!]!` 与 `appExtensions.edges.node` 均为列表+非空项，语义不变。
- 权限：不变——`appExtensions` 连接要求 `AUTHENTICATED_STAFF_USER | AUTHENTICATED_APP`（`saleor/graphql/app/schema.py:97-108`）；`accessToken` 解析沿用 app 归属/JWT 三方令牌校验；`App.manifest` 沿用 `MANAGE_APPS`/owner 规则。
- 错误：查询侧无新增错误码；字段为派生值，不抛业务错误。manifest 写入侧（`appInstall`/`appFetchManifest`）的 manifest 校验错误不变（`AppErrorCode.INVALID` 等）。
- 完成判定：查询即解析，无持久化、无事件、无异步任务；`ExtensionList` 一次请求内可稳定读到三字段（loader `AppExtensionByAppIdLoader`/`AppByIdLoader` 行为不变）。
- 变更与兼容：对 3.22 消费者完全向后兼容——`mount`/`target`/`options`/`widgetTarget`/`newTabTarget`/`method` 全部保留且解析行为不变，仅增加 deprecated 标记；dashboard 3.22.9 的 `AppManifest` 片段（旧字段）继续合法。dashboard 3.22.9+ 的 `ExtensionList`（新字段）在 3.22.0 core 上会因 schema 缺字段而失败，本次补齐后恢复（这正是 F2P 的契约缺口）。

### I02 · 批量请求 mutation 数量上限（HTTP 层，无 SDL 变化）
- 所属设计单元：BD03（backend）；FD03 联调验证（frontend）
- 提供方：`saleor/` 仓库 `saleor/graphql/views.py`（`execute_graphql_request` 内接线）+ `saleor/graphql/core/validators/mutation_count.py`（拟新增）+ `saleor/settings.py`（`GRAPHQL_MUTATION_COUNT_LIMIT`，拟新增）
- 调用方：所有 `/graphql/` POST 客户端；部署层 `/opt/runtime/services.sh:84` 以 `GRAPHQL_MUTATION_COUNT_LIMIT=4` 启动 API 进程；dashboard `VariantUpdate`（`src/products/mutations.ts:110-175`，单文档 4 根字段）为限内正常用例
- 目标定义：无 SDL 元素（`target-schema.graphql` 不含对应类型）；目标行为描述：请求（含 JSON 数组批量中的每个条目文档）中全部 mutation 操作的根字段总数 N 超过环境变量 `GRAPHQL_MUTATION_COUNT_LIMIT`（>0 时启用）即拒绝

请求/响应形态：

```json
// 请求（任意 POST /graphql/，单条或批量数组中之一条）
{"query": "mutation A { m1 { id } m2 { id } m3 { id } m4 { id } m5 { id } }"}

// 响应（limit=4 时）
// HTTP 400
{"errors": [{
  "message": "GraphQL request exceeded the maximum number of mutation fields (5 > 4).",
  "extensions": {"code": "GRAPHQL_MUTATION_COUNT_LIMIT_EXCEEDED", "mutationCount": 5, "limit": 4}
}]}
```

- 字段说明：`extensions.code` 固定 `GRAPHQL_MUTATION_COUNT_LIMIT_EXCEEDED`；`mutationCount` 为该文档 mutation 根字段总数（别名不改计数，多 mutation 操作求和；query/subscription 根字段不计）；`limit` 为当前配置值。计数对 `data` 为数组的批量请求逐条目独立执行，超限条目返回错误，其余条目正常执行；整体 HTTP 状态码取最大值（400）。
- 权限：不涉权限——校验发生在认证/解析后、执行前，对匿名与已认证请求一致。
- 错误：本接口即错误路径本身；正常限内请求无任何可见变化（响应体、延迟均与 3.22 一致）。变量 `GRAPHQL_MUTATION_COUNT_LIMIT=0` 或未设置（默认）→ 功能关闭，行为与基线逐字节一致；pytest 进程不设置该变量（`services.sh` 注释明示），上游测试语义保留。
- 完成判定：无持久化/事件/异步；拒绝路径不执行任何 resolver。幂等：同一文档重复请求结果确定。
- 变更与兼容：默认关闭，升级对既有消费者零影响；仅在运维显式配置限值的部署（本次评估运行时 =4）中，单文档 mutation 根字段 >4 的新/旧客户端会收到 400——dashboard 既有流程恰好为 4，不受影响。

### I03 · shop 版本字段输出 3.23.0/3.23
- 所属设计单元：BD01（backend）；FD03 联调核对（frontend）
- 提供方：`saleor/` 仓库 `saleor/__init__.py`（`__version__`/`schema_version`）与 `saleor/graphql/shop/types.py`（`resolve_version`/`resolve_schema_version`）
- 调用方：外部消费者与集成工具（schema 版本探测）；dashboard 不直接消费（`config.saleor.schemaVersion` 为其自身声明值）
- 目标定义：`target-schema.graphql` 中 `type Shop` 的：

```graphql
  """Saleor API version."""
  version: String!
  """Minor Saleor API version."""
  schemaVersion: String!
```

- 字段说明：`version` 输出 `"3.23.0"`；`schemaVersion` 输出 `"3.23"`（由 `__version__.split(".", 2)` 派生）。均为非空 String。
- 权限：`version` 要求 `AUTHENTICATED_STAFF_USER | AUTHENTICATED_APP`（`shop/types.py:344-352`）；`schemaVersion` 无权限要求（公开给任何已认证上下文，语义与 3.22 一致）。
- 错误：无新增错误路径。
- 完成判定：查询即返回模块常量；无持久化。幂等确定。
- 变更与兼容：仅值变化（3.22.0→3.23.0、3.22→3.23），SDL 与解析器不变；依赖版本探测的集成按 semver 正常识别 minor 升级。

## 3. 其他
- `scalar JSON`：core 既有 `generic.GenericScalar` 实例，SDL 印刷名 `JSON`；I01 的 `settings` 使用该标量。`scalar JSON` 在 SDL 中的打印位置随 print_schema 的引用顺序出现在 `AppExtensionTargetEnum` 之后（与 dashboard 3.22.9 期望一致），属生成器确定性输出。
- 无法由 SDL 表达的语义：I02（HTTP 状态码与部署级环境变量）、`settings` 的 JSON 内键结构（`newTabTarget|widgetTarget` 互斥，`method ∈ {GET, POST}`）——前者已在本文件与 BD03 固化；后者由消费端 zod schema（`src/extensions/domain/app-extension-manifest-options.ts`）与提供端 BD02 解析器共同约束，不引入 GraphQL 层枚举（与上游一致）。
- 已执行的检查：`target-schema.graphql` 通过 graphql (npm, buildSchema/parse) 语法与根类型校验；与 dashboard 3.22.9 `schema.graphql` diff 为零（逐字符一致）；与 core 基线 schema 的 diff 仅覆盖 I01 域。未执行：core 运行时导出比对（实现阶段 BT02 以 `get_graphql_schema` 完成）。
- 编号使用记录：I01～I03 首发；后续修订顺延，不重排、不复用。
