# 接口对齐文档：Saleor Core 与 Dashboard 协同迁移至 3.23.0

版本：v1
责任：后端技术设计
依据：后端技术设计 v1，backend-design.md
修订：首次交付（2026-10-13）；登记版本返回值变化、App扩展六字段兼容变更及不变回归边界；与完整target-schema.graphql一致。

## 1. 通用约定

1. **协议与入口：**沿用HTTP GraphQL `/graphql/`，本地Core通常`http://localhost:8000/graphql/`，Dashboard通过runtime `window.__SALEOR_CONFIG__.API_URL`配置，不硬编码业务请求域名。JSON请求含query、variables及可选operationName，上传沿用既有multipart link。本轮不改变传输协议，不新增REST/gRPC。
2. **权威定义：**同目录`target-schema.graphql`是从给定Core Base推导的完整目标SDL，保留所有未变更定义。以下片段只展示边界，省略的输入/返回字段仍在完整SDL中，不代表删除。I01是返回值变化；I02/I03各新增三个字段并提示旧字段弃用；I04—I09保持Base，不称为3.23新功能。新增范围是现有两端消费差异修复，不是完整上游3.23 schema的证明。
3. **身份：**保持SDK/Apollo既有token/credentials机制和Core权限实现；全局登录不意味着拥有每项业务权限。App、员工与匿名客户的可见性由每个接口说明限定。UI权限、PERMISSION查询变量不是服务端授权。
4. **错误分层：**transport/network错误、GraphQL语法/变量/标量错误、顶层resolver/权限错误与payload业务errors分别处理。Core BaseMutation对PermissionDenied抛顶层GraphQL错误（现有`extensions.exception.code="PermissionDenied"`），不要在前端假设所有权限失败都在payload.errors。HTTP200、onCompleted、errors空但payload/必要对象缺失均不等于成功。列表`[XError!]!`表示列表和项不可空，成功为`[]`；nullable业务实体不能无检查访问id。业务错误码沿用完整SDL的域内enum，不增加统一虚构错误码。
5. **ID/数值：**ID为GraphQL opaque Node ID，不拆解猜数据库主键；不同实体的ID不得互换。externalReference/SKU不自动代表upsert或幂等键。Decimal/PositiveDecimal、UUID、JSONString使用Base标量规范。新增settings使用**JSON原生对象**，不能用JSONString或JSON编码字符串替代。
6. **可空/缺省：**按SDL区分省略、null与空列表；不把可空输入统一解释为清空/默认。输入字段的缺省只在SDL明确有默认值时成立，其余受Base业务清理约束。GraphQL列表可为空，即使是`[T!]!`也不隐含至少一项。非空字段失败可能向父对象传播null，不承诺partial data总能保留。
7. **完成与重试：**typed errors为空且必要对象非空只是本次同步操作成功；异步安装、支付/通知和webhook需独立状态。多个Mutation根及跨请求组合不提供整体原子事务。创建、草稿完成、授予退款与资金动作不得因timeout盲目重发；先重读已有对象。I09有特定结算重入逻辑，不把其推广到所有接口。
8. **兼容：**保留旧App枚举、options union、filter、manifest校验及所有未变更操作；弃用不是删除。未来获批目标变化须稳定追加/修订I编号，不能静默换SDL或替换冻结PRD/测试。

## 2. 接口契约

### I01 · 商店版本返回值
- 所属设计单元：BD01
- 提供方：`saleor/saleor/graphql/shop/types.py.Shop.resolve_version/resolve_schema_version`；版本源` saleor/__init__.py`（现有，拟更新元数据）
- 调用方：Dashboard配置/版本联调（FD01）；授权员工/App及配对验收客户端
- 目标定义：`Query.shop`、`Shop.version`、`Shop.schemaVersion`

```graphql
query MigrationVersion {
  shop { version schemaVersion }
}
```

