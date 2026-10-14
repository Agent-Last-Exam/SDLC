# 四模型文档阶段 rollout 记录

仅运行 PRD、技术设计、测试用例设计。没有开发、部署或 QA 执行阶段。

| 模型 | 档位 | 状态 | 已完成阶段 | 模型执行起累计分钟 | 缓存读取 token | 网关响应报告费用 |
| --- | --- | --- | ---: | ---: | ---: | --- |
| opus55-xhigh | xhigh | failed | 0/3 | 2.55 | 726,482 | $0.7198124 |

每模型累计上限 60 分钟；缓存开启且有实际命中证据。流式用量按请求最终快照归并，缓存不重复叠加。
输入优先采用显式原生 billing_usage 的含缓存 prompt_tokens；缺少原生计费字段时，按 Anthropic 输入不含缓存的协议口径归一化。
网关响应费用是 usage.billing_usage.openai_usage.cost 的报告值，不等于后台账单已对账；缺少字段时不估造费用。客户端 total_cost_usd 不作为实际扣费依据。
accepted 表示文件交付被运行器接受，尚未进行独立内容评测。

## opus55-xhigh

状态：failed；已完成 0/3 阶段。
运行器错误：Missing regular output: /workspace/artifacts/sprint1/prd/prd.md
原生客户端最后 stop_reason=error，仅有截断思考内容；客户端 is_error=false / terminal_reason=completed，但 PRD 缺失。错误来自网关还是上游尚未确认。未自动重跑。

交付文件数：0；详细用量、版本、阶段及哈希见 results.json。

验证：86 项运行器/用量测试通过；三阶段容器 smoke 到边界即停；独立超时看门狗实测终止三个阶段身份下的进程。
四模型原生工具循环与缓存预检通过；题目及仓库基线与之前 GPT-6.1 rollout 一致。
请求审计证明发往网关的模型、thinking、effort、缓存标记；不证明网关私有上游路由或各厂商对 effort 的解释。
