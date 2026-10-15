# 后端技术设计：Saleor 3.23 结账、收款与商户运营一致性交付

版本：v1
责任：后端技术设计
依据：PRD v1，artifacts/sprint1/prd/prd.md
修订：首次交付；后续修订需记录版本、内容与原因

## 1. 方案概述

本次交付以 Saleor Core 3.22.0（`/workspace/repos/saleor`，`saleor/graphql/schema.graphql` 35185 行）与 Dashboard 3.22.9（`/workspace/repos/saleor-dashboard`）为升级起点，后端在既有商业链路上补齐一致性、可解释失败与权限边界。所有新增 schema 元素注释统一写 `Added in Saleor 3.23.`；弃用统一使用 `@deprecated(reason: "...")` 且 reason 必须给出替代路径；mutation 统一返回 `errors: [XxxError!]!`（含 `field`、`code`、`message`），权限失败返回权限错误而非空结果。

现有行为链与源码依据：

- **结账与配送**：`saleor/checkout/fetch.py` 的 `CheckoutInfo.get_all_shipping_methods()`（139-190）、`valid_shipping_methods`（277-279）、`valid_delivery_methods`（281-290）、`get_delivery_method_info()`（229-275）以及 `DeliveryMethodBase`/`ShippingMethodInfo`/`CollectionPointInfo`（306-426）已能计算内置与外部配送方法；`saleor/graphql/checkout/mutations/utils.py:75-96 clean_delivery_method`、`checkout_delivery_method_update.py:158-240`、`saleor/checkout/checkout_cleaner.py:24-63 clean_checkout_shipping`、`checkout_complete.py:170-346` 负责更新与完成时的校验。基线**没有**「可用选项 + 当前选择」的统一重算返回结构（PRD 5.1-1），R01/R02 为此新增能力并保留 `shippingMethod`/`availableShippingMethods`/`checkoutShippingMethodUpdate` 的弃用读取语义。
- **库存**：`Channel.warehouses`（`Warehouse.channels` M2M，through `ChannelWarehouse`，`saleor/warehouse/models.py:265-293`）关系已存在；可售量用 `StockQuerySet.annotate_available_quantity`（330-346）、`get_available_quantity`（`availability.py:521-534`），预留用 `check_stock_and_preorder_quantity_bulk`（141-186）。R03 统一商品查询、结账、订单、履约、草稿订单的语义并保留未切换商店行为。
- **收款与订单**：`TransactionItem`（`saleor/payment/models.py:31-191`）与 legacy `Payment`（257 起）两条路径并存；订单金额分解字段 `totalAuthorized`/`totalCharged`/`totalRefunded`/`totalBalance`（`saleor/graphql/order/types.py:2254-2325,2827+`）已存在。礼品卡当前只是折扣式抵扣（`Checkout.gift_cards`/`Order.gift_cards` M2M，`checkoutAddPromoCode` 写入），`TransactionItem` 上没有礼品卡字段（PRD 5.1-5）。
- **身份与安全**：密码登录由 `CreateToken`/`SetPassword`/`PasswordChange`/`RequestPasswordReset` 分别处理，无商店级策略；Google OIDC 在 `enable_refresh_token` 时仅追加 `offline_access` scope（`plugins/openid_connect/plugin.py:221-234`），无 `access_type`（PRD 5.1 及核对结论）。富文本清理偏弱（`core/utils/editorjs.py:8` 仅黑名单 `javascript:`，无深度限制、不处理 rel）。
- **扩展与事件**：`AppExtension` 模型（`app/models.py:156-176`）提供 `mount`/`target`/`http_target_method`，GraphQL 暴露 `mount`/`target`/`options`（`graphql/app/types.py:199-288`），而 Dashboard 生成客户端请求 `mountName`/`targetName`/`settings`（`saleor-dashboard/schema.graphql:3015-3067`）——两侧不一致。Webhook 投递状态仅 `PENDING/SUCCESS/FAILED`（`core/__init__.py:30-39`、`graphql/webhook/enums.py:305-311`），无「重试中」。
- **历史数据**：订单以 `shipping_method` FK（`order/models.py:171`）与 `shipping_method_name`（185）去规范化记录配送方式，外部运费标识存于 private metadata（`external_app_shipping_id`，`checkout/utils.py:84`），无 public/private 元数据快照（PRD 5.1-13）。

方案按三条主线落地：（1）**一致事实**——BD01–BD04、BD16 让可售性、库存、配送选择、配送元数据在各入口一致；（2）**统一账本**——BD07–BD10 把礼品卡纳入交易生命周期，统一金额分解、资金动作边界与基础交易检索；（3）**安全与兼容**——BD05/BD06、BD11–BD15、BD17–BD20 用服务端校验、明确失败与权限边界替代页面隐藏或静默降级。未显式切换（`useChannelWarehousesForStock=false`、自动完成未配置渠道）、旧客户端合法旧标识、历史订单配送元数据均保持升级前语义；不新增数值约定（一致性窗口、重试次数、超时、深度上限沿用既有常量或由实现给出并在错误中可定位，见 PRD Q1–Q8）；失败不产生部分写入，资金与库存动作依据最新对象状态做幂等检查。

本文件中的行号锚点均对照 `/workspace/repos/saleor` 基线核对；对脊柱中描述有偏差的锚点，本文件使用核对后的实际落点（例如 `giftcard/__init__.py:9-38` 为 `GiftCardEvents` 常量、`giftcard/events.py:213-238` 为 `gift_cards_used_in_order_event` 辅助函数；支付 mutation 实际位于 `saleor/graphql/payment/mutations/transaction/` 子目录）。

## 2. 需求覆盖

下表列出后端承接的全部需求及对应设计单元。R14、R15、R20、R21、R29、R30、R31 的后端贡献为「无后端改动」，由前端设计单元承担；此处仍逐条列出以保证覆盖可审计。

| 需求 | 设计单元 |
| --- | --- |
| R01 结账配送选项的主动重新计算与当前选择 | BD01 |
| R02 更新配送方式与完成结账时的有效性复核 | BD02 |
| R03 渠道与仓库直连的库存计算与既有行为保留 | BD03 |
| R04 商品编辑页按渠道的可售性诊断 | BD04 |
| R05 已支付结账自动完成的资格条件与幂等 | BD05 |
| R06 自动完成策略的按渠道配置与状态呈现 | BD06 |
| R07 礼品卡纳入统一支付生命周期 | BD07 |
| R08 结账取消与订单售后的礼品卡对账 | BD07 |
| R09 订单金额分解的可解释性 | BD08 |
| R10 人工资金动作的权限、状态与余额限制 | BD08 |
| R11 交易的基础检索能力 | BD09 |
| R12 主体搜索能力边界 | BD10 |
| R13 搜索更新、分页与异常的可解释性 | BD10 |
| R14 锁定筛选与普通筛选的合并 | 无后端改动（由 FD02 承担；搜索语义沿用，见 §4 无接口变化清单） |
| R15 选择器去重与返回路径上下文 | 无后端改动（由 FD03 承担） |
| R16 密码登录策略由商店统一控制 | BD11 |
| R17 外部身份关联与 Google OIDC 离线授权 | BD12 |
| R18 富文本与外链的保存前校验 | BD13 |
| R19 扩展安装、查询与历史数据迁移约定 | BD14 |
| R20 扩展表单响应的处理 | 无后端改动（由 FD05 承担；同步载荷与字段解析见 BD15） |
| R21 自托管商店的扩展目录 | 无后端改动（由 FD05 承担） |
| R22 Webhook 同步与异步载荷的构建边界 | BD15 |
| R23 事件投递的隔离、重试与状态展示 | BD15 |
| R24 订单中的配送元数据快照 | BD16 |
| R25 元数据基础编辑保留，独立管理入口不交付 | BD17 |
| R26 执行前的输入校验与可分支的失败语义 | BD18 |
| R27 弃用读取与已退出能力的明确错误 | BD19 |
| R28 查得出与改得动都要有对应权限 | BD20 |
| R29 配置加载与保存的上下文一致性 | 无后端改动（由 FD06 承担） |
| R30 展示准确性与草稿订单动作可用性 | 无后端改动（由 FD07 承担；后端保证字段准确，见 BD18） |
| R31 不新增独立功能，保留既有基础能力 | 无后端改动（由 FD11 及前端非目标承担；后端非目标见 §6） |

## 3. 详细设计

以下按 BD01..BD20 展开。涉及的数据模型变更统一在 **§3 末尾的迁移清单**（本节各单元只写字段与迁移名），迁移文件序号以基线各 app 的最新迁移为起点递增。

### BD01 · 结账配送选项重算与当前选择
- 覆盖需求：R01
- 设计说明：

  **落点与复用**。新增 GraphQL mutation `checkoutDeliveryOptionsRecalculate(id, token)`（接口 I01），实现于新文件 `saleor/graphql/checkout/mutations/checkout_delivery_options_recalculate.py`，并在 `saleor/graphql/checkout/schema.py` 注册。该 mutation 直接复用现有计算链，不另写一套配送计算：`fetch_checkout_lines(checkout)` → `fetch_checkout_info(checkout, lines, manager)`（`saleor/checkout/fetch.py:429-640`）→ `CheckoutInfo.valid_delivery_methods`（`fetch.py:281-290`，内部链式组合 `valid_shipping_methods` 与 `valid_pick_up_points`）与 `CheckoutInfo.get_delivery_method_info()`（`fetch.py:229-275`）。外部同步配送服务结果通过 `get_all_shipping_methods()`（`fetch.py:139-190`）在 `allow_sync_webhooks=True` 时调用 `manager.list_shipping_methods_for_checkout` 与 `manager.excluded_shipping_methods_for_checkout` 获得，与 `checkoutComplete` 完全同源。

  **返回结构**。`type CheckoutDeliveryOptions{availableDeliveryOptions: [DeliveryOption!]!, selectedDeliveryOptionId: ID, isSelectedDeliveryOptionAvailable: Boolean}`，`type DeliveryOption{id: ID!, deliveryMethod: DeliveryMethod, name: String!, price: Money, message: String}`（`DeliveryMethod` 复用 `saleor/graphql/checkout/types.py:588-604` 的 union）。可空语义：`selectedDeliveryOptionId` 与 `isSelectedDeliveryOptionAvailable` 在结账尚无有效选择时均为 `null`（三态：无选择 / 选择仍可用 / 选择已失效），`deliveryMethod` 仅在底层方法无法映射到 union 成员时为 `null`。以 `target-schema.graphql` 为准。`availableDeliveryOptions` 的每一项由 `CheckoutInfo.valid_delivery_methods` 逐项转换：内置 `ShippingMethodData` 用 `graphql_id`（`shipping/interface.py:49-54`，`ShippingMethod:<pk>`），pick-up 点用 `Warehouse` 的 global id，外部方法保留 base64 app id（`webhook/transport/shipping_helpers.py:7-11 to_shipping_app_id`，格式 `app:<identifier>:<method_id>`）；`price` 取 `ShippingMethodData.price`，pick-up 点取 `zero_money`，`message` 取 `ShippingMethodData.message`（`initialize_shipping_method_active_status` 写入的排除原因，`shipping/utils.py:67-79`）。

  **三态配送标识兼容**。`selectedDeliveryOptionId` 与 `isSelectedDeliveryOptionAvailable` 依据 `CheckoutInfo.get_delivery_method_info()` 的返回对象判定，需同时支持：
  1. 内置 `ShippingMethod:<pk>`：`delivery_method_order_field = {"shipping_method_id": int(...)}`，`is_valid_delivery_method()` 要求存在 `shipping_address`（`ShippingMethodInfo`，`fetch.py:341-364`）。
  2. 外部 base64 app id：`ShippingMethodData.is_external` 为真（`shipping/interface.py:37-47`），`id` 为 base64 串；当旧格式 `app:<pk>:<method_id>` 时需要 `convert_to_app_id_with_identifier`（`shipping_helpers.py:14-32`）归一化后与 `get_all_shipping_methods()` 的 id 比对（`fetch.py:247-262`）。
  3. `Warehouse:<uuid>`：`CollectionPointInfo`，`is_valid_delivery_method()` 要求 shipping_address 等于仓库地址（`fetch.py:367-408`）。

  判定逻辑：`selected = get_delivery_method_info()`；`selected_id` 为该对象对应 global id（`None` 当无选择）；`is_available = selected.is_method_in_valid_methods(checkout_info)`（`fetch.py:334-335,404-408`）。若 `selected_id` 不在 `valid_delivery_methods` 中，则 `selectedDeliveryOptionId` 按 AC-01-4 返回空或明确标识不可用，且**不**出现在 `availableDeliveryOptions` 中。

  **失败语义（不覆盖有效选择）**。mutation 全程只读：计算阶段不调用 `checkout.save()`，不写 `shipping_method_name`/`undiscounted_base_shipping_price_amount`/`last_change`。注意 `get_delivery_method_info()` 会通过 `_update_denormalized_shipping_method_fields`（`fetch.py:202-227`）写回 `shipping_method_name` 与 `undiscounted_base_shipping_price_amount`——为避免重算副作用，新 mutation 在调用前设置 `checkout_info.allow_sync_webhooks` 保持默认但**不**触发该写回路径：具体做法是在新代码中调用 `get_delivery_method_info()` 后丢弃写回（或复用现有 `get_delivery_method_info`，接受其仅同步去规范化字段）；设计约定：重算失败（地址缺失/配送服务报错/结账不存在）时抛 `ValidationError`，由 `BaseMutation` 转换为 `errors`，DB 不产生新的配送选择写入。失败分支：
  - 地址缺失/字段不完整：`errors=[{field: "shippingAddress", code: "SHIPPING_ADDRESS_NOT_SET", message: ...}]`（复用 `CheckoutErrorCode.SHIPPING_ADDRESS_NOT_SET`，`checkout/error_codes.py:17`）。
  - 同步配送服务报错：`errors=[{field: "deliveryOptions", code: "DELIVERY_OPTIONS_SERVICE_ERROR", message: ...}]`（新增，见 I01/I02）。
  - 结账不存在：`get_checkout(...)` 抛 `NOT_FOUND`，响应不包含其他结账的配送信息（AC-01-7）。

  新增错误码（`saleor/checkout/error_codes.py` 的 `CheckoutErrorCode`）：`DELIVERY_METHOD_NOT_FOUND = "delivery_method_not_found"`、`DELIVERY_OPTIONS_SERVICE_ERROR = "delivery_options_service_error"`；并在 `saleor/graphql/core/enums.py` 的 `CheckoutErrorCode` GraphQL enum 自动同步（该 enum 由 `graphene.Enum.from_enum` 生成）。复用既有 `SHIPPING_METHOD_NOT_SET`、`DELIVERY_METHOD_NOT_APPLICABLE`、`SHIPPING_ADDRESS_NOT_SET`。

  **不破坏既有读取语义**。`Checkout.shippingMethods`（`graphql/checkout/types.py:699-719`）、`Checkout.deliveryMethod`（795-814）、已弃用的 `availableShippingMethods`（677-698）保持原 resolver 与弃用 reason 不变；本单元不修改这些字段。

  **迁移**：无（纯读路径）。

