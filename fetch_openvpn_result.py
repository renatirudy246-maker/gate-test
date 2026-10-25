"""Read only this test repository's run; do not log auth or signed URLs."""
import hashlib
import io
import json
import subprocess
import sys
import zipfile
from pathlib import Path
import requests

def main():
    run_id=sys.argv[1]
    if not run_id.isdecimal():raise ValueError('Invalid run ID')
    token=subprocess.run(['gh','auth','token'],capture_output=True,text=True,check=True,timeout=10).stdout.strip()
    session=requests.Session();session.headers.update({'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json'})
    prefix='https://api.github.com/repos/renatirudy246-maker/gate-test'
    r=session.get(prefix+'/actions/runs/'+run_id,timeout=25);r.raise_for_status();run=r.json()
    print(json.dumps({k:run.get(k) for k in ('id','status','conclusion','head_sha')}))
    if run['status']!='completed':return
    r=session.get(prefix+'/actions/runs/'+run_id+'/artifacts',timeout=25);r.raise_for_status()
    artifact=next(a for a in r.json()['artifacts'] if a['name']=='gate-direct-openvpn-diagnostics')
    r=session.get(prefix+'/actions/artifacts/'+str(artifact['id'])+'/zip',timeout=40);r.raise_for_status()
    digest=hashlib.sha256(r.content).hexdigest()
    if 'sha256:'+digest!=artifact['digest']:raise ValueError('Artifact digest mismatch')
    archive=zipfile.ZipFile(io.BytesIO(r.content))
    if archive.namelist()!=['run.json']:raise ValueError('Unexpected diagnostic artifact files')
    raw=archive.read('run.json');report=json.loads(raw)
    folder=Path('diagnostics/openvpn-'+run_id);folder.mkdir(exist_ok=True)
    (folder/'run.json').write_bytes(raw)
    document={'workflow_url':run['html_url'],'executed_commit':run['head_sha'],'artifact_zip_sha256':digest,
              'raw_run_sha256':hashlib.sha256(raw).hexdigest(),'measurements':report,
              'measurement_note':'In initial commit 6ad4c29, verified_sessions=6 was a mislabeled counter. Actual successful test uses one OpenVPN session and seven HTTPS requests; no independent reconnect is claimed.'}
    Path('reports/direct-openvpn-'+run_id+'.json').write_text(json.dumps(document,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:report.get(k) for k in ('status','checked','success','selected','selected_countries','error')}))
    for node in report['results']:
        print(json.dumps({k:node.get(k) for k in ('host','success','exit_ip','country','min_download_mbps','max_download_mbps','error','core_error_categories')}))

if __name__=='__main__':
    try:main()
    except Exception as error:
        print('Read-only result retrieval failed: '+type(error).__name__);raise SystemExit(1)
