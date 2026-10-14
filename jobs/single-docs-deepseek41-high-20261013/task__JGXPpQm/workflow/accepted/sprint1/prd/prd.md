# PRD：Saleor Core 与 Dashboard 3.23.0 协同迁移

版本：v1
责任：产品
状态：需求范围与验收条件已定义
输入：instruction.md；现有项目代码
修订：首次交付

## 1. 业务背景与目标

Saleor 商家平台由两个仓库协同构成：`saleor`（核心后端，对外提供 GraphQL API）与 `saleor-dashboard`（商家管理前端，其 GraphQL 客户端类型由核心 schema 生成）。两者通过 GraphQL 契约强耦合：后端新增/删除字段、类型与枚举，前端必须同步重新生成客户端产物；前端升级所依赖的字段，后端必须实际提供。

当前工作区基线为 core `3.22.0`、dashboard `3.22.9`，目标版本为 `3.23.0`。本次需求是把两个仓库**协同升级到 3.23.0**：后端 API 与 Dashboard 行为保持一致，涵盖 GraphQL 契约、生成的客户端产物、数据库迁移以及构建/依赖声明；在实现目标行为的同时，保留回归测试所覆盖的既有行为；不得用测试专用桩替代缺失的生产功能。

目标：

1. 两仓库版本标识、GraphQL 契约、数据库迁移与依赖声明全部对齐到 3.23.0，且相互一致（前端不引用后端不存在的字段，后端不遗漏前端已使用的字段）。
2. 迁移过程中商家侧关键操作路径（登录、产品/订单/渠道/应用扩展管理等）与既有测试覆盖的行为不发生回归。
3. 全程离线完成：不抓取目标源码、不联网安装依赖；改动以普通源码提交形式落在工作树中，可导出相对固定基线的 diff。

依据：`instruction.md` 明确要求在两仓库实施协调的生产代码迁移，并列举了契约、生成产物、迁移与构建声明四类一致性对象；其中亦声明当前 benchmark 的 F2P/P2P 名单尚未冻结，因此本 PRD 不引用任何未发布的指标。本次没有可用的业务量化指标数据，故不编造指标。

## 2. 用户与场景

| 用户类型 | 典型任务 | 迁移影响 |
| --- | --- | --- |
| 商家运营人员（Dashboard 使用者） | 登录后台、维护产品与库存、处理订单、配置渠道与配送、安装与管理 App 扩展、编辑富文本描述与页面内容 | 升级后上述操作路径与交互结果不回归；富文本、图标、通知、日期展示等基础能力保持一致 |
| 第三方 App 开发者 / 集成方 | 依据 GraphQL 契约开发应用；读取 App 扩展的挂载点、打开目标与设置 | 契约字段（如 AppExtension 的 `mountName`/`targetName`/`settings`）必须在后端真实可用，废弃字段需有明确的 deprecated 说明 |
| 平台运维 / 发布负责人 | 部署新版本、执行数据库迁移、管理依赖与构建产物 | 迁移可升级可回滚、依赖声明可离线复现、版本标识正确 |
| 质量工程 / 评测执行者 | 运行 core-unit、core-e2e、dash-unit、dash-e2e 四个套件 | 套件可运行；fail-to-pass 通过、pass-to-pass 保持；评测物料不被改动 |

## 3. 需求条目

### 业务域 A：版本与发布基线

#### R01 · 双仓库版本与 schema 版本升级到 3.23.0