### BD02 · 配送方式更新与完成结账的有效性复核
- 覆盖需求：R02
- 设计说明：

  **统一复核入口**。在 `saleor/checkout/checkout_cleaner.py` 的 `clean_checkout_shipping`（24-63）之外，新增供 `checkoutDeliveryMethodUpdate`/`checkoutComplete`/已弃用 `checkoutShippingMethodUpdate` 共用的复核函数 `revalidate_delivery_method(checkout_info, lines, error_code)`，落点 `saleor/checkout/checkout_cleaner.py`。它基于当前结账事实重算 `checkout_info.valid_delivery_methods` 并给出**可区分**的失效原因：

  | 情形 | 字段 | code | 处理 |
  | --- | --- | --- | --- |
  | 需配送但未设置方式 | `shipping_method` | `SHIPPING_METHOD_NOT_SET` | 阻止完成/更新 |
  | 已设置但地址无效（`is_valid_delivery_method` 为假） | `shipping_address` | `SHIPPING_ADDRESS_NOT_SET` | 阻止 |
  | 已设置但不在 `valid_delivery_methods`（`is_method_in_valid_methods` 为假） | `shipping_method` | `DELIVERY_METHOD_NOT_APPLICABLE` | 清除选择并阻止 |
  | 标识归属不属于该结账 | `delivery_method_id` | `DELIVERY_METHOD_NOT_FOUND` | 拒绝且不改动原选择 |

  第 3 行沿用既有 `clean_checkout_shipping` 的 `clear_delivery_method(checkout_info)` 行为（`checkout_cleaner.py:54-63`，同时调用 `saleor/checkout/utils.py:1040-1062`），保证「失效选择被清除」的一致语义。

  **归属校验**。`CheckoutDeliveryMethodUpdate.get_delivery_method_data`（`checkout_delivery_method_update.py:204-240`）已按 `_resolve_delivery_method_type`（183-202）区分 `Warehouse`/`ShippingMethod`/`APP_ID_PREFIX` 三类，并通过 `clean_delivery_method`（`mutations/utils.py:75-96`）验证。需补充：当解析到的方法不属于当前结账（内置方法无该渠道 listing、外部方法经 `manager.get_shipping_method` 返回 `None`、warehouse 不是有效 pick-up 点）时，返回 `DELIVERY_METHOD_NOT_FOUND` 而非笼统的 `NOT_FOUND`/`INVALID`，且**不写入**任何选择（当前 `assign_delivery_method_to_checkout` 只在通过校验后调用，保持）。

  **完成结账复核**。`checkoutComplete`（`graphql/checkout/mutations/checkout_complete.py:225-346`）当前在 `validate_checkout_addresses`（170-223）内调用 `clean_checkout_shipping`（188）。设计调整为：完成路径在 `complete_checkout`（`checkout/complete_checkout.py:1674-1750`）内部对 `is_automatic_completion=False` 与 `True` 都执行一次 `revalidate_delivery_method`，确保「提交前失效 → 失败且不创建订单」（AC-02-2、AC-02-7）。失败时不进入 `complete_checkout_with_payment`/`complete_checkout_with_transaction` 的写路径，不产生 `Payment`/`TransactionItem`/`Order`/库存预留副作用；结账保持可重试（`completing_started_at` 不被置位超过既有超时窗口）。

  **旧路径兼容**。`checkoutShippingMethodUpdate`（`graphql/checkout/mutations/checkout_shipping_method_update.py`）保留弃用但继续可读：其 `_check_delivery_method`（105-120）改用同一 `revalidate_delivery_method`，最终落库字段（`shipping_method`/`shipping_method_name`）与 `checkoutDeliveryMethodUpdate` 完全一致（AC-02-5）；`Checkout.shippingMethod`（`graphql/checkout/types.py:774-794`）保留弃用读取。

  **权限与不泄露**。两个 mutation 的 `get_checkout` 已做 scoping；无权限/不归属时抛权限或 `NOT_FOUND`，响应不包含该结账配送信息（AC-02-6）。

  **迁移**：无。

### BD03 · 渠道-仓库直连库存语义与既有行为保留
- 覆盖需求：R03
- 设计说明：

  **开关与两种库存来源**。新增渠道级字段 `Channel.use_channel_warehouses_for_stock`（`saleor/channel/models.py`，`BooleanField(default=False)`），GraphQL 暴露为 `type StockSettings{allocationStrategy, useChannelWarehousesForStock}` 与 `input StockSettingsInput{allocationStrategy, useChannelWarehousesForStock}`（当前 `StockSettings` 仅含 `allocationStrategy`，`graphql/channel/types.py:52`、`graphql/channel/mutations/channel_create.py:45`）。语义：
  - `use_channel_warehouses_for_stock=false`（默认，未切换）：沿用既有「配送区域 + 地址」库存行为，即 `WarehouseQueryset.for_channel_with_active_shipping_zone_or_cc`（`warehouse/models.py:54-85`）与 `for_country_and_channel`（87-114）通过 `Channel.shipping_zones.through` / `ShippingZone.warehouses.through` 关联仓库。升级后未改设置不变（AC-03-1）。
  - `use_channel_warehouses_for_stock=true`：仅 `Warehouse.channels`（through `ChannelWarehouse`，`warehouse/models.py:265-293`）直接关联当前渠道的仓库参与可售与预留；未直接关联的仓库即使有库存也不计入（AC-03-2）。旧地址参数仍被接受但**非决定性**：`checkoutShippingAddressUpdate` 等仍可传地址，计算时忽略其影响的仓库集合（AC-03-4）。

  **单一解析点**。在 `saleor/warehouse/models.py` 新增 `WarehouseQueryset.for_channel_stock_source(channel, channel_slug_or_obj)`（或等价命名），统一返回「参与可售/预留的仓库 queryset」，内部分支取决于 `channel.use_channel_warehouses_for_stock`。以下入口全部改为调用该单一解析，替换各自的仓库集合来源：
  - 商品查询可售量：`saleor/product/managers.py:266-286` 的 `annotate_quantities`（`=Sum(stock.quantity)`）需按该解析限定 `stock__warehouse__in`；`saleor/graphql/product/filters/product_helpers.py:119-121 filter_products_by_stock_availability` 的 `Warehouse.objects.for_channel_with_active_shipping_zone_or_cc(channel_slug)` 改为该解析（AC-03-3）。
  - 结账可用性/预留：`saleor/warehouse/availability.py:141-186 check_stock_and_preorder_quantity_bulk`、`521-534 get_available_quantity`；`saleor/checkout/complete_checkout.py:558-638 _create_lines_for_order`（`additional_warehouse_lookup`）与 `822-841 allocate_stocks/allocate_preorders`。
  - 订单/履约/草稿订单：履约分配走 `saleor/order/`（`allocate_stocks` 调用点）与 draft order 的 `saleor/graphql/order/mutations/` 分配路径，均改为传入同一解析结果。设计约定：所有入口通过同一 helper 获得 warehouse queryset，避免「各算一套」。

  **一致性与预留保证**。可售量以 `StockQuerySet.annotate_available_quantity`（`warehouse/models.py:330-346`，`quantity - Coalesce(Subquery(sum(allocations.quantity_allocated)),0)`）为唯一事实。预留失败抛 `InsufficientStock`（`core/exceptions.py`），路由到既有 `INSUFFICIENT_STOCK`/`AVAILABLE_QUANTITY` 错误，不产生部分预留（依赖 `allocate_stocks` 的事务）；并发下 `select_for_update` 与 allocation 唯一约束保证不超卖（AC-03-6）。仓库关系变更立即生效（不缓存 warehouse queryset，AC-03-5），已完成预留不受影响（allocation 行持久化）。

  **权限**。仓库/渠道读取沿用现有权限（AC-03-7）。切换开关需 `MANAGE_CHANNELS`/`MANAGE_CHANNEL_SETTINGS`（沿用 channel mutation 权限，见 BD06）。

  **迁移**：`saleor/channel/migrations/00XX_channel_use_channel_warehouses_for_stock.py`（`AddField`，默认 `False`）。

### BD04 · 商品按渠道可售性诊断
- 覆盖需求：R04
- 设计说明：

  **落点**。新增 `Product.channelAvailabilityDiagnostics(filter, sortBy, before, after, first, last)`（接口 I04），resolver 落点 `saleor/graphql/product/types/products.py`（紧随 `resolve_is_available`，1312-1359）；聚合算法落点新文件 `saleor/product/utils/diagnostics.py`，参照三态先例 `saleor/checkout/problems.py`（union/dataclass 问题模型）与 GraphQL union `CheckoutProblem`（`graphql/checkout/types.py:243-257`）。GraphQL 新增类型 `ProductChannelAvailabilityDiagnostics{channel, currency, problems: [ProductChannelAvailabilityDiagnosticsProblem!]!, problemCount, severitySummary}`、问题 union 与 `enum ProductChannelAvailabilityProblemTypeEnum`、`enum ProductChannelAvailabilityProblemSeverityEnum`。

  **聚合算法**（对给定商品在其所有渠道 listing 上逐项判定）。输入事实：
  1. 发布/可购买时间：`ProductChannelListing`（`product/models.py:303-345`）的 `is_published`、`published_at`（继承自 `PublishableModel`，`core/models.py:63-77`）、`available_for_purchase_at`、`is_available_for_purchase()`（`models.py:340-344`）。
  2. 商品与变体库存：`ProductVariantChannelListing`（`product/models.py:492-520`，`price_amount`）、`StockQuerySet.annotate_available_quantity`（`warehouse/models.py:330-346`）。
  3. 仓库关联：BD03 的库存来源解析（direct 或 shipping-zone）。
  4. 配送区域：`ShippingZone.countries`（`shipping/models.py:87-92`）与 `ShippingMethodQueryset.applicable_shipping_methods`（`shipping/models.py:140+`，`shipping_zone__countries__contains=country_code`）。
  5. 是否需配送：`ProductType.is_shipping_required`；数字商品跳过且**仅**跳过配送区域检查（AC-04-4）。

  **分级判定表**：

  | 检查项 | 条件 | 严重度 | 说明 |
  | --- | --- | --- | --- |
  | 发布状态 | `is_published is False` | blocker | 阻断，且不再把因此产生的库存/配送依赖重复报为错误（AC-04-2） |
  | 可购买时间 | `available_for_purchase_at > now` | blocker | 同上 |
  | 渠道 listing | `ProductChannelListing` 缺失或 `is_available_for_purchase()` 为假 | blocker | |
  | 变体价格 | 所有 `ProductVariantChannelListing.price_amount` 为空 | blocker | |
  | 库存 | 变体 `available_quantity = 0` 或低于阈值 | warning | 未发布时不重复报错 |
  | 仓库关联 | 无仓库直接关联渠道（direct 模式） | warning | 仅在发布且可购买时有意义 |
  | 配送区域 | 需配送但存在未覆盖国家且无可用配送方式 | blocker（需配送） | 数字商品 not-applicable |

  优先级规则：一个渠道若已由发布/可购买时间判定为 blocker，则其库存与配送依赖结果标记为 `not-applicable` 而非 `warning`/`blocker`，避免「正常依赖淹没实际问题」（AC-04-2、AC-04-3）。`severitySummary` 分别给出 blocker/warning/not-applicable 计数，与明细条目一致（AC-04-1）。

  **筛选与分页**。`filter` 支持按 `channel`（名称/slug）与 `currency`；`sortBy` 复用现有排序枚举风格；分页沿用 `graphql/core/connection.py` 的 `CountableConnection`（709-728）稳定游标；`problemCount` 与 `problems` 长度一致、分页稳定（AC-04-1）。

  **权限**。`Product.channelAvailabilityDiagnostics` 标注 `MANAGE_PRODUCTS`/`MANAGE_CHANNELS` 之一；无权员工看不到受限字段明细，错误信息不含受限数据（AC-04-5）。

  **失败语义**。诊断查询异常返回可重试错误（`errors`/GraphQL error），不返回空结果冒充成功（AC-04-6）；编辑中旧结果不覆盖编辑内容属前端（FD01）职责，后端保证每次请求返回当下的服务端事实、不缓存。数字商品跳过配送区域检查但库存/发布/核心条件仍判定（AC-04-4）。

  **迁移**：无（纯读聚合）。

