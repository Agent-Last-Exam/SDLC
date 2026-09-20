# 本机 Harbor：Single Agent SDLC

默认 Single 按飞书 workflow 执行 **PRD → 技术设计 → 测试设计 → 开发 → 本地部署 → QA**。首轮 QA 失败后进入修复 Sprint：研判报告，按需更新设计，沿用第一轮测试用例，修复、重新部署、复测；第二轮仍失败则停止并保留报告。详见 [当前流程与实现边界](docs/single-agent-lifecycle.md)。

同一 Codex 原生会话跨阶段延续，developer 消息明确切换职责。各轮文档和代码快照独立保存，部署服务由运行器维持给 QA 使用。当前新增能力经过无模型测试与合成容器联调，尚未运行真实模型的完整 Saleor 交付。

## 目录怎么读

| 目录 | 放什么 | 什么时候看 |
| --- | --- | --- |
| [runtime/](runtime/README.md) | 准备器、Controller、Codex 适配、封存、报告生成 | 修改执行机制 |
| [tasks/](tasks/README.md) | 每个 task 的 Instruction、workflow、roles、templates 和环境 | 修改任务、阶段输入输出和代码版本 |
| [jobs/](jobs/README.md) | 每次 rollout 的 report、状态、轨迹、正式产物 | 看运行结果、定位失败 |
| [reports/](reports/README.md) | 历史验收证据和运行报告导航 | 看已经验证了哪些能力 |
| [docs/](docs/README.md) | 当前设计、运行记录说明、目录迁移说明 | 理解机制和目录关系 |
| [runtime/tests/](runtime/tests/README.md) | 不调用模型的单元测试 | 验证运行器改动 |
| `.prepared/<job>/` | 启动时冻结的公开输入、哈希清单和 Harbor recipe | 追溯某次实际使用的配置 |

`.env` 只存本机配置，忽略提交；[requirements.txt](requirements.txt) 是额外 Python 依赖。`jobs/` 和 `.prepared/` 是本地产生的数据，不移动或手工改写历史记录。

## 启动一次真实 Single rollout

以下命令在 **仓库根目录**执行。使用已安装的 Harbor Python，Docker Desktop 和 `harbor` 需可用；本机已经准备好源码与依赖。

```bash
/Users/zhihu/.local/share/uv/tools/harbor/bin/python -m runtime --task tasks/saleor-prd-tdd --mode single --use-local-codex-auth
```

省略 `--task/--mode` 时默认 Saleor Single 完整流程；Flat / Hierarchical 仅有新契约的声明配置，启动器拒绝执行。具体任务文件见 [Saleor task README](tasks/saleor-prd-tdd/README.md)。

显式读取本机 `~/.codex/auth.json`，模型默认从本机 Codex 配置读取；可用 `--model` 覆盖。凭证经进程环境注入容器，不进入公开准备包或报告。每次分配新 job 名；可用 `--job-name my-sdlc-run` 指定。

```bash
# 无模型：只校验三仓版本和配置。
/Users/zhihu/.local/share/uv/tools/harbor/bin/python -m runtime.prepare_workflow

# 无模型：实际启动容器，验证完整修复链、隔离、服务保留和报告生成。
/Users/zhihu/.local/share/uv/tools/harbor/bin/python -m runtime --smoke

# 无模型：所有单元测试。
/Users/zhihu/.local/share/uv/tools/harbor/bin/python -m unittest discover -s runtime/tests -t . -v
```

首次在新机器准备时先执行 `python3 -m runtime.prepare_sources`，并在 Harbor Python 环境安装 `requirements.txt`。源码完整 SHA 见 [base-revisions.json](tasks/saleor-prd-tdd/environment/base-revisions.json)。

## 从哪里找产物

每次运行结束自动生成 `jobs/<job>/report.md`。报告链接到：

- `<trial>/workflow/accepted/sprint1/prd/prd.md`：正式 PRD。
- `<trial>/workflow/accepted/sprint1/tech-design/`：前后端技术设计、接口契约、完整 Schema、其他协议文件。
- `<trial>/workflow/accepted/sprintN/`：各轮测试用例、开发/部署提测报告及 QA 结果。
- `<trial>/workflow/candidates/sprintN/development/`：多仓代码归档和摘要清单。
- `<trial>/workflow/state.json` / `events.jsonl`：阶段状态、提交记录、输入输出哈希。
- `<trial>/agent/`：原生会话、Agent 日志与 Harbor trajectory。

**report.md 是运行器生成的运行报告。** 旧运行中的 `review.md` 是当时的自审产物，当前流程不再生成。 `artifacts/` 是 Harbor 回收副本；正式产物以 `workflow/state.json` 标记封存的 `workflow/accepted/` 文件为准。封存不代表内容验收。详细路径与失败记录说明见 [rollout-records.md](docs/rollout-records.md)。

## 当前支持范围

| 模式 / Agent | 当前能力 |
| --- | --- |
| Single / Codex | 同一原生主会话；六阶段首轮和有界修复 Sprint；无模型联调已验证 |
| Flat / Codex | 共用 lifecycle 契约；执行后端尚未实现，启动时明确拒绝 |
| Hierarchical | 共用契约已配置；Lead 执行后端尚未实现，启动时明确拒绝 |
| Claude Code | 分阶段 workflow 尚未接入 |

退出码：`0` 交付完成，`1` 执行失败或第二轮 QA 未通过。文件封存不等于业务批准；未启用独立业务 verifier。当前不支持断点续跑；失败后保留记录并新建运行。
