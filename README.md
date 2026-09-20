# 本机 Harbor：Instruction → PRD → 技术设计

这里用固定版本的 Saleor 源码启动 Codex，按顺序完成 **PM / PRD → 架构师 / 前后端技术设计**。每阶段有明确输入、模板、角色和输出，接受的产物只读，流程在技术设计交付后停止。角色 System Prompt 明确输入、工作、输出路径和交接边界；模板定义字段与格式。

后续的 **QA 测试设计 → 开发 → 部署 → QA 测试执行** 已补齐[角色与交接定义](tasks/saleor-prd-tdd/roles/README.md)及[模板](tasks/saleor-prd-tdd/templates/README.md)，自动执行和 QA 失败后的返工循环尚未接通。

**历史运行结果：** [真实 rollout 报告](jobs/workflow-single-20260918-b/report.md) · [全部运行索引](jobs/README.md) · [正式交付文件](jobs/workflow-single-20260918-b/task__bVyhiV4/workflow/accepted/sprint1/)。

当前流程已取消额外公共交付规范和自审步骤，尚未重跑真实模型。2026-09-18 的旧流程已用本机 Codex 登录完成真实文档交付；自审为 `blocked`，原因是两项产品/迁移信息待确认。首次运行修复角色切换后在同一原生会话续跑，原失败记录保留。完整记录见报告。

## 目录怎么读

| 目录 | 放什么 | 什么时候看 |
| --- | --- | --- |
| [runtime/](runtime/README.md) | 准备器、Controller、Codex 适配、门禁、报告生成 | 修改执行机制 |
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

省略 `--task/--mode` 时默认 Saleor Single；切换模式用 `--mode flat`。具体任务文件见 [Saleor task README](tasks/saleor-prd-tdd/README.md)。

显式读取本机 `~/.codex/auth.json`，模型默认从本机 Codex 配置读取；可用 `--model` 覆盖。凭证经进程环境注入容器，不进入公开准备包或报告。每次分配新 job 名；可用 `--job-name my-design-run` 指定。

```bash
# 无模型：只校验三仓版本和配置。
/Users/zhihu/.local/share/uv/tools/harbor/bin/python -m runtime.prepare_workflow

# 无模型：实际启动容器，验证两个阶段、隔离、交接和报告生成。
/Users/zhihu/.local/share/uv/tools/harbor/bin/python -m runtime --smoke

# 无模型：所有单元测试。
/Users/zhihu/.local/share/uv/tools/harbor/bin/python -m unittest discover -s runtime/tests -t . -v
```

首次在新机器准备时先执行 `python3 -m runtime.prepare_sources`，并在 Harbor Python 环境安装 `requirements.txt`。源码完整 SHA 见 [base-revisions.json](tasks/saleor-prd-tdd/environment/base-revisions.json)。

## 从哪里找产物

每次运行结束自动生成 `jobs/<job>/report.md`。报告链接到：

- `<trial>/workflow/accepted/sprint1/prd/prd.md`：正式 PRD。
- `<trial>/workflow/accepted/sprint1/tech-design/`：前后端技术设计、接口契约、完整 Schema、其他协议文件。
- `<trial>/workflow/state.json` / `events.jsonl`：阶段状态、提交记录、输入输出哈希。
- `<trial>/agent/`：原生会话、Agent 日志与 Harbor trajectory。

**report.md 是运行器生成的运行报告。** 旧运行中的 `review.md` 是当时的自审产物，当前流程不再生成。 `artifacts/` 还可能含未通过门禁的草稿，正式交付以 `workflow/accepted/` 为准。详细路径与失败记录说明见 [rollout-records.md](docs/rollout-records.md)。

## 当前支持范围

| 模式 / Agent | 当前能力 |
| --- | --- |
| Single / Codex | 同一原生主会话，阶段切换角色；旧契约真实文档交付已验证 |
| Flat / Codex | 每阶段新 Agent，仅文件交接；无模型容器联调已验证 |
| Hierarchical | 共用契约已配置；Lead 执行后端尚未实现，启动时明确拒绝 |
| Claude Code | 分阶段 workflow 尚未接入 |

退出码：`0` 文档交付完成，`1` 执行失败（参数错误由 CLI 返回）。设计中的待确认事项保留在对应文档中，不额外生成自审结论或触发业务 blocked。结构验收通过不表示业务正确性已获批准。当前没有开发、QA、部署阶段，没有 Oracle/Noop 或独立语义评分。