### BD05 · 已支付结账自动完成的资格条件与幂等
- 覆盖需求：R05
- 设计说明：

  **现状与落点**。基线已有 `Channel.automatically_complete_fully_paid_checkouts`（`channel/models.py:50`）与单结账任务 `automatic_checkout_completion_task`（`checkout/tasks.py:128-227`），由 `saleor/checkout/actions.py:272-337 _transaction_amounts_for_checkout_updated` 在 authorize 状态转入 FULL 时 `.delay(...)` 触发；任务调用 `complete_checkout(..., is_automatic_completion=True)`（`checkout/complete_checkout.py:1674-1750`）。本单元在此之上补齐**批量准入扫描 + 逐项复核 + 幂等**，并明确状态可诊断。

  **资格谓词**（`automatic_completion_eligible(checkout_info, lines, manager) -> EligibilityResult`，落点 `saleor/checkout/actions.py` 附近或新 `saleor/checkout/automatic_completion.py`）：
  1. **fully paid**：`CheckoutChargeStatus.FULL/OVERCHARGED`（Transaction 路径，`checkout/payment_utils.py:16-119`）或 legacy `is_fully_paid`（`checkout/utils.py:1065-1089`，Payment 路径且 `is_active`）；完整授权（`CheckoutAuthorizeStatus.FULL`）按对应支付方式约定处理（AC-05-2、PRD Q5）。两路径不可混算（见 BD08 不重复计入口径）。
  2. 存在客户或邮箱：`checkout_info.get_customer_email()`（`fetch.py:298-303`）非空。
  3. 账单地址：`checkout_info.billing_address` 非空。
  4. 需配送时：具备 `shipping_address` 与有效配送方式（复用 BD02 的 `revalidate_delivery_method`）。
  5. 商品可售：`unavailable_variant_pks` 为空（`fetch_checkout_lines`）。
  6. 总额大于零：`checkout_total.gross.amount > 0`。

  任一不满足则不创建订单，并留下**可诊断原因**（写入结账 metadata 键 `automatic_completion.last_error` 或专用诊断字段，含原因码与时间；不改动金额与支付）。

  **批量扫描 + 逐项复核**。新增周期性任务（Celery beat，落点 `saleor/checkout/tasks.py`：`automatic_checkout_completion_scan_task`），按渠道分组，仅处理 `channel.automatically_complete_fully_paid_checkouts=True` 且满足 BD06 延迟/cutoff 的结账；分批（沿用既有批大小常量，不新增数值，PRD Q1–Q8）读取候选。**任务只负责入队/调度**，真正完成前在 `automatic_checkout_completion_task` 内用最新 `CheckoutInfo` 重新执行资格谓词：库存、配送或支付失效时拒绝成单（AC-05-5）。单结账失败（`ValidationError`/`InsufficientStock`）不影响同批次其他结账（AC-05-8），与现有任务的异常处理（warn/不重试 vs `IntegrityError`/`DatabaseError` 重试）一致。

  **幂等**。既有关键设计（任务在 `select_for_update` 事务内完成，见 `complete_checkout_with_payment`，1798-1927；`complete_checkout` 返回已存在订单时短路）。加固：
  - **单订单结果**：完成前校验 `Order.objects.get_by_checkout_token(checkout.token)`，若已存在则直接返回该订单、不重复成单（AC-05-4）。`checkoutComplete` 已有此短路（`checkout_complete.py:245-276`），自动完成任务复用同逻辑。
  - **无重复扣款/通知**：`complete_checkout_with_payment` 的 `payment_refund_or_void`、`NOTIFY_USER`/`ORDER_CREATED` 事件在短路分支不触发（AC-05-6）。
  - **不改已完成订单金额**：短路分支不触碰已存在订单的金额与 `Payment`/`TransactionItem`（AC-05-7）。
  - 乐观并发：完成事务对 checkout `select_for_update`，与手动 `checkoutComplete` 互斥，二次尝试读到已完成 checkout 而短路。

  **可诊断、可重试状态**。失败保留 `automatic_completion` 的尝试记录（时间、原因、尝试者），条件修复后重试仍只形成一个订单（AC-05-3、AC-05-6）；重试不重置金额与支付记录。

  **迁移**：`saleor/checkout/migrations/00XX_checkout_automatic_completion_state.py`（如需持久化诊断状态字段，`AddField`；若采用 metadata 承载则无迁移）。

### BD06 · 自动完成策略的按渠道配置与状态呈现
- 覆盖需求：R06
- 设计说明：

  **配置模型**。在 `Channel` 上新增：`automatic_completion_delay`（`models.DurationField(null=True, blank=True)`，允许空表示未配置）、`automatic_completion_cutoff_date`（`models.DateTimeField(null=True, blank=True)`）、以及记录设置变更的 `checkout_settings_updated_at`（`models.DateTimeField(null=True, blank=True)`，用于乐观并发）。既有 `automatically_complete_fully_paid_checkouts`（`channel/models.py:50`）作为总开关。GraphQL：`type CheckoutSettings{useLegacyErrorFlow, automaticallyCompleteFullyPaidCheckouts, automaticCompletionDelay: Minute, automaticCompletionCutoffDate: DateTime, updatedAt: DateTime}`（现类型仅前两项，`graphql/channel/types.py:66-98`）；`input CheckoutSettingsInput{..., automaticCompletionDelay: Minute, automaticCompletionCutoffDate: DateTime, expectedUpdatedAt: DateTime}`（现 `graphql/channel/mutations/channel_create.py:58-88`）。`updatedAt` 以 `Minute`/`DateTime` 暴露既有标量，不新增数值约定。

  **语义**。
  - **延迟**：自结账**最近一次变化**（`Checkout.last_change`）起算，仅当 `now - last_change > automatic_completion_delay` 才进入待处理范围（AC-06-2）。延迟为 `Null`/未配置时沿用关闭或既有默认（PRD Q4、AC-06-8）。
  - **cutoff**：`automatic_completion_cutoff_date` 是结账**创建时间**（`Checkout.created_at`）的**下界**，只考虑 `created_at >= cutoff` 的结账；它不是任务停止执行时间，cutoff 之后新建的结账仍被处理（AC-06-3）。这与 `PaymentSettings.checkoutReleaseFundsCutOffDate`（`graphql/channel/types.py:5448-5455`）语义不同，需在字段描述中显式区分。
  - **未配置渠道**：`automatically_complete_fully_paid_checkouts=False` 时不扫描、不改变历史手工流程（AC-06-1、AC-06-8）。

  **校验与错误**。在 `saleor/graphql/channel/mutations/utils.py:108-118 clean_input_checkout_settings` 补校验：延迟为负（`automaticCompletionDelay < 0`）或 cutoff 与适用范围组合非法时，抛 `ValidationError`，`code=ChannelErrorCode.INVALID`（`channel/error_codes.py`），并**保留上次生效值**（AC-06-4）。`Minute`/`Hour`/`Day` 标量本身拒绝负值（BD18）。新增 `ChannelErrorCode.CHECKOUT_SETTINGS_OUTDATED = "checkout_settings_outdated"`（接口 I05）用于保存冲突。

  **乐观并发**。保存时携带 `expectedUpdatedAt`；若与库中 `checkout_settings_updated_at` 不一致，抛 `CHECKOUT_SETTINGS_OUTDATED`，不写入（AC-06-6、AC-06-4）。保存成功后更新 `checkout_settings_updated_at`（AC-06-1，合法值可保存并重读）。

  **权限**。`channelUpdate` 修改 `checkoutSettings` 需要 `MANAGE_CHANNELS`/`MANAGE_CHECKOUTS`（沿用 schema 描述 `graphql/schema.graphql:18686` 既有提示）；无权限的身份不能保存，现有配置不变（AC-06-5）。

  **设置状态 ≠ 执行结果**。`CheckoutSettings`/`updatedAt` 只反映**设置状态**；后端不在保存响应中宣称订单已生成；订单是否存在以结账状态与订单实际存在为准（AC-06-7）。后端不新增「已生成」字段。

  **迁移**：`saleor/channel/migrations/00XX_channel_automatic_completion_settings.py`（`AddField`：delay、cutoff、updated_at）。

### BD07 · 礼品卡统一支付生命周期
- 覆盖需求：R07, R08
- 设计说明：

  **模型变更**。
  - `TransactionItem`（`payment/models.py:31-191`）新增 `gift_card = models.ForeignKey("giftcard.GiftCard", null=True, blank=True, on_delete=models.SET_NULL, related_name="transactions")`；`TransactionEvent`（194-254）新增 `gift_card = models.ForeignKey("giftcard.GiftCard", null=True, blank=True, on_delete=models.SET_NULL, related_name="events")`，用于把授权/取消/扣款/退款事件归到具体礼品卡。
  - `GiftCard`（`giftcard/models.py:45-151`）新增 `reserved_balance_amount`（`MoneyField`，默认 0）→ 属性 `reserved_balance`；派生 `available_balance = current_balance - reserved_balance`（`availableBalance`）。`currentBalance`（107-113）保持既有含义。
  - `GiftCardEvents`（常量类在 `giftcard/__init__.py:9-38`，非 `giftcard/events.py`）新增 `AUTHORIZED`、`AUTHORIZATION_RELEASED`、`REFUNDED`，并同步 `graphql/core/enums.py` 的 `GiftCardEventsEnum`（基线 `graphql/schema.graphql:10838-10852`）。

  **授权 → 扣款 → 退款生命周期**。新增 mutation `checkoutGiftCardPaymentCreate`、`checkoutGiftCardPaymentCancel`（接口 I06），落点 `saleor/graphql/payment/mutations/transaction/`（沿用现有 transaction mutation 目录）。流程：
  1. **校验**：礼品卡存在、`is_active`、未过期（`expiry_date` 与当前日期比较，参照 `checkout_cleaner.py:111-121 _validate_gift_cards` 的 active 判定）、币种等于结账/订单币种、`available_balance >= amount`。任一不满足返回可识别错误（`GIFT_CARD_NOT_APPLICABLE`，既有；或新增礼品卡支付专属码），**不修改余额与支付状态**（AC-07-2/3/4），**不改走普通支付**（AC-07-3）。
  2. **授权**：创建 `TransactionItem`（`paymentMethodDetails = GiftCardPaymentMethodDetails`，见下），设置 `amount_authorized`，礼品卡 `reserved_balance += amount`，事件 `AUTHORIZED`（AC-07-1）。
  3. **扣款**：`charge` 时 `amount_charged += amount`、`current_balance -= amount`、`reserved_balance -= amount`（AC-07-1）；结账/订单支付状态经 `update_checkout_payment_statuses`（`checkout/payment_utils.py:82-119`）或订单侧 `update_order_charge_data`（`order/utils.py:1084`）刷新。
  4. **退款**：`GiftCardPaymentMethodDetails` 的退款受可退余额约束（AC-08-2/3），退款事件 `REFUNDED`，礼品卡 `current_balance += amount`。

  **金额与余额不变量**：`current_balance >= 0`、`reserved_balance >= 0`、`available_balance >= 0`；扣款受 `amount_authorized` 限制；退款受可退余额（已扣款减已退款）限制。

  **`GiftCardPaymentMethodDetails`**。新增 `type GiftCardPaymentMethodDetails implements PaymentMethodDetails{name, ...}`（`interface PaymentMethodDetails` 在 `graphql/schema.graphql:12614`；现有实现 `CardPaymentMethodDetails:34825`、`OtherPaymentMethodDetails:34850`），`TransactionItem.paymentMethodDetails`（11008）返回它，`TransactionItem.giftCard` 暴露关联礼品卡。

  **幂等**。幂等键 = `(checkout|order, gift_card, amount)`：同一结账/订单对同一礼品卡同一金额的重复请求只形成一次有效授权或扣款、一次余额变化（AC-07-6）。实现：以 `TransactionItem.idempotency_key`（模型已有 `unique_transaction_idempotency` 约束，`payment/models.py:191` 附近）承载，先查后建，命中则返回既有结果。

  **权限**。`PaymentPermissions.HANDLE_PAYMENTS`（`transaction/transaction_request_action.py:81`、`transaction/transaction_create.py:121`）；无权限调用方不能使用礼品卡支付，错误不泄露余额（AC-07-5）。

  **legacy promo code 路径**。`checkoutAddPromoCode`（`graphql/checkout/mutations/checkout_add_promo_code.py`）当前经 `add_promo_code_to_checkout`（`checkout/utils.py:805`）走礼品卡分支 `add_gift_card_code_to_checkout`（`giftcard/utils.py:36-56`）。设计：礼品卡分支**拒绝**并返回替代路径错误（指向 `checkoutGiftCardPaymentCreate`），不再新增 `checkout.gift_cards` 关联作为抵扣。`Checkout.giftCards`（`graphql/checkout/types.py:737-741`）与 `Order.giftCards`（`graphql/schema.graphql:11324`）保持**可读且弃用**（`@deprecated(reason: "Use gift card transactions ...")`），历史订单/结账仍可解释（AC-07-7、AC-08-5）。

  **对账一致**。取消授权 `checkoutGiftCardPaymentCancel` 后授权状态与可用余额恢复（`reserved_balance -= amount`、事件 `AUTHORIZATION_RELEASED`），交易事件、礼品卡余额、结账支付状态反映同一结果（AC-08-1/4）；无事件时返回空事件列表而非请求失败（AC-08-7）。

  **迁移**：`saleor/payment/migrations/00XX_transactionitem_transactionevent_gift_card.py`（`AddField` 两个 FK）、`saleor/giftcard/migrations/00XX_giftcard_reserved_balance.py`（`AddField reserved_balance_amount`，默认 0）。

