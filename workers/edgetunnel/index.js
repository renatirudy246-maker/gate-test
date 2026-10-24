import upstream, { MD5MD5, base64SecretDecode } from './_worker.js';

const encoder = new TextEncoder();
const json = (data, status = 200) => new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' } });
function equal(a, b) {
  if (typeof a !== 'string' || typeof b !== 'string' || a.length !== b.length) return false;
  let diff = 0; for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}
async function sessionKey(env, ua) {
  const bytes = await crypto.subtle.digest('SHA-256', encoder.encode(env.ADMIN + '|' + ua));
  return [...new Uint8Array(bytes)].map(x => x.toString(16).padStart(2, '0')).join('');
}
async function adminAuth(request, env) {
  if (equal(request.headers.get('Authorization'), `Bearer ${env.ADMIN}`)) return true;
  const cookie = (request.headers.get('Cookie') || '').split(';').map(x => x.trim()).find(x => x.startsWith('gate_auth='))?.slice(10);
  return equal(cookie, await sessionKey(env, request.headers.get('User-Agent') || ''));
}
export function toClash(text) {
  const lines = text.trim().split('\n').filter(Boolean);
  if (!lines.length || lines.length > 10) throw Error('No bounded test subscription');
  const proxies = lines.map(line => {
    const u = new URL(line.trim());
    if (u.protocol !== 'vless:' || u.searchParams.get('type') !== 'ws' || !u.searchParams.get('path')?.startsWith('/video/')) throw Error('Unexpected test node format');
    return { name: decodeURIComponent(u.hash.slice(1)), type: 'vless', server: u.hostname,
      port: Number(u.port || 443), uuid: u.username, network: 'ws', tls: true, udp: false,
      servername: u.searchParams.get('sni'), 'skip-cert-verify': false,
      'ws-opts': { path: u.searchParams.get('path'), headers: { Host: u.searchParams.get('host') } } };
  });
  // JSON is valid YAML 1.2, avoiding third-party subscription converters entirely.
  return JSON.stringify({ proxies, 'proxy-groups': [{ name: 'Gate Test', type: 'select', proxies: proxies.map(p => p.name) }], rules: ['MATCH,Gate Test'] }, null, 2);
}
export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    if (url.pathname === '/health') return json({ service: 'edgetunnel-test', configured: Boolean(env.ADMIN && env.UUID && env.SUB_TOKEN && env.KV), automatic_update: false });
    if (!env.ADMIN || !env.UUID || !env.SUB_TOKEN || !env.KV) return json({ error: 'Independent test credentials/binding missing' }, 503);
    if (url.pathname === '/login') {
      if (request.method === 'POST') {
        const form = new URLSearchParams(await request.text());
        if (!equal(form.get('password'), env.ADMIN)) return json({ error: 'Unauthorized' }, 401);
        return new Response(null, { status: 303, headers: { Location: '/admin', 'Set-Cookie': `gate_auth=${await sessionKey(env, request.headers.get('User-Agent') || '')}; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age=3600`, 'Cache-Control': 'no-store' } });
      }
      return new Response('<!doctype html><meta charset="utf-8"><title>edgetunnel-test login</title><h1>独立测试后台</h1><form method="post"><label>测试 ADMIN <input name="password" type="password" autocomplete="off"></label><button>登录</button></form>', { headers: { 'Content-Type': 'text/html; charset=utf-8', 'Content-Security-Policy': "default-src 'none'; form-action 'self'; frame-ancestors 'none'", 'Cache-Control': 'no-store' } });
    }
    const isAdmin = url.pathname === '/admin' || url.pathname === '/admin/subscription';
    if (isAdmin && !await adminAuth(request, env)) return new Response(null, { status: 302, headers: { Location: '/login' } });
    if (url.pathname === '/admin') {
      return new Response('<!doctype html><meta charset="utf-8"><title>edgetunnel-test</title><h1>独立测试环境</h1><p>不连接生产 KV，不使用第三方订阅转换。</p><a href="/admin/subscription">下载本次测试订阅（须已有成功出口）</a>', { headers: { 'Content-Type': 'text/html; charset=utf-8', 'Content-Security-Policy': "default-src 'none'; frame-ancestors 'none'", 'Cache-Control': 'no-store' } });
    }
    if (url.pathname === '/sub' || url.pathname === '/admin/subscription') {
      if (!isAdmin && !equal(url.searchParams.get('token'), env.SUB_TOKEN)) return json({ error: 'Unauthorized' }, 401);
      if (request.method !== 'GET') return json({ error: 'Method not allowed' }, 405);
      const source = await fetch(env.NODES_URL, { redirect: 'error', cache: 'no-store' });
      if (!source.ok) return json({ error: 'No verified test nodes published', source_status: source.status }, 503);
      const nodes = (await source.text()).trim().split('\n').filter(Boolean);
      if (!nodes.length || nodes.length > 10 || !nodes.every(n => /^[a-z0-9.-]+:443#[^\r\n]+\$sstp:\/\/vpn:vpn@(?:vpn\d+|vpnv\d+|public-vpn-[a-z0-9-]+)\.opengw\.net:\d{1,5}$/i.test(n))) return json({ error: 'Invalid verified nodes list' }, 503);
      const internal = new URL('/sub', url.origin);
      internal.searchParams.set('target', 'mixed');
      internal.searchParams.set('token', await MD5MD5(url.hostname + env.UUID));
      const response = await upstream.fetch(new Request(internal, { headers: { 'User-Agent': 'Mozilla/5.0 gate-test' }, cf: request.cf }), env, ctx);
      if (!response.ok) return json({ error: 'Subscription generation failed' }, 503);
      try {
        return new Response(toClash(await response.text()), { headers: { 'Content-Type': 'text/yaml; charset=utf-8', 'Cache-Control': 'no-store', 'Content-Disposition': 'attachment; filename=gate-test.yaml' } });
      } catch { return json({ error: 'Subscription validation failed' }, 503); }
    }
    if (/^\/video\/[^/]+\/?$/.test(url.pathname) && (request.headers.get('Upgrade') || '').toLowerCase() === 'websocket') {
      try {
        const chain = JSON.parse(base64SecretDecode(url.pathname.split('/')[2], env.UUID));
        if (chain.type !== 'sstp' || !/\.opengw\.net$/i.test(chain.hostname) || chain.username !== 'vpn' || chain.password !== 'vpn') return json({ error: 'SSTP test path required' }, 403);
      } catch { return json({ error: 'Invalid test path' }, 403); }
      return upstream.fetch(request, env, ctx);
    }
    return json({ service: 'edgetunnel-test', admin: '/admin' }, url.pathname === '/' ? 200 : 404);
  }
};
