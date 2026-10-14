# Saleor 3.23 Golden Pruning Harbor Package Builder

This directory owns the Harbor task definition and package export. It
references published runtime image digests but does not build application
runtime images.

- `package.yaml`, `manifest.json`, and `instruction.md` define the task.
- `env/` contains the existing E inputs and their baseline manifest.
- `patches/` contains the final pruned G and bound T inputs.
- `verifier/` constructs C as `E + T` and D as `E + T + G`, then grades the
  frozen F2P/P2P selection.
- `calibration/source-selection.json` preserves the exact recalibration
  evidence; `calibration/selection.json` is its package-schema projection.
- `calibration/audit-summary.json` records the source reports, patch identity,
  suite counts, reruns, and target-side exclusions.

The official exporter writes the generated `standard/` delivery. Generated
files must not be edited as builder source.

## 业务题目输入

- 根目录 `instruction.md` 是正式业务题目（原 query.md 全文），不再包含旧的迁移执行说明。
- 根目录 `business-conversations.md` 是同一题目的必需补充条件，与主问题一起读取。
- 自定义 workflow 在每个阶段显式声明并复制两份输入，缺失、空白或阶段漏传时拒绝启动；准备产物中的 `input-manifest.json` 保存两份文件的 SHA-256。
- Harbor 原生任务通过 Job 配置 `extra_instruction_paths` 指定补充文件的宿主机路径，将其全文追加到 instruction。仅放置 Markdown 链接不会自动把文件传入环境。workflow 生成的 Job 已配置这一项，且另将两份文件分别复制到 `/workspace/`。
- Golden、评分细则和私有参考不属于 Agent 输入。生成与评测必须使用同一运行冻结的两份题目；后加的题目不追溯适用于旧 rollout。
