# 后端技术设计：Saleor Core 与 Dashboard 3.23.0 协同迁移（后端）

版本：v1
责任：后端技术设计
依据：PRD v1，artifacts/sprint1/prd/prd.md
修订：首次交付

## 1. 方案概述

本次后端工作的目标是把 `saleor`（core）从 3.22.0 提升到 3.23.0，并保证其对外 GraphQL 契约与 `saleor-dashboard` 3.23.0 的消费方式一致。整体方案分三条主线：

1. **契约主线**：补齐 dashboard 已经消费、但当前 core 尚未提供的 `AppExtension` / `AppManifestExtension` 字段（`mountName`、`targetName`、`settings`），并把被替代的 `mount`、`target`、`options` 及其子类型字段标记为 deprecated；随后以代码为准重新导出 `saleor/graphql/schema.graphql`。
2. **支付主线**：删除 Adyen 支付网关（`saleor/payment/gateways/adyen/`、插件注册），并按 `Transaction` 模型注释指明的清理路径删除两个 Adyen 专用遗留字段，配套新增数据库迁移。
3. **依赖与运行时主线**：按目标依赖声明替换运行时依赖（`draftjs-sanitizer`/`html-to-draftjs` → `nh3`；`pillow-avif-plugin` → Pillow 12 原生 AVIF；移除 `posuto`；接入 `orjson`、`idna`、`kombu[sqs]`），并保证对外可观察行为不变。

关键事实与源码依据：

- 契约差距可精确定位：以 core 的 `saleor/graphql/schema.graphql` 为 schema、以 dashboard 的 GraphQL 文档为 documents 运行 codegen，得到 **3 条错误**，全部集中在 `src/extensions/queries.ts` 的 `mountName`、`targetName`、`settings`；换成目标 schema 后 0 错误（命令与结果见 BD03）。
- 版本标识以 `saleor/__init__.py` 的 `__version__` 为单一来源，`schema_version` / `user_agent_version` 由其派生。
- `saleor/graphql/schema.graphql` 由 `./manage.py get_graphql_schema` 生成，`.pre-commit-config.yaml` 以 `./manage.py get_graphql_schema | diff saleor/graphql/schema.graphql -` 作为一致性门禁；在当前 Base 上该命令输出为空（已验证），因此本次任何契约改动都必须同步重新导出该文件。

## 2. 需求覆盖

| 需求 | 设计单元 |
| --- | --- |
| R01 | BD01 |
| R02 | BD02、BD03 |
| R04 | BD05 |
| R05 | BD04、BD05 |
| R06 | BD06 |
| R07 | BD07 |
| R08 | BD08 |
| R09 | BD09 |
| R14 | BD10 |
| R16 | BD11 |

前端承接的 R03、R10–R13、R15 不在本文件展开，见 frontend-design.md。R01 中 dashboard 侧版本标识由前端设计承接（FD07），此处只覆盖 core 侧。

## 3. 详细设计

### BD01 · core 版本与 schema 版本标识

- 覆盖需求：R01
- 设计说明：`saleor/__init__.py` 中 `__version__` 由 `"3.22.0"` 改为 `"3.23.0"`；该模块已有的派生逻辑 `_major, _minor, _ = __version__.split(".", 2)` 会自动得到 `schema_version = "3.23"`、`user_agent_version = "Saleor/3.23"`，无需额外改动。`pyproject.toml` 的 `[project] version` 同步改为 `"3.23.0"`。注意 `pyproject.toml` 中依赖项的增删属于 BD10，与版本号改动同批次提交。
- 验证方法：`python -c "import saleor; print(saleor.__version__, saleor.schema_version, saleor.user_agent_version)"` 输出 `3.23.0 3.23 Saleor/3.23`；`grep '^version' pyproject.toml` 输出 `version = "3.23.0"`。

### BD02 · AppExtension 契约扩展