- 来源：Instruction「The baselines are core 3.22.0 and dashboard 3.22.9; the intended target is 3.23.0.」「Implement the coordinated production-code migration to 3.23.0 across both repositories.」
- 优先级：P0
- 需求描述：把两个仓库的版本标识统一提升到 3.23.0。后端以 `saleor/__init__.py` 的 `__version__` 为单一事实来源，并由其派生 `schema_version` 与 `user_agent_version`；`pyproject.toml` 的项目版本同步。前端提升 `package.json` 的 `version`，并把用于拉取/生成契约的 `config.saleor.schemaVersion` 指向 3.23。
- 验收条件：
  - AC-01-1：读取 `saleor/__init__.py`，`__version__` 为 `"3.23.0"`；由其派生的 `schema_version` 为 `"3.23"`，`user_agent_version` 为 `"Saleor/3.23"`。
  - AC-01-2：`pyproject.toml` 中 `[project]` 的 `version` 为 `"3.23.0"`。
  - AC-01-3：`saleor-dashboard/package.json` 中 `version` 为 `"3.23.0"`，`config.saleor.schemaVersion` 为 `"3.23"`。
  - AC-01-4：两仓库版本号一致，且改动后的 diff 中不存在把版本号改回 3.22 的修改。

### 业务域 B：GraphQL 契约与生成产物

#### R02 · core GraphQL schema 与 Dashboard 期望契约对齐

- 来源：Instruction「Keep the backend API and Dashboard behavior consistent, including their GraphQL contracts, generated client artifacts…」；推导依据：工作区内 dashboard `schema.graphql` 与 core `saleor/graphql/schema.graphql` 存在契约差异——dashboard 侧 `AppExtension` 已包含 `mountName`、`targetName`、`settings`，而 core 侧 `saleor/graphql/app/types.py` 仍只有 `mount`/`target`/`options`。
- 优先级：P0
- 需求描述：core 必须以代码为准生成并提交最新 `saleor/graphql/schema.graphql`，并补齐 dashboard 已在使用、但当前后端尚未提供的扩展字段：`AppExtension`（及 `AppManifestExtension`）提供 `mountName: String!`、`targetName: String!`、`settings: JSON!`，同时把 `mount`、`target`、`options` 标记为 deprecated 并指向替代字段；`WidgetTargetOptions.widgetTarget`、`NewTabTargetOptions.newTabTarget`、`HttpMethod.method` 同样标记 deprecated 并指向 `settings`。前端不得引用后端在 3.23 中已移除的字段。
- 验收条件：
  - AC-02-1：由 core 代码导出的 schema 与仓库内 `saleor/graphql/schema.graphql` 完全一致（导出结果与文件 diff 为空）。
  - AC-02-2：schema 中 `AppExtension` 暴露 `mountName: String!`、`targetName: String!`、`settings: JSON!`；`mount`、`target`、`options` 带 `@deprecated` 且 reason 指向替代字段。
  - AC-02-3：schema 中 `AppExtensionOptionsWidget.widgetTarget`、`AppExtensionOptionsNewTab.newTabTarget`、`HttpMethod.method` 带 `@deprecated`。
  - AC-02-4：dashboard 端所有 GraphQL 文档（`src/**/queries.ts`、`src/**/mutations.ts`、`src/**/fragments/*.ts`、`src/searches/*.ts`）在 3.23 schema 上校验通过，无未知字段、类型或参数错误。
  - AC-02-5：dashboard 中不再存在对 3.23 已删除契约的引用（例如 Adyen 相关支付类型/字段，若在该版本中被移除）。

#### R03 · Dashboard 客户端产物按 3.23 契约重新生成

