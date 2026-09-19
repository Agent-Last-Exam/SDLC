# 目标接口描述交付规范

这是一份说明，不是需要复制到输出目录的接口答案。

Saleor 使用 GraphQL。读取 `/workspace/repos/saleor/saleor/graphql/schema.graphql`，基于 Base 和本次技术设计形成 `/workspace/artifacts/sprint1/tech-design/target-schema.graphql`。

- 输出改动完成后的完整 SDL，保留未变更的 Base 定义；不能只交 diff、片段或省略号。
- 仅采用给定 Base 与自行推导的设计，不检索升级后版本的 schema。
- `interface-contract.md` 的 I 编号对应具体操作/类型/字段，文字语义与 SDL 一致。
- 检查语法、类型引用及前后端消费一致性；记录实际执行的检查和未运行的检查。
- Saleor 本轮业务明确包含接口变更，目标 SDL 为必交。通用任务若无接口变更，可以由任务配置声明不要求，并在后端设计 §2 说明；Agent 不自行删除本轮必交项。
- 若其他边界使用 REST/gRPC，沿用边界现有格式提供完整 OpenAPI/proto，并在接口契约中登记文件；不强制转换为 GraphQL。

这些目标描述保留协议原生格式；PRD、设计与评审等叙述文档统一使用 Markdown。
