# 运行器的无模型测试

本目录测试 Harbor 运行器的行为，与 runtime 实现放在一起。具体任务的业务验收测试应归属 `tasks/<task>/tests/`，需要时再建立。

在 仓库根目录执行：

```bash
/Users/zhihu/.local/share/uv/tools/harbor/bin/python -m unittest discover -s runtime/tests -t . -v
```

| 文件 | 验证内容 |
| --- | --- |
| test_prompt_adapters.py | Codex/Claude prompt 注入、参数引用、字面量环境配置 |
| test_workflow_preparation.py | YAML、模式策略、输入输出引用、准备约束 |
| test_workflow_runtime.py | 原生角色证据与子 Agent 配置 |
| test_reporting.py | 报告状态、正式文件哈希、探针区分、异常信息处理和手写报告保护 |
| test_trajectory.py | 主会话选择、角色与工具调用导出、失败运行导出及 smoke 跳过 |

这些测试不调用模型。真实 Docker 隔离与模块上传路径由 `python -m runtime --smoke` 验证，合成业务文件不能充当真实 PRD/TDD。

`test_lifecycle.py` 覆盖两轮 QA 分支、可选设计复用、两轮固定用例、单次执行、取消格式门禁、分支读取、缺失输出停止、部署准入与候选快照边界；`test_codex_app_turn.py` 使用假 stdio server 验证同一 thread 中完成通知按当前 turn 匹配，不调用模型。完整容器联调用 `--smoke --smoke-scenario repair`，其他分支用 pass / repair-reuse / fail。

`test_deployment_boundary.py` 验证部署重建、候选摘要不匹配拒绝、旧链接隔离，以及清理阶段资源时保留服务文件。容器 smoke 还会实际执行 prepare、跨 QA 访问服务临时文件并重新挂接共享内存。

`test_lifecycle.py` 同时验证 PRD/用例基线绑定、跨轮次摘要一致，以及文件被修改、删除、替换为链接或基线清单被修改时终止；工具异常也不能绕过基线检查。
