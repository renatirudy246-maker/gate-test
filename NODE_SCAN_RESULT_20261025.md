# 实际 SSTP 出口测试结果（2026-10-25）

本轮已恢复可执行的检测路径，并取得真实隧道出口：检测 10 个候选，6 个成功，
其中 2 个被独立数据源明确分类为住宅宽带分配。**低风险合格住宅出口仍为 0**：
这 2 个住宅候选均被识别为公开代理，风险评分 100/100，未发布订阅。

## 住宅候选的实际数据

| 实际出口 IP | 国家 / ASN / ISP | 分配类型证据 | 三次验证耗时 | 风险 |
| --- | --- | --- | --- | --- |
| 1.240.128.118 | KR / AS9318 / SK Broadband | Proxycheck Residential，hosting=false | 3238 / 3248 / 2935 ms | 100/100；proxy=true、anonymous=true |
| 110.13.26.111 | KR / AS9318 / SK Broadband | Proxycheck Residential，hosting=false | 2777 / 2706 / 2715 ms | 100/100；proxy=true、anonymous=true、scraper=true |

公共 VPN Gate 连接入口分别为：
- `vpn517964018.opengw.net:1323`，入口与实测出口 IP 相同。
- `vpn890613352.opengw.net:995`，入口 IP `1.253.137.231`，实测出口为
  `110.13.26.111`；没有将入口 IP 当作出口。

两者均通过用户态 SSTP/PPP 建立了三次独立连接；隧道内请求 `ipwho.is` 和
`api.ipify.org`，Node 原生 TLS 校验 CA 和域名，两个独立服务报告相同 IP，
第三次连接再次返回相同出口。两者在短时样本中均为 3/3 成功。
耗时包含 SSTP、PPP、内层 TLS、HTTP 请求，**不是 ICMP ping 或 Clash 延迟**。

北京时间实测窗口：
- 1.240.128.118：05:59:14–05:59:20；风险资料复核约 06:03:47。
- 110.13.26.111：05:59:27–05:59:33；风险资料复核约 06:03:53。

查询实际出口 IP 的三家资料源（ipwho.is、ipapi.is、Proxycheck）的国家与 ASN
全部一致。住宅分配类型来自 Proxycheck 的明确分类，**不是由节点名称、
主机名或 ISP 名称推断**。该分类仍可能误判，不能证明物理设备位于家庭中；
家庭设备、原生属性、长期固定性和纯净程度均未得到证实。

风险分值是 [Proxycheck 的服务评分](https://proxycheck.io/api/)，不是“100% 欺诈概率”。
公开代理识别足以使当前发布门槛失败。缺失的独立黑名单/攻击历史未解释成无记录，
也没有把这些出口称为低风险或纯净家宽。

## 全部成功出口

| 出口 IP | 国家 | ASN | 当前分类 | 风险评分 |
| --- | --- | --- | --- | --- |
| 221.71.146.229 | JP | 17676 | 未知（分配资料为 Business） | 100 |
| 219.100.37.239 | JP | 36599 | 机房（Hosting） | 100 |
| 1.240.128.118 | KR | 9318 | 住宅宽带候选 | 100 |
| 123.143.79.15 | KR | 3786 | 未知（Business） | 100 |
| 110.13.26.111 | KR | 9318 | 住宅宽带候选 | 100 |
| 182.220.175.195 | KR | 17858 | 未知（Business） | 100 |

另外 4 个候选分别出现 SSTP 连接超时、外层 TLS bad record type、连接超时和
SSTP socket closed；没有生成出口。实际候选总数 10、并发上限 2，没有第二批扫描。
本批没有验证到美国或新加坡出口；没有用其他地区名称替代。

## 实现和失败修复

Cloudflare Worker 的 1101 根因未修复，也没有再次部署 Worker 或 Pages。
改用现有公开测试仓库的 GitHub Actions 临时 Linux 运行器：

- `node-checker/` 复用上游的 SSTP/PPP/TCP 实现，适配 Node 出站套接字，
  只绑定运行器回环随机端口；代码拒绝在当前 Windows 电脑启动监听器。
- 健康检查实际返回 HTTP 200、configured=true 后才读取节点并扫描。
  服务身份、鉴权、10 个不同候选和并发 2 的限制均保留。
- 外层公共 VPN Gate TLS 允许其自签名证书；内层出口观测 HTTPS 强制 CA 和
  主机名校验，无直连回退，不发送测试认证令牌给出口服务。
- 原 Worker 的 HMAC 验证路径未放宽；Node 路径单独校验两家服务及重复观测。
- 工作流只有 `workflow_dispatch`，没有 schedule。

实测运行：[40136541061](https://github.com/renatirudy246-maker/gate-test/actions/runs/40136541061)，
代码提交 `9036876`。健康检查通过，10 个节点确已扫描。随后元数据解析出现
`AttributeError: 'str' object has no attribute 'get'`，导致工作流失败、发布跳过。

已定位到 ipapi.is 的匿名响应：`asn`、`company` 是字符串，且不提供风险标志。
[官方文档](https://ipapi.is/developers.html)确认了这个响应形态和无密钥限制。
修复了类型解析；缺失风险继续保持未知。新增无需密钥的 Proxycheck HTTPS
资料源，提供明确的分配类型、代理标志及数值风险，拒绝缺字段和高风险结果。
住宅分类收紧为明确 Residential 分配，不能仅凭消费 ISP 的 ASN 名称认定住宅。
使用 Proxycheck 作为风险依据时，要求完整负面标志为 false 且评分在 0–25；
任何资料源的阳性风险标志优先阻止发布。资料缺失不产生低风险结论。

`review_saved_exits.py` 对已保存的 6 个真实出口进行**元数据复核**，没有重连 VPN、
扩大候选或重跑扫描；结果为出口交叉验证 6、住宅候选 2、合格住宅 0。
复核仍未写 nodes.txt 或发布，原失败工作流没有被修改为成功。

新增/变更：手动 Node 工作流、`node-checker/`、`vpngate.py`、元数据复核脚本、
针对性测试及上游 SSTP 函数的命名导出；Cloudflare 部署未改变。
Python 12 项测试通过；Node 8 项测试通过；Node bundle 加载和手动工作流 YAML
检查通过。没有新增或升级依赖。

## 结果证据、费用和环境

可复核的脱敏证据：`reports/node-scan-40136541061.json`，含实际观测时间、出口、
提供商结果、原始运行文件 SHA-256 和复核时间；没有任何认证信息。
完整原始扫描及健康检查位于本地忽略目录
`diagnostics/node-scan-40136541061/`，资料复核位于 `diagnostics/node-exit-review.json`。

仅运行了一次公开仓库标准 Linux Actions 任务和有限的免费元数据查询。
没有 Cloudflare 新资源、部署或 KV 数据写入，没有付费或额外权限。
未修改生产 Worker/Pages/KV、yylo.ccwu.cc、生产密钥/订阅，以及当前 Windows
代理、DNS、路由、VPN/TUN、网卡或 Clash 配置。

低风险门槛未过，**没有可用的合格测试订阅，也没有导入或切换 Clash**。
未作长时间稳定性、全部公开黑名单和 Clash 端到端验证。
