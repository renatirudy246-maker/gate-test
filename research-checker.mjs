// Read-only evidence collection. Fixed test targets; no resource mutation APIs.
// Credentials stay in memory. Only explicitly selected metadata is retained.
import { execFileSync } from 'node:child_process';
import { fetch, EnvHttpProxyAgent } from 'undici';
import { mkdir, writeFile } from 'node:fs/promises';
const account = 'e5a0857508f37d031d9137c3ecec80e3';
const worker = 'gate-checker-test';
const api = 'https://api.cloudflare.com/client/v4';
const dispatcher = new EnvHttpProxyAgent();
const report = { time: new Date().toISOString(), worker, evidence: {} };
const bindings = list => list?.map(b => ({ name: b.name, type: b.type }));
let headers;
async function read(path, select) {
  const r = await fetch(api + path, { headers, dispatcher, signal: AbortSignal.timeout(20000) });
  const j = await r.json();
  const safe = { http: r.status, success: j.success, errors: j.errors?.map(e => ({ code: e.code, message: e.message })) };
  if (r.ok && j.success) safe.result = select(j.result);
  report.evidence[path.replace(`/accounts/${account}`, '')] = safe;
  return r.ok && j.success ? j.result : null;
}
try {
  let raw;
  try { raw = execFileSync(process.execPath, ['node_modules/wrangler/bin/wrangler.js', 'auth', 'token', '--json'], { encoding: 'utf8', timeout: 20000, stdio: ['ignore', 'pipe', 'pipe'], env: { ...process.env, WRANGLER_SEND_METRICS: 'false', WRANGLER_LOG: 'none' } }); }
  catch { throw Error('Existing CLI authorization unavailable; no credentials retained'); }
  const auth = JSON.parse(raw.slice(raw.indexOf('{'), raw.lastIndexOf('}') + 1));
  headers = { Authorization: `Bearer ${auth.token}` };
  const prefix = `/accounts/${account}`;
  const script = prefix + `/workers/scripts/${worker}`;
  if (process.argv[2] === 'telemetry') {
    const request = { queryId: 'gate-test-readonly-diagnosis', dry: true, view: 'events', limit: 20,
      timeframe: { from: Date.parse('2026-10-24T21:27:00Z'), to: Date.parse('2026-10-24T21:31:00Z') },
      parameters: { filters: [{ key: '$workers.scriptName', operation: 'eq', type: 'string', value: worker }], needle: { value: 'a4fc1326bfed58bf', isRegex: false, matchCase: false } } };
    const r = await fetch(api + prefix + '/workers/observability/telemetry/query', { method: 'POST', headers: { ...headers, 'Content-Type': 'application/json' }, body: JSON.stringify(request), dispatcher, signal: AbortSignal.timeout(20000) });
    const j = await r.json();
    report.evidence.telemetry = { http: r.status, success: j.success, errors: j.errors?.map(e => ({ code: e.code, message: e.message })), event_count: j.result?.events?.events?.length, result_keys: j.success ? Object.keys(j.result || {}) : undefined,
      // Deliberately never retain raw events, headers, logs or request bodies.
      events: j.result?.events?.events?.map(e => ({ timestamp: e.timestamp, worker: e.$workers?.scriptName, outcome: e.$workers?.outcome, request_id: e.$workers?.requestId, version: e.$workers?.scriptVersion?.id })) };
    const g = await fetch(api + '/graphql', { method: 'POST', headers: { ...headers, 'Content-Type': 'application/json' }, body: JSON.stringify({ query: 'query($account: string, $start: Time, $end: Time, $script: string) { viewer { accounts(filter:{accountTag:$account}) { workersInvocationsAdaptive(limit:100,filter:{scriptName:$script,datetime_geq:$start,datetime_leq:$end}) { dimensions { datetime scriptName status } sum { requests errors } } } } }', variables: { account, script: worker, start: '2026-10-24T21:00:00Z', end: new Date().toISOString() } }), dispatcher, signal: AbortSignal.timeout(20000) });
    const gj = await g.json();
    report.evidence.analytics = { http: g.status, errors: gj.errors?.map(e => ({ message: e.message })), rows: gj.data?.viewer?.accounts?.flatMap(a => a.workersInvocationsAdaptive || []) };
  } else {
  const deployments = await read(script + '/deployments', r => { const d = r.deployments?.[0]; return { latest: d && { id: d.id, source: d.source, strategy: d.strategy, versions: d.versions, created_on: d.created_on } }; });
  const version = deployments?.deployments?.[0]?.versions?.[0]?.version_id;
  if (version && /^[a-f0-9-]{36}$/.test(version)) await read(script + '/versions/' + version, r => ({ id: r.id, created_on: r.metadata?.created_on, source: r.metadata?.source, script: { handlers: r.resources?.script?.handlers, etag: r.resources?.script?.etag }, runtime: r.resources?.script_runtime, bindings: bindings(r.resources?.bindings) }));
  await read(prefix + '/workers/subdomain', r => ({ subdomain: r.subdomain }));
  await read(script + '/subdomain', r => ({ enabled: r.enabled, previews_enabled: r.previews_enabled }));
  await read(prefix + `/workers/services/${worker}`, r => ({ id: r.id, default_environment: r.default_environment && { name: r.default_environment.environment, script: { name: r.default_environment.script?.id, handlers: r.default_environment.script?.handlers, compatibility_date: r.default_environment.script?.compatibility_date } }, environments: r.environments?.map(e => ({ environment: e.environment })) }));
  await read(prefix + '/workers/domains', r => r.filter(d => d.service === worker).map(d => ({ hostname: d.hostname, service: d.service, environment: d.environment })));
  await read(prefix + '/pages/projects/edgetunnel-test', r => ({ name: r.name, subdomain: r.subdomain, domains: r.domains, production_branch: r.production_branch, production_deployment: r.canonical_deployment && { id: r.canonical_deployment.id, created_on: r.canonical_deployment.created_on, environment: r.canonical_deployment.environment, latest_stage: r.canonical_deployment.latest_stage?.status }, configuration: Object.fromEntries(Object.entries(r.deployment_configs || {}).map(([k,v]) => [k, { compatibility_date: v.compatibility_date, compatibility_flags: v.compatibility_flags, env_var_names: Object.keys(v.env_vars || {}), kv_binding_names: Object.keys(v.kv_namespaces || {}) }])) }));
  // GraphQL POST is a query, with a mandatory exact test script filter.
  const body = { query: 'query($account: string, $start: Time, $end: Time, $script: string) { viewer { accounts(filter:{accountTag:$account}) { workersInvocationsAdaptive(limit:100,filter:{scriptName:$script,datetime_geq:$start,datetime_leq:$end}) { dimensions { scriptName status } sum { requests errors } } } } }', variables: { account, script: worker, start: '2026-10-24T21:00:00Z', end: new Date().toISOString() } };
  const r = await fetch(api + '/graphql', { method: 'POST', headers: { ...headers, 'Content-Type': 'application/json' }, body: JSON.stringify(body), dispatcher, signal: AbortSignal.timeout(20000) });
  const j = await r.json();
  report.evidence.analytics = { http: r.status, errors: j.errors?.map(e => ({ message: e.message, code: e.extensions?.code })), rows: j.data?.viewer?.accounts?.flatMap(a => a.workersInvocationsAdaptive || []) };
  for (const [name, url] of [['checker', 'https://gate-checker-test.renatirudy246.workers.dev/health'], ['test_pages', 'https://edgetunnel-test-4pz.pages.dev/health']]) {
    const r = await fetch(url + '?research=' + Date.now(), { dispatcher, signal: AbortSignal.timeout(15000), headers: { 'Cache-Control': 'no-cache' } });
    const text = await r.text(); let parsed;
    try { const j = JSON.parse(text); parsed = { service: j.service, configured: j.configured }; } catch { parsed = { cloudflare_error: /1101/.test(text) ? 1101 : null }; }
    report.evidence[name] = { time: new Date().toISOString(), http: r.status, body: parsed, ray: r.headers.get('cf-ray'), date: r.headers.get('date') };
  }
  }
} catch (e) { report.error = { name: e.name, message: e.message }; process.exitCode = 1; }
finally {
  await mkdir('diagnostics', { recursive: true });
  await writeFile(process.argv[2] === 'telemetry' ? 'diagnostics/research-telemetry.json' : 'diagnostics/research-readonly.json', JSON.stringify(report, null, 2));
  console.log(JSON.stringify(report, null, 2));
  await dispatcher.destroy();
}
