# Saleor 3.23 Golden Code Patch 组成分析

日期：2026-09-28

## 1. 目的与结论

本文分析正式 Harbor 包 `saleor-3.23-pruned-20260927-01` 中两个 Golden code patch 的组成，区分：

- 可以由仓库工具生成或派生的文件；
- 可由工具创建骨架、但必须由 Agent 设计和审核的内容；
- 从外部来源导入并随仓库存储的代码或资源；
- 必须由 Agent 直接实现和维护的业务代码、配置和内容。

核心结论：两个 code patch 共包含 318,672 行 patch 动作。其中约 209,139 行（65.6%）属于生成或派生内容，23,396 行（7.3%）属于批量导入内容，83,534 行（26.2%）需要 Agent 直接实现，另有 2,603 行（0.8%）数据库迁移需要工具辅助并由 Agent 负责语义和审核。

“生成或派生”不表示 Harbor 验证器会替 Agent 生成这些文件。Agent 仍需在工作树中运行生成工具、准备离线输入并提交结果。验证器只在 post 阶段应用 Agent 导出的 `saleor.model.patch` 和 `saleor-dashboard.model.patch`，然后应用官方 test patch。

## 2. 分析对象与口径

只统计以下两个正式 code patch：

| 仓库 | Patch | SHA-256 |
| --- | --- | --- |
| Saleor Core | `solution/saleor.code.patch` | `dfcee8e2ef4dd10092efea58b28d26726ae99f8eb5aca0f18a8adb6cb3a8887f` |
| Saleor Dashboard | `solution/saleor-dashboard.code.patch` | `fa0c4769a01daead3fa4c921a076e39c27ecf431f699f358db1a199fce397abe` |

本统计不包含 environment patch、test patch、Golden 文档或 Harbor verifier 文件。

“变更行数”按统一 diff 的新增行加删除行计算，不是最终仓库的总代码行数，也不等于手写代码量。统计可使用：

```bash
cd /tmp
git apply --numstat \
  /home/yang/SDLC/tasks/saleor-3.23-pruned/solution/saleor.code.patch
git apply --numstat \
  /home/yang/SDLC/tasks/saleor-3.23-pruned/solution/saleor-dashboard.code.patch
```

Dashboard patch 有 2,940 个 diff 动作、2,939 个唯一路径。`schema.graphql` 先删除旧普通文件，再建立指向 `schema-main.graphql` 的符号链接，因此同一路径出现两次。

## 3. 原始变更规模

| 仓库 | Diff 动作 | 唯一路径 | 新增 | 删除 | 总变更 | 净增加 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Saleor Core | 515 | 515 | 22,001 | 15,257 | 37,258 | 6,744 |
| Saleor Dashboard | 2,940 | 2,939 | 225,113 | 56,301 | 281,414 | 168,812 |
| 合计 | 3,455 | 3,454 | 247,114 | 71,558 | 318,672 | 175,556 |

## 4. 按内容来源分类

这里的“内容来源”是指文件应通过什么过程产生，不是指文件在最终交付中是否可以省略，也不是指 Harbor 会替 Agent 完成什么。以下四类内容最终都可能需要出现在 Agent 工作树中；分类的目的，是区分哪些文件应手工设计、哪些应通过工具重建或获取、哪些需要从受信来源导入。

本节按 Fabbrica 的两个 `codegen-main.ts` output blocks 已恢复后的正确目标状态分类。配置缺失的历史原因和交付修复边界见第 7 节，不再把同一种生成产物拆成独立内容类别。

| 类别 | Core | Dashboard | 合计 | 占比 |
| --- | ---: | ---: | ---: | ---: |
| 可由明确流程生成或获取的派生产物 | 3,543 | 205,596 | 209,139 | 65.6% |
| Django migration，工具辅助且需 Agent 负责 | 2,603 | 0 | 2,603 | 0.8% |
| 外部导入或随仓库存储资源 | 0 | 23,396 | 23,396 | 7.3% |
| Agent 直接实现和维护 | 31,112 | 52,422 | 83,534 | 26.2% |
| 合计 | 37,258 | 281,414 | 318,672 | 100% |

第一类内部包括 99,022 行本地生成产物，以及 110,117 行 Dashboard GraphQL schema 自动获取与替换内容。但从执行责任看，Golden code patch 不会自动应用到 Agent 工作树，Agent 最终仍需使生成产物、schema 输入、迁移、导入资源和业务代码共同形成可测试的 model patch。

### 4.1 四类内容分别表示什么

