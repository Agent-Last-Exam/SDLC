# Stage 02: R11 Product Variant Generator 剪枝记录

## 1. 决策

- 功能：Product Variant Generator
- 主体关联度：弱；它是 Dashboard 商品详情中的批量组合生成入口，不属于 Checkout、配送、库存、支付、自动订单或订单操作主链。
- 处理决定：删除独立 Generator，保留普通单变体创建、required attributes、`hasVariants` 兼容行为以及 Core GraphQL/migration 合同。
- 父快照：阶段 01 commit `90a557ac5fc707a7d237d4f2238d8490ce9b1f18`，tree `3d16b49fc56a744d45eb1ed7f07cc556998555d4`。
- 输出快照：commit `57ffe57cbcd1aeaf4be2f81e6add470910e87e36`，tree `584b30aca6f25b0ed44622b3040e782388fe5914`。

## 2. 证据和边界

主要参考提交为 Dashboard `57cef5304ea96f4d178a790833998dd5d2e2ba8e`，Target 为 `61a3c045f7d7aba8dc343563757fdfdd249cd656`。后续提交 `d65d06657`、`6f61b4f3a`、`972ca6445`、`1245dabbd` 和 `7bf722f63` 仅用于理解 required attributes、`hasVariants` 和 Ripple 的演化；最终边界以 code patch、test patch、生成文件和调用方搜索为准。

删除：

- `src/products/components/ProductVariantGenerator/` 的组件、状态、工具、样式和专用测试。
- 商品更新页和变体区中的 Generator 打开、提交和批量处理接入。
- Generator 专用 Ripple、文案、locale 和 changelog 条目。
- Generator 专用 GraphQL response fields；普通 datagrid 保存仍需的 `ProductVariantBulkCreate` mutation 保留最小 `errors` 与 `productVariants { id }` 返回值。

保留：

- Core 的 product type attribute assignment 放宽、`hasVariants` 弃用及 schema/API 兼容合同。
- 普通单变体创建、编辑、库存、渠道价格和 required attributes UI。
- `ModalSectionHeader`，因为订单 capture 流程仍在使用。
- Core migration 和 generated schema；本阶段没有 Core 代码变化。

## 3. 变更量与生成物

- 阶段增量：35 个文件，68 行新增、4,334 行删除。
- 非测试：68 行新增、3,418 行删除。
- 专用测试：删除 `utils.test.ts` 的 916 行。
- 已重新生成 `src/graphql/hooks.generated.ts`、`src/graphql/types.generated.ts` 和 `locale/defaultMessages.json`。
- Dashboard `generate`、`extract-messages`、source typecheck（3,020 files）和 production build 均通过。

## 4. 冻结测试

- 从 F2P 删除 33 个仅覆盖 `ProductVariantGenerator/utils.test.ts` 的 ID，并以 `excluded R11 Variant Generator feature` 留痕。
- 最新冻结名单：F2P 5,849，P2P 7,026，总计 12,875。
- Dashboard unit：2,616 个选中 ID 全部通过。
- Core unit：复用阶段 01 报告，10,069 个选中 ID 全部通过。
- Core E2E：复用阶段 01 报告，24 个选中 ID 全部通过。
- Dashboard E2E：166 个冻结 ID 全部通过。
- 最终 grader：F2P `5,849/5,849`，P2P `7,026/7,026`，`reward=1`。

完整 Dashboard E2E 在干净容器中展开为 181 项（15 个 setup、166 个评分 ID），首轮 180 项通过；`SALEOR_78` 因测试在动作完成后才注册 `waitForResponse` 而错过请求并超时。重新执行标准 seed 后，该冻结 ID 单独通过，合并报告通过 grader。原始完整报告、定向重跑报告和 seed 日志均保留在 `reports/stage-02-r11-variant-generator/dashboard-e2e/`。

## 5. 容器问题记录

第一次阶段 02 容器在 Target Core 注入和 migration 完成前启动 API，内存 schema 仍是旧 `AppExtension.mount/target/options`，导致 Dashboard 的 `mountName/targetName/settings` 查询返回 400。修复方式是创建干净长驻容器，先复制阶段 01 已验收 Core，再启动 migration、sample data、API 和测试。没有重建 Docker image。

一轮受污染数据库上的 E2E 出现 `SALEOR_37` 和 `SALEOR_60` 失败：此前运行已改变 by-name fixture，而 seed 只按主键重置专用对象。干净容器中两项均通过，因此不归因于 R11，也没有修改生产代码或测试断言规避失败。

## 6. Patch 验证

- 阶段增量 patch：`dashboard-increment.patch`，SHA-256 `560a8ad79f76c0f795b1db2c7a0f259aec0eec5cb8da1b411a99376a17cb3158`。
- 累计 Dashboard code patch：3,037 个 diff section，18,997,011 bytes，SHA-256 `2c6fbf344eb129b11cf6fd6da498d1e6666a1e3909914e2bc5956e777d5e0031`。
- 累计 Dashboard test patch：476 个 diff section，1,421,589 bytes，SHA-256 `75ccec0d7c376a090e4dacefae9b8c2b86a7a5e8c985797ecb77c7c0018bdd8e`。
- `code -> test` 与 `test -> code` 均得到 tree `584b30aca6f25b0ed44622b3040e782388fe5914`。
- Core patch 未变化；本阶段复用同一 Base/Test image，没有构建或 `docker commit` 新镜像。
