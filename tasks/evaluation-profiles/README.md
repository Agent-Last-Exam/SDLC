# 独立评测配置

`saleor-3.23-no-browser.json` 从完整剪枝题派生不含浏览器 E2E 的独立评测包。
原始 `tasks/saleor-3.23-pruned` 保持不变，派生包使用不同的 task / release 标识。

在仓库根目录生成到一个不存在的新目录：

```bash
python3 -m runtime.prepare_evaluation --output .prepared/saleor-no-browser-v1/task
```

派生包保留 `core-unit`、`core-e2e`、`dash-unit`，前后两轮均不执行 `dash-e2e`，评分清单也同步移除浏览器用例。
F2P 5,182，P2P 15,012，共 20,194 项；保留原测试补丁和参考代码补丁。
仍需真实数据库、后端服务和 Dashboard 构建，不是纯静态或纯后端评测。

`reward.json` 只输出 `{"reward": 0}` 或 `{"reward": 1}`，供 Harbor 解析。
详细指标和报告路径放入 `reward-details.json`，CTRF 和 `reward.txt` 继续保留。
通过条件仍要求选中测试 post 全通过、pre F2P 无通过且 pre P2P 全通过。

要执行真实无模型校准，可使用生成的独立 task：

```bash
harbor run --agent oracle --path .prepared/saleor-no-browser-v1/task --n-concurrent 1 --verifier-timeout-multiplier 3
harbor run --agent nop --path .prepared/saleor-no-browser-v1/task --n-concurrent 1 --verifier-timeout-multiplier 3
```

这些命令不是快速运行：剩余三组测试仍会跑前后两轮。生成不会启动测试、容器或模型。
剔除浏览器改变了评测范围，新配置分数不能与完整配置直接比较；不能把排除 18 项基线争议当成解决原完整清单的校准问题。

## 本机验证（2026-10-13）

生成已通过；脚本语法校验通过；现有输出目录会被拒绝覆盖。
从保存的 `saleor-oracle-20261013-r4` 三组 pre/post 测试报告离线重算：

- 参考实现：F2P 5,182/5,182，P2P 15,012/15,012，reward 1。
- 基线对照（同一份 pre 报告作为前后结果）：F2P 0/5,182，P2P 15,012/15,012，reward 0。
- 两种 reward.json 都经 Harbor 0.24.0 的实际解析器验证通过。
- 原输出中的 reports 字典触发的解析错误也已复现。
- 原完整题包文件哈希未变化；生产/官方测试补丁与环境文件未变化。

这验证了范围过滤和评分格式；没有启动新容器、模型或新一轮完整 oracle/NOP。
生成包：`.prepared/saleor-no-browser-v1/task`；验证记录：`.prepared/saleor-no-browser-v1/validation.json`。
