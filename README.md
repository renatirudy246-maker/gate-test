# gate-test: isolated manual SSTP experiment

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