- 字段说明：`shop: Shop!`；`version: String!`目标返回`3.23.0`，`schemaVersion: String!`目标返回`3.23`。无参数/列表。类型不变，真实值来自版本元数据派生。
- 权限：version允许AUTHENTICATED_STAFF_USER或AUTHENTICATED_APP；schemaVersion未配置相同字段权限，不把它描述为必须MANAGE_SETTINGS。shop根不是全域管理权限门。
- 错误：version未授权为顶层GraphQL权限错误，非空可能影响shop；不能返回伪旧版/空串规避权限。
- 完成判定：正常运行Core返回真实版本，Dashboard构建版本同为3.23.0；仅此读取不证明目标能力实现，无写入/事件。
- 变更与兼容：由3.22.0/3.22变成3.23.0/3.23，SDL签名不变；不承诺3.22与3.23任意混搭。

### I02 · 已安装App扩展读取与三个兼容字段
- 所属设计单元：BD02
- 提供方：`saleor/saleor/graphql/app/schema.py.AppQueries`、`app/types.py.AppExtension`（拟新增派生resolver）；`saleor/app/models.py.AppExtension`为现有数据源
- 调用方：`saleor-dashboard/src/extensions/queries.ts.extensionList/ExtensionList`、`hooks/useExtensions.ts`、AppWidgets（FD02、FD03）
- 目标定义：`Query.appExtensions`、`Query.appExtension`、`AppExtension`、`AppExtensionFilterInput`

```graphql
query CompatibleExtensions($mounts: [AppExtensionMountEnum!]) {
  appExtensions(filter: {mount: $mounts}, first: 100) {
    edges {
      node {
        id label url mount target mountName targetName settings
      }
    }
  }
}
```

- 字段说明：`appExtensions(filter:AppExtensionFilterInput,before:String,after:String,first:Int,last:Int):AppExtensionCountableConnection`可空；`edges:[AppExtensionCountableEdge!]!`、`edge.node:AppExtension!`不可空，列表可空集合；`appExtension(id:ID!):AppExtension`可空。filter.mount为`[AppExtensionMountEnum!]`（列表可空，项非空）、filter.target为nullable Enum。仍用现有分页最大100限制与cursor语义，不引入字符串filter。
  - 新增`mountName:String!`等于旧mount的现有**大写枚举名称**；`targetName:String!`等于旧target的大写名称，仅POPUP/APP_PAGE/NEW_TAB/WIDGET。不是任意自由字符串挂载点协议。
  - 新增`settings:JSON!`保证为对象：普通/无配置`{}`；NEW_TAB有method为`{"newTabTarget":{"method":"GET"}}`或POST；WIDGET为`widgetTarget`同形。method缺省/null输出`{}`，前端当前默认GET；不返回null/JSON字符串，不同时输出两个target子对象。
  - 对已安装模型从小写mount/target及`http_target_method`派生，不新建settings持久字段。原`options` union和新settings来自同一源值；旧`mount/target`依旧非空，旧`options`依旧可空。
- 权限：入口允许authenticated staff或App；parent App解析对App限制自身，staff按Base可见性；accessToken仍需请求者覆盖扩展permissions才可生成，不足时为null。新增字段不赋予安装权限，不返回token/私有metadata，不绕过既有对象边界。
- 错误：变量类型/分页错误沿用Base；鉴权拒绝为顶层；非法历史mount/target/方法视数据完整性问题，不伪造默认挂载。非空派生resolver异常可能null bubbling，需联调校验合法存量数据。
- 完成判定：纯读取无写入/外部请求/事件；对合法旧数据新旧字段一一对应，真实ExtensionList可验证且正常挂载。非法扩展前端局部错误/不执行action，不能影响有效项。
- 变更与兼容：新增三个字段；旧mount/target/options只增加弃用提示且保留类型与resolver。旧filter、Enum与union保留；不扩大manifest输入支持范围。本差异来自已有Dashboard3.22.9消费，不标记上游3.23新增业务。

