# Role Blueprint

这里的 Role Blueprint 是本 task 的角色 system prompt，采用用户优化后的正文，不作为跨 task 的公共角色。业务目标由 instruction.md 提供，格式由公开模板定义。

| 角色 | Prompt | 输入 | 输出 |
| --- | --- | --- | --- |
| PM | [pm.system.md](pm.system.md) | Instruction、Base、公开规范与 PRD 模板 | artifacts/sprint1/prd/prd.md |
| 研发负责人（architect） | [architect.system.md](architect.system.md) | 原始输入、封存 PRD、技术模板 | artifacts/sprint1/tech-design/ 下的 frontend-design.md、backend-design.md、interface-contract.md、target-schema.graphql、review.md |

这些路径相对 `/workspace`。架构师同时设计前端和后端，并在技术设计阶段末进行自审；不改变已封存的 PRD。尚未编写前端开发、后端开发、QA、Deploy、Lead Blueprint，本次也不启动这些角色。

完整的 [公开交付规范](../organization-delivery.md)、[模板](../templates/prd.md) 和 [workflow 配置](../workflows/design-delivery.yaml) 已建立；角色 prompt 明确要求读取这些文件并按规范输出。

准备器 `runtime/prepare_workflow.py` 可以校验配置并冻结公开工作区，不调用模型。Controller、Codex 原生会话角色切换与产物门禁已接入 `runtime/run_workflow.py`；运行结果与适用边界详见 [当前落地与剩余工作](../../../docs/instruction-to-review.md)。