| 类别 | 判断标准 | Agent 负责的输入 | 产出方式 | 是否允许手工逐行维护 |
| --- | --- | --- | --- | --- |
| 可由明确流程生成或获取的派生产物 | 仓库内能找到生成、提取、锁定或 schema 获取流程及明确输出路径 | 模型、GraphQL operation、消息、依赖 manifest、受信 schema 来源及版本 | 执行仓库已有生成命令，或从 Core 生成结果复制/自动获取 | 不建议；应修正权威输入后重建或重新获取 |
| Django migration，工具辅助且需 Agent 负责 | `makemigrations` 能产生结构骨架，但文件还承载数据语义、顺序和升级风险 | 模型变化、历史数据规则、兼容策略 | 工具生成骨架，Agent 编写和审核数据迁移 | 允许且经常必须人工编写 |
| 外部导入或随仓库存储资源 | 本仓库没有生成器，内容来自 SDK、图标集或其他受信来源 | 来源版本、许可证、校验值、选择范围 | 批量导入或 vendor | 不应手工重造；需要审计来源 |
| Agent 直接实现和维护 | 文件本身就是业务或技术设计的权威输入 | PRD、TDD、接口合同和现有架构 | Agent 编码、评审和测试 | 是 |

### 4.2 “自动生成”不等于“评测系统自动完成”

Harbor 的 pre/post 组合是：

```text
pre / Base   = agent baseline + official test patch
post / Target = agent baseline + Agent model patch + official test patch
```

`solution/*.code.patch` 是 Golden 参考实现，不会在普通 Agent post 阶段自动应用。所谓“可由明确流程生成或获取”，只表示 Agent 可以通过仓库工具产生或取得这些文件，而不是可以不提交这些文件。Agent 的责任链仍然是：

```text
修改或固定权威输入 -> 运行生成/获取流程 -> 审查派生差异 -> 纳入 model patch
```

如果生成器没有运行、输出没有进入工作树，或者输出与权威输入不一致，构建、类型检查或 F2P/P2P 仍可能失败。

### 4.3 分类边界

分类依据是路径、文件内容、仓库脚本和生成配置，不是只根据文件名猜测。例如：

- `types.generated.ts` 同时有 `.generated` 命名和 `codegen-main.ts` 输出声明，因此属于“可由明确流程生成或获取的派生产物”；
- `fabbrica.generated.ts` 和 `fabbricaTypes.generated.ts` 有上游 PR #6334 的生成配置、插件和更新历史；按配置已恢复的目标状态，也属于该类；
- Dashboard schema snapshot 有 `fetch-schema:main`、`fetch-schema:staging` 和上游自动更新 workflow，虽然内容由 Core 定义而非 Dashboard 生成，也属于该类；
- migration 即使由 `makemigrations` 创建，也可能包含手工 `RunPython`，因此不能整体归入纯生成文件；
- `legacy-sdk` 虽然可能由上游项目构建或复制而来，但本仓库没有重建命令，因此归入 vendored 内容。

统计是对 Golden patch 的来源分析，不代表每一行都能仅凭路径证明作者身份，也不代表通过测试的最小实现必须逐字节复制 Golden patch。

## 5. 可由明确流程生成或获取的派生产物

### 5.1 Saleor Core

| 文件 | 变更行数 | 生成入口 | Agent 的输入责任 |
| --- | ---: | --- | --- |
| `saleor/graphql/schema.graphql` | 3,407 | `uv run poe build-schema` | 完成 GraphQL 类型、查询、mutation 和 resolver 实现 |
| `uv.lock` | 136 | `uv lock` | 正确维护 `pyproject.toml` 依赖声明 |

Core 的 `pyproject.toml` 已声明 `build-schema`，实际命令为 `python manage.py get_graphql_schema`，输出捕获到 `saleor/graphql/schema.graphql`。

这里的权威输入是 Core 中的 GraphQL type、query、mutation、resolver 和相关模型。Agent 应修改这些源文件，再重建 schema；不应直接在 `schema.graphql` 中添加字段，因为下一次运行 `build-schema` 会覆盖手工修改，而且运行时后端也不会因此获得对应 resolver。

### 5.2 Saleor Dashboard

Dashboard 在第一类中的 205,596 行由以下五部分组成。这里的 24,146 行只是一组普通 main/staging GraphQL 客户端产物，不是 Dashboard 自动派生产物的总数：

| Dashboard 派生产物 | 变更行数 | 占 Dashboard 第一类 |
| --- | ---: | ---: |
| main/staging GraphQL 客户端生成文件（以下 8 个文件） | 24,146 | 11.7% |
| Fabbrica 类型与 factory（第 7 节） | 69,060 | 33.6% |
| main/staging schema 获取与替换（第 6 节） | 110,117 | 53.6% |
| `locale/defaultMessages.json` | 2,217 | 1.1% |
| `pnpm-lock.yaml` | 56 | <0.1% |
| **Dashboard 合计** | **205,596** | **100%** |

