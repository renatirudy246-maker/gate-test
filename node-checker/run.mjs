// This runner deliberately refuses to start a listener on the user's computer.
import { createServer } from 'node:http';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { mkdir, writeFile } from 'node:fs/promises';
import { build } from 'esbuild';
import tls from 'node:tls';
import { makeHandler } from './server.mjs';
if (process.env.GITHUB_ACTIONS !== 'true' || process.platform !== 'linux') throw Error('Only disposable Linux GitHub Actions runners are permitted');
if (!process.env.CHECK_TOKEN || process.env.CHECK_TOKEN.length < 16) throw Error('Missing independent test secret');
await mkdir('dist', { recursive: true });
await build({ entryPoints: ['node-checker/check.mjs'], outfile: 'dist/node-checker.mjs', bundle: true, platform: 'node', format: 'esm', alias: { 'cloudflare:sockets': './node-checker/sockets.mjs' } });
const { checkCandidate } = await import('../dist/node-checker.mjs');
// Validate the real TLS runtime before claiming readiness. No VPN candidate is
// contacted by this check. All candidate observers use the same native PKI API.
const control = tls.connect({ host: 'ipwho.is', port: 443, servername: 'ipwho.is', rejectUnauthorized: true });
try { await Promise.race([once(control, 'secureConnect'), new Promise((_, reject) => { const timer = setTimeout(() => reject(Error('TLS self-test timeout')), 15000); timer.unref(); })]); if (!control.authorized) throw Error('TLS self-test failed'); }
finally { control.destroy(); }
const server = createServer(makeHandler({ token: process.env.CHECK_TOKEN, checkCandidate, ready: true }));
server.listen(0, '127.0.0.1'); await once(server, 'listening');
const checker = `http://127.0.0.1:${server.address().port}/check`;
try {
  const health = await fetch(checker.replace('/check', '/health'));
  const body = await health.json();
  await mkdir('diagnostics', { recursive: true });
  await writeFile('diagnostics/node-health.json', JSON.stringify({ time: new Date().toISOString(), http: health.status, ...body }, null, 2));
  if (health.status !== 200 || body.configured !== true) throw Error('Actual node health check failed; scanning blocked');
  console.log(JSON.stringify({ node_health: health.status, configured: body.configured, max_candidates: 10, max_concurrency: 2 }));
  const child = spawn('python', ['vpngate.py'], { stdio: 'inherit', env: { ...process.env, CHECK_WORKER: checker, CHECK_BACKEND: 'node-local', MAX_CHECK_NODES: '10', CHECK_CONCURRENCY: '2' } });
  const [code] = await once(child, 'exit'); process.exitCode = code ?? 1;
} finally { server.closeAllConnections(); await new Promise(resolve => server.close(resolve)); }
