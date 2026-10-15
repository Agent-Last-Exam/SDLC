# Rollout 的记录、报告和交付

一个 job 是一次 Harbor 启动；本地默认一个 trial。当前每次运行从新 job 开始，不支持断点续跑。历史记录中曾存在跨 job 续接，阅读这些记录时应保留原始链路。

```text
SDLC-data/
  .prepared/<job>/
    job.json                     # 当时的 Harbor recipe
    resolved-workflow.json       # 当时解析后的模式与输入输出
    input-manifest.json          # 公开输入哈希
    workspace/                   # 当时的角色、模板、Instruction、Base
    task/                        # 为该 job 构建的 Harbor 环境
  jobs/<job>/
    report.md                    # 给人看的运行报告（运行器生成）
    config.json, result.json      # Harbor job 记录
    <trial>/
      result.json, exception.txt # Trial 结果 / 异常（视结果存在）
      workflow/
        state.json, events.jsonl # 主机上的阶段游标、哈希和事件
        stages/<sprint>/<stage>/
          role.md, instruction.md
          codex.jsonl, sessions/, native-evidence.json
          deployment-evidence.json, service-logs/ # 部署或 QA 日志（如有）
        accepted/<sprint>/<stage>/ # 直接收集的文件；以 state 标记封存为准
        baseline.json            # PRD 与测试用例的冻结版本
        candidates/<sprint>/<stage>/ # 开发阶段的源码快照
      agent/                     # 原生日志及标准 ATIF trajectory.json
      artifacts/logs/artifacts/  # 容器回收文件，可能仍含未接受草稿
```

当前不生成 attempts 目录，不保留按提交次数复制的产物。accepted 表示输出已封存，不代表内容验收通过；失败阶段可能留下未封存的部分文件，报告不将其列为正式产物。历史运行中的 attempts 原样保留。Harbor 的 artifacts 回收机制保持不变。

安装检查和角色探针的记录结构较小，不会生成业务 PRD。报告会明确写出类型，不把 smoke fixture 当作业务文档。

## 用 Harbor Viewer 看轨迹

真实运行回收日志后自动生成 `agent/trajectory.json`，包括已执行阶段的角色指令、对话、工具调用与返回结果；失败运行也导出已保存的轨迹。转换复用 Harbor 原生 Codex 转换器，按 `workflow/state.json` 的主会话 ID 选择日志，保留原始 `agent/sessions/`，不把子会话混入主轨迹。合成 smoke 不生成模型轨迹。

```bash
# 仓库根目录：启动本地 Viewer，选择 job、trial 后打开 Trajectory。
harbor view jobs --host 127.0.0.1

# 历史运行离线补导出；不调用模型，不重新执行任务。
python -m runtime.trajectory jobs/single-real-baseline-20260920/task__z8eyG6L
```

上述命令使用安装 Harbor 的同一 Python 环境。导出只新增或更新 `agent/trajectory.json`，不会改写运行状态、基线或业务产物。原始运行若按要求停止，Viewer 中仍显示当时的失败状态。

## 当前运行报告与历史自审文件

`report.md` 由主机运行器读取 state、result 和 accepted 文件生成，记录阶段状态、原生会话、续跑关系、哈希校验和证据链接。不会再调用模型。当前流程交付各轮设计、用例、开发与部署提测报告、源码快照和 QA 报告。读取旧记录时，报告仍可展示历史自审问题。

2026-09-18 旧流程中的 `review.md` 由架构师 Agent 生成，当时属于技术设计交付的一部分；记录设计覆盖、检查范围、问题、pass/blocked 结论。当时是同一个 Agent 自审；这些历史文件与状态保持原样。

旧流程中，结构验收通过与自审 blocked 可以同时成立：文件完整且格式合规，但某些业务决策待确认。Harbor verifier 已禁用，Mean=0 不说明文档质量为零；应读取 workflow/state.json。

## 2026-09-18 旧契约真实 rollout 的链路

