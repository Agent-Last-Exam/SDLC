# Saleor Flat rollout — GPT-6.1-Sol / xhigh

本目录归档一次真实模型实验：PRD → 技术设计（TDD）→ QA 用例设计 → coding。四阶段均已封存，最终停止在 `sprint1/development`；未部署，也未运行独立业务 QA。使用四个独立主会话，阶段内可调用子 Agent。

**流程完成不代表业务验收通过。** 开发交接报告明确保留 P0 功能缺口、失败回归和失败门禁；本次产物不是可直接生产发布的版本。详见 `documents/sprint1/development/test-handoff.md` 的 D01—D09。

| 路径 | 内容 |
| --- | --- |
| `inputs/` | 本次运行实际使用的业务说明、业务对话和代码 baseline commit |
| `documents/sprint1/prd/` | 已封存 PRD |
| `documents/sprint1/tech-design/` | 前后端技术设计、接口契约、GraphQL SDL、OpenAPI/边界 schema |
| `documents/sprint1/test-design/` | 已封存 440 条 QA 用例 |
| `documents/sprint1/development/` | 开发交接、代码清单与本地开发自测证据 |
| `code-diffs/` | 后端和 Dashboard 相对原 baseline 的补丁，包含新增文件 |
| `trajectories/trajectory.atif.json.gz` | 覆盖四阶段的完整导出 ATIF trajectory，保留子 Agent/sidechain 标记；已做敏感信息替换 |
| `trajectories/manifest.json` | 轨迹格式、步数、阶段分布和导出哈希 |
| `metadata/` | 模型配置、主会话标识、阶段提示词、原生角色证据、脱敏统计 |
| `verification.json` | 封存产物与候选归档核验、补丁基线检查结果 |
| `coding-timing-summary.json` | Coding 请求耗时统计；不是纯网络延迟测量 |
| `report.md` | 交付范围、性能分析及验证边界 |
| `checksums.sha256` | 此目录导出文件的 SHA256 |

## 结果及验证

- GPT-6.1-Sol，`xhigh`，Claude Code 2.1.280，请求审计开启；无金额预算或模型执行时限。
- 四个主会话独立；各阶段原生角色激活及封存文件哈希核验通过。压缩轨迹只保留最终 coding job 的完整导出，不重复叠加前两个 job 的轨迹。
- 两个补丁均通过对对应 baseline 的 `git apply --cached --check`，基线见 `inputs/base-revisions.json`；这是补丁可应用性验证，不代表功能验收。
- 已核对封存开发自测日志：Core 新增整合集 551 passed；公开输入回归 205 passed；Dashboard 改动测试 77 suites / 741 tests passed；类型检查通过。集合可能重叠，不累计为一个总通过数。
- 资金混合回归、既有 OIDC 回归、全仓 lint/knip 等仍有失败；未完成的业务分支见交接文档。没有独立重跑所有业务测试。
- 镜像丢失、依赖硬链接及跨 job 角色证据恢复问题曾阻断续跑；PRD/设计和 QA 完成后均从封存边界继续，没有重跑已完成模型阶段。运行器修复不属于此归档 PR。

## 使用

在本目录运行：

```bash
sha256sum -c checksums.sha256
gzip -dc trajectories/trajectory.atif.json.gz > /tmp/saleor-flat-trajectory.json
```

代码补丁分别针对 Saleor 和 saleor-dashboard 两个仓库，在各自 baseline checkout 上执行 `git apply --check <对应补丁>` 后再应用。本归档保持 SDLC 仓库的单个 commit，不把两个应用仓库的 Git 历史合并到 SDLC。

完整候选 `repos.tar` 约 1.35GB，以及 Docker 镜像归档保留在运行主机，不纳入 Git；依赖目录、镜像、认证环境、原始进程参数也不在此目录。原始封存哈希记录在 `verification.json`，脱敏后的导出内容可能与原件不同，导出哈希以 `checksums.sha256` 为准。

归档文件保留原始字节和行尾；本目录的 `.gitattributes` 防止 Git 改写行尾，并对原始补丁、日志等证据关闭空白风格检查。此设置不影响仓库中的运行器或应用源码检查。
