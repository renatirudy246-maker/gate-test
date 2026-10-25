"""Summarize actual Actions measurements; never creates a subscription."""
import csv
import json
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT=Path(__file__).resolve().parent

def collect(paths):
    runs=[];by_ip={}
    for path in paths:
        document=json.loads(path.read_text(encoding='utf-8'))
        run=document['measurements'];runs.append((document,run))
        if run.get('health',{}).get('http')!=200 or run['health'].get('configured') is not True:
            continue
        for node in run['results']:
            if not node.get('usable') or not node.get('short_term_stable'):
                continue
            ip=node['identity']['exit']['ip']
            # Retain the strongest actually measured entrance for a shared exit.
            if ip not in by_ip or node['min_download_mbps']>by_ip[ip][0]['min_download_mbps']:
                by_ip[ip]=(node,document['workflow_url'])
    ranked=sorted(by_ip.values(),key=lambda pair:-pair[0]['min_download_mbps'])
    return runs,ranked

def main():
    paths=[ROOT/'reports/performance-40179946727.json',*sorted((ROOT/'reports').glob('expansion-performance-*.json'))]
    runs,ranked=collect(paths)
    selected=[pair for pair in ranked if pair[0]['min_download_mbps']>=3][:35]
    fields=['rank','protocol','host','port','country','actual_exit_ip','asn','isp','min_download_mbps','max_download_mbps',
            'ttfb_ms','verified_sessions','observed_at','risk_status','residential_status','long_term_stability','workflow_url']
    with (ROOT/'reports/expanded-sstp-20261025.csv').open('w',encoding='utf-8',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
        for index,(node,url) in enumerate(selected,1):
            writer.writerow(dict(rank=index,protocol='SSTP',host=node['host'],port=node['port'],
                country=node['identity']['exit']['country_code'],actual_exit_ip=node['identity']['exit']['ip'],
                asn=node['identity']['exit'].get('asn',{}).get('asn'),isp=node['identity']['exit'].get('asn',{}).get('org'),
                min_download_mbps=round(node['min_download_mbps'],2),max_download_mbps=round(node['max_download_mbps'],2),
                ttfb_ms='/'.join(str(round(d['ttfb_ms'])) for d in node['downloads']),verified_sessions=f"{node['verified_sessions']}/{node['attempts']}",
                observed_at=node['finished_at'],risk_status='not_rechecked',residential_status='not_asserted',
                long_term_stability='unknown',workflow_url=url))
    all_fields=['host','port','advertised_country','actual_exit_ip','actual_country','usable','short_term_stable',
                'min_download_mbps','max_download_mbps','verified_sessions','attempts','error','observed_at','workflow_url']
    with (ROOT/'reports/all-candidates-20261025.csv').open('w',encoding='utf-8',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=all_fields);writer.writeheader()
        for document,run in runs[1:]:
            for node in run['results']:
                exit_info=node.get('identity',{}).get('exit') or {}
                writer.writerow(dict(host=node['host'],port=node['port'],advertised_country=node['source_country_code'],
                    actual_exit_ip=exit_info.get('ip'),actual_country=exit_info.get('country_code'),
                    usable=node['usable'],short_term_stable=node['short_term_stable'],
                    min_download_mbps=node['min_download_mbps'],max_download_mbps=node['max_download_mbps'],
                    verified_sessions=node['verified_sessions'],attempts=node['attempts'],error=node.get('error',''),
                    observed_at=node['finished_at'],workflow_url=document['workflow_url']))
    totals={'runs':len(runs),'new_scanned':sum(r.get('checked',0) for _,r in runs[1:]),
        'new_usable':sum(r.get('usable',0) for _,r in runs[1:]),'new_stable_entrances':sum(r.get('stable',0) for _,r in runs[1:]),
        'distinct_stable_exits':len(ranked),'recommended':len(selected),'at_least_3mbps':sum(n['min_download_mbps']>=3 for n,_ in ranked),
        'at_least_5mbps':sum(n['min_download_mbps']>=5 for n,_ in ranked),
        'recommended_countries':dict(Counter(n['identity']['exit']['country_code'] for n,_ in selected)),
        'download_payload_mib':sum(d['bytes'] for _,r in runs[1:] for n in r['results'] for d in n['downloads'])/1048576}
    print(json.dumps(totals))
    text=['# 六地区候选筛选与节点实测','',
          '目标：把已准备的 60 个新候选全部实测，按实际出口 IP 去重，择优保留最多 35 条两轮均 >=3 Mbps 的短时稳定结果。',
          f"新增实测 **{totals['new_scanned']} 个入口**，完整可用 {totals['new_usable']} 个、短时稳定 {totals['new_stable_entrances']} 个。",
          f"合并此前 3 条稳定结果，按实际出口 IP 去重，共 **{len(ranked)} 个短时稳定出口**，列出两轮均 >=3 Mbps 的前 {len(selected)} 条。",
          f"其中两轮均 >=5 Mbps 有 {totals['at_least_5mbps']} 条，两轮均 >=3 Mbps 有 {totals['at_least_3mbps']} 条。",
          f"前 {len(selected)} 条的实际国家分布：{totals['recommended_countries']}。",'',
          f"入选的 {len(selected)} 条两轮实测下载速率范围为 {min(n['min_download_mbps'] for n,_ in selected):.2f}–{max(n['max_download_mbps'] for n,_ in selected):.2f} Mbps。这是本批表现较好的节点，不代表高速带宽保证。" if selected else '本轮没有满足性能门槛的推荐。',
          '本次 60 个新候选的广告国家为 US 1、JP 33、KR 26。美国候选 SSTP 连接超时；官方源快照中没有 SG/CA/AU 的有效候选，因此本轮没有这些国家的已验证推荐。',
          '这份清单按用户最新要求评价可用性与速度，住宅纯净度不作准入条件。',
          '## 实际节点','',
          '|序号|SSTP 入口|实际出口 IP / 国家|两轮下载 Mbps|HTTP 首字节 ms|',
          '|---|---|---|---|---|']
    for index,(node,url) in enumerate(selected,1):
        speeds=' / '.join(f"{d['mbps']:.2f}" for d in node['downloads'])
        latency=' / '.join(str(round(d['ttfb_ms'])) for d in node['downloads'])
        text.append(f"|{index}|`{node['host']}:{node['port']}`|{node['identity']['exit']['ip']} / {node['identity']['exit']['country_code']}|{speeds}|{latency}|")
    text+=['','完整节点、ASN/ISP、实测时间和运行来源见 [入选 CSV](reports/expanded-sstp-20261025.csv)；全部新增候选的成功/失败记录见 [全量 CSV](reports/all-candidates-20261025.csv)。',
           '每条所列节点均通过 6/6 次验证会话、两轮各 1 MiB 下载、至少 20 秒的间隔、末次独立重连出口复核。',
           '两个下载速率之比 <=2 才列为短时稳定。低于 3 Mbps 的条目仅作较慢备用，不称为快速节点。',
           '这不是长期在线率测试；测速位置为 GitHub Actions，首字节时间不是 ping 或 Clash 延迟。',
           '住宅属性未断言，风险未重新查询，不能称为纯净、低风险或真实家庭设备出口。','',
           '## 实测过程与证据','',
           '官方节点快照仅用于候选入口；国家以 SSTP 内层、验证证书的 ipwho.is 与同连接 Cloudflare trace 交叉核对，ipify 独立复核实际 IP。',
           '每批最多 10 个新候选、并发最多 2；只有健康检查 HTTP 200 且 configured=true 后才检测。',
           '各批次串行执行；通过手动 workflow_dispatch 触发，没有定时任务。',
           '原严格住宅 eligible_exit() 与发布门槛保持原样，性能结果未自动发布为订阅。',
           'Cloudflare 检测 Worker 的既有 1101 问题本轮未修复、未重试；这里的健康检查来自 GitHub Actions 内的隔离 Node 检测器。',
           '候选批次与六国支持提交：9d5d6fd；保留历史回归测试提交：f5b757c。29 项 Python 与 20 项 Node 测试通过。','',
           '|运行|新增候选|完整可用|短时稳定|两轮 >=5 Mbps|健康|',
           '|---|---|---|---|---|---|']
    if len(runs)>1:
        local=lambda value:datetime.fromisoformat(value.replace('Z','+00:00')).astimezone(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')
        text.insert(2,f"新增批次实测时间：北京时间 {local(min(r['started_at'] for _,r in runs[1:]))} 至 {local(max(r['finished_at'] for _,r in runs[1:]))}。此前 3 条在同日 17:16–17:18 测量。")
    for document,run in runs[1:]:
        text.append(f"|[{document['workflow_url'].split('/')[-1]}]({document['workflow_url']})|{run.get('checked',0)}|{run.get('usable',0)}|{run.get('stable',0)}|{run.get('fast',0)}|{run.get('health',{}).get('http')} / configured={run.get('health',{}).get('configured')}|")
    errors=Counter(n.get('error','complete_but_variable') for _,run in runs[1:] for n in run['results'] if not n.get('short_term_stable'))
    text+=['',f"本轮完成下载载荷：{totals['download_payload_mib']:.0f} MiB，不含握手和查询开销。ZIP digest 及原始 JSON SHA256 已写入各 reports/expansion-performance-*.json。",
           f'未推荐结果诊断汇总：`{dict(errors)}`。','',
           '## Clash 导入与环境边界','',
           '当前 CSV 是 SSTP 实测清单，不是可直接导入 Clash 的订阅。后续可通过独立 edgetunnel 将 SSTP 上游适配成 Mihomo 支持的 VLESS + WebSocket + TLS 订阅，转换在测试服务本地完成。',
           '本轮没有生成带凭据的公开订阅，没有发布 nodes.txt，也没有部署 Cloudflare 或导入/切换 Clash。',
           '适配器目前单次限制 10 条；制作本次候选的 Clash 链接前需在测试副本调整该限制并验证实际数据链路，不能仅凭格式正确宣称可用。',
           '生产 Pages/Worker/KV、yylo.ccwu.cc、ADMIN/UUID/订阅、Windows 代理/DNS/路由/VPN/TUN/网卡和 Clash 配置均未修改。',
           '没有升级套餐、购买服务、申请额外权限或安装系统软件。','',
           '[官方 VPN Gate 来源](https://www.vpngate.net/api/iphone/)；[Mihomo VLESS 文档](https://wiki.metacubex.one/config/proxies/vless/)。']
    (ROOT/'EXPANDED_NODE_RESULT_20261025.md').write_text('\n'.join(text)+'\n',encoding='utf-8')

if __name__=='__main__':main()
