export default {
  fetch() {
    return new Response('{"service":"gate-checker-test","stage":"static-minimal","configured":false}',{headers:{'Content-Type':'application/json','Cache-Control':'no-store'}});
  }
};