计算关系为：

```text
24,146 + 69,060 + 110,117 + 2,217 + 56 = 205,596
```

以下 8 个文件由 `pnpm run generate` 调用 main/staging GraphQL Code Generator 配置生成，共 24,146 行变更：

- `src/graphql/fragmentTypes.generated.ts`
- `src/graphql/fragmentTypesStaging.generated.ts`
- `src/graphql/hooks.generated.ts`
- `src/graphql/hooksStaging.generated.ts`
- `src/graphql/typePolicies.generated.ts`
- `src/graphql/typePoliciesStaging.generated.ts`
- `src/graphql/types.generated.ts`
- `src/graphql/typesStaging.generated.ts`

另外两类有明确生成入口：

| 文件 | 变更行数 | 生成入口 |
| --- | ---: | --- |
| `locale/defaultMessages.json` | 2,217 | `pnpm run extract-messages` |
| `pnpm-lock.yaml` | 56 | pnpm lockfile 更新流程 |

Agent 不应手工编辑这些生成内容。正确流程是先修改 GraphQL operation、组件消息、依赖声明和 codegen 配置，再运行相应生成命令并审查差异。

第 7 节所述两份 Fabbrica 文件共 69,060 行，也计入本类。恢复两个 output blocks 后，它们由同一个 `pnpm run generate:main` 入口根据 `schema-main.graphql` 生成。因此本地生成部分中，Dashboard 合计为 95,479 行，Core 与 Dashboard 合计为 99,022 行。

再加上第 6 节的 110,117 行 Dashboard schema 自动获取与替换内容，本类最终合计为 209,139 行，占全部 code patch 动作的 65.6%。

生成器只负责机械转换，不负责判断业务设计是否正确。例如 GraphQL Code Generator 可以根据 operation 生成 TypeScript 类型，却不能判断 Dashboard 是否调用了正确 mutation、是否处理了错误分支，或者 staging operation 是否应该进入稳定路径。这些仍属于 Agent 的实现责任。

## 6. Dashboard Schema 自动获取与替换

这部分属于自动化派生产物。“获取”表示 Dashboard 从 Saleor Core API 契约取得 schema snapshot；“替换”表示原来的单 schema 文件被 main/staging 双 schema 结构替代。Core schema 本身由后端类型系统生成，Dashboard 再通过 `fetch-schema` 或等价的本地复制流程取得结果。Dashboard 不拥有 GraphQL API 定义，它只保存 schema 快照供静态检查和客户端代码生成使用。

变更前：

```text
schema.graphql
    -> 所有 Dashboard operation 的唯一 schema 输入
```

变更后：

```text
schema-main.graphql
    -> 普通 queries/mutations/fragments
    -> types.generated.ts、hooks.generated.ts 等稳定客户端产物

schema-staging.graphql
    -> *.staging.ts operation
    -> typesStaging.generated.ts、hooksStaging.generated.ts 等 staging 产物

schema.graphql
    -> 符号链接到 schema-main.graphql，兼容仍读取旧路径的工具
```

Dashboard schema 相关 patch 动作共 110,118 行，其中 110,117 行属于 schema 生成或替换，1 行属于 Agent 维护的符号链接：

| 动作 | 变更行数 | 分类 |
| --- | ---: | --- |
| 新增 `schema-main.graphql` | 37,445 | schema snapshot |
| 新增 `schema-staging.graphql` | 37,445 | schema snapshot |
| 删除旧 `schema.graphql` 内容 | 35,227 | 删除旧生成产物 |
| 建立 `schema.graphql -> schema-main.graphql` | 1 | Agent 配置 |

Dashboard 的 `package.json` 提供 `pnpm run fetch-schema`，但该命令使用 `curl` 从 GitHub 获取 schema，而任务说明明确要求离线工作。因此正式 Agent 流程不能把联网 fetch 当成可用前提，应从本地或预置的受信 schema 输入生成 main/staging snapshot。

Golden patch 中 main 和 staging schema 内容相同，但这只是当前目标状态，不能推广为所有后续版本的固定规则。

### 6.1 上游 Git 历史说明

Dashboard schema 的维护方式有明确的上游 commit 证据，但需要区分“机制由谁提交”和“schema 内容由谁产生”。

