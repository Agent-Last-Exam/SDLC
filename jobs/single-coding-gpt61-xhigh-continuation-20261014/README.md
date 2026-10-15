# GPT 6.1 xhigh：coding 续跑与独立 F2P/P2P 评测

本目录统一归档 coding job 的交付和派生评测，但它们是独立执行的 job/trial。`run-lineage.json` 绑定文档源、coding原始快照、原始候选补丁及评测副本。

- 文档源：`single-docs-gpt61-xhigh-instruction-20261014 / task__Fq5bK83`。
- coding：`single-coding-gpt61-xhigh-continuation-20261014 / task__DuLbKeC`。恢复原生同一会话，约170.84分钟后正常停在development；原13份文档及代码快照已核对。
- 独立评测：`coding-f2p-p2p-gpt61-20261015-retry1 / task__JetSyCL`，无模型调用。F2P98/5182、P2P14671/15012，严格reward0，341项P2P回归。

## 交付与证据

- `artifacts/test-handoff.md`：部分实现、整体发布阻断；自动成单、资金账本等未完成。
- `coding/`：原始完整候选补丁，含模型修改的测试，8237个源码/符号链接条目回放验证。
- `agent/trajectory.json.gz`：结构化coding轨迹；不包含原生session目录、CLI设置或认证文件。
- `workflow/`：阶段状态、事件、基线、实际提示及请求审计。
- `configuration/`：输入/执行代码哈希、原候选回放校验；历史运行依赖本地主工作区扩展，不声称当前PR基线可完整复现历史启动CLI。
- `evaluation/报告.md`：F2P/P2P结果；六份原始JUnit/Jest、全部20194项状态、执行日志与环境身份。
- `evaluation/candidate-patches/`：真正送入评测的独立副本补丁，与`coding/`的原样补丁分开保存。

## 评测限制

采用既有no-browser派生配置，不含浏览器E2E。原样候选修改与冻结T在4个文件产生冲突，独立评测副本恢复31个测试/fixture文件的冻结基线，再应用原冻结T；业务代码未修复。选择、测试补丁与grader公式未改变。见evaluation-projection.json，不将分数称作原样候选测试树的得分。第一次镜像缺失失败不计模型0分；随后按冻结Dockerfile重建镜像并重跑，不能声称新旧二进制镜像相同。

部署和QA尚未执行。续接时应恢复原始coding快照、已接受文档和原生session，不使用评测投影；需扩展当前四阶段续跑图和恢复器，停止边界应另行明确。部署/QA不会自动补齐已缺失需求；验收失败可在独立授权范围进入triage/修复循环。原生session及含依赖完整快照留在原始本机job中，未提交到Git。不会自动合并PR。
