# 已归档运行的阶段提示词索引

按原始 job 和 trial 查找。相同 rollout 在文档归档和 coding 归档中出现时，源身份保持一致；不同续跑不混为一次运行。

| 原始 job | trial | 归档入口 | 阶段快照数 |
| --- | --- | --- | --- |
| `single-gpt61-xhigh-20261013` | `task__6eAQsS5` | [提示词与来源](single-gpt61-xhigh-20261013/prompt-snapshots/README.md) | 6 |
| `single-docs-gpt61-xhigh-instruction-20261014` | `task__Fq5bK83` | [提示词与来源](single-docs-gpt61-xhigh-instruction-20261014/prompt-snapshots/README.md) | 3 |
| `single-coding-gpt61-xhigh-continuation-20261014` | `task__DuLbKeC` | [提示词与来源](single-coding-gpt61-xhigh-continuation-20261014/prompt-snapshots/README.md) | 4 |
| `single-coding-deepseek41-high-instruction-20261014` | `task__DkkX3ja` | [提示词与来源](single-coding-deepseek41-high-instruction-20261014/prompt-snapshots/README.md) | 3 |
| `single-coding-deepseek41-high-continuation-20261015-r2` | `task__n9Njzk6` | [提示词与来源](saleor-deepseek41-high-coding-attempts-20261015/single-continuation/prompt-snapshots/README.md) | 4 |
| `flat-coding-deepseek41-high-20261014-r2` | `task__B2eCFbL` | [提示词与来源](saleor-deepseek41-high-coding-attempts-20261015/flat-initial/prompt-snapshots/README.md) | 4 |
| `flat-coding-deepseek41-high-restart-20261015-r3` | `task__G8uLjvp` | [提示词与来源](saleor-deepseek41-high-coding-attempts-20261015/flat-restart/prompt-snapshots/README.md) | 4 |
| `flat-coding-deepseek41-high-20261014-r2` | `task__B2eCFbL` | [提示词与来源](saleor-flat-deepseek41-high-docs-20261014/prompt-snapshots/README.md) | 4 |
| `flat-docs-gpt61-xhigh-20261014-r2` | `task__mNZwqCY` | [提示词与来源](saleor-flat-gpt61-xhigh-20261015/prompt-snapshots/README.md) | 2 |
| `flat-qa-gpt61-xhigh-20261015` | `task__EAUAgkr` | [提示词与来源](saleor-flat-gpt61-xhigh-20261015/prompt-snapshots/README.md) | 3 |
| `flat-qa-gpt61-xhigh-20261015-r2` | `task__hQuP84i` | [提示词与来源](saleor-flat-gpt61-xhigh-20261015/prompt-snapshots/README.md) | 3 |
| `flat-coding-gpt61-xhigh-20261015` | `task__LLJigf4` | [提示词与来源](saleor-flat-gpt61-xhigh-20261015/prompt-snapshots/README.md) | 4 |

快照仅包含运行器保存的阶段职责和指令。继承关系、原件与导出 SHA-256、原生会话 ID、已有轨迹覆盖范围分别记录在各归档的 manifest。没有以当前模板重建历史提示词，也没有把未导出的子会话宣称为完整记录。

要在 Harbor Viewer 内直接查看提示词及继承关系，可生成独立展示副本，操作见 [Viewer 展示说明](../docs/rollout-records.md#在-harbor-viewer-中显示已归档的阶段提示词)。现有轨迹文件不改写，补充卡片不冒充原始对话事件。
