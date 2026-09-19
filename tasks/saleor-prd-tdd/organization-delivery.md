# 公开交付规范：Instruction → PRD → 技术设计与评审

规范版本：1。业务目标只来自 instruction.md；本文件与 templates/ 定义公开输出格式。参考答案、rubric 和 Target 源码不属于输入。

## 运行范围与目录

本轮只有 `sprint1/prd`、`sprint1/tech-design` 两个 stage。后者内部完成设计与自审，最后交付 review.md；无 Code、QA 或 Deploy。技术评审默认是架构师在同一阶段内自审，不代表独立评审或人工批准。

所有下列路径相对 `/workspace`：

```text
instruction.md
organization-delivery.md
base-revisions.json
repos/{saleor,saleor-dashboard,saleor-platform}/
roles/{pm,architect}.system.md
templates/{prd,frontend-design,backend-design,interface-contract,technical-review,target-interface}.md
artifacts/sprint1/prd/prd.md
artifacts/sprint1/tech-design/frontend-design.md
artifacts/sprint1/tech-design/backend-design.md
artifacts/sprint1/tech-design/interface-contract.md
artifacts/sprint1/tech-design/target-schema.graphql
artifacts/sprint1/tech-design/review.md
artifacts/sprint1/tech-design/interfaces/  # 按需：其他协议的完整目标描述
scratch/                               # 临时调查，不自动传给 Flat 的下一 Agent
```

运行器的冻结配置、哈希、状态、session 和事件记录属于控制面，不是 Agent 可写产物。每个 run 独立目录，禁止用 latest 路径传递阶段输入。

## PRD 阶段

输入：instruction.md、organization-delivery.md、templates/prd.md、Base 源码及版本清单。角色：roles/pm.system.md。

输出：artifacts/sprint1/prd/prd.md，必须按照 [PRD 模板](templates/prd.md) 填写。保留固定标题、字段和 ID 位置。需求用 R01；验收条件用 AC-01-1。优先级定义见模板。事实、产品决定和假设要能区分。不单独增加升级兼容槽位，任务涉及的要求写入相应需求。

提交后由运行器检查并封存；下一阶段的输入就是这份文件，不复制为另一套有歧义的 PRD.md。运行器记录其内容哈希。PM 不生成 TDD。

## 技术设计阶段

输入：原始 instruction.md、公开规范、相同 Base、前一阶段已封存的 prd.md，以及其余五份模板。角色：roles/architect.system.md。PRD 缺失或来源不匹配时不能启动。

输出：frontend-design.md、backend-design.md、interface-contract.md、target-schema.graphql、review.md，全部位于 artifacts/sprint1/tech-design/。

前后端文档严格使用对应模板；FD / BD 覆盖 R，BT 引用 BD，接口 I 归属 BD，前端通过 I 引用权威接口契约。编号发布后不重排、不复用。字段与 ID 位置固定，具体设计内容在粗粒度槽位中展开。

本轮 Saleor 必须交付完整目标 GraphQL SDL，不是 diff。未变更部分与 Base 一致；不能拷贝未来 Target。其他变化的对外边界使用其已有描述格式，放在 interfaces/ 并在接口契约中登记。文本产物统一 Markdown；协议描述保留原生格式。

前端和后端是两种开发职责。架构师在本阶段同时生成两端设计；异步任务、迁移、外部集成归后端，不新增“第三端”。

## 技术评审与交接

在技术设计阶段内先形成设计草稿，再按照 technical-review.md 自审。可在该阶段内修正未封存的设计草稿，但不能返回 PRD 阶段或修改已封存 PRD。

review.md 必须逐条对照 R，说明前后端承担、接口一致性、工程依赖与未解决问题；结论仅为 pass 或 blocked。存在未解决阻塞项时为 blocked。仍保存已有产物，运行状态为 blocked；不能把“报告已提交”当作“评审已通过”。

无论评审结论如何，本轮都在此结束。未运行的业务测试、迁移、服务启动与部署不得写成已验证。

## 三种运行模式的共同契约

- Single：一个主原生会话跨阶段延续；固定向前。每个边界由运行器激活对应角色、结束上一阶段子任务并封存产物。
- Flat：每个 stage 新 Agent；只传声明的 workspace 输入与已接受产物。当前两阶段不并行；未来前后端开发可按另一个 Code stage 的配置并行。
- Hierarchical：Lead 自主组织角色，允许返修；本表 stage 描述交付类别，不是强制执行顺序。每次接受产生新 revision；最终交付必须引用同一组相容版本。Lead Blueprint、团队 Skill 和工具需要实现后才能运行。

三种模式共用模板、角色、产物标识和目录。运行器负责权限与流程约束，仅在 prompt 中写“不得回退”不能构成强制保证。
