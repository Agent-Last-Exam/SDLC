# DeepSeek V4.1 Flash / high：Single 与 Flat coding 中断记录

保存真实运行的失败轨迹和可恢复代码，供复盘中断与比较执行过程。以下运行均没有接受 development 交付，未部署或执行独立业务 QA；不得将代码快照视为完成验收。

| 目录 | 模式和范围 | 结果与保存情况 |
| --- | --- | --- |
| `single-continuation/` | Single 同会话恢复文档检查点后继续 coding；轨迹包含先前文档历史 | Harbor 超时，未保存代码快照；保留原始 interrupted 状态及连续会话轨迹 |
| `flat-initial/` | Flat 首次进入 coding；轨迹仅恢复 coding 会话 | 3 小时总执行上限中断，未回收 coding 快照 |
| `flat-restart/` | Flat 复用封存文档，从干净代码重新 coding；轨迹仅 coding | 4 小时 Stage 上限中断；已回收双仓 partial candidate，导出含新增文件的完整源码补丁 |

源 job/trial、轨迹步数、超时错误原文和历史状态见 `attempts.json` 与各目录 `summary.json`。Flat 两份 coding ATIF 是本次从已回收原生会话离线转换，包含可恢复主/子会话，不虚构未保存事件；原 job 的自动 ATIF 仅覆盖完成阶段，因此不能用原导出替代失败阶段轨迹。Single 导出保留原连续历史，包含文档内容，分析时应避免重复计数。历史 CLI/converter token 与费用字段不是已核对账单，部分中断统计不完整。

`flat-restart/code-diffs/` 的补丁对应 Saleor `c864e66b8e537d30732ddba62d3a4c47e49e4a3e` 和 Dashboard `aebb2401b5079fbbb8c60150289d1896c108feca`。均通过对应 baseline 的索引应用检查和完整源码回放核验；见 `verification.json`。补丁保留原字节，未修复候选业务代码或测试。含源码和测试改动，不含依赖、认证环境或完整 Git 历史。

1.19 GB 最终 partial candidate 和额外实时备份保留本机。`snapshot-verification.json` 记录归档哈希及逐文件核验；这只是回收完整性，不是业务通过。前两次运行没有回收到代码，不能从轨迹声称已重建同等快照。启动前镜像/路径/硬链接等预检失败另见下方摘要，没有计作模型失败轮次。

最近一次 Flat 的自测中，前端定向集成集 187 suites / 1236 passed / 3 skipped；后端部分定向回归通过，但最后 checkout 较大回归仍有 8 failed、1574 passed、1 error。前端全量 Jest 没有找到最终成功汇总，TypeScript 检查仍有 Storybook 模块解析错误。各批次可能重叠，不能累计通过数；没有独立重跑这些业务测试。详细监督见 `flat-restart/supervision-report.md`。

Single 首次续跑在客户端路径检查失败；Flat 首次全流程启动因基础镜像缺失失败，coding 重启的前两次分别在客户端路径和硬链接预检失败。它们均在相应模型执行前失败，仅作环境历史说明。实际模型运行标识以 `attempts.json` 为准。

文档产物分别已归档于 PR #4（DeepSeek Single）和 PR #7（DeepSeek Flat），此处不重复提交。全部发布文本和解压轨迹已扫描配置凭证/端点及常见 token 模式，敏感值替换为 `[REDACTED]`，操作员本机路径已规范化；原始本地记录不修改。全量请求审计和原生日志留本地，不重复堆叠。可执行 `sha256sum -c checksums.sha256` 检查归档。

Single 和 Flat 恢复的是各自生成的文档检查点，coding 起点、会话历史及时间预算不同；本归档用于复盘，不构成控制变量充分的模式优劣实验。Single 未回收到代码，不能用它与 Flat 做同等源码或测试成绩比较。
