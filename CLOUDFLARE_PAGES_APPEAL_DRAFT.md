# Cloudflare Pages review request — draft only, not sent

To: abusereply@cloudflare.com
Subject: Request review of blocked Pages project edgetunnel-test (API error 8000119)

Hello Cloudflare team,

Please review the block on my Pages project `edgetunnel-test` in account
`e5a0857508f37d031d9137c3ecec80e3`. The default hostname is
`edgetunnel-test-4pz.pages.dev`; it has no custom domain.

At approximately **2026-10-25 10:06:17–10:06:26 UTC**, the Pages deployment API
`POST /accounts/e5a0857508f37d031d9137c3ecec80e3/pages/projects/edgetunnel-test/deployments`
rejected an update with error **8000119**:

> Your Pages project has been blocked. Contact abusereply@cloudflare.com.

This is a separate test project on the Free plan. Its intended function is an
authenticated VLESS/WebSocket relay using selected public VPN Gate SSTP gateways,
with a private Clash subscription. It is not an anonymous public subscription;
credentials are kept in test secrets. Existing unrelated production services
have not been changed.

The last active deployment is `5e84ea9d-bd15-4f40-abe4-fa370d32cc57`, created
2026-10-24 21:02:21 UTC. A read-only project/deployment check after the rejection
confirmed that no new deployment became active.

Please explain the reason and scope of this block, review whether this intended
test use is permitted, and identify any compliance or remediation steps needed.
I have stopped deployment attempts and will not create alternate projects or
domains to evade the block. Please do not modify or remove unrelated projects.

No passwords, API tokens, UUID credentials, cookies or subscription access keys
are included in this message. Please use your authenticated support channel if
additional account verification is necessary.

Thank you.

---

本文件仅为供账户所有者核对、发送的草稿，没有自动发送邮件或支持工单。
封禁的具体原因和范围尚未知；不要推测它只影响代码、整个账户或其他项目。
