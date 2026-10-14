import json,os,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from runtime.environment import load_env
from runtime.reporting import write_report,write_index
OUT=Path(__file__).resolve().parent
env=os.environ.copy();load_env(ROOT/'.env',env);env['PYTHONPATH']=str(ROOT)
with (OUT/'kimi-continuation.launcher.log').open('w') as log:
 result=subprocess.run(['harbor','run','--config',str(OUT/'kimi-continuation-job.json')],env=env,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
job=ROOT/'jobs/single-docs-kimi-k3-max-continuation-20261013'
write_report(job);write_index(ROOT/'jobs')
print('CONTINUATION_EXIT',result.returncode,flush=True)
