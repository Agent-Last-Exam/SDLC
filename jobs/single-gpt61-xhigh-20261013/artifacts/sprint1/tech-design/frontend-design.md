# 前端技术设计：Saleor Core 与 Dashboard 协同迁移至 3.23.0

版本：v1
责任：前端技术设计
依据：PRD v1，artifacts/sprint1/prd/prd.md
修订：首次交付（2026-10-13）；按真实 Dashboard 消费、错误与构建链设计；目标协议集中引用接口契约，不编造未确认的3.23新页面或业务规则。

## 1. 方案概述

继续使用现有 React/TypeScript 单页、React Router v5、Apollo、Saleor SDK 认证、React Intl 与现有 UI组件。实际 `package.json` 为 React 18.3.1、Apollo 3.4.17、GraphQL 16.11.0、TypeScript 5.8.3、Vite 7.3.1、Node 24/pnpm 10.28.1；不沿用说明文档中的 React17/npm 假设，也不做框架或认证重写。仓库 `/workspace/repos/saleor-dashboard`，本阶段代码只读。

方案分为：版本/工具链一致化（FD01），本地唯一 schema及四生成产物（FD02），已有 App 扩展新字段消费与旧预览兼容（FD03），可靠错误/提交状态（FD04），商品/订单/退款/渠道的持久化回归（FD05—FD08），验证与交付（FD09）。不用新 feature flag 掩盖缺失生产能力，不根据版本名称启用 `new_order_ui` 或删除旧URL。

Core Base与Dashboard Base存在明确六字段差异，I02的三字段在 `src/extensions/queries.ts.ExtensionList` 已消费；I03的manifest预览仍读取旧枚举。后端BD02补齐派生字段且保留旧API；前端不需要双schema或临时mock服务。本设计的完整目标SDL可静态验证全部当前操作，但完整3.23行为仍受PRD Q01/Q02限制。

## 2. 需求覆盖

| 需求 | 设计单元 |
| --- | --- |
| R01 | FD01、FD03、FD09 |
| R02 | FD02、FD03、FD04、FD05—FD08 |
| R03 | FD02、FD03、FD09 |
| R04 | FD03—FD08 |
| R06 | FD01、FD02、FD09 |
| R07 | FD09 |
| R08 | FD09 |

R05不由前端实现数据库迁移；FD05—FD08承担升级后对象/金额/渠道/关联的回读，等待BD04数据库可用。R01未知目标业务不由已有回归流程代替，Q01确认后追加稳定FD编号。PRD中“本阶段只写PRD”属上一阶段说明，当前遵守技术设计阶段范围，冻结文件仍保持只读。

## 3. 详细设计

### FD01 · 版本、工具链与离线构建入口
- 覆盖需求：R01、R06
- 设计说明：
  - 实施落点 `package.json.version=3.23.0`、`config.saleor.schemaVersion=3.23`、根锁文件/发布配置及`src/config.ts.APP_VERSION`。保留合法的CUSTOM_VERSION使用方式，但批准环境不得把真实3.23发布覆盖展示为旧版；Vite注入的RELEASE_NAME跟随版本，不人工分叉。
  - 继续现有Node24/pnpm10/`pnpm-lock.yaml`/`pnpm-workspace.yaml`。Dockerfile与`.github/workflows/main.yml`若在批准入口范围，改为相同工具链和锁文件；不能遗留Node20/npm ci并称其已验证。离线缺镜像/缓存则报告阻塞，不联网拉取。
  - 本地target依赖manifest只用于核对可用包和版本，不直接整份覆盖。它的main/staging codegen脚本依赖不存在的目标配置/两份schema，本轮保留单schema工作流，不凭依赖清单引入未知staging契约。
  - 实施验证顺序为离线依赖一致性→生成→`check-types:src/check-types:playwright`→build。`lint`包含`--fix/--write`，本阶段不运行；实施只读lint使用不自动修复的等效入口。当前未执行这些命令。

