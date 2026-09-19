# 执行代码

面向使用者的入口是仓库根目录执行 `python -m runtime`。这里只放实现，不放业务 prompt、实验结果或历史报告。

| 文件 | 职责 |
| --- | --- |
| run_workflow.py | 解析参数、冻结输入、创建 Harbor job、回收结果并生成 report.md |
| prepare_workflow.py | 解析 task 配置、校验依赖与 Base SHA、生成公开 workspace |
| prepare_sources.py | 精确获取并校验三仓 Base；不复制工作树改动 |
| workflow_controller.py | 阶段游标、同阶段补交、封存、失败续接 |
| workflow_agent.py | Harbor/Codex 适配、用户权限隔离、会话证据、阶段进程清理 |
| codex_app_turn.py | 容器内原生 App Server 连接、角色消息注入、执行回合 |
| workflow_gates.py | Markdown、编号引用、工程依赖、GraphQL SDL 等公开门禁 |
| reporting.py | 从主机证据生成每个 job 的 report.md 和 jobs/README.md |
| workflow_smoke.py | 明确标记 SYNTHETIC 的无模型容器联调 |
| agents.py | Codex/Claude Code prompt 薄适配器；当前 workflow 使用 Codex |
| environment.py | 按字面量读取本机 .env，不执行 shell |

`prepare_workflow.HERE` 指向 仓库根目录，不依赖 shell 当前目录推算资源位置；用户传入的相对路径仍相对调用目录。公开规范、角色、模板、workflow 和业务源码都位于 tasks/<task>/，执行记录位于 jobs/。

Controller 数据在 trial/workflow 下，不挂载给 Agent。Agent 只拥有本阶段产物和 scratch 等目录的写权限；已接受文件与源码归 root 只读。详见 [当前设计](../docs/instruction-to-review.md)。

运行器改动后执行 [tests/](tests/README.md)；涉及 Docker、包导入或上传路径时再跑 `python -m runtime --smoke`。升级 Codex 原生接口时，用 `--role-probe --use-local-codex-auth` 做两个真实模型回合验证。

`--task` 与 `--mode` 选择 task 下的 workflows/<mode>.yaml；`--config` 可显式指定 YAML。准备器按配置的 task_root 加载 task.toml 和 environment/Dockerfile，启动器不再内置 Saleor 容器定义或超时配置。具体交付门禁当前仍针对 PRD/技术设计，不代表任意 stage 已可执行。