### BD08 · 订单金额分解与人工资金动作边界
- 覆盖需求：R09, R10
- 设计说明：

  **金额分解一致性**。订单明细分解需分别呈现商品、折扣、税费、配送、礼品卡、已授权、已扣款、已退款、剩余待付，并对 Payment 与 Transaction 两条路径都成立（AC-09-1/5）。落点：
  - 已授权/已扣款/已退款/剩余：复用 `order/types.py:2254-2325`（`resolve_total_authorized`/`resolve_total_charged`/`resolve_total_balance`）与 `2827+`（`resolve_total_refunded` + pending resolvers），口径统一为「Transaction 路径取 `TransactionItem.amount_*`，legacy 路径取 `Payment`/`get_total_authorized`（`payment/model_helpers.py:12-20`）」，禁止同一笔金额被两条路径重复计入（AC-09-3）。
  - 新增 `Order.totalGiftCard`（接口 I07）：等于该订单礼品卡类交易的有效扣款/授权合计（来自 BD07 的 `TransactionItem`，`paymentMethodDetails` 为 `GiftCardPaymentMethodDetails`），**只计一次**，不叠加到普通支付（AC-09-4）。
  - 剩余待付 = 应付金额 − 已有效支付金额；为零时显示已结清（AC-09-6）。`total_balance`（`order/models.py:536-538`，`total_charged - total.gross`）需纳入礼品卡扣款口径。
  - Dashboard 展示各异（FD08）须与服务端逐一一致（AC-09-2）：服务端为唯一事实来源，resolver 不返回近似值。

  多交易汇总：按「有效事件」去重（`TransactionEvent.include_in_calculations`，`payment/models.py:233`），已使用额度不重复占用。

  **人工资金动作边界**。动作 `orderMarkAsPaid`/`orderCapture`/`orderRefund`/`transactionRequestAction`（`OrderAction` 枚举 `graphql/schema.graphql:11800-11812`、`TransactionActionEnum:11133`）：
  - **展示/执行门控**：`Order.actions`（`order/types.py:2167-2184`）与 `TransactionItem.actions`（11051）按**当前支付方式与订单状态**产出允许动作；不允许的动作不出现（AC-10-1）。
  - **金额非负**：所有金额入参拒绝负值（`PositiveDecimal`/`NonNegativeDecimal` 标量 + resolver 校验），返回 `field`/`code`（AC-10-2）。
  - **标记已支付**：存在支付或交易记录时禁止；无记录且满足条件时可用（AC-10-3，`order/models.py:can_mark_as_paid`）。
  - **捕获**：`amount <= capturable authorization`；等于边界成功，超过拒绝且订单/支付状态不变（AC-10-4）。capturable 取当前真实授权余额。
  - **退款**：`amount <= refundable balance`；等于可退余额成功，超过拒绝，多笔交易不重复占用同一额度（AC-10-5）。
  - **幂等**：资金动作以最新对象状态做幂等检查；重复提交只产生一次扣款/退款与一组事件（AC-10-6）。落点：`order/utils.py:1045-1176`（`update_order_charge_status`/`update_order_charge_data`/`update_order_authorize_data`）在事务内 `select_for_update`；`payment/utils.py:1647-1812`（手动调整事件 helper：`prepare_manual_event`、`create_manual_adjustment_events`）。
  - **失败原子**：失败保留原状态，`order/utils.py` 与 payment 事件写在一个事务，失败回滚，错误可区分（AC-10-7）。
  - **成功刷新**：成功后返回刷新后的订单、`TransactionEvent` 与余额（AC-10-8）。
  - **权限**：`OrderPermissions.MANAGE_ORDERS`（`order_mark_as_paid.py:47`、`order_capture.py:51`、`order_refund.py:64`）；无权限不操作且错误不泄露受限金额（AC-10-9）。

  **迁移**：无（`totalGiftCard` 为 resolver 派生；如为性能在 `Order` 增加 denormalized 字段则 `saleor/order/migrations/00XX_order_total_gift_card.py`）。设计优先 resolver 派生。

### BD09 · 交易基础检索
- 覆盖需求：R11
- 设计说明：

  **新增根级字段**。`Query.transactions(where, before, after, first, last): TransactionItemCountableConnection`（接口 I08），落点 `saleor/graphql/payment/schema.py`（与单条 `transaction` 同级，`schema.py:66-91`），resolver 复用 `TransactionItem` 类型（`graphql/payment/types.py:541-728`）。`input TransactionWhereInput{ids, orderId, checkoutId, pspReference, appId}`；类型 `TransactionItemCountableConnection/TransactionItemCountableEdge` 沿用 `graphql/core/connection.py:709-728` 的 `CountableConnection`。

  **过滤语义**：按订单/结账关联、交易 ID、`pspReference`、`appId` 定位；礼品卡、普通支付与多交易订单都能定位（AC-11-1/2/3/4）。多交易返回全部相关交易且稳定。

  **字段**：返回订单金额、支付方式（`paymentMethodDetails`）、状态与事件展示所需字段（AC-11-5，复用 `TransactionItem` 既有字段）。

  **权限与范围**：客户、员工、App 只能看到自身可见范围；客户仅见自己订单/结账的交易，App 仅见自身 `appId` 或可见渠道，员工按 `HANDLE_PAYMENTS` + 对象范围；越权查询不泄露详情（AC-11-6）。权限失败返回权限错误而非空列表（AC-11-7/8 语义）。

  **分页/参数稳定错误**：空分页项、越界分页、错误过滤类型返回稳定结果/稳定错误而非意外错误（AC-11-7/8）。`TransactionWhereInput` 类型校验由 `BaseInputObjectType` 完成（非法类型→GraphQL 校验错误）。

  **明确不做**：无创建/修改日期、事件类型或日期筛选；无本查询专用排序与索引（AC-11-9、spine §6、PRD 4.2）。请求这些能力时行为明确（字段不存在→GraphQL 校验错误），不静默忽略为空。

  **迁移**：无。

### BD10 · 主体搜索边界与搜索更新一致性
- 覆盖需求：R12, R13
- 设计说明：

  **保留各自搜索语义**（不新增接口）：
  - 结账：`graphql/checkout/filters.py:100 filter_checkout_search`（按支付 id / 用户邮箱姓名 `Exists`）保持。
  - 礼品卡：`giftcard/search.py:35-72`（`mark_gift_cards_search_index_as_dirty` + `update_gift_cards_search_vector` + `search_gift_cards`）保持 SearchVector。
  - 商品：`product/search.py:53-176`（`update_products_search_vector`/`search_products`）保持全文检索与 RANK 行为。
  - 订单：`order/search.py:275 search_orders`（`SearchQuery` + `SearchRank`）保持。
  - 客户/员工：`account/search.py:124 search_users`（`search_document__ilike`，空格组合词）保持**基础搜索文档**，不恢复向量/前缀/相关度/RANK（AC-12-2、AC-12-4）。
  - 页面：`graphql/page/filters.py:61 search_pages`（trigram/icontains，标题/slug/内容）保持（AC-12-3）。

  **两条更新路径**（保持现状，明确边界）：
  - 内联（同步）：订单（`update_order_search_vector` 在 order mutation 中直接调用）、用户（`prepare_user_search_document_value` 在 account mutation 中）。
  - dirty 标记 + 周期任务：商品（`search_index_dirty=True` → `product/tasks.py:299 update_products_search_vector_task`）、礼品卡（`mark_gift_cards_search_index_as_dirty` → `giftcard/tasks.py:32 update_gift_cards_search_vector_task`）。核心 `core/search_tasks.py` 任务兼作 backfill。

  **页面 → 商品引用名耦合**：`graphql/page/mutations/page_update.py:47-81` 在 `title` 变化时调用 `update_products_search_index`，对引用该页面的商品置 `search_index_dirty=True`，保证商品搜索能按新名称找到（AC-12-5）。不破坏不可回收点：修改页面仅标记商品 dirty，不直接重写商品向量。

  **异常与输入**：空关键词不触发不可控全量查询（在 filter 层对空/纯空白关键词短路并明确行为）；过长/非法输入返回校验错误或明确空态，不阻塞其他列表操作（AC-13-4/5）；搜索服务异常返回错误或空态，**不转为成功空结果**（AC-13-6）。更新遵守既有最终一致性窗口（不新增数值，PRD Q1），新值在既有窗口内可被搜到、旧值不再成为唯一结果（AC-13-1/2）。分页/重复关键词/大小写稳定（AC-13-3）。客户/员工隐私受权限保护（AC-13-7）。

  **迁移**：无（不新增 Page/User 高级搜索的专用索引、后台任务与迁移，spine §6）。

### BD11 · 密码登录策略由商店统一控制
- 覆盖需求：R16
- 设计说明：

  **枚举与配置模型**。新增 `enum PasswordLoginModeEnum{ENABLED, CUSTOMERS_ONLY, DISABLED}`（接口 I09）；`Shop.passwordLoginMode` 暴露，`ShopSettingsInput.passwordLoginMode` 可写（`graphql/shop/mutations/shop_settings_update.py:23-222`，现输入含 `enableAccountConfirmationByEmail`/`allowLoginWithoutConfirmation` 等）。持久化落点：`SiteSettings`（`site/models.py:37-70`，`allow_login_without_confirmation` 在 69 行）新增 `password_login_mode`（`CharField(choices, default=ENABLED, max_length=32)`）。

  **执行点**（同一策略，服务端统一读取）：
  - `CreateToken`（`graphql/account/mutations/authentication/create_token.py:45-113`）：`DISABLED` 抛 `PASSWORD_LOGIN_DISABLED`；`CUSTOMERS_ONLY` 且用户为员工（`user.is_staff`）抛 `PASSWORD_LOGIN_CUSTOMERS_ONLY`（AC-16-2/3/4）。
  - `SetPassword`（`set_password.py:52-85`）：`DISABLED` 拒绝设置密码。
  - `PasswordChange`（`password_change.py:19-71`）：`DISABLED` 拒绝修改。
  - `RequestPasswordReset`（`request_password_reset.py:62-106`）：`DISABLED` 拒绝重置（AC-16-5）。
  - **旧 token 路径**：`RefreshToken`（`refresh_token.py`）与 `VerifyToken`（`verify_token.py`）在 JWT owner 为密码所有者时同样受策略约束：`DISABLED` 下拒绝签发/续期（依据 user 与策略判定），返回明确原因（AC-16-5）。`core/jwt.py:19-142` 的 payload 已含用户标识，据此判定归属。

  **新错误码**：`AccountErrorCode`（`account/error_codes.py`，GraphQL enum `graphql/schema.graphql:29975+`）新增 `PASSWORD_LOGIN_DISABLED = "password_login_disabled"`、`PASSWORD_LOGIN_CUSTOMERS_ONLY = "password_login_customers_only"`。

  **权限与即时生效**：仅 `SitePermissions.MANAGE_SETTINGS`（`shop_settings_update.py:129`）可修改；保存后认证请求立即读取新值（策略读取无缓存，直接查 `SiteSettings`）（AC-16-6/7）。加载/保存失败保留上次生效值，不把未保存值当成功（AC-16-9）。外部认证独立按自身配置（AC-16-10，见 BD12）。

  **登录页/设置页**（禁用入口、稳定空态）由 FD04 承担，后端保证 `Shop.passwordLoginMode` 与 `ShopSettingsUpdate` 一致可读。

  **迁移**：`saleor/site/migrations/00XX_sitesettings_password_login_mode.py`（`AddField`，默认 `ENABLED`）。