- 来源：Instruction「…generated client artifacts…」；推导依据：`saleor-dashboard/package.json` 现有 `generate`（`graphql-codegen`，配置 `codegen.ts`）与 `fetch-schema`（按 `config.saleor.schemaVersion` 拉取 schema）脚本，以及 `src/graphql/` 下已提交的生成文件。
- 优先级：P0
- 需求描述：dashboard 以 3.23 契约重新生成 `src/graphql/types.generated.ts`、`src/graphql/hooks.generated.ts`、`src/graphql/fragmentTypes.generated.ts`、`src/graphql/typePolicies.generated.ts`，生成结果必须与手写代码、现有查询文档自洽；同时按目标工程的流程，把契约来源区分为「版本化主契约」（按 `config.saleor.schemaVersion` 拉取）与「main 分支 staging 契约」两条独立链路，两者各自产出、互不覆盖。
- 验收条件：
  - AC-03-1：在离线环境下执行生成命令（主契约链路）成功，产出的 `src/graphql/*.generated.ts` 与仓库中提交的内容一致；重复执行无 diff（生成结果稳定、可复现）。
  - AC-03-2：`package.json` 中主契约链路使用 `schemaVersion = 3.23` 的 schema 文件，staging 链路使用 main 分支 schema；两条链路的 schema 文件与生成产物互不覆盖。
  - AC-03-3：`pnpm run check-types` 通过；`pnpm run lint` 不因本次契约变更产生新错误。
  - AC-03-4：dashboard 单测（jest）中不出现因类型/字段缺失导致的编译或运行失败。

### 业务域 C：数据库迁移

#### R04 · 模型变更伴随数据库迁移且迁移图保持可升级

- 来源：Instruction「…database migrations…」「Preserve existing behavior covered by regression tests…」
- 优先级：P0
- 需求描述：本迁移中所有 Django 模型变更（尤其因支付网关移除而产生的字段删除）必须提供对应迁移文件；迁移图保持线性、可升级与可回滚；不得修改已发布的历史迁移文件，只允许新增。
- 验收条件：
  - AC-04-1：执行 `python manage.py makemigrations --check --dry-run` 无待生成迁移（模型与迁移文件一致）。
  - AC-04-2：新增迁移可在 3.22 基线的数据库上成功 upgrade，并可成功 downgrade 回退。
  - AC-04-3：`saleor/*/migrations/` 下不存在对既有迁移文件的修改，只有新增文件。
  - AC-04-4：在干净数据库与 3.22 基线数据库上执行 `python manage.py migrate` 均成功，迁移图无分叉或冲突。

### 业务域 D：后端功能迁移

#### R05 · 移除 Adyen 支付网关及其遗留字段

- 来源：推导依据（三处一致指向同一结论）：① 目标依赖清单中 core `pyproject.toml` 删除 `Adyen>=4.0.0,<5`；② `saleor/settings.py` 的 `BUILTIN_PLUGINS` 注册了 `saleor.payment.gateways.adyen.plugin.AdyenGatewayPlugin`；③ `saleor/payment/models.py` 中遗留字段注释写明「Legacy fields that allow Adyen plugin to work until it's removed… Once plugin is removed, these fields should be removed from the model.」
- 优先级：P0
- 需求描述：删除 Adyen 支付网关实现及其测试，解除插件注册与相关依赖；按模型注释指明的清理路径，删除仅为 Adyen 保留的 `Transaction` 遗留字段 `legacy_adyen_plugin_result_code`、`legacy_adyen_plugin_payment_method`，并提供对应迁移（见 R04）。除 Adyen 外的支付网关能力保持不变。
- 验收条件：
  - AC-05-1：`saleor/payment/gateways/adyen/`（含其测试）不再存在；生产代码中不存在对 `AdyenGatewayPlugin` 的引用。
  - AC-05-2：`settings` 的 `BUILTIN_PLUGINS`（进而 `PLUGINS`）中不再包含 `saleor.payment.gateways.adyen.plugin.AdyenGatewayPlugin`。
  - AC-05-3：生产代码中不再写入 `legacy_adyen_plugin_result_code`、`legacy_adyen_plugin_payment_method`；这两个模型字段经新增迁移删除，`makemigrations --check` 无残留（见 AC-04-1）。
  - AC-05-4：其余支付网关（`stripe`、`braintree`、`razorpay`、`authorize_net`、`np_atobarai`、`dummy`、`dummy_credit_card`）的注册与行为与 3.22 一致，其单元测试全部通过。

#### R06 · 富文本序列化/消毒依赖替换（draftjs-sanitizer、html-to-draftjs → nh3）

