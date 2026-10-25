"""Publish a browsing-only snapshot after actual local and fresh-session checks."""
import copy
import hashlib
import ipaddress
import json
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parent

def qualified(node):
    observations=[c for c in node.get('checks',[]) if c.get('kind') in {'ipwhois','ipify'}]
    pages=node.get('web_checks',[]);downloads=node.get('downloads',[])
    return (node.get('verified_exit') is True and node.get('browser_usable') is True and
        len(observations)==2 and {c.get('kind') for c in observations}=={'ipwhois','ipify'} and
        all(c.get('http')==200 and c.get('certificate_verified') is True and c.get('ip')==node['last_ip_check'].get('ip') for c in observations) and
        len(pages)==2 and {p.get('kind') for p in pages}=={'google-search','bing-search'} and all(p.get('http')==200 for p in pages) and
        len(downloads)==2 and all(d.get('bytes')==524288 and d.get('certificate_verified') is True and d.get('exit_ip')==node['last_ip_check'].get('ip') for d in downloads) and
        max(d['mbps'] for d in downloads)/min(d['mbps'] for d in downloads)<=2 and
        node['last_ip_check'].get('certificate_verified') is True and node.get('temporary_process_stopped') is True)

def build():
    document=json.loads((ROOT/'reports/local-openvpn-diagnosis-20261025.json').read_text())
    base=json.loads((ROOT/'subscriptions/github-verified-35.yaml').read_text())
    remote={r['name']:r for r in document['remote_dns']['results'] if qualified(r)}
    recheck={r['name']:r for r in document['fresh_recheck']['results'] if qualified(r)}
    names=remote.keys()&recheck.keys()
    if not names:raise ValueError('No locally browsable exit survived the fresh-session recheck')
    for name in names:
        result=recheck[name]
        age=(datetime.now(timezone.utc)-datetime.fromisoformat(result['finished_at'])).total_seconds()
        if not 0<=age<=3600:raise ValueError('Local acceptance evidence is stale')
        if not ipaddress.ip_address(result['last_ip_check']['ip']).is_global:raise ValueError('Public actual exit required')
        if next(c for c in result['checks'] if c['kind']=='ipwhois').get('country') not in {'US','JP','KR','SG','CA','AU'}:raise ValueError('Actual exit country is outside target countries')
    proxies=[]
    for p in base['proxies']:
        if p['name'] not in names:continue
        result=recheck[p['name']];proxy=copy.deepcopy(p)
        proxy.update({'remote-dns-resolve':True,'dns':['https://1.1.1.1/dns-query','https://8.8.8.8/dns-query']})
        mbps=min(d['mbps'] for d in result['downloads'])
        proxy['name']=f"LOCAL-BROWSING-{result['last_ip_check']['ip']}-{mbps:.2f}Mbps"
        proxies.append(proxy)
    if not proxies or len(proxies)>4:raise ValueError('Invalid small local verification snapshot')
    config={'proxies':proxies,'proxy-groups':[{'name':'Gate Direct','type':'select','proxies':[p['name'] for p in proxies]}],'rules':['MATCH,Gate Direct']}
    return config

def main():
    config=build();public=ROOT/'public';public.mkdir(exist_ok=True)
    data=json.dumps(config,indent=2)+'\n'
    for name in ('clash-openvpn.yaml','clash-local.yaml'):(public/name).write_text(data,encoding='utf-8')
    (public/'clash-github-only-35.yaml').write_bytes((ROOT/'subscriptions/github-verified-35.yaml').read_bytes())
    (public/'verification.json').write_text(json.dumps({'category':'local-browsing-only-not-high-speed','nodes':len(config['proxies']),'snapshot':'2026-10-25','automatic_update':False,'production_modified':False},indent=2))
    (public/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>Gate local browsing test</title><p>Old 35-node overseas measurements do not establish local usability.</p><a href="clash-local.yaml">Locally checked browsing-only snapshot; not high-speed</a>',encoding='utf-8')
    print(json.dumps({'locally_verified':len(config['proxies']),'speed_claim':'none','sha256':hashlib.sha256(data.encode()).hexdigest()}))

if __name__=='__main__':main()
