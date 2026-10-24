// Fixed test-only target. No auth values or raw Cloudflare responses are retained.
import { execFileSync } from 'node:child_process';
import { fetch, EnvHttpProxyAgent } from 'undici';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
const account = 'e5a0857508f37d031d9137c3ecec80e3';
const worker = 'gate-checker-probe';
const root = `https://api.cloudflare.com/client/v4/accounts/${account}`;
const dispatcher = new EnvHttpProxyAgent();
const mode = process.argv[2];
const report = { time: new Date().toISOString(), worker, mode };
async function save() {
  await mkdir('diagnostics/probe', { recursive: true });
  await writeFile(`diagnostics/probe/${mode}.json`, JSON.stringify(report, null, 2));
  console.log(JSON.stringify(report, null, 2));
}
try {
  if (!['preflight', 'health', 'snapshot'].includes(mode)) throw Error('Allowed: preflight, health, snapshot');
  if (mode === 'health') {
    const r = await fetch(`https://${worker}.renatirudy246.workers.dev/health?probe=${Date.now()}`, { dispatcher, signal: AbortSignal.timeout(20000), redirect: 'manual', headers: { 'Cache-Control': 'no-cache' } });
    const text = await r.text();
    report.http = r.status; report.ray = r.headers.get('cf-ray'); report.date = r.headers.get('date');
    try { const j = JSON.parse(text); report.body = { service: j.service, stage: j.stage, configured: j.configured }; }
    catch { report.body = { cloudflare_error: /1101/.test(text) ? 1101 : null }; }
  } else {
    let raw;
    try { raw = execFileSync(process.execPath, ['node_modules/wrangler/bin/wrangler.js', 'auth', 'token', '--json'], { encoding: 'utf8', timeout: 20000, stdio: ['ignore', 'pipe', 'pipe'], env: { ...process.env, WRANGLER_SEND_METRICS: 'false', WRANGLER_LOG: 'none' } }); }
    catch { throw Error('Existing CLI authorization unavailable; stop without expanding permissions'); }
    const auth = JSON.parse(raw.slice(raw.indexOf('{'), raw.lastIndexOf('}') + 1));
    const headers = { Authorization: `Bearer ${auth.token}` };
    async function get(path) {
      const r = await fetch(root + path, { headers, dispatcher, signal: AbortSignal.timeout(20000) });
      const j = await r.json();
      if (!r.ok || !j.success) throw Error(`Read ${path} HTTP ${r.status}; codes ${(j.errors || []).map(e => e.code).join(',')}`);
      return j.result;
    }
    const active = await get('/workers/scripts/gate-checker-test/deployments');
    report.original_worker_active = active.deployments?.[0]?.versions;
    if (mode === 'preflight') {
      const prior = await readFile('diagnostics/probe/preflight.json', 'utf8').catch(() => null);
      if (prior) throw Error('Prior probe preflight exists; do not recreate or overwrite its ownership record');
      const scripts = await get('/workers/scripts');
      report.worker_count = scripts.length;
      report.name_available = !scripts.some(s => s.id === worker);
      const subdomain = await get('/workers/subdomain');
      report.subdomain_matches = subdomain.subdomain === 'renatirudy246';
      if (!report.name_available || !report.subdomain_matches || scripts.length >= 100) throw Error('Probe name/account/free Worker-count guard failed; no creation allowed');
      report.allowed_target = { account, worker, config: 'workers/probe/wrangler.jsonc' };
    } else {
      const deployments = await get(`/workers/scripts/${worker}/deployments`);
      report.probe_deployments = deployments.deployments?.map(d => ({ id: d.id, created_on: d.created_on, versions: d.versions }));
      const id = deployments.deployments?.[0]?.versions?.[0]?.version_id;
      if (!id || !/^[a-f0-9-]{36}$/.test(id)) throw Error('Active probe version cannot be confirmed');
      const version = await get(`/workers/scripts/${worker}/versions/${id}`);
      report.probe_version = { id: version.id, runtime: version.resources?.script_runtime, handlers: version.resources?.script?.handlers, bindings: version.resources?.bindings?.map(b => ({ name: b.name, type: b.type })) };
      const subdomain = await get(`/workers/scripts/${worker}/subdomain`);
      report.workers_dev = { enabled: subdomain.enabled, previews_enabled: subdomain.previews_enabled };
    }
  }
} catch (e) { report.error = e.message; process.exitCode = 1; }
finally { await save(); await dispatcher.destroy(); }
