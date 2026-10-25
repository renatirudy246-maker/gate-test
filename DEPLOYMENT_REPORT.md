# Independent test deployment: 2026-10-25 (Asia/Shanghai)

Latest performance objective: see `PERFORMANCE_RESULT_20261025.md`. The user now
prioritizes availability and throughput over residential purity. Six historical
entries were revalidated; the final measured run 40179946727 found four fully
usable, three short-term stable, and two exceeding 5 Mbps in both downloads.
No subscription was published and no Cloudflare or local network changes were
made. The residential-only publication gate remains intact.

Latest second-batch attempt: see `BATCH2_RESULT_20261025.md`. Residential-only
publication now requires explicit allocation evidence, all seven Proxycheck
flags false and a score of 0-25. All ten prior attempts (including failures)
are excluded and balanced selection is tested. Actions 40144734339 passed
actual detector health but hit ConnectTimeout fetching the official feed:
zero nodes scanned, no publication and no third batch. No Cloudflare or system
network resource was changed.

Latest real scan: see `NODE_SCAN_RESULT_20261025.md`. A bounded Actions-only Node
SSTP backend passed actual HTTP health checks and scanned ten candidates: six
authenticated repeated exits, two explicitly residential allocations, but all
six scored 100/100 and were flagged as public proxies. Zero qualified residential
exits and no subscription published. The scan's metadata parser failure was
fixed and its saved exits reviewed without another tunnel scan. Cloudflare
deployments and the user's current network remain untouched.

Latest discriminating test: see `PROBE_RESULT_20261025.md`. One new isolated
gate-checker-probe was created with a constant response, no imports or bindings.
Its first health request also returned 500/1101. No detector deployment or scan
followed. Technical support was not submitted: official Free support excludes
general technical cases, and the browser support-page attempt timed out. A
complete private draft is retained locally; no production resource was changed.

Latest read-only follow-up: see `CHECKER_RESEARCH_20261025.md`. Active version
unchanged; historical telemetry API returned 403, Analytics showed only one
earlier success, and no runtime stack was obtained. No repair deployment or scan
was performed. Test Pages remains 200/configured=true; test Worker remains 500.

Previous follow-up: reversible minimal/constant/classic Worker controls and full
restoration were performed on gate-checker-test only. All health requests still
returned 500/1101; no scan was allowed. Full details and version IDs are in
`CHECKER_DIAGNOSIS_20261025.md`. Final active version is
`30706388-c405-4f3d-8bb1-142065a7b563`; full test source and bindings restored.

## Follow-up diagnosis and target-country update

Baseline checked: `a3ec2a84b8bf4c62cd168f16166162a8003cfd54`; worktree initially clean.
No checker code/config changes or redeployment were made in this follow-up,
because no real exception stack was obtained. The health endpoint still
returned HTTP 500 during the live diagnostic session.

Existing CLI authorization successfully created a test-only tail session
(HTTP 200). With the existing process proxy unchanged, an undici WebSocket
connection opened; a health request returned HTTP 500, but no event or
exception arrived within 35 seconds. No actual stack or cause can be reported.
A ws transport variant encountered ECONNRESET. This is a log-delivery/connection
blocker, not demonstrated missing authorization. Session IDs, auth tokens,
WebSocket URLs, request headers and raw events are not saved in diagnostics.
The diagnostic script now captures only exception fields and connection state,
uses a bounded credential-read timeout, and closes its own tail session.
Latest sanitized local result: `diagnostics/checker-runtime.json`.

A focused browser attempt to open only the test Worker console timed out;
browser control was stopped without retrying the failed navigation.
A reliable Cloudflare console live-log/exception view is the remaining path
to obtain a stack. No additional account permission was requested: the tail
creation endpoint already authorized the existing credential.

Target countries are now configurable through `TARGET_COUNTRIES`, default
`US,JP,KR,SG`. Actual signed observed exit country must match both independent
metadata providers. Source country can prioritize candidates but never qualify
an exit. Publishing additionally requires complete boolean proxy/VPN/Tor/abuser
indicators with no positive flag; absent fields stay unknown and block publishing.
This is a conservative indicator gate, not proof of numerical low risk.
Residential ISP, datacenter, unknown, and numerical risk score remain separate.

The scanner itself now checks health before any candidate source fetch, in
addition to workflow preflight. Eight Python tests and five JavaScript tests
passed, including failed-health prevention, actual-country filtering and missing
risk evidence rejection. JavaScript syntax and diff whitespace checks passed.
No new workflow was dispatched, no candidate was scanned, and no result was
published. Qualified exits verified so far: 0; country/type/latency/risk results
remain unmeasured. Do not confuse zero scanned with absence of public candidates.

Outcome: independent resources created, but the first manual workflow FAILED
at the service preflight. This is not a working node/subscription deployment.