### I03 · Manifest预览及扩展字段一致性
- 所属设计单元：BD02
- 提供方：`saleor/saleor/graphql/app/mutations/app_fetch_manifest.py.AppFetchManifest`、`app/types.py.AppManifestExtension`（拟新增dict派生resolver）、`saleor/app/manifest_validations.py`
- 调用方：Dashboard `src/extensions/mutations.ts.AppFetch`、`src/fragments/apps.ts.appManifestFragment`、安装页`useFetchManifest`（FD03）；新字段验收客户端
- 目标定义：`Mutation.appFetchManifest`、`AppFetchManifest.manifest`、`Manifest.extensions`、`AppManifestExtension`

```graphql
mutation PreviewExtensionManifest($url: String!) {
  appFetchManifest(manifestUrl: $url) {
    errors { field message code }
    manifest {
      extensions { label url mount target mountName targetName settings }
    }
  }
}
```

- 字段说明：`appFetchManifest(manifestUrl:String!):AppFetchManifest`可空；`manifest:Manifest`可空，`errors:[AppError!]!`；`Manifest.extensions:[AppManifestExtension!]!`列表/项不可空（允许[]）。新三字段类型与I02相同，无新增输入；权限列表`[Permission!]!`保持。字典root是已验证并清洗的manifest，不是数据库模型。
  - mountName为已有mount大写；target未指定按既有popup默认→POPUP；options内部snake_case `new_tab_target/widget_target`转输出camelCase。无method/options输出`{}`，只输出已认可配置；未知字段不透传。不接受任意新增manifest key。
- 权限：MANAGE_APPS，保持Base requester/object授权；不要把普通扩展读取权限视为manifest获取权限。
- 错误：URL、网络获取、JSON/manifest及权限校验沿用AppError与顶层错误；不因新增字段放宽http/url/manifest验证、requiredSaleorVersion检查或permissions检查。typed error时不将空manifest当成功。正式协议可获取许可网络manifest；本任务验证只用允许本地服务，不访问外网。
- 完成判定：errors空且manifest非空表示**预览/验证成功**，没有安装或持久化。相同manifest安装后的I02配置与预览一致。无side-effect mutation事件；不把fetch命名等同安装。
- 变更与兼容：新增三个字段，旧mount/target加弃用但保留。当前Dashboard预览仍消费旧mount/target，不要求强制切换；没有名为Query.appManifest的新入口。

### I04 · App安装、重试及异步状态
- 所属设计单元：BD02
- 提供方：Core `saleor/graphql/app/mutations/app_install.py.AppInstall`、`app_retry_install.py.AppRetryInstall`、`saleor/app/installation_utils.py.install_app`及现有安装任务
- 调用方：Dashboard扩展安装页及`src/extensions/mutations.ts`（FD03）
- 目标定义：`Mutation.appInstall/appRetryInstall`、`Query.appsInstallations`、`AppInstallation`、`AppInstallInput`

```graphql
mutation InstallCompatibleApp($input: AppInstallInput!) {
  appInstall(input: $input) {
    errors { field message code }
    appInstallation { id status message }
  }
}
```

- 字段说明：`appInstall(input:AppInstallInput!):AppInstall`；`appRetryInstall(activateAfterInstallation:Boolean=true,id:ID!):AppRetryInstall`；payload安装对象可空，errors为`[AppError!]!`。`appsInstallations:[AppInstallation!]!`列表/项不可空；status为`JobStatusEnum!`。input manifestUrl/appName可空但业务约束仍存在；activateAfterInstallation默认true；permissions为`[PermissionEnum!]`（列表可空，项非空）。安装root字段语义不改。
- 权限：appInstall须authenticated staff且MANAGE_APPS；重试/状态查询按Base MANAGE_APPS。requested permissions不能超出既有许可，App不借新字段自行安装。
- 错误：输入与AppError沿用；任务失败由AppInstallation状态/message记录，mutation errors空不掩盖任务失败。
- 完成判定：mutation有有效installation.id只是创建/接受任务；后续status实际SUCCESS且App/扩展可重读才算安装完成。失败重试用原installation.id，不能无限自动重新appInstall。APP_INSTALLED等事件沿用原任务生命周期；settings在安装时仍通过既有method持久化，没有新双写。
- 变更与兼容：签名/数据模型/异步行为不变；仅与I02/I03新增读取映射协同。