| Commit | PR | 作用 | 性质 |
| --- | --- | --- | --- |
| `cdc2bdad018fdd2fd90530d80b3c52a392c01a03` | `saleor-dashboard#5646` | 将 schema 来源从运行中的 Saleor API 改为 Saleor Git 仓库；增加定时 `update-schema` workflow | 开发者设计并提交自动更新机制 |
| `6df089ce4bb759020954891949436110714334c3` | `saleor-dashboard#6070` | 引入 main/staging 双 Schema、两套 codegen 配置、`schema.graphql` 符号链接及 multi-schema 文档 | 开发者设计并提交双 Schema 架构，同时提交当时的 schema snapshot 和 generated files |
| `a480a789ea5f33e7def86ff0ca72a21c15906b89` | `saleor-dashboard#6956` | 2026-09-24 更新 3.23 schema 和 generated types | 定时流程生成 PR，`saleor-deployments[bot]` 提交结果 |

对应的上游流程是：

```text
GitHub Actions 定时或人工触发
        |
        v
执行 fetch-schema
        |
        v
执行 GraphQL codegen
        |
        v
检查 Git diff
        |
        v
自动创建 PR
        |
        v
schema snapshot 和 generated TypeScript 作为普通 Git 文件提交
```

因此答案不是单纯的“自动生成”或“人手工提交”：

- 双 Schema 的目录结构、脚本、codegen 配置、feature flag 和符号链接由开发者在 PR #6070 中设计并提交；
- schema 文件内容由 fetch 流程取得，generated TypeScript 由 codegen 产生；
- 生成结果仍然被提交进 Git，不是在 Dashboard 每次构建时临时生成后丢弃；
- 日常更新通常由 workflow 自动创建 PR，并由 bot 形成 commit；开发者仍需评审和合并该 PR。

### 6.2 Golden Patch 的精确来源边界

Golden Dashboard patch 中：

```text
schema-main.graphql     blob 46dd821668f050f3b64016cb2e42e773c5c26156
schema-staging.graphql  blob 46dd821668f050f3b64016cb2e42e773c5c26156
schema.graphql          symlink -> schema-main.graphql
```

两个 snapshot 在 Golden target 中内容完全相同，均为 37,445 行。但是对上游 `main` 和 `3.23` 分支历史进行对象级查询，没有找到包含 blob `46dd8216...` 的 commit。2026-09-24 的上游自动更新 commit `a480a789...` 也不是这份内容：该 commit 的 main schema blob 为 `d7d02ccb...`，staging schema blob 为 `709452da...`，二者并不相同。

因此能够确认的是：

- 双 Schema 机制来自上游 PR #6070；
- Golden 包中的两个具体 snapshot 由 Candidate/Golden code patch 直接提供并作为目标文件提交；
- 现有证据不能把 Golden blob 归因到某一个公开上游 Dashboard commit；
- Harbor verifier 不会在评测时执行 `fetch-schema` 来替 Agent 生成这两个文件。

### 6.3 与最终剪枝 Core Schema 的关系

最终工作树中的 schema 状态为：

| 文件 | 行数 | Git blob |
| --- | ---: | --- |
| Dashboard `schema-main.graphql` | 37,445 | `46dd821668f050f3b64016cb2e42e773c5c26156` |
| Dashboard `schema-staging.graphql` | 37,445 | `46dd821668f050f3b64016cb2e42e773c5c26156` |
| Core `saleor/graphql/schema.graphql` | 37,354 | `9c4086bd9cf44dbecaca379b7f764ebf6f4d5237` |

Dashboard snapshot 与最终剪枝 Core schema 不同。Dashboard snapshot 仍包含后来从 Core 剪枝掉的 Transaction date/event sorting/filtering，以及 Page/User `RANK` 等合同。剪枝过程记录证明 Core schema 在各相关阶段使用 `get_graphql_schema` 重新生成并校验，但没有证据表明最终又把该 Core schema复制到 Dashboard 的 main/staging snapshot 并重跑全部 Dashboard codegen。

这不影响已经冻结的 F2P/P2P 通过结论，但意味着 Golden Dashboard schema 是“参考目标中提交的客户端合同快照”，不能描述成“最终剪枝 Core schema 的逐字节同步副本”。若后续要求严格消除已剪枝合同的所有客户端残留，应把 schema 同步和 generated TypeScript 重建作为独立变更，并重新校准 F2P/P2P，而不能只替换两个大文件后沿用旧验证结果。

这 110,117 行不应解释为新增了 110,117 行业务逻辑。它主要来自两个完整 snapshot 的加入，以及旧 snapshot 的删除。Golden patch 的 schema 文件是已提交的目标输入，而不是评测期间动态生成的临时文件。真正需要 Agent 决策的是：

