# Tech Owner：部署

将当前 `/workspace/repos/` 的代码部署到本次容器内的隔离测试环境。读取本轮开发提测报告，在指定输出路径交付更新后的提测报告，填写版本、测试入口和验证方式。
源码只读。按 deployment.schema.json 交付 deployment.json，包含 prepare、services 和 healthchecks。

运行器会在你提交后清空 `/workspace/deployment/`，从本轮已接受源码生成 `/workspace/deployment/repos/`，核验源码摘要。不要依赖之前 deployment 中的文件、scratch 或阶段用户的 home。你在阶段内手动准备的部署文件不会进入最终服务。
将安装依赖、构建、配置、数据库初始化和迁移写成 prepare 数组中的 argv/cwd 命令，按顺序执行；不需要准备时填空数组。命令所需的脚本应来自候选源码，或在 argv 中直接声明。命令在全新 deployment 中以服务用户执行，生成的依赖、配置和服务数据保存在该目录中。
services 声明前台运行的服务 argv 和 cwd，依赖的数据库、缓存也需列入。所有 cwd 位于 `/workspace/deployment/` 内。健康地址使用 `http://127.0.0.1:<port>/path`，返回 2xx。所有服务留在本容器，不使用宿主机 Docker socket 或外部部署目标。

运行器在本阶段结束后以独立服务用户执行准备、启动服务并验活，保留服务给 QA；服务自身的临时文件与共享内存跨阶段保留。prepare 命令须自行等待所需依赖；服务启动后健康检查最多等待 60 秒。失败会要求你修正本阶段，下一次部署仍从全新源码副本开始。prepare/service 日志位于 `/workspace/deployment/.runtime-logs/`。报告如实描述已验证和仍待验证的部分。阶段内临时启动的进程会被清理。
