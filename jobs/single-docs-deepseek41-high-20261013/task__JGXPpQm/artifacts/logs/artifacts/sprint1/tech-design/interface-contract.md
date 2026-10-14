# 接口对齐文档：Saleor Core 与 Dashboard 3.23.0 协同迁移

版本：v1
责任：后端技术设计
依据：后端技术设计 v1，backend-design.md
修订：首次交付

## 1. 通用约定

- **协议与入口**：本迁移中唯一发生变化的对外接口边界是 Saleor 的 GraphQL API，入口为 `/graphql/`（单一端点，POST）。前后端不新增 REST 或其它协议接口。
- **契约描述文件**：GraphQL 的完整目标描述见同目录的 `target-schema.graphql`（由 core 的 Base SDL 加上本次设计推导的变更构成）。该文件即 3.23.0 的目标契约，dashboard 侧的所有查询/变更文档必须能在此 schema 上通过校验。
- **认证**：沿用现有机制。商家用户（staff）通过会话/JWT 认证；第三方 App 通过 App token 认证。`appExtensions`、`appExtension` 查询要求 `AUTHENTICATED_STAFF_USER` 或 `AUTHENTICATED_APP` 之一（`saleor/graphql/app/schema.py:97-103`）。
- **错误分层**：GraphQL 层错误统一以 `errors[]` 返回。权限不足返回 `PermissionDenied`（`extensions.code = PERMISSION_DENIED`，`permissions` 数组给出缺失权限）；参数或业务条件错误返回 `ValidationError`/领域错误（`extensions.code` 为对应错误码）；对象不存在返回 `null`（非空字段不成立时由 GraphQL 层报错）。本次新增字段不引入新的错误类型。
- **ID 规则**：沿用 Relay 全局 ID（`base64("<Type>:<pk>")`），本次不新增 ID 形态。
- **可空性与默认值语义**：`String!` / `JSON!` 表示字段永不为 null（查询可省略该字段，但一旦选中必然返回非空值）；`String` 表示可能为 null。列表字段的 `!` 分别作用于列表本身与列表项，`[Permission!]!` 表示列表与元素均非空。
- **成功判定**：GraphQL 查询以 `errors` 为空且 `data` 中对应字段存在非空值判定成功；变更（mutation）除返回体无错误外，还需满足各接口「完成判定」中的持久化要求。
- **版本约定**：新字段描述文本沿用仓库既有常量 `ADDED_IN_322`（`"\n\nAdded in Saleor 3.22."`），与 dashboard 已在消费的契约文本保持一致；这是文案约定，不影响运行时行为。

## 2. 接口契约

### I01 · `AppExtension` 新增 `mountName` / `targetName` / `settings`

- 所属设计单元：BD02
- 提供方：`saleor`（core）— `saleor/graphql/app/types.py` 的 `class AppExtension`（拟新增 3 个字段与对应 resolver：`resolve_mount_name`、`resolve_target_name`、`resolve_settings`）
- 调用方：`saleor-dashboard` — `src/extensions/queries.ts`（`ExtensionList` 查询，`appExtensions { edges { node { … } } }`）→ 由 `src/extensions/hooks/useExtensions.ts` 消费；本次无新增 FD，消费方设计单元为 FD01
- 目标定义：`target-schema.graphql` → `type AppExtension`、`Query.appExtensions`、`Query.appExtension`

```graphql
type AppExtension implements Node @doc(category: "Apps") {
  """The ID of the app extension."""
  id: ID!

  """List of the app extension's permissions."""
  permissions: [Permission!]!

  """Label of the extension to show in the dashboard."""
  label: String!

  """URL of a view where extension's iframe is placed."""
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

  """The app assigned to app extension."""
  app: App!

  """JWT token used to authenticate by third-party app extension."""
  accessToken: String

  """
  App extension options.

  Added in Saleor 3.22.
  """
  options: AppExtensionPossibleOptions @deprecated(reason: "Use `settings` field instead.")
}
```