- main 和 staging 分别使用哪个受信 schema 版本；
- 哪些 operation 属于稳定合同，哪些属于 staging；
- 旧 `schema.graphql` 使用符号链接兼容是否符合构建环境；
- schema 更新后是否统一重建所有客户端类型；
- 离线环境中 schema 输入如何被固定、校验和追踪。

不能通过手工向 Dashboard schema snapshot 添加字段来替代 Core 实现。这样可能让 TypeScript 编译暂时通过，但运行时 Core 并不存在相应字段，属于合同伪造。

## 7. Fabbrica 的生成来源与配置恢复记录

以下两个文件名称和内容明确属于 GraphQL 生成代码，共 69,060 行：

| 文件 | 新增行数 |
| --- | ---: |
| `src/graphql/fabbrica.generated.ts` | 36,575 |
| `src/graphql/fabbricaTypes.generated.ts` | 32,485 |

Dashboard 依赖中包含 `@mizdra/graphql-codegen-typescript-fabbrica`。按本文采用的正确目标状态，`codegen-main.ts` 已恢复两个 output blocks，因此 `pnpm run generate:main` 可以重建这两个文件。

正式 Golden patch 的既有版本曾只有 77 行 `codegen-main.ts`，无法重建这两个文件。该问题不能解释为“上游仓库没有提供生成入口”：Git 历史证明上游一直有完整入口，第 7.4 节记录的是配置在 Candidate/Golden 分层过程中如何丢失以及为何需要恢复。

### 7.1 首次引入的上游 Git commit

两份文件和生成配置由以下提交同时引入：

```text
commit 5669ef5cdcc8ed86959a3e3677d2fac253623d1a
Author: Jonatan Witoszek
Date:   2026-02-12
Title:  Add stories for assign attribute value modals (#6334)
```

该提交不是把两个不明来源的大文件单独复制进仓库，而是一次性完成了完整生成链：

- 新增 `src/graphql/fabbrica.generated.ts`，首次提交为 36,503 行；
- 新增 `src/graphql/fabbricaTypes.generated.ts`，首次提交为 31,449 行；
- 在 `package.json` 加入 `@mizdra/graphql-codegen-typescript-fabbrica`；
- 在 `codegen-main.ts` 声明两个 output；
- 新增使用这些 factory 的 Assign Dialog Storybook stories 和共享 factories。

上游加入的核心配置是：

```ts
"./src/graphql/fabbricaTypes.generated.ts": {
  plugins: ["typescript"],
  config: {
    enumsAsTypes: true,
    avoidOptionals: true,
    nonOptionalTypename: true,
    scalars: { Day: "number", Hour: "number", Date: "string" },
    namingConvention: { enumValues: "change-case-all#upperCase" },
  },
},
"./src/graphql/fabbrica.generated.ts": {
  plugins: ["@mizdra/graphql-codegen-typescript-fabbrica"],
  config: { typesFile: "./fabbricaTypes.generated" },
},
```

`package.json` 的 `generate:main` 执行 `graphql-codegen --config codegen-main.ts`，所以这两份文件原本就是普通 `pnpm run generate` 流程的一部分，不存在另一套隐藏脚本。

### 7.2 后续更新方式

引入以后，两份文件随 Dashboard schema 更新被反复重建并提交。例如：

```text
commit a480a789ea5f33e7def86ff0ca72a21c15906b89
Author: saleor-deployments[bot]
Date:   2026-09-24
Title:  chore: update GraphQL schema and generated types
        (schema: 3.23, 2026-09-24) (#6956)
```

该 bot commit 同时修改了 main/staging schema、`fabbrica.generated.ts` 和 `fabbricaTypes.generated.ts`。这进一步证明 Fabbrica 文件由 schema/codegen 自动产生，然后作为普通 Git 文件提交；它们不是开发者逐行手写的业务代码。

### 7.3 Golden 文件为何不是某个上游 commit 的原样副本

Saleor Dashboard 3.23.0 发布提交 `61a3c045f7d7aba8dc343563757fdfdd249cd656` 仍包含 99 行的完整 `codegen-main.ts`，其 Fabbrica 文件分别为 36,858 行和 32,668 行。当前 Golden 文件分别为 36,575 行和 32,485 行，Git blob 也不同。

差异来自本任务的生成后剪枝：`tmp/candidate-20260924-01/dashboard-pruning.patch` 对两个文件分别执行了 59 增加/342 删除和 53 增加/236 删除，内容包括移除 App Problems GraphQL 类型等已剪枝合同。因此：

```text
上游 commit #6334
    -> 建立 Fabbrica 生成机制和首批产物
后续 schema/bot commits
    -> 持续重建并提交产物
本任务 dashboard-pruning.patch
    -> 根据剪枝后的合同更新两份生成结果
```

