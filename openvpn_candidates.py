"""Convert public official VPN Gate profiles; never reads existing proxy secrets."""
import base64
import csv
import hashlib
import io
import json
import re
import shlex
import sys
from pathlib import Path
import vpngate as gate
from summarize_expansion import collect

ROOT=Path(__file__).resolve().parent
ALLOWED_COUNTRIES={'US','JP','KR','SG','CA','AU'}

def convert_profile(text, row, measured):
    blocks={name:re.search(r'<'+name+r'>\s*(.*?)\s*</'+name+r'>',text,re.S) for name in ('ca','cert','key','tls-auth','tls-crypt','tls-crypt-v2')}
    directives={}
    outside=re.sub(r'<[a-z0-9-]+>.*?</[a-z0-9-]+>','',text,flags=re.S)
    for line in outside.splitlines():
        if not line.strip() or line.lstrip().startswith(('#',';')):continue
        parts=shlex.split(line,comments=True)
        if parts:directives.setdefault(parts[0],[]).append(parts[1:])
    if len(directives.get('remote',[]))!=1:raise ValueError('Exactly one official remote required')
    remote=directives['remote'][0]
    if len(remote)!=2 or remote[0]!=row['IP'] or not gate.public_ip(remote[0]) or int(remote[1])!=measured['port']:raise ValueError('Official remote differs from measured entrance')
    if directives.get('proto')!=[['tcp']] or directives.get('dev')!=[['tun']]:raise ValueError('Only official TCP profile is supported')
    if not all(blocks[n] for n in ('ca','cert','key')):raise ValueError('Public profile certificate material incomplete')
    if any(k in directives for k in ('script-security','up','down','plugin','auth-user-pass','http-proxy','socks-proxy')):raise ValueError('Unsupported profile authentication or executable directive')
    if any(blocks[n] for n in ('tls-auth','tls-crypt','tls-crypt-v2')):raise ValueError('Unsupported static-key profile')
    cipher=directives.get('cipher',[['']])[0][0]
    auth=directives.get('auth',[['']])[0][0]
    if cipher!='AES-128-CBC' or auth!='SHA1':raise ValueError('Unexpected official cryptographic profile')
    return {'name':f"{measured['country']}-{measured['exit_ip']}",'type':'openvpn','server':row['IP'],'port':measured['port'],
            'proto':'tcp','ca':blocks['ca'][1],'cert':blocks['cert'][1],'key':blocks['key'][1],
            'cipher':cipher,'data-ciphers':[cipher],'data-ciphers-fallback':cipher,'auth':auth,
            'handshake-timeout':25,'ip-stack':{'mode':'gvisor'},'udp':False}

def prepare(source_path, output_path):
    raw=source_path.read_bytes();lines=raw.decode('utf-8-sig').splitlines()
    start=next(i for i,line in enumerate(lines) if line.lstrip('#').startswith('HostName,'))
    rows=csv.DictReader(io.StringIO('\n'.join([lines[start].lstrip('#')]+lines[start+1:])))
    byhost={r['HostName']+'.opengw.net':r for r in rows if r.get('HostName')}
    _,ranked=collect([ROOT/'reports/performance-40179946727.json',*sorted((ROOT/'reports').glob('expansion-performance-*.json'))])
    entries=[];skipped=[]
    for measured,url in ranked:
        if measured['min_download_mbps']<3:continue
        exit_info=measured['identity']['exit'];country=exit_info['country_code']
        if country not in ALLOWED_COUNTRIES:continue
        row=byhost.get(measured['host'])
        try:
            if not row:raise ValueError('No matching public profile in source snapshot')
            text=base64.b64decode(row['OpenVPN_ConfigData_Base64'],validate=True).decode('utf-8')
            meta={'host':measured['host'],'port':measured['port'],'exit_ip':exit_info['ip'],'country':country,
                  'prior_min_mbps':measured['min_download_mbps'],'prior_run':url}
            proxy=convert_profile(text,row,meta)
            entries.append({'expected':meta,'proxy':proxy,'public_profile_sha256':hashlib.sha256(text.encode()).hexdigest()})
        except ValueError as error:skipped.append({'host':measured['host'],'reason':str(error)})
        if len(entries)==35:break
    if not entries:raise ValueError('No official direct OpenVPN candidate profiles')
    document={'source':gate.SOURCE,'source_sha256':hashlib.sha256(raw).hexdigest(),
              'credential_provenance':'Only publicly distributed VPN Gate client certificate/key from official API; no user or Cloudflare credentials',
              'candidates':entries,'skipped':skipped}
    output_path.parent.mkdir(parents=True,exist_ok=True);output_path.write_text(json.dumps(document,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'prepared':len(entries),'skipped':skipped,'profile_values_logged':False}))

if __name__=='__main__':prepare(Path(sys.argv[1]),Path(sys.argv[2]))
