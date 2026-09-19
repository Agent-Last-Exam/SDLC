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
| test_workflow_runtime.py | 固定前进、同阶段补交、会话、哈希、blocked、隔离相关结构检查和门禁 |
| test_reporting.py | 报告状态、正式文件哈希、探针区分、异常信息处理和手写报告保护 |

这些测试不调用模型。真实 Docker 隔离与模块上传路径由 `python -m runtime --smoke` 验证，合成业务文件不能充当真实 PRD/TDD。
