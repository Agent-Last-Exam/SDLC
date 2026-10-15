# 补充协议：Google OIDC 离线授权与外部身份关联

对应接口编号：I16（见 `../interface-contract.md`）
所属设计单元：BD14（见 `../backend-design.md`）
提供方：`saleor/plugins/openid_connect/plugin.py`（授权参数拼装，基线约 L222-229）、`saleor/plugins/openid_connect/utils.py:391 get_or_create_user_from_payload`（身份关联）
调用方：Storefront 登录入口、Dashboard 外部分登录入口
依据：R18；BC-017

本文件描述 Core 的 OpenID Connect 插件在 Google provider 场景下的授权参数约定与外部身份关联行为。这部分不属于 GraphQL 契约，无法在 `target-schema.graphql` 中表达，因此单独记录并由 `interface-contract.md` 的 I16 引用。

## 1. 现行行为（基线）

- `saleor/plugins/openid_connect/plugin.py` 目前把 scope 拼装为 `openid profile email`，并在需要 refresh token 时追加 `offline_access` scope（基线约 L222-229）。
- 插件配置项 `use_scope_permissions` 影响权限来源。
- 仓库中**不存在** `access_type` 参数的拼装逻辑。
- 首次登录时由 `saleor/plugins/openid_connect/utils.py:391 get_or_create_user_from_payload` 按 payload 查找或创建用户。

## 2. 目标行为（本轮）

### 2.1 离线授权参数

| 项 | 目标值 |
| --- | --- |
| provider | Google OIDC |
| refresh token 需求场景 | 需要离线访问（授权码模式） |
| 参数 | `access_type=offline` |
| scope | `openid profile email` |
| 禁止 | 追加 `offline_access` scope（Google 不识别该 scope 语义） |

其他 provider（非 Google）按各自既有合同发起授权，不受本条约束。

### 2.2 授权请求形态

```
GET {authorization_endpoint}
    ?client_id={client_id}
    &redirect_uri={redirect_uri}
    &response_type=code
    &scope=openid%20profile%20email
    &state={state}
    &nonce={nonce}
    &access_type=offline
```

其中 `access_type=offline` 仅在 Google provider 且需要 refresh token 时出现。

### 2.3 失败与敏感信息

- 授权失败（provider 返回 `error`、state/nonce 校验失败、token 交换失败）返回**可识别**的错误码，调用方能区分失败原因类别。
- 错误响应中**不得**包含 `id_token`、`access_token`、`refresh_token`、完整 identity payload 或邮箱以外的身份属性。
- 前端**不得**把 token 或不必要的身份信息持久化到 localStorage 等非必要存储；token 只经既有安全通道处理。

## 3. 外部身份关联行为

### 3.1 首次关联已存在的本地用户

给定某邮箱已存在本地用户：

1. 该用户首次通过外部身份完成关联时，服务端清理或禁用该用户的本地密码路径——使既有密码不能再通过 `tokenCreate`、`passwordChange` 等入口取得会话。
2. 关联后的身份映射被持久化，后续登录命中同一用户。
3. 清理动作与关联动作在同一事务内完成，不留下「关联成功但旧密码仍可用」的中间态。

### 3.2 后续登录

同一 OIDC 身份（同 provider + 同 `sub`）后续登录必须被识别为同一用户，不重复创建用户记录。

## 4. 权限

沿用 OIDC 插件既有配置与 `get_or_create_user_from_payload` 的既有权限语义，本轮不改变权限模型。

## 5. 完成判定

- AC-18-1：需要 refresh token 的 Google OIDC 授权请求使用 `access_type=offline` 且不含 `offline_access` scope；其他 provider 按各自合同发起。
- AC-18-2：一次授权失败的错误响应与前端存储中不含 token 与敏感身份信息。
- AC-18-3：邮箱已存在本地用户时，首次完成外部身份关联后旧密码不能再绕过外部身份策略。
- AC-18-4：同一 OIDC 身份后续登录稳定命中同一用户。

## 6. 验证方法

| 检查 | 方法 |
| --- | --- |
| 授权参数 | 捕获授权重定向 URL，断言含 `access_type=offline`、不含 `offline_access` |
| 其他 provider | 对非 Google provider 断言授权参数与其既有合同一致 |
| 失败响应 | 构造授权失败，断言响应与前端存储不含 token 与身份信息 |
| 首次关联 | 预置本地用户与密码，完成首次关联后断言密码路径不可用 |
| 身份稳定 | 同一 `sub` 二次登录，断言用户数不变 |

## 7. 未执行的检查

- 未对真实 Google OIDC 端点发起授权请求。
- 未运行 Core 测试套件（本轮为设计交付，不开发代码）。
