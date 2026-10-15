import json,os,signal,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from runtime.environment import load_env
from runtime.reporting import write_report,write_index
OUT=Path(__file__).resolve().parent
env=os.environ.copy();load_env(ROOT/'.env',env);env['PYTHONPATH']=str(ROOT)
profiles=json.loads((OUT/'launch-profiles.json').read_text())
assert all(p['passed'] for p in json.loads((OUT/'native-preflight-results.json').read_text()))
smoke=json.loads(next((ROOT/'jobs/docs-boundary-smoke-v2-20261013').glob('*/workflow/state.json')).read_text())
assert smoke['status']=='stopped_at_boundary' and len(smoke['stages'])==3
results=[]
status={'status':'running','results':results,'active':None}
def save():
 tmp=OUT/'supervision-status.tmp';tmp.write_text(json.dumps(status,indent=2));tmp.replace(OUT/'supervision-status.json')
for profile in profiles:
 name=profile['job_name'];job=ROOT/'jobs'/name
 assert not job.exists(),f'Refuse replay: {name}'
 recipe=json.loads(Path(profile['recipe']).read_text());kw=recipe['agents'][0]['kwargs']
 config=json.loads((Path(kw['prepared_path'])/'resolved-workflow.json').read_text())
 assert [s['role'] for s in config['stages']]==['pm','architect','qa-design']
 assert kw['request_profile'] and kw['max_runtime_sec']==3600 and kw['client_version']=='2.1.280'
 assert kw['reasoning_effort']==profile['effort'] and not config['run']['execution']['subagents']['enabled']
 status['active']=name;save();print('START '+name,flush=True)
 start=time.time()
 with (OUT/(name+'.launcher.log')).open('w') as log:
  child=subprocess.Popen(['harbor','run','--config',profile['recipe']],env=env,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
  while child.poll() is None:
   states=list(job.glob('*/workflow/state.json'))
   if states:
    try:
     state=json.loads(states[0].read_text())
     status['active_state']={'status':state['status'],'stages':[{'id':s['id'],'status':s['status']} for s in state['stages']]}
     if any(s['role'] not in ['pm','architect','qa-design'] for s in state['stages']):
      os.killpg(child.pid,signal.SIGTERM);status['status']='guard_failed';save();raise RuntimeError('Unexpected code stage')
    except (ValueError,KeyError):pass
   save();time.sleep(5)
 states=list(job.glob('*/workflow/state.json'));state=json.loads(states[0].read_text()) if states else {}
 row={'job_name':name,'model':profile['model'],'effort':profile['effort'],'exit_code':child.returncode,'elapsed_including_setup_sec':round(time.time()-start,2),'status':state.get('status','failed'),'stages':state.get('stages',[])}
 evidences=list(job.glob('*/workflow/request-evidence.jsonl'))
 rows=[json.loads(l) for l in evidences[0].read_text().splitlines()] if evidences else []
 requests=[r for r in rows if r['kind']=='request'];usages=[r['usage'] for r in rows if r['kind']=='usage']
 row['audited_requests']=len(requests);row['request_profile_verified']=bool(requests) and all(r['model']==profile['model'] and r['effort']==profile['effort'] and r['cache_breakpoints']>0 for r in requests)
 row['cache_read_input_tokens']=sum(u.get('cache_read_input_tokens',0) for u in usages)
 row['cache_creation_input_tokens']=sum(u.get('cache_creation_input_tokens',0) for u in usages)
 # SSE message-start and message-delta usage have separate semantics. Keep
 # original usage evidence rather than presenting a naive output sum.
 results.append(row);status.pop('active_state',None);save()
 try:write_report(job);write_index(ROOT/'jobs')
 except Exception as exc:row['report_error_type']=type(exc).__name__
 print('FINISH '+json.dumps({k:v for k,v in row.items() if k!='stages'}),flush=True)
 if requests and not row['request_profile_verified']:
  status['status']='guard_failed';save();raise RuntimeError('Request profile mismatch')
status['status']='finished';status['active']=None;save();print('ALL_FINISHED',flush=True)
