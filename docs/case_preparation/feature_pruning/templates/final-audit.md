# 剪枝与标准导出审核

Case/Run：{case_id / run_id}
状态：{incomplete / blocked / staged}
输入与方法：{第一步 manifest、范围政策、E/G/T、工具和被测树身份}

## 1. 产品范围

{主体、逐 R/AC 决定、必要依赖、保护属性、最终活动 PRD 与实现的双向核对。}

## 2. 连续剪枝与实现

{父/子快照、共享能力、migration、接口、生成链、patch 分类、增量和累计重建。}

## 3. 校准与验证

{C/D、候选全集、选择/ID/解析版本、逐 ID 变化、排除/重跑依据、冻结结果和独立守卫。明确额外测试和未选中限制。}

## 4. 标准 exporter 与导出 verifier

{真实 exporter、来源 fingerprint、schema、依赖布局、镜像复用/重建、正式 prepare/applier/runner/grader 的实际检查。}

## 5. 发现

### PF-{编号} · {标题}

- 影响：{需求、阶段、节点、输入或工具身份}
- 是否阻塞与理由：{真实影响}
- 来源证据：{路径、哈希、locator}
- 处理主体和政策：{已明确决定或分析处理}
- 修正与关闭证据：{实际结果}
- 状态：{open / resolved / accepted_limit}

## 6. 归档准备与交接

{第一步与本步的冻结材料、最终包内位置、归档相对引用、父修订、manifest 和第三步活动范围。归档后包级终检写入独立 packaging-audit，不回写冻结报告。}
