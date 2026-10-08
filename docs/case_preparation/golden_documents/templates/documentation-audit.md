# Golden 文档包级审核

Case/Release：{case_id / 新 release_id}
父发布：{输入旧绑定的冻结副本与哈希}
文档状态：{ready / ready_with_limits / blocked / incomplete}
发布状态：{ready / blocked / incomplete}

## 1. 文档与最终实现配对

{活动 PRD、G/T、目标、模板、TDD/Test/完整接口定义及 Golden manifest 身份。}

## 2. 原运行证据与限制

{保留第二条实际验证及 C/D 组合，说明本轮未重新执行的范围，不伪造新功能验证。}

## 3. 三条 workflow 归档

{run/index/manifest、全部副本哈希、来源定位、父修订和可移植引用的实际检查。}

## 4. 完整性与可见性

{runtime/evidence/golden/run/binding 的覆盖范围和无环关系，外部绑定校验；Golden/制作记录不会注入 Agent。}

## 5. 发布与交接

{全部必需检查、文档限制、未决项、后续输入入口，以及是否实际压缩/提交/发布。}
