"""Bounded local diagnosis; never reads or writes the user's Clash configuration."""
import concurrent.futures
import hashlib
import json
import os
import re
import socket
import subprocess
import threading
import time
from datetime import datetime,timezone
from pathlib import Path
import requests

ROOT=Path(__file__).resolve().parent
DIR=ROOT/'diagnostics/local-openvpn';DIR.mkdir(exist_ok=True)
CORE=Path(r'D:\Program Files\Clash Verge Rev\verge-mihomo.exe')
PROTECTED={7897,17897,17898,17899,9097}

def utcnow():return datetime.now(timezone.utc).isoformat()

def tcp_probe(proxy):
    started=time.monotonic()
    try:
        with socket.create_connection((proxy['server'],proxy['port']),timeout=5):pass
        return {'name':proxy['name'],'ip':proxy['server'],'port':proxy['port'],'tcp':True,'elapsed_ms':round((time.monotonic()-started)*1000)}
    except Exception as e:return {'name':proxy['name'],'ip':proxy['server'],'port':proxy['port'],'tcp':False,'error':type(e).__name__,'elapsed_ms':round((time.monotonic()-started)*1000)}

def ports():
    sockets=[]
    try:
        for _ in range(2):
            s=socket.socket();s.bind(('127.0.0.1',0));sockets.append(s)
        values=[s.getsockname()[1] for s in sockets]
        if any(p in PROTECTED for p in values):raise ValueError('Protected port guard')
        return values
    finally:
        for s in sockets:s.close()

def test_proxy(proxy,index,extended=False):
    folder=DIR/f'node-{index}';folder.mkdir(exist_ok=True);mixed,controller=ports()
    config={'mixed-port':mixed,'bind-address':'127.0.0.1','allow-lan':False,'external-controller':f'127.0.0.1:{controller}',
            'log-level':'warning','mode':'rule','tun':{'enable':False},'dns':{'enable':False},
            'proxies':[proxy],'proxy-groups':[{'name':'Isolated Test','type':'select','proxies':[proxy['name']]}],
            'rules':['MATCH,Isolated Test']}
    path=folder/'config.json';path.write_text(json.dumps(config),encoding='utf-8')
    result={'name':proxy['name'],'ip':proxy['server'],'port':proxy['port'],'started_at':utcnow(),'checks':[],'local_settings_modified':False}
    child_env={k:v for k,v in os.environ.items() if not k.startswith(('CLASH_','MIHOMO_'))}
    log=(folder/'core.log').open('wb');process=None;watchdog=None
    control=requests.Session();control.trust_env=False
    session=requests.Session();session.trust_env=False;session.proxies={'http':f'http://127.0.0.1:{mixed}','https':f'http://127.0.0.1:{mixed}'}
    try:
        process=subprocess.Popen([str(CORE),'-d',str(folder/'home'),'-f',str(path)],env=child_env,stdin=subprocess.DEVNULL,stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW)
        watchdog=threading.Timer(120,process.terminate);watchdog.daemon=True;watchdog.start()
        for _ in range(50):
            if process.poll() is not None:raise ValueError('Temporary core exited before health')
            try:
                r=control.get(f'http://127.0.0.1:{controller}/version',timeout=1);r.raise_for_status();result['health']={'http':r.status_code,'version':r.json().get('version')};break
            except requests.ConnectionError:time.sleep(.1)
        else:raise ValueError('Temporary core readiness failed')
        for kind,url in [('latency-url','https://www.gstatic.com/generate_204'),('ipwhois','https://ipwho.is/'),('ipify','https://api.ipify.org/?format=json')]:
            started=time.monotonic()
            try:
                r=session.get(url,timeout=(8,20),allow_redirects=False)
                check={'kind':kind,'http':r.status_code,'elapsed_ms':round((time.monotonic()-started)*1000)}
                if kind in ('ipwhois','ipify') and r.ok:
                    body=r.json();check.update(ip=body.get('ip'),country=body.get('country_code'),certificate_verified=True)
                result['checks'].append(check)
            except requests.RequestException as error:
                result['checks'].append({'kind':kind,'error':type(error).__name__,'elapsed_ms':round((time.monotonic()-started)*1000)})
        result['verified_exit']=len([c for c in result['checks'] if c.get('ip')])==2 and len({c['ip'] for c in result['checks'] if c.get('ip')})==1
        if extended and result['verified_exit']:
            result['web_checks']=[];result['downloads']=[]
            for kind,url in [('google-search','https://www.google.com/search?q=example'),('bing-search','https://www.bing.com/search?q=example')]:
                before=time.monotonic()
                try:
                    with session.get(url,timeout=(8,15),stream=True,allow_redirects=False) as response:
                        chunk=next(response.iter_content(8192),b'')
                        result['web_checks'].append({'kind':kind,'http':response.status_code,'first_chunk_bytes':len(chunk),'elapsed_ms':round((time.monotonic()-before)*1000)})
                except requests.RequestException as error:result['web_checks'].append({'kind':kind,'error':type(error).__name__})
            for round_index in range(2):
                if round_index:time.sleep(20)
                try:
                    trace=session.get('https://speed.cloudflare.com/cdn-cgi/trace',timeout=(8,15));trace.raise_for_status()
                    fields=dict(line.split('=',1) for line in trace.text.splitlines() if '=' in line)
                    if fields.get('ip')!=result['checks'][1].get('ip'):raise ValueError('Actual speed-session exit changed')
                    before=time.monotonic();count=0;first=None
                    with session.get('https://speed.cloudflare.com/__down?bytes=524288',headers={'Accept-Encoding':'identity'},stream=True,timeout=(8,15)) as response:
                        response.raise_for_status()
                        for chunk in response.iter_content(16384):
                            if first is None:first=round((time.monotonic()-before)*1000)
                            count+=len(chunk)
                            if count>524288:raise ValueError('Bounded speed payload exceeded')
                            if time.monotonic()-before>15:raise ValueError('Download exceeded 15-second speed budget')
                    if count!=524288:raise ValueError('Incomplete speed response')
                    result['downloads'].append({'bytes':count,'mbps':count*8/(time.monotonic()-before)/1e6,'ttfb_ms':first,'exit_ip':fields['ip'],'country':fields.get('loc'),'certificate_verified':True})
                except Exception as error:
                    result['speed_error']=str(error) if isinstance(error,ValueError) else type(error).__name__;break
            result['last_ip_check']={}
            try:
                after=session.get('https://api.ipify.org/?format=json',timeout=(8,15));after.raise_for_status();result['last_ip_check']={'ip':after.json().get('ip'),'certificate_verified':True}
            except requests.RequestException as error:result['last_ip_check']={'error':type(error).__name__}
            result['browser_usable']=all(c.get('http')==200 for c in result['web_checks']) and len(result['downloads'])==2 and result['last_ip_check'].get('ip')==result['checks'][1].get('ip')
    except Exception as e:result['error']=str(e) if isinstance(e,ValueError) else type(e).__name__
    finally:
        session.close();control.close()
        if watchdog:watchdog.cancel()
        if process:
            process.terminate()
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
        log.close()
        text=(folder/'core.log').read_text(encoding='utf-8',errors='replace')
        labels=['make OpenVPN handshake','handshake timeout','certificate','unknown authority','expired','timeout','unsupported','refused','no such host','gvisor','context deadline exceeded','network is unreachable']
        result['core_error_categories']={label:sum(label.lower() in line.lower() for line in text.splitlines()) for label in labels if label.lower() in text.lower()}
        result['protocol_errors']=list(dict.fromkeys(re.findall(r'error: ([^\r\n]+)',text)))[:4]
        result.update(finished_at=utcnow(),temporary_process_stopped=process is None or process.poll() is not None)
    return result