- 覆盖需求：R02
- 设计说明：落点在 `saleor/graphql/app/types.py`。

  **a) 新增字段与描述文本**（描述必须与下述文本逐字一致，否则 BD03 的导出比对会失败）：

  - `AppManifestExtension`（基类，`saleor/graphql/app/types.py:108`）与 `AppExtension`（`saleor/graphql/app/types.py:199`，继承前者）同时获得三个字段：
    - `mountName = graphene.String(required=True, description="Name of the extension mount point in the dashboard. Replaces `mount`" + ADDED_IN_322)`
    - `targetName = graphene.String(required=True, description="Name of the extension target in the dashboard. Replaces `target`" + ADDED_IN_322)`
    - `settings = graphene.JSONString(required=True, description=...)`，其中 `AppExtension` 覆写描述为 `"App extension settings. Replaces `options` field." + ADDED_IN_322`，`AppManifestExtension` 保留 `"JSON object with settings for this extension." + ADDED_IN_322`。
  - `ADDED_IN_322` 取自 `saleor/graphql/core/descriptions.py`（现有常量，值为 `"\n\nAdded in Saleor 3.22."`）。沿用该常量可保证生成的 SDL 与 dashboard 已在消费的契约文本一致。

  **b) 废弃标记**（`deprecation_reason`）：

  - `AppManifestExtension.mount` / `AppExtension.mount`：`"Use `mountName` instead."`
  - `AppManifestExtension.target` / `AppExtension.target`：`"Use `targetName` instead."`
  - `AppExtension.options`：`"Use `settings` field instead."`
  - `AppExtensionOptionsWidget.widgetTarget`、`AppExtensionOptionsNewTab.newTabTarget`、`WidgetTargetOptions.method`、`NewTabTargetOptions.method`：`"Use `settings` field directly."`
  - `HttpMethod` 枚举本身与 `AppExtensionPossibleOptions` union 保持不变，仅作为废弃字段的类型继续存在。

  **c) 解析器**：`mountName`/`targetName` 的语义是「枚举成员名」，与 GraphQL 枚举序列化结果一致（现有测试 `saleor/graphql/app/tests/queries/test_app_extension.py` 亦以 `extension_data["mount"].lower()` 与模型值比较，可佐证线上值为大写成员名）。

  - `AppExtension`（模型根对象，`root.mount` / `root.target` 为 `saleor/app/types.py` 中的小写取值）：
    - `resolve_mount_name(root, _info) -> root.mount.upper()`
    - `resolve_target_name(root, _info) -> root.target.upper()`
  - `AppManifestExtension`（根对象是 `clean_manifest_data` 清洗后的 manifest 字典，见 `saleor/app/manifest_validations.py:228` 的 `_clean_extension_enum_field`，其值同样是小写枚举值）：
    - `resolve_mount_name(root, _info) -> str(root.get("mount", "")).upper()`
    - `resolve_target_name(root, _info) -> str(root.get("target") or AppExtensionTarget.POPUP).upper()`

  **d) `settings` 的取值语义**：模型上并不存在 settings 字段，`AppExtension` 只持久化 `target` 与 `http_target_method`（`saleor/app/models.py:156`）。因此 `settings` 由现有数据推导，结构为：

  ```json
  // target == WIDGET 且 http_target_method 非空
  { "widgetTarget": { "method": "GET" | "POST" } }
  // target == NEW_TAB 且 http_target_method 非空
  { "newTabTarget": { "method": "GET" | "POST" } }
  // 其他情况
  {}
  ```

  该推导与 manifest 的原始 `options` 内容等价：`saleor/app/validators.py` 中 `NewTabTargetOptions`/`WidgetTargetOptions` 的 `method` 为必填，且 `saleor/app/installation_utils.py:243` 仅在对应 options 存在时写入 `http_target_method`，因此「options 存在」与「method 非空」互为充要条件。推导实现避免了新增模型字段与数据迁移，是风险最低的方案。

  - `AppExtension.resolve_settings(root, _info)`：按上表由 `root.target` 与 `root.http_target_method` 构造。
  - `AppManifestExtension.resolve_settings(root, _info)`：从清洗后的 manifest 字典读取 `options`（snake_case：`new_tab_target` / `widget_target`），转换为上表的 camelCase 结构；无对应键时返回 `{}`。

  **e) 兼容性**：`mount`、`target`、`options` 字段继续返回原有值，仅附加 deprecated 说明，老消费者无需改造即可继续工作。

