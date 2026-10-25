"""Disposable Linux-only Mihomo OpenVPN validation and public config export."""
import concurrent.futures
import gzip
import hashlib
import json
import os
import socket
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
import requests
import vpngate as gate

ROOT=Path(__file__).resolve().parent
DIR=ROOT/'diagnostics/openvpn-verification'
BINARY=ROOT/'dist/openvpn/mihomo'
VERSION='v1.19.32'
CORE_URL=f'https://github.com/MetaCubeX/mihomo/releases/download/{VERSION}/mihomo-linux-amd64-compatible-{VERSION}.gz'
CORE_SHA256='ba3ce607747a07f948fc35780e108a4a7c7f552a38b9bd4d115f313ebcb89c20'
BYTES=1048576

def utcnow():return datetime.now(timezone.utc).isoformat()

def free_ports(count):
    # The two workers use pre-reserved distinct loopback ports only on the runner.
    holders=[]
    try:
        for _ in range(count):
            s=socket.socket();s.bind(('127.0.0.1',0));holders.append(s)
        return [s.getsockname()[1] for s in holders]
    finally:
        for s in holders:s.close()

def get_json(session,url,**kwargs):
    r=session.get(url,timeout=(8,30),allow_redirects=False,**kwargs)
    r.raise_for_status()
    if len(r.content)>65536:raise ValueError('Observer response budget exceeded')
    return r.json()

def benchmark(entry,index,ports):
    expected=entry['expected'];proxy={**entry['proxy'],'remote-dns-resolve':True,'dns':['https://1.1.1.1/dns-query','https://8.8.8.8/dns-query']};folder=DIR/f'node-{index:02d}';folder.mkdir(exist_ok=True)
    mixed,controller=ports
    config={'mixed-port':mixed,'bind-address':'127.0.0.1','allow-lan':False,'external-controller':f'127.0.0.1:{controller}',
            'log-level':'warning','mode':'rule','tun':{'enable':False},'dns':{'enable':False},
            'proxies':[proxy],'proxy-groups':[{'name':'Gate Test','type':'select','proxies':[proxy['name']]}],
            'rules':['MATCH,Gate Test']}
    cfg=folder/'config.json';cfg.write_text(json.dumps(config),encoding='utf-8')
    result={'host':expected['host'],'port':expected['port'],'expected_exit':expected['exit_ip'],'expected_country':expected['country'],
            'started_at':utcnow(),'observations':[],'downloads':[],'success':False,'verified_https_checks':0,'openvpn_tunnel_sessions':1}
    started=time.monotonic();process=None;logfile=(folder/'core.log').open('wb')
    control=requests.Session();control.trust_env=False
    session=requests.Session();session.trust_env=False;session.proxies={'http':f'http://127.0.0.1:{mixed}','https':f'http://127.0.0.1:{mixed}'}
    try:
        process=subprocess.Popen([str(BINARY),'-d',str(folder/'home'),'-f',str(cfg)],stdin=subprocess.DEVNULL,stdout=logfile,stderr=logfile)
        healthy=False
        for _ in range(50):
            if process.poll() is not None:raise ValueError('Mihomo process exited during readiness')
            try:
                health=get_json(control,f'http://127.0.0.1:{controller}/version')
                if health.get('version')!='1.19.32' and health.get('version')!='v1.19.32':raise ValueError('Unexpected core version')
                healthy=True;break
            except requests.ConnectionError:time.sleep(.1)
        if not healthy:raise ValueError('Actual controller readiness failed')
        result['health']={'http':200,'version':health['version'],'configured':True}
        who=get_json(session,'https://ipwho.is/')
        if who.get('success') is False or not gate.public_ip(who.get('ip')) or who.get('country_code') not in {'US','JP','KR','SG','CA','AU'}:raise ValueError('Unverified public OpenVPN exit or non-target actual country')
        if expected.get('exit_ip') and (who['ip']!=expected['exit_ip'] or who['country_code']!=expected['country']):raise ValueError('Actual OpenVPN exit or country differs from measured SSTP exit')
        result['observations'].append({'source':'ipwho.is','ip':who['ip'],'country':who['country_code'],'asn':who.get('connection',{}).get('asn'),'certificate_verified':True})
        ipify=get_json(session,'https://api.ipify.org/?format=json')
        if ipify.get('ip')!=who['ip']:raise ValueError('Independent actual exit providers disagree')
        result['observations'].append({'source':'ipify','ip':ipify['ip'],'certificate_verified':True})
        for attempt in range(2):
            if attempt:time.sleep(20)
            trace=session.get('https://speed.cloudflare.com/cdn-cgi/trace',timeout=(8,30),allow_redirects=False);trace.raise_for_status()
            fields=dict(line.split('=',1) for line in trace.text.strip().splitlines() if '=' in line)
            if fields.get('ip')!=who['ip'] or fields.get('loc')!=who['country_code']:raise ValueError('Independent OpenVPN speed observer IP/country mismatch')
            before=time.monotonic();count=0;first=None
            with session.get(f'https://speed.cloudflare.com/__down?bytes={BYTES}',headers={'Accept-Encoding':'identity','Cache-Control':'no-cache'},timeout=(8,30),stream=True,allow_redirects=False) as response:
                response.raise_for_status()
                for chunk in response.iter_content(16384):
                    if first is None:first=(time.monotonic()-before)*1000
                    count+=len(chunk)
                    if count>BYTES:raise ValueError('Download exceeded byte budget')
            elapsed=time.monotonic()-before
            if count!=BYTES:raise ValueError('Incomplete OpenVPN download')
            result['downloads'].append({'bytes':count,'mbps':count*8/elapsed/1e6,'ttfb_ms':first,'certificate_verified':True,'observed_at':utcnow()})
        final=get_json(session,'https://api.ipify.org/?format=json')
        if final.get('ip')!=who['ip']:raise ValueError('Actual exit changed at final observation')
        result.update(success=True,exit_ip=who['ip'],country=who['country_code'],asn=who.get('connection',{}).get('asn'),isp=who.get('connection',{}).get('org'),verified_https_checks=7)
        speeds=[d['mbps'] for d in result['downloads']]
        result.update(min_download_mbps=min(speeds),max_download_mbps=max(speeds),short_term_stable=max(speeds)/min(speeds)<=2 and time.monotonic()-started>=20,long_term_stability='unknown')
    except Exception as error:
        # Do not include exception strings: requests can embed private config URLs.
        result['error']=str(error) if isinstance(error,ValueError) else type(error).__name__
    finally:
        session.close();control.close()
        if process:
            process.terminate()
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
        logfile.close()
        if not result['success']:
            # Retain only known protocol error categories, never raw core lines.
            log=(folder/'core.log').read_text(encoding='utf-8',errors='replace')
            result['core_error_categories']=[label for label in ('make OpenVPN handshake','certificate','unknown authority','expired','timeout','unsupported','create OpenVPN stack device','refused','no such host') if label.lower() in log.lower()]
        result.update(finished_at=utcnow(),elapsed_ms=round((time.monotonic()-started)*1000))
    return result

