// Exact test project allowlist. No credential values enter reports or output.
import { execFileSync } from 'node:child_process';
import { fetch, EnvHttpProxyAgent } from 'undici';
import { mkdir, writeFile,access } from 'node:fs/promises';
const account='e5a0857508f37d031d9137c3ecec80e3', project='edgetunnel-test', kv='9bd2a387ba5647acba9a3d27c5327444';
const base=`https://api.cloudflare.com/client/v4/accounts/${account}/pages/projects/${project}`;
const dispatcher=new EnvHttpProxyAgent();
try {
  const mode=process.argv[2]||'inspect';
  if(mode!=='inspect')throw Error('Only read-only inspect is enabled');
  let raw;
  try {raw=execFileSync(process.execPath,['node_modules/wrangler/bin/wrangler.js','auth','token','--json'],{encoding:'utf8',timeout:20000,stdio:['ignore','pipe','pipe'],env:{...process.env,WRANGLER_SEND_METRICS:'false',WRANGLER_LOG:'none'}});}catch{throw Error('Existing CLI authorization unavailable');}
  const auth=JSON.parse(raw.slice(raw.indexOf('{'),raw.lastIndexOf('}')+1));raw=null;
  const r=await fetch(base,{headers:{Authorization:`Bearer ${auth.token}`},dispatcher,signal:AbortSignal.timeout(20000)});
  const j=await r.json();if(!r.ok||!j.success)throw Error('Test project read HTTP '+r.status);
  const p=j.result;
  if(p.name!==project||p.subdomain!=='edgetunnel-test-4pz.pages.dev'||p.deployment_configs?.production?.kv_namespaces?.KV?.namespace_id!==kv)throw Error('Test project ownership/binding mismatch');
  const report={time:new Date().toISOString(),account,project,domains:p.domains,production_branch:p.production_branch,
    deployment:p.canonical_deployment&&{id:p.canonical_deployment.id,url:p.canonical_deployment.url,created_on:p.canonical_deployment.created_on,status:p.canonical_deployment.latest_stage?.status},
    environments:Object.fromEntries(Object.entries(p.deployment_configs||{}).map(([name,c])=>[name,{compatibility_date:c.compatibility_date,compatibility_flags:c.compatibility_flags,kv:c.kv_namespaces,env_var_types:Object.fromEntries(Object.entries(c.env_vars||{}).map(([k,v])=>[k,v.type]))}]))};
  if(report.domains.some(d=>!d.endsWith('.pages.dev')))throw Error('Unexpected custom domain on test project');
  const dr=await fetch(base+'/deployments?per_page=3',{headers:{Authorization:`Bearer ${auth.token}`},dispatcher,signal:AbortSignal.timeout(20000)});
  const dj=await dr.json();
  if(dr.ok&&dj.success)report.latest_deployments=dj.result.map(d=>({id:d.id,created_on:d.created_on,environment:d.environment,stage:d.latest_stage?.name,status:d.latest_stage?.status}));
  await mkdir('diagnostics/subscription',{recursive:true});
  const output='diagnostics/subscription/'+(process.argv[3]==='after'?'after':'before')+'.json';
  let exists=false;try{await access(output);exists=true;}catch{}
  if(!exists||process.argv[3]==='after')await writeFile(output,JSON.stringify(report,null,2));
  console.log(JSON.stringify(report));
}catch(error){console.log(JSON.stringify({error:error.message}));process.exitCode=1;}
finally{await dispatcher.destroy();}