当前 Golden blob 是本任务组合出的生成结果，不能归因成某个公开上游 commit 的逐字节副本；但它的文件类型、生成工具和配置来源都有明确 Git 证据。

### 7.4 生成内容的删除 commit 与配置入口缺失不是同一件事

本任务确实存在删除 Fabbrica **生成内容**的 Git commit：

```text
commit 5458afcbe0c2ea22065b84dd200d1375cec499a7
Title:  remove app problems feature
```

该提交修改了：

| 文件 | 新增 | 删除 |
| --- | ---: | ---: |
| `src/graphql/fabbrica.generated.ts` | 59 | 342 |
| `src/graphql/fabbricaTypes.generated.ts` | 53 | 236 |
| 合计 | 112 | 578 |

这些删除对应 App Problems 类型等已剪枝 GraphQL 合同，解释了 Golden Fabbrica 文件为什么不同于未剪枝 target。该 commit 没有修改 `codegen-main.ts`，因此它不是删除两个 output blocks 的提交。

配置入口需要按 Harbor 分层追踪：

| 层 | `codegen-main.ts` | Fabbrica 插件依赖 | Fabbrica 生成文件 | 结论 |
| --- | --- | --- | --- | --- |
| 上游 Base `e934ff0a` | 不存在 | 不存在 | 不存在 | 3.22 基线尚未引入该机制 |
| E/env commit `aebb2401` | 不存在 | 已加入 | 不存在 | env 只准备目标依赖环境 |
| Incoming candidate G | 新增 77 行，无 Fabbrica outputs | 已由 E 提供 | 新增 | 生成结果进入 G，但生成声明没有进入 E 或 G |
| 剪枝 commit `5458afcb` | 不修改 | 不修改 | 删除 578 行、新增 112 行 | 只更新生成内容 |
| 恢复前的正式 Golden G | 77 行，无 Fabbrica outputs | 已由 E 提供 | 保留剪枝后版本 | 当时的混合状态不可完整重建 |

正式 env patch 位于 `environment/harbor/saleor-3.23/env/saleor-dashboard.env.patch`，SHA-256 为 `fd9edc96a558db352b9d866c72e33b1f45bf6578061783985a4273a173829fbc`。它只修改 7 个路径：`.npmrc`、`.nvmrc`、`jest.config.js`、`package-lock.json`、`package.json`、`pnpm-lock.yaml` 和 `pnpm-workspace.yaml`。其中 `package.json` 和 lockfile 加入了 `@mizdra/graphql-codegen-typescript-fabbrica`，但 patch 不包含 `codegen-main.ts` 或两份 Fabbrica 文件。

环境镜像中的实际 Git commit `aebb2401b5079fbbb8c60150289d1896c108feca` 也验证了相同结果：该 commit 的父提交是 `e934ff0a`，只改上述 7 个路径，工作树中不存在 `codegen-main.ts`。因此可以说“Fabbrica 插件依赖是架构升级 E 的一部分”，但不能说“Fabbrica 生成配置已经在 E 中”。

未剪枝的 `candidate-20260924-01-target` 工作树已经是 77 行配置；最终剪枝只把两份生成文件从 36,858/32,668 行变成 36,575/32,485 行。也就是说，两个 output blocks 在接入剪枝 patch 之前就未进入 incoming candidate 的交付层。

进一步对比 candidate builder 保存的原始和重分类 patch，可以把缺失点精确定位到 2026-09-24 candidate 的 E/G/T 重分类步骤：

| Candidate 输入/输出 | `codegen-main.ts` | Fabbrica 生成文件 |
| --- | --- | --- |
| `raw-patches/saleor-dashboard.code.patch` | 完整 99 行，包含两个 outputs | 两个文件都在 raw G |
| `env/saleor-dashboard.env.patch` | 不包含 | 不包含，只提供插件依赖 |
| `patches/saleor-dashboard.code.patch` | 被裁成 77 行 | 不包含 |
| `patches/saleor-dashboard.test.patch` | 不包含 | 两个文件被移动到 T |

这一步把测试使用的 Storybook/Fabbrica 生成文件从 raw G 移入了 T，却没有把与它们绑定的 22 行 codegen 配置一起移入 T，也没有将配置保留在 G。该变化不是一个 Saleor Git commit，而是 Harbor patch 分层时对同一 raw diff 的重新组织。后续 Golden 重组将剪枝后的两个生成文件重新归入 G，但直接沿用了 candidate 的 77 行 `codegen-main.ts`，所以没有自动修复此前遗漏。

