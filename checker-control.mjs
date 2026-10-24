// Narrow test-only deployment evidence. Never print/store auth or binding values.
import {execFileSync} from 'node:child_process';
import {fetch,EnvHttpProxyAgent} from 'undici';
import {mkdir,writeFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
const account='e5a0857508f37d031d9137c3ecec80e3', worker='gate-checker-test';
const base=`https://api.cloudflare.com/client/v4/accounts/${account}/workers/scripts/${worker}`;
const dir=process.argv[3]||'diagnostics/before-minimal';
const dispatcher=new EnvHttpProxyAgent();
async function main() {
try {
  if(process.argv[2]==='health') {
    const r=await fetch(`https://${worker}.renatirudy246.workers.dev/health?diagnostic=${Date.now()}`,{dispatcher,signal:AbortSignal.timeout(15000),headers:{'Cache-Control':'no-cache'}});
    const text=await r.text();let body;try{body=JSON.parse(text)}catch{body={cloudflare_error:/1101/.test(text)?1101:null}}
    const result={time:new Date().toISOString(),http:r.status,body,response_metadata:Object.fromEntries(['date','age','server','cf-ray','cf-cache-status','content-type'].map(k=>[k,r.headers.get(k)]))};console.log(JSON.stringify(result));await mkdir('diagnostics',{recursive:true});await writeFile(dir,JSON.stringify(result,null,2));
  } else if(['snapshot','inspect','refresh-subdomain','version-check'].includes(process.argv[2])) {
    let raw;
    try{raw=execFileSync(process.execPath,['node_modules/wrangler/bin/wrangler.js','auth','token','--json'],{encoding:'utf8',timeout:20000,stdio:['ignore','pipe','pipe'],env:{...process.env,WRANGLER_SEND_METRICS:'false',WRANGLER_LOG:'none'}});}catch{throw Error('CLI authorization unavailable')}
    const auth=JSON.parse(raw.slice(raw.indexOf('{'),raw.lastIndexOf('}')+1));
    const headers={Authorization:`Bearer ${auth.token}`};
    if(process.argv[2]==='version-check') {
      const setPreview=async enabled=>{const r=await fetch(base+'/subdomain',{method:'POST',headers:{...headers,'Content-Type':'application/json'},body:JSON.stringify({enabled:true,previews_enabled:enabled}),dispatcher,signal:AbortSignal.timeout(15000)});const j=await r.json();if(!r.ok||!j.success)throw Error('Test version URL toggle failed');};
      const records=[];await setPreview(true);
      try{for(const prefix of ['cc1096d5','89090aeb']){const r=await fetch(`https://${prefix}-${worker}.renatirudy246.workers.dev/health`,{dispatcher,signal:AbortSignal.timeout(15000)});const text=await r.text();let body;try{body=JSON.parse(text)}catch{body={cloudflare_error:/1101/.test(text)?1101:null}}records.push({version_prefix:prefix,http:r.status,body});}}
      finally{await setPreview(false);}
      await writeFile(dir,JSON.stringify(records,null,2));console.log(JSON.stringify(records));return;
    }
    if(process.argv[2]!=='snapshot') {
      const report={account,worker};
      for(const suffix of ['/subdomain','/versions/cc1096d5-0185-487d-bd5f-02a3278172a0']) {
        const r=await fetch(base+suffix,{headers,dispatcher,signal:AbortSignal.timeout(15000)});const j=await r.json();
        report[suffix]={http:r.status,success:j.success,result:suffix==='/subdomain'?j.result:{id:j.result?.id,metadata:j.result?.metadata,resource_keys:Object.keys(j.result?.resources||{}),script:j.result?.resources?.script,bindings:j.result?.resources?.bindings?.map(b=>({name:b.name,type:b.type}))}};
      }
      if(process.argv[2]==='refresh-subdomain') {
        for(const enabled of [false,true]) {
          const r=await fetch(base+'/subdomain',{method:'POST',headers:{...headers,'Content-Type':'application/json'},body:JSON.stringify({enabled,previews_enabled:false}),dispatcher,signal:AbortSignal.timeout(15000)});const j=await r.json();
          report['set_enabled_'+enabled]={http:r.status,success:j.success};if(!r.ok||!j.success)throw Error('Test workers.dev refresh failed');
        }
      }
      await mkdir('diagnostics',{recursive:true});await writeFile(dir,JSON.stringify(report,null,2));console.log(JSON.stringify(report));return;
    }
    await mkdir(dir,{recursive:true});const report={account,worker,time:new Date().toISOString()};
    for(const suffix of ['/deployments','/settings','']){
      const r=await fetch(base+suffix,{headers,dispatcher,signal:AbortSignal.timeout(20000)});
      if(!r.ok)throw Error('Snapshot '+suffix+' HTTP '+r.status);
      if(suffix==='') {
        const text=await r.text();await writeFile(dir+'/deployed-content.txt',text);
        report.content={sha256:createHash('sha256').update(text).digest('hex'),bytes:Buffer.byteLength(text),content_type:r.headers.get('content-type')};
      } else {
        const j=await r.json();if(!j.success)throw Error('Snapshot request failed');
        if(suffix==='/settings')report.settings={compatibility_date:j.result.compatibility_date,compatibility_flags:j.result.compatibility_flags,bindings:j.result.bindings?.map(b=>({name:b.name,type:b.type})),observability:j.result.observability};
        else report.deployments=j.result.deployments?.map(d=>({id:d.id,created_on:d.created_on,source:d.source,versions:d.versions}));
      }
    }
    await writeFile(dir+'/snapshot.json',JSON.stringify(report,null,2));console.log(JSON.stringify(report));
  } else throw Error('Allowed modes: snapshot, health, inspect, refresh-subdomain, version-check');
} catch(e){console.log(JSON.stringify({error:e.message}));process.exitCode=1;}
finally{await dispatcher.destroy();}
}
await main();
