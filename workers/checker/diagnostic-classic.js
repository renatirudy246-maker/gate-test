// Test-only classic-format control: no imports, no secrets, no network calls.
addEventListener('fetch', event => event.respondWith(new Response('{"service":"gate-checker-test","stage":"classic-minimal","configured":false}', {headers:{'Content-Type':'application/json','Cache-Control':'no-store'}})));
