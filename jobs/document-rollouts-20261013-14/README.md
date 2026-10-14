# 文档阶段 rollout 轨迹与产物（2026-10-13～14）

记录同一道 Saleor 3.23 题的 7 个逻辑运行、10 个原始 job。仅运行 PRD、技术设计、测试用例设计；未进入开发、部署或 QA 执行阶段。原始失败、超时、用户停止及运行器边界记录保持原样。

| 轮次 | 模型／档位 | 有效状态 | 交付阶段 | 用例数 | 网关报告费用 |
| --- | --- | --- | ---: | ---: | --- |
| 首轮 | anthropic/claude-opus-5.5 / xhigh | failed | 0/3 | — | $0.7198124 |
| 首轮 | deepseek/deepseek-v4.1-flash / high | stopped_at_boundary | 3/3 | 80 | 未返回 |
| 首轮 | moonshotai/kimi-k3 / max | stopped_at_boundary | 3/3 | 41 | $2.84351808 |
| 首轮 | z-ai/glm-5.3-flash / max | timed_out | 1/3 | — | 未返回 |
| GLM 重跑 | z-ai/glm-5.3-flash / max | stopped_at_boundary | 3/3 | 35 | 未返回 |
| Opus xhigh 重跑／用户停止 | anthropic/claude-opus-5.5 / xhigh | user_stopped | 0/3 | — | $18.4234668（部分请求） |
| Opus high 新轮＋边界续做 | anthropic/claude-opus-5.5 / high | stopped_at_boundary | 3/3 | 144 | $53.918911（部分请求） |

所有正式轮次均启用缓存并有实际命中证据。费用仅为网关响应报告值，未与后台账单对账；没有字段的请求不推测费用。输入总量包含缓存读取／写入，不重复叠加。流式 usage 按请求最终已捕获快照去重；客户端 total_cost_usd 不作为实际扣费依据。

关键中断和续做事实：

- Kimi 原轮因运行器把 SDK 自动压缩摘要误识别为角色激活而停止；验证原正常 end_turn、角色和文件后，同会话仅续做测试设计，原一小时截止不延长。
- 首轮 GLM 在累计一小时截止停止，仅交付 PRD；后续新轮取消限时，三阶段交付完成。
- Opus xhigh 首轮流式异常，未交付 PRD。次日重跑曾人工暂停以移除限时并追加恢复指令，之后用户要求停止；仍未交付 PRD。此轮不能视为未受干预的连续 rollout。
- Opus high 使用全新隔离环境和会话。技术设计正常完成后触发默认 $50 客户端估算预算（当时客户端约 $57.28、网关已报告约 $27.58）。保留 budget_exhausted 原记录后恢复同一会话和原已接受文件，仅执行原定测试设计，不添加额外恢复指令。存在运行器边界续做，不能视为未受干预的连续运行。

产物和日志导航：

