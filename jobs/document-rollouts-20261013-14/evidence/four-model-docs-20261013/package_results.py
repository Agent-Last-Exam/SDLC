import hashlib,json,sys,zipfile,csv
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from runtime.request_usage import summarize
OUT=Path(__file__).resolve().parent
PROFILES=json.loads((OUT/'launch-profiles.json').read_text())
def build(only=None):
 rows=[];archive_files=[]
 for profile in PROFILES:
  if only and profile['job_name']!=only:continue
  job=ROOT/'jobs'/profile['job_name']
  continuation=ROOT/'jobs/single-docs-kimi-k3-max-continuation-20261013'
  if profile['model']=='moonshotai/kimi-k3' and list(continuation.glob('*/workflow/state.json')):
   job=continuation
  states=list(job.glob('*/workflow/state.json'))
  if not states:continue
  state=json.loads(states[0].read_text())
  if state['status']=='running':continue
  workflow=states[0].parent;trial=workflow.parent
  name=profile['job_name'].removeprefix('single-docs-').removesuffix('-20261013')
  evidence=workflow/'request-evidence.jsonl'
  records=[json.loads(l) for l in evidence.read_text().splitlines()] if evidence.exists() else []
  original_records=[]
  recovery_source=state.get('recovery_source')
  if recovery_source:
   source=Path(recovery_source);original_evidence=source/'workflow/request-evidence.jsonl'
   original_records=[json.loads(l) for l in original_evidence.read_text().splitlines()]
  usage=summarize(original_records+records)
  compiled=json.loads((Path(profile['recipe']).parent/'resolved-workflow.json').read_text())
  accepted={s['id']:s for s in state['stages'] if s['status']=='accepted'}
  outputs=[]
  for stage in compiled['stages']:
   directory=workflow/'accepted'/stage['stage_id']
   for declared in stage['outputs'].values():
    rel=Path(declared).relative_to(stage['writable_directory']);path=directory/rel
    if not path.is_file():
     for candidate in [workflow/'stages'/stage['stage_id']/'partial-artifacts'/rel,trial/'artifacts/logs/artifacts'/stage['stage_id']/rel]:
      if candidate.is_file() and not candidate.is_symlink():path=candidate;break
    if path.is_file() and not path.is_symlink():
     sha=hashlib.sha256(path.read_bytes()).hexdigest()
     valid=stage['stage_id'] in accepted and accepted[stage['stage_id']]['outputs'].get(str(rel))==sha
     kind='accepted' if valid else 'partial'
     outputs.append({'stage':stage['stage_id'],'file':str(rel),'status':kind,'sha256':sha})
     archive_files.append((path,name+'/'+kind+'/'+stage['stage_id']+'/'+str(rel)))
  events=[json.loads(l) for l in (workflow/'events.jsonl').read_text().splitlines()]
  starts=[r['time'] for r in events if r['event']=='stage_execution_started']
  if recovery_source:
   starts=[json.loads(l)['time'] for l in (Path(recovery_source)/'workflow/events.jsonl').read_text().splitlines() if json.loads(l)['event']=='stage_execution_started']
  elapsed=round(events[-1]['time']-starts[0],2) if starts else None
  req=[r for r in original_records+records if r['kind']=='request']
  profile_ok=bool(req) and all(r['model']==profile['model'] and r['effort']==profile['effort'] and r['cache_breakpoints']>0 and r['thinking']=={'type':'adaptive'} for r in req)
  cli_results=[];native=[]
  for stage in state['stages']:
   stream=workflow/'stages'/stage['id']/'claude-code.jsonl'
   if stream.exists():
    for line in stream.read_text().splitlines():
     try:r=json.loads(line)
     except ValueError:continue
     if r.get('type')=='result':cli_results.append({'stage':stage['id'],'stop_reason':r.get('stop_reason'),'is_error':r.get('is_error'),'terminal_reason':r.get('terminal_reason'),'subagents_spawned':r.get('subagent_stats',{}).get('spawned')})
     if r.get('type')=='system' and r.get('subtype')=='init':native.append({'stage':stage['id'],'model':r.get('model'),'version':r.get('claude_code_version'),'subagent_tool_available':any(t in r.get('tools',[]) for t in ['Agent','Task'])})
  casepath=workflow/'accepted/sprint1/test-design/test-cases.v1.csv'
  casecount=sum(1 for _ in csv.DictReader(casepath.open(newline='',encoding='utf-8'))) if casepath.is_file() else None
  rows.append(dict(recovery_source=recovery_source,test_case_count=casecount,model=profile['model'],effort=profile['effort'],label=name,status=state['status'],error=state.get('error'),accepted_stages=len(accepted),runtime_from_first_stage_execution_sec=elapsed,max_runtime_sec=3600,request_profile_verified=profile_ok,usage=usage,outputs=outputs,native=native,client_results=cli_results))
 return rows,archive_files