- 来源：推导依据：目标依赖清单中 core `pyproject.toml` 删除 `draftjs-sanitizer>=1.0.0,<2`、`html-to-draftjs>=1.0.1,<2`，新增 `nh3>=0.2.20`；工作区中 `saleor/core/utils/json_serializer.py` 直接 `from draftjs_sanitizer import SafeJSONEncoder`，并被 `CustomJsonEncoder`/`HTMLSafeJSON` 体系使用。
- 优先级：P1
- 需求描述：移除对 `draftjs-sanitizer`、`html-to-draftjs` 的运行时依赖，改用目标版本声明的消毒能力（`nh3`）或等价的本仓实现，保持既有对外行为：富文本字段保存时的消毒结果、用于搜索与长度校验的纯文本转换结果、以及把 JSON 嵌入 HTML 时的字符转义行为均不得改变。
- 验收条件：
  - AC-06-1：代码与依赖声明中不再出现 `draftjs_sanitizer`、`html_to_draftjs`（历史迁移文件除外）。
  - AC-06-2：`Product`、`Category`、`Collection`、`Page`、`AttributeValue`、`Discount`、`ShippingMethod` 等富文本字段在保存时仍执行消毒；非法 URL scheme（如 `javascript:`）被替换的行为与 3.22 一致。
  - AC-06-3：`clean_editor_js(..., to_string=True)` 仍返回去除标签的纯文本，供搜索向量与长度校验使用；相关单测通过。
  - AC-06-4：把 JSON 嵌入 HTML 的场景中，`<`、`>`、`&`、U+2028、U+2029 仍被转义；等价替换实现有单测覆盖。

#### R07 · 缩略图 AVIF 能力改用 Pillow 原生支持

- 来源：推导依据：目标依赖清单中 core `pyproject.toml` 删除 `pillow-avif-plugin>=1.5.2,<2` 并把 `pillow` 提升到 `>=12.1.1,<13`；工作区 `saleor/__init__.py` 首行 `import pillow_avif`，`saleor/thumbnail/__init__.py` 的 `ThumbnailFormat` 含 `AVIF` 且列入 `ALLOWED_THUMBNAIL_FORMATS`。
- 优先级：P1
- 需求描述：去掉 `pillow_avif` 的副作用导入与依赖，由 Pillow 12 原生支持 AVIF；AVIF 格式的识别、上传校验与缩略图转换能力保持不变。
- 验收条件：
  - AC-07-1：`saleor/__init__.py` 不再导入 `pillow_avif`；依赖声明中不存在 `pillow-avif-plugin`。
  - AC-07-2：`ThumbnailFormat.AVIF` 与 `ALLOWED_THUMBNAIL_FORMATS` 保持不变；AVIF 图片的上传校验与缩略图生成路径行为与 3.22 一致，相关测试（含 `saleor/graphql/core/tests/test_file_validation.py` 中 AVIF 用例）通过。
  - AC-07-3：安装的 Pillow 版本满足 `>=12.1.1,<13`，且不引入额外 AVIF 插件包。

#### R08 · 移除 posuto，日本地址处理不回归

- 来源：推导依据：目标依赖清单中 core `pyproject.toml` 删除 `posuto>=2025.1.0,<2026`；工作区 `saleor/payment/gateways/np_atobarai/api_helpers.py` 使用 `from posuto import Posuto` 由邮编解析日本地址。
- 优先级：P2
- 需求描述：去掉 `posuto` 依赖及其导入，np_atobarai 网关的地址处理逻辑在无本地邮编库的情况下仍能正常工作，且不因邮编解析失败而中断支付流程。
- 验收条件：
  - AC-08-1：依赖声明中不存在 `posuto`，生产代码中不存在 `posuto` 导入。
  - AC-08-2：np_atobarai 相关单元测试通过；地址处理在邮编无法解析时的降级行为明确（不抛出未捕获异常）。

#### R09 · 新增运行时依赖的接入

