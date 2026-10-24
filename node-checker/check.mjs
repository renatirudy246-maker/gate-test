import { Agent, request } from 'node:https';
import tls from 'node:tls';
import { Duplex } from 'node:stream';
import { sstpConnect } from '../workers/checker/upstream.js';

export const EVIDENCE = 'SSTP tunnel to two certificate-validated independent HTTPS exit services';
const observers = { ipwhois: ['ipwho.is', '/'], ipify: ['api.ipify.org', '/?format=json'] };
export async function observeExit(proxy, observer) {
  const [host, path] = observers[observer];
  const started = Date.now();
  const tunnel = await sstpConnect(proxy, host, 443);
  tunnel.closed.catch(() => {});
  const bridge = Duplex.fromWeb({ readable: tunnel.readable, writable: tunnel.writable });
  bridge.on('error', () => {});
  const agent = new Agent({ keepAlive: false, maxSockets: 1 });
  let secure;
  // A dedicated agent has no direct-network fallback: its only socket comes
  // from the userspace SSTP tunnel. Node performs CA and hostname verification.
  agent.createConnection = (_options, callback) => {
    let called = false;
    const done = (error, value) => { if (!called) { called = true; callback(error, value); } };
    secure = tls.connect({ socket: bridge, servername: host, rejectUnauthorized: true, ALPNProtocols: ['http/1.1'] });
    secure.once('secureConnect', () => done(secure.authorized ? null : Error('Observer certificate not authorized'), secure));
    secure.once('error', error => done(error));
  };
  try {
    const body = await new Promise((resolve, reject) => {
      const req = request({ hostname: host, port: 443, path, agent, method: 'GET', signal: AbortSignal.timeout(25000), headers: { Accept: 'application/json', 'Accept-Encoding': 'identity', Connection: 'close', 'User-Agent': 'gate-test-bounded-check/1.0' } }, res => {
        if (res.statusCode !== 200) { res.resume(); reject(Error(`Exit observer ${observer} HTTP ${res.statusCode}`)); return; }
        const chunks = []; let bytes = 0;
        res.on('data', chunk => { bytes += chunk.length; if (bytes > 65536) req.destroy(Error('Exit observer response too large')); else chunks.push(chunk); });
        res.on('error', reject);
        res.on('end', () => { try { resolve(JSON.parse(Buffer.concat(chunks).toString('utf8'))); } catch { reject(Error('Exit observer returned invalid JSON')); } });
      });
      req.on('error', reject); req.end();
    });
    if (!secure?.authorized || typeof body.ip !== 'string' || body.success === false) throw Error('Unverified exit observation');
    return { observer, ip: body.ip, country_code: body.country_code, asn: body.connection?.asn, org: body.connection?.org, latency_ms: Date.now() - started, observed_at: new Date().toISOString(), certificate_verified: true };
  } finally { agent.destroy(); bridge.destroy(); tunnel.close(); }
}

export async function checkCandidate(value) {
  const match = /^vpn:vpn@((?:vpn\d+|vpnv\d+|public-vpn-[a-z0-9-]+)\.opengw\.net):(\d{1,5})$/i.exec(value);
  if (!match || +match[2] < 1 || +match[2] > 65535) throw Error('Invalid public VPN Gate candidate');
  const proxy = { type: 'sstp', hostname: match[1], port: +match[2], username: 'vpn', password: 'vpn' };
  const observations = [];
  try {
  observations.push(await observeExit(proxy, 'ipwhois'));
  observations.push(await observeExit(proxy, 'ipify'));
  if (observations[0].ip !== observations[1].ip) throw Error('Independent tunnel exit observations disagree');
  // A third fresh tunnel records short repeatability, not long-term stability.
  observations.push(await observeExit(proxy, 'ipify'));
  if (observations.some(x => x.ip !== observations[0].ip)) throw Error('Exit changed during repeated tunnel observations');
  const first = observations[0];
  return { success: true, responseTime: first.latency_ms, evidence: EVIDENCE,
    exit: { ip: first.ip, country_code: first.country_code, asn: { asn: first.asn, org: first.org } },
    observations, stability: { successful_observations: 3, total_observations: 3, same_exit: true, long_term: 'unknown' } };
  } catch (error) {
    return { success: false, error: String(error.message).slice(0, 240), observations,
      stability: { successful_observations: observations.length, total_observations: observations.length + 1, long_term: 'unknown' } };
  }
}
