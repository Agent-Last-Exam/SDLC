# Stage 03: R07 外部产品图片异步下载与失败回退剪枝记录

## 1. 决策

- 功能：外部产品图片异步下载、pending 图片代理状态和 Dashboard 加载失败回退。
- 主体关联度：弱到中；它改变媒体导入的执行方式和失败展示，但不是 Checkout、库存、支付、订单生成或订单操作主链。
- 处理决定：删除 Target 新增的异步能力，恢复并保留 Base 已有的同步 `mediaUrl` 图片下载合同。
- Core 父快照：阶段 02 累计 commit `75a536196270e8f76ae1f4707d08339876327ae5`，tree `e6506f2c2594b9d465a52e5dfa4a1769cd9660ef`。
- Core 输出：commit `0c1df570e4afe0c8315b58069b1652e9a174d902`，tree `4638d44447beff6a1d57cc2fa7d2997b31f56365`。
- Dashboard 父快照：阶段 02 commit `57ffe57cbcd1aeaf4be2f81e6add470910e87e36`，tree `584b30aca6f25b0ed44622b3040e782388fe5914`。
- Dashboard 输出：commit `05dea6f0fc8cbc8e4800ec25dff8bcfb3ae57d9f`，tree `713d53f9eca6a6084e59b6a56056d2285db260fc`。

## 2. 证据和边界

Git 参考为 Core `114553593e43db990a55bad6c40b69dcaa51e3d6`（`Fetch product media images asynchronously (#18971)`）和 Dashboard `e7890fceb028e2500db45b2b7e6e2401a36e3d3a`（`Add MediaFallback component for graceful image error handling (#6421)`）。提交只用于确认设计意图，最终边界来自 Base/code patch/test patch、schema 和调用方。

Base 已支持 `productMediaCreate` 和 `productBulkCreate` 的 `mediaUrl`：mutation 同步请求 URL，图片内容立即写入媒体文件；非图片 URL 仍走 oEmbed。因而 `mediaUrl` 输入和 Dashboard 外部 URL 上传入口不是 R07 新功能，不能随异步实现删除。

删除：

- `fetch_product_media_image_task`、失败处理和 `FETCH_IMAGES_QUEUE_NAME` 专用队列。
- 只保存 `external_url`、尚无图片文件的 pending IMAGE 状态及其 probe/task 工具。
- pending thumbnail/original image 的 HTTP 503、`Retry-After` 和原图 proxy endpoint。
- Dashboard `MediaWithFallback`、Story、消息和产品媒体页面中的失败占位接入。
- 只验证上述异步、pending、proxy 和 fallback 行为的测试与 fixture。

保留：

- `ProductMediaCreateInput.mediaUrl` 和 bulk-create media URL 输入。
- 同步 `HTTPClient.send_request` 图片下载、MIME 校验和文件创建。
- 本地文件上传、外部视频/oEmbed、普通商品媒体展示。
- Dashboard `ProductExternalMediaDialog` 及外链上传入口。
- 共享文件中仍服务于同步行为的校验、文件名和媒体类型逻辑。

本阶段没有新增或删除 migration。重新运行 `python manage.py get_graphql_schema` 后，生成结果与仓库中的 `saleor/graphql/schema.graphql` 一致，公开 GraphQL 输入合同不变。

## 3. 改动量

- Core：22 个文件，350 行新增、1,292 行删除。新增行主要是把 Target 抽取/替换掉的 Base 同步下载实现恢复到 mutation 和 GraphQL file validators，不是增加另一套媒体功能。
- Dashboard：7 个文件，3 行新增、148 行删除。
- Core 专用工具测试、task 测试、mutation/query 测试和 thumbnail view 测试同步清理；Dashboard fallback Story 和 locale 同步清理。

## 4. 测试名单

从冻结名单删除 83 个只验证 R07 被删合同的 ID，原因均为 `excluded R07 asynchronous external product media feature`：

