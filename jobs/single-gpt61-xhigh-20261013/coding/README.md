# Coding 评测输入：首轮开发候选

这两份补丁来自已封存的 `sprint1/development/repos.tar`，不是 Oracle 参考答案，也不是后来推测或重新生成的实现。QA 阶段未进行源码修复，因此这就是本轮候选。

| 仓库 | 基线 commit | 补丁 | 改动文件 |
| --- | --- | --- | --- |
| Saleor Core | c864e66b8e537d30732ddba62d3a4c47e49e4a3e | [saleor.model.patch](saleor.model.patch) | 8 |
| Dashboard | aebb2401b5079fbbb8c60150289d1896c108feca | [saleor-dashboard.model.patch](saleor-dashboard.model.patch) | 36 |

补丁是 `git diff --binary --full-index <baseline>`，包含相对基线的完整受版本控制代码变更。候选开发交付声明无 untracked 文件。依赖安装目录、缓存、Git 内部文件、构建产物不属于代码补丁。

## 验证

从冻结快照取出 Git 对象和受版本控制文件，在两个独立本地 checkout 上检出各自基线，先 `git apply --check --index`，再 `git apply --index --binary`。还原后的 Core 4428、Dashboard 3771 个文件逐一对照冻结快照清单，路径、内容 SHA-256、执行位均一致，改动文件集合与开发交付清单一致。补丁保持原始代码字节，未做影响评测的文本脱敏；已检查不包含本机已知模型凭证及常见 token 模式。

`evaluation-input.json` 保存 baseline commit/tree、候选归档摘要、补丁摘要和验证结论；两份 `*.files.json` 保存完整受版本控制候选的内容/模式清单，用于重建核对。Git 内部目录和 ignored 文件不计入这些清单，不能用它们与包含全工作区的原候选 inventory 整体摘要直接比较。

## 接入现有评分器

题包 `tasks/saleor-3.23-pruned` 的 `task.toml` 使用独立 verifier 环境；`tests/prepare.py post` 读取 `/logs/artifacts/saleor.model.patch` 与 `/logs/artifacts/saleor-dashboard.model.patch`。本目录使用同样命名，基线 commit 与该题包的 patch manifest 一致。准备评分时将两份文件放入 verifier 的 `/logs/artifacts/`，沿用题包冻结测试层和原环境；pre 测原始基线，post 测应用候选补丁后的代码。

不能直接对空仓库应用，也不能把 Saleor 的补丁应用到本 SDLC 仓库。若用另一评测 profile，应先确认同样的 baseline commit/tree 和补丁输入约定。本次只准备代码输入，没有启动官方测试或模型。原完整题包的评分 JSON 格式及浏览器 F2P 校准问题仍需按既有报告处理；补丁可重建不表示题包正式校准或代码测试通过。
