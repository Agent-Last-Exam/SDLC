# Golden 验证摘要

日期：2026-09-27  
范围：剪枝后的 Core/Dashboard target  
结论：配对剪枝 patch 按最终 C/D 口径重新校准并通过冻结测试选择；`saleor-standard-20260927-01` 由官方 exporter 生成，随后补齐 Fabbrica codegen 配置并重算完整性身份，与 Golden target 配对。

当前产品范围：`../PRD/prd-golden.md`。本文件中的 patch、tree 和测试结果是该精简范围的实现证据；旧版 `PRD/prd.md` 仅用于历史需求追踪。

## Golden Patch 身份

| 仓库 | Code patch SHA-256 | Test patch SHA-256 | Combined tree |
| --- | --- | --- | --- |
| Core | `dfcee8e2ef4dd10092efea58b28d26726ae99f8eb5aca0f18a8adb6cb3a8887f` | `1f544aa7a18f316f6e9df997b4da0bd35be24eea4671b025b4368d3fa3599e80` | `0b4ecb1130bcc42aad5facd1657f088ed0d7b7ac` |
| Dashboard | `fa0c4769a01daead3fa4c921a076e39c27ecf431f699f358db1a199fce397abe` | `14488c9b7e8127976f2ab8abfd78543185d2e48979d005965906358db4456bae` | `8e16e2dc3fa083aceef5bc99b46e73be86573dfe` |

## 运行结果

组合口径：Base 为 architecture-upgraded environment 加最终剪枝 test patch；Target 使用同一 test patch 并增加最终剪枝 code patch。

| 集合 | 通过 | 总数 |
| --- | ---: | ---: |
| F2P | 5,365 | 5,365 |
| P2P | 15,013 | 15,013 |
| 合计 | 20,378 | 20,378 |

- Reward：`1`
- Base：P2P `15013/15013`，F2P `0/5365`
- CTRF：passed `20378`，failed/skipped/pending/other 均为 `0`
- Selection SHA-256：`c6652cccc79707f4d744e2e7c0a437902e8b3be25a87efd6157952ac3c4a9e60`
- `reward.json` SHA-256：`9553a43ab4f0ea75bd46b0c6613b103d7651144582bed51e2f1144f8adae0f47`
- CTRF SHA-256：`11b06c48065953d659d641c5eae8e65aecab544e40107ce1caafbf97d5f1d5b4`
- 校准审计 SHA-256：`a83d8babbd410872fac59fbd4eb65486899ad8d49ce1001adb91d4c97248d244`
- 原始校准结果已固化到当前 `evidence/` 目录；运行报告来源路径和 SHA-256 保留在 `calibration-audit.json` 中。

Target Dashboard E2E 原有四个失败项经标准 seed 后隔离复跑，`SALEOR_28`、`SALEOR_76`、`SALEOR_87` 通过并按精确 Playwright identity 合并；`SALEOR_119` 再次因外部 Klaviyo manifest 安装按钮保持 disabled 而超时，保留失败证据且不进入 F2P/P2P。

## 正式 Harbor 配对审计

正式交付目录为 `../..`，即 Git task `tasks/saleor-3.23-pruned/`；release ID 为 `saleor-3.23-pruned-20260927-01`。

- Harbor manifest SHA-256：`af0cc9e1bdabaa629f1c99f9302bb490a57a94ab7a16c8009c04ff0559037dfb`
- Source fingerprint：`caa062ec2fabfcf2ba9978e08f93afaaf2fbdb5ff65c67c40fde94fcf821dfd7`
- Shared payload fingerprint：`b7a65b099cc7e178d5498f1d6216abed47421d9d84f6e2d38d6493fdae107681`
- Environment image：`sdlcbench/saleor-3.23-env:build-0a5d5bc656cb`
- Environment build fingerprint：`0a5d5bc656cb3cb95590de479cc5de02b823db42953a2eda0e05a38395b7da93`
- Harbor selection v2 SHA-256：`1917f52b0d106d712908701e61a4b3d25c9a05da4289f4b278b48bbe95a346df`
- 原始冻结 selection SHA-256：`c6652cccc79707f4d744e2e7c0a437902e8b3be25a87efd6157952ac3c4a9e60`

实际构造 tree：

| 阶段 | Core | Dashboard |
| --- | --- | --- |
| Base / C：environment + test patch | `8238527a020c7105be5a4671315ffab50b6ed025` | `4f2a89c3140dc77ed6fc4741084a424769863c42` |
| Target / D：C + code patch | `0b4ecb1130bcc42aad5facd1657f088ed0d7b7ac` | `8e16e2dc3fa083aceef5bc99b46e73be86573dfe` |

Package 内 grader 使用正式合并报告复核得到 F2P `5365/5365`、P2P `15013/15013`、Base F2P `0/5365`、Base P2P `15013/15013`、reward `1`。Harbor manifest 内 32 个文件哈希全部重算一致；详细机器可读记录见 `harbor-delivery.json`。

2026-09-29 补齐 Dashboard `codegen-main.ts` 中两个 Fabbrica output blocks，共 22 行生成配置。修复后 code/test 与 test/code 两种应用顺序均得到 Dashboard combined tree `8e16e2dc3fa083aceef5bc99b46e73be86573dfe`；使用包内既有依赖执行 main GraphQL Code Generator 成功，六组 outputs 全部生成，运行后无额外文件差异。该修复不修改生成文件、运行时代码、test patch 或冻结选择，因此沿用上述 F2P/P2P 功能验证结果，未重新执行完整测试套件。

## 历史不配对包

`saleor-standard-20260926-01` 中的 patch SHA 为：

| 仓库 | Code patch SHA-256 | Test patch SHA-256 |
| --- | --- | --- |
| Core | `fac345acb493d74f1640bc18e3776bcc1a2f25c879d2a8b1d46d66885b1439e5` | `646b829dd529ec7990ed5f6fa053964d9fa5fe3073e50f5e8042319b24ecc56f` |
| Dashboard | `e02693f6b42f38b19ec122eb95e568e879af6dacb518c811663d3adef6d8f6a5` | `6f729b63db239a024d92cc7401988f7afde497935fa4698b282f69d62dca4d7d` |

这些 SHA 与导入的未剪枝 Candidate 相同，Core code patch 中仍包含 `AppProblem` model、migration 和 GraphQL mutations，冻结选择也仍包含 App Problems 正向用例。因此它不能证明 Golden PRD 中的剪枝目标。

该问题已由 `saleor-standard-20260927-01` 解决。后续再生交付仍必须以本文件第一节的四个 SHA 和 `selection.json` 为输入：Base 应用 environment 与最终 test patch，Target 在相同测试树上增加最终 code patch；不得再使用旧的 `5658/7021`、过渡配置 `5949/14592` 或未剪枝 Candidate 的 `3002/17647`。
