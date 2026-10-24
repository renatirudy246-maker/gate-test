// Outbound sockets only. Used on a disposable Actions runner, never as a VPN/TUN.
import tls from 'node:tls';
import { Duplex } from 'node:stream';
const VPN_HOST = /^(?:vpn\d+|vpnv\d+|public-vpn-[a-z0-9-]+)\.opengw\.net$/i;
export function connect({ hostname, port }, options = {}) {
  if (!VPN_HOST.test(hostname) || options.secureTransport !== 'on' || !Number.isInteger(port) || port < 1 || port > 65535) throw Error('Only public VPN Gate outer SSTP TLS sockets allowed');
  // VPN Gate gateways use self-signed certificates. This exception applies ONLY
  // to the outer public gateway. Inner exit-observer HTTPS always validates PKI.
  const socket = tls.connect({ host: hostname, port, servername: hostname, rejectUnauthorized: false, timeout: 12000 });
  socket.on('timeout', () => socket.destroy(Error('Outer SSTP TLS timeout')));
  const opened = new Promise((resolve, reject) => { socket.once('secureConnect', resolve); socket.once('error', reject); });
  const closed = new Promise(resolve => socket.once('close', resolve));
  const web = Duplex.toWeb(socket);
  return { ...web, opened, closed, close() { socket.destroy(); } };
}