### I05 · 商品、变体、库存与渠道listing
- 所属设计单元：BD03
- 提供方：Core `saleor/graphql/product/mutations/product/product_create.py.ProductCreate`、`product_variant/product_variant_create.py.ProductVariantCreate`与现有listing/stock mutations
- 调用方：Dashboard `src/products/mutations.ts`、ProductVariantCreate、ProductVariant、useSubmitChannels（FD04、FD05）
- 目标定义：`Mutation.productCreate/productVariantCreate/productVariantUpdate/productChannelListingUpdate/productVariantChannelListingUpdate/productVariantStocksCreate/productVariantStocksUpdate/productVariantStocksDelete`，`Query.product/productVariant`及其完整输入/结果类型

```graphql
mutation CreateCompatibleVariant($input: ProductVariantCreateInput!) {
  productVariantCreate(input: $input) {
    errors { field message code attributes values }
    productVariant { id sku }
  }
}
```

- 字段说明：productCreate.input为`ProductCreateInput!`，其中productType为`ID!`，name等按完整SDL（可空不豁免业务必填）；variantCreate.input为`ProductVariantCreateInput!`，product为`ID!`，attributes为`[AttributeValueInput!]!`（必须传，可为[]但受商品类型校验），stocks为`[StockInput!]`（列表可空/项非空），StockInput仓库/数量均必填。价格不在variantCreate中，通过`productVariantChannelListingUpdate(id:ID,input:[ProductVariantChannelListingAddInput!]!,sku:String)`配置；variantUpdate外部reference/id/sku按Base选择，不任意混用。
  - 产品/变体实体返回可空，errors `[ProductError!]!`；`Query.product`和`productVariant`可按完整SDL的id/slug/sku/externalReference/channel读回，channel是slug字符串不是Channel ID。返回金额单位及可空规则不改。所有详细输入保持完整SDL，不重新手写类型缩减。
- 权限：写入MANAGE_PRODUCTS，读取遵循具体对象/渠道/发布可见性与字段权限；不把有MANAGE_PRODUCTS等同所有渠道数据一律公开。
- 错误：ProductError包含field/message/code及attributes/values；SKU、属性、库存、重量/数量、渠道错误沿用Base；权限顶层。多root任一失败都算整个前端提交未完全完成。
- 完成判定：局部创建原事务提交且返回有效对象不代表后续listing/media/metadata都成功。前端等待全部必需root/请求并重读；失败时记录部分成功，不假装跨请求回滚。无通用幂等键；timeout后先重读，不自动重复创建。
- 变更与兼容：全部SDL不变，保留旧弃用字段；只改前端成功判定而不改生产数据规则。

### I06 · 草稿订单创建与完成
- 所属设计单元：BD03
- 提供方：Core `saleor/graphql/order/mutations/draft_order_create.py.DraftOrderCreate`、`draft_order_complete.py.DraftOrderComplete`
- 调用方：Dashboard OrderDraftList、OrderDraftDetails、OrderOperations、`src/orders/mutations.ts.OrderDraftFinalize`（FD04、FD06）
- 目标定义：`Mutation.draftOrderCreate/draftOrderComplete`、`DraftOrderCreateInput`、`DraftOrderComplete`、`Query.order`

```graphql
mutation CompleteCompatibleDraft($id: ID!) {
  draftOrderComplete(id: $id) {
    errors { field message code orderLines variants warehouse }
    order { id status }
  }
}
```