- 验证方法：新增/补充 `saleor/graphql/app/tests/queries/` 下的查询测试，断言三个新字段的取值与上述语义一致（含 WIDGET、NEW_TAB、POPUP 三种 target 与 `http_target_method` 为空的情形）；运行 `pytest saleor/graphql/app/tests/ -q`。

### BD03 · schema 导出与契约一致性校验

- 覆盖需求：R02
- 设计说明：BD02 落地后执行 `./manage.py get_graphql_schema > saleor/graphql/schema.graphql`，使仓库内的 SDL 与代码一致；该文件即本次交付的 `target-schema.graphql` 的内容来源。生成物必须逐字等于「Base + BD02 的字段与废弃标记」，不允许手工编辑。

  本次已完成的校验（作为交付证据，未运行项在 §6 说明）：

  1. Base 一致性：`./manage.py get_graphql_schema | diff saleor/graphql/schema.graphql -` → 输出为空（Base 文件与代码一致，说明该校验口径可靠）。
  2. 契约差距定位：以 Base schema 校验 dashboard 全部 GraphQL 文档（`src/**/queries.ts`、`src/**/mutations.ts`、`src/**/fragments/*.ts`、`src/searches/*.ts`）→ 3 条错误，全部为 `Cannot query field "mountName"/"targetName"/"settings" on type "AppExtension"`（`src/extensions/queries.ts:9-11`）。
  3. 目标校验：以本次交付的 `target-schema.graphql` 校验同一批文档 → 0 错误，生成产物中 `ExtensionListQuery` 的节点类型为 `mountName: string, targetName: string, settings: any`，与前端消费方式一致。
  4. SDL 差异核对：`target-schema.graphql` 与 Base 的差异共 9 处 hunk，全部为 BD02 约定的新增字段与 `@deprecated` 标记；与 dashboard 现有 `schema.graphql` 比对，除 `scalar JSON` 的声明位置（排序差异，无语义影响）外完全一致。

- 验证方法：`.pre-commit-config.yaml` 中的 hook `./manage.py get_graphql_schema | diff saleor/graphql/schema.graphql -` 必须输出为空。

### BD04 · 移除 Adyen 支付网关

- 覆盖需求：R05
- 设计说明：

  - 删除目录 `saleor/payment/gateways/adyen/`（含 `plugin.py`、`webhooks.py`、`utils/`、`tests/` 与 `tests/fixtures/`）。
  - `saleor/settings.py:861` 从 `BUILTIN_PLUGINS` 中移除 `"saleor.payment.gateways.adyen.plugin.AdyenGatewayPlugin"`；`PLUGINS` 由 `BUILTIN_PLUGINS + EXTERNAL_PLUGINS` 派生，无需额外改动。
  - 依赖声明中移除 `Adyen>=4.0.0,<5`（属 BD10）。
  - 其他网关（`stripe`、`braintree`、`razorpay`、`authorize_net`、`np_atobarai`、`dummy`、`dummy_credit_card`）的实现与注册保持不变；`saleor/payment/interface.py`、`saleor/payment/utils.py` 中与 Adyen 无关的通用路径不动。
  - 历史迁移文件不得修改：`saleor/payment/migrations/0061_transaction_legacy_adyen_plugin_payment_method_and_more.py` 保留原样（其作用只是记录当时的字段创建）。
- 验证方法：`grep -ri "adyen" saleor/ --include="*.py" | grep -v "/migrations/"` 无输出；`pytest saleor/payment/tests saleor/payment/gateways -q` 通过；`pytest saleor/graphql/payment -q` 通过。

### BD05 · 支付遗留字段清理与数据库迁移

- 覆盖需求：R04、R05
- 设计说明：

  - 删除模型字段：`saleor/payment/models.py` 中 `Transaction.legacy_adyen_plugin_result_code` 与 `Transaction.legacy_adyen_plugin_payment_method`（及其上方说明注释）。
  - 删除传递链路：`saleor/payment/interface.py` 的 `GatewayResponse` 数据类中对应两个字段；`saleor/payment/utils.py:500-501` 的 `Transaction.objects.create(...)` 调用中对应两个关键字参数。
  - **保留** `Transaction.gateway_response` 字段与 GraphQL 字段 `Transaction.gatewayResponse`（已带 deprecated 说明）。理由：该字段并非 Adyen 独有，`saleor/payment/utils.py:253` 的 `generate_transactions_data` 会把它作为 `TransactionData.gateway_response` 传给所有网关；且它被大量既有测试夹具引用（如 `saleor/checkout/tests/fixtures/checkout_with_payment.py`），删除会造成与本次迁移目标无关的回归面。
  - 新增迁移：`python manage.py makemigrations payment` 生成一个 `RemoveField` 迁移（依赖当前 payment 应用的最新迁移 `0065_transactionevent_reason_reference`），并确认迁移图仍为线性（`saleor/order/migrations/0214_orderevent_order_orderevent_date_idx.py` 等跨应用依赖已指向既有节点，不受影响）。
