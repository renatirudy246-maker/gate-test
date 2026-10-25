"""Produce credential-free evidence for the successfully published direct link."""
import csv
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT=Path(__file__).resolve().parent
URL='https://renatirudy246-maker.github.io/gate-test/clash-openvpn.yaml'

def main():
    paths=[ROOT/'reports/direct-openvpn-40184315423.json',ROOT/'reports/direct-openvpn-40185099871.json']
    documents=[json.loads(p.read_text()) for p in paths]
    by_ip={};seen=set()
    for document in documents:
        run_id=document['workflow_url'].split('/')[-1]
        raw=(ROOT/f'diagnostics/openvpn-{run_id}/run.json').read_bytes()
        if hashlib.sha256(raw).hexdigest()!=document['raw_run_sha256']:raise ValueError('Stored actual report hash mismatch')
        report=document['measurements']
        for node in report['results']:
            key=(node['host'],node['port'])
            if key in seen:raise ValueError('Repeated OpenVPN candidate across batches')
            seen.add(key)
            if not (node['success'] and node.get('short_term_stable') and node['min_download_mbps']>=3):continue
            if node['health']['http']!=200 or node['health']['configured'] is not True or len(node['downloads'])!=2 or len(node['observations'])!=2:raise ValueError('Invalid actual path evidence')
            if not all(o['ip']==node['exit_ip'] and o['certificate_verified'] is True for o in node['observations']):raise ValueError('Missing independent IP evidence')
            if not all(d['bytes']==1048576 and d['certificate_verified'] is True for d in node['downloads']):raise ValueError('Incomplete HTTPS download evidence')
            if node['exit_ip'] not in by_ip or node['min_download_mbps']>by_ip[node['exit_ip']][0]['min_download_mbps']:
                by_ip[node['exit_ip']]=(node,document['workflow_url'])
    selected=sorted(by_ip.values(),key=lambda pair:-pair[0]['min_download_mbps'])[:35]
    link=json.loads((ROOT/'diagnostics/openvpn-final-link-check.json').read_text())
    if link['nodes']!=len(selected) or set(documents[-1]['measurements']['selected_exits'])!={n['exit_ip'] for n,_ in selected}:raise ValueError('Published link does not match actual eligible exits')
    fields=['rank','protocol','host','port','actual_exit_ip','country','asn','isp','min_download_mbps','max_download_mbps','ttfb_ms','observed_at','long_term_stability','risk_status','workflow_url']
    with (ROOT/'reports/clash-direct-openvpn-20261025.csv').open('w',encoding='utf-8',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
        for rank,(node,url) in enumerate(selected,1):
            writer.writerow(dict(rank=rank,protocol='OpenVPN TCP',host=node['host'],port=node['port'],actual_exit_ip=node['exit_ip'],country=node['country'],asn=node.get('asn'),isp=node.get('isp'),min_download_mbps=round(node['min_download_mbps'],2),max_download_mbps=round(node['max_download_mbps'],2),ttfb_ms='/'.join(str(round(d['ttfb_ms'])) for d in node['downloads']),observed_at=node['finished_at'],long_term_stability='unknown',risk_status='not_rechecked',workflow_url=url))
    runs=[d['measurements'] for d in documents]
    total_bytes=sum(d['bytes'] for r in runs for n in r['results'] for d in n['downloads'])
    countries=dict(Counter(n['country'] for n,_ in selected));errors=Counter(n.get('error','speed_or_variation_gate') for r in runs for n in r['results'] if not(n['success'] and n.get('short_term_stable') and n['min_download_mbps']>=3))
    local=lambda value:datetime.fromisoformat(value.replace('Z','+00:00')).astimezone(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')
    text=['# 已发布的 Clash / Mihomo 直连 OpenVPN 订阅','',f'订阅地址：[{URL}]({URL})。',
          f'已实际下载检查：HTTP {link["http"]}，{link["nodes"]} 条节点，{link["bytes"]} 字节，SHA256 `{link["sha256"]}`。',
          f'最终选出 **{len(selected)} 条**，实际国家分布 **{countries}**。',
          f'两轮测量速度范围为 **{min(n["min_download_mbps"] for n,_ in selected):.2f}–{max(n["max_download_mbps"] for n,_ in selected):.2f} Mbps**，按较慢一轮的速度排序。',
          f'其中 **{sum(n["min_download_mbps"]>=5 for n,_ in selected)} 条**两轮均达到 5 Mbps。',
          f'北京时间测试区间：{local(min(r["started_at"] for r in runs))} 至 {local(max(r["finished_at"] for r in runs))}。','',
          '## 这次使用的路线','',
          'Clash Verge Rev / Mihomo → VPN Gate OpenVPN TCP 网关 → 真实出口。GitHub Pages 仅托管静态订阅，不中转流量。',
          '不依赖 edgetunnel 或 Cloudflare Worker/Pages；没有改动受限 Cloudflare 项目，没有通过另建项目规避限制。',
          '这些节点先前的 SSTP 测量只用于挑选候选，不能代替 OpenVPN 验证。此次从官方源提取公开 OpenVPN 配置，用固定官方核心 Mihomo v1.19.32 和 gVisor 用户态协议栈重新实测。',
          '公开文件中的客户端证书/key 来自 VPN Gate 官方公开分发的公共配置；没有使用、保存或泄露用户的 ADMIN、UUID、Cookie、订阅令牌或 Cloudflare/GitHub 认证凭据。','',
          '## 实际验证','',
          '- 下载的官方 Linux Mihomo 核心已校验 GitHub Release 提供的 SHA256。',
          '- 每条使用独立临时 Mihomo 进程；先检查实际 controller HTTP 200 和版本；连接/控制端口仅位于 Actions 隔离 Linux 的回环接口，并发最多 2。',
          '- ipwho.is 和 ipify 必须报告相同真实出口；Cloudflare trace 再交叉核对实际出口 IP 与国家。国家必须属于 US/JP/KR/SG/CA/AU。',
          '- 初始候选有既往已验证出口时，还要求与旧实测一致；未知旧出口不会用入口 IP 或广告国家代替。',
          '- 两轮各下载 1 MiB，间隔至少 20 秒；精确核对字节数，内层 HTTPS 验证 CA/域名；最后再次查询 ipify，要求出口不变。',
          '- 两轮均至少 3 Mbps、速度之比不超过 2 才发布。保留最快的 35 个不同实际出口。没有放宽失败节点的门槛。',
          '- Windows 上仅执行了现有 Mihomo 的 -v 和独立 -t 配置语法检查，没有运行代理监听、导入配置或切换网络。',
          '- **33 项 Python 测试通过**，本机 Mihomo v1.19.32 对最终下载订阅的语法检查通过。','',
          '|手动运行|实际候选|完整测试成功|发布作业|','|---|---|---|---|']
    for d in documents:
        r=d['measurements'];text.append(f'|[{d["workflow_url"].split("/")[-1]}]({d["workflow_url"]})|{r["checked"]}|{r["success"]}|成功|')
    text+=['',f'共检测 **{len(seen)} 个不重复入口**，成功完成整套测试 {sum(r["success"] for r in runs)} 个；满足速度与稳定性门槛的不同出口 {len(by_ip)} 个。',
           f'完成下载载荷 **{total_bytes/1048576:.0f} MiB**，不含 TLS/协议及查询开销；错误/未选原因：`{dict(errors)}`。',
           '来源与原始报告 digest 保存在 reports/direct-openvpn-*.json，最终出口/ASN/速度清单在 reports/clash-direct-openvpn-20261025.csv。','',
           '## 如何使用与限制','',
           '在 Clash Verge Rev 的“订阅”页选择新建/导入远程订阅，粘贴上面的 HTTPS 地址。等你决定使用时再手动启用；本次没有代你导入或切换现有订阅。',
           '需要支持 type: openvpn 的 Mihomo 核心。已只读确认本机稳定核心 v1.19.32，并对下载后的实际配置通过 -t 校验。',
           '订阅不包含 mixed-port、DNS、TUN、网卡、路由或外部控制器设置，策略组为 Gate Direct；当前只发布 TCP 代理配置，UDP 未测试/未启用。',
           '每个成功结果是在同一个 OpenVPN 会话内完成的 7 次 HTTPS 请求，不能称为 7 次独立 VPN 重连。早期报告中的 verified_sessions=6 是统计字段误名，已在源码修正并在原始报告旁明确解释。',
           '测速来自 GitHub Actions，小流量短时结果不能保证用户本地速度、长期在线率或持续带宽；HTTP 首字节时间不是 ICMP 或 Clash 延迟。',
           '公共志愿者节点可能下线；住宅属性未重新确认，风险未重新查询，不能保证纯净或低风险。仅连接测试，不用重要账号或敏感信息。',
           '没有启用自动更新或定时工作流，当前链接为手动验证后的静态快照。','',
           '## 改动与环境','',
           '实现提交：6ad4c29（首轮原生 OpenVPN 验证/发布），87dd5c3（剩余原候选补测/合并）。',
           '新增官方配置转换器、原生核心隔离验证器、手动 GitHub Pages 发布工作流、公共候选配置与相应测试。',
           'Cloudflare 生产与测试 Worker/Pages/KV、yylo.ccwu.cc、现有订阅和密钥没有更改。Windows 代理/DNS/路由/VPN/TUN/网卡和 Clash 配置没有更改。',
           '没有升级套餐、付费、安装系统级软件或申请额外权限。','',
           '[Mihomo OpenVPN 官方文档](https://wiki.metacubex.one/config/proxies/openvpn/)；[VPN Gate 官方 OpenVPN 说明](https://www.vpngate.net/en/howto_openvpn.aspx)。']
    if (ROOT/'reports/local-openvpn-diagnosis-20261025.json').exists():
        text[0]='# 历史海外 OpenVPN 实测：本机验收未通过'
        text[1:1]=['','**后续本机复测失败：这份 35 条快照不能作为当前网络的可用订阅推荐。详见 [本机诊断](LOCAL_OPENVPN_RESULT_20261025.md)。旧数据保留供审计，不能代替本机网页或稳定性验收。**','']
    (ROOT/'DIRECT_OPENVPN_RESULT_20261025.md').write_text('\n'.join(text)+'\n',encoding='utf-8')
    print(json.dumps({'selected':len(selected),'countries':countries,'all_candidates':len(seen),'all_complete':sum(r['success'] for r in runs),'eligible_distinct_exits':len(by_ip),'download_payload_mib':total_bytes/1048576}))

if __name__=='__main__':main()