- 来源：推导依据：目标依赖清单中 core `pyproject.toml` 新增 `orjson>=3.11.4`、`idna>=3.10`、`kombu[sqs]>=4.6.11,<6.0.0`（`celery` 亦带 `sqs` extra）。
- 优先级：P2
- 需求描述：按目标声明引入上述依赖；若被用于替换既有实现（JSON 序列化、域名/主机名编码、Celery broker 传输），必须保证对外可观察行为（响应体、日志、任务投递语义）与 3.22 等价。
- 验收条件：
  - AC-09-1：依赖声明中包含 `orjson`、`idna`、`kombu[sqs]`，且可在离线环境中成功导入。
  - AC-09-2：引入后 GraphQL 响应与 Webhook/日志中的 JSON 内容与 3.22 等价（键与值语义一致），相关单测通过。

### 业务域 E：Dashboard 前端迁移

#### R10 · 移除 @saleor/sdk，改为本仓实现认证与客户端配置

- 来源：推导依据：① 目标依赖清单中 dashboard `package.json` 删除 `@saleor/sdk`；② 工作区代码内已标注迁移意图：`src/graphql/client.ts` 注释「TODO: Remove once @saleor/sdk is removed in favor of local implementation for auth」，且 `src/index.tsx`、`src/auth/**`、`src/utils/**` 等共 17 个文件引用该库。
- 优先级：P1
- 需求描述：移除 `@saleor/sdk` 依赖及其全部导入，用本仓实现等价能力：Apollo 客户端构造与 fetch 包装、Saleor 配置读取、认证状态与登录/刷新/登出、外部 access token、地址校验与元数据更新等辅助逻辑。对外行为（登录流程、token 刷新、权限与错误提示）保持与 3.22 一致。
- 验收条件：
  - AC-10-1：`package.json` 不再声明 `@saleor/sdk`；`src/`、`playwright/` 中不存在 `@saleor/sdk` 导入。
  - AC-10-2：`useAuthProvider`、`AuthProvider`、凭据管理、地址校验、元数据更新等既有单测通过；登录、登出、token 刷新、外部 access token 流程行为不变。
  - AC-10-3：`src/graphql/client.ts` 中「移除 @saleor/sdk」相关 TODO 被清除，客户端配置能力由本仓实现提供，类型检查通过。
  - AC-10-4：dashboard e2e 的登录/初始化用例（setup 项目）通过。

#### R11 · 图标体系统一到 lucide-react，移除 @material-ui/icons

- 来源：推导依据：① 目标依赖清单中 dashboard `package.json` 删除 `@material-ui/icons`；② 仓库内 lint 规则 `lint/rules/no-deprecated-icons.cjs` 明确要求「Avoid importing icons from @material-ui/icons. Use lucide-react instead.」，并在 `eslint.config.mjs` 中以 `local-rules/no-deprecated-icons` 生效；③ 当前有 9 个源文件引用 `@material-ui/icons`。
- 优先级：P1
- 需求描述：把 `@material-ui/icons` 的全部使用替换为 `lucide-react`（或仓库既有本地图标组件），移除该依赖；受影响的界面在视觉与交互上保持等价。
- 验收条件：
  - AC-11-1：`src/` 中不存在 `@material-ui/icons` 导入；受影响的 9 个文件（产品类型变体属性、产品库存卡片底部、翻译字段、App 组件挂件、国家列表、Chip、确认按钮、渠道分配策略、配置首页）改用 `lucide-react` 或本地图标。
  - AC-11-2：`package.json` 不再声明 `@material-ui/icons`；`local-rules/no-deprecated-icons` 校验无违规。
  - AC-11-3：上述受影响页面的既有 jest 测试通过，交互与展示无回归。

#### R12 · 前端基础能力依赖对齐（通知、日期、路由历史、动效、编辑器）