if __name__=='__main__':
 only=sys.argv[1] if len(sys.argv)>1 else None
 rows,files=build(only)
 suffix=rows[0]['label'] if only and rows else 'all'
 target=OUT/('results-'+suffix+'.json');target.write_text(json.dumps(rows,ensure_ascii=False,indent=2))
 lines=['# 四模型文档阶段 rollout 记录','', '仅运行 PRD、技术设计、测试用例设计。没有开发、部署或 QA 执行阶段。','', '| 模型 | 档位 | 状态 | 已完成阶段 | 模型执行起累计分钟 | 缓存读取 token | 网关响应报告费用 |','| --- | --- | --- | ---: | ---: | ---: | --- |']
 for r in rows:
  u=r['usage'];cost=u['gateway_reported_cost_usd'];fee='未返回' if cost is None else ('$'+str(cost)+('（部分请求）' if not u['gateway_cost_complete'] else ''))
  minutes=round(r['runtime_from_first_stage_execution_sec']/60,2) if r['runtime_from_first_stage_execution_sec'] is not None else '-'
  lines.append(f"| {r['label']} | {r['effort']} | {r['status']} | {r['accepted_stages']}/3 | {minutes} | {u['cache_read_input_tokens']:,} | {fee} |")
 lines+=['','每模型累计上限 60 分钟；缓存开启且有实际命中证据。流式用量按请求最终快照归并，缓存不重复叠加。','输入优先采用显式原生 billing_usage 的含缓存 prompt_tokens；缺少原生计费字段时，按 Anthropic 输入不含缓存的协议口径归一化。','费用表仅含正式 rollout 请求，短请求预检另计。网关响应费用是 usage.billing_usage.openai_usage.cost 的报告值，不等于后台账单已对账；缺少字段时不估造费用。客户端 total_cost_usd 不作为实际扣费依据。','accepted 表示文件交付被运行器接受，尚未进行独立内容评测。','']
 for r in rows:
  lines+=['## '+r['label'],'', '状态：'+r['status']+'；已完成 '+str(r['accepted_stages'])+'/3 阶段。']
  if r['error']:lines.append('运行器错误：'+r['error'])
  if r['status']=='timed_out':lines.append('累计 60 分钟到点中断，未自动加时或重跑。末条中断请求可能缺少最终 usage，统计仅包含已捕获的报告值。')
  if r.get('recovery_source'):lines.append('原轮因检查器误把自动压缩摘要当成角色激活而中止；修正检查后验证原角色与正常结束记录，恢复原会话只续做测试设计。前两阶段文件未重做，原 60 分钟绝对截止未延长。用量合并原轮和续做请求，每个请求只计一次。')
  if r['label']=='opus55-xhigh' and r['status']=='failed':lines.append('原生客户端最后 stop_reason=error，仅有截断思考内容；客户端 is_error=false / terminal_reason=completed，但 PRD 缺失。错误来自网关还是上游尚未确认。未自动重跑。')
  lines+=['','交付文件数：'+str(len(r['outputs']))+'；详细用量、版本、阶段及哈希见 results.json。','']
 lines+=['验证：88 项运行器/用量测试通过；三阶段容器 smoke 到边界即停；独立超时看门狗实测终止三个阶段身份下的进程。','四模型原生工具循环与缓存预检通过；题目及仓库基线与之前 GPT-6.1 rollout 一致。','请求审计证明发往网关的模型、thinking、effort、缓存标记；不证明网关私有上游路由或各厂商对 effort 的解释。']
 report=OUT/('report-'+suffix+'.md');report.write_text('\n'.join(lines)+'\n')
 archive=OUT/('rollout-documents-'+suffix+'-20261013.zip')
 with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
  for path,name in files:z.write(path,name)
  z.write(report,'report.md');z.write(target,'results.json');z.write(OUT/'launch-profiles.json','launch-profiles.json');z.write(OUT/'validation.json','validation.json')
 print(archive);print(report);print(json.dumps([(r['label'],r['status'],len(r['outputs'])) for r in rows]))
