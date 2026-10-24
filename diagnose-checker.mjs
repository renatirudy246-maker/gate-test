// Official test-only tail session; credentials and raw events remain in memory.
import { execFileSync } from 'node:child_process';
import { fetch, WebSocket, EnvHttpProxyAgent } from 'undici';
import { mkdir, writeFile } from 'node:fs/promises';
const base = 'https://api.cloudflare.com/client/v4/accounts/e5a0857508f37d031d9137c3ecec80e3/workers/scripts/gate-checker-test';
const dispatcher = new EnvHttpProxyAgent();
let raw;
try { raw = execFileSync(process.execPath, ['node_modules/wrangler/bin/wrangler.js','auth','token','--json'], { timeout:20000,encoding:'utf8', env:{...process.env,WRANGLER_SEND_METRICS:'false',WRANGLER_LOG:'none'},stdio:['ignore','pipe','pipe'] }); }
catch { console.log(JSON.stringify({stage:'cli_authorization',error:'CLI credential read failed or timed out; no credential output retained'}));process.exit(1); }
const auth = JSON.parse(raw.slice(raw.indexOf('{'),raw.lastIndexOf('}')+1));
const response = await fetch(base+'/tails', {method:'POST',headers:{Authorization:`Bearer ${auth.token}`,'Content-Type':'application/json'},body:'{}',dispatcher,signal:AbortSignal.timeout(20000)});
const data = await response.json();
if(!response.ok || !data.success) { console.log(JSON.stringify({stage:'tail_api',http:response.status,errors:data.errors?.map(e=>({code:e.code,message:e.message}))})); process.exit(1); }
const report={tail_api_http:response.status,connected:false,events:[],health:null};
const socket = new WebSocket(data.result.url,{protocols:['trace-v1'],dispatcher,headers:{'User-Agent':'wrangler/4.152.0'}});
await new Promise(resolve=>{
  const timer=setTimeout(()=>{report.connection_error='WebSocket connection/event timeout';resolve();},35000);
  socket.addEventListener('error',e=>{report.connection_error=e.error?.code||e.error?.name||'WebSocket error';clearTimeout(timer);resolve();});
  socket.addEventListener('close',e=>{report.close={code:e.code,reason:e.reason};clearTimeout(timer);resolve();});
  socket.addEventListener('open',async()=>{
    report.connected=true;
    socket.send(JSON.stringify({debug:false}));
    await new Promise(r=>setTimeout(r,1000));
    try{const h=await fetch('https://gate-checker-test.renatirudy246.workers.dev/health',{dispatcher,signal:AbortSignal.timeout(12000)});report.health={http:h.status};await h.text();}catch(e){report.health={error:e.name};}
  });
  socket.addEventListener('message',async e=>{
    try{const text=typeof e.data==='string'?e.data:e.data instanceof ArrayBuffer?Buffer.from(e.data).toString():await e.data.text();const event=JSON.parse(text);report.events.push({keys:Object.keys(event),outcome:event.outcome,exceptions:(event.exceptions||[]).map(x=>({name:x.name,message:x.message,stack:x.stack})),debug:event.type==='exception'?{description:event.description,stack:event.stack}:undefined});clearTimeout(timer);resolve();}catch(error){report.parse_error=error.name;report.message_type=typeof e.data;}
  });
});
socket.close();
await fetch(base+'/tails/'+data.result.id,{method:'DELETE',headers:{Authorization:`Bearer ${auth.token}`},dispatcher,signal:AbortSignal.timeout(10000)}).then(r=>r.text()).catch(()=>{});
await mkdir('diagnostics',{recursive:true});
await writeFile('diagnostics/checker-runtime.json',JSON.stringify(report,null,2));
console.log(JSON.stringify(report));
await dispatcher.destroy();
process.exit(0);