- 来源：推导依据：目标依赖清单中 dashboard `package.json` 新增直接依赖 `sonner@^2.0.7`、`moment@2.30.1`、`history@4.10.1`、`react-transition-group@4.4.5`、`@react-editor-js/core@2.1.0`（其中 `@react-editor-js/core` 已被 `src/components/RichTextEditor/ReactEditorJS.tsx` 引用但尚未声明为直接依赖）。
- 优先级：P2
- 需求描述：把上述库声明为直接依赖，并让通知提示、日期展示、路由历史与页面切换动效、富文本编辑器按目标版本的方式实现；用户可观察行为与 3.22 保持一致。
- 验收条件：
  - AC-12-1：`package.json` 中声明了 `sonner`、`moment`、`history`、`react-transition-group`、`@react-editor-js/core`，版本与目标清单一致。
  - AC-12-2：通知提示、日期时间展示（含时区相关组件）、路由前进/后退、动效、富文本编辑与保存的行为与 3.22 一致，相关 jest/storybook 测试通过。

#### R13 · 删除计划于 3.23 移除的兼容代码

- 来源：推导依据：工作区源码内标注「TODO: Remove in Saleor Dashboard 3.23」——`src/products/urls.ts` 的 `productVariantLegacyEditPath`（`/** @deprecated TODO: Remove in Saleor Dashboard 3.23 */`）与 `src/products/index.tsx` 中把旧版变体路径重定向到新格式的路由。
- 优先级：P2
- 需求描述：删除旧版产品变体编辑路径（`/products/<productId>/variant/<variantId>`）及其重定向逻辑与导出函数，仅保留新路径（`/products/variant/<variantId>`）。
- 验收条件：
  - AC-13-1：`productVariantLegacyEditPath` 与旧路径重定向路由被移除，全仓无残留引用，`TODO: Remove in Saleor Dashboard 3.23` 标注清零。
  - AC-13-2：产品变体编辑的新路径路由与页面行为不变，相关测试通过。

### 业务域 F：依赖声明、构建与质量门禁

#### R14 · 依赖与构建声明与目标一致

- 来源：Instruction「…and build/dependency declarations.」「Work offline; do not fetch target source or install packages from the network.」
- 优先级：P0
- 需求描述：两仓库的依赖声明与锁文件对齐目标版本：core 的 `pyproject.toml`/`uv.lock`，dashboard 的 `package.json`/`pnpm-lock.yaml`/`pnpm-workspace.yaml`/`.npmrc`。声明层面新增/删除的包必须与代码中的实际使用一致（不留无用依赖，也不留未声明的隐式依赖）。
- 验收条件：
  - AC-14-1：core `pyproject.toml` 依赖集合与目标清单一致——新增 `kombu[sqs]`、`nh3`、`idna`、`orjson`；移除 `Adyen`、`draftjs-sanitizer`、`html-to-draftjs`、`pillow-avif-plugin`、`posuto`；`uv.lock` 与之一致。
  - AC-14-2：dashboard `package.json` 依赖集合与目标清单一致——移除 `@material-ui/icons`、`@saleor/sdk`；新增 `@react-editor-js/core`、`history`、`moment`、`react-transition-group`、`sonner`。
  - AC-14-3：离线环境下安装/构建可直接完成（依赖已预装时无需联网），`pnpm run build` 成功，core 依赖可被 Python 运行时成功导入。
  - AC-14-4：代码中不再出现对已移除依赖的导入（`Adyen`、`draftjs_sanitizer`、`html_to_draftjs`、`pillow_avif`、`posuto`、`@material-ui/icons`、`@saleor/sdk`）。

#### R15 · 工程脚本与 lint 规则对齐目标

