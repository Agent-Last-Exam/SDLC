# Saleor Flat：GPT-6.1-Sol / xhigh

PRD → 技术设计 → QA 用例设计 → coding 四阶段已封存，停在 `sprint1/development`。四个独立主会话，阶段内允许子 Agent；未部署或执行独立业务 QA。

- `documents/sprint1/prd/`、`tech-design/`、`test-design/`：正式 PRD、前后端设计、接口协议、GraphQL SDL、OpenAPI/边界 schema 及 440 条 QA 用例。
- `documents/sprint1/development/test-handoff.md`：开发交接报告。
- `code-diffs/`：两个应用仓库的完整补丁，包含新增文件。
- `trajectories/trajectory.atif.json.gz`：完整 ATIF 轨迹，3,698 步，保留 3,262 个 sidechain 标记步骤。

补丁基线：Saleor `c864e66b8e537d30732ddba62d3a4c47e49e4a3e`，Dashboard `aebb2401b5079fbbb8c60150289d1896c108feca`。在对应 baseline checkout 上检查并应用各自补丁。

流程完成不代表业务验收通过。开发报告 D01—D09 保留 P0 缺口、资金/OIDC 回归及 lint/knip 失败；自测集合存在重叠，不累计为一个总通过数。

开发报告内的 validation-evidence 路径指向本地保留的原始自测记录。辅助日志、配置快照、源码清单和完整候选包均留在本地，验证结论见 PR 描述。`.gitattributes` 保留产物和补丁原字节，避免行尾转换。
