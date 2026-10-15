# 四模型文档阶段 rollout 记录

仅运行 PRD、技术设计、测试用例设计。没有开发、部署或 QA 执行阶段。

| 模型 | 档位 | 状态 | 已完成阶段 | 模型执行起累计分钟 | 缓存读取 token | 网关响应报告费用 |
| --- | --- | --- | ---: | ---: | ---: | --- |
| opus55-xhigh | xhigh | failed | 0/3 | 2.55 | 726,482 | $0.7198124 |
| deepseek41-high | high | stopped_at_boundary | 3/3 | 17.9 | 12,675,456 | 未返回 |
| kimi-k3-max | max | stopped_at_boundary | 3/3 | 32.2 | 3,573,504 | $2.84351808 |
| glm53flash-max | max | timed_out | 1/3 | 60.02 | 17,735,424 | 未返回 |

每模型累计上限 60 分钟；缓存开启且有实际命中证据。流式用量按请求最终快照归并，缓存不重复叠加。
输入优先采用显式原生 billing_usage 的含缓存 prompt_tokens；缺少原生计费字段时，按 Anthropic 输入不含缓存的协议口径归一化。
费用表仅含正式 rollout 请求，短请求预检另计。网关响应费用是 usage.billing_usage.openai_usage.cost 的报告值，不等于后台账单已对账；缺少字段时不估造费用。客户端 total_cost_usd 不作为实际扣费依据。
accepted 表示文件交付被运行器接受，尚未进行独立内容评测。

## opus55-xhigh

状态：failed；已完成 0/3 阶段。
运行器错误：Missing regular output: /workspace/artifacts/sprint1/prd/prd.md
原生客户端最后 stop_reason=error，仅有截断思考内容；客户端 is_error=false / terminal_reason=completed，但 PRD 缺失。错误来自网关还是上游尚未确认。未自动重跑。

交付文件数：0；详细用量、版本、阶段及哈希见 results.json。

## deepseek41-high

状态：stopped_at_boundary；已完成 3/3 阶段。

交付文件数：6；详细用量、版本、阶段及哈希见 results.json。

## kimi-k3-max

状态：stopped_at_boundary；已完成 3/3 阶段。
原轮因检查器误把自动压缩摘要当成角色激活而中止；修正检查后验证原角色与正常结束记录，恢复原会话只续做测试设计。前两阶段文件未重做，原 60 分钟绝对截止未延长。用量合并原轮和续做请求，每个请求只计一次。

交付文件数：6；详细用量、版本、阶段及哈希见 results.json。

## glm53flash-max

状态：timed_out；已完成 1/3 阶段。
运行器错误：Total model execution wall time exhausted
累计 60 分钟到点中断，未自动加时或重跑。末条中断请求可能缺少最终 usage，统计仅包含已捕获的报告值。

交付文件数：1；详细用量、版本、阶段及哈希见 results.json。

验证：88 项运行器/用量测试通过；三阶段容器 smoke 到边界即停；独立超时看门狗实测终止三个阶段身份下的进程。
四模型原生工具循环与缓存预检通过；题目及仓库基线与之前 GPT-6.1 rollout 一致。
请求审计证明发往网关的模型、thinking、effort、缓存标记；不证明网关私有上游路由或各厂商对 effort 的解释。

GLM 在 60 分钟处终止模型与工具；随后快照/清理约 1.4 秒，因此表内结束事件累计为 60.02 分钟。
