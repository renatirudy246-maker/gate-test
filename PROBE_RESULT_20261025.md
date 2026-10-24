# 独立新 Worker 区分测试结果

日期：2026-10-25（Asia/Shanghai）。分支 B：新 Worker 的固定响应程序也返回 1101。

## 实际执行

1. 创建前，Cloudflare API 列出账户现有独立 Worker 数为 1；
   `gate-checker-probe` 名称未被占用，账户 workers.dev 子域名符合预期。
   [官方 Free 限制](https://developers.cloudflare.com/workers/platform/limits/)
   为每账户最多 100 个 Worker，因此本次没有碰到 Worker 数量上限。
   继续使用用户已确认的 Free 套餐，未开通收费功能。
2. 创建并部署唯一的新 Worker：
   `https://gate-checker-probe.renatirudy246.workers.dev`。
   源码仅返回固定 JSON HTTP 200，不导入模块，不使用绑定、密钥或外部请求。
3. 上传和激活成功：
   - 版本 `5349d28a-1304-49c6-80f5-5245db8d33f1`，100%。
   - 部署 `5dbacdcf-2835-4638-9c25-5df4db1b01b3`。
   - 兼容日期 `2026-10-24`，handler `fetch`，绑定列表为空。
   - workers.dev enabled=true，Version URLs disabled；无自定义域名配置。
4. 首次请求 `/health`：**HTTP 500 / Cloudflare 1101**。
   - UTC：`2026-10-24 21:47:56`；北京时间：`2026-10-25 05:47:56`。
   - Ray：`a4fc2ecdbd2e8be0-NRT`。
   - 与源码预期的固定 200 不符，未收到程序所定义的 JSON。

没有再创建 Worker、重复部署或更改映射。没有部署正式检测程序；
不需要执行恢复部署，探针保留为无密钥、无绑定的固定响应程序。
本轮实际部署次数 **1/3**，新 Worker **1/1**，扫描 **0/1**。
部署前 Git 检查点为 `d492114`；原 Worker 的代码和版本保持原状。

## 结论边界

新名称、独立无绑定的 Worker 也出现相同错误，进一步削弱了原检测代码或
原 Worker 单独损坏这一解释，但不足以确认具体平台、账户、路由或执行根因。
仍无真实异常堆栈。没有据此修改原 Worker 或生产配置。

创建前后原 `gate-checker-test` 活动版本均为
`30706388-c405-4f3d-8bb1-142065a7b563`，100%，未变更。

## 技术支持状态

**未提交工单，无工单编号。**

[Cloudflare 官方支持规则](https://developers.cloudflare.com/support/contacting-cloudflare-support/)
明确：Free 用户仅可就 billing、account、registrar 问题提交标准工单，
一般技术支持工单不在可用范围。本问题没有改投账单等不相符类别。
现有 Wrangler 没有技术工单提交命令，也没有发现可用的 Cloudflare 工单连接器。

额外尝试通过已有 Chrome 会话打开官方 Support 链接，浏览器工具返回
`js execution timed out; kernel reset, rerun your request`。未确认支持页面是否打开，
没有重试、操作认证流程或假定登录失败。因此，套餐限制依据官方文档；
当前账户支持页面的实际控件状态未能验证。

完整英文工单草稿保存在本地被 Git 忽略的
`diagnostics/probe/CLOUDFLARE_SUPPORT_DRAFT.md`，包含账户标识、两套 Worker 的
活动版本、UTC、Ray、最小源码、预期/实测差异及关联内部日志的明确请求。
没有 Secret、Cookie、认证头、管理员凭据或订阅令牌。未公开草稿、未发社区帖、
未升级套餐、未索取新授权。后续需要可用且有权限的 Cloudflare 技术支持渠道。

## 节点和环境结果

健康检查未过，正式检测程序和手动工作流均未启动。
候选扫描 0；实测合格住宅出口 0；合格普通出口 0。
没有出口 IP、国家、住宅类型、延迟或风险评分的新增实测结果。
US/JP/KR/SG、10 候选、并发 2 和现有发布门槛均未改变。

本轮只新增探针源码、独立 Wrangler 配置、固定目标证据脚本及此报告，
并更新部署报告。两个新 JS 文件语法检查及 Git whitespace 检查通过。
诊断证据保存在 `diagnostics/probe/{preflight,health,snapshot}.json`，未提交到 Git。

没有运行 KV 数据读写、GitHub Actions 或节点抓取；仅一次探针健康请求和少量
管理 API 查询。没有修改现有生产 Pages、Worker、KV、域名、密钥、订阅或
Windows 代理/DNS/路由/VPN/TUN/网卡/Clash 配置。