### FD02 · 唯一生产schema与四类生成产物
- 覆盖需求：R02、R03、R06
- 设计说明：
  - 权威输入最终来自BD02/BT05的Core生产导出；同步`schema.graphql`，不执行联网`fetch-schema`。当前`target-schema.graphql`为设计目标，不把文件存在当resolver已经实现。优先复制Core导出以保留自定义directive；若使用本地introspection，语义比较须考虑其不保留部分应用directive注解，不将格式差异误判成业务变化。
  - 按现有`codegen.ts`：`src/**/queries.ts`、`src/**/mutations.ts`、`src/**/fragments/*.ts`、`src/searches/*.ts`为documents。生成`src/graphql/fragmentTypes.generated.ts`、`typePolicies.generated.ts`、`types.generated.ts`、`hooks.generated.ts`；不手改生成代码。
  - 实际缓存`src/graphql/client.ts.apolloClient`使用possibleTypes；TypedTypePolicies仅约束手写cache policy，不是自动生成整套运行时策略。新增的六字段是对象标量字段，不修改ID/cache key；现有AppExtension节点仍按ID归一化。
  - 生成hooks使用`@dashboard/hooks/graphql`包装，保留PERMISSION变量注入及错误处理。SDL JSON映射和运行数据分开：generated类型不能保证settings对象形状，FD03仍作边界校验。
  - 静态提取发现`src/fragments/errors.ts`的同名`PageTypeDeleteErrorFragment`被两次取得，内容一致。检查时仅合并**同名且打印内容相同**的fragment；若内容冲突必须失败。不要为消除重复修改冻结测试。真实codegen是否自带去重须在实施阶段验证，不能凭静态聚合通过宣称生成成功。
  - 验证：全量操作校验、两次相同输入生成无差异、类型检查、构建；扩展运行查询与旧安装预览分别联调。实际静态结果见接口契约§3，运行生成尚未执行。

### FD03 · App扩展运行挂载与旧manifest预览兼容
- 覆盖需求：R01、R02、R03、R04
- 设计说明：
  - 路径：`src/extensions/queries.ts.extensionList`→`src/extensions/hooks/useExtensions.ts.prepareExtensionsWithActions`→AppExtensionContext/AppWidgets。保持I02的新三字段及`filter.mount`使用旧Enum。安装预览`src/fragments/apps.ts.appManifestFragment`→`src/extensions/mutations.ts.AppFetch`→`useFetchManifest`仍读取I03旧`mount/target`，不强制替换。
  - JSON要求和大小写仅引用I02/I03权威契约。有效settings为对象，缺省`{}`；GET/POST按target打开，默认GET；不得把JSON字符串再容错解析为有效对象，掩盖后端契约错误。
  - 当前对mountName/targetName使用Zod `.parse`可能把单个异常扩展升级为整个页面抛错。实施调整为边界`safeParse`：有效项继续渲染，无效项不给可执行action并给局部错误/可诊断信息；不猜测默认mount/target，不越过URL或权限校验。此为接口异常处理，不扩展可用挂载点。
  - 保持http/https URL限制、token/context规则。settings不包含token/私有metadata；权限不足时accessToken可空，不自行生成认证令牌。WIDGET GET使用AppFrame，POST使用IframePost；NEW_TAB按method调用原行为。安装是否可用沿用`ExtensionManifestValidator/canInstall`，不借文案矛盾绕过验证。
  - 验证矩阵：四target、现有mount、无options/GET/POST、旧字段预览、受限用户、无效settings/null、非法URL。读取异常应局部失败，不显示“安装/打开成功”。I04安装是异步，须待实际状态和扩展重读，不凭mutation回包宣称完成。

### FD04 · 错误分层、鉴权与可靠提交状态
- 覆盖需求：R02、R04
- 设计说明：
  - 保留`src/graphql/client.ts`的业务Apollo客户端与SDK `saleorClient`职责：SDK认证和`createFetch`，Apollo业务/上传/cache；`credentials:include`与runtime API_URL保持。不要因为deprecated TODO更换整套认证。
  - `src/hooks/makeQuery.ts`当前`cache-and-network/errorPolicy:all`允许data+errors；partial data只用于受控展示，不能为缺失对象自动填写成功数据。`makeMutation.ts`处理nested errors后仍调页面callback，callback必须自行确认成功，不能假定onCompleted=业务成功。
  - 实施集中完善`src/misc.ts.getMutationStatus/getMutationErrors`或在调用层提供共用提交结果判定：transport/top-level error优先为失败；无payload/缺必要实体为失败；所有相关root和bulk result的typed errors非空为失败；pending期间禁止重复提交；只有全部必要步骤完成且结果对象有效才给成功。不要用“无data→errors=[]”判成功。保留现有错误字段映射、国际化文案与toast策略，避免重复通知。
  - 多步骤本地状态统一为idle/submitting/partial-failure/success（前端状态而非新增服务器enum）；保存成功但后续步骤失败时展示已保存部分，保存表单/返回错误，不自动再次创建。最终回读失败时显示“已提交，验证失败/请刷新”，不要重发已提交请求。
  - 保持JWT失效logout/sessionExpired、logout清Apollo store；`useAuthProvider`要求staff/有效权限，`SectionRoute`在用户未知时不渲染并按all/any权限匹配。UI权限/accessibleChannels只控制交互，服务端拒绝是最终边界；不扩大后台权限。
  - 验证：网络失败、HTTP200顶层GraphQL errors、PermissionDenied、JWT、payload errors、空实体、多root局部失败、旧缓存与切换用户。统一状态函数变更影响多页，先运行其现有单测与依赖页回归，不能为了某场景全局放宽错误规则。