| 分类 | F2P | P2P |
| --- | ---: | ---: |
| MIME/content-type 专用 validator | 23 | 0 |
| bulk create 异步媒体行为 | 10 | 0 |
| media create 异步媒体行为 | 10 | 0 |
| pending media GraphQL URL | 2 | 0 |
| 异步抓取 task、重试与失败处理 | 25 | 0 |
| thumbnail/original proxy | 8 | 5 |
| 合计 | 78 | 5 |

审计清单位于 `reports/stage-03-r07-external-media/dropped-f2p.json`；文件名沿用早期命名，但内容同时含 `f2p_ids` 和 `p2p_ids`。

最终冻结名单为 F2P 5,771、P2P 7,021，共 12,792 个评分 ID。正式结果：

- Core unit：普通 9,976/9,976，garbage-collection 10/10，合计 9,986/9,986。
- Core E2E：24/24。
- Dashboard unit：2,616/2,616；Jest 另报 6 个 skipped，均不属于评分 ID。
- Dashboard E2E：166/166，setup 15/15。
- Grader：F2P `5,771/5,771`、P2P `7,021/7,021`、`reward=1`。

Dashboard E2E 首轮为 165 passed、1 failed。`SALEOR_44` 在删除多个商品时点击 loading/即将替换的确认按钮，页面拦截 pointer event 并在 35 秒超时；其调用链与 R07 无关。未修改生产代码、测试断言或超时；重新执行标准 seed 后定向重跑为 passed。最终 `results.json` 只用该成功对象替换同 ID 的失败对象，保留首轮其余结果与 15 个 setup；合并脚本、首轮报告、重跑报告和 seed 日志均已留存。

## 5. 完整性检查

- Core Ruff、`compileall`、受影响测试（300 passed、1 skipped）通过。
- `makemigrations --check`：无变化。
- GraphQL schema 重新生成后一致。早期尝试的 `graphql_schema` 不是本版本命令；正确命令为 `get_graphql_schema`。
- Dashboard 定向 ESLint：0 errors、12 个既有 warnings。
- Dashboard `generate`、`extract-messages`、source typecheck（3,017 strict files）和 production build 通过。
- 空数据库 migration、`populatedb`、API/Celery/nginx 启动和标准 E2E seed 通过。

## 6. Patch 与复现

| 仓库/类型 | 文件数 | bytes | SHA-256 |
| --- | ---: | ---: | --- |
| Core 累计 code | 587 | 2,020,161 | `8bae41b73ef947b44376dbc38daf616f1d652529c484ee654ed85426cf9e81c6` |
| Core 累计 test | 472 | 3,154,667 | `07a76a5dc34d410b073867f8e2fe7c20d468b769bd872e9c7aa62eb35c1370ae` |
| Core 阶段增量 | 22 | 72,401 | `ed770848f2690b34bf1e769b626daa060ba5c40d8674e09d2e344477d4b0d0bd` |
| Dashboard 累计 code | 3,034 | 18,267,537 | `eda5bc8c006f6e8701546c8a09275c2bc282768375efee39198850ce48a5a882` |
| Dashboard 累计 test | 475 | 1,313,996 | `8a5ab66bd4089932caaef9dc781a7c02d0f3788131f1c91000c59594d0e5f8f2` |
| Dashboard 阶段增量 | 7 | 7,412 | `38b59eb76071f642c102ac55ab137ca3d4f99ae64b05d6f94237e6ec79b43082` |

累计 patch 的 `code -> test` 与 `test -> code` 均得到 Core tree `4638d44447beff6a1d57cc2fa7d2997b31f56365` 和 Dashboard tree `713d53f9eca6a6084e59b6a56056d2285db260fc`；阶段增量 patch 也能从各自父快照得到相同 tree。

全程复用 `sdlcbench/saleor-3.23-test:standard-a-20260920` 和长驻容器 `saleor-stage03-validation`，通过 bind mount 注入工作树、配置和报告目录。没有重建镜像，也没有使用 `docker commit`。