- 字段说明：`draftOrderCreate(input:DraftOrderCreateInput!):DraftOrderCreate`、`draftOrderComplete(id:ID!):DraftOrderComplete`可空payload；order可空；errors为`[OrderError!]!`；orderLines/variants为nullable非空项ID列表。Query.order(id:ID,externalReference:String):Order可空，标识语义沿用Base。
- 权限：MANAGE_ORDERS；complete显式检查员工渠道权限，App的渠道行为沿用Base。不能仅因公共helper存在就推断所有相关mutation采用相同渠道检查。
- 错误：非草稿重复complete为id/INVALID；缺库存等转typed OrderError，权限顶层。金额/税价刷新可能在完成原子区外，失败不承诺数据库绝对无任何更新；但受限完成不能执行。
- 完成判定：完成原子区更新订单/库存/预售/voucher等，on_commit执行地址/订单事件；errors空、order非空及重读实际状态才是完成，不固定预设UNFULFILLED/已付款。通知最终投递非同步成功前提。非草稿再complete不是幂等成功，不自动重试。
- 变更与兼容：签名、状态与校验不变；前端补错误/实体判定，不放宽草稿规则。

### I07 · 退款授予、资金请求与支付结果
- 所属设计单元：BD03
- 提供方：Core `saleor/graphql/order/mutations/order_grant_refund_create.py`、`saleor/graphql/order/mutations/order_grant_refund_update.py`、`saleor/graphql/order/mutations/order_refund.py`、`saleor/graphql/payment/mutations/transaction/transaction_request_refund_for_granted_refund.py`及既有商品退款/transaction mutations
- 调用方：Dashboard `src/orders/mutations.ts`、OrderRefund、OrderTransactionRefundCreate/Edit、手工transaction相关页（FD04、FD07）
- 目标定义：`Mutation.orderGrantRefundCreate/orderGrantRefundUpdate/orderRefund/transactionRequestRefundForGrantedRefund/orderFulfillmentRefundProducts/transactionRequestAction/transactionCreate`及完整结果/输入类型

```graphql
mutation SaveCompatibleGrantedRefund($orderId: ID!, $input: OrderGrantRefundCreateInput!) {
  orderGrantRefundCreate(id: $orderId, input: $input) {
    errors { field message code }
    grantedRefund { id }
    order { id }
  }
}
```

- 字段说明：create的id是Order ID，update的id是OrderGrantedRefund ID。create.input.transactionId为`ID!`；update.input.transactionId为`ID`可空（实际类型优先于历史说明里的“将必填”）。amount/reason/reasonReference可空；create.lines为`[OrderGrantRefundCreateLineInput!]`、update.addLines为`[OrderGrantRefundUpdateLineAddInput!]`、removeLines为`[ID!]`，列表可空/项非空；line.id/quantity必填，removeLines使用GrantedRefundLine ID而不是OrderLine ID。输入至少满足Base的amount/lines/shipping条件。
  - create/update返回order与grantedRefund可空，errors分别`[OrderGrantRefundCreateError!]!`/`[OrderGrantRefundUpdateError!]!`；嵌套line错误按完整类型。`orderRefund(amount:PositiveDecimal!,id:ID!):OrderRefund`走legacy Payment；`transactionRequestRefundForGrantedRefund(grantedRefundId:ID!,id:ID,token:UUID):TransactionRequestRefundForGrantedRefund`返回transaction可空/errors非空。两者不是同一实现。
- 权限：granted create/update、legacy orderRefund要求MANAGE_ORDERS；transaction refund请求要求HANDLE_PAYMENTS。orderRefund显式渠道检查，granted create/update当前未显式调用同helper，不凭空更改它们的授权规则；未来若需变化应获Q01/Q02确认。
- 错误：granted错误码含NOT_FOUND、INVALID、REQUIRED、AMOUNT_GREATER_THAN_AVAILABLE、SHIPPING_COSTS_ALREADY_GRANTED；line数量受可退上限。关联transaction必须属该订单；PENDING/SUCCESS granted记录仅严格reason更新按Base允许，不能简单把reasonReference当同样可更新。legacy付款缺失/不可退/网关失败沿用OrderError，事务请求按其域内错误，权限仍顶层。
- 完成判定：授予记录保存不意味着资金动作；退款请求接受不意味着外部支付成功。granted line保存使用既有事务，update后order charge更新并非全在同一atomic；legacy网关与本地数据库不可全原子回滚，失败可保留审计。UI按NONE/PENDING/FAILURE/SUCCESS及transaction事件和重读金额分层显示。无通用请求去重，超时不得自动再次退款。
- 变更与兼容：全部签名/状态/金额规则保留；商品退款/手工记录操作在完整SDL中保留，不归并到orderRefund。前端仅修复未等待请求、缺实体与误报最终成功。

