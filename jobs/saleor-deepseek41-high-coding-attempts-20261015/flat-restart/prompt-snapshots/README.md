# 当次运行的阶段提示词快照

按原始 job / trial / stage 分目录，保存当时的 `role.md`、`instruction.md` 和可用的 `native-evidence.json`。没有用当前模板补造历史提示词。

`role.md` 是运行器保存的阶段职责提示词；原生证据记录具体注入方式（例如 `--append-system-prompt`）。它不包含 CLI 内置 system prompt 或完整供应商请求。

对应关系、原件/导出哈希、会话 ID、原始状态和继承来源见 [manifest.json](manifest.json)。继承的阶段快照仅代表文件保留，不代表本次重新执行；失败尝试也独立列出。

| 原始 job | trial | 阶段快照数 |
| --- | --- | --- |
| [flat-coding-deepseek41-high-restart-20261015-r3](flat-coding-deepseek41-high-restart-20261015-r3/task__G8uLjvp/stages/) | `task__G8uLjvp` | 4 |

关联的现有轨迹：4129 步，3712 步带 sidechain 标记。轨迹字节未改写；标记数量不证明所有子会话均已归档。当前补传只增加阶段提示词与身份凭据，不补造缺失对话。
