# 补充协议：配送选项标识（delivery option id）

关联接口：I01（`checkoutDeliveryOptionsRecalculate`）、I02（`checkoutDeliveryMethodUpdate` / `checkoutComplete` / 弃用的 `checkoutShippingMethodUpdate`）
关联设计单元：BD01、BD02
版本：v1（sprint1/tech-design 第 1 轮）

## 1. 标识形态

`DeliveryOption.id` 与 `checkoutDeliveryMethodUpdate(deliveryMethodId:)` 使用**同一套**标识，共三类，直接透传、不做二次编码：

| 形态 | 格式 | 来源 |
| --- | --- | --- |
| 内置配送方式 | `ShippingMethod:<pk>` | 渠道内 `ShippingMethod` 记录 |
| 外部配送服务 | `app:<identifier>:<method>`（base64） | 同步配送服务 webhook 返回的方法 |
| 自提点 | `Warehouse:<uuid>` | 渠道直接关联的仓库 |

旧客户端可能提交历史格式 `app:<pk>:<method>`（`identifier` 为 App 主键而非标识符）。服务端在比对前做归一化，两种格式指向同一方法时视为同一选项，不以「未找到」拒绝。

## 2. 取值约定

1. `DeliveryOption.id` 是**不透明字符串**，调用方不得解析、拼接或构造，只能原样回传。
2. `DeliveryOption.id` 的有效范围是**当前结账**。同一标识在另一笔结账中不保证有效。
3. `DeliveryOption.id` 仅在当前请求的有效集合内有效；结账地址、行项目、渠道、同步配送服务结果变化后可能失效并停止出现在 `availableDeliveryOptions` 中。

## 3. 重算与更新的一致性

- 调用方须先调用 I01 取得 `availableDeliveryOptions` 与 `selectedDeliveryOptionId`，再从该集合中选取一项提交给 I02。
- I02 收到标识后**重新校验**（地址、行项目、渠道、同步配送服务），不信任调用方传来的有效性：
  - 标识可解析且属于当前结账，但已不在当前有效集合内 → `field: "shipping_method"`, `code: DELIVERY_METHOD_NOT_APPLICABLE`。
  - 标识不属于当前结账或无法解析 → `field: "delivery_method_id"`, `code: DELIVERY_METHOD_NOT_FOUND`。
  - 同步配送服务报错 → `field: "delivery_method_id"`, `code: DELIVERY_OPTIONS_SERVICE_ERROR`。
- 上述任一失败：**不写入** `shipping_method`、`shipping_method_name`、`last_change`，原选择保持可用；`checkoutDeliveryMethodUpdate` 与弃用的 `checkoutShippingMethodUpdate` 结果一致。
- 调用方不得提交 `selectedDeliveryOptionId` 之外的、来自其他结账的或自行拼接的标识。

## 4. 三态选择语义（I01 返回）

| `selectedDeliveryOptionId` | `isSelectedDeliveryOptionAvailable` | 含义 | 调用方动作 |
| --- | --- | --- | --- |
| `null` | `null` | 结账尚无有效选择 | 重新选择 |
| 非空 | `true` | 选择仍有效，且出现在 `availableDeliveryOptions` 中 | 可直接提交 |
| 非空 | `false` | 选择已失效，且**不**出现在 `availableDeliveryOptions` 中 | 必须重新选择 |

`DeliveryOption.deliveryMethod` 为 `null` 表示底层方法无法映射到 `DeliveryMethod` union 成员，此时仍以 `id` 作为提交依据。

## 5. 失败语义

- I01 计算失败时 `deliveryOptions` 为 `null` 且 `errors` 非空；不覆盖已保存的有效选择，不写入半成品选择。
- I01 为只读操作，不因调用改变结账。
- `checkoutComplete` 在提交前执行同一复核；失效时阻止完成，不创建订单、不产生支付/交易/库存预留副作用。
