"""Remaining entrances in the already-authorized sixty-node pool, without repeats."""
import base64
import csv
import hashlib
import io
import json
from pathlib import Path
from openvpn_candidates import convert_profile,ROOT
from vpngate import node_key

raw=(ROOT/'diagnostics/openvpn/official-current.csv').read_bytes();lines=raw.decode('utf-8-sig').splitlines()
start=next(i for i,line in enumerate(lines) if line.lstrip('#').startswith('HostName,'))
rows=csv.DictReader(io.StringIO('\n'.join([lines[start].lstrip('#')]+lines[start+1:])))
byhost={r['HostName']+'.opengw.net':r for r in rows if r.get('HostName')}
old=json.loads((ROOT/'candidates/direct-openvpn-20261025.json').read_text());seen={node_key(e['expected']) for e in old['candidates']}
entries=[];skipped=[]
known={}
for path in (ROOT/'reports').glob('expansion-performance-*.json'):
    for node in json.loads(path.read_text())['measurements']['results']:
        if node.get('identity',{}).get('success') is True:known[node_key(node)]=node['identity']['exit']
for path in sorted((ROOT/'candidates').glob('expand-20261025-*.json')):
    for node in json.loads(path.read_text())['candidates']:
        key=node_key(node)
        if key in seen:continue
        seen.add(key);row=byhost.get(node['host'])
        try:
            if not row:raise ValueError('Missing current official public profile')
            exit_info=known.get(key,{})
            # A missing SSTP identity never makes the entry IP an assumed exit.
            meta={'host':node['host'],'port':node['port'],'exit_ip':exit_info.get('ip'),'country':exit_info.get('country_code'),
                  'advertised_country_hint':node['source_country_code']}
            profile=base64.b64decode(row['OpenVPN_ConfigData_Base64'],validate=True).decode('utf-8')
            proxy=convert_profile(profile,row,meta)
            entries.append({'expected':meta,'proxy':proxy,'public_profile_sha256':hashlib.sha256(profile.encode()).hexdigest()})
        except ValueError as error:skipped.append({'host':node['host'],'reason':str(error)})
if not 2<=len(entries)<=35:raise ValueError('Invalid remaining candidate budget')
doc={'source':old['source'],'source_sha256':hashlib.sha256(raw).hexdigest(),'credential_provenance':old['credential_provenance'],'candidates':entries,'skipped':skipped}
(ROOT/'candidates/direct-openvpn-extra-20261025.json').write_text(json.dumps(doc,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'remaining':len(entries),'skipped':skipped,'duplicate_previous_nodes':0}))