- [single-docs-deepseek41-high-20261013](../single-docs-deepseek41-high-20261013/)：[原始状态](../single-docs-deepseek41-high-20261013/task__JGXPpQm/workflow/state.json)、[事件](../single-docs-deepseek41-high-20261013/task__JGXPpQm/workflow/events.jsonl)、[轨迹](../single-docs-deepseek41-high-20261013/task__JGXPpQm/agent/trajectory.json)、[已接受产物](../single-docs-deepseek41-high-20261013/task__JGXPpQm/workflow/accepted/)。
- [single-docs-glm53flash-max-20261013](../single-docs-glm53flash-max-20261013/)：[原始状态](../single-docs-glm53flash-max-20261013/task__Aouwagg/workflow/state.json)、[事件](../single-docs-glm53flash-max-20261013/task__Aouwagg/workflow/events.jsonl)、[轨迹](../single-docs-glm53flash-max-20261013/task__Aouwagg/agent/trajectory.json)、[已接受产物](../single-docs-glm53flash-max-20261013/task__Aouwagg/workflow/accepted/)。
- [single-docs-glm53flash-max-retry-20261014](../single-docs-glm53flash-max-retry-20261014/)：[原始状态](../single-docs-glm53flash-max-retry-20261014/task__oUgV9U2/workflow/state.json)、[事件](../single-docs-glm53flash-max-retry-20261014/task__oUgV9U2/workflow/events.jsonl)、[轨迹](../single-docs-glm53flash-max-retry-20261014/task__oUgV9U2/agent/trajectory.json)、[已接受产物](../single-docs-glm53flash-max-retry-20261014/task__oUgV9U2/workflow/accepted/)。
- [single-docs-kimi-k3-max-20261013](../single-docs-kimi-k3-max-20261013/)：[原始状态](../single-docs-kimi-k3-max-20261013/task__HHz96Rh/workflow/state.json)、[事件](../single-docs-kimi-k3-max-20261013/task__HHz96Rh/workflow/events.jsonl)、[轨迹](../single-docs-kimi-k3-max-20261013/task__HHz96Rh/agent/trajectory.json)、[已接受产物](../single-docs-kimi-k3-max-20261013/task__HHz96Rh/workflow/accepted/)。
- [single-docs-kimi-k3-max-continuation-20261013](../single-docs-kimi-k3-max-continuation-20261013/)：[原始状态](../single-docs-kimi-k3-max-continuation-20261013/task__eY6C9jZ/workflow/state.json)、[事件](../single-docs-kimi-k3-max-continuation-20261013/task__eY6C9jZ/workflow/events.jsonl)、[轨迹](../single-docs-kimi-k3-max-continuation-20261013/task__eY6C9jZ/agent/trajectory.json)、[已接受产物](../single-docs-kimi-k3-max-continuation-20261013/task__eY6C9jZ/workflow/accepted/)。
- [single-docs-opus55-high-20261014](../single-docs-opus55-high-20261014/)：[原始状态](../single-docs-opus55-high-20261014/task__vMvSwRQ/workflow/state.json)、[事件](../single-docs-opus55-high-20261014/task__vMvSwRQ/workflow/events.jsonl)、[轨迹](../single-docs-opus55-high-20261014/task__vMvSwRQ/agent/trajectory.json)、[已接受产物](../single-docs-opus55-high-20261014/task__vMvSwRQ/workflow/accepted/)。
- [single-docs-opus55-high-continuation-20261014](../single-docs-opus55-high-continuation-20261014/)：[原始状态](../single-docs-opus55-high-continuation-20261014/task__b8VLrwE/workflow/state.json)、[事件](../single-docs-opus55-high-continuation-20261014/task__b8VLrwE/workflow/events.jsonl)、[轨迹](../single-docs-opus55-high-continuation-20261014/task__b8VLrwE/agent/trajectory.json)、[已接受产物](../single-docs-opus55-high-continuation-20261014/task__b8VLrwE/workflow/accepted/)。
- [single-docs-opus55-xhigh-20261013](../single-docs-opus55-xhigh-20261013/)：[原始状态](../single-docs-opus55-xhigh-20261013/task__y4Wfq6m/workflow/state.json)、[事件](../single-docs-opus55-xhigh-20261013/task__y4Wfq6m/workflow/events.jsonl)、[轨迹](../single-docs-opus55-xhigh-20261013/task__y4Wfq6m/agent/trajectory.json)、正式产物未交付。
- [single-docs-opus55-xhigh-resume-20261014](../single-docs-opus55-xhigh-resume-20261014/)：[原始状态](../single-docs-opus55-xhigh-resume-20261014/task__MjcF4mz/workflow/state.json)、[事件](../single-docs-opus55-xhigh-resume-20261014/task__MjcF4mz/workflow/events.jsonl)、[轨迹](../single-docs-opus55-xhigh-resume-20261014/task__MjcF4mz/agent/trajectory.json)、正式产物未交付。
- [single-docs-opus55-xhigh-retry-20261014](../single-docs-opus55-xhigh-retry-20261014/)：[原始状态](../single-docs-opus55-xhigh-retry-20261014/task__3UfmikH/workflow/state.json)、[事件](../single-docs-opus55-xhigh-retry-20261014/task__3UfmikH/workflow/events.jsonl)、[轨迹](../single-docs-opus55-xhigh-retry-20261014/task__3UfmikH/agent/trajectory.json)、正式产物未交付。

推荐先阅读 [有效结果与合并用量](effective-results.json)，再查看各原始 job。用户停止可能在底层显示 failed / exit143；有效状态由停止标记和事实说明识别，未重写原状态。Harbor result.json 的整体 trial 成功不能替代阶段交付检查。

- [配置与题目基线快照](configuration/)：每个 job 的 recipe、三阶段图、题目、角色、模板及冻结仓库基线。
- [汇总报告、缓存／工具预检与隔离证据](evidence/)：原 Telegram 报告与规范化结果。
- [实际运行器源码快照](runtime-snapshot/)：仅供审计，不修改仓库现有运行器。
- CLI 本地设置、备份和机器／用户标识不发布；会话 JSONL、工具结果和正式产物完整保留，原始文件仍在本机。
- [发布文件清单及哈希](published-files.json)、[隐私检查结果](privacy-check.json)。

本提交验证产物哈希、CSV 结构、角色／主会话连续性、请求模型与 effort／缓存标记、阶段边界和已知凭据扫描。未做独立内容评测，accepted 仅代表阶段文件交付被运行器接受。请求审计不独立证明网关私有路由或其对 effort 的解释。

不包含早先 GPT-6.1 全流程 rollout／代码评测。仓库现有运行器文件不做修改；实际运行时源码仅作为审计快照保存。