def main():
    if os.environ.get('GITHUB_ACTIONS')!='true' or os.name!='posix':raise SystemExit('Direct OpenVPN validation is restricted to disposable Linux Actions')
    DIR.mkdir(parents=True,exist_ok=True);BINARY.parent.mkdir(parents=True,exist_ok=True)
    report={'started_at':utcnow(),'core':VERSION,'max_candidates':35,'max_concurrency':2,'max_download_payload_mib':70,
            'backend':'native-mihomo-openvpn-gvisor','results':[],'published':False}
    def save():(DIR/'run.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    try:
        response=requests.get(CORE_URL,timeout=60);response.raise_for_status()
        if len(response.content)>40*1024*1024 or hashlib.sha256(response.content).hexdigest()!=CORE_SHA256:raise ValueError('Official core asset digest mismatch')
        BINARY.write_bytes(gzip.decompress(response.content));BINARY.chmod(0o700)
        report['core_asset_sha256']=CORE_SHA256
        batch=os.environ.get('OPENVPN_BATCH','initial')
        if batch not in {'initial','remaining'}:raise ValueError('Invalid manual batch choice')
        manifest='candidates/direct-openvpn-'+('extra-' if batch=='remaining' else '')+'20261025.json'
        doc=json.loads((ROOT/manifest).read_text());candidates=doc['candidates'];report['manifest']=manifest
        if not 2<=len(candidates)<=35:raise ValueError('Invalid bounded candidate list')
        reserved=free_ports(len(candidates)*2)
        pilot=[next((i for i,e in enumerate(candidates) if e['expected'].get('country')=='JP'),0),
               next(i for i,e in enumerate(candidates) if e['expected'].get('country')=='KR')]
        by_index={}
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            for i,res in zip(pilot,pool.map(lambda i:benchmark(candidates[i],i,reserved[2*i:2*i+2]),pilot)):
                by_index[i]=res;report['results']=[by_index[k] for k in sorted(by_index)];save();print(json.dumps({'pilot':True,'host':res['host'],'success':res['success'],'error':res.get('error')}),flush=True)
            if not any(r['success'] for r in by_index.values()):raise ValueError('Both independent pilot exits failed; further connection tests stopped')
            remaining=[i for i in range(len(candidates)) if i not in pilot]
            for i,res in zip(remaining,pool.map(lambda i:benchmark(candidates[i],i,reserved[2*i:2*i+2]),remaining)):
                by_index[i]=res;report['results']=[by_index[k] for k in sorted(by_index)];save();print(json.dumps({'host':res['host'],'success':res['success'],'stable':res.get('short_term_stable'),'min_mbps':res.get('min_download_mbps'),'error':res.get('error')}),flush=True)
        successful=[(i,r) for i,r in by_index.items() if r['success'] and r.get('short_term_stable') and r['min_download_mbps']>=3]
        successful.sort(key=lambda pair:-pair[1]['min_download_mbps'])
        if not successful:raise ValueError('No independently validated stable OpenVPN exits meet 3 Mbps gate')
        combined=[(candidates[i]['proxy'],r) for i,r in successful]
        if batch=='remaining':
            previous=json.loads((ROOT/'reports/direct-openvpn-40184315423.json').read_text())['measurements']
            old_candidates=json.loads((ROOT/'candidates/direct-openvpn-20261025.json').read_text())['candidates']
            lookup={(e['expected']['host'],e['expected']['port']):e['proxy'] for e in old_candidates}
            for old in previous['results']:
                if old['success'] and old.get('short_term_stable') and old['min_download_mbps']>=3:
                    combined.append((lookup[(old['host'],old['port'])],old))
            report['merge_base']='reports/direct-openvpn-40184315423.json'
        distinct={}
        for proxy,r in combined:
            if r['exit_ip'] not in distinct or r['min_download_mbps']>distinct[r['exit_ip']][1]['min_download_mbps']:distinct[r['exit_ip']]=(proxy,r)
        combined=sorted(distinct.values(),key=lambda pair:-pair[1]['min_download_mbps'])[:35]
        proxies=[{**proxy,'remote-dns-resolve':True,'dns':['https://1.1.1.1/dns-query','https://8.8.8.8/dns-query'],'name':f"{rank:02d}-{r['country']}-{r['exit_ip']}-{r['min_download_mbps']:.2f}Mbps"} for rank,(proxy,r) in enumerate(combined,1)]
        config={'proxies':proxies,'proxy-groups':[{'name':'Gate Direct','type':'select','proxies':[p['name'] for p in proxies]}],'rules':['MATCH,Gate Direct']}
        PUBLIC=ROOT/'public';PUBLIC.mkdir(exist_ok=True)
        (PUBLIC/'clash-openvpn.yaml').write_text(json.dumps(config,indent=2)+'\n',encoding='utf-8')
        subprocess.run([str(BINARY),'-t','-d',str(DIR/'final-syntax'),'-f',str(PUBLIC/'clash-openvpn.yaml')],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=20)
        report.update(status='remote_checks_completed_local_acceptance_pending',selected=len(proxies),selected_countries={country:sum(r['country']==country for _,r in combined) for country in ('US','JP','KR','SG','CA','AU')},selected_exits=[r['exit_ip'] for _,r in combined],published=False)
        (PUBLIC/'verification.json').write_text(json.dumps({'measured_at':utcnow(),'protocol':'openvpn','core':VERSION,'count':len(proxies),'source':doc['source'],'no_cloudflare_relay':True,'local_acceptance':'pending','published':False},indent=2),encoding='utf-8')
        (PUBLIC/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>Remote diagnostic candidates</title><p>Remote measurements only. Local acceptance pending. Not a local usability recommendation.</p>',encoding='utf-8')
    except Exception as error:
        report.update(status='failed',error=str(error) if isinstance(error,ValueError) else type(error).__name__);print(json.dumps({'status':'failed','error':report['error']}),flush=True);return 1
    finally:
        report.update(checked=len(report['results']),success=sum(r['success'] for r in report['results']),finished_at=utcnow());save()
    print(json.dumps({k:report[k] for k in ('status','checked','success','selected','selected_countries')}),flush=True)
    return 0

if __name__=='__main__':raise SystemExit(main())