- 字段说明：

  | 字段 | 类型 | 取值语义 |
  | --- | --- | --- |
  | `mountName` | `String!`（非空，无参数，无默认值） | 挂载点**枚举成员名**，取值为 `AppExtensionMountEnum` 的成员名字面量（UPPER_CASE），如 `"PRODUCT_DETAILS_WIDGETS"`；与 `mount` 返回的是同一挂载点，仅序列化形式不同（`mount` 为枚举值 `PRODUCT_DETAILS_WIDGETS`，`mountName` 为字符串 `"PRODUCT_DETAILS_WIDGETS"`） |
  | `targetName` | `String!`（非空，无参数，无默认值） | 打开方式**枚举成员名**，取值为 `AppExtensionTargetEnum` 的成员名字面量（UPPER_CASE）：`"POPUP"`、`"APP_PAGE"`、`"NEW_TAB"`、`"WIDGET"` |
  | `settings` | `JSON!`（非空，无参数，无默认值） | 扩展设置对象。结构为 `{"widgetTarget": {"method": "GET"\|"POST"}}`、`{"newTabTarget": {"method": "GET"\|"POST"}}` 或 `{}`（见下方推导规则） |

  **`mountName` / `targetName` 的推导**：模型层 `saleor/app/models.py:156` 的 `AppExtension.mount` / `.target` 存放的是小写枚举值（如 `product_details_widgets`、`new_tab`），取自 `saleor/app/types.py` 中的 `AppExtensionMount` / `AppExtensionTarget` 常量。resolver 返回其 `upper()` 形式，即枚举成员名。

  **`settings` 的推导**（模型无 settings 字段，由现有数据构造）：

  | 条件 | 返回值 |
  | --- | --- |
  | `target == WIDGET` 且 `http_target_method` 非空 | `{"widgetTarget": {"method": "<GET\|POST>"}}` |
  | `target == NEW_TAB` 且 `http_target_method` 非空 | `{"newTabTarget": {"method": "<GET\|POST>"}}` |
  | 其他（含 `POPUP`、`APP_PAGE`、`http_target_method` 为空） | `{}` |

  该推导与 manifest 原始 `options` 内容等价：`saleor/app/validators.py` 中 `NewTabTargetOptions`/`WidgetTargetOptions` 的 `method` 为必填，`saleor/app/installation_utils.py:243` 仅在对应 options 存在时写入 `http_target_method`，因此「options 存在」与「method 非空」互为充要条件。

- 权限：字段级无额外权限要求，可见性继承父对象。`appExtensions` 查询要求 `AUTHENTICATED_STAFF_USER` 或 `AUTHENTICATED_APP`；同一对象上的 `app` 字段对非本人 App 会抛 `PERMISSION_DENIED`（需 `MANAGE_APPS` 或 `OWNER`），`accessToken` 仅对本人 App 有值。三个新字段本身不区分身份，对有权读取该扩展的调用方返回相同值。
- 错误：字段无参数，不产生参数错误。父对象为空时返回 null；解析器不抛业务错误。非空约束由 GraphQL 层保证：`mountName`/`targetName` 在底层值为空时返回空字符串 `""`，`settings` 至少返回 `{}`，不会因非空字段为 null 而产生 `errors`。
- 完成判定：纯读接口，无持久化副作用。同一数据在同一时刻的重复查询结果一致（`settings` 对象由持久化字段确定性地构造）。
- 变更与兼容：本次新增（Base 中不存在）。`mount`、`target`、`options` 三个旧字段保留原行为，仅附加 `@deprecated`（见 I03），旧消费者无需改造。前端消费方已在使用新字段，过渡期不存在「前端读新、后端未提供」的窗口（前端引用见 `src/extensions/queries.ts:9-11`）。

### I02 · `AppManifestExtension` 新增 `mountName` / `targetName` / `settings`

- 所属设计单元：BD02
- 提供方：`saleor`（core）— `saleor/graphql/app/types.py` 的 `class AppManifestExtension`（拟新增 3 个字段与对应 resolver）
- 调用方：外部 App 开发者 / 集成方通过 `appFetchManifest` mutation 的返回体读取（`saleor/graphql/app/mutations/app_fetch_manifest.py:19` 的 `Manifest` 类型 → `Manifest.extensions`）。dashboard 本次不消费该路径；消费方设计单元为 FD01（用于契约一致性与后续扩展）
- 目标定义：`target-schema.graphql` → `type AppManifestExtension`、`type Manifest`、`Mutation.appFetchManifest`