### I08 · 渠道与仓库排序
- 所属设计单元：BD03
- 提供方：Core `saleor/graphql/channel/mutations/` 的ChannelCreate/ChannelUpdate/ChannelReorderWarehouses及现有读取
- 调用方：Dashboard `src/channels/mutations.ts`、ChannelCreate/useSaveChannel、ChannelDetails/useChannelWarehouseReorder（FD04、FD08）
- 目标定义：`Mutation.channelCreate/channelUpdate/channelReorderWarehouses`、`Query.channel/channels`及完整输入/结果

```graphql
mutation SaveCompatibleChannel($id: ID!, $input: ChannelUpdateInput!) {
  channelUpdate(id: $id, input: $input) {
    errors { field message code }
    channel { id slug isActive }
  }
}
```

- 字段说明：create(input:ChannelCreateInput!):ChannelCreate、update(id:ID!,input:ChannelUpdateInput!):ChannelUpdate；reorder(channelId:ID!,moves:[ReorderInput!]!):ChannelReorderWarehouses，moves列表/项必填但可[]。payload.channel可空/errors `[ChannelError!]!`。query.channel(id:ID,slug:String):Channel可空；channels为`[Channel!]`（列表可空、项非空）。settings详细类型及默认值保持完整SDL。
- 权限：一般MANAGE_CHANNELS；仅orderSettings更新可MANAGE_CHANNELS或MANAGE_ORDERS，仅checkoutSettings可MANAGE_CHANNELS或MANAGE_CHECKOUTS，仅paymentSettings可MANAGE_CHANNELS或HANDLE_PAYMENTS；混合写入不泛化这些例外。reorder保持MANAGE_CHANNELS，UI路由权限不因此自行放开。
- 错误：字段/关联/货币/删除等限制沿用ChannelError，权限顶层。第二次reorder失败不能掩盖为整体保存成功。
- 完成判定：update/create与reorder是独立请求；都成功且重读设置/顺序/关联后才显示完整成功。create后refetchUser更新可访问渠道。CHANNEL_CREATED/UPDATED/METADATA_UPDATED事件按Base触发，异步投递独立；不假装跨请求回滚。
- 变更与兼容：不改变SDL、激活/停用/删除及货币限制。前端聚合成功与失败结果，旧消费者不需改请求格式。

### I09 · 结算完成、支付确认与建单重入
- 所属设计单元：BD03
- 提供方：Core `saleor/graphql/checkout/mutations/checkout_complete.py.CheckoutComplete`、`saleor/checkout/complete_checkout.py`
- 调用方：外部店面/客户（允许匿名），Core结算回归；FD09仅观察跨端订单/库存结果，不新增Dashboard结算页
- 目标定义：`Mutation.checkoutComplete`、`CheckoutComplete`、`CheckoutError`、`Order`

```graphql
mutation CompleteCompatibleCheckout($id: ID!) {
  checkoutComplete(id: $id) {
    errors { field message code variants lines addressType }
    confirmationNeeded
    confirmationData
    order { id status }
  }
}
```

- 字段说明：完整参数`checkoutId:ID,id:ID,metadata:[MetadataInput!],paymentData:JSONString,redirectUrl:String,storeSource:Boolean=false,token:UUID`；前三种标识由业务要求**恰好一个**，不能省略全部或多传。旧checkoutId/token/storeSource弃用但保留。payload可空，order可空，confirmationNeeded为Boolean!、confirmationData为nullable JSONString、errors `[CheckoutError!]!`。settings的JSON!与这里JSONString不同，不统一替换。
- 权限：允许匿名客户完成checkout，不要求MANAGE_ORDERS。IMPERSONATE_USER只影响使用所属用户身份处理，非完成必需权限；不把metadata helper存在描述成所有请求均检查管理权限。
- 错误：地址/email/空行/商品/库存/支付/渠道失败沿用CheckoutError；inactive channel返回CHANNEL_INACTIVE。支付失败可保留付款/预留/审计记录，legacy路径有commit_on_errors策略，不承诺整请求所有数据回滚。
- 完成判定：confirmationNeeded=true且order=null是需二次支付确认，不算订单已建；支付确认后再调用。正常建单采用checkout锁及原子建单/分配，在commit后发order/notify事件。checkout不再存在时按其token查原订单且渠道有效可返回已有订单；这是特定重入行为，不基于Order.checkout_token唯一约束（该字段非unique），不推广为其他mutation幂等。
- 变更与兼容：SDL和业务规则全部不变，包含allowUnpaidOrders例外、旧Payment和Transaction路径。目标未授权改结算策略，不用dummy payment替代生产功能。

