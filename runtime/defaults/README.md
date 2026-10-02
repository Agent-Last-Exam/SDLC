# 默认 workflow 资产

runtime 拥有的角色、模板和交付契约。task 包不携带这些文件，只携带业务输入、Base 身份
和已发布镜像。

| 目录 | 内容 |
| --- | --- |
| roles/ | 11 个角色 SP，契约用 `defaults:<文件名>` 引用 |
| templates/ | 12 个产物模板与 schema，同样用 `defaults:` 引用 |
| workflows/{single,flat,hierarchical}.yaml | 三个模式的运行配置 |
| workflows/lifecycle.yaml | 交付契约：11 个 Stage 的输入接线与产物路径 |

`--mode` 直接选择对应的 yaml，该文件的 `contract:` 指向 `lifecycle.yaml`。三个模式共享
同一份契约。yaml 是配置来源，不是待核对的副本：运行器只做 schema 校验（预算为正数、
`max_concurrency <= max_members` 等），不再和代码常量对账。

`mode` 字段必须与文件名一致 —— 控制器按 mode 分支，不一致会执行成另一个模式。

`max_cost_usd` 是整个 run 的成本上限，三个模式都必须声明。成本取自 Agent 自己上报的
`total_cost_usd`（`claude-code.jsonl` 的 result 事件）：Single/Flat 在每个 Stage 封存后累加，
Hierarchical 在每个 Lead 回合和它派出的 assignment 后累加。超限即 `budget_exhausted`，
已完成的 Stage 和 revision 保留。被拒绝的 Lead 计划同样计费 —— 产生它的模型调用已经花了钱。
未上报成本的阶段按"未知"处理，不记为 0 也不凭空计数。

执行上限方面，Single/Flat 严格单向推进，每个 Stage 执行一次，没有需要配置的上限；QA 轮数由
`lifecycle.yaml` 的 `stages:` 决定（Controller 取 QA Stage 的最大 `round`），不在别处声明。
Hierarchical 的六个 `max_*` 由 TeamBroker 在每个 Lead 动作上检查。

`lifecycle.yaml` 的业务输入是 task 根的 `instruction.md`，每个输入显式声明容器内路径。
契约里 `task:` 相对 task 根解析，`derive:` 声明该输入由指定的
包内文件推导：`base_revisions` 取 `env/manifest.json` 记录的 agent baseline commit，
即 verifier 导出 diff 的基准，而不是 upstream tag。

task 包声明 `docker_image` 时，Harbor 任务定义由运行器生成：task.toml 使用包自身的
资源配额，Dockerfile 以该镜像为基础叠加 Agent 工具，并把镜像内的仓库迁移到
`/workspace/repos/`，同时在原路径留下符号链接供镜像自带的测试运行时解析。包原有的
task.toml 与 empty/gold/verifier 入口不被读取也不被修改。

包自带 `environment/Dockerfile` 而不声明镜像时，改用该 Dockerfile，仓库由宿主按
`environment/base-revisions.json` 准备。这两种形态由包的内容决定，不需要额外声明。

改这里的文件会影响所有 task。
