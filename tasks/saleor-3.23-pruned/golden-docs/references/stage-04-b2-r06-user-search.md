# Stage 04-B2: R06 User 搜索增强剪枝记录

## 1. 决策与快照

- 功能：User search vector、GIN index、email domain/prefix/accent/relevance 搜索、`UserSortField.RANK`，以及账户 mutation、OIDC、随机数据和批处理中的 vector 更新链。
- 主体关联度：弱到中；客户和员工搜索入口服务 Dashboard，但 Target 新增的 vector/relevance 实现不承担账户、订单、支付或权限主流程。
- 处理决定：删除 User 增强搜索，恢复 Base `search_document` 搜索；保留 `customers(search:)`、`staffUsers(filter.search)`、账户 CRUD、OIDC、客户属性及 Dashboard 调用方。
- Core 父快照：阶段 04-B1 commit `50c797102cd2693ce85d426452d1d9d1cda08501`，tree `ea83176de24d437bbd11df0abbbb985d98849052`。
- Core 输出：commit `8d07e9510`，tree `479dacdbcd96e4864e692eb572104c70aefb65c8`。
- Dashboard 未改：commit `05dea6f0fc8cbc8e4800ec25dff8bcfb3ae57d9f`，tree `713d53f9eca6a6084e59b6a56056d2285db260fc`。

## 2. 证据与删除边界

主要 Git 参考为 `bb61600598c932e83ba65b258153a68d5f4fe4b4`（Improve user search）、`365ca6a79b783658abd0768167d8edbfa82bde54`（email domain vector）和 `1233f8eb3c565b16ea4b0d413836e0fcc48d0ea4`（prefix/relevance search）。Git 仅用于解释背景，最终边界由累计 code/test patch、schema、migration、调用方和冻结测试决定。

删除：

- User `search_vector` 字段、`user_tsearch` GIN index 和 migrations `0096`-`0098`。
- User vector 生成/保存链，以及客户、员工、地址、注册、邮箱确认、OIDC 和批处理中的 vector 更新。
- User prefix/accent/domain/relevance 搜索和 `UserSortField.RANK`。
- 只验证上述增强行为的测试和 changelog 内容。

恢复或保留：

- Base `search_document`、`user_search_gin`、按空格 AND 的 `ilike` 搜索，以及 mutation/OIDC 对 search document 的同步更新。
- `customers(search:)`、`CustomerFilterInput.search` 和 `staffUsers(filter.search)`；Dashboard 客户列表、员工列表和订单客户选择器继续使用这些入口。
- 客户属性、权限、账户 CRUD、OIDC 密码安全变化和 Gift Card dirty-index 联动。
- `generate_email_vector` 最小 helper。它虽然最初随 User 增强搜索引入，但 Order 搜索仍直接使用；删除后 Django 启动检查立即暴露导入错误，因此作为跨域依赖保留。
- Checkout、Gift Card、Product、Order 的 R06 搜索增强和共享 `core/search.py`。

## 3. Migration、schema 与改动量

- 删除 `account/0096_user_search_vector.py`、`0097_user_user_tsearch.py`、`0098_update_user_search_vector.py`；保留的 `0099` dependency 改接 `0095`。
- 空数据库全量 migration 成功，Account graph 从 `0095` 直接到 `0099`；`makemigrations --check --dry-run` 返回 `No changes detected`。
- `get_graphql_schema` 与仓库 schema 一致；公开合同只移除 User `RANK`，客户/员工 search 参数保留。
- Core 阶段增量：46 个文件，332 additions、487 deletions。新增行主要恢复 Base search document 实现和测试，不是新增业务能力。

## 4. 测试名单与正式结果

初始候选为 43 个 User 专用 F2P。第一次正式 collection 在执行前停止，发现 `test_query_customers_root_level_filter[allen@example.com-1]` 未映射。复核完整参数组后确认 13 个 root-level filter F2P 都来自 Target test patch 的 vector 语义，其中 12 个虽仍同名也已恢复为 Base 实现；为防止同 ID 冒充旧语义，整组纳入 dropped 审计。最终从 F2P 删除 56 个、从 P2P 删除 0 个。

冻结名单为 F2P 5,658、P2P 7,021，共 12,679 个评分 ID。审计见 `reports/stage-04-b2-r06-user-search/dropped-ids.json`。

正式结果：

- Focused 回归：429/429。
- Core unit：普通 9,863/9,863，garbage-collection 10/10，合计 9,873/9,873。
- Core E2E：24/24。
- Dashboard unit：2,616/2,616；另有 6 个非评分 skipped。
- Dashboard E2E：166/166，setup 15/15；单轮全部通过，无隔离重跑。
- Grader：F2P `5,658/5,658`、P2P `7,021/7,021`、`reward=1`。

## 5. Patch 与容器

| 仓库/类型 | 文件数 | bytes | SHA-256 |
| --- | ---: | ---: | --- |
| Core 累计 code | 563 | 1,966,205 | `48fbf786f1fb177b831d90efb37c69e3f2182f274f91e326bf80f48c0c7bd30c` |
| Core 累计 test | 444 | 3,053,790 | `631cc08df7052e1eb575959fd45a4f9c4edf39b4151b7503a1f094a0476407c9` |
| Core 阶段增量 | 46 | 60,933 | `6de1b8f369f3ffaee76558f082b26ae30496c1e3bb390b81f676018df1e212f9` |
| Dashboard 累计 code | 3,034 | 18,267,537 | `eda5bc8c006f6e8701546c8a09275c2bc282768375efee39198850ce48a5a882` |
| Dashboard 累计 test | 475 | 1,313,996 | `8a5ab66bd4089932caaef9dc781a7c02d0f3788131f1c91000c59594d0e5f8f2` |
| Dashboard 阶段增量 | 0 | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |

Core 的 `code -> test`、`test -> code` 和阶段增量均得到 `479dacdbcd96e4864e692eb572104c70aefb65c8`；单独 code/test tree 分别为 `4372c3091957f054c0af0a7ee44d784a4ab49f9d` 和 `34116b3b79abf2a332664c918b91236c462ecaf2`。Dashboard 两种顺序均得到 `713d53f9eca6a6084e59b6a56056d2285db260fc`；两个仓库的 code/test 路径重叠数均为 0。

本阶段复用镜像 `sdlcbench/saleor-3.23-test:standard-a-20260920` 和长驻容器 `saleor-stage04b2-tooling`，没有重建镜像或使用 `docker commit`。服务器重启中断了第一次 focused 会话，源码未丢失；恢复后重新执行并取得完整 429/429 结果。后续边界复核决定不再建立 04-B3：Checkout、Gift Card、Product、Order 搜索与结账、支付、商品可售和订单操作主线关联较强，均作为主体需求保留；阶段 04 在本阶段验收树冻结。
