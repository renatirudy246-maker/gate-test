"""Six TCP probes only; no proxy, VPN, DNS or configuration mutation."""
import concurrent.futures
import ipaddress
import json
import os
import socket
import time
from datetime import datetime,timezone
from pathlib import Path

def main():
    if os.environ.get('GITHUB_ACTIONS')!='true' or os.name!='posix':raise SystemExit('Disposable Linux runner required')
    rows=json.loads(Path('candidates/reachability-control-20261025.json').read_text())
    if len(rows)!=6 or len({(r['ip'],r['port']) for r in rows})!=6:raise ValueError('Invalid six-probe budget')
    if not all(ipaddress.ip_address(r['ip']).is_global and type(r['port']) is int and 1<=r['port']<=65535 for r in rows):raise ValueError('Public candidate targets only')
    def probe(row):
        before=time.monotonic();result={**row,'time':datetime.now(timezone.utc).isoformat()}
        try:
            with socket.create_connection((row['ip'],row['port']),timeout=5):pass
            result['tcp']=True
        except OSError as error:result.update(tcp=False,error=type(error).__name__)
        result['elapsed_ms']=round((time.monotonic()-before)*1000);return result
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(probe,rows))
    report={'backend':'isolated-github-linux','max_concurrency':2,'results':results}
    folder=Path('diagnostics/reachability');folder.mkdir(parents=True,exist_ok=True)
    (folder/'run.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))

if __name__=='__main__':main()