- 验证方法：`python manage.py makemigrations --check --dry-run` 无输出；`python manage.py migrate` 在干净库与 3.22 基线库上均成功；`pytest saleor/payment -q`、`pytest saleor/checkout -q`、`pytest saleor/graphql/payment -q` 通过。

### BD06 · 富文本序列化/消毒依赖替换

- 覆盖需求：R06
- 设计说明：

  - 唯一直接引用点：`saleor/core/utils/json_serializer.py:3` 的 `from draftjs_sanitizer import SafeJSONEncoder`，被同文件的 `HTMLSafeJSON(SafeJSONEncoder, DjangoJSONEncoder)` 使用（该类当前在 core 内无其他调用点，属于对外保留的工具类）。
  - `SafeJSONEncoder` 的语义是「在标准 JSON 编码基础上转义 HTML 危险字符」（`<`、`>`、`&`、U+2028、U+2029），与 `draftjs` 无实质关系，只是历史上由该包提供。设计上改为在本仓实现等价的 `HTMLSafeJSONEncoder`（在 `default()`/`encode()` 中对上述字符做转义），`HTMLSafeJSON` 继承它并保留原有类名与导入路径，避免影响外部使用方。
  - 富文本消毒链路（`saleor/core/utils/editorjs.py` 的 `clean_editor_js`）本身不依赖 `draftjs-sanitizer`/`html-to-draftjs`，保持行为不变：`clean_list_item`/`clean_image_item`/`clean_embed_item`/`clean_other_items` 的 URL 白名单与黑名单 scheme 逻辑不动，`to_string=True` 仍返回拼接后的纯文本。
  - 新增依赖 `nh3` 用于本仓实现中的 HTML 转义/清洗能力（目标依赖清单已声明）；若实现中不需要，则仅声明依赖不引入调用，不得因此改变既有输出。
- 验证方法：`pytest saleor/core/tests saleor/product/tests/test_utils.py -q`；新增针对 `HTMLSafeJSON` 的单元测试覆盖上述五个字符的转义；`grep -rn "draftjs" saleor/ --include="*.py" | grep -v "/migrations/"` 无输出。

### BD07 · 缩略图 AVIF 能力改用 Pillow 原生支持

- 覆盖需求：R07
- 设计说明：删除 `saleor/__init__.py:1` 的 `import pillow_avif  # noqa: F401 # imported for side effects`。`saleor/thumbnail/__init__.py` 中的 `ThumbnailFormat.AVIF`、`ALLOWED_THUMBNAIL_FORMATS`、`MIME_TYPE_TO_PIL_IDENTIFIER["image/avif"]` 全部保留；Pillow 12 原生支持 AVIF，缩略图生成与图片校验路径无需改动。依赖声明同步把 `pillow` 提升到 `>=12.1.1,<13` 并删除 `pillow-avif-plugin`（属 BD10）。
- 验证方法：`pytest saleor/thumbnail saleor/graphql/core/tests/test_file_validation.py -q`（含 `test_clean_image_file_in_avif_format`）；`python -c "from PIL import Image; print(Image.registered_extensions())"` 中包含 `.avif`。

### BD08 · posuto 移除与 np_atobarai 地址处理

- 覆盖需求：R08
- 设计说明：`saleor/payment/gateways/np_atobarai/api_helpers.py` 中 `from posuto import Posuto` 与 `with Posuto() as pp: jap_ad = pp.get(ad.postal_code)` 的邮编解析逻辑移除，改为不依赖本地邮编库的实现：地址数据直接取支付信息中的字段（`city`、`country_area`、`postal_code` 等），无法解析时走既有的 `logger.warning("Invalid japanese postal code: %s", ...)` 分支，保证支付流程不因地址解析失败而中断。依赖声明中删除 `posuto`（属 BD10）。
- 验证方法：`pytest saleor/payment/gateways/np_atobarai -q` 通过；`grep -rn "posuto" saleor/` 无输出。

