# 机器可读的验收证据

这里的 JSON 是阶段性验收记录。业务 rollout 的逐次状态在 jobs/<job>/<trial>/workflow/state.json，面向阅读的报告在 jobs/<job>/report.md。

验收记录只适用于生成时检查的版本与范围。它们不是单次模型运行的完整清单；包括 DeepSeek 在内的运行报告统一从 [jobs 索引](../../jobs/README.md) 查找。部分历史原始目录本机已不再保留，JSON 中的路径作为历史记录保留。

2026-09-18 目录整理前生成的 verification JSON 原样移动；其相对路径仍以 仓库根目录为基准。读取时应区分准备检查、安装检查、合成联调和真实模型交付。完整导航见 [上级 README](../README.md)。
