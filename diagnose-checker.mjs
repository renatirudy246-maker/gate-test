// Read only this test Worker's exceptions. Raw tail events stay in memory.
import { spawn, execFile } from 'node:child_process';
const tail = spawn(process.execPath, ['node_modules/wrangler/bin/wrangler.js', 'tail', 'gate-checker-test', '--config', 'workers/checker/wrangler.jsonc', '--format', 'json', '--method', 'GET', '--status', 'error'],
  { env: { ...process.env, WRANGLER_SEND_METRICS: 'false' }, stdio: ['ignore', 'pipe', 'pipe'] });
let output = '', errors = '';
tail.stdout.on('data', b => { output += b.toString(); });
tail.stderr.on('data', b => { errors += b.toString(); });
await new Promise(resolve => setTimeout(resolve, 5000));
await new Promise(resolve => execFile('powershell.exe', ['-NoProfile', '-Command', "try{Invoke-WebRequest 'https://gate-checker-test.renatirudy246.workers.dev/health' -TimeoutSec 10|Out-Null}catch{}"], { windowsHide: true }, resolve));
await new Promise(resolve => setTimeout(resolve, 4000));
tail.kill();
await new Promise(resolve => setTimeout(resolve, 300));
const chunks = output.split(/(?=\{\s*"outcome")/);
const exceptions = [];
for (const chunk of chunks) {
  try { const event = JSON.parse(chunk); for (const e of event.exceptions || []) exceptions.push({ name: e.name, message: String(e.message).slice(0, 200) }); } catch {}
}
const connected = /Connected|Successfully created tail|"outcome"/.test(output + errors);
const summary = connected ? '' : (output + errors).replace(/https?:\/\/\S+/g, '[URL]').replace(/Bearer\s+\S+/gi, 'Bearer [redacted]').split('\n').filter(s => /ERROR|failed|not |scope|Pages|WebSocket|fetch/i.test(s)).join('\n').slice(0,600);
console.log(JSON.stringify({ exceptions, permission_denied: /unauthoriz|permission|authentication|403/i.test(errors), tail_connected: connected, connection_error: summary }));