### BD09 · 运行时依赖接入（orjson、idna、kombu[sqs]）

- 覆盖需求：R09
- 设计说明：目标依赖清单新增 `orjson>=3.11.4`、`idna>=3.10`、`kombu[sqs]>=4.6.11,<6.0.0`。当前 Base 中三者均无引用，因此设计上按「最小接入」处理：仅在依赖声明中引入（BD10），不在本次迁移中主动替换现有 `json` 序列化路径、URL 编码路径或 Celery broker 配置，以免引入与迁移目标无关的行为变化。`idna` 与 `orjson` 作为传递/可选依赖被显式声明，供后续版本使用；`kombu[sqs]` 的声明使 Celery 具备 SQS 传输能力（现有 `CELERY_BROKER_URL` 解析逻辑不变）。
- 验证方法：`python -c "import orjson, idna, kombu; print(orjson.__version__)"` 成功；`pytest saleor/core/tests saleor/webhook -q` 不出现与 JSON 序列化相关的回归。

### BD10 · 依赖声明与构建声明对齐

- 覆盖需求：R14
- 设计说明：`pyproject.toml` 的 `[project] dependencies` 按目标清单调整为：

  - 新增：`kombu[sqs]>=4.6.11,<6.0.0`、`nh3>=0.2.20`、`idna>=3.10`、`orjson>=3.11.4`
  - 移除：`Adyen>=4.0.0,<5`、`draftjs-sanitizer>=1.0.0,<2`、`html-to-draftjs>=1.0.1,<2`、`pillow-avif-plugin>=1.5.2,<2`、`posuto>=2025.1.0,<2026`
  - 已有提升（由环境补丁先行落地，本次不重复改动）：`authlib>=1.6.9`、`cryptography>=44.0.2,<47`、`django[bcrypt]~=5.2.13`、`pillow>=12.1.1,<13`
  - `uv.lock` 与声明保持一致；`[tool.*]` 各段落不做改动。
- 验证方法：离线环境下 `python -c "import saleor"` 成功；`uv lock --check`（若可用）或等价的一致性检查通过；`grep -E "^(Adyen|posuto|draftjs|html-to-draftjs|pillow-avif)" pyproject.toml` 无输出。

### BD11 · 后端回归与质量门禁

- 覆盖需求：R16
- 设计说明：本次后端改动不得改变既有回归行为，也不得引入仅服务于测试的桩实现。回归范围：`core-unit`（`pytest -m 'not e2e'`）与 `core-e2e`（`pytest -m e2e`）。本地执行方式：`/opt/runtime/run-suite.sh <attempt> core-unit core-e2e`（该脚本会启动并回收本地 runtime；仅健康检查通过不算测试通过）。
- 验证方法：上述套件在改动后无新增失败；改动前后失败集合的差集为空；评测阶段提供的 fail-to-pass 用例全部通过、pass-to-pass 用例保持通过。

## 4. 接口清单

完整契约集中写在 interface-contract.md。

| 接口 | 所属设计单元 | 说明 |
| --- | --- | --- |
| I01 | BD02 | `AppExtension` 新增 `mountName`、`targetName`、`settings` 三个非空字段 |
| I02 | BD02 | `AppManifestExtension` 新增同名三个非空字段（manifest 视图） |
| I03 | BD02 | `AppExtension.mount` / `target` / `options` 增加 deprecated 标记（行为不变） |
| I04 | BD02 | 扩展选项类型的字段级 deprecated 标记（`widgetTarget`、`newTabTarget`、`method`） |

## 5. 工程任务与依赖

### BT01 · 版本标识升级

- 覆盖设计单元：BD01
- 依赖：无
- 工作与验证：改 `saleor/__init__.py` 的 `__version__` 与 `pyproject.toml` 的 `project.version`；验证 `import saleor` 输出的三个版本字符串。

### BT02 · AppExtension 契约字段与解析器

