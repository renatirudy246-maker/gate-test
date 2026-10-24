import { timingSafeEqual } from 'node:crypto';
export const HOST_RE = /^vpn:vpn@(?:vpn\d+|vpnv\d+|public-vpn-[a-z0-9-]+)\.opengw\.net:\d{1,5}$/i;
export function makeHandler({ token, checkCandidate, ready }) {
  let attempted = 0, active = 0;
  const used = new Set();
  const same = value => typeof token === 'string' && token.length >= 16 && typeof value === 'string' && Buffer.byteLength(value) === Buffer.byteLength(`Bearer ${token}`) && timingSafeEqual(Buffer.from(value), Buffer.from(`Bearer ${token}`));
  return async (req, res) => {
    const reply = (body, code = 200) => { res.writeHead(code, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' }); res.end(JSON.stringify(body)); };
    const url = new URL(req.url, 'http://127.0.0.1');
    const configured = ready === true && typeof token === 'string' && token.length >= 16;
    if (url.pathname === '/health') return reply({ service: 'gate-checker-test', backend: 'isolated-node-sstp', configured, max_candidates: 10, max_concurrency: 2 }, configured ? 200 : 503);
    if (!configured) return reply({ error: 'Node checker not ready' }, 503);
    if (!same(req.headers.authorization)) return reply({ error: 'Unauthorized' }, 401);
    if (url.pathname !== '/check' || req.method !== 'GET') return reply({ error: 'Not found' }, 404);
    const value = url.searchParams.get('sstp') || '';
    const port = Number(value.slice(value.lastIndexOf(':') + 1));
    if (!HOST_RE.test(value) || port < 1 || port > 65535) return reply({ error: 'Invalid candidate' }, 400);
    if (attempted >= 10 || active >= 2 || used.has(value)) return reply({ error: 'Single-run candidate/concurrency budget exhausted' }, 429);
    attempted++; active++; used.add(value);
    try { reply(await checkCandidate(value)); }
    catch (error) { reply({ success: false, error: String(error.message).slice(0, 240) }); }
    finally { active--; }
  };
}