### BD12 · 外部身份关联与 Google OIDC 离线授权
- 覆盖需求：R17
- 设计说明：

  **Google 离线授权参数**。基线在 `enable_refresh_token` 时把 `offline_access` 追加进 scope（`plugins/openid_connect/plugin.py:221-234 _get_oauth_session`），且无 `access_type`。设计：对 **Google** provider 使用授权参数 `access_type=offline`，**不**发送 `offline_access` scope（AC-17-1）；其他 provider 按其自身合同处理，不套用 Google 参数（AC-17-2）。落点：`_get_oauth_session`（221-234）与 `external_authentication_url`（343-371）按 provider 区分构造 `authorization_url` 参数；provider 识别依据插件配置的 `authorization_url`/`token_url`/`json_url` 或显式配置项。

  **失败可识别 + 不泄露**：授权失败返回可识别错误；错误响应、日志与前端不必要持久化中不含 token 或敏感身份信息（AC-17-3）。落点 `plugin.py:244 external_obtain_access_tokens` 的异常路径与 `utils.py` 的 token 解析；不把原始 id/access/refresh token 放入 `errors[].message`。

  **首次关联清理旧密码通道**：`get_or_create_user_from_payload`（`utils.py:391`，keyed on `oidc:<authorization_url>` 私有 metadata `sub`，回退 email）在**首次**把 OIDC 身份关联到已存在的本地用户（邮箱已存在）时，清理/禁用可绕过外部身份策略的旧密码路径（例如清除可用密码、标记需走外部认证），使旧密码不再成为后门（AC-17-4、BC-017）。

  **稳定身份**：同一 OIDC 身份后续登录按 `sub` 命中同一用户，不重复创建（AC-17-5）。落点 `utils.py:541 get_user_from_token`、`553 is_owner_of_token_valid`、`561 create_tokens_from_oauth_payload`；身份键不依赖每次变化的 token。

  **迁移**：无（如需标记「仅外部认证」可在 `User` 增加布尔字段，`saleor/account/migrations/00XX_user_...`；设计优先使用既有 `set_unusable_password` 语义，无新迁移）。

### BD13 · 富文本与外链保存前校验
- 覆盖需求：R18
- 设计说明：

  **结构校验在前，清理在后**。`clean_editor_js`（`core/utils/editorjs.py:6-153`）当前只做黑名单 URL 替换（`BLACKLISTED_URL_SCHEMES=("javascript",)`，第 8 行），无深度限制、不处理 `rel`。设计改造 `clean_editor_js` 为两阶段：
  1. **结构校验**（新，先于清理）：校验 EditorJS `blocks` 结构（合法 block 类型集合）、拒绝未知/多余字段（block/block.data 级别的白名单）、校验链接 scheme 在**允许列表**内（`http`/`https`/`mailto`/`tel` 等，替代黑名单）、校验嵌套深度不超过既有约定上限（`MAX_EDITOR_JS_DEPTH`，由实现给定常量并在错误中可定位，PRD Q3）。
  2. **清理**（后）：对通过校验的内容清理 URL 与链接属性，对新窗口外链补安全 `rel`（`rel="noopener noreferrer"`），防止 opener 控制来源页（AC-18-5）。
  校验失败抛 `ValidationError`，错误指向具体**字段/链接/深度**（AC-18-7），**不**写库（AC-18-8，`SanitizedJSONField.get_db_prep_save`，`core/db/fields.py:12-29` 在保存前调用 sanitizer，校验失败即中止）。合法富文本、嵌套列表、`http/https/mailto/tel` 链接正常保存并读回一致（AC-18-1）。

  **落点**：`clean_text_data_block`（122-154）与 `ITEM_TYPE_TO_CLEAN_FUNC_MAP`（11-15，`list`/`image`/`embed`）；富文本属性通道 `graphql/attribute/utils/type_handlers.py:573-587 RichTextAttributeHandler.clean_and_validate` 复用同一校验，字段级错误由 `pre_save_value`（580）前抛。

  **不可配置绕过**：不存在通过配置扩展协议白名单的途径（AC-18-6）——白名单为代码常量，不读设置/环境变量。

  **迁移**：无。

### BD14 · 扩展安装、查询与迁移约定
- 覆盖需求：R19
- 设计说明：

  **字段约定与弃用**。`AppExtension`（GraphQL `graphql/app/types.py:199-288`）与 `AppManifestExtension`（`graphql/app/types.py:108`，注意它是 GraphQL BaseObjectType，非 Django model）新增 `mountName: String!`、`targetName: String!`、`settings: JSON!`，并将 `mount`/`target`/`options` 标记 `@deprecated`，reason 给出替代（I10）。这使得 Core 与 Dashboard 生成客户端（`saleor-dashboard/schema.graphql:3015-3067` 已请求 `mountName`/`targetName`/`settings`）一致。数据来源：`AppExtension` 模型（`app/models.py:156-176`）的 `mount`/`target`/`http_target_method` 映射到 `mountName`/`targetName`/`settings`（`settings` 由模型 `http_target_method` 与 manifest options 组合，落点 `graphql/app/types.py` 的 `resolve_settings`，替换 `resolve_options`，280）。

  **数据迁移**。``saleor/app/migrations/00XX_appextension_settings_from_options.py``：把历史扩展的 `options`/manifest 内容迁移到 `settings` 的等价结构，保留设置内容（AC-19-1/2）；迁移幂等（按行比对，不重复写入），不丢失既有数据。迁移后历史扩展仍可查询、编辑、渲染（AC-19-2）。

  **安装校验**。`manifest_validations.py:66-460` 已校验 URL/permissions/target 与 options（`_clean_extension_options`:240、`_validate_mounts_for_widget`:269、`_clean_extensions`:291）；`installation_utils.py:213 install_app`（206-308）创建 App/AppExtension/webhook。补强：
  - 重复 `identifier` 的安装/更新拒绝，且不破坏已有扩展数据（AC-19-3）——identifier 唯一性在创建前校验。
  - 无效权限、非法 target 拒绝，不产生部分安装数据（AC-19-4，`clean_manifest_data`:143 已有，确保失败回滚/不落库）。
  - 设置无法解析时拒绝安装/更新，不写入部分数据（AC-19-5，`_clean_extension_options`:240 / pydantic 模型 `app/validators.py` 校验）。

  **可选安装信息与 token**。`AppInstallInput.appName`/`manifestUrl` 必填（I11，见 BD19）；`activateAfterInstallation`/`permissions` 可选；`tokenTargetUrl` 属**可选安装信息**（在 manifest `webhooks` 或安装配置中），缺省不使合法安装失败（AC-19-6）；不需要新建/安装 token 时不返回 token（AC-19-7，`app_install.py:19-83` 的 `token` 字段按需返回）。

  **权限**。`AppPermission.MANAGE_APPS`（`app_install.py:57`）用于安装/更新；读取仅返回调用方允许的扩展数据（AC-19-8），落点 `app/schema.py:97-189` 的 `resolve_app_extensions`/`resolve_app_extension`（148/158）按 app/渠道范围过滤。

  **迁移顺序**：schema `AddField` + 数据迁移先于 GraphQL 弃用切换；Dashboard 生成客户端在 Core schema 更新后重新生成（不手改生成文件）。

  **迁移**：`saleor/app/migrations/00XX_appextension_mount_name_target_name_settings.py`（`AddField mount_name`、`target_name`、`settings` 或复用现有列 + 数据迁移）+ `00XX_data_migrate_options_to_settings.py`。

### BD15 · Webhook 载荷构建边界与投递隔离
- 覆盖需求：R22, R23
- 设计说明：

  **同步订阅只解析选中字段**。`graphql/webhook/subscription_payload.py:165-231 generate_payload_from_subscription` 已按订阅 query 解析；需确保同步路径只解析**实际选择**的字段，不构建未请求内容（AC-22-1）。落点 `webhook/transport/synchronous/transport.py:189-433`（`trigger_webhook_sync_if_not_cached`/`create_delivery_for_subscription_sync_event`）。

  **异步载荷在任务边界构建（deferred payload）**。基线 `event_types.py:604-609` 已有 `is_deferred_payload`（如 `CHECKOUT_CREATED` 的 `is_deferred_payload: True`）。设计：订单/草稿订单/履约异步事件统一在 **Celery 任务边界**构建完整载荷，业务请求不等待完整异步载荷（AC-22-2/3）。落点 `webhook/transport/asynchronous/transport.py:88-669`（`create_deliveries_for_multiple_subscription_objects`/`trigger_webhooks_async`/`send_webhook_request_async`）；业务调用点仅登记待构建任务，`EventPayload` 由任务填充（`core/models.py:171-204`）。

  **纯异步订阅不触发无关同步 + 不额外调用**。纯异步订阅不提前触发无关同步通知，不顺带多调用未需要的税务/配送服务（AC-22-4）。落点 `plugins/webhook/plugin.py:815-1557` 的事件分发与 `webhook/event_types.py` 的 `WEBHOOK_TYPES_MAP`：仅当存在 sync 订阅时才触发 sync 路径。既有调用次数/超时/重试/熔断上限不变，不通过重复解析放大负载（AC-22-5，PRD Q2）。

  **投递隔离**。同一事件通知多 App 时，单个 delivery 失败只影响该 delivery，其他继续（AC-23-1）。`EventDelivery`（`core/models.py:206-221`）与 `EventDeliveryAttempt`（223-241）已按 webhook 独立；`webhook/transport/utils.py:333-613`（`handle_webhook_retry`/`process_failed_deliveries`/`delivery_update`）保证隔离与重试记录（AC-23-2）。

  **RETRYING 状态**。`EventDeliveryStatus`（`core/__init__.py:30-39`）新增 `RETRYING = "retrying"` 与 `CHOICES` 项；`EventDelivery.status` 与 `EventDeliveryAttempt.status`（`core/models.py:208,234`）choices 同步；GraphQL `EventDeliveryStatusEnum`（`graphql/webhook/enums.py:305-311`，schema `3263-3267`）新增 `RETRYING`（I12）。重试进行时状态置 `RETRYING` 并持久化（AC-23-4）；异步内容未生成时不显示成功（AC-23-5）。

  **单条重试权限**。`eventDeliveryRetry`（`graphql/webhook/mutations/event_delivery_retry.py:27`，`AppPermission.MANAGE_APPS`）已存在；确保具备相关 App 或业务域权限时可单条重试，无权限拒绝（AC-23-6），重试内容不超 App 可见字段边界（AC-23-7）。

  **失败告警保留**。既有 Webhook 失败告警（`AdminEmailPlugin`/`UserEmailPlugin` 通知）保留；**不**引入 App Problems 类型/字段/操作/问题列表（AC-23-8、spine §6）。

  **迁移**：`saleor/core/migrations/00XX_eventdelivery_status_retrying.py`（`AlterField` choices；如 choices 变更需迁移）。

### BD16 · 订单配送元数据快照
- 覆盖需求：R24
- 设计说明：

  **快照列**。`Order`（`order/models.py:109-185`）新增 `shipping_method_metadata = models.JSONField(default=dict, blank=True)` 与 `shipping_method_private_metadata = models.JSONField(default=dict, blank=True)`，暴露为 `Order.shippingMethodMetadata`/`Order.shippingMethodPrivateMetadata`（接口 I13）。快照内容取自创建时配送方式的 `ShippingMethodData.metadata`/`private_metadata`（`shipping/interface.py:31-32`，`shipping/utils.py:58-59 convert_to_shipping_method_data` 已填充），外部方法经 `get_external_shipping_id`（`checkout/utils.py:1278-1294`）与 BD02 的复核结果获取。

  **两条成单路径都写快照**：
  - 结账成单：`checkout/complete_checkout.py:180-228 _process_shipping_data_for_order` 在构造订单数据时加入快照字段；`756-872 _create_order` 落库。
  - 草稿订单成单：`graphql/order/mutations/draft_order_complete.py:103-147` 的 `perform_mutation` 注入快照（来源为草稿订单当前配送方式）。

  **不重写历史**：源配送方式修改/停用/删除后（`shipping_method` FK `on_delete=SET_NULL`，`order/models.py:171-177`），快照列不变（AC-24-3）。`ShippingMethodUpdateMixin`（`graphql/order/mutations/utils.py:91-106`）修改 `shipping_method_name` 时不触碰快照。

  **可见性**：public/private 分别按权限（复用 `graphql/meta/permissions.py` 的订单元数据权限），私有内容不向未授权身份泄露（AC-24-4）。

  **事件一致**：order/draft-order 相关事件载荷中的配送信息改用快照（而非实时 `shipping_method`），与订单保存一致（AC-24-5）。落点 `graphql/order/types.py:2568-2619 resolve_shipping_method` 与事件构造。

  **迁移**。`saleor/order/migrations/00XX_order_shipping_method_metadata_snapshot.py`：`AddField` 两列；数据回填按现有订单的 `shipping_method` 当前 metadata 填一次（幂等：仅当快照为空且存在 `shipping_method` 时填；无 metadata 的记录留稳定 null/空，AC-24-6）。回填不重复、不丢失、不覆盖已有快照（AC-24-6）。

