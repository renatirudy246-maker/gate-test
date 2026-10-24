# Checker minimization diagnosis — 2026-10-25, Asia/Shanghai

Result: HTTP 500 / Cloudflare 1101 persists even for a constant-response Worker
with no imports, no binding reads and no asynchronous operations. There is no
evidence-backed application-code fix yet. No scan or workflow was started.

## Baseline and static comparison

- Git baseline: `145041ef67a675de15ee7f2871c7d5504a57bd03`; initial worktree clean.
- Rollback checkpoint commit: `a204b07`.
- Account: `e5a0857508f37d031d9137c3ecec80e3`.
- Only deployed target: `gate-checker-test`.
- Baseline active version: `cc1096d5-0185-487d-bd5f-02a3278172a0`, 100%.
- The actual uploaded source map contains index.js and upstream.js identical
  byte-for-byte to the local files. This was verified before and after diagnosis.
- `index.js:1` imports only `checkProxy`; `index.js:19` health does not call it.
- `upstream.js:1` imports `cloudflare:sockets`; top-level initialization consists
  of encoders, constants, arrays/maps and declarations. Crypto and socket work
  occurs inside functions/constructors; no top-level outbound request was found.
- Compared to the original checker, the test upstream change exports checkProxy,
  accepts an echo host/path, and omits iplocate field normalization. These changed
  statements are in the check function, not the health route. The test wrapper
  adds authenticated routes, signed echo and a rate-limit binding. The original
  uses compatibility date 2026-05-01; the test uses 2026-10-24.
- `/health` catches binding-access exceptions, but a 1101 does not identify the
  throwing statement. No module or binding was blamed without evidence.

Source/config and deployment snapshots were retained locally under the ignored
`diagnostics/` directory. They contain public code and binding names/types, never
Secret values or credentials. Remote version history is retained for rollback.

## Actual diagnostic deployments

All times below are 2026-10-25, Asia/Shanghai. Every stage used the same Worker
and account; no production Pages, KV, domain, route or Secret was touched.

| Time | Control | Version | Actual health result |
| --- | --- | --- | --- |
| 05:24:36 | Original baseline | cc1096d5-0185-487d-bd5f-02a3278172a0 | 500 / 1101 |
| 05:24:54 | Minimal ESM, real binding-presence check, no upstream import | 1d8f0068-285b-4f06-bed8-36952a92dfa2 | 500 / 1101 |
| 05:25:19 | Constant ESM response, no env access, original rate binding | cd13115a-136d-4ebc-b686-bd6d26bf6660 | 500 / 1101 |
| 05:25:30 | Constant ESM, no rate binding, 2026-10-24 compatibility | d6907c9c-929d-42d8-9ba9-935714b613b3 | 500 / 1101 |
| 05:26:10 | Same constant ESM, original 2026-05-01 compatibility | 89090aeb-05f2-4d33-b962-1c8d65d03096 | 500 / 1101 |
| 05:26:32 | Rollback baseline active version | cc1096d5-0185-487d-bd5f-02a3278172a0 | 500 / 1101 |
| 05:27:07 | Re-enable only test workers.dev mapping | baseline active | 500 / 1101 |
| 05:28:12 | Full source restored from local baseline | f2b8ce27-2f0c-4ec7-9dc5-0dbf834fba9d | 500 / 1101 |
| 05:28:33 | Classic addEventListener constant response, no imports/bindings | c32e6625-314a-493a-9511-053b2154fcb7 | 500 / 1101 |
| 05:29:03 | Final full source and rate binding restored | 30706388-c405-4f3d-8bb1-142065a7b563 | 500 / 1101 |

Additional checks:

- Cache-busting query and no-cache request still returned a fresh 500 with a new
  CF-Ray and response date; no Age/cache-hit header was present.
- Test workers.dev mapping was already enabled. Toggling only this test mapping
  off then on succeeded (API 200) but did not fix health.
- Temporarily enabled only this test Worker's Version URLs and compared the
  baseline prefix cc1096d5 with minimal prefix 89090aeb: both returned 500/1101.
  Version URLs were disabled again immediately. No custom domain was added.
- Independent web retrieval could not access the health URL; it supplied no
  additional runtime evidence and was not treated as a second successful test.
- Rollback updates the active deployment. The legacy script content/settings
  GET can still describe the latest upload; final evidence therefore comes from
  a fresh full-source upload, current deployment ID, and source-map comparison.

## Final state and limits of the conclusion

Final active version: `30706388-c405-4f3d-8bb1-142065a7b563`, 100%.
Full original test index.js/upstream.js restored; compatibility 2026-10-24;
CHECK_LIMITER and CHECK_TOKEN binding names/types present. No Secret was rotated.
Preview URLs disabled, normal workers.dev enabled. No diagnostic entry remains
active. Final CF-Ray: `a4fc1326bfed58bf-NRT` (05:29:03).

The controls do not support blaming SSTP, module import, HMAC, binding reads,
rate-limit binding, or the chosen compatibility date for the persistent response.
Inference: the unresolved failure lies beyond the exercised application logic,
possibly in deployment/execution or request routing. Its exact location and
provider-side cause remain UNKNOWN; no runtime stack has been obtained. A 1101
page alone is not proof of a specific Cloudflare incident or account restriction.

The next discriminating evidence would be a provider-side request trace using
the final CF-Ray and version IDs, or a functioning minimal response on this same
Worker. It is not necessary to ask the owner to disclose passwords/tokens or
change production resources. No support message was sent automatically.

## Validation and scan gate

- Eight Python tests passed, including healthy-service prerequisite, bounded
  count/concurrency, actual-exit-country filtering and unknown-risk rejection.
- Five JavaScript tests passed; diagnostic script syntax checks passed.
- Local unit tests are not proof of deployed runtime health.
- Health remains 500, so no manual workflow/scan was dispatched.
- Scanned candidates: 0. Verified/qualified residential exits: 0. No IP, latency,
  residential attribute or risk score can be reported as measured in this run.
- Target-country default remains US,JP,KR,SG. Unknown and datacenter exits cannot
  be relabeled residential. Publication safeguards remain unchanged.
- No plan upgrade, scheduled scan, Clash import, Windows proxy/DNS/route/TUN,
  production deployment or production resource change occurred.

## Reproducible test-only tools

`checker-control.mjs` hardcodes only this account and Worker. `snapshot` saves
code and sanitized deployment/setting metadata. `health` saves response status
and harmless response metadata. `inspect` reads test configuration/version data.
`refresh-subdomain` and `version-check` are explicit mutations confined to the
test Worker's workers.dev/Version URL settings; do not run them routinely.

Diagnostic entries and the no-limit configuration are retained for reproducible
controls. They are NOT a repair and NOT the main deployment entry. The normal
configuration remains `workers/checker/wrangler.jsonc` → `index.js`.