```graphql
type AppManifestExtension @doc(category: "Apps") {
  """List of the app extension's permissions."""
  permissions: [Permission!]!

  """Label of the extension to show in the dashboard."""
  label: String!

  """URL of a view where extension's iframe is placed."""
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

  | 字段 | 类型 | 取值语义 |
  | --- | --- | --- |
  | `mountName` | `String!` | 同 I01：挂载点枚举成员名（UPPER_CASE） |
  | `targetName` | `String!` | 同 I01：打开方式枚举成员名（UPPER_CASE）；manifest 未声明 `target` 时按 `AppExtensionTarget.POPUP` 取值（与既有 `resolve_target` 的默认值一致），即返回 `"POPUP"` |
  | `settings` | `JSON!` | 由清洗后的 manifest 数据构造；描述文本为 `JSON object with settings for this extension.`（与 I01 的描述文本不同，需逐字保持） |

  根对象是 `saleor/app/manifest_validations.py` 的 `clean_manifest_data` 清洗后的 manifest 字典（`_clean_extension_enum_field` 已把 `mount`/`target` 归一为小写枚举值，`_clean_extension_options` 把 `options` 归一为 snake_case 并 `exclude_none=True`）。`settings` 由 `options`（`new_tab_target` / `widget_target`）转换为 camelCase：`{"newTabTarget": {"method": ...}}`、`{"widgetTarget": {"method": ...}}`；无对应键时返回 `{}`。`mount`/`target` 缺失时返回空字符串而非 null。

- 权限：`appFetchManifest` 要求 App token 或具备 `MANAGE_APPS` 的 staff 用户；字段级无额外要求。manifest 是请求方提交的内容，不涉及跨对象可见性差异。
- 错误：manifest 校验失败时 mutation 返回校验错误（既有行为，不受本次改动影响）；新增字段本身不产生错误。
- 完成判定：`appFetchManifest` 不持久化，只做校验与回显；同一 manifest 的重复调用结果一致。
- 变更与兼容：本次新增（Base 中不存在）。`mount`、`target` 保留并附加 `@deprecated`（见 I03）。新增字段为非空，resolver 对缺失值返回 `""` / `{}`。

### I03 · `AppExtension` / `AppManifestExtension` 旧字段废弃标记

- 所属设计单元：BD02
- 提供方：`saleor`（core）— `saleor/graphql/app/types.py`
- 调用方：既有外部消费者；`saleor-dashboard` 本次不再引用这些字段（`src/extensions/queries.ts` 已改用新字段）
- 目标定义：`target-schema.graphql` → `type AppExtension`、`type AppManifestExtension`

```graphql
"""Place where given extension will be mounted."""
mount: AppExtensionMountEnum! @deprecated(reason: "Use `mountName` instead.")

"""Type of way how app extension will be opened."""
target: AppExtensionTargetEnum! @deprecated(reason: "Use `targetName` instead.")

"""
App extension options.

Added in Saleor 3.22.
"""
options: AppExtensionPossibleOptions @deprecated(reason: "Use `settings` field instead.")
```

（`mount` / `target` 在两个类型上各出现一次，deprecation reason 完全相同；`options` 仅存在于 `AppExtension`。）

- 字段说明：字段类型、可空性与取值语义与 Base 完全一致，本次**只增加 `@deprecated` 指令**，不改变解析逻辑。`mount` 仍返回 `AppExtensionMountEnum` 枚举值，`target` 仍返回 `AppExtensionTargetEnum` 枚举值，`options` 仍返回 `AppExtensionPossibleOptions` union（`WIDGET` → `AppExtensionOptionsWidget`，`NEW_TAB` → `AppExtensionOptionsNewTab`，其他 → `null`）。
- 权限：与 I01/I02 相同（继承父对象可见性），本次不改动。
- 错误：无变化。`options` 保持可空，非 WIDGET/NEW_TAB 时返回 `null`（不产生错误）。
- 完成判定：纯读接口，无副作用。
- 变更与兼容：**向后兼容的软废弃**。`@deprecated` 只影响 introspection 与生成产物的类型注释，不改变运行时行为，旧消费者可继续使用；新消费者应改用 `mountName`/`targetName`/`settings`。废弃字段在 3.23.0 中不删除。

### I04 · 扩展选项类型的字段级废弃标记

- 所属设计单元：BD02
- 提供方：`saleor`（core）— `saleor/graphql/app/types.py` 的 `AppExtensionOptionsWidget`、`AppExtensionOptionsNewTab`、`WidgetTargetOptions`、`NewTabTargetOptions`
- 调用方：既有外部消费者（通过已废弃的 `AppExtension.options` 读取）；`saleor-dashboard` 本次不引用
- 目标定义：`target-schema.graphql` → `union AppExtensionPossibleOptions` 及其成员类型

```graphql
"""Represents the options for an app extension."""
type AppExtensionOptionsWidget @doc(category: "Apps") {
  """Options for displaying a Widget"""
  widgetTarget: WidgetTargetOptions @deprecated(reason: "Use `settings` field directly.")
}