### BD17 · 元数据基础读写边界
- 覆盖需求：R25
- 设计说明：

  **保留基础读写**。结账、草稿订单、订单、履约（fulfillment）继续支持基础元数据读写，沿用 `graphql/meta/` 的通用 mutation（`graphql/meta/mutations/`：`UpdateMetadata`/`UpdatePrivateMetadata`/`DeleteMetadata`/`DeletePrivateMetadata`）与 `ModelWithMetadata`（`core/models.py:80-134`）。订单详情的**行内编辑**与**订单行元数据**能力保留（`graphql/meta/resolvers.py:26-145` 的 `resolve_object_with_metadata_type`/`resolve_metadata`/`resolve_private_metadata`，以及 order 的 metadata 字段）。

  **不产生部分写入**。非法键值、权限不足或保存失败不改变原值，不部分写入（AC-25-3/4）：元数据更新在单个事务内完成，校验失败回滚；权限检查在 mutation 入口（`graphql/meta/permissions.py:305-390` 的 `PUBLIC_META_PERMISSION_MAP`/`PRIVATE_META_PERMISSION_MAP`）。

  **显式非目标**。订单、履约与仓库**不新增**独立元数据弹窗、专用路由或隐藏入口（AC-25-5、spine §6）——本单元不改动 `graphql/meta/mutations`，仅确认既有能力保留；不新增任何 metadata 专用 mutation/query/route。

  **迁移**：无。

### BD18 · 公开接口输入校验与失败语义
- 覆盖需求：R26
- 设计说明：

  **执行前校验**。数值、时间、分页、枚举、必填项与组合关系在执行前校验：
  - `Minute`/`Hour`/`Day` 标量（`graphql/core/scalars.py:202-232`）拒绝负值（AC-26-2）；`PositiveInt`（214）非正返回校验错误。
  - Federation representations：`_entities(representations: [_Any!]!)`（I14，`graphql/core/federation/schema.py:15-145`）。基线 SDL 为 `_entities(representations: [_Any]): [_Entity]`（`schema.graphql:1665`，**nullable**），且 `resolve_entities`（101）将 `representations` 作为无默认的 keyword-only 参数。设计改为 **non-null 列表、元素 non-null**：`representations` 为 null 或含 null 项时返回稳定 GraphQL 校验错误（AC-26-4）。
  - 数组空项、错误类型、越界分页：`graphql/core/connection.py:145 _validate_connection_args`、`312 create_connection_slice`、`365 _validate_slice_args` 与 `graphql/core/validators/__init__.py` 校验必填/空项/组合（AC-26-3/5）。
  - 分页越界返回稳定错误或稳定空结果，行为一致可预期（AC-26-5）。

  **可分支的失败语义**。失败响应含 `field`、`code`、`message`（`graphql/core/types/common.py:156-164` 的 `Error`；mutation 经 `graphql/core/mutations.py:86-541` 的 `validation_error_to_error_type` 转换），调用方可分支处理（AC-26-6）；校验失败不产生部分写入（AC-26-7）；未知错误**不**转成成功空列表（AC-26-8，resolver 不 `try/except` 吞异常为空）。

  **合法的单值/数组/组合**继续可用，`OrderWhereInput`（`graphql/order/filters.py:974`）与用户关联订单查询（`graphql/account/types.py:410,662-682`）返回准确结果与稳定分页（AC-26-9）。

  **类型区分**。对象 ID、结账 token、UUID、渠道 slug 按各自类型使用，不互换；混用返回稳定错误（AC-26-10）。落点 `graphql/core/validators/__init__.py` 的相关校验与 `graphql/channel/mutations/utils.py:11-58` 的渠道 slug 处理。

  **幂等**。金额、库存与状态变更依据最新对象状态做幂等检查，重复请求不产生重复变更（AC-26-11）：复用 BD07/BD08 的 idempotency 与 `select_for_update` 口径。

  **迁移**：无。

### BD19 · 弃用读取与已退出能力的明确错误
- 覆盖需求：R27
- 设计说明：

  **弃用读取 + 替代路径**（I15）：保留的弃用字段/输入仍可读并给出替代 reason（AC-27-1），例如 `Payment.totalCaptured`（已有弃用）、`Checkout.shippingMethod`、`Checkout.availableShippingMethods`、`Checkout.giftCards`/`Order.giftCards`。

  **已退出能力返回不存在/迁移错误**（非成功空响应，AC-27-2）：
  - 旧 Adyen、NP Atobarai 插件：不再随发行提供（从 `settings.py:853-880` 的 `BUILTIN_PLUGINS`/`PLUGINS` 移除对应插件路径；`payment/gateways/adyen`、`payment/gateways/np_atobarai` 目录及相关配置移除或不可加载）。请求相关能力返回不存在/迁移错误。
  - `Payment.partial`（`payment/models.py:275`）标记弃用；`Payment.partial` 逻辑不再作为能力承诺。
  - 旧数字商品接口：`graphql/product/mutations/digital_contents.py:66-317` 的四个 mutation（`digitalContentCreate`/`digitalContentDelete`/`digitalContentUpdate`/`digitalContentUrlCreate`）**从公开 schema 移除**；调用方收到「字段不存在」的 schema 校验错误（等价于迁移错误），不再出现无解释的成功空响应。读取侧 `ProductVariant.digitalContent`、`OrderLine.digitalContentUrl`、`Query.digitalContent`、`Query.digitalContents` 保留可读并标记弃用（reason 给出替代：通过 Apps 或现行方案提供数字商品），可按权限读取既有数字内容（AC-27-2、instruction）。

  **导出**：商品、礼品卡、voucher 使用当前查询导出 mutation（`graphql/csv/mutations/export_products.py`/`export_gift_cards.py`/`export_voucher_codes.py`，schema `18183-18217`）。核对基线 schema：**不存在**其它旧导出 mutation（仅 `exportProducts`/`exportGiftCards`/`exportVoucherCodes`），因此「旧导出 mutation 按弃用约定处理」在当前基线无额外对象；如未来出现则加弃用 reason（AC-27-3）。

  **草稿订单 voucher**：`DraftOrderInput.voucher`（`graphql/order/mutations/draft_order_create.py:123`）标记弃用，替代 `voucherCode`（128，`ADDED_IN_318`）；旧 `voucher` 输入按弃用约定处理（AC-27-4）。

  **必填项**：属性 `name`/`slug`/`type` 不能为空（`graphql/attribute/mutations/` 的校验与 `validators.py`）；`AppInstallInput.appName`/`manifestUrl` 必填（`app_install.py:19-39`，I11）（AC-27-5）。

  **客户端一致性**：Core 公开 schema 更新后，Dashboard 生成客户端（`saleor-dashboard/src/graphql/*.generated.ts`）重新生成、错误映射同步；不继续生成不支持的操作（AC-27-6）。

  **迁移可从空库执行**：所有 `AddField`/数据迁移可在空库 `migrate` 完成（AC-27-7），并保留既有订单、交易、扩展、库存与元数据的业务含义（AC-27-8）；不新增仅针对主体的专用迁移（spine §6）。

  **迁移**：无新增结构性迁移（移除能力通过代码/配置变更；`Payment.partial` 弃用为字段注释）。

### BD20 · 查询与变更的权限边界
- 覆盖需求：R28
- 设计说明：

  **员工删除（真正删除）**。`remove_staff_member`（`account/utils.py:146-155`）当前在 `staff.orders.exists()` 时**软删除**（`is_staff=False` + 清权限），仅无订单才 `delete()`。设计：修改为**真正删除**员工记录（含历史订单场景），不保留 staff 标记（AC-28-1）。订单对 user 的 FK 为 `on_delete=SET_NULL`（`order/models.py:132-138`），删除后可保留历史订单（订单 user 置空/匿名化）。`StaffDelete`（`graphql/account/mutations/staff/staff_delete.py:35-55`）保持 `MANAGE_STAFF`；**自删**与无权限删除被拒绝（AC-28-1）。删除后 `instance.id = db_id` 使响应含原 ID（既有行为）。

  **属性更新权限不可绕过**：`graphql/attribute/mutations/`（`attribute_update.py`/`attribute_bulk_update.py`/`attribute_value_update.py` 等）统一要求 `MANAGE_PRODUCT_TYPES_AND_ATTRIBUTES`；任何查询/变更入口（含 bulk、reorder、value 变更）不因换入口放宽（AC-28-2）。

  **App 安装权限**：`AppPermission.MANAGE_APPS`（`app_install.py:57`），无权限拒绝（AC-28-3）。

  **导出权限**：`export_products.py`（`MANAGE_PRODUCTS`）、`export_gift_cards.py`（`MANAGE_GIFT_CARD`）、`export_voucher_codes.py`（`MANAGE_DISCOUNTS`）沿用并确保生效（AC-28-4）。

  **税务敏感字段**：`HANDLE_TAXES`（`permission/enums.py:50`；`graphql/meta/permissions.py:296-301 tax_permissions`，用于 `TaxConfiguration`/`TaxClass` 的 public/private metadata）以及结账/订单相关私有元数据，遵循 `HANDLE_TAXES` 等权限，不向未授权身份泄露（AC-28-5）。

  **范围始终生效**：客户、员工与 App 的对象范围、渠道与仓库可见性在所有入口一致生效（AC-28-6）。**权限失败 ≠ 空结果，失败 ≠ 成功**：mutation 入口的权限检查（`graphql/core/mutations.py:126-...` 的 `BaseMutation.mutate`）抛权限错误，resolver 不返回空列表冒充成功（AC-28-7）。

  **迁移**：无。

### 数据模型变更与迁移清单（§3 汇总）

| # | App | 迁移文件（基线最新序号起递增） | 变更 |
| --- | --- | --- | --- |
| M1 | channel | `00XX_channel_use_channel_warehouses_for_stock.py` | `AddField Channel.use_channel_warehouses_for_stock (default False)` |
| M2 | channel | `00XX_channel_automatic_completion_settings.py` | `AddField automatic_completion_delay / automatic_completion_cutoff_date / checkout_settings_updated_at` |
| M3 | payment | `00XX_transactionitem_transactionevent_gift_card.py` | `AddField TransactionItem.gift_card`、`TransactionEvent.gift_card` |
| M4 | giftcard | `00XX_giftcard_reserved_balance.py` | `AddField GiftCard.reserved_balance_amount (default 0)` |
| M5 | site | `00XX_sitesettings_password_login_mode.py` | `AddField SiteSettings.password_login_mode (default ENABLED)` |
| M6 | app | `00XX_appextension_settings.py` + `00XX_data_migrate_options_to_settings.py` | `AddField AppExtension.mount_name/target_name/settings` + 数据迁移保留历史设置 |
| M7 | core | `00XX_eventdelivery_status_retrying.py` | `AlterField EventDelivery.status / EventDeliveryAttempt.status choices` |
| M8 | order | `00XX_order_shipping_method_metadata_snapshot.py` | `AddField Order.shipping_method_metadata / shipping_method_private_metadata` + 幂等回填 |

说明：`Order.totalGiftCard`、`Product.channelAvailabilityDiagnostics`、`Query.transactions` 等为 resolver/派生，无迁移；`GiftCardEvents`/`EventDeliveryStatus`/`CheckoutErrorCode`/`ChannelErrorCode`/`AccountErrorCode` 为枚举常量新增，随代码发布（`core` 状态 choices 见 M7）。所有迁移须可从空库执行并保留既有业务含义（AC-27-7/8，PRD Q7）。

## 4. 接口清单

完整契约集中写在 `interface-contract.md`；本表只列后端关心的对外边界与所属设计单元。编号与标题严格采用脊柱 §2。

