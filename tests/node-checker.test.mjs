import test from 'node:test';
import assert from 'node:assert/strict';
import { makeHandler } from '../node-checker/server.mjs';

const token = 'unit-test-token-not-a-real-secret';
function invoke(handler, url, authorization = `Bearer ${token}`) {
  return new Promise(resolve => handler({ url, method: 'GET', headers: { authorization } }, { writeHead(status) { this.status = status; }, end(text) { resolve({ status: this.status, body: JSON.parse(text) }); } }));
}
test('readiness and authorization fail closed without opening sockets', async () => {
  let calls = 0;
  const checkCandidate = async () => { calls++; };
  assert.equal((await invoke(makeHandler({ token, checkCandidate, ready: false }), '/health')).status, 503);
  const handler = makeHandler({ token, checkCandidate, ready: true });
  assert.equal((await invoke(handler, '/health')).body.configured, true);
  assert.equal((await invoke(handler, '/check', 'Bearer wrong')).status, 401);
  assert.equal((await invoke(handler, '/check?sstp=vpn:vpn@127.0.0.1:443')).status, 400);
  assert.equal((await invoke(handler, '/check?sstp=vpn:vpn@vpn123.opengw.net:99999')).status, 400);
  assert.equal(calls, 0);
});
test('ten-candidate budget cannot be exceeded and duplicates cannot be retried', async () => {
  let calls = 0;
  const handler = makeHandler({ token, ready: true, checkCandidate: async () => { calls++; return { success: false }; } });
  for (let i = 0; i < 10; i++) assert.equal((await invoke(handler, `/check?sstp=vpn:vpn@vpn${i}.opengw.net:443`)).status, 200);
  assert.equal((await invoke(handler, '/check?sstp=vpn:vpn@vpn10.opengw.net:443')).status, 429);
  assert.equal((await invoke(handler, '/check?sstp=vpn:vpn@vpn0.opengw.net:443')).status, 429);
  assert.equal(calls, 10);
});
test('third concurrent candidate is denied before opening a tunnel', async () => {
  let release;
  const wait = new Promise(resolve => { release = resolve; });
  const handler = makeHandler({ token, ready: true, checkCandidate: async () => { await wait; return { success: false }; } });
  const one = invoke(handler, '/check?sstp=vpn:vpn@vpn1.opengw.net:443');
  const two = invoke(handler, '/check?sstp=vpn:vpn@vpn2.opengw.net:443');
  assert.equal((await invoke(handler, '/check?sstp=vpn:vpn@vpn3.opengw.net:443')).status, 429);
  release(); await Promise.all([one, two]);
});