上游 `3.23` 的 `git log -S'./src/graphql/fabbricaTypes.generated.ts' -- codegen-main.ts` 只找到 `5669ef5c` 的引入记录，当前分支也仍保留配置。现有交付证据没有一个“删除 Fabbrica 配置”的上游 commit；能够定位的是 raw target 到 E/G/T patch 分层时发生了配置遗漏。若另有构建系统内部的删除 commit，需要对应仓库或 commit hash 才能继续归因，不能用生成内容删除 commit `5458afcb` 代替。

恢复前的状态之所以没有立即报错，是因为 GraphQL Code Generator 只写入配置声明的 outputs，不会清理磁盘上未声明的旧 `.generated.ts` 文件。于是当时的 `pnpm run generate` 可以成功，但两份已有 Fabbrica 文件只是原样残留；这个成功不能证明它们可重复生成。

### 7.5 分类与恢复口径

本文的来源分类默认采用恢复方案：恢复上游两个 output blocks，固定 `schema-main.graphql` 和插件版本，运行 `pnpm run generate`，再验证第二次运行没有额外 diff。这样保留现有 Storybook consumers，同时恢复可重复生成性。因此两份文件已经并入第 4、5 节的“可由明确流程生成或获取的派生产物”，不再单列“缺少生成入口”类别。

只有在决定连同 Fabbrica consumers 一起剪枝时，才应采用删除方案：同时删除 Storybook factories、所有相关 stories/import、插件依赖、TypeScript path alias、两个生成文件及对应测试。只删除生成文件或只保留当前混合状态都不完整。

## 8. Django Migration 的责任边界

Core code patch 包含 94 个 migration 文件，共 2,603 行变更：

| 类型 | 文件数 | 新增 | 删除 | 总变更 |
| --- | ---: | ---: | ---: | ---: |
| 编号 migration | 79 | 1,536 | 582 | 2,118 |
| `migrations/tasks/` 升级任务 | 15 | 482 | 3 | 485 |
| 合计 | 94 | 2,018 | 585 | 2,603 |

文件状态包括新增 68、修改 25、重命名 1。内容包含 `RunPython`、`RunSQL`、数据清理、搜索索引更新、批处理和历史升级任务。

以新增模型字段为例，`makemigrations` 可以从模型差异生成 `AddField`、`AlterField` 或 `AddIndex` 等结构操作。但如果目标要求为历史 Channel、Checkout、Order 或 Gift Card 数据填充值，Django 无法从字段定义推断业务值，Agent 必须编写类似以下数据迁移：

```python
def populate_existing_rows(apps, schema_editor):
    Model = apps.get_model("app_name", "Model")
    Model.objects.filter(new_field__isnull=True).update(new_field=default_value)


class Migration(migrations.Migration):
    operations = [
        migrations.RunPython(
            populate_existing_rows,
            migrations.RunPython.noop,
        ),
    ]
```

这个例子中的函数、默认值、筛选范围、反向策略和执行批次都属于业务决策，不是 `makemigrations` 能自动给出的答案。

`uv run poe make-migrations` 可以根据模型变化创建部分 schema migration 骨架，但不能替代 Agent 对以下内容的设计：

- 数据迁移的正向和反向语义；
- 大数据量下的批处理与事务边界；
- 索引、锁和停机风险；
- 历史版本升级任务；
- migration 与运行时代码的版本兼容性。

因此 migration 被归为“工具辅助且 Agent 负责”，不计入纯自动生成产物。

### 8.1 Agent 对 Migration 的具体责任

1. 确认结构操作正确，包括字段类型、nullability、默认值、约束和索引。
2. 定义历史数据转换规则，避免只支持新数据而破坏已有订单或 checkout。
3. 设计迁移顺序，必要时采用“先增加可空字段、再回填、最后增加约束”的多阶段方式。
4. 明确正向和反向行为；不可逆迁移必须显式记录，而不是提供虚假的 rollback。
5. 评估大表更新的锁、事务、超时和磁盘风险，必要时批处理或使用 `migrations/tasks/`。
6. 保证滚动部署期间新旧代码对中间数据库状态的兼容性。
7. 审查被修改的历史 migration。当前 patch 修改了 25 个既有 migration 文件，通常不应无理由改写已经发布的迁移历史。

### 8.2 最低验证要求

```bash
python manage.py makemigrations --check
python manage.py migrate
```

以上只能证明没有遗漏模型差异且迁移能够执行。对于本任务，还应从真实 Base 数据库状态升级，验证关键历史数据、索引和业务读取结果，并运行对应 F2P/P2P。只在空数据库执行全部 migration 不能覆盖真实升级风险。

## 9. 外部导入和随仓库存储内容

Dashboard 中有两组大体量内容不是 Agent 手写，也没有当前仓库生成命令：