def main():
    mode=os.sys.argv[1]
    if mode not in {'tcp','native','reachable','remote-dns','remote-dns-extra','remote-dns-recheck'}:raise ValueError('Explicit bounded diagnostic mode required')
    config=json.loads((ROOT/'dist/direct-openvpn.yaml').read_text());proxies=config['proxies']
    if len(proxies)!=35 or not all(p['type']=='openvpn' for p in proxies):raise ValueError('Only known 35-node public test subscription permitted')
    report={'time':utcnow(),'max_concurrency':2,'mode':mode,'results':[]}
    if mode=='tcp':
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:report['results']=list(pool.map(tcp_probe,proxies))
    elif mode=='native':
        # Only one Japanese and one Korean candidate; no scan of all profiles.
        reachable={r['name'] for r in json.loads((DIR/'tcp.json').read_text())['results'] if r['tcp']}
        selected=[next(p for p in proxies if '-JP-' in p['name'] and p['name'] in reachable),next(p for p in proxies if '-KR-' in p['name'] and p['name'] in reachable)]
        for index,p in enumerate(selected):
            r=test_proxy(p,index);report['results'].append(r);print(json.dumps(r),flush=True)
    elif mode=='reachable':
        reachable={r['name'] for r in json.loads((DIR/'tcp.json').read_text())['results'] if r['tcp']}
        selected=[p for p in proxies if p['name'] in reachable]
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(test_proxy,p,100+i,True) for i,p in enumerate(selected)]
            for future in concurrent.futures.as_completed(futures):
                result=future.result()
                report['results'].append(result);(DIR/(mode+'.json')).write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(result),flush=True)
    else:
        previous=json.loads((DIR/('remote-dns.json' if mode=='remote-dns-recheck' else 'reachable.json')).read_text())['results']
        names=({r['name'] for r in previous if r.get('browser_usable')} if mode=='remote-dns-recheck' else
               {r['name'] for r in previous if r.get('verified_exit') and
                (any(c.get('http')==200 for c in r.get('web_checks',[])) if mode=='remote-dns' else not any(c.get('http')==200 for c in r.get('web_checks',[])))})
        selected=[{**p,'remote-dns-resolve':True,'dns':['https://1.1.1.1/dns-query','https://8.8.8.8/dns-query']} for p in proxies if p['name'] in names]
        if not 1<=len(selected)<=4:raise ValueError('At most four resolver-isolation controls permitted')
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(test_proxy,p,200+i,True) for i,p in enumerate(selected)]
            for future in concurrent.futures.as_completed(futures):
                result=future.result();report['results'].append(result);(DIR/(mode+'.json')).write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(result),flush=True)
    (DIR/(mode+'.json')).write_text(json.dumps(report,indent=2),encoding='utf-8')
    if mode=='tcp':print(json.dumps({'checked':len(proxies),'tcp_connected':sum(r['tcp'] for r in report['results']),'results':report['results']}))

if __name__=='__main__':main()
