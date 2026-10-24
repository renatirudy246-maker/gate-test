# 检测 Worker 后续只读调查（2026-10-25，Asia/Shanghai）

结论：根因仍未知；没有足够证据支持一次具体修复部署。本轮没有部署、
切换 workers.dev、修改绑定或运行节点扫描。没有重复此前的最小化实验。

## 新取得的实际证据

| 检查 | 实际结果 |
| --- | --- |
| 当前活动部署 | `79e39d26-025c-44d9-8893-d526456cfc1a` |
| 活动版本 | `30706388-c405-4f3d-8bb1-142065a7b563`，100% |
| 活动版本运行时 | compatibility_date `2026-10-24`，usage_model `standard`，handler `fetch` |
| 绑定名称/类型 | `CHECK_LIMITER` / ratelimit；`CHECK_TOKEN` / secret_text；未输出或保存值 |
| 账户默认子域名 | `renatirudy246`，与请求地址一致 |
| 测试 Worker 映射 | workers.dev enabled=true；previews_enabled=false；未列出该服务的自定义域名 |
| 服务环境 | API 默认环境名 `production`，脚本名 `gate-checker-test`；这是测试 Worker 的默认环境标签，不是现有生产 Pages |
| 05:36:23 健康请求 | HTTP 500 / 1101；Ray `a4fc1de269f8f831-NRT` |
| 05:39:15 官方 CLI 日志诊断中的请求 | HTTP 500；Ray `a4fc22191faa25f8-NRT` |
| 测试 Pages 对照 | 05:36:24 HTTP 200、service=edgetunnel-test、configured=true；同为 NRT |

当前 Pages 项目 `edgetunnel-test` 的部署
`5e84ea9d-bd15-4f40-abe4-fa370d32cc57` 状态 success。
仅有 `edgetunnel-test-4pz.pages.dev` 域名；配置兼容日期同为 `2026-10-24`，
flags 为空；读取时只保留变量名称和 KV 绑定名称。该结果说明现有网络路径
能够访问这个 Pages 函数，不能证明独立 Worker 的执行路径正常。

## 日志、指标及请求追踪

1. 现有 OAuth 可读取部署、版本、服务元数据、workers.dev 映射和 GraphQL Analytics。
2. 对测试脚本查询 `workersInvocationsAdaptive`，时间范围为
   `2026-10-24T21:00:00Z` 至查询时刻：只返回一条
   `2026-10-24T21:00:55Z`、status=success、requests=1、errors=0。
   第二次增加时间维度后仍是这条记录，没有报告后续错误。
   这与多次 HTTP 500 存在差异，但该数据集可能采样、延迟，不能据此断言请求
   没有进入 Worker，或断言是路由/平台故障。
3. 针对旧 Ray `a4fc1326bfed58bf`、21:27–21:31 UTC 的历史遥测查询，
   使用 `dry=true`、精确测试脚本过滤、最多 20 条事件；返回
   **HTTP 403，code=10000，Authentication error**。没有扩大 OAuth 权限。
   官方文档列出的查询接口权限是 Workers Observability Write；
   此次凭据的有效权限不足以完成这个端点的查询，不能把 403 当作没有异常。
4. 为排除自写 WebSocket 客户端的差异，另外使用现有官方 Wrangler 4.152.0
   `tail gate-checker-test --format=json --config=workers/checker/wrangler.jsonc`。
   API 新建会话数量 1；探测返回 500；没有取得可解析异常事件或堆栈。
   本次 JSON 模式没有确认 WebSocket 已连通，因此不能把它当作“运行时无异常”的证据。
   官方 CLI 已终止，所创建的临时会话删除返回 200；没有遗留该命令的 Node tail 进程。
5. 当前配置未启用持久 Workers Logs。实时 tail 不回放历史请求；
   Ray 是关联标识，不是凭现有授权即可下载的异常堆栈。
   Rules Trace 属于请求规则模拟，也不能替代旧请求的 JavaScript 运行栈。

## 官方资料核对

