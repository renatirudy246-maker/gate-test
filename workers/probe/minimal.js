// Deliberately no imports, bindings, secrets, initialization or external calls.
export default {
  fetch() {
    return new Response('{"service":"gate-checker-probe","stage":"static-minimal","configured":false}', {
      status: 200,
      headers: { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' }
    });
  }
};