1. [workflow-single-20260918-a](../jobs/workflow-single-20260918-a/report.md)：PRD 接受，原生角色切换未生效，技术阶段失败。
2. [role-probe-a](../jobs/workflow-role-probe-20260918-a/report.md) / [role-probe-b](../jobs/workflow-role-probe-20260918-b/report.md)：前者记录另一种失败的切换方式；后者验证同会话的原生 developer 消息注入。
3. [workflow-single-20260918-b](../jobs/workflow-single-20260918-b/report.md)：继承已接受 PRD，续接原生 session，技术设计完整交付，最终自审 blocked。

主原生会话 ID 为 `01a0b2e7-36b8-73d1-b4c4-1c57aa7e2b6a`。最终交付在 b 的 workflow/accepted 下，包括从 a 继承的 PRD。a 的 PM 原始回合证据仍在 a 中。

## 生成或刷新报告

新 workflow 入口在 Harbor 退出或中断后自动写 `report.md`，并更新 jobs/README.md。准备器失败、参数检查失败和 `--prepare-only` 不算 rollout，不创建 job 报告。

```bash
# 无模型，补齐现有所有 job 的报告。
/Users/zhihu/.local/share/uv/tools/harbor/bin/python -m runtime.reporting --all

# 无模型，只刷新一份报告。
/Users/zhihu/.local/share/uv/tools/harbor/bin/python -m runtime.reporting   jobs/workflow-single-20260918-b
```

自动报告开头有生成标记；手写同名文件不会被覆盖。人工解读另存 notes.md。历史 jobs 与冻结 workspace 是证据，不通过重命名或编辑 JSON 来修正过去的失败。

## 失败后的运行

保留失败 job、日志和已接受产物。修正配置或代码后启动新的 job；当前入口不支持跨 job 恢复。旧 recipe 的模块路径和冻结输入保持原样，新运行通过当前入口重新准备。

## 在 Harbor Viewer 中显示已归档的阶段提示词

已归档轨迹的旁置提示词文件不会被 Viewer 自动展示。可从 [提示词快照索引](../jobs/prompt-snapshots.md) 对应的归档生成独立查看副本；在仓库根目录执行：

```bash
python3 -m runtime.viewer_context --jobs jobs --output /tmp/sdlc-context-view
harbor view /tmp/sdlc-context-view --host 127.0.0.1
```

输出目录必须尚不存在，并且位于源 jobs 目录之外。命令校验轨迹和快照哈希后才生成文件；不调用模型、不执行任务，不覆盖历史 `agent/trajectory.json` 或运行结果。只处理带 `prompt-snapshots/manifest.json` 的已归档记录，不会把当前工作区模板当成历史提示词。

在 Viewer 选择 `context--` 开头的归档，进入 Rollouts，打开 `archive-view` 的 Trajectory。开头的 system 卡片明确标为“归档补充上下文 · 非原始对话事件”，显示原始 job/trial、阶段、角色、继承来源、缺失证据、注入方式、保存的提示词及 SHA-256。跨 job 续跑、继承快照和失败尝试分别标明；这些卡片的排列不是消息发送时间线。卡片默认可能折叠，点击步骤编号或卡片可展开提示词全文。随后才显示原始对话与工具调用。

展示副本只顺延对话的展示编号，并在各步 `extra.archive_original_step_id` 保存原编号。原始时间戳、消息、工具返回、sidechain 标记和 token/cost 指标保持不变；补充卡片不计为模型调用。CLI 内置 system prompt、未保存的项目指令和缺失子会话不能从这些快照重建，界面会明确说明边界。

展示配置仅供 Viewer 发现目录，不是历史运行配置；不生成 `result.json`，不伪造成功状态、奖励或成本。Viewer 若将该目录显示为 pending/running，仅表示没有执行结果，不代表新任务在运行。各源 rollout 的身份映射另存于输出根目录的 `context-views.json`。
