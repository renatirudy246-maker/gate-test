import { AsyncLocalStorage } from 'node:async_hooks';
import { connect as baseConnect } from './sockets.mjs';
const scope = new AsyncLocalStorage();
export function connect(address, options) {
  const socket = baseConnect(address, options);
  const sockets = scope.getStore();
  sockets?.add(socket);
  socket.closed.then(() => sockets?.delete(socket));
  return socket;
}
export async function withSocketScope(work, timeoutMs) {
  const sockets = new Set();
  return scope.run(sockets, async () => {
    let timer;
    try {
      return await Promise.race([work(), new Promise((_, reject) => {
        timer = setTimeout(() => reject(Error('Bounded tunnel measurement deadline exceeded')), timeoutMs);
        timer.unref();
      })]);
    } finally {
      clearTimeout(timer);
      for (const socket of sockets) socket.close();
    }
  });
}