- 来源：推导依据：目标依赖清单中 dashboard `package.json` 的 `scripts` 与当前仓库的差异（新增契约 main/staging 双链路、lint 规则测试、storybook 测试等）；工作区已存在 `lint/rules/`（`named-styles`、`no-deprecated-icons`）但缺少 `named-effects`。
- 优先级：P1
- 需求描述：补齐/调整工程脚本与本地 lint 规则，使目标工程约定的命令可直接运行：契约生成与拉取的 main/staging 双链路、未使用 GraphQL 字段检查、lint 规则自测（含新增的命名副作用规则）、storybook 测试、支付资源更新、关闭严格模式的开发命令、e2e 认证清理与 chromatic 脚本。
- 验收条件：
  - AC-15-1：`package.json` 的 `scripts` 与目标一致，至少包含 `generate:main`/`generate:staging`、`fetch-schema:main`/`fetch-schema:staging`、`graphql-lint-unused`、`test:lint-rules`、`test-storybook`、`test-storybook:coverage`、`update-payment-assets`、`dev:no-strict`、`e2e:clean-auth`、`chromatic`。
  - AC-15-2：`pnpm run test:lint-rules` 通过，覆盖 `named-styles` 与新增的命名副作用规则。
  - AC-15-3：`pnpm run test` 通过（jest 套件 + lint 规则测试）；`pnpm run lint` 与 `pnpm run check-types` 不产生新错误。

#### R16 · 回归保持与质量门禁

- 来源：Instruction「Preserve existing behavior covered by regression tests while implementing the target behavior. Do not replace missing production features with test-specific stubs.」「The intended acceptance rule requires all selected fail-to-pass tests to pass after your changes and all selected pass-to-pass tests to remain passing.」「Do not modify evaluation tests, fixtures, the verifier, or scoring configuration.」
- 优先级：P0
- 需求描述：本次迁移必须在实现目标行为的同时保持既有回归行为；不得以测试专用桩替代缺失的生产功能；不得改动评测测试、夹具、verifier 或评分配置；改动以普通源码编辑提交到工作树，可导出相对固定基线的 diff。
- 验收条件：
  - AC-16-1：core-unit、core-e2e、dash-unit、dash-e2e 四个套件均可在本地 runtime 运行，且不因本次改动引入新的失败；收集失败或缺失结果不计为通过。
  - AC-16-2：评测选定的 fail-to-pass 用例在改动后全部通过，pass-to-pass 用例全部保持通过。
  - AC-16-3：评测测试、夹具、verifier、评分配置未被修改；生产功能不存在仅供测试使用的桩实现。
  - AC-16-4：两仓库的改动均已提交，diff 相对各自固定的 agent 基线可完整导出。

## 4. 范围与非目标

本次包含：

- 上述 R01–R16 的全部内容：两个仓库的版本标识、GraphQL 契约与生成产物、数据库迁移、后端功能迁移（支付网关、富文本消毒、图片、地址、运行时依赖）、前端迁移与兼容代码清理、依赖与构建声明、工程脚本与质量门禁。
- 为达成契约一致而必须进行的前后端配套改动（后端补字段、前端去引用）。

本次不包含（非目标）：

- 不实现 3.23.0 之外的新功能，不顺手重构与本次迁移无关的模块或 UI。
- 不进行线上数据回填或历史数据修复（除非迁移本身要求）。
- 不联网抓取目标源码、不联网安装依赖包；不替换预装的运行时与工具链。
- 不修改评测测试、夹具、verifier 或评分配置；不修改 benchmark 的 F2P/P2P 名单（由维护者冻结）。
- 不追求与上游目标树逐字节一致（Instruction 明确 evaluated tree 不要求逐字节相同）。

延期事项：无。

## 5. 其他

### 5.1 事实依据（本 PRD 的证据来源）

