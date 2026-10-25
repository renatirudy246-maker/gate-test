# Clash 订阅制作结果：代码完成，部署被平台封禁拦截

**目前没有可交付为已验证可用的 Clash 订阅链接。**

已把此前实测的 35 条性能候选整理为独立测试订阅生成器，完成本地检查。
Cloudflare 在正式部署时返回明确拒绝：

```text
Your Pages project has been blocked. Contact abusereply@cloudflare.com.
code: 8000119
```

API：`POST /accounts/e5a0857508f37d031d9137c3ecec80e3/pages/projects/edgetunnel-test/deployments`。
时间：北京时间 2026-10-25 18:06:17–18:06:26（UTC 10:06:17–10:06:26）。
具体封禁原因及范围未知。收到明确拒绝后，已停止所有 Cloudflare 写操作；没有创建
其他项目、Worker 或域名来绕过限制，也没有发送申诉。

## 已完成

- 从保存的真实隧道/HTTPS 观测中导出 35 条独立出口，重新校验两家独立 IP 来源、
  证书标记、两轮完整下载、最终重连和去重；文件为
  `workers/edgetunnel/verified-nodes.json`，不包含私有凭据。
- 独立适配器支持 35 条 VLESS + WebSocket + TLS 节点，在测试服务内完成转换，
  不经过第三方转换服务，不使用随机或静态示例节点。
- WebSocket 上游仅允许这 35 条实测 SSTP host+port；复用之前已验证的 TCP
  去重/乱序接收实现和窗口设置，禁止直接连接回退。
- 增加仅手动触发的 Linux Actions 订阅链路验证器；不保存订阅正文、UUID、
  WebSocket 路径或认证头。初始独立出口均失败时停止后续检查。
- **29 项 Python + 22 项 Node 测试通过**；Pages bundle 构建及差异检查通过。
- 实现提交：`1ee685cac7fd0ccd0d2bf96952d843b0b0fb6d2b`。

## 实际远端状态

部署前再次确认：账户 `e5a0857508f37d031d9137c3ecec80e3`，项目 `edgetunnel-test`，
唯一域名 `edgetunnel-test-4pz.pages.dev`，KV 绑定
`9bd2a387ba5647acba9a3d27c5327444`（EDGETUNNEL_TEST_KV）。

第一次部署命令异常退出，没有激活新版本；安全日志仅记录到上传阶段。
只读检查确认没有产生新部署后，用正常错误级别重试同一实现一次，取得上述
8000119 拒绝。没有继续重试。

拒绝后只读确认，活动部署仍是 **5e84ea9d-bd15-4f40-abe4-fa370d32cc57**，
创建于 2026-10-24 21:02:21 UTC。无需回滚，因为新代码从未激活。
原有健康页不代表新 35 条订阅已经上线。

新增了一个独立测试 Pages Secret `IMPORT_TOKEN`，用于将新链接与原测试订阅
令牌分开；其值未输出、落盘或提交。它尚未被活动代码使用。
尝试同步到 Actions 新 Secret 时，该子进程没有可用 GitHub 授权；名字清单复查
确认并未创建 `TEST_IMPORT_TOKEN`，原 CHECK_TOKEN、TEST_ADMIN、TEST_SUB_TOKEN 保持原样。
没有修改已有 ADMIN、KEY、UUID、SUB_TOKEN 的值。

没有运行远端订阅链路验证工作流，没有重新扫描 VPN Gate，也没有将格式检查
写成真实出口链路测试成功。没有生成或传播带凭据的公开订阅文件。

## 下一步与边界

封禁需由账户所有者向 Cloudflare 核实并申诉。无凭据草稿见
[申诉草稿](CLOUDFLARE_PAGES_APPEAL_DRAFT.md)。等待官方确认可继续使用该服务后，
再部署测试版、确认新健康配置、实际测试 WSS → SSTP → HTTPS 出口，最后交付链接。

生产 yylo-vless、yylo.ccwu.cc、生产 KV/密钥/订阅及部署未修改。
Windows 系统代理、DNS、路由、VPN/TUN、网卡和现有 Clash 配置均未修改。
没有套餐升级、付费、系统软件安装或定时任务。Cloudflare gate-checker-test 未修改。

可回滚代码检查点为 `2e513fb`；项目活动部署保持原版本。
本地 `diagnostics/subscription/` 保存了仅含名字/类型/绑定 ID 的前后部署元数据，
没有保存 Cloudflare 密钥或新订阅令牌。
