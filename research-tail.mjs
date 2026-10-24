// One official Wrangler tail attempt. Raw child output is never printed/saved.
// This checks the CLI's own WebSocket implementation, without changing a Worker.
import { spawn, execFileSync } from 'node:child_process';
import { fetch, EnvHttpProxyAgent } from 'undici';
import { writeFile } from 'node:fs/promises';
const worker = 'gate-checker-test';
const base = 'https://api.cloudflare.com/client/v4/accounts/e5a0857508f37d031d9137c3ecec80e3/workers/scripts/' + worker;
const env = { ...process.env, WRANGLER_SEND_METRICS: 'false', WRANGLER_LOG: 'none' };
const dispatcher = new EnvHttpProxyAgent();
let child;
const report = { time: new Date().toISOString(), worker, connection_confirmed: false, events: [], stderr_received: false };
const safeMessage = value => String(value || '').replace(/Bearer\s+\S+|(?:token|secret|password|cookie|authorization)\s*[:=]\s*\S+/gi, '[redacted]').slice(0, 500);
try {
  let raw;
  try { raw = execFileSync(process.execPath, ['node_modules/wrangler/bin/wrangler.js', 'auth', 'token', '--json'], { encoding: 'utf8', timeout: 20000, stdio: ['ignore', 'pipe', 'pipe'], env }); }
  catch { throw Error('Existing authorization unavailable'); }
  const auth = JSON.parse(raw.slice(raw.indexOf('{'), raw.lastIndexOf('}') + 1));
  const headers = { Authorization: `Bearer ${auth.token}` };
  async function tails() { const r = await fetch(base + '/tails', { headers, dispatcher, signal: AbortSignal.timeout(15000) }); const j = await r.json(); if (!r.ok || !j.success) throw Error('Tail list HTTP ' + r.status); return j.result.map(t => t.id); }
  const before = new Set(await tails());
  child = spawn(process.execPath, ['node_modules/wrangler/bin/wrangler.js', 'tail', worker, '--format=json', '--config=workers/checker/wrangler.jsonc'], { env, stdio: ['ignore', 'pipe', 'pipe'], windowsHide: true });
  let buffer = '', depth = 0, quoted = false, escaped = false, stdoutBytes = 0;
  child.stdout.on('data', chunk => {
    stdoutBytes += chunk.length;
    // JSON output is indented and may span arbitrary stdout chunks.
    for (const c of chunk.toString()) {
      if (!depth) { if (c !== '{') continue; buffer = ''; quoted = false; escaped = false; }
      buffer += c;
      if (quoted) { if (escaped) escaped = false; else if (c === '\\') escaped = true; else if (c === '"') quoted = false; }
      else if (c === '"') quoted = true;
      else if (c === '{') depth++;
      else if (c === '}' && --depth === 0) {
        try { const e = JSON.parse(buffer); if (e.outcome) { report.connection_confirmed = true; report.events.push({ outcome: e.outcome, worker: e.scriptName, exceptions: (e.exceptions || []).map(x => ({ name: x.name, message: safeMessage(x.message), stack: safeMessage(x.stack) })) }); } } catch { report.parse_error = true; }
        buffer = '';
      }
    }
  });
  child.stderr.on('data', () => { report.stderr_received = true; });
  child.on('exit', (code, signal) => { report.child_exit = { code, signal }; });
  await new Promise(resolve => setTimeout(resolve, 5000));
  const own = (await tails()).filter(id => !before.has(id));
  report.new_session_count = own.length;
  try { const r = await fetch('https://gate-checker-test.renatirudy246.workers.dev/health?official_tail=' + Date.now(), { dispatcher, signal: AbortSignal.timeout(15000) }); report.health = { http: r.status, ray: r.headers.get('cf-ray'), time: new Date().toISOString() }; await r.text(); }
  catch (e) { report.health = { error: e.name }; }
  await new Promise(resolve => setTimeout(resolve, 20000));
  report.stdout_bytes = stdoutBytes;
  child.kill();
  // Only remove the new transient tail created by this invocation. Never touch preexisting sessions.
  if (own.length === 1) {
    const r = await fetch(base + '/tails/' + own[0], { method: 'DELETE', headers, dispatcher, signal: AbortSignal.timeout(15000) });
    report.own_session_cleanup_http = r.status; await r.text();
  }
} catch (e) { report.error = { name: e.name, message: safeMessage(e.message) }; process.exitCode = 1; }
finally {
  child?.kill();
  await writeFile('diagnostics/research-official-tail.json', JSON.stringify(report, null, 2));
  console.log(JSON.stringify(report, null, 2));
  await dispatcher.destroy();
}
