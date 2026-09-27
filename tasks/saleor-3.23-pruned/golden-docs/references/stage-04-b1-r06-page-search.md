# Stage 04-B1: R06 Page 搜索增强剪枝记录

## 1. 决策与快照

- 功能：Page/Model search vector、dirty flag、后台更新任务、属性/PageType 内容索引、相关度排序和专用数据库索引。
- 主体关联度：弱；不承担 Checkout、库存、支付、订单生成或 Dashboard 订单操作。
- 处理决定：删除 Page 的增强搜索实现，恢复 Base 已有的 title/slug/content 搜索；保留 `pages(search:)` API、Page CRUD、EditorJS 和 Product 对 Page reference 的搜索一致性。
- Core 父快照：阶段 04-A commit `209391c036ad9fe75f8bf4a5a5a198ff5be3f4ff`，tree `f3bef3f74c0a614c24a94d575a3dca6f55174d03`。
- Core 输出：commit `50c797102`，tree `ea83176de24d437bbd11df0abbbb985d98849052`。
- Dashboard 未改：commit `05dea6f0fc8cbc8e4800ec25dff8bcfb3ae57d9f`，tree `713d53f9eca6a6084e59b6a56056d2285db260fc`。

## 2. 证据与删除边界

主要 Git 参考为 `2c9e8869e02407b69387274d034d480d4c8bc8e2`（Improve page search）和 `1233f8eb3c565b16ea4b0d413836e0fcc48d0ea4`（Improve searching experience）。本地裁剪仓库最初缺少 `2c9e886` 对象，已从上游拉取用于理解影响面；最终边界仍由 Base、当前累计 code/test patch、schema、migration、冻结测试和 Dashboard 调用方共同确定。

删除：

- Page 的 `search_vector`、`search_index_dirty` 字段及更新/锁定/batch task。
- Attribute、Page、PageType mutation 对 Page dirty flag 的传播。
- Page 标题、slug、content、属性值和 PageType 信息的 vector 构建。
- Page 搜索的 prefix query、默认相关度及 `PageSortField.RANK`。
- Celery beat Page 搜索调度和 Page 索引上限设置。
- migrations `0032` 到 `0035`，以及专用 query/task/vector/dirty tests 和 changelog。

恢复或保留：

- `pages(search:)` 与旧 `PageFilterInput.search` API。
- Base 的 title trigram、slug trigram、content `icontains` 搜索及 10 个参数化回归用例。
- Page CRUD、PageType/attribute 管理、EditorJS sanitizer 和普通 slug 查询。
- Product 搜索向量中的 Page reference title，以及 Page 改名/删除时标记 Product 索引为 dirty 的四个冻结 F2P。
- checkout、user、gift-card、order、product 的 R06 搜索增强，本子阶段未触碰。

Dashboard 的 Page 列表、模型引用选择器和全局搜索确实发送 `pages(search: ...)`，因此 API 不得删除。Dashboard 未请求 Page `RANK`，本阶段没有 Dashboard 源码变化。

## 3. Migration、schema 与改动量

- `0032` 新增 Page vector/dirty，`0033` 新增 vector GIN，`0034` 删除 Base title/slug GIN，`0035` 新增 slug BTree；四者构成当前 Page migration 尾部链，整体删除后恢复 `0031` 为终点。
- 空数据库全量 migration 成功；`showmigrations page` 终点为 `0031`。
- `makemigrations --check --dry-run` 返回 `No changes detected`。
- `get_graphql_schema` 与仓库 schema 一致；公开合同只移除 `PageSortField.RANK`，`pages(search:)` 保留。
- Core 阶段增量：43 个文件，133 additions、1,498 deletions。
- 133 行恢复内容主要是 Base 搜索函数、10 个基础搜索参数化用例，以及为保留 schedule 固定旧测试 ID；不代表新增业务能力。

## 4. 测试名单与正式结果

第一次冻结 collection 被 runner 阻止，报告 5 个旧 ID 未收集：3 个 `PageTypeUpdate only_*` 用例也是 dirty-flag 专用测试；另两个通用 schedule 参数因删除 Page 参数后编号漂移。修正方式是删除 Page 的两个 `schedule0` ID，并将保留的 Product/GiftCard 参数显式固定为 `schedule1/schedule2`。没有让错误语义的用例冒充旧 ID。

最终从 F2P 删除 39 个、从 P2P 删除 0 个。审计见 `reports/stage-04-b1-r06-page-search/dropped-ids.json`。冻结名单为 F2P 5,714、P2P 7,021，共 12,735 个评分 ID。

正式结果：

- Core unit：普通 9,919/9,919，garbage-collection 10/10，合计 9,929/9,929。
- Core E2E：24/24。
- Dashboard unit：2,616/2,616；另有 6 个非评分 skipped。
- Dashboard E2E：166/166，setup 15/15。
- Grader：F2P `5,714/5,714`、P2P `7,021/7,021`、`reward=1`。

Focused 回归 246/246 通过，覆盖 Base Page 搜索、Page/Attribute mutation 和保留的 Product reference 索引链。Dashboard E2E 完整轮为 180 passed、1 failed；`SALEOR_78` 在 fulfillment 完成后等待 GraphQL response 超时。重新标准 seed 后单 worker 隔离重跑同一失败身份，15 setup 加该用例共 16/16 通过。没有修改产品代码、断言或超时，最终报告按 project/file/spec/title 严格合并。

## 5. Patch 与容器

| 仓库/类型 | 文件数 | bytes | SHA-256 |
| --- | ---: | ---: | --- |
| Core 累计 code | 572 | 1,984,875 | `b878fcf9595af0176495d91aaff62a335468e147c780921d15df067a619b73f4` |
| Core 累计 test | 458 | 3,086,486 | `c19df35a318c9ec614884aaa475cbd0001803e096cbc698f3fb25b78838e60a1` |
| Core 阶段增量 | 43 | 73,565 | `efbc742da96f1293b7ba6745cb17604a4d6e1e339b53df4d13fbc60183c83d30` |
| Dashboard 累计 code | 3,034 | 18,267,537 | `eda5bc8c006f6e8701546c8a09275c2bc282768375efee39198850ce48a5a882` |
| Dashboard 累计 test | 475 | 1,313,996 | `8a5ab66bd4089932caaef9dc781a7c02d0f3788131f1c91000c59594d0e5f8f2` |
| Dashboard 阶段增量 | 0 | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |

交付固化时重新从 Base 应用累计 patch。Core 的 `code -> test` 与 `test -> code` 均得到 `ea83176de24d437bbd11df0abbbb985d98849052`；单独 code/test tree 分别为 `1430c2871020bb6481c905372be36933e8e7ec9c` 和 `f665e5f8803bddc1090d006c121d661c43e7464b`。Dashboard 两种顺序均得到 `713d53f9eca6a6084e59b6a56056d2285db260fc`；单独 code/test tree 分别为 `ef0cd5a93cb519880004815081c7fb7cf3044c53` 和 `76164c6576ffad28fc759a9b89d3ecc114e3276e`。两个仓库的 code/test patch 路径重叠数均为 0。

本阶段复用镜像 `sdlcbench/saleor-3.23-test:standard-a-20260920`，新增长驻容器 `saleor-stage04b-tooling` 以 bind mount 本轮工作树。没有重建镜像，也没有使用 `docker commit`。R06 后续对象域必须继续从本阶段已验收 tree 开始，建议下一轮处理 user 搜索；不能回到未裁剪 Target，也不能一次删除 checkout/product/order/gift-card。
