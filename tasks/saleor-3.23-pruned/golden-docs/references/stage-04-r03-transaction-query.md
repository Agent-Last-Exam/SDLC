# Stage 04-A: R03 Transaction 查询增强剪枝记录

## 1. 决策

- 功能：Transaction 创建/修改时间筛选、event 类型/时间筛选及创建/修改时间排序。
- 主体关联度：弱；它是后台查询增强，不承担 Checkout、支付执行、订单生成或 Dashboard 订单交易操作。
- 处理决定：删除上述 R03 增强，保留根级 `transactions` query、`TransactionWhereInput` 以及 ID、`pspReference`、`appIdentifier` 基础 where。
- Core 父快照：阶段 03 commit `0c1df570e4afe0c8315b58069b1652e9a174d902`，tree `4638d44447beff6a1d57cc2fa7d2997b31f56365`。
- Core 输出：commit `209391c036ad9fe75f8bf4a5a5a198ff5be3f4ff`，tree `f3bef3f74c0a614c24a94d575a3dca6f55174d03`。
- Dashboard 未改：commit `05dea6f0fc8cbc8e4800ec25dff8bcfb3ae57d9f`，tree `713d53f9eca6a6084e59b6a56056d2285db260fc`。

## 2. 证据和边界

Git 参考为 Core `8116df6e0d927d5d14e7f00015cf11c35cf9280a`（`Extend transactions sorting and filtering (#18949)`）。需求文档曾记录短 hash `4d333d0`，但本地历史不存在该对象；最终边界由 Base、Target、code/test patch、schema、migration 和 `8116df6` 交叉确认，不依赖缺失的 commit。

删除：

- `TransactionWhereInput` 中 `createdAt`、`modifiedAt` 和 `events` 条件。
- transaction event 的 type/date where input 与 resolver 分支。
- `sortBy`、`TransactionSortingInput` 和 `TransactionSortField`。
- transaction/event 的四个 date/type 专用索引。
- 叶子 migration `saleor/payment/migrations/0072_transaction_date_indexes.py`。
- 只验证这些筛选、排序和索引的测试、changelog 及专用规则说明。

保留：

- 根级 `transactions = FilterConnectionField(...)` 与权限、分页和 resolver。
- `TransactionWhereInput` 及 ID、`pspReference`、`appIdentifier` 条件。
- `psp_reference_idx` 和 `app_identifier_idx` 两个基础索引。
- R02 礼品卡 Transaction 支付、退款、事件、订单查询和 Dashboard 交易展示。
- R12 Dashboard 订单金额、capture、transaction action 和订单详情能力。

Dashboard 没有调用 R03 的 transaction date/event where 或 `sortBy`，所以本阶段没有 Dashboard 源码增量。不能因为删除查询增强而删除基础 transaction query 或 R02/R12 支付合同。

## 3. 改动量和 migration

- Core：10 个文件，4 行新增、1,181 行删除。
- Dashboard：0 个文件变化。
- `0072_transaction_date_indexes.py` 是依赖 `payment.0071` 的叶子 migration，没有后继 migration 依赖它。
- 空数据库全量 migration 成功，payment graph 终点回到 `0071`。
- `makemigrations --check --dry-run` 返回 `No changes detected`。
- `python manage.py get_graphql_schema` 生成结果与仓库 schema 完全一致。

## 4. 测试名单和正式结果

从 F2P 删除 18 个仅验证 R03 date/event where 和 sort 的 ID；P2P 删除 0 个。完整清单位于 `reports/stage-04-r03-transaction-query/dropped-ids.json`，统一原因是 `excluded R03 transaction date event filtering and sorting`。

保留的 24 个 ID/PSP/app transaction where 定向测试全部通过。最终冻结名单为 F2P 5,753、P2P 7,021，共 12,774 个评分 ID。正式结果：

- Core unit：普通 9,958/9,958，garbage-collection 10/10，合计 9,968/9,968。
- Core E2E：24/24。
- Dashboard unit：2,616/2,616；Jest 另报 6 个 skipped，均不属于评分 ID。
- Dashboard E2E：166/166，setup 15/15。
- Grader：F2P `5,753/5,753`、P2P `7,021/7,021`、`reward=1`。

