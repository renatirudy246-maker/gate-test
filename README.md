# gate-test: independent VPN Gate tests

## Local acceptance FAILED — current status

**Do not treat the published 35-node snapshot as usable on the user's network.**
Only 11/35 gateways completed a 5-second local TCP probe. Four locally timed-out
entrances remained reachable from GitHub Linux in 111–131 ms. The remote-runner
ranking therefore does not establish local reachability.

The original profiles also lacked per-node remote DNS, and local Google
resolution differed from authenticated DoH. Enabling only the temporary node's
remote resolver let one Korean exit load Google/Bing in 625/749 ms, but its
fresh-session recheck failed. **Zero stable locally recommended exits remain.**
No new "fixed" subscription was published. The original public file is retained
as a historical snapshot, not a current local-use recommendation. Remote-only
automatic publication has been removed. Per-node resolver settings are corrected
for future test configs, and a separate local publisher refuses publication
without both browsing verification and a successful fresh-session recheck.

See [local diagnosis](LOCAL_OPENVPN_RESULT_20261025.md). The user's production
subscription, Windows DNS/routes/TUN, protected ports and active Clash settings
were not changed. All our temporary diagnostic core processes were stopped.

## Historical overseas-verified OpenVPN snapshot — 2026-10-25

[Clash / Mihomo subscription](https://renatirudy246-maker.github.io/gate-test/clash-openvpn.yaml)

**35 independently observed exits: 16 Japan, 19 South Korea.** Two manual
Actions runs tested 58 distinct OpenVPN entrances; 44 completed all checks and
36 met the current speed/stability gate. The fastest 35 distinct exits are
published. Each was checked through native Mihomo v1.19.32 using ipwho.is,
ipify, Cloudflare trace and two 1-MiB HTTPS downloads at least 20 seconds apart.
29 selected exits exceeded 5 Mbps in both rounds. Long-term stability and
current reputation remain unknown.

Mihomo connects directly to the public VPN Gate OpenVPN TCP gateway. GitHub
Pages only hosts this static configuration; no Cloudflare relay is involved.
The download contains publicly distributed VPN Gate client certificates/keys
from the official source, **no private user or Cloudflare credentials**.
It includes no DNS, TUN, interface, mixed-port or controller settings.
The published download passed the user's installed Mihomo v1.19.32 `-t` check.
Nothing was imported into or activated in the existing Clash setup.

See [actual measurements and limits](DIRECT_OPENVPN_RESULT_20261025.md) and
[selected exits CSV](reports/clash-direct-openvpn-20261025.csv).
The Cloudflare test project remains blocked; it was not redeployed or replaced.
Updates are manual only, without any schedule.

## Earlier SSTP / residential-only experiment

The following records describe the original stricter pipeline. They do not
describe the independent OpenVPN performance subscription above.

This repository owns only `gate-checker-test`, Pages project `edgetunnel-test`,
KV `EDGETUNNEL_TEST_KV`, and this repository's GitHub Pages/Actions resources.
No production resources or local proxy settings are managed here.

- Manual dispatch only; **no cron**. Maximum 10 candidates, concurrency 2.
- `TARGET_COUNTRIES` is configurable via a repository variable, default
  `US,JP,KR,SG`. Only the authenticated observed exit country, crosschecked
  against both metadata providers, controls eligibility. Advertised entry
  country only prioritizes candidates and cannot qualify an exit.
- Both workflow and standalone scanner block before scanning unless checker
  health is HTTP 200 with service identity and `configured=true`.
- Publication also requires complete boolean proxy/VPN/Tor/abuser indicators
  with none flagged. Missing risk data remains unknown and cannot qualify.
  `no_flags_reported` is not a numerical low-risk or cleanliness guarantee.
- HTTPS official VPN Gate CSV supplies candidates. TCP OpenVPN ports are not
  assumed to support SSTP: actual SSTP/PPP and tunneled TCP must succeed.
- Checker requires a Bearer Secret and accepts only public VPN Gate hostnames
  with public `vpn:vpn` credentials. Native rate limiting is 10/minute per colo;
  it is approximate, not a global account quota reservation.
- Exit IP is observed by our Cloudflare echo through the SSTP tunnel. A fresh
  nonce and HMAC authenticate the response despite upstream userspace TLS lacking
  certificate-chain validation. IP geolocation/ASN is crosschecked against
  ipwho.is and ipapi.is over normal validated HTTPS.
- Residential, datacenter and unknown are distinct. Residential means a
  **consumer ISP candidate**, never proof of a home device or clean IP. Missing
  abuse/hosting fields remain null. No numeric fraud score is invented.
- All failed checks, missing exit evidence, metadata disagreement, or empty
  output fail the workflow. Failure diagnostics have 1-day retention. Pages
  publication requires the successful check job. A failed later run does not
  refresh an existing previously successful Pages deployment.
- edgetunnel uses independent secrets and KV. Its minimal admin UI and Clash
  conversion run locally in the Worker. External converters are disabled.
  It refuses to generate subscriptions without a nonempty verified node list.
  No subscription is imported into Clash and no local listener is started.

Secrets exist only in Cloudflare Secret bindings and GitHub Actions Secrets.
`CHECK_TOKEN` is shared by this checker and this repository; `TEST_ADMIN` and
`TEST_SUB_TOKEN` refer only to the independent Pages instance. Do not print them.
CLI OAuth is encrypted with an OS-keychain key, separate from application secrets.

## Validation

```text
python -m unittest discover -s tests
node --test tests/workers.test.mjs
node build.mjs
```

Workflow: **Manual bounded SSTP test**. Results are not a guarantee of current
availability. Repeated stability, speed, household provenance and IP cleanliness
require further evidence. VPN Gate may log sessions: use no important accounts
or sensitive traffic.

## Source provenance

- gate: `hezhanleiok/gate@4ff9b273cba0c02fb413444f1a515f2dd0e75cb5`
- checker: `lsh8848/cm-Workers-CheckSocks5@2f31cf9a242444eb22905d888d4d8871b0625b3a`
  (GPL-3.0 license retained in `workers/checker/LICENSE`)
- edgetunnel: `cmliu/edgetunnel@a8ab11125ece9bc27983f609a6359be81b21050c`
  (upstream license retained in `workers/edgetunnel/LICENSE`)

Test changes: restricted entry wrappers, signed exit echo, strict Python
pipeline and diagnostics, disabled external conversion/random endpoints,
minimal admin, local Clash conversion. Upstream's unused trailing comment
padding was omitted from the test copy. Original audit copies are unchanged.
