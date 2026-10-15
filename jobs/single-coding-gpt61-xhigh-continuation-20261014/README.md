# GPT 6.1 xhigh：coding 与独立 F2P/P2P 结果

文档源：`single-docs-gpt61-xhigh-instruction-20261014 / task__Fq5bK83`。coding：`single-coding-gpt61-xhigh-continuation-20261014 / task__DuLbKeC`，恢复同一原生会话，约 170.84 分钟后停在 development；135 文件、+6772/-943 行。

- `artifacts/test-handoff.md`：正式提测报告；部分实现、整体发布阻断。
- `coding/`：原始完整候选补丁，包含模型修改的测试。
- `agent/trajectory.json.gz`：coding 结构化轨迹。
- `evaluation/报告.md`、`summary.json`、`selected-test-results.csv`：独立评测结论、汇总及 20,194 项逐项结果。
- `evaluation/candidate-patches/`：实际送测副本补丁；`evaluation-projection.json` 与 `environment-provenance.json` 保留解释分数所需的候选差异和环境身份。

两个应用仓库的补丁基线：Saleor `c864e66b8e537d30732ddba62d3a4c47e49e4a3e`，Dashboard `aebb2401b5079fbbb8c60150289d1896c108feca`。

独立评测：`coding-f2p-p2p-gpt61-20261015-retry1 / task__JetSyCL`，F2P 98/5182，P2P 14671/15012，严格 reward 0，341 项 P2P 回归。评测副本恢复 31 个测试/fixture 的冻结基线后应用原冻结 T，业务代码未修复；该分数对应该副本。不含浏览器 E2E，未部署或执行正式 QA。续跑应恢复原始 coding 快照，不能使用评测投影替代。

开发报告中的 evidence 路径指向本地保留的原始自测记录；辅助日志、源码清单和配置快照不纳入精简归档。验证结论与历史执行环境限制见 PR 描述。

## 当次阶段提示词

当时保存的职责、用户阶段指令及原生注入证据见 [prompt-snapshots/](prompt-snapshots/README.md)，按原始 job、trial、阶段区分，并标记继承快照。该补充不代表完整供应商请求或全部子会话日志。