Dashboard E2E 保留了完整原始失败证据。首次有效完整运行因环境负载和 destructive fixtures 状态串扰出现 110 passed、71 failed；重新标准 seed 后收敛为 172 passed、9 failed。对 9 个失败评分 ID 单 worker 隔离复跑后，5 个直接通过；其余 4 个暴露长期容器 seeder 的幂等缺口：channel 的开关未恢复初始状态，软删除 App 的 `removed_at` 未清空。只修复 `seed_e2e_fixtures.py` 的 fixture 重置，不修改产品代码、测试、断言或超时。修复后 3 个通过，剩余 `SALEOR_44` 与阶段 03 相同，因 loading 按钮 DOM 替换导致原始 35 秒超时；再次标准 seed 后单项通过。

最终 `results.json` 按 `(project, file, spec id, title)` 严格替换第二轮完整报告中的 9 个失败对象，保留其余结果和 15 个 setup。原始报告、每轮 rerun、seed 日志和合并脚本均位于阶段报告/验证目录。

## 5. 无效尝试和环境修正

- 首次 Ruff 把 `AGENTS.md`、`CHANGELOG.md` 当成 Python，产生语法噪声；改为只检查 Python 文件后通过。
- 首次 focused pytest 在 PostgreSQL 尚未启动时全部 fixture setup `connection refused`；启动既定 services 后为 24 passed。
- 首次 Dashboard E2E 时新 worktree 没有未跟踪的 `build/`，API 200、nginx Dashboard 500，整轮作废。
- 手工 production build 首次继承镜像 `STATIC_URL=/static/`，而 nginx root 直接服务 build 目录，JS/CSS 请求回退为 HTML，浏览器空白；按 `start-services.sh` 的 `STATIC_URL=/` 参数重新 build 后资源 MIME 和页面恢复。该轮在连续超时后终止，没有作为测试证据。
- 长驻容器重复执行 destructive E2E 暴露 seeder 没有重置 channel 状态和软删除 App；已同步修复 environment/runtime 与 verifier 两份 seeder。

## 6. Patch、复现和容器

| 仓库/类型 | 文件数 | bytes | SHA-256 |
| --- | ---: | ---: | --- |
| Core 累计 code | 585 | 2,010,919 | `77be33ead6921cc3b5b4663b53fd85a5d3608cf7484137d6001c032ceb9a6491` |
| Core 累计 test | 471 | 3,125,105 | `bbe0658a88d0e936792f6a73a822b2ff499202790e9bbcc5e8655479c2562493` |
| Core 阶段增量 | 10 | 42,099 | `7d18f29aac70d3a382d6860ced6836ff9f7f3cd10e973ae169080f92dfacf37d` |
| Dashboard 累计 code | 3,034 | 18,267,537 | `eda5bc8c006f6e8701546c8a09275c2bc282768375efee39198850ce48a5a882` |
| Dashboard 累计 test | 475 | 1,313,996 | `8a5ab66bd4089932caaef9dc781a7c02d0f3788131f1c91000c59594d0e5f8f2` |
| Dashboard 阶段增量 | 0 | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |

累计 patch 的 `code -> test` 与 `test -> code` 均得到 Core tree `f3bef3f74c0a614c24a94d575a3dca6f55174d03` 和 Dashboard tree `713d53f9eca6a6084e59b6a56056d2285db260fc`。阶段增量也从阶段 03 父快照得到同一输出 tree。

本阶段复用镜像 `sdlcbench/saleor-3.23-test:standard-a-20260920`（ID `sha256:34b08f53da5c6b0c7ddbac1a12713a6961be8471df5952bc684349c3cd2d80b0`）和长驻容器 `saleor-stage04-tooling`。没有重建镜像，也没有使用 `docker commit`。

R06 跨对象增强搜索尚未开始。它跨 product/order/gift-card/checkout/page/user、search vector、dirty flag、tasks 和 migrations，应作为 Stage 04-B 独立执行，不能与已验收的 R03 一次性合并删除。
