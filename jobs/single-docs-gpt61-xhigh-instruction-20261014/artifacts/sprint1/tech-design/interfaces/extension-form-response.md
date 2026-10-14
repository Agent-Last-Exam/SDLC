# Dashboard ↔ App 表单响应协议（I17）

版本：v1。保留现有 App SDK notification、redirect、updateRouting、notifyReady、requestPermissions 的动作/response envelope。新增表单动作，不更改 GraphQL schema，不将现有 App SDK 当作已支持该动作的事实。实施时在 `useAppActions.ts` / `appActionsHandler.ts` 增加运行时校验与 handler；不得只以 TypeScript assertion 接收跨域数据。

## 端点与鉴别

使用浏览器 postMessage；发送端 targetOrigin 必须为明确 App origin / Dashboard origin，不能 `*`。Dashboard 接收端同时校验 `event.origin === resolvedAppOrigin` 和 `event.source === registeredFrame.contentWindow`。每次 frame 挂载生成随机 frameId，每次商品/翻译表单切换生成 formContextId（含 objectId、locale、字段/版本的内存关联），维护单调 formRevision。关闭/卸载/导航/iframe src 改变使 frame 和 context 失效，移除 listener，清除待响应记录。只有该 frame 完成 notifyReady 握手后才能交换表单数据；未握手时不返回 token 或内容。App 停用、权限变化立即失效。

握手完成后不直接发送表单：Dashboard 先发 `formProtocolHello`，App 回 `formProtocolReady`，版本和 frameId 一致且当前 registered source 合法后才发 `formContext`。协议不匹配/缺省时保留原非表单 SDK 动作，不发任何表单内容。仅在用户显式打开表单扩展且满足字段权限时发送允许字段，不发送完整 User/私有元数据或未请求 token。appToken 继续在受验证 notifyReady 握手内存中传递，禁止 URL、日志、localStorage 和 sessionStorage 持久化。非握手窗口同 origin 也不能获取 token。Base `AppFrame.tsx::handleLoad` 直接发送带 token 的兼容握手必须改为仅重置 loading/ready，不能凭 onLoad 宣告已鉴别；token refresh/update 路径也仅在当前 frame 真正 notifyReady 后启用。

## 完整 envelope

```typescript
type FormProtocolHello = {
  type: "formProtocolHello";
  payload: { frameId: string; protocolVersion: 1 }; // Dashboard → 已 notifyReady 的 App
};
type FormProtocolReady = {
  type: "formProtocolReady";
  payload: { frameId: string; protocolVersion: 1 }; // App → Dashboard，回显同一 frame
};
type FieldError = { field: string; code: "INVALID" | "REQUIRED" | "FORBIDDEN"; message: string };
type FormContext = {
  type: "formContext";
  payload: {
    frameId: string;
    formContextId: string;
    revision: number; // 非负整数
    objectId: string; // Relay Product ID 或翻译源对象 ID，不是 token
    locale: string | null; // 商品表单 null，翻译表单使用目标 locale
    fields: Record<string, string | null>; // 仅允许 name、description；description 是合法 EditorJS JSON 字符串
  };
};
type FormResponse = {
  type: "formResponse";
  payload: {
    actionId: string; // 1..128 字符，本 frame 内唯一
    frameId: string;
    formContextId: string;
    revision: number;
    status: "SUCCESS" | "VALIDATION_ERROR" | "PERMISSION_DENIED" | "APP_CLOSED";
    fields?: Record<string, string | null>;
    errors?: FieldError[];
  };
};
type FormResponseAck = {
  type: "response";
  payload: {
    actionId: string;
    ok: boolean;
    code?: "APPLIED" | "VALIDATION_ERROR" | "PERMISSION_DENIED" | "APP_CLOSED" |
           "STALE_CONTEXT" | "UNKNOWN_ACTION" | "INVALID_RESPONSE" | "FRAME_NOT_READY";
    errors?: FieldError[];
  };
};
```

对象不接受上面未声明字段，message 不接受 HTML，单条消息 UTF-8 不超过 1 MiB；fields/errors 最多 100 项，不允许 null 数组项。缺省 fields 和 errors 各规范化为空对象/空数组，绝不将缺省解释为清空表单。明确 null 才可清空所属表单允许清空的字段；name 不接受空值，description 按 I15。只接受当前 handler 注册的字段，未知字段 INVALID_RESPONSE。

## 应用、去重及失败

- SUCCESS 必须没有 errors，先对所有返回字段应用本地表单校验（富文本遵循 I15），全部通过才原子更新内存表单，标记 dirty；不自动触发 Core mutation，不更新 Apollo 已保存缓存，不显示“已保存”。若用户在等待期间编辑使 revision 不同，返回 STALE_CONTEXT，不覆盖新输入。
- VALIDATION_ERROR 不应用任何 fields，仅为对应字段显示 errors；PERMISSION_DENIED 显示权限错误；APP_CLOSED 结束当前扩展等待但保留表单。错误 status 携带 fields 仍不能应用。
- 相同 actionId、同一规范化 payload 重发返回原 ACK，不重复更新或保存；同 actionId 不同 payload 返回 INVALID_RESPONSE。cache 限当前 frame 生命周期（最多 1000 项，超限拒绝新消息并提示重新打开），没有跨 frame 复用。
- origin/source 验证失败丢弃且不向伪造发送方 ACK；已鉴别但未握手、过期 context、未知 action 返回 ok=false 与稳定 code。现行未知动作抛异常的路径改为可处理拒绝，不让单条坏消息拆掉全局监听。
- 旧 SDK 不发送 frame/context/revision 的消息仍可使用原有非表单动作，不能修改任何表单；新增动作须显式协商本协议版本，不降低鉴别要求来兼容旧 App。

## 验证

两同源 frame 同时打开，仅 source 对应 frame 能更新自己的表单；旧商品/旧 locale、迟到响应、重复/冲突 actionId、未加载 frame、卸载后响应、App 停用、未知 action 和富文本失败均不能污染编辑；合法返回使表单 dirty，只有随后实际 Core 保存业务成功才刷新缓存。测试落点 `AppFrame/appActionsHandler.test.ts`、`AppExtensionContextProvider.test.tsx`、商品/翻译表单测试。
