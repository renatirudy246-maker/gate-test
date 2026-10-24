import { checkProxy } from './upstream.js';

const headers = { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' };
const json = (data, status = 200) => new Response(JSON.stringify(data), { status, headers });
const hex = bytes => [...new Uint8Array(bytes)].map(x => x.toString(16).padStart(2, '0')).join('');
async function sign(secret, message) {
  const key = await crypto.subtle.importKey('raw', new TextEncoder().encode(secret), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
  return hex(await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(message)));
}
function equal(a, b) {
  if (typeof a !== 'string' || typeof b !== 'string' || a.length !== b.length) return false;
  let diff = 0; for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}
export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === '/health') {
      try { return json({ service: 'gate-checker-test', configured: Boolean(env.CHECK_TOKEN && env.CHECK_LIMITER) }); }
      catch (error) { return json({ service: 'gate-checker-test', configured: false, error: String(error.message).slice(0,160) }, 503); }
    }
    if (!env.CHECK_TOKEN || !env.CHECK_LIMITER) return json({ error: 'Test checker not configured' }, 503);
    // This public endpoint is reached THROUGH the candidate SSTP tunnel. It never
    // reveals a credential. The unpredictable nonce + HMAC authenticate the echo
    // even though the upstream userspace TLS implementation lacks PKI validation.
    if (url.pathname === '/echo' && request.method === 'GET') {
      const nonce = url.searchParams.get('nonce');
      if (!/^[a-f0-9]{48}$/.test(nonce || '')) return json({ error: 'Invalid nonce' }, 400);
      const ip = request.headers.get('CF-Connecting-IP');
      if (!ip) return json({ error: 'Missing observed IP' }, 502);
      const timestamp = Date.now();
      return json({ ip, nonce, timestamp, country_code: request.cf?.country ?? null,
        asn: { asn: request.cf?.asn ?? null, org: request.cf?.asOrganization ?? null },
        signature: await sign(env.CHECK_TOKEN, `${ip}|${nonce}|${timestamp}`) });
    }
    if (!equal(request.headers.get('Authorization'), `Bearer ${env.CHECK_TOKEN}`)) return json({ error: 'Unauthorized' }, 401);
    if (url.pathname !== '/check' || request.method !== 'GET') return json({ error: 'Not found' }, 404);
    const candidate = url.searchParams.get('sstp') || '';
    const match = /^vpn:vpn@((?:vpn\d+|vpnv\d+|public-vpn-[a-z0-9-]+)\.opengw\.net):(\d{1,5})$/i.exec(candidate);
    if (!match || Number(match[2]) < 1 || Number(match[2]) > 65535) return json({ error: 'Only public VPN Gate SSTP candidates accepted' }, 400);
    const limit = await env.CHECK_LIMITER.limit({ key: 'gate-test-sstp' });
    if (!limit.success) return json({ error: 'Test request limit reached' }, 429);
    const nonce = hex(crypto.getRandomValues(new Uint8Array(24)));
    const result = await checkProxy({ type: 'sstp', value: candidate }, request.cf?.colo ?? null,
      { host: url.hostname, path: `/echo?nonce=${nonce}` });
    if (!result.success) return json({ success: false, error: result.error, responseTime: result.responseTime });
    const exit = result.exit;
    const valid = exit?.nonce === nonce && Number.isFinite(exit.timestamp) && Math.abs(Date.now() - exit.timestamp) < 120000 &&
      equal(exit.signature, await sign(env.CHECK_TOKEN, `${exit.ip}|${nonce}|${exit.timestamp}`));
    if (!valid) return json({ success: false, error: 'Exit echo authentication failed', responseTime: result.responseTime });
    return json({ success: true, responseTime: result.responseTime, colo: result.colo,
      exit: { ip: exit.ip, country_code: exit.country_code, asn: exit.asn, is_datacenter: null },
      evidence: 'SSTP tunnel to nonce-bound HMAC-authenticated Cloudflare echo' });
  }
};
