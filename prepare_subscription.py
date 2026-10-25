"""Export only measured, certificate-verified performance candidates; no secrets."""
import json
from pathlib import Path
from summarize_expansion import collect
import vpngate as gate
ROOT=Path(__file__).resolve().parent

def export():
    _,ranked=collect([ROOT/'reports/performance-40179946727.json',*sorted((ROOT/'reports').glob('expansion-performance-*.json'))])
    rows=[]
    for node,url in ranked:
        if node['min_download_mbps']<3:continue
        identity=node['identity'];ip=identity['exit']['ip'];country=identity['exit']['country_code']
        gate.node_key(node)
        if not gate.public_ip(ip) or country not in {'US','JP','KR','SG','CA','AU'}:raise ValueError('Invalid measured exit')
        observations=identity.get('observations',[])
        if identity.get('evidence')!='SSTP tunnel to two certificate-validated independent HTTPS exit services' or len(observations)!=3 or {o['observer'] for o in observations}!={'ipwhois','ipify'} or not all(o['ip']==ip and o['certificate_verified'] is True for o in observations):raise ValueError('Missing independent certificate-verified exit observations')
        if node['attempts']!=6 or node['verified_sessions']!=6 or len(node['downloads'])!=2 or node['elapsed_ms']<20000:raise ValueError('Incomplete repeat measurements')
        if not all(d['bytes']==1048576 and d['exit_ip']==ip and d['country_code']==country and d['same_tls_connection'] is True and d['certificate_verified'] is True for d in node['downloads']):raise ValueError('Invalid measured download path')
        if node['final_exit']['ip']!=ip or node['final_exit']['certificate_verified'] is not True:raise ValueError('Final exit changed')
        rows.append({k:node[k] for k in ('host','port','min_download_mbps','max_download_mbps','finished_at')})
        rows[-1].update(exit_ip=ip,country=country,workflow_url=url)
        if len(rows)==35:break
    if len(rows)!=35 or len({r['exit_ip'] for r in rows})!=35:raise ValueError('Refuse empty, short or duplicate exit list')
    return rows

if __name__=='__main__':
    rows=export();(ROOT/'workers/edgetunnel/verified-nodes.json').write_text(json.dumps(rows,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'exported':len(rows),'secrets':False}))