"""Represents the WIDGET target options for an app extension."""
type WidgetTargetOptions @doc(category: "Apps") {
  """HTTP method for Widget target (GET or POST)"""
  method: HttpMethod! @deprecated(reason: "Use `settings` field directly.")
}

"""Represents the options for an app extension."""
type AppExtensionOptionsNewTab @doc(category: "Apps") {
  """Options controlling behavior of the NEW_TAB extension target"""
  newTabTarget: NewTabTargetOptions @deprecated(reason: "Use `settings` field directly.")
}

"""Represents the NEW_TAB target options for an app extension."""
type NewTabTargetOptions @doc(category: "Apps") {
  """HTTP method for New Tab target (GET or POST)"""
  method: HttpMethod! @deprecated(reason: "Use `settings` field directly.")
}

enum HttpMethod {
  POST
  GET
}

union AppExtensionPossibleOptions = AppExtensionOptionsWidget | AppExtensionOptionsNewTab
```

- 字段说明：类型、可空性与取值语义与 Base 完全一致，本次只增加 `@deprecated`。`widgetTarget`/`newTabTarget` 保持可空（对应 target 不匹配时为 null）；`method` 保持 `HttpMethod!` 非空，取值为 `POST` 或 `GET`。`HttpMethod` 枚举与 `AppExtensionPossibleOptions` union 本身不变，仅作为废弃字段的类型继续存在。
- 权限：继承父对象（`AppExtension`）可见性，本次不改动。
- 错误：无变化。
- 完成判定：纯读接口，无副作用。
- 变更与兼容：向后兼容的软废弃，理由同 I03。

## 3. 其他

### 3.1 未登记的接口边界（说明理由）

- **`@saleor/sdk` 移除（FD02）**：属于 dashboard 内部的实现替换，不构成跨仓库的对外契约边界——SDK 调用的仍是既有 GraphQL 操作（`tokenCreate`、`externalAuthenticationUrl`、`externalObtainAccessTokens`、`tokenRefresh`、`tokensDeactivateAll`、`setPassword`、`user` 查询），这些操作在 Base 与目标 schema 中均已存在且本次不改动其定义。因此不新增接口编号。
- **`productVariantLegacyEditPath` 与旧路径重定向删除（FD05）**：属于 dashboard 前端路由的内部约定，不经过 GraphQL，也不在 `target-schema.graphql` 的表述范围内，故不登记为接口。
- **依赖声明、工程脚本、lint 规则（FD06/FD07/BD10）**：构建期约定，不是运行时接口边界。

### 3.2 无法由目标描述语言表达的语义

- `settings` 的构造规则（由 `target` + `http_target_method` 推导，见 I01）无法在 SDL 中表达，只能以文档约定；这是本次前后端联调必须共同遵守的语义。
- `mountName` / `targetName` 取「枚举成员名」而非「枚举值的序列化结果」这一约定同样无法在 SDL 中表达。前端 `src/extensions/hooks/useExtensions.ts` 用 `ALL_APP_EXTENSION_MOUNTS.parse(mountName)` 与 `AppExtensionManifestTarget.parse(targetName)` 做**严格**（非转换）校验，仅接受 UPPER_CASE 成员名；若后端返回小写值会抛错并使该扩展不可用。这是联调首要验证项。
- `AppExtension.settings` 与 `AppManifestExtension.settings` 的描述文本不同（前者 `App extension settings. Replaces \`options\` field.`，后者 `JSON object with settings for this extension.`），但两者语义相同。文本差异需逐字保留，否则 `./manage.py get_graphql_schema | diff saleor/graphql/schema.graphql -` 门禁会失败。
- `scalar JSON` 在 Base 与 dashboard 现有 `schema.graphql` 中的声明位置不同（纯排序差异，无语义影响）。`target-schema.graphql` 保留 Base 的位置，不人为重排。

### 3.3 未决项

- `Transaction.gatewayResponse` 的去留（PRD §5.3 待确认项 2）由 BD05 决策为**保留**（已带 deprecated），因此它仍是既有接口的一部分，本次未变更，不登记为新增接口；若后续确证需删除，应作为新的接口编号登记。
- 3.23.0 除 `AppExtension` 之外是否还有其它契约变更无法在离线工作区完整确证。本文件只登记可确证的接口变化；以「dashboard 全部 GraphQL 文档在 `target-schema.graphql` 上校验通过（0 错误）」作为契约完整的判据。
- `settings` 若在目标实现中改为持久化字段，I01/I02 的字段级契约不变，仅「字段说明」中的推导规则需替换为直读语义。
