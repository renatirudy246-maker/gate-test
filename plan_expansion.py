"""Build bounded official-source batches without opening candidate connections."""
import hashlib
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import vpngate as gate

def build_batches(csv_path, output_dir):
    raw=csv_path.read_bytes()
    fetched=datetime.fromtimestamp(csv_path.stat().st_mtime,timezone.utc).isoformat()
    os.environ['TARGET_COUNTRIES']='US,JP,KR,SG,CA,AU'
    nodes=gate.parse_candidates(raw.decode('utf-8-sig'))
    excluded=gate.load_excluded_nodes([gate.ROOT/'reports/node-scan-40136541061.json'])
    # Favor distinct volunteers before alternate public-vpn entrances into the
    # same known shared network. Final deduplication uses observed exit IPs.
    nodes.sort(key=lambda n:n['host'].lower().startswith('public-vpn-'))
    seen_ips=set(); distinct=[]
    for row in nodes:
        if gate.node_key(row) in excluded or row['entry_ip'] in seen_ips:
            continue
        seen_ips.add(row['entry_ip']);distinct.append(row)
    selected,available=gate.select_candidates(distinct,60,set())
    output_dir.mkdir(exist_ok=True,parents=True)
    files=[]
    for start in range(0,len(selected),10):
        rows=selected[start:start+10]
        path=output_dir/f'expand-20261025-{start//10+1:02d}.json'
        if path.exists():
            raise ValueError('Preserve existing candidate manifest')
        document={'format':'gate-performance-candidates-v1','source':gate.SOURCE,'tls_verified':True,
                  'source_sha256':hashlib.sha256(raw).hexdigest(),'fetched_at':fetched,
                  'excluded_prior_nodes':len(excluded),'candidates':rows}
        path.write_text(json.dumps(document,ensure_ascii=False,indent=2),encoding='utf8');files.append(str(path.relative_to(gate.ROOT)))
    print(json.dumps({'source_candidates':len(nodes),'eligible_distinct_entry_pools':available,
                      'selected':len(selected),'advertised_distribution':dict(Counter(r['source_country_code'] for r in selected)),'manifests':files}))

if __name__=='__main__':
    build_batches(Path(sys.argv[1]),gate.ROOT/'candidates')