- 覆盖设计单元：BD02
- 依赖：无
- 工作与验证：按 BD02 在 `saleor/graphql/app/types.py` 增加字段、deprecated 标记与解析器；补 `saleor/graphql/app/tests/queries/` 的断言；运行 `pytest saleor/graphql/app/tests -q`。

### BT03 · 重新导出并提交 schema.graphql

- 覆盖设计单元：BD03
- 依赖：BT02
- 工作与验证：`./manage.py get_graphql_schema > saleor/graphql/schema.graphql`，随后 `./manage.py get_graphql_schema | diff saleor/graphql/schema.graphql -` 必须为空；导出结果应与交付的 `target-schema.graphql` 完全一致。

### BT04 · 移除 Adyen 网关

- 覆盖设计单元：BD04
- 依赖：无
- 工作与验证：删除网关目录、解除插件注册；运行支付相关测试，确认其他网关不受影响。

### BT05 · 支付遗留字段清理与迁移

- 覆盖设计单元：BD05
- 依赖：BT04
- 工作与验证：删除模型字段与数据类字段，`makemigrations` 生成迁移；验证 `makemigrations --check --dry-run` 无输出、`migrate` 成功。

### BT06 · 富文本序列化依赖替换

- 覆盖设计单元：BD06
- 依赖：无
- 工作与验证：本仓实现 HTML 安全 JSON 编码器，替换 `draftjs_sanitizer.SafeJSONEncoder`；补单测并运行 core 相关测试。

### BT07 · AVIF 依赖迁移

- 覆盖设计单元：BD07
- 依赖：无
- 工作与验证：删除 `pillow_avif` 导入；运行缩略图与文件校验测试。

### BT08 · posuto 移除

- 覆盖设计单元：BD08
- 依赖：无
- 工作与验证：改造 `np_atobarai/api_helpers.py` 的地址处理；运行该网关测试。

### BT09 · 运行时依赖接入

- 覆盖设计单元：BD09
- 依赖：BT06、BT07、BT08
- 工作与验证：确认三个新增依赖可导入且未改变既有行为；运行 core 单测抽样。

### BT10 · 依赖声明对齐

- 覆盖设计单元：BD10
- 依赖：BT04、BT06、BT07、BT08、BT09
- 工作与验证：按 BD10 调整 `pyproject.toml` 并同步锁文件；确认离线可导入。

### BT11 · 后端回归验证

- 覆盖设计单元：BD11
- 依赖：BT01–BT10
- 工作与验证：运行 `/opt/runtime/run-suite.sh <attempt> core-unit core-e2e`，比对改动前后的失败集合。

## 6. 其他

### 6.1 未运行与待确认的检查

- 本地未运行完整的 core-unit / core-e2e 套件（需要本地数据库与 runtime，属实施阶段的验证任务 BT11）。
- 未运行 `migrate`/`makemigrations`（迁移文件尚不存在，属 BT05）。
- 未在本阶段修改任何生产代码；`target-schema.graphql` 由脚本对 Base 施加 BD02 的差异生成，脚本位于 `/workspace/scratch/gen_target_schema.py`。

### 6.2 风险与决策记录

- **`settings` 采用推导而非新增模型字段**：与 manifest 原始 `options` 内容等价（理由见 BD02-d），避免新增字段与数据迁移；若后续确证目标实现引入了 `settings` 持久化字段，本设计可平滑替换为字段直读，契约不变。
- **`Transaction.gatewayResponse` 保留**：见 BD05；这是与 PRD §5.3 待确认项 2 对应的决策——采取最小改动以避免与本次迁移无关的回归面。
- **`ADDED_IN_322` 文案沿用**：新字段的描述文本与 dashboard 已在消费的契约文本保持一致，避免前后端文档不一致；文案不影响运行时行为。
- **`scalar JSON` 声明位置**：Base 与 dashboard 现有 `schema.graphql` 中该标量位置不同（纯排序差异）。目标 SDL 保留 Base 的位置，不人为重排。
- 新增字段为非空（`String!` / `JSON!`），因此解析器必须保证任何情况下都返回非空值：`mountName`/`targetName` 对空值返回空字符串而非 `None`；`settings` 至少返回 `{}`。