### FD05 · 商品/变体多步骤持久化及旧链接
- 覆盖需求：R02、R04
- 设计说明：
  - `src/products/views/ProductVariantCreate.tsx`依次上传→VariantCreate→渠道listing→metadata；将成功通知/导航移到所有必需步骤完成后，检查每步errors和有效variant.id。后续失败保留创建结果，提供编辑恢复，不重试VariantCreate。
  - `src/products/views/ProductVariant/ProductVariant.tsx`与`useSubmitChannels.ts`组合库存根、变体更新、渠道、media、metadata；检查同一个VariantUpdate文档中的stock create/update/delete与productVariantUpdate各payload，删除渠道的listing也必须提取errors。聚合pending/失败，不能只以变体root成功提示全部保存。
  - I05多个Mutation根串行并不构成跨请求原子事务；失败信息指明哪部分已保存，重读SKU/属性/库存/价格/渠道/metadata确认。金额使用既有表单/Decimal输入规范，不以JS浮点累计改变服务器金额。
  - 保留`productVariantLegacyEditPath`及`src/products/index.tsx`旧`/products/:productId/variant/:variantId`→新`/products/variant/:variantId`重定向，保留`location.search`并维持路由优先顺序。Q05确认前不删除旧链接。
  - 验证：有权限正向创建/编辑；库存root失败、渠道第二步失败、metadata失败、缺实体、受限员工；刷新重读；旧URL的ID、query/action无丢失。正常成功行为不改。

### FD06 · 草稿订单创建、编辑与完成
- 覆盖需求：R02、R04
- 设计说明：
  - `src/orders/views/OrderDraftList/OrderDraftList.tsx`创建callback先检查typed errors及order.id再导航，错误保留dialog/输入。`OrderDraftDetails`继续按channel.slug查变体及允许的地址/库存/发布条件。
  - `src/orders/containers/OrderOperations.tsx.finalizeDraft`→OrderDraftFinalize→I06；完成按钮等待所有必需编辑请求及finalize完成。成功判定沿用`OrderDetailsMessages.handleDraftFinalize`的errors检查并补返回实体检查，重读订单状态及lines/customer/address/shipping/total。
  - 状态以服务器DRAFT/UNCONFIRMED/其他实际值呈现，不把离开草稿页硬编码为已付款/已确认。服务端非草稿再complete会报INVALID，不能自动重试重复完成。
  - 验证：创建空order/errors、编辑失败、库存不足、无权限/不可访问渠道、完成后重读与重复点击。接口typed错误展示在既有表单区域，禁止失败toast成功或进入不存在订单。

### FD07 · 退款草稿、请求及最终状态分离
- 覆盖需求：R02、R04
- 设计说明：
  - `OrderRefund/OrderRefund.tsx`legacy miscellaneous分支必须return/await错误提取，提交状态覆盖实际请求。商品退款沿用独立product退款操作，不能把它等同`orderRefund`；其SDL已保留，未改业务规则。
  - `OrderTransactionRefundCreate/handlers.ts`创建granted refund只在errors空且grantedRefund.id有效时显示“退款草稿已保存”，不使用空字符串fallback导航。edit/send经I07 `transactionRequestRefundForGrantedRefund` errors空仅代表请求接受，随后按实际NONE/PENDING/FAILURE/SUCCESS及transaction events展示，不能toast“已到账”。
  - 手工transaction action、手工退款记录与legacy Payment退款保持各自链路；禁止未知结果自动重试资金动作。网络超时先重读交易/授予退款记录，必要时由用户明确操作，不新增前端幂等键假装后端支持。
  - 金额、订单行ID/退款行ID、理由reference及transaction关联规则引用I07，不放宽超额/已退款限制；客户端预校验只改善交互，不能代替Core检查。
  - 验证：空/超额金额、权限拒绝、草稿保存、请求接受pending、最终failure/success、timeout重读、返回实体空、支付方式不同。退款表/订单详情重读金额/状态，区分系统记录与外部资金状态。

