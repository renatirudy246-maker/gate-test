import test from 'node:test';
import assert from 'node:assert/strict';
import { build } from 'esbuild';
const built = await build({ entryPoints:['node-checker/performance-core.mjs'],bundle:true,write:false,platform:'node',format:'esm',alias:{'cloudflare:sockets':'./node-checker/performance-sockets.mjs'} });
const { throughputMbps, parseTrace, summarizePerformance, DOWNLOAD_BYTES } = await import('data:text/javascript;base64,'+Buffer.from(built.outputFiles[0].text).toString('base64'));
function fixture() {
  const ip='1.1.1.1'; // Unit fixture, not a measured VPN exit.
  return { identity:{success:true,evidence:'SSTP tunnel to two certificate-validated independent HTTPS exit services',exit:{ip,country_code:'JP'},observations:['ipwhois','ipify','ipify'].map(observer=>({observer,ip,certificate_verified:true}))},
    downloads:[10,12].map(mbps=>({mbps,bytes:DOWNLOAD_BYTES,exit_ip:ip,country_code:'JP',certificate_verified:true,same_tls_connection:true})),
    final_exit:{ip,certificate_verified:true},elapsed_ms:30000,historical_risk_score:100 };
}
test('throughput uses actual completed bytes and elapsed time',()=>{
  assert.equal(throughputMbps(1048576,1000),8.388608);
  for(const [bytes,time] of [[1024,1000],[1048576,0],[1048576,NaN]]) assert.throws(()=>throughputMbps(bytes,time));
});
test('performance admission permits high historical risk but requires verified stable transport',()=>{
  const result=summarizePerformance(fixture());
  assert.equal(result.usable,true);assert.equal(result.short_term_stable,true);assert.equal(result.meets_5mbps_target,true);
  assert.equal(result.long_term_stability,'unknown');
});
test('partial download, direct fallback, missing certificate or changed exit cannot be ranked',()=>{
  for(const change of [{bytes:1024},{same_tls_connection:false},{certificate_verified:false},{exit_ip:'8.8.8.8'},{country_code:'DE'}]) {
    const r=fixture();Object.assign(r.downloads[0],change);assert.equal(summarizePerformance(r).usable,false);
  }
  const r=fixture();r.identity.observations[0].certificate_verified=false;assert.equal(summarizePerformance(r).usable,false);
});
test('large throughput variation or short samples are not called stable',()=>{
  const r=fixture();r.downloads[0].mbps=1;assert.equal(summarizePerformance(r).short_term_stable,false);
  r.downloads[0].mbps=10;r.elapsed_ms=1000;assert.equal(summarizePerformance(r).short_term_stable,false);
});
test('trace requires an exit address and country',()=>{
  assert.deepEqual(parseTrace('ip=1.1.1.1\nloc=JP\ncolo=NRT\n'),{ip:'1.1.1.1',country_code:'JP',colo:'NRT'});
  assert.throws(()=>parseTrace('loc=JP\n'));
});