- [Workers errors](https://developers.cloudflare.com/workers/observability/errors/)：
  1101 表示 JavaScript 异常，也包含无法返回响应的未完成 Promise 等情况；
  路由失败和免费请求额度耗尽分别另列为 1022、1027。
  当前错误页没有提供可定位文件行号的栈，不能直接定位某一模块或绑定。
- [实时日志](https://developers.cloudflare.com/workers/observability/logs/real-time-logs/)：
  tail 可捕获调用及异常；实时日志本身不存储历史日志。
- [历史遥测查询接口](https://developers.cloudflare.com/api/resources/workers/subresources/observability/subresources/telemetry/methods/query/)：
  核对了请求字段、dry 模式及所需权限。
- [Workers 指标查询](https://developers.cloudflare.com/analytics/graphql-api/tutorials/querying-workers-metrics/)
  与[数据集采样说明](https://developers.cloudflare.com/analytics/graphql-api/features/data-sets/)：
  指标可提供调用状态，不能直接给出某条 Ray 的堆栈。
- [Cloudflare 状态页](https://www.cloudflarestatus.com/)：查询时显示 No known service issues。
  [最近 Workflows 事件](https://www.cloudflarestatus.com/incidents/pij2josz3rvz)
  在 10 月 24 日 13:57 UTC 已解决，早于本次约 21:00–21:39 UTC 的问题窗口，
  且影响服务为 Workflows；没有证据把两者关联。

## 判断和停止原因

已重新阅读入口、上游模块头尾、运行时配置和前次实验记录。
健康路由不执行 SSTP 检测；先前纯静态、无导入/绑定、旧兼容日期和 classic
入口都曾失败，但本轮没有重做这些实验。
部署元数据与预期一致；Pages 对照正常；现有指标与失败请求不能直接对应；
历史日志 API 被拒绝；没有真实异常栈。因此尚不能在应用代码、部署/执行、
请求路由和平台问题之间作出可靠归因。

没有根据去修改某个模块、绑定或兼容日期；未使用获准的一次修复部署额度。
后续需要 Cloudflare 侧将 Ray、UTC 时间及活动版本关联到内部执行/路由记录，
或提供可读取的对应运行栈。已在本地忽略目录
`diagnostics/CLOUDFLARE_SUPPORT_DRAFT.md` 整理不含凭据的草稿，**未发送**。
没有请求用户重新登录或必须手动打开控制台；也未申请额外权限。

## 修改、验证及资源消耗

- 新增 `research-checker.mjs`：固定测试目标，只读元数据、精确脚本指标、
  dry 历史遥测查询；响应按字段白名单保存，认证信息仅在内存。
- 新增 `research-tail.mjs`：使用官方 CLI 的一次限时日志诊断；只输出筛选后的
  异常字段，原始子进程输出不落盘。后续完善分块 JSON 解析并通过语法检查，
  没有为此再次连接或触发探测。
- 两个脚本 `node --check` 通过；Git whitespace 检查通过。
  运行时代码及筛选逻辑未修改，未重复运行与文档/诊断脚本无关的单元测试。
- 新健康探测：测试 Worker 2 次，测试 Pages 1 次；历史指标查询 2 次；
  历史遥测查询 1 次；瞬时 tail 会话 1 个并已关闭。
  另有少量只读部署元数据和公开文档/状态查询；没有据此宣称账户剩余额度。
- 没有 KV 数据读写命令、Actions 执行、节点抓取、扫描或发布；扫描候选 0，
  合格普通出口 0，合格住宅出口 0。IP、国家、延迟、住宅属性和风险评分均无实测值。
- 当前扫描限制仍为最多 10 个候选、并发最多 2，目标为 US/JP/KR/SG；
  必须先 /health=200 且 configured=true，未知住宅/风险状态不能改标为合格。
- 未修改生产资源、密钥、域名、订阅或系统网络；未付费、增加资源或启用定时更新。

本地原始证据位置（被 Git 忽略，未提交）：
`diagnostics/research-before/`、`research-routing.json`、`research-readonly.json`、
`research-telemetry.json`、`research-official-tail.json`。
