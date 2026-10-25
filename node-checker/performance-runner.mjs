// Outbound benchmarks run ONLY on a disposable Linux Actions machine.
import { createServer } from 'node:http';
import { spawnSync } from 'node:child_process';
import { once } from 'node:events';
import { mkdir, writeFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { build } from 'esbuild';
import tls from 'node:tls';
if (process.env.GITHUB_ACTIONS !== 'true' || process.platform !== 'linux') throw Error('Performance runner is restricted to disposable Linux Actions');
const report = { started_at: new Date().toISOString(), status: 'preflight', purpose: 'availability-and-performance',
  max_candidates: 10, max_concurrency: 2, max_download_payload_bytes: 20*1048576,
  risk_is_hard_gate: false, published: false, results: [], recommendations: [] };
await mkdir('diagnostics/performance', { recursive: true }); await mkdir('dist', { recursive: true });
let writing = Promise.resolve(), server;
const save = () => { const text = JSON.stringify(report, null, 2); writing = writing.then(() => writeFile('diagnostics/performance/run.json', text)); return writing; };
try {
  await build({ entryPoints: ['node-checker/performance-core.mjs'], outfile: 'dist/performance-core.mjs', bundle: true, platform: 'node', format: 'esm', alias: { 'cloudflare:sockets': './node-checker/performance-sockets.mjs' } });
  const { benchmarkNode } = await import('../dist/performance-core.mjs');
  const control = tls.connect({ host: 'ipwho.is', port: 443, servername: 'ipwho.is', rejectUnauthorized: true });
  try { await Promise.race([once(control, 'secureConnect'), new Promise((_, reject) => { const t=setTimeout(()=>reject(Error('TLS readiness timeout')),15000);t.unref(); })]); if (!control.authorized) throw Error('TLS readiness failed'); }
  finally { control.destroy(); }
  // Read-only readiness route. There is no public or local proxy/check endpoint.
  server = createServer((req, res) => { res.writeHead(req.url === '/health' ? 200 : 404, { 'Content-Type':'application/json' }); res.end(JSON.stringify({ service:'gate-performance-checker', configured:true, backend:'isolated-node-sstp', max_candidates:10, max_concurrency:2 })); });
  server.listen(0, '127.0.0.1'); await once(server, 'listening');
  const health = await fetch(`http://127.0.0.1:${server.address().port}/health`);
  report.health = { time:new Date().toISOString(), http:health.status, ...await health.json() };
  await save();
  if (health.status !== 200 || report.health.configured !== true) throw Error('Actual readiness failed; no candidate connections allowed');
  console.log(JSON.stringify({ health:report.health.http, configured:report.health.configured }));
  // A source outage must not block revalidation of previously measured successes.
  const feedUrl = 'https://www.vpngate.net/api/iphone/'; let freshFile;
  try {
    const response = await fetch(feedUrl, { signal:AbortSignal.timeout(15000), redirect:'error' });
    if (!response.ok) throw Error('Official feed HTTP '+response.status);
    const chunks=[]; let length=0;
    for await (const chunk of response.body) { length+=chunk.length; if(length>4*1024*1024) throw Error('Official feed exceeds byte budget'); chunks.push(chunk); }
    const data=Buffer.concat(chunks); freshFile='dist/performance-official.csv'; await writeFile(freshFile,data);
    report.official_feed={url:feedUrl,http:response.status,sha256:createHash('sha256').update(data).digest('hex'),fetched_at:new Date().toISOString()};
  } catch(error) { report.official_feed={url:feedUrl,status:'unavailable',error:error.name}; }
  let selection=spawnSync('python',['performance_candidates.py',...(freshFile?[freshFile]:[])],{encoding:'utf8',timeout:10000});
  if(selection.status!==0 && freshFile) { report.official_feed.parse_status='invalid'; selection=spawnSync('python',['performance_candidates.py'],{encoding:'utf8',timeout:10000}); }
  if(selection.status!==0) throw Error('Historical candidate selection failed');
  const candidates=JSON.parse(selection.stdout);
  if(!Array.isArray(candidates)||!candidates.length||candidates.length>10||new Set(candidates.map(n=>n.host.toLowerCase()+':'+n.port)).size!==candidates.length) throw Error('Invalid candidate budget or duplicates');
  report.selected_candidates=candidates; report.status='running'; await save();
  console.log(JSON.stringify({selected:candidates.length,concurrency:2,official_feed:report.official_feed.status||'available'}));
  let cursor=0;
  async function worker() {
    for(;;) {
      const index=cursor++; if(index>=candidates.length) return;
      report.results[index]=await benchmarkNode(candidates[index]); await save();
      const r=report.results[index]; console.log(JSON.stringify({host:r.host,port:r.port,usable:r.usable,stable:r.short_term_stable,min_mbps:r.min_download_mbps,error:r.error}));
    }
  }
  await Promise.all([worker(),worker()]);
  report.recommendations=report.results.filter(r=>r.usable&&r.short_term_stable).sort((a,b)=>b.min_download_mbps-a.min_download_mbps||a.identity.responseTime-b.identity.responseTime).slice(0,3);
  report.status=report.recommendations.length?'completed_with_candidates':'completed_no_verified_candidates';
  report.checked=candidates.length; report.usable=report.results.filter(r=>r.usable).length;
  report.stable=report.results.filter(r=>r.short_term_stable).length;
  report.fast=report.results.filter(r=>r.short_term_stable&&r.meets_5mbps_target).length;
  report.note='Measurements originate from the Actions runner. Short repetition and small downloads do not establish long-term stability or the user network speed. Historical risk is not a current reputation check.';
  if(!report.recommendations.length) process.exitCode=1;
} catch(error) { report.status='failed'; report.error=error.message; process.exitCode=1; }
finally {
  report.finished_at=new Date().toISOString(); await save();
  if(server) {server.closeAllConnections();await new Promise(resolve=>server.close(resolve));}
}
