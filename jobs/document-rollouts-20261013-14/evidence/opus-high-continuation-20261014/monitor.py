import json,subprocess
from pathlib import Path
jobs=["single-docs-opus55-high-continuation-20261014"]
for name in jobs:
 trial=next(Path("jobs",name).glob("task__*"));p=trial/"workflow/state.json";s=json.loads(p.read_text()) if p.exists() else {}
 row={"job":name,"status":s.get("status"),"stages":[{"id":x["id"],"status":x["status"]} for x in s.get("stages",[])]}
 container=trial.name.lower()+"__env-main-1"
 script="import json,pathlib; p=pathlib.Path('/logs/request-evidence.jsonl'); rs=[json.loads(l) for l in p.read_text().splitlines()] if p.exists() else []; u={}; [u.setdefault(r['id'],{}).update(r['usage']) for r in rs if r.get('kind')=='usage']; print(json.dumps({'requests':sum(r.get('kind')=='request' for r in rs),'cache_read':sum(x.get('cache_read_input_tokens',0) or 0 for x in u.values()),'errors':sum(r.get('kind') in ['upstream_error','relay_error'] for r in rs),'files':[str(x.relative_to('/workspace/artifacts')) for x in pathlib.Path('/workspace/artifacts').rglob('*') if x.is_file()],'last_event':{k:rs[-1].get(k) for k in ['kind','time','stop_reason']} if rs else None}))"
 result=subprocess.run(["docker","exec",container,"python","-c",script],capture_output=True,text=True)
 if result.returncode==0:row.update(json.loads(result.stdout))
 print(json.dumps(row))
