# 默认角色 SP

这些是 runtime 交付契约使用的角色 System Prompt。契约用 `defaults:<文件名>` 明确引用
本目录，runtime 不做 task 级静默覆盖。

`pm`、`architect`、`qa-design` 与契约声明的输入绑定：这里的版本读
`/workspace/instruction.md`，对应 `defaults/workflows/lifecycle.yaml`。

仓库清单按两仓（`saleor`、`saleor-dashboard`）措辞，与当前 Saleor 交付契约一致。
