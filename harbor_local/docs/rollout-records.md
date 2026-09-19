# Rollout 的记录、报告和交付

一个 job 是一次 Harbor 启动；本地默认一个 trial。一个逻辑 workflow 可跨失败续跑的多个 job，所以既保留 a 的失败，也保留 b 的续接，不能仅把最终 job 当作一次从头无错误运行。

```text
harbor_local/
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
        attempts/<sprint>/<stage>/<attempt>/
          role.md, instruction.md
          codex.jsonl, sessions/, native-evidence.json
          outputs/               # 该次提交的快照，可能被拒绝
        accepted/<sprint>/<stage>/ # 已接受的正式文件
      agent/                     # 原生日志和 Harbor trajectory
      artifacts/logs/artifacts/  # 容器回收文件，可能仍含未接受草稿
```

安装检查和角色探针的记录结构较小，不会生成业务 PRD。报告会明确写出类型，不把 smoke fixture 当作业务文档。

## report.md 与 review.md

`report.md` 由主机运行器读取 state、result 和 accepted 文件生成，记录阶段状态、原生会话、续跑关系、哈希校验和证据链接。不会再调用模型。它引用 Agent 自审的问题表，不增加独立语义评价。

`review.md` 由架构师 Agent 生成，是技术设计交付的一部分；记录设计覆盖、检查范围、问题、pass/blocked 结论。本次是同一个 Agent 自审。

结构验收通过与自审 blocked 可以同时成立：文件完整且格式合规，但某些业务决策待确认。Harbor verifier 已禁用，Mean=0 不说明文档质量为零；应读取 workflow/state.json。

## 本次真实 rollout 的链路

1. [workflow-single-20260918-a](../jobs/workflow-single-20260918-a/report.md)：PRD 接受，原生角色切换未生效，技术阶段失败。
2. [role-probe-a](../jobs/workflow-role-probe-20260918-a/report.md) / [role-probe-b](../jobs/workflow-role-probe-20260918-b/report.md)：前者记录另一种失败的切换方式；后者验证同会话的原生 developer 消息注入。
3. [workflow-single-20260918-b](../jobs/workflow-single-20260918-b/report.md)：继承已接受 PRD，续接原生 session，技术设计完整交付，最终自审 blocked。

主原生会话 ID 为 `01a0b2e7-36b8-73d1-b4c4-1c57aa7e2b6a`。最终交付在 b 的 workflow/accepted 下，包括从 a 继承的 PRD。a 的 PM 原始回合证据仍在 a 中。

## 生成或刷新报告

新 workflow 入口在 Harbor 退出或中断后自动写 `report.md`，并更新 jobs/README.md。准备器失败、参数检查失败和 `--prepare-only` 不算 rollout，不创建 job 报告。

```bash
# 无模型，补齐现有所有 job 的报告。
/Users/zhihu/.local/share/uv/tools/harbor/bin/python -m harbor_local.runtime.reporting --all

# 无模型，只刷新一份报告。
/Users/zhihu/.local/share/uv/tools/harbor/bin/python -m harbor_local.runtime.reporting   harbor_local/jobs/workflow-single-20260918-b
```

自动报告开头有生成标记；手写同名文件不会被覆盖。人工解读另存 notes.md。历史 jobs 与冻结 workspace 是证据，不通过重命名或编辑 JSON 来修正过去的失败。

## 继续一个失败任务

```bash
/Users/zhihu/.local/share/uv/tools/harbor/bin/python -m harbor_local   --use-local-codex-auth --continue-from harbor_local/jobs/<failed-job>/<trial>
```

仅支持已经接受 PRD 后的失败/中断记录，并核对全部公开输入与接受文件哈希。业务自审 blocked 不能用此入口绕过；源输入变化时新建 run。旧历史 recipe 中的模块路径保留原样；新运行请用新入口生成 recipe。
