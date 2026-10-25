import { Agent, request } from 'node:https';
import tls from 'node:tls';
import { Duplex } from 'node:stream';
import { sstpConnect } from '../workers/checker/upstream.js';
import { checkCandidate, observeExit, EVIDENCE } from './check.mjs';
import { withSocketScope } from './performance-sockets.mjs';
export const DOWNLOAD_BYTES = 1048576;
export const TARGET_COUNTRIES = new Set(['US', 'JP', 'KR', 'SG']);

export function throughputMbps(bytes, elapsedMs) {
  if (bytes !== DOWNLOAD_BYTES || !Number.isFinite(elapsedMs) || elapsedMs <= 0) throw Error('Incomplete or invalid download measurement');
  return bytes * 8 / elapsedMs / 1000;
}
export function parseTrace(text) {
  const fields = Object.fromEntries(text.trim().split('\n').map(line => { const i = line.indexOf('='); return [line.slice(0, i), line.slice(i + 1)]; }));
  if (!fields.ip || !/^[A-Z]{2}$/.test(fields.loc || '')) throw Error('Missing authenticated speed-session exit');
  return { ip: fields.ip, country_code: fields.loc, colo: fields.colo };
}
export function summarizePerformance(result) {
  const speeds = result.downloads.map(d => d.mbps);
  const observations = result.identity?.observations || [];
  const identityVerified = result.identity?.success === true && result.identity.evidence === EVIDENCE && observations.length === 3 &&
    new Set(observations.map(o=>o.observer)).size === 2 && observations.some(o=>o.observer==='ipwhois') && observations.some(o=>o.observer==='ipify') &&
    observations.every(o=>o.ip===result.identity.exit.ip && o.certificate_verified===true);
  const complete = identityVerified && result.downloads.length === 2 && result.final_exit?.ip === result.identity.exit.ip && result.final_exit?.certificate_verified === true &&
    TARGET_COUNTRIES.has(result.identity.exit.country_code) && result.downloads.every(d =>
      d.exit_ip === result.identity.exit.ip && d.country_code === result.identity.exit.country_code &&
      d.bytes === DOWNLOAD_BYTES && d.certificate_verified === true && d.same_tls_connection === true && Number.isFinite(d.mbps) && d.mbps > 0);
  const min = complete ? Math.min(...speeds) : null, max = complete ? Math.max(...speeds) : null;
  return { usable: complete, min_download_mbps: min, max_download_mbps: max,
    short_term_stable: complete && max / min <= 2 && result.elapsed_ms >= 20000,
    meets_5mbps_target: complete && min >= 5, long_term_stability: 'unknown' };
}
async function speedRound(proxy, expected) {
  const host = 'speed.cloudflare.com';
  const tunnel = await sstpConnect(proxy, host, 443);
  tunnel.closed.catch(() => {});
  const bridge = Duplex.fromWeb({ readable: tunnel.readable, writable: tunnel.writable });
  bridge.on('error', () => {});
  const agent = new Agent({ keepAlive: true, maxSockets: 1 });
  let secure, connectionCount = 0;
  agent.createConnection = (_options, callback) => {
    if (++connectionCount !== 1) { callback(Error('Speed session closed; direct/reconnection fallback forbidden')); return; }
    let called = false;
    const done = (error, value) => { if (!called) { called = true; callback(error, value); } };
    secure = tls.connect({ socket: bridge, servername: host, rejectUnauthorized: true, ALPNProtocols: ['http/1.1'] });
    secure.once('secureConnect', () => done(secure.authorized ? null : Error('Speed endpoint certificate invalid'), secure));
    secure.once('error', error => done(error));
  };
  async function get(path, maximum, collect) {
    const started = performance.now();
    return new Promise((resolve, reject) => {
      const req = request({ hostname: host, port: 443, path, agent, signal: AbortSignal.timeout(30000), headers: {
        'Accept-Encoding': 'identity', 'Cache-Control': 'no-cache', 'User-Agent': 'gate-test-bounded-performance/1.0'
      } }, res => {
        if (res.statusCode !== 200 || res.socket !== secure || !secure.authorized || (res.headers['content-encoding'] && res.headers['content-encoding'] !== 'identity')) {
          res.resume(); reject(Error(`Speed endpoint HTTP ${res.statusCode} or unverified tunnel socket`)); return;
        }
        let bytes = 0, firstByteMs = null; const chunks = [];
        res.on('data', chunk => {
          if (firstByteMs === null) firstByteMs = performance.now() - started;
          bytes += chunk.length;
          if (bytes > maximum) req.destroy(Error('Measurement exceeded byte budget'));
          else if (collect) chunks.push(chunk);
        });
        res.on('error', reject);
        res.on('aborted', () => reject(Error('Speed response aborted')));
        res.on('end', () => resolve({ bytes, elapsed_ms: performance.now() - started, ttfb_ms: firstByteMs,
          text: collect ? Buffer.concat(chunks).toString('utf8') : undefined }));
      });
      req.on('error', reject); req.end();
    });
  }
  try {
    // Cloudflare reports the observer IP on the SAME TLS connection used below.
    // No credentials, Referer spoofing or access-control bypass is used.
    const trace = parseTrace((await get('/cdn-cgi/trace', 65536, true)).text);
    if (trace.ip !== expected.ip || trace.country_code !== expected.country_code) throw Error('Speed-session exit changed or country sources disagree');
    const download = await get(`/__down?bytes=${DOWNLOAD_BYTES}`, DOWNLOAD_BYTES, false);
    return { ...download, mbps: throughputMbps(download.bytes, download.elapsed_ms), exit_ip: trace.ip,
      country_code: trace.country_code, colo: trace.colo, certificate_verified: secure.authorized,
      same_tls_connection: connectionCount === 1, observed_at: new Date().toISOString() };
  } finally { agent.destroy(); bridge.destroy(); tunnel.close(); }
}
export async function benchmarkNode(node) {
  const started = Date.now();
  const value = `vpn:vpn@${node.host}:${node.port}`;
  const result = { host: node.host, port: node.port, source_country_code: node.source_country_code,
    candidate_origin: node.candidate_origin, previous_exit_ip: node.previous_exit_ip,
    historical_risk_score: node.historical_risk_score, historical_risk_checked_at: node.historical_risk_checked_at,
    started_at: new Date().toISOString(), downloads: [], attempts: 0, verified_sessions: 0 };
  try {
    result.identity = await withSocketScope(() => checkCandidate(value), 60000);
    result.attempts = result.identity.stability?.total_observations || 3;
    result.verified_sessions = result.identity.observations?.length || 0;
    if (!result.identity.success) throw Error(result.identity.error || 'Current exit verification failed');
    if (!TARGET_COUNTRIES.has(result.identity.exit.country_code)) throw Error('Actual exit outside target countries');
    const proxy = { type: 'sstp', hostname: node.host, port: node.port, username: 'vpn', password: 'vpn' };
    result.attempts++;
    result.downloads.push(await withSocketScope(() => speedRound(proxy, result.identity.exit), 45000));
    result.verified_sessions++;
    await new Promise(resolve => setTimeout(resolve, 20000));
    result.attempts++;
    result.downloads.push(await withSocketScope(() => speedRound(proxy, result.identity.exit), 45000));
    result.verified_sessions++;
    result.attempts++;
    result.final_exit = await withSocketScope(() => observeExit(proxy, 'ipify'), 30000);
    if (result.final_exit.ip !== result.identity.exit.ip) throw Error('Exit changed at final independent reconnect');
    result.verified_sessions = 6;
  } catch (error) { result.error = String(error.message).slice(0, 300); }
  result.finished_at = new Date().toISOString(); result.elapsed_ms = Date.now() - started;
  Object.assign(result, summarizePerformance(result));
  return result;
}