## Resources actually created

| Resource | Identifier / URL | Verified state |
| --- | --- | --- |
| GitHub repository | https://github.com/renatirudy246-maker/gate-test | Initial code pushed |
| Detection Worker | https://gate-checker-test.renatirudy246.workers.dev | Exists and workers.dev enabled; HTTP 500 / Cloudflare 1101 |
| Independent KV | EDGETUNNEL_TEST_KV / `9bd2a387ba5647acba9a3d27c5327444` | Created; contains `ADD.txt` only |
| Test Pages project | edgetunnel-test | Successfully deployed |
| Test Pages URL | https://edgetunnel-test-4pz.pages.dev | Health HTTP 200, configured=true |
| Test admin | https://edgetunnel-test-4pz.pages.dev/admin | Authenticated HTTP 200 from GitHub Runner |
| GitHub Pages | https://renatirudy246-maker.github.io/gate-test/ | Workflow source enabled, no result deployment published |

Pages production binding `KV` points to the new test namespace, not the
production namespace. Its independent ADMIN, KEY, UUID and SUB_TOKEN are Secret
bindings. GitHub Actions holds CHECK_TOKEN, TEST_ADMIN and TEST_SUB_TOKEN.
No credential values are recorded in source, this report, or diagnostics.

## First actual manual run

Run: https://github.com/renatirudy246-maker/gate-test/actions/runs/40132730979

- Time: 2026-10-25 05:06:19-05:06:29 Asia/Shanghai.
- Code: `ed2fda715092d5e04cf8ee7101f070d1576b09ac`.
- Dependency installation and five Python tests passed.
- Service preflight: checker HTTP 500; test Pages health HTTP 200;
  authenticated test ADMIN HTTP 200.
- Candidate scan was SKIPPED (0 nodes), so 0 actual exits were verified.
- Diagnostic artifact upload succeeded; retention is 1 day. A local copy is
  retained at `diagnostics/first-manual-run/preflight.json` (gitignored).
- Result artifact upload and GitHub Pages publication were SKIPPED.
- No nodes.txt, candidate risk scores, usable live subscription, latency,
  stability, or real US residential exit can be claimed.

Additional local validation: five JavaScript tests passed (authorization,
target allowlist, rate-limit gate, signed echo, local Clash-format conversion).
Pages bundling and JavaScript syntax checks passed. These do not establish
Cloudflare checker runtime correctness or live subscription correctness.

## Remaining blocker

The checker returns Cloudflare 1101 on its health endpoint, both locally and
from GitHub Runner. The exact runtime exception remains unknown. A limited
test-only tail attempt did not establish a connection and returned no exception
trace; no additional OAuth scopes were requested. Initial CLI/API activation
errors were resolved by enabling only this Worker's workers.dev endpoint.
Successful upload/activation is not treated as a healthy service.

Keep scanning and all schedules stopped. Next work should obtain a reliable
exception trace for this Worker and repair that specific failure, then rerun a
single manual test (at most ten candidates, concurrency at most two). Do not
broaden scans, upgrade the plan, or modify production to work around the failure.

## Safety / unchanged production

- No plan upgrade or paid service was requested.
- Production `yylo-vless` still has domains yylo-vless.pages.dev and yylo.ccwu.cc,
  and its KV binding still points to `yylo-vless-kv`.
- No production ADMIN, UUID, KEY, KV values, routes, domain binding, nameservers,
  subscription, or deployment was modified.
- No Windows proxy, DNS, route, VPN/TUN, NIC or Clash configuration was changed.
  Existing listeners 7897 and 17898 remain; no local proxy service was launched.
- Original audit-source hashes remain unchanged.
- No schedule was created. No test subscription was imported into Clash.
- Test resources consume shared free-account allowance; the ten-candidate cap
  and rate limiter are safeguards, not reserved account quota. Rate limiting
  is approximate per Cloudflare location and is not yet verified on the live
  failing checker.

## Changes / next use

The strict Python pipeline keeps unknown classifications and missing risk
fields explicit; requires signed observed IP and two metadata sources before
publication; fails with diagnostics on empty/unverified results. The checker
wrapper restricts targets, requires a Secret and adds request limiting. The
test edgetunnel wrapper uses a minimal local admin and local Clash conversion,
with no external subscription converter or random fallback nodes.

The subscription endpoint is `/sub` with an independent test Secret; the
authenticated admin download endpoint is `/admin/subscription`. Neither is
reported as a usable subscription until verified nodes exist. Test credentials
are not printed. If the owner wants a known test ADMIN, set a new Secret only on
the independent test Pages project in a separately authorized step.

Residential ISP metadata would not prove a home device, and a numerical
cleanliness/fraud score must not be invented from missing provider fields.
VPN Gate may log connections; future tests must use no sensitive traffic.
