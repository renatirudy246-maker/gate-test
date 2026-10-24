import test from 'node:test';
import assert from 'node:assert/strict';
import { build } from 'esbuild';

async function load(entry) {
  const result = await build({ entryPoints: [entry], bundle: true, write: false, format: 'esm', platform: 'browser',
    plugins: [{ name: 'deny-network', setup(b) {
      b.onResolve({ filter: /^cloudflare:sockets$/ }, () => ({ path: 'sockets', namespace: 'mock' }));
      b.onLoad({ filter: /.*/, namespace: 'mock' }, () => ({ contents: 'export function connect(){throw Error("Network forbidden in unit test")}' }));
    } }] });
  return import('data:text/javascript;base64,' + Buffer.from(result.outputFiles[0].text).toString('base64'));
}
const checker = (await load('workers/checker/index.js')).default;
const edge = await load('workers/edgetunnel/index.js');
const env = { CHECK_TOKEN: 'unit-test-only', CHECK_LIMITER: { limit: async () => ({ success: false }) } };

test('checker fails closed without secrets and without authorization', async () => {
  assert.equal((await checker.fetch(new Request('https://test.workers.dev/check'), {})).status, 503);
  assert.equal((await checker.fetch(new Request('https://test.workers.dev/check'), env)).status, 401);
});
test('checker rejects arbitrary proxy targets before opening sockets', async () => {
  const req = new Request('https://test.workers.dev/check?sstp=vpn:vpn@127.0.0.1:443', { headers: { Authorization: 'Bearer unit-test-only' } });
  assert.equal((await checker.fetch(req, env)).status, 400);
});
test('checker enforces rate limiting before opening sockets', async () => {
  const req = new Request('https://test.workers.dev/check?sstp=vpn:vpn@vpn123456.opengw.net:443', { headers: { Authorization: 'Bearer unit-test-only' } });
  assert.equal((await checker.fetch(req, env)).status, 429);
});
test('exit echo is nonce bound and signed without revealing credentials', async () => {
  const nonce = 'ab'.repeat(24);
  const req = new Request('https://test.workers.dev/echo?nonce=' + nonce, { headers: { 'CF-Connecting-IP': '1.1.1.1' } });
  const body = await (await checker.fetch(req, env)).json();
  assert.equal(body.ip, '1.1.1.1');
  assert.equal(body.nonce, nonce);
  assert.match(body.signature, /^[a-f0-9]{64}$/);
  assert.ok(!JSON.stringify(body).includes(env.CHECK_TOKEN));
});
test('Clash conversion stays local, preserves paths, and rejects empty nodes', () => {
  assert.throws(() => edge.toClash(''));
  const link = 'vless://00000000-0000-4000-8000-000000000000@test.pages.dev:443?type=ws&security=tls&host=test.pages.dev&sni=test.pages.dev&path=%2Fvideo%2Ftest#US-unknown';
  const sub = JSON.parse(edge.toClash(link));
  assert.equal(sub.proxies.length, 1);
  assert.equal(sub.proxies[0]['ws-opts'].path, '/video/test');
  assert.equal(sub.proxies[0]['skip-cert-verify'], false);
  assert.ok(!('mixed-port' in sub));
  assert.ok(!('tun' in sub));
});
