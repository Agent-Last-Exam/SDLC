import http.server,json,subprocess,threading,time,urllib.request
from pathlib import Path
class Upstream(http.server.BaseHTTPRequestHandler):
 def do_POST(self):
  self.rfile.read(int(self.headers['Content-Length']));data=b'{"usage":{"input_tokens":1}}'
  self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
 def log_message(self,*args):pass
server=http.server.ThreadingHTTPServer(('127.0.0.1',18081),Upstream);threading.Thread(target=server.serve_forever,daemon=True).start()
processes=[subprocess.Popen(['sleep','30'],user=uid) for uid in (1201,1211,1221)]
relay=subprocess.Popen(['python3','/check/request_relay.py','--upstream','http://127.0.0.1:18081','--model','fixture','--effort','high','--max-runtime-sec','.2','--evidence','/tmp/evidence.jsonl'])
try:
 for _ in range(50):
  try:
   urllib.request.urlopen('http://127.0.0.1:18080/health',timeout=.1);break
  except OSError:time.sleep(.02)
 body=json.dumps(dict(model='fixture',system='inert',messages=[],max_tokens=1)).encode()
 urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:18080/v1/messages',body,{'Content-Type':'application/json'}),timeout=2).read()
 codes=[p.wait(timeout=2) for p in processes]
 assert codes==[-9,-9,-9],codes
 assert 'runtime_deadline_exhausted' in Path('/tmp/evidence.jsonl').read_text()
 print('PASS: independent relay watchdog killed all three stage identities; mock upstream only, no paid calls.')
finally:
 relay.terminate();relay.wait(timeout=2)
 for p in processes:
  if p.poll() is None:p.kill()
