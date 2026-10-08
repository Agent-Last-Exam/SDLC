# 最终 Harbor 包级审核

Case/Release：{case_id / release_id}
状态：{ready / blocked / incomplete}
包根：{实际位置；引用使用包内相对路径}

## 1. 运行包与身份

{exporter/version/schema、runtime manifest SHA、E/G/T、B/C/D、镜像、实际 verifier 结果。}

## 2. 最终活动范围

{prd-golden.md、scope-decisions、目标和测试的配对与指纹。历史未剪枝 PRD 只作证据。}

## 3. 两条 workflow 归档

{所有 run_id、阶段范围、包内索引、run manifest、逐文件哈希、引用/父修订可移植性、archive_status。}

## 4. 可见性与清单覆盖

{Agent/Verifier 准备的实际文件与路径；Golden、参考生产实现、隐藏测试和制作记录不会进入 Agent 输入。root/evidence/binding 各自管理范围、外部绑定校验和无环关系。}

## 5. 结论、限制与交接

{必需检查结果、剩余阻塞、非选中排除、外部限制、第三步按发布绑定可定位的输入；声明是否实际生成归档/提交/发布。}
