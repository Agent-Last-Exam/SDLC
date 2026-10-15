# DeepSeek Flat coding 重跑终态监督报告

Job：flat-coding-deepseek41-high-restart-20261015-r3
Trial：task__G8uLjvp

## 结果

未完成 coding 提测封存。2026-10-15 02:41:08 UTC 开始执行 development，06:41:09 左右触发单 Stage 14400 秒（4 小时）上限；06:43:18 Harbor 完成日志和快照回收。workflow/state.json 终态为 timed_out。

没有判定明确死循环，也没有人工提前停止。最后一次监督仍看到后端测试推进和前端测试进程。本轮没有自动重跑或改模型，定时监督任务 7f1ce330 已删除。

Harbor 结果另记 AgentTimeoutError / 16200 秒；workflow 原始事件明确先发生单阶段 14400 秒超时。因此本报告按实际 Stage 截止事件说明终止原因，不把 Harbor 外层错误文案当作实际已执行 4.5 小时的证据。

## 代码和文档回收

成功保存双仓未验收工作区归档：
`jobs/flat-coding-deepseek41-high-restart-20261015-r3/task__G8uLjvp/workflow/partial-candidates/sprint1/development/repos.tar`

- 大小：1,189,939,200 字节，约 1.19 GB。
- SHA256：836d92e0c3df95db7ccc5aa79ae698d9aaaea052a5b90d00412cfe304a9b8ba2。
- 逐文件核验 101,309 个常规文件，均与 manifest 匹配；缺失和哈希不符均为 0。
- 归档路径检查未发现绝对路径或父目录跳转。
- 这是超时后的 partial candidate，accepted=false，不能作为已验收 coding 交付。
- development 正式 accepted 快照不存在，partial-artifacts 目录为空，未回收到正式 test-handoff.md。
- 原 PRD、技术设计、接口补充协议、目标 schema、217 条测试用例对应的 8 个封存文件哈希全部一致。
- 另保留 06:27 和 06:37 UTC 两份增量补丁及未跟踪源码备份；它们不是原子封存快照。

launcher 已退出，专属容器已回收。本轮代码已保留，可供后续恢复评估。

## 测试事实和未完成项

以下来自执行日志，属于 rollout 自测；没有再独立重跑测试。不同批次可能重叠，不累计通过数量。

- 前端定向集成测试：187 个 suite 通过，1236 项通过，3 项跳过。
- 后端订单 GraphQL 某次回归：1855 项通过。
- 后端 app/webhook 后续回归：1449 项通过。
- 后端 payment/giftcard 回归：937 项通过。
- 最近日志中的 checkout 较大回归仍有 8 项失败、1574 项通过、1 项错误；错误涉及数据库 flush。模型推测可能与并行数据库争用有关，尚未经独立确认。
- 前端全量 Jest 未找到最终成功汇总；TypeScript 检查仍出现 Storybook 模块解析错误。
- 运行中修改过部分测试预期；定向通过不能替代业务验收或全量回归通过。

未形成正式提测报告，未完成全量验证，未执行部署和 QA。

## 本轮冻结配置

DeepSeek deepseek/deepseek-v4.1-flash，high；Flat；Claude Code 2.1.280。仅恢复先前三阶段封存文档，从干净基线重新 coding，不恢复旧开发代码和聊天。独立镜像 talon-flat-deepseek-coding:20261015-0220，Redis 已预装并在启动时检查 PONG。

单阶段上限 14400 秒，Harbor 外层配置 16200 秒，没有显式总模型时限。请求证据共 20649 行（包括审计事件，不代表 20649 次模型请求）。未以 workflow 的未结算 cost_usd=0 推断实际花费为零。
