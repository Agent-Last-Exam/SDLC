# 补充协议：Webhook 投递状态（event delivery status）

关联接口：I12（`EventDeliveryStatusEnum`、`eventDeliveryRetry`）
关联设计单元：BD15（R23）
版本：v1（sprint1/tech-design 第 1 轮）

## 1. 状态集合

`EventDelivery.status` 与 `EventDeliveryAttempt.status` 使用同一枚举 `EventDeliveryStatusEnum`：

| 值 | 终态 | 含义 |
| --- | --- | --- |
| `PENDING` | 否 | 已接受但尚未产生投递结果（含同步内容仍在生成） |
| `RETRYING` | 否 | 重试进行中（本轮新增） |
| `SUCCESS` | 是 | 投递成功 |
| `FAILED` | 是 | 投递失败且无进一步重试 |

## 2. 状态机

```
PENDING ──► RETRYING ──► SUCCESS
   │            │
   │            └────────► FAILED
   └─────────────────────► SUCCESS / FAILED
```

- 同一 delivery 只允许朝终态收敛，不得从终态回到非终态。
- `RETRYING` 是**非终态**：前端不得将其渲染为成功，也不得视为最终失败。
- 失败隔离：单条 delivery 失败只影响该 delivery，同订阅的其他 delivery 继续。

## 3. 展示约定（FD10）

- 列表与详情对非终态（`PENDING` / `RETRYING`）显示进行中，不显示成功样式。
- **异步内容尚未生成时不得显示为成功。**
- 终态与对应 `EventDeliveryAttempt` 记录一致：最近一次尝试成功 → `SUCCESS`；耗尽重试仍失败 → `FAILED`。
- 前端重新拉取时以服务端当前状态为准，不使用本地推断的中间态作为结论。

## 4. 单条重试

- 入口：既有 `eventDeliveryRetry(id: ID!)`，签名与权限（`MANAGE_APPS`）不变；语义收敛为「按单条 delivery 重试」。
- 重试对象必须是可重试的 delivery；重试不改变其他 delivery 的状态。
- 重试内容不超出 App 可见字段边界，不泄露无权数据。
- 重试失败经既有 `EventDeliveryRetry` payload 的 `errors` 表达，不静默成功。
- 既有 Webhook 失败告警保留；本轮不扩展为 App Problems 功能（属 R31 非目标）。

## 5. 兼容性

`RETRYING` 为本轮新增枚举值。未识别该值的旧客户端在解析响应时可能失败，须升级为「非终态」处理（BC-023 / interface-contract §3.2）。三个 Base 既有值语义不变。
