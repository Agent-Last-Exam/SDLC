# Role Blueprint

这里的 Role Blueprint 是本 task 的角色 system prompt，每份以职业身份和具体工作展开，说明参考材料、代码仓库、模板和交付文件的位置。角色只需要了解自己的工作。业务目标由 instruction.md 提供，字段和格式由对应模板定义。

| 角色 | Prompt | 输入 | 输出 |
| --- | --- | --- | --- |
| PM | [pm.system.md](pm.system.md) | Instruction、Base 与 PRD 模板 | artifacts/sprint1/prd/prd.md |
| 软件架构师（architect） | [architect.system.md](architect.system.md) | 原始输入、PRD、技术模板 | artifacts/sprint1/tech-design/ 下的 frontend-design.md、backend-design.md、interface-contract.md、target-schema.graphql，按需附 interfaces/ |
| QA：测试设计（qa-design） | [qa-design.system.md](qa-design.system.md) | PRD、四份技术产物、当前源码、测试用例模板 | artifacts/sprint1/test-design/test-cases.v1.csv |
| 开发主管：开发（developer） | [developer.system.md](developer.system.md) | PRD、四份技术产物、当前源码、提测报告模板；返工时增加上一轮 QA 产物 | repos/ 中的代码；artifacts/sprint1/development/test-handoff.md |
| 开发主管：部署（deployer） | [deployer.system.md](deployer.system.md) | 已开发代码、提测报告、当前环境的部署配置与资源 | 可测试环境；更新 artifacts/sprint1/development/test-handoff.md |
| QA：测试执行（qa） | [qa.system.md](qa.system.md) | 测试用例、更新后的提测报告、可测试环境、PRD、技术产物、当前源码、QA 模板 | artifacts/sprint1/qa/ 下的 test-results.{round}.csv、test-report.{round}.md、test-verify.json |

这些路径相对 `/workspace`。PM、架构师保留用户删减后的提示词。新增角色沿用相同风格，只交代职业身份、工作、输入和输出。部署是开发主管承担的另一个阶段，QA 分为开发前设计用例和部署后执行测试两次工作。

## 阶段与交接定义

PM → Architect → QA 测试设计 → 开发 → 部署 → QA 测试执行。

开发角色接到任务时，以技术方案已完成评审为工作前提；这里不新增 Architect 自审步骤或 review.md，也不把格式检查称作技术评审。

开发先写提测报告，部署在原路径更新这份报告的部署版本、测试入口和验证方式。QA 使用更新后的报告进入环境。部署完成是可供 QA 开始测试的条件，开发报告中的“待部署”信息不能作为已可测试环境交接。

首轮 QA 的 `round` 为 1，记录为 `test-results.1.csv` 和 `test-report.1.md`。`test-verify.json` 仅包含 `round` 和 `verdict`：

```json
{"round": 1, "verdict": "fail"}
```

Workflow 读取同轮 JSON：`pass` 结束本次交付；`fail` 将同轮执行记录和测试报告交回开发，之后重新部署、交给 QA 复测。返工沿用 PRD、技术设计及已设计的测试用例，不自动重跑 PM 和 Architect。复测轮次递增，执行记录和报告使用新的轮次文件名，保留上一轮文件及 JSON 快照；提测报告和当前 `test-verify.json` 在固定路径更新。

后续接入运行器时，由 Workflow 在每次任务中提供实际轮次、测试用例版本、上一轮报告及本轮输出路径。QA 报告给出测试结论，JSON 表达同一结论；此处不增加通过率阈值或其他业务判定规则。

## 当前执行状态

四份新角色 Prompt 与对应模板已定义；自动执行及返工循环尚未接入运行器。现有 Single/Flat 配置仍只运行 PM、Architect 两个阶段并停止，不会自动启动开发或部署。当前运行器的源码只读、上游产物不可改写和阶段结束清理进程等机制，也尚未适配代码修改、同一提测报告更新及跨阶段保留测试环境。

[模板](../templates/README.md) 定义文档格式；[当前 workflow 配置](../workflows/design-delivery.yaml) 供运行器执行。运行器仅附加本次材料和交付文件的路径列表，不传入阶段配置 JSON 或控制器说明。base-revisions.json 供准备器核对仓库版本，不作为角色的阅读任务。Agent 不再读取额外公共规范，也不需要交付自审报告。

准备器 `runtime/prepare_workflow.py` 可以校验配置并冻结公开工作区，不调用模型。Controller、Codex 原生会话角色切换与产物门禁已接入 `runtime/run_workflow.py`；运行结果与适用边界详见 [当前落地与剩余工作](../../../docs/instruction-to-review.md)。
