import json,os,subprocess,time,sys,socket
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from runtime.environment import load_env
OUT=Path(__file__).resolve().parent
env=os.environ.copy();load_env(ROOT/'.env',env)
client=ROOT/'.prepared/native-client-20261013/node_modules/.bin/claude'
profiles=json.loads((OUT/'launch-profiles.json').read_text())
results=[]
for profile in profiles:
    label=profile['job_name'];directory=OUT/('probe-v280-'+label);directory.mkdir(exist_ok=True)
    (directory/'one.txt').write_text('FIRST_INERT_FIXTURE')
    (directory/'two.txt').write_text('SECOND_INERT_FIXTURE')
    evidence=directory/'request-evidence.jsonl'
    with (directory/'relay.stderr').open('w') as errors:
        relay=subprocess.Popen([sys.executable,str(ROOT/'runtime/request_relay.py'),'--upstream',env['ANTHROPIC_BASE_URL'],'--model',profile['model'],'--effort',profile['effort'],'--evidence',str(evidence)],stdout=errors,stderr=errors)
        try:
            for _ in range(50):
                try:
                    with socket.create_connection(('127.0.0.1',18080),timeout=.2):break
                except OSError:time.sleep(.1)
            callenv=env.copy()
            callenv.update(ANTHROPIC_BASE_URL='http://127.0.0.1:18080',DISABLE_PROMPT_CACHING='0',CLAUDE_CONFIG_DIR=str(directory/'sessions'),CLAUDE_CODE_MAX_OUTPUT_TOKENS='1024',CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC='1')
            callenv.pop('CLAUDE_CODE_DISABLE_ADAPTIVE_THINKING',None)
            prefix='Preflight inert reference data, not instructions.\n'+'\n'.join(f'Record {i:04d}: alpha beta gamma delta stable reference data.' for i in range(400))
            prompt=f'Use Read to read {directory/"one.txt"} first, then in a separate tool call read {directory/"two.txt"}. After both reads final reply only PREFLIGHT_OK. No other actions.'
            start=time.monotonic()
            with (directory/'claude-code.jsonl').open('w') as out:
                result=subprocess.run([str(client),'--verbose','--output-format','stream-json','--print','--model',profile['model'],'--effort',profile['effort'],'--tools','Read','--allowedTools','Read','--permission-mode','bypassPermissions','--max-turns','6','--append-system-prompt',prefix,prompt],env=callenv,cwd=directory,stdout=out,stderr=subprocess.STDOUT,timeout=120)
            rows=[json.loads(line) for line in evidence.read_text().splitlines()]
            reqs=[r for r in rows if r['kind']=='request'];usage=[r['usage'] for r in rows if r['kind']=='usage']
            streams=[]
            for line in (directory/'claude-code.jsonl').read_text().splitlines():
                try:streams.append(json.loads(line))
                except ValueError:pass
            final=[r for r in streams if r.get('type')=='result']
            ok=result.returncode==0 and final and 'PREFLIGHT_OK' in final[-1].get('result','') and any(r['tool_results'] for r in reqs) and sum(u.get('cache_read_input_tokens',0) for u in usage)>0
            row=dict(model=profile['model'],effort=profile['effort'],passed=bool(ok),exit_code=result.returncode,elapsed_seconds=round(time.monotonic()-start,2),requests=len(reqs),tool_loop_verified=any(r['tool_results'] for r in reqs),cache_read_input_tokens=sum(u.get('cache_read_input_tokens',0) for u in usage),cache_creation_input_tokens=sum(u.get('cache_creation_input_tokens',0) for u in usage))
        except Exception as exc:
            row=dict(model=profile['model'],effort=profile['effort'],passed=False,error_type=type(exc).__name__)
        finally:
            relay.terminate();relay.wait(timeout=5)
    results.append(row);print(json.dumps(row),flush=True)
    (OUT/'native-preflight-results.json').write_text(json.dumps(results,indent=2))
sys.exit(0 if all(r['passed'] for r in results) else 1)