| 接口 | 所属设计单元 | 说明 |
| --- | --- | --- |
| I01 | BD01 | 结账配送选项重算：mutation `checkoutDeliveryOptionsRecalculate(id, token)`；`type CheckoutDeliveryOptionsRecalculate{checkout, deliveryOptions, errors}`；`type CheckoutDeliveryOptions{availableDeliveryOptions, selectedDeliveryOptionId, isSelectedDeliveryOptionAvailable}`；`type DeliveryOption{id, deliveryMethod, name, price, message}` |
| I02 | BD02 | 配送方式有效性与完成结账复核：`checkoutDeliveryMethodUpdate`/`checkoutComplete`/`checkoutShippingMethodUpdate`(deprecated) 语义与错误码；`enum CheckoutErrorCode` 新增 `DELIVERY_METHOD_NOT_FOUND`、`DELIVERY_OPTIONS_SERVICE_ERROR` |
| I03 | BD03 | 渠道-仓库直连库存开关：`type StockSettings{allocationStrategy, useChannelWarehousesForStock}`；`input StockSettingsInput{allocationStrategy, useChannelWarehousesForStock}` |
| I04 | BD04 | 商品按渠道可售性诊断：`Product.channelAvailabilityDiagnostics(filter, sortBy, before, after, first, last)`；`ProductChannelAvailabilityDiagnostics*` 与 `ProductChannelAvailabilityProblemTypeEnum`、`ProductChannelAvailabilityProblemSeverityEnum` |
| I05 | BD05/BD06 | 渠道自动完成设置：`type CheckoutSettings{..., automaticCompletionDelay, automaticCompletionCutoffDate, updatedAt}`；`input CheckoutSettingsInput{..., automaticCompletionDelay, automaticCompletionCutoffDate, expectedUpdatedAt}`；`enum ChannelErrorCode` 新增 `CHECKOUT_SETTINGS_OUTDATED` |
| I06 | BD07 | 礼品卡支付生命周期：`checkoutGiftCardPaymentCreate`/`checkoutGiftCardPaymentCancel`；`type GiftCardPaymentMethodDetails implements PaymentMethodDetails`；`TransactionItem.giftCard`；`GiftCard.reservedBalance/availableBalance`；`enum GiftCardEventsEnum` 新增 `AUTHORIZED`/`AUTHORIZATION_RELEASED`/`REFUNDED`；`checkoutAddPromoCode` 礼品卡分支语义 |
| I07 | BD08 | 订单金额分解与资金动作边界：`Order.totalGiftCard`；`Order.actions`/`TransactionItem.actions` 与金额边界语义；`orderMarkAsPaid`/`orderCapture`/`orderRefund`/`transactionRequestAction` 语义 |
| I08 | BD09 | 根级交易查询：`Query.transactions(where, before, after, first, last): TransactionItemCountableConnection`；`input TransactionWhereInput{ids, orderId, checkoutId, pspReference, appId}`；`TransactionItemCountableConnection/Edge` |
| I09 | BD11 | 密码登录策略：`Shop.passwordLoginMode`；`input ShopSettingsInput.passwordLoginMode`；`enum PasswordLoginModeEnum{ENABLED, CUSTOMERS_ONLY, DISABLED}`；`enum AccountErrorCode` 新增 `PASSWORD_LOGIN_DISABLED`、`PASSWORD_LOGIN_CUSTOMERS_ONLY` |
| I10 | BD14 | 扩展字段与安装校验：`AppExtension`/`AppManifestExtension` 新增 `mountName`、`targetName`、`settings`，`mount`/`target`/`options` 弃用 |
| I11 | BD14/BD19 | 安装输入必填与 token 语义：`input AppInstallInput{appName: String!, manifestUrl: String!, activateAfterInstallation, permissions}`；无 `tokenTargetUrl` 时不新建/不发送 token |
| I12 | BD15 | 投递状态与单条重试：`enum EventDeliveryStatusEnum{..., RETRYING}`；`eventDeliveryRetry` 权限与语义 |
| I13 | BD16 | 订单配送元数据快照：`Order.shippingMethodMetadata`、`Order.shippingMethodPrivateMetadata` |
| I14 | BD18 | Federation representations 校验：`_entities(representations: [_Any!]!)` |
| I15 | BD19 | 弃用读取与已退出能力：`Payment.partial` 弃用；草稿订单 `voucher` 输入弃用；数字商品 mutation 移除、读取弃用 |

### 无接口变化的边界（原因）

以下边界后端有行为/校验落点调整，但**不新增或改变公开 schema 契约**（对齐脊柱 §2 底部），因此不出现在接口清单中：

- **R12/R13 搜索语义（BD10）**：保留各主体既有搜索入口与过滤字段，不新增 schema；仅明确「异常不转空结果、空关键词不引发全量」。无接口变化。
- **R14/R15 Dashboard 列表与选择器**：无后端改动（由 FD02/FD03 承担）。
- **R17 OIDC 参数（BD12）**：Google `access_type=offline` 是外部 OIDC provider 授权参数，不改变 Saleor 公开 schema。无接口变化。
- **R18 富文本校验（BD13）**：校验在既有 `AttributeValue` 富文本写入通道内完成，不新增字段/类型；校验失败通过既有 mutation 的 `errors` 表达。无接口变化。
- **R22 同步载荷（BD15）**：同步订阅载荷构建边界调整，不改变 `WebhookEventInfo`/订阅 schema。无接口变化。
- **R20 扩展表单响应、R21 自托管扩展目录（FD05）**：前端承担。
- **R25 元数据基础读写（BD17）**：沿用既有 `graphql/meta/` mutation，不新增入口。无接口变化。
- **R28 权限边界（BD20）**：权限收紧/正确化，字段与类型不变。无接口变化。
- **R29/R30 工作台一致性（FD06/FD07）**：前端承担。
- **R31 非目标（§6）**：不新增任何类型/字段/操作。无接口变化。

## 5. 工程任务与依赖

任务按「schema+迁移 → 核心逻辑 → GraphQL 层 → 任务/传输 → 校验/权限 → 迁移/回填」排序，每个 BT 标注覆盖设计单元，便于覆盖追踪。BT 编号发布后不重排、不复用。

### BT01 · 数据模型与迁移基础
- 覆盖设计单元：BD03, BD06, BD07, BD11, BD14, BD15, BD16
- 依赖：无
- 工作与验证：落地 §3 迁移清单 M1–M8 的 `AddField`/`AlterField` 与数据迁移骨架（字段、默认值、null 策略）。前置条件：以基线各 app 最新迁移序号为起点，生成 `00XX` 迁移并可从空库 `migrate` 通过。完成依据：`python manage.py migrate`（空库）成功；每个迁移带 `makemigrations --check` 无遗漏；对含历史数据的表（Order 快照回填、AppExtension settings 迁移）有幂等测试。验证：迁移单测断言空库可执行、回填幂等、旧数据业务含义不变（AC-24-6、AC-27-7/8）。

### BT02 · 结账配送重算与有效性复核（GraphQL 层）
- 覆盖设计单元：BD01, BD02
- 依赖：BT01（错误码枚举随代码发布，无迁移依赖）
- 工作与验证：新增 `checkoutDeliveryOptionsRecalculate` 与 `CheckoutDeliveryOptionsRecalculate`/`CheckoutDeliveryOptions`/`DeliveryOption` 类型；新增错误码 `DELIVERY_METHOD_NOT_FOUND`/`DELIVERY_OPTIONS_SERVICE_ERROR`；在 `clean_checkout_shipping` 旁新增 `revalidate_delivery_method` 并接入 `checkoutDeliveryMethodUpdate`/`checkoutComplete`/弃用的 `checkoutShippingMethodUpdate`。完成依据：三态标识（`ShippingMethod:<pk>`/base64 app id/`Warehouse:<uuid>`）正确解析；失败不写入、不清除有效选择、不泄露其他结账信息。验证：新增/扩展 `test_checkout_delivery_options_recalculate.py`、`test_checkout_delivery_method_update.py`、`test_checkout_complete.py`，覆盖 AC-01-1..7、AC-02-1..7。

### BT03 · 渠道-仓库直连库存语义
- 覆盖设计单元：BD03
- 依赖：BT01（M1）
- 工作与验证：实现统一仓库来源解析并在商品查询/结账/订单/履约/草稿订单接入；`StockSettings`/`StockSettingsInput` 增加 `useChannelWarehousesForStock` 及 channel create/update 映射。完成依据：`false` 语义与升级前一致；`true` 仅计直接关联且有库存的仓库；旧地址参数非决定性；预留成功各入口剩余量一致、失败不超卖。验证：`saleor/warehouse/tests/`、`saleor/checkout/tests/`、`saleor/graphql/product/tests/` 覆盖 AC-03-1..7。

### BT04 · 商品按渠道可售性诊断
- 覆盖设计单元：BD04
- 依赖：BT03（库存来源解析）、BT01（无）
- 工作与验证：实现诊断聚合与 GraphQL 类型/连接/枚举；实现分级判定与「发布阻断时抑制下游依赖」规则、数字商品仅跳过配送区域检查；按渠道名/币种筛选与稳定分页。完成依据：problemCount 与明细一致、三类严重度可分、权限过滤生效、异常不返回空结果。验证：`saleor/graphql/product/tests/` 覆盖 AC-04-1..6。

### BT05 · 已支付结账自动完成资格与批量扫描
- 覆盖设计单元：BD05
- 依赖：BT01、BT02（配送复核复用）
- 工作与验证：实现资格谓词、批量扫描任务、逐项重查与幂等短路（已存在订单则跳过）、失败诊断状态。完成依据：满足条件生成一个订单；不满足留可诊断原因；重复/重试只形成一个订单、不重复扣款/通知/改金额；单结账失败不影响同批次。验证：扩展 `saleor/checkout/tests/test_tasks.py` 与新增批量任务测试，覆盖 AC-05-1..8。

### BT06 · 自动完成按渠道配置与并发
- 覆盖设计单元：BD06
- 依赖：BT01（M2）、BT05
- 工作与验证：`CheckoutSettings`/`CheckoutSettingsInput` 增加延迟/cutoff/`updatedAt`/`expectedUpdatedAt`；`clean_input_checkout_settings` 增加负延迟与组合校验；保存乐观并发（`CHECKOUT_SETTINGS_OUTDATED`）；任务按延迟（自 `last_change`）与 cutoff（`created_at` 下界）过滤。完成依据：合法值可保存重读；非法/无权限/冲突明确报错并保留上次生效值；未配置渠道行为不变。验证：`saleor/graphql/channel/tests/`、`saleor/checkout/tests/` 覆盖 AC-06-1..8。

### BT07 · 礼品卡统一支付生命周期
- 覆盖设计单元：BD07
- 依赖：BT01（M3, M4）
- 工作与验证：`TransactionItem`/`TransactionEvent` 加 `gift_card` FK，`GiftCard` 加 `reserved_balance`/`available_balance`；新增 `checkoutGiftCardPaymentCreate`/`checkoutGiftCardPaymentCancel` 与 `GiftCardPaymentMethodDetails`；`TransactionItem.giftCard` 字段；`GiftCardEvents` 增 `AUTHORIZED`/`AUTHORIZATION_RELEASED`/`REFUNDED` 并同步 GraphQL enum；`checkoutAddPromoCode` 礼品卡分支改为拒绝并给替代路径；`Checkout.giftCards`/`Order.giftCards` 弃用可读。完成依据：授权/扣款/退款与余额不变量成立；幂等键防重复；退款受可退余额；失败不改余额/不改走普通支付。验证：`saleor/payment/tests/`、`saleor/giftcard/tests/`、`saleor/graphql/payment/tests/` 覆盖 AC-07-1..7、AC-08-1..7。

### BT08 · 订单金额分解与人工资金动作边界
- 覆盖设计单元：BD08
- 依赖：BT07（礼品卡口径）
- 工作与验证：新增 `Order.totalGiftCard`；统一 authorized/charged/refunded/remaining 口径并纳入礼品卡扣款、去除 Payment/Transaction 重复计入；`Order.actions`/`TransactionItem.actions` 按支付方式与订单状态门控；资金动作金额非负、capture≤可捕获、refund≤可退、幂等、失败原子。完成依据：分解与服务端逐一一致、剩余待付=应付−已有效支付、边界等于成功/超过拒绝、重复请求一次效果。验证：`saleor/graphql/order/tests/`、`saleor/order/tests/` 覆盖 AC-09-1..6、AC-10-1..9。

### BT09 · 根级交易查询
- 覆盖设计单元：BD09
- 依赖：无（复用既有 TransactionItem 类型）
- 工作与验证：新增 `Query.transactions` + `TransactionWhereInput` + `TransactionItemCountableConnection`；按 order/checkout/ids/pspReference/appId 过滤；权限与可见范围；稳定分页与稳定错误。完成依据：礼品卡/普通/多交易可定位；越权不泄露；空分页项与越界稳定；无日期/事件筛选与专用排序。验证：`saleor/graphql/payment/tests/` 覆盖 AC-11-1..9。

### BT10 · 主体搜索边界与更新一致性
- 覆盖设计单元：BD10
- 依赖：无
- 工作与验证：确认各主体搜索入口与语义不变；修正空关键词短路、过长/非法输入、搜索服务异常不转成功空结果；确认页面→商品引用名 dirty 标记链路不被破坏；确认不新增 Page/User 高级搜索索引/任务/迁移。完成依据：既有增强搜索行为保持；新值在既有窗口可搜、旧值不唯一命中；异常可辨。验证：`saleor/core/tests/`、`saleor/graphql/page/tests/`、`saleor/graphql/account/tests/` 覆盖 AC-12-1..5、AC-13-1..7。