- `instruction.md` 全文：迁移范围、基线/目标版本、一致性对象、离线约束、回归与评测规则。
- 版本与依赖现状：`saleor/__init__.py`、`saleor/pyproject.toml`、`saleor-dashboard/package.json`（`version`、`config.saleor.schemaVersion`、`scripts`、`dependencies`）。
- 目标依赖清单（环境内提供的目标 manifest：core `pyproject.toml`/`uv.lock`，dashboard `.npmrc`/`package.json`/`pnpm-lock.yaml`/`pnpm-workspace.yaml`）：R05–R15 中所有依赖增删的推导依据，也是 R14 的验收锚点。
- 代码内的迁移标注：`saleor-dashboard/src/graphql/client.ts`（移除 `@saleor/sdk` 的 TODO）、`src/products/urls.ts` 与 `src/products/index.tsx`（Remove in Saleor Dashboard 3.23）、`saleor/payment/models.py`（Adyen 遗留字段注释）、`lint/rules/no-deprecated-icons.cjs`（图标迁移约束）、`eslint.config.mjs`（本地规则注册）。
- 契约差异证据：dashboard `schema.graphql` 与 core `saleor/graphql/schema.graphql` 的差异（`AppExtension` 的 `mountName`/`targetName`/`settings` 与对应 deprecated 标记）。
- 现状引用规模：`@material-ui/icons` 引用 9 个文件；`@saleor/sdk` 引用 17 个文件（`src/` 与 `playwright/`）。

### 5.2 产品决策

1. 以「契约一致 + 行为不回归」为验收主线：后端负责补齐前端已依赖的契约，前端负责去除对已移除契约的引用。
2. 版本与依赖以目标依赖清单为唯一锚点，不以当前工作区已有声明为准；但代码改动以满足既有回归测试为准，不做超出清单的额外改造。
3. 对工作区无法确证的目标实现细节（见 5.3），采取「最小改动 + 保持既有测试通过」的处理原则，并在实现阶段以官方测试的实际要求校正。

### 5.3 假设与待确认项

1. 3.23.0 新增的 GraphQL 字段与变更集合无法在离线工作区完整确证，需以目标源码为准。本 PRD 只对可确证的契约点（版本标识、`AppExtension` 字段与 deprecated 标记）给出具体验收条件，其余契约变更以「前后端一致、无未知字段引用」为验收口径。
2. `Transaction.gateway_response` 是否随 Adyen 一并移除尚未确证：模型注释指向该清理路径，但该字段同时被 GraphQL 暴露（`saleor/graphql/payment/types.py`）且被多处测试夹具引用。若保留，则 AC-05-3 仅覆盖 `legacy_adyen_plugin_*` 两个字段。
3. 契约 main/staging 双链路的产物文件命名与目录结构未确证（目标脚本引用 `codegen-main.ts`/`codegen-staging.ts` 与 `schema-main.graphql`/`schema-staging.graphql`，具体生成目标未知），AC-03-2 因此只约束「两条链路互不覆盖、主链路使用 3.23 契约」。
4. 新增 lint 规则（命名副作用）的具体约束未确证：目标脚本引用 `lint/rules/named-effects.test.mjs`，仓库已有 `named-styles` 与 `no-deprecated-icons` 两个规则及其注册方式，可据此推定形态，但规则的具体判定条件需以实现阶段为准。
5. `orjson`、`idna`、`nh3` 的具体接入点未确证（当前仓库无任何引用）。R06 与 R09 的验收条件因此限定为「行为等价」，不规定实现方式。
6. 官方测试在评测阶段单独提供，本 PRD 不预设具体用例名称；AC-16-1/AC-16-2 以套件与验收规则口径描述。
7. 工作区 `/workspace/artifacts/sprint1/prd/` 当前为空，未发现已封存的 PRD 冻结基线；若存在，本文件为首次交付版本，后续修订按模板要求记录版本、内容与原因。

### 5.4 依赖与风险提示

- 前端移除 `@saleor/sdk`（17 个引用点）与替换 `@material-ui/icons`（9 个文件）是本批次中改动面最大的两项，需优先保证认证链路与受影响页面的回归测试通过。
- 后端 Adyen 移除会连带影响支付模型字段与迁移，属于不可逆的 API 面收缩，必须与 R02/R03 的契约再生成同一批次完成，避免出现「后端已删、前端仍引用」的中间态。