| 内容 | 文件数 | 变更行数 | 性质 |
| --- | ---: | ---: | --- |
| `public/payment-methods/*.svg` | 862 | 862 | 支付方式图标资源 |
| `src/legacy-sdk/` | 28 | 22,534 | 内嵌的旧 SDK 兼容实现 |
| 合计 | 890 | 23,396 | 批量导入或 vendored 内容 |

支付图标应从允许的本地来源批量导入，不应要求 Agent 手工绘制。Legacy SDK 是实际参与认证、GraphQL client 和旧类型兼容的运行时代码，必须存在等价实现，但当前没有证据表明它由仓库脚本生成。

这类内容与“generated 但缺少入口”的区别是：Fabbrica 文件可以从 schema 和 codegen 配置逻辑性地派生；SVG 和 Legacy SDK 则是独立来源内容，本仓库没有足够输入可以从零推导出相同结果。Agent 应验证来源、版本、许可证和校验值，而不是为它们虚构生成命令。

## 10. Agent 直接实现的内容

### 10.1 Core

| 内容 | 变更行数 |
| --- | ---: |
| 后端业务代码和配置 | 26,738 |
| 邮件模板 | 2,858 |
| populatedb seed 数据 | 1,507 |
| `pyproject.toml` 依赖声明 | 9 |
| 合计 | 31,112 |

主要业务域包括 GraphQL、payment、plugins、checkout、core、order、webhook、app、product、giftcard、shipping、site、tax 和 warehouse。

这些文件是其他生成流程的权威输入。例如 Core GraphQL 类型和 resolver 决定 Core schema，模型与 migration 共同决定数据库状态。Agent 如果只修改生成结果而不修改这些源文件，运行时行为不会正确改变。

### 10.2 Dashboard

| 内容 | 变更行数 |
| --- | ---: |
| React/TypeScript 业务代码及一般配置 | 52,103 |
| codegen 配置 | 186 |
| code patch 中保留的 3 个源仓库单元测试 | 102 |
| `package.json` 脚本和依赖声明 | 28 |
| 人工维护的 locale 数据 | 2 |
| `schema.graphql` 符号链接 | 1 |
| 合计 | 52,422 |

code patch 中的 3 个测试文件是 Extensions 功能的源仓库测试，不是官方 test patch：

- `src/extensions/components/AppAlerts/useAppsAlert.test.ts`
- `src/extensions/views/InstalledExtensions/InstalledExtensions.test.tsx`
- `src/extensions/views/InstalledExtensions/hooks/useInstalledExtensions.test.tsx`

官方评测测试仍由 `tests/saleor.test.patch` 和 `tests/saleor-dashboard.test.patch` 单独提供，Agent 不得修改 evaluator 测试、fixture、verifier 或评分配置。

Dashboard 业务源文件中的 query、mutation 和 fragment 又是 TypeScript GraphQL codegen 的输入。正确顺序是先完成这些 operation 和 UI 行为，再生成类型；不能通过修改 `types.generated.ts` 绕过 operation 或后端合同错误。

## 11. 推荐 Agent 工作流

```text
修改 Core/Dashboard 权威业务源代码和配置
                  |
                  v
生成并人工审核 Django schema/data migrations
                  |
                  v
从 Core 类型系统生成 Core GraphQL schema
                  |
                  v
离线准备 Dashboard main/staging schema 输入
                  |
                  v
运行 Dashboard GraphQL codegen，包括已恢复配置的 Fabbrica outputs
                  |
                  v
提取 i18n catalog，更新 uv/pnpm lockfile
                  |
                  v
加入必要的 vendored SDK 和静态资源
                  |
                  v
运行 F2P/P2P，导出两个 repository model patch
```

生成产物必须在权威输入稳定后统一重建，避免每次业务代码修改都手工调整大文件。迁移、生成配置、依赖 manifest 和离线输入来源必须进入 code review；生成文件本身重点检查可重复生成性和非预期漂移。

## 12. 对任务规模的正确表述

不应将本任务描述成“Agent 手写 318,672 行代码”。更准确的表达是：

- 209,139 行是生成或派生文件的 patch 动作；
- 23,396 行是外部导入或随仓库存储内容；
- 83,534 行需要 Agent 直接实现和维护；
- 2,603 行 migration 由工具辅助，但业务语义、数据安全和审核责任仍属于 Agent。

同时，Golden patch 是一份参考实现，不是最小实现证明。任务说明明确指出 evaluated tree 不要求与 upstream target tree 逐字节一致；最终充分性和必要性应以冻结 F2P/P2P 行为以及 PRD/TDD 约束为准，而不是以复刻全部 Golden 文件为唯一标准。
