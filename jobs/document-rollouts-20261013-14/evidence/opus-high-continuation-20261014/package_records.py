import hashlib,json,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from runtime.environment import load_env
OUT=Path(__file__).resolve().parent
sources=[]
for name in ['single-docs-opus55-high-20261014','single-docs-opus55-high-continuation-20261014']:
 sources.append((ROOT/'jobs'/name,'records/'+name));sources.append((ROOT/'.prepared'/name,'configuration/'+name))
env={};load_env(ROOT/'.env',env);protected=[v.encode() for k,v in env.items() if any(x in k.upper() for x in ['TOKEN','KEY','PASSWORD','AUTH','BASE_URL']) and len(v)>6]
manifest=[];redacted=0
archive=OUT/'opus55-high-complete-records-20261014.zip'
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
 def add(path,name):
  global redacted
  raw=path.read_bytes();data=raw
  for value in protected:data=data.replace(value,b'[REDACTED]')
  changed=raw!=data;redacted+=changed;assert all(v not in data for v in protected)
  z.writestr(name,data);manifest.append({'file':name,'bytes':len(raw),'original_sha256':hashlib.sha256(raw).hexdigest(),'archive_sha256':hashlib.sha256(data).hexdigest(),'redacted':changed})
 for source,prefix in sources:
  for p in sorted(source.rglob('*')):
   name=prefix+'/'+str(p.relative_to(source))
   if p.is_symlink():raise ValueError('Do not archive symlink')
   if p.is_dir():z.writestr(name+'/',b'')
   else:add(p,name)
 for name in ['workflow_agent.py','workflow_controller.py','request_relay.py','request_usage.py','document_budget_continuation.py']:
  add(ROOT/'runtime'/name,'runtime/'+name)
 for pattern in ['results-opus55-high-continuation.json','report-opus55-high-continuation.md','launch-profiles.json','validation.json']:
  add(OUT/pattern,pattern)
 add(ROOT/'.prepared/opus-high-20261014/isolation.json','isolation.json')
 z.writestr('record-manifest.json',json.dumps(manifest,ensure_ascii=False,indent=2))
print(json.dumps({'archive':str(archive),'files':len(manifest),'redacted_files':redacted,'archive_bytes':archive.stat().st_size}))
