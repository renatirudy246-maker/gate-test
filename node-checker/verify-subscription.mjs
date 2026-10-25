// Read-only end-to-end client. Never saves a UUID, cookie, path or subscription.
import {fetch,WebSocket,EnvHttpProxyAgent} from 'undici';
import {Duplex} from 'node:stream';
import tls from 'node:tls';
import {Agent,request} from 'node:https';
import {mkdir,writeFile} from 'node:fs/promises';
import nodes from '../workers/edgetunnel/verified-nodes.json' with {type:'json'};
if(process.env.GITHUB_ACTIONS!=='true'||process.platform!=='linux')throw Error('Only disposable Linux Actions may run this client');
const base='https://edgetunnel-test-4pz.pages.dev',dispatcher=new EnvHttpProxyAgent();
const report={started_at:new Date().toISOString(),max_concurrency:2,backend:'VLESS over certificate-validated WSS -> test Pages -> SSTP -> certificate-validated HTTPS',results:[]};
await mkdir('diagnostics/subscription',{recursive:true});
const save=()=>writeFile('diagnostics/subscription/run.json',JSON.stringify(report,null,2));
async function observe(proxy,observer) {
  const host=observer==='ipwhois'?'ipwho.is':'speed.cloudflare.com',path=observer==='ipwhois'?'/':'/cdn-cgi/trace';
  const started=Date.now();let ws,secure,bridge;const agent=new Agent({keepAlive:false,maxSockets:1});let connections=0;
  const timer=setTimeout(()=>bridge?.destroy(Error('Tunnel observation timeout')),30000);timer.unref();
  agent.createConnection=(_opts,callback)=>{
    if(++connections!==1){callback(Error('Direct or reconnection fallback forbidden'));return;}
    ws=new WebSocket('wss://'+proxy.server+proxy['ws-opts'].path,{dispatcher});ws.binaryType='arraybuffer';
    let prefix=Buffer.alloc(0),headerRead=false;
    bridge=new Duplex({read(){},write(chunk,_encoding,done){try{if(ws.readyState!==ws.OPEN)throw Error('WebSocket not open');ws.send(chunk);done();}catch{done(Error('WebSocket write failed'));}},destroy(error,done){try{ws.close();}catch{}done(error);}});
    bridge.on('error',()=>{});
    ws.addEventListener('message',event=>{
      let data=Buffer.from(event.data);
      if(!headerRead){prefix=Buffer.concat([prefix,data]);if(prefix.length<2||prefix.length<2+prefix[1])return;if(prefix[0]!==0){bridge.destroy(Error('Unexpected VLESS version'));return;}data=prefix.subarray(2+prefix[1]);headerRead=true;}
      if(data.length)bridge.push(data);
    });
    ws.addEventListener('close',()=>bridge.push(null));
    ws.addEventListener('error',()=>bridge.destroy(Error('WebSocket upgrade or stream failed')));
    let called=false;const done=(error,value)=>{if(!called){called=true;callback(error,value);}};
    ws.addEventListener('open',()=>{
      const name=Buffer.from(host),port=Buffer.from([1,187]);
      ws.send(Buffer.concat([Buffer.from([0]),Buffer.from(proxy.uuid.replaceAll('-',''),'hex'),Buffer.from([0,1]),port,Buffer.from([2,name.length]),name]));
      secure=tls.connect({socket:bridge,servername:host,rejectUnauthorized:true,ALPNProtocols:['http/1.1']});
      secure.once('secureConnect',()=>done(secure.authorized?null:Error('Unverified inner TLS'),secure));
      secure.once('error',error=>done(error));
    });
    bridge.once('error',error=>done(error));
  };
  try {
    const body=await new Promise((resolve,reject)=>{
      const req=request({hostname:host,port:443,path,agent,signal:AbortSignal.timeout(35000),headers:{'Accept-Encoding':'identity','User-Agent':'gate-test-private-subscription-verifier/1.0'}},res=>{
        if(res.statusCode!==200||!secure?.authorized){res.resume();reject(Error('Observer HTTP/TLS verification failed'));return;}
        let size=0;const chunks=[];res.on('data',chunk=>{size+=chunk.length;if(size>65536)req.destroy(Error('Observer response exceeds budget'));else chunks.push(chunk);});
        res.on('error',reject);res.on('aborted',()=>reject(Error('Observer aborted')));res.on('end',()=>resolve(Buffer.concat(chunks).toString('utf8')));
      });req.on('error',reject);req.end();
    });
    const value=observer==='ipwhois'?JSON.parse(body):Object.fromEntries(body.trim().split('\n').map(line=>{const i=line.indexOf('=');return [line.slice(0,i),line.slice(i+1)];}));
    return {observer,ip:value.ip,country:observer==='ipwhois'?value.country_code:value.loc,asn:observer==='ipwhois'?value.connection?.asn:undefined,certificate_verified:secure.authorized,elapsed_ms:Date.now()-started};
  }finally{clearTimeout(timer);agent.destroy();secure?.destroy();bridge?.destroy();try{ws?.close();}catch{}}
}
try {
  const health=await fetch(base+'/health',{dispatcher,signal:AbortSignal.timeout(20000),redirect:'error'});report.health={http:health.status,...await health.json()};
  if(health.status!==200||!report.health.configured||report.health.node_count!==35||!report.health.import_configured)throw Error('Test Pages health/configuration failed');
  if(!process.env.TEST_ADMIN)throw Error('Existing test ADMIN secret unavailable');
  const subscription=await fetch(base+'/admin/subscription',{headers:{Authorization:'Bearer '+process.env.TEST_ADMIN},dispatcher,signal:AbortSignal.timeout(20000),redirect:'error'});
  if(subscription.status!==200)throw Error('Authenticated subscription HTTP '+subscription.status);
  const config=await subscription.json(),proxies=config.proxies;
  if(proxies?.length!==35||new Set(proxies.map(p=>p.name)).size!==35||new Set(proxies.map(p=>p['ws-opts'].path)).size!==35||!proxies.every(p=>p.server===new URL(base).hostname&&p.port===443&&p.type==='vless'&&p.network==='ws'&&p.tls===true&&p['skip-cert-verify']===false&&/^\/video\//.test(p['ws-opts'].path)))throw Error('Invalid 35-node test subscription');
  if(['tun','dns','mixed-port','external-controller','redir-port'].some(k=>k in config))throw Error('Unexpected network/listener settings');
  report.subscription={http:subscription.status,validated_proxies:proxies.length,secrets_retained:false};await save();
  const limit=Number(process.env.SUB_TEST_LIMIT||35);if(!Number.isInteger(limit)||limit<1||limit>35)throw Error('Invalid end-to-end budget');
  async function verify(index){const node=nodes[index],result={rank:index+1,host:node.host,port:node.port,expected_ip:node.exit_ip,expected_country:node.country,observations:[]};
    try {for(const observer of ['ipwhois','trace'])result.observations.push(await observe(proxies[index],observer));result.success=result.observations.every(o=>o.certificate_verified&&o.ip===node.exit_ip&&o.country===node.country);if(!result.success)result.error='Observed exit or country differs from measured candidate';}
    catch(error){result.success=false;result.error='End-to-end WSS/SSTP/HTTPS observation failed';result.error_code=/^[A-Z0-9_]+$/.test(error.code||'')?error.code:undefined;}
    report.results[index]=result;await save();console.log(JSON.stringify({rank:index+1,country:node.country,success:result.success,error:result.error}));
  }
  const initial=[0,...(limit>1?[Math.min(limit-1,nodes.findIndex(n=>n.country==='KR'))]:[])];
  await Promise.all(initial.map(verify));
  if(!initial.some(i=>report.results[i]?.success))throw Error('Independent initial exits both failed; remaining end-to-end tests stopped');
  let cursor=0;
  async function worker(){for(;;){const index=cursor++;if(index>=limit)return;if(initial.includes(index))continue;await verify(index);}}
  await Promise.all([worker(),worker()]);report.checked=limit;report.success=report.results.filter(r=>r?.success).length;report.status=report.success===limit?'all_verified':'partial_or_failed';if(!report.success)process.exitCode=1;
}catch(error){report.status='failed';report.error=error.message;process.exitCode=1;}
finally{report.checked=report.results.filter(Boolean).length;report.success=report.results.filter(r=>r?.success).length;report.finished_at=new Date().toISOString();await save();await dispatcher.destroy();}