### FD08 · 渠道设置与仓库顺序完整提交
- 覆盖需求：R02、R04
- 设计说明：
  - `src/channels/views/ChannelCreate/useSaveChannel.ts`：create→warehouse reorder→refetchUser；`ChannelDetails.tsx`：update→reorder。两个阶段的transport/top-level/payload errors均纳入整体返回值，成功toast延后，保留channel.id供恢复。`useChannelWarehouseReorder`局部错误不能同时显示整体成功。
  - 保存后重读payment/order/checkout/stock settings、shipping关联、仓库顺序和isActive；创建后更新accessibleChannels，避免成功页面却无法访问。输入字段/货币/迁移目标限制与I08/Base保持一致，不增加对全部渠道的访问。
  - 权限保持入口MANAGE_CHANNELS，服务端针对单一settings的例外见I08；不借服务端例外自行放开未确认的新页面入口。
  - 验证：创建/更新正常；reorder失败后的部分成功、再次只重试失败步骤、激活停用/删除错误、无权限；重新进入详情验证持久化，不只查看toast。

### FD09 · 联调验证、差异交付与冻结保护
- 覆盖需求：R03、R06、R07、R08
- 设计说明：
  - 后续工程顺序：FD01可与BT02并行；BT05 schema交付→FD02生成→FD03扩展联调；FD04共用错误门后实现FD05—FD08的局部提交聚合；最后类型/构建与真实四套件。FD04全局函数与局部页面避免并发写相同文件。
  - 仅提交普通源diff：SDL/operations/fragments/四产物/页面与必要依赖配置；不改官方测试、fixtures、verifier和评分配置。不把scratch校验脚本当生产功能。
  - 真实配对服务执行商品、草稿/退款、渠道/权限回归并通过API重读；全量dash-unit/dash-e2e由规定运行器执行，联合Core结果核对选定ID完整性。健康检查、构建和截图不代替测试结果。
  - Q01/Q02未闭合前只结论为已知兼容范围；Q04未冻结前只报告本地/候选验证。本阶段实际静态校验范围在接口契约§3；codegen/build/types/unit/e2e均未执行。

## 4. 依赖与联调

| 接口 | 消费方设计单元 | 对应需求 | 开发依赖 |
| --- | --- | --- | --- |
| I01 | FD01 | R01 | 版本配置可独立；真实读取等待BD01 |
| I02 | FD02、FD03 | R02、R03、R04 | 静态类型准备可独立；运行挂载等待BD02/BT05 |
| I03 | FD03 | R02、R03 | 旧预览可独立回归；新字段映射等待BD02 |
| I04 | FD03 | R04 | 保持生命周期；真实安装需批准的本地manifest服务与BD02 |
| I05 | FD04、FD05 | R02、R04 | 基线操作不改可独立；最终联调等待统一schema和BD04环境 |
| I06 | FD04、FD06 | R02、R04 | 提交聚合可独立；完成/权限/重读需Core |
| I07 | FD04、FD07 | R02、R04 | UI状态可独立；资金/事件验证需对应插件或获准本地支付测试环境 |
| I08 | FD04、FD08 | R02、R04 | 聚合可独立；仓库及设置持久化需Core |
| I09 | FD09（跨端回归观察，不新增Dashboard结算页） | R04、R08 | 需Core结算/库存/支付环境 |

开发隔离只使用开发阶段自有单测mock（不修改冻结fixtures）：按目标SDL构造有效对象与transport/top-level/typed error案例，用真实settings对象和有效实体ID。mock验证页面行为，不作为生产API通过证据。I04 manifest服务使用本地授权URL，不依赖外网；GraphQL入口协议不变，无额外REST/gRPC待对齐。

## 5. 其他

- 未决：PRD Q01完整目标页面/行为、Q02全部契约、Q03目标模型、Q04正式清单、Q05删除边界、Q06批准发布入口；各项不通过本设计“猜测完成”。FD02的单schema决策不意味着未来staging能力被业务否定，只是没有目标源文件/规格依据，当前不盲复制。
- 风险：共享错误函数会影响大量页；多步请求已部分成功不能假装原子回滚；订单/退款异步状态可能被旧缓存暂存。用聚合结果、有效实体、明确partial-failure和重读解决，不放宽服务器校验。
- 本轮无新增页面路由/REST API/业务enum；FD04前端本地状态不进入SDL。前端文件引用接口编号，不重复定义字段和权限权威。
- 当前已完成静态schema与全量操作检查，重复fragment原始聚合失败已如实记录；去重相同fragment后目标0错误。未执行生成、构建、类型、浏览器和运行套件，不能宣称3.23功能/回归或正式验收已经通过。
