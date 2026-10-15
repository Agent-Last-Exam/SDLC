import json,time,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
status=json.loads((Path(__file__).parent/'supervision-status.json').read_text())
print('supervisor',status['status'],'finished',[(r['job_name'],r['status']) for r in status['results']])
name=status.get('active')
if name:
 job=ROOT/'jobs'/name
 for p in job.glob('*/workflow/state.json'):
  state=json.loads(p.read_text());events=[json.loads(l) for l in (p.parent/'events.jsonl').read_text().splitlines()];starts=[r['time'] for r in events if r['event']=='stage_execution_started']
  print('active',name,'minutes',round((time.time()-starts[0])/60,1) if starts else 'setup','stages',[(s['id'],s['status']) for s in state['stages']])
  container=p.parent.parent.name.lower()+'__env-main-1'
  r=subprocess.run(['docker','exec',container,'find','/workspace/artifacts/sprint1','-type','f','-printf','%P %s bytes\n'],capture_output=True,text=True,timeout=10)
  if r.returncode==0:print(r.stdout.strip())