## 3. 其他

### 实际执行的静态检查与可复现证据

2026-10-13使用预装`graphql-js 16.11.0`在离线环境只读取材料，校验脚本/结果保存于`/workspace/scratch/validate-design.cjs`及`/workspace/scratch/schema-validation.json`，不属于生产代码。

| 检查 | 实际结果 |
| --- | --- |
| 完整Core Base SDL parse/buildSchema/validateSchema | 0错误；Base 35185行 |
| 完整目标SDL parse/buildSchema/validateSchema（含类型引用） | 0错误；目标35203行，全部未修改定义保留 |
| Base→target结构diff | 仅AppExtension/AppManifestExtension各新增3字段；0 breaking、0 dangerous；旧字段增加deprecated描述 |
| 两端原有SDL结构比较 | Dashboard较Core仅多这六字段，没有其他结构破坏性变化；不是上游target schema比较 |
| 契约文档9个GraphQL请求示例独立parse/validate | 全部0错误，与目标SDL字段/输入/类型引用一致 |
| 按codegen匹配范围提取documents | 620份提取文档（不等于620个唯一文件），643个原始定义，401operation |
| 原始聚合直接validate目标 | **失败1项**：重复PageTypeDeleteErrorFragment，两份均来自src/fragments/errors.ts，内容相同；未修改源文件 |
| 只去重同名且内容相同的fragment后 | 642定义＝401operation+241fragment；Core Base校验3错误（AppExtension三个缺字段）；目标校验0错误 |

聚合校验仅排除NoUnusedFragmentsRule（独立源fragment允许未被全局使用），其余specifiedRules执行；重复fragment冲突仍失败。没有排除未知字段、重复名称、变量/类型/枚举等错误规则。此结果证明当前**源操作静态可消费目标类型**，不证明生成产物、resolver或权限在运行时正确。

- Base SHA-256：`328f599c6a90be4f1b1cd366b48e470f2f26cb2304f00a9d577109d61976f71a`。
- 目标 SHA-256：`7ab4230561a99a672c646aa200834376221a64120e5d21a4cf1b2164dd77cccc`。
- 当前**未运行**：Core生产导出与目标语义比对、resolver/API权限/错误测试、数据库迁移、依赖安装/锁更新、Dashboard codegen/两次生成、类型检查、构建、浏览器、unit/e2e及正式F2P/P2P。这些均为后续验证门，不把静态通过当它们通过。

### 未决与稳定性

Q01—Q03仍阻塞完整目标业务、全量契约变化和真实模型变更，Q04阻塞正式评分，Q05阻塞旧入口删除，Q06阻塞全部生产发布入口结论。当前完整SDL是**本设计明确范围的完整接口目标**，不是完整上游3.23差异清单。不能因为存在mandatory SDL就编造新字段/目标行为，也不能因规格缺失省略本轮已证实接口变更。新增接口边界已全部登记I01—I03；未来获批差异稳定追加编号并同步SDL/两端设计，冻结PRD/测试保持不变。

本轮没有改变manifest JSON输入格式、iframe协议或REST/gRPC边界，不需要在interfaces/增加未知协议文件。SDL无法表达的枚举名称限制、settings对象形状、权限、幂等、异步状态与成功判定在本契约中定义，前后端共同引用。
