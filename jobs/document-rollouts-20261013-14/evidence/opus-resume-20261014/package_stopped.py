import hashlib,json,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from runtime.environment import load_env
from runtime.request_usage import summarize
OUT=Path(__file__).resolve().parent
names=['single-docs-opus55-xhigh-retry-20261014','single-docs-opus55-xhigh-resume-20261014'];records=[];parts=[];sources=[]
for name in names:
 job=ROOT/'jobs'/name;sources.append((job,'records/'+name))
 trial=next(job.glob('task__*'));workflow=trial/'workflow'
 rows=[json.loads(l) for l in (workflow/'request-evidence.jsonl').read_text().splitlines()];records+=rows
 events=[json.loads(l) for l in (workflow/'events.jsonl').read_text().splitlines()]
 start=next(e['time'] for e in events if e['event']=='stage_execution_started')
 parts.append({'job_name':name,'captured_execution_interval_sec':round(events[-1]['time']-start,2),'usage':summarize(rows),'raw_state_status':json.loads((workflow/'state.json').read_text())['status']})
usage=summarize(records)
result={'status':'user_stopped','model':'anthropic/claude-opus-5.5','effort':'xhigh','thinking':{'type':'adaptive'},'principal_session':'5dbaeee0-a251-4942-bd3b-23aa420ddc5d','completed_stages':0,'formal_documents':0,'parts':parts,'usage':usage,'notes':['人工中断以取消限时后，原会话续做；此轮受干预。','最后由用户要求停止；原始运行器 failed/exit143 记录保留，表示客户端中断，不冒充正常完成。','token 使用按每请求最后已捕获快照合并；两次中断请求可能缺少最终 usage 或费用。','缓存包含在输入总量中，不重复加总。','网关响应报告费用不是后台账单对账值。']}
(OUT/'stopped-results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
u=usage
report=f'''# Opus 5.5 / xhigh：用户停止记录

本轮已按用户要求停止。仍在 PRD 阶段，完成 0/3 阶段，正式交付文件 0 份；没有技术设计、测试设计或开发阶段。已有完整会话、工具结果、轨迹、请求审计、阶段角色与配置、原始异常及停止标记均保留。

- 含缓存输入：{u['input_tokens_including_cache']:,} token
- 输出：{u['output_tokens']:,} token
- 输入＋输出：{u['input_tokens_including_cache']+u['output_tokens']:,} token
- 缓存读取：{u['cache_read_input_tokens']:,} token（已包含在输入中）
- 缓存写入：{u['cache_creation_input_tokens']:,} token（已包含在输入中）
- 请求：{u['requests']} 次；有 usage 快照：{u['requests_with_usage']} 次
- 网关响应报告费用：${u['gateway_reported_cost_usd']}，仅 {u['requests_with_gateway_cost']}/{u['requests']} 次请求提供费用，尚未与后台账单对账。

统计合并本次 xhigh 重跑中断前与同会话续做两段；不含 2026-10-13 的早先失败轮或预检。流式 usage 按请求最终已捕获快照去重。最后两次中断请求可能缺少最终 usage，不能把本表当作完整后台扣费。

本轮曾人工中断客户端并追加恢复指令取消一小时限制，因此不能作为未受干预的连续 rollout。最终再次中断来自用户停止指示；原始 failed/exit143 记录保持不变。与全新 high 轮的会话、容器、日志及产物隔离。

完整记录包中的文本按凭据与私有配置值进行脱敏；原文件原样保留在本机。文件清单包含原始哈希与附件版本哈希。没有独立内容评测。
'''
(OUT/'stopped-report.md').write_text(report)
sources += [(ROOT/'.prepared/single-docs-opus55-xhigh-retry-20261014','configuration/original'),(ROOT/'.prepared/single-docs-opus55-xhigh-resume-20261014','configuration/resume'),(OUT/'user-stop-scratch','scratch/final'),(ROOT/'.prepared/opus-retry-20261014/checkpoint-scratch','scratch/first-interruption')]
env={};load_env(ROOT/'.env',env);protected=[v.encode() for k,v in env.items() if any(t in k.upper() for t in ['TOKEN','KEY','PASSWORD','AUTH','BASE_URL']) and len(v)>6]
manifest=[];redacted=0
archive=OUT/'opus55-xhigh-stopped-records-20261014.zip'
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
 for source,prefix in sources:
  if not source.exists():continue
  for p in sorted(source.rglob('*')):
   name=prefix+'/'+str(p.relative_to(source))
   if p.is_symlink():raise ValueError('Do not archive symlink')
   if p.is_dir():z.writestr(name+'/',b'');continue
   raw=p.read_bytes();data=raw
   for value in protected:data=data.replace(value,b'[REDACTED]')
   changed=raw!=data;redacted+=changed
   assert all(v not in data for v in protected)
   z.writestr(name,data)
   manifest.append({'file':name,'bytes':len(raw),'original_sha256':hashlib.sha256(raw).hexdigest(),'archive_sha256':hashlib.sha256(data).hexdigest(),'redacted':changed})
 for p in [OUT/'stopped-results.json',OUT/'stopped-report.md']:
  data=p.read_bytes();assert all(v not in data for v in protected);z.writestr(p.name,data)
 z.writestr('record-manifest.json',json.dumps(manifest,ensure_ascii=False,indent=2))
print(json.dumps({'archive':str(archive),'files':len(manifest),'redacted_files':redacted,'archive_bytes':archive.stat().st_size,'usage':usage},indent=2))