### BT11 · 密码登录策略
- 覆盖设计单元：BD11
- 依赖：BT01（M5）
- 工作与验证：`SiteSettings.password_login_mode` + `Shop.passwordLoginMode` + `ShopSettingsInput.passwordLoginMode` + `PasswordLoginModeEnum`；在 `CreateToken`/`SetPassword`/`PasswordChange`/`RequestPasswordReset` 与 `RefreshToken`/`VerifyToken` 执行策略；新增 `PASSWORD_LOGIN_DISABLED`/`PASSWORD_LOGIN_CUSTOMERS_ONLY`。完成依据：三模式行为正确；`CUSTOMERS_ONLY` 阻止员工会话；`DISABLED` 拒绝登录/重置/设置/修改与旧 token 路径；保存后立即生效；无权限不改。验证：`saleor/graphql/account/tests/`、`saleor/graphql/shop/tests/` 覆盖 AC-16-1..10。

### BT12 · 外部身份关联与 Google OIDC 离线授权
- 覆盖设计单元：BD12
- 依赖：无
- 工作与验证：对 Google 使用 `access_type=offline`（不用 `offline_access` scope），其他 provider 不变；错误不含 token/敏感信息；首次关联清理旧密码通道；后续登录身份稳定。完成依据：参数正确、失败可辨、同一 `sub` 稳定命中。验证：`saleor/plugins/openid_connect/tests/` 覆盖 AC-17-1..5。

### BT13 · 富文本与外链保存前校验
- 覆盖设计单元：BD13
- 依赖：无
- 工作与验证：`clean_editor_js` 改为「先结构校验、后清理」；scheme 白名单；深度上限常量；新窗口链接安全 `rel`；拒绝未知/多余字段；错误指向字段/链接/深度；无配置绕过。完成依据：合法内容可保存读回一致；非法 scheme/未知字段/超深被拒且不落库；无部分写入。验证：`saleor/core/tests/`、`saleor/graphql/attribute/tests/` 覆盖 AC-18-1..8。

### BT14 · 扩展安装、查询与迁移
- 覆盖设计单元：BD14
- 依赖：BT01（M6）
- 工作与验证：`AppExtension`/`AppManifestExtension` 增 `mountName`/`targetName`/`settings` 并弃用旧字段；数据迁移保留历史设置；安装校验 identifier/权限/target/settings；可选信息（含 `tokenTargetUrl`）缺省不失败、不需要时不返回 token；权限与读取范围。完成依据：迁移后历史扩展可查/改/渲染、设置不丢；重复 identifier/非法权限/target/设置被拒且无部分数据；无 token 场景不返回 token。验证：`saleor/app/tests/`、`saleor/graphql/app/tests/` 覆盖 AC-19-1..8。

### BT15 · Webhook 载荷边界与投递隔离
- 覆盖设计单元：BD15
- 依赖：BT01（M7）
- 工作与验证：同步订阅仅解析选中字段；订单/草稿订单/履约异步载荷在任务边界构建；纯异步不触发无关同步、不额外调用；投递隔离与既有上限不变；`EventDeliveryStatus`/`EventDeliveryStatusEnum` 增 `RETRYING` 并持久化；`eventDeliveryRetry` 权限与语义；保留失败告警、不引入 App Problems。完成依据：业务请求不等待完整异步载荷；一个接收方失败不阻断其他；状态可区分等待/成功/失败/重试中；无权限重试被拒。验证：`saleor/webhook/tests/`、`saleor/graphql/webhook/tests/` 覆盖 AC-22-1..5、AC-23-1..8。

### BT16 · 订单配送元数据快照与回填
- 覆盖设计单元：BD16
- 依赖：BT01（M8）
- 工作与验证：`Order` 加快照列并暴露 public/private 字段；结账成单与草稿成单两路径写入快照；源配送方式变更不回写；事件载荷用快照；迁移幂等回填。完成依据：两条成单路径都保留快照；源变更/删除后不变；可见性按权限；无元数据记录稳定空值、回填不重复不丢失。验证：`saleor/order/tests/`、`saleor/checkout/tests/` 覆盖 AC-24-1..6。

### BT17 · 元数据基础读写边界
- 覆盖设计单元：BD17
- 依赖：无
- 工作与验证：确认结账/草稿订单/订单/履约基础读写与订单行元数据/行内编辑保留；校验失败/权限失败不部分写入；不新增独立元数据弹窗/路由/入口。完成依据：合法键值可读写、非法/无权限不改原值、无新增入口。验证：`saleor/graphql/meta/tests/` 覆盖 AC-25-1..5。

### BT18 · 公开接口输入校验与失败语义
- 覆盖设计单元：BD18
- 依赖：无
- 工作与验证：数值/时间标量拒绝负值；`_entities(representations: [_Any!]!)` 非空且无 null 项；分页/数组空项/枚举/必填/组合执行前校验；错误含 field/code/message、不部分写入、未知错误不转空列表；类型不互换；幂等依据最新状态；`OrderWhereInput`/用户订单查询准确稳定。完成依据：非法请求稳定失败可分支、合法请求准确。验证：`saleor/graphql/core/tests/`、`saleor/graphql/order/tests/` 覆盖 AC-26-1..11。

### BT19 · 弃用读取与已退出能力
- 覆盖设计单元：BD19
- 依赖：BT14（I11 安装必填）
- 工作与验证：保留弃用读取并给替代路径；移除 Adyen/NP Atobarai 插件随附、弃用 `Payment.partial`、移除数字商品 mutation（读取弃用）；商品/礼品卡/voucher 走当前导出 mutation 且核对无其他旧导出 mutation；草稿订单 `voucher` 弃用；属性 name/slug/type 与 `AppInstallInput.appName`/`manifestUrl` 必填；Core↔Dashboard 生成客户端↔错误映射一致。完成依据：已退出能力返回迁移/不存在错误而非成功空响应；必填校验生效；客户端不生成不支持操作；迁移可空库执行。验证：`saleor/graphql/*/tests/` 与 schema 快照对比，覆盖 AC-27-1..8。

### BT20 · 查询与变更权限边界
- 覆盖设计单元：BD20
- 依赖：无
- 工作与验证：`remove_staff_member` 改为真正删除（含历史订单），自删/无权限拒绝；属性更新、App 安装、导出、`HANDLE_TAXES` 敏感字段与私有元数据的权限不可绕过；对象/渠道/仓库范围始终生效；权限失败返回权限错误而非空结果。完成依据：合法删除真正移除、越权被拒且不泄露。验证：`saleor/graphql/account/tests/`、`saleor/graphql/attribute/tests/`、`saleor/graphql/csv/tests/`、`saleor/graphql/meta/tests/` 覆盖 AC-28-1..7。

### BT21 · 跨切面：空库迁移与客户端一致性
- 覆盖设计单元：BD03, BD06, BD07, BD11, BD14, BD15, BD16, BD19
- 依赖：BT01、BT14、BT16、BT19
- 工作与验证：从空库执行全部迁移并保留既有业务含义；重新生成 Dashboard 生成客户端与错误映射，核对 Core 公开 schema、Dashboard 与文档一致、不生成不支持操作；确认无「别名/隐藏路由/生成文件」重新暴露非目标。完成依据：空库 `migrate` 成功、`schema.graphql` 快照与生成客户端一致、非目标未出现。验证：迁移 CI 任务 + schema 一致性检查，覆盖 AC-27-6/7/8、AC-31-1/2。

## 6. 其他

### 6.1 待实现决策（不新增数值，PRD Q1–Q8）

- **Q1 搜索最终一致性窗口**：沿用既有约定，不新增数值；验收以「既有窗口内新值可搜到」为准（BD10）。
- **Q2 Webhook 调用次数/超时/重试/熔断上限**：沿用既有常量（`webhook/transport/utils.py`），不新增；验收以「既有上限继续生效」为准（BD15）。
- **Q3 富文本嵌套深度上限**：由实现给出明确常量 `MAX_EDITOR_JS_DEPTH` 并在错误中可定位（BD13）；不在此设计阶段编造具体数字。
- **Q4 自动完成延迟/cutoff 默认值**：未配置渠道沿用关闭/既有默认，不改变历史手工流程（BD06）；不编造默认值。
- **Q5 所支持支付方式清单**：按「受支持完整授权、完整扣款，以及 Transaction 与兼容 Payment 流程各自约定」处理（BD05/BD08）。
- **Q6 根级交易查询字段命名与分页形式**：本设计按脊柱 I08 定为 `Query.transactions(...)` + `TransactionWhereInput`（BD09）。
- **Q7 历史扩展与历史订单元数据迁移范围/批次**：以「空库可执行、保留既有业务含义、不重复不丢失」为验收标准（BD14/BD16/BT21）。
- **Q8 自托管扩展目录数据来源/降级**：由 FD05 承担；后端保证扩展安装/查询/迁移契约稳定（BD14）。

### 6.2 迁移、发布与回填说明

- 迁移顺序建议：先 `AddField`（M1–M8），再数据迁移（M6 扩展设置、M8 订单快照回填），最后弃用/移除切换（BD19）。所有迁移可从空库执行（AC-27-7）。
- 回填幂等：M8 仅对快照为空且存在 `shipping_method` 的订单回填一次；无元数据记录留稳定 null/空，不重复、不丢失（AC-24-6）。M6 按行比对，不重复写入，不丢历史设置（AC-19-2）。
- 兼容顺序：Core schema 更新后重新生成 Dashboard 客户端；旧字段在替代字段稳定后再移除（本轮仅弃用，不硬删公开字段，`Payment.partial`/草稿订单 `voucher` 保留弃用读取）。
- 开关默认值保证「未切换即沿用既有行为」：`useChannelWarehousesForStock=false`、自动完成未配置渠道、旧配送标识、历史订单配送元数据均保持升级前语义。

### 6.3 兼容性规则

- 旧客户端合法旧标识（`shippingMethod`/`checkoutShippingMethodUpdate`）继续可用，最终状态与新路径一致；`Checkout.shippingMethod`/`availableShippingMethods` 保留弃用读取。
- `Checkout.giftCards`/`Order.giftCards` 保留可读且弃用；礼品卡新写路径为交易生命周期，`checkoutAddPromoCode` 礼品卡分支拒绝并给替代路径。
- 枚举只增不改：`CheckoutErrorCode`、`ChannelErrorCode`、`AccountErrorCode`、`GiftCardEventsEnum`、`EventDeliveryStatusEnum` 仅新增值，不移除既有值。
- 弃用字段 reason 必须给出替代路径；不通过别名/隐藏路由/生成文件重新暴露被移除能力。

### 6.4 明确非目标（spine §6，三个文档共同遵守）

后端**不新增**以下能力，且不通过别名、隐藏路由或生成文件重新暴露：

- App Problems 的类型/字段/操作/问题列表；既有 Webhook 失败告警保留（BD15）。
- Page/User 向量高级搜索、RANK 排序与专用索引、后台维护任务与迁移（BD10）。
- 交易日期/事件筛选与本查询专用排序索引（BD09）。
- 异步外链图片抓取与 pending/503/proxy 状态与专用失败回退。
- 独立变体生成器页面/菜单/任务/状态。
- 订单、履约、仓库的独立元数据弹窗/专用路由/隐藏入口（BD17）。

保留边界：基础搜索、普通媒体与变体操作、基础交易查询、元数据基础编辑、Webhook 失败告警均保留（R31）。依赖升级、CI、运行器、生成工具、遥测与内部重构不另立业务需求；只有影响上述业务约定的部分属于本次交付约束。

### 6.5 基线核对与脊柱锚点偏差（不修改 PRD）

以下为对照 `/workspace/repos/saleor` 基线时发现的脊柱锚点描述偏差，本文件已采用核对后的实际落点，供实现与接口契约对齐：

- `giftcard/events.py:213-238` 实际是 `gift_cards_used_in_order_event` 辅助函数；`GiftCardEvents` 常量类在 `giftcard/__init__.py:9-38`（GraphQL enum 在 `schema.graphql:10838`）。
- 支付 mutation 实际路径为 `saleor/graphql/payment/mutations/transaction/transaction_request_action.py` 与 `.../transaction_create.py`（脊柱省略了 `transaction/` 子目录）。
- `saleor/warehouse/models.py:44-114` 为 `WarehouseQueryset` 方法（非 Stock/Warehouse 字段）；`330-449` 为 `StockQuerySet`；`applicable_for_click_and_collect` 在 165-247。
- `saleor/product/models.py:492-520` 为 `ProductVariantChannelListing`（非 `ProductChannelListing`）；`is_published`/`published_at`/`is_visible` 继承自 `core/models.py:63-77`。
- `saleor/graphql/order/filters.py:974` 是 `OrderWhereInput`；`TransactionFilterInput` 在 588。
- `saleor/settings.py:861-863` 属 `BUILTIN_PLUGINS`（定义于 853）；`PLUGINS` 在 880。
- Federation `_entities` 基线 SDL 为 `[_Any]`（nullable，`schema.graphql:1665`），需改为 `[_Any!]!`（BD18）。
- 基线无 `access_type` 参数（Google 离线仅以 `offline_access` scope 表达，`plugin.py:221-234`），BD12 需新增。
- 基线无渠道级 `ChannelCheckoutSettings` 模型，自动完成开关/延迟落在 `Channel` 字段（`channel/models.py:50` 及 M2 新增）。

以上均不影响 PRD 需求范围与验收条件；如需调整，属实现阶段决策，不修改 `artifacts/sprint1/prd/prd.md`。






