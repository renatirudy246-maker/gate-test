"""Check only the independent service endpoints; never log response credentials."""
import json
import os
from pathlib import Path
import requests

checks = []
try:
    for service, base in [('checker', os.environ['CHECK_WORKER'].removesuffix('/check')), ('edgetunnel', os.environ['TEST_EDGE_URL'])]:
        response = requests.get(base + '/health', timeout=20, allow_redirects=False)
        body = response.json() if response.status_code == 200 else {}
        checks.append({'service': service, 'http': response.status_code, 'configured': body.get('configured')})
    response = requests.get(os.environ['TEST_EDGE_URL'] + '/admin', headers={'Authorization': 'Bearer ' + os.environ['TEST_ADMIN']}, timeout=20, allow_redirects=False)
    checks.append({'service': 'test-admin', 'http': response.status_code})
    if any(c['http'] != 200 or c.get('configured', True) is not True for c in checks):
        raise SystemExit('Independent service preflight failed; no nodes will be scanned')
except requests.RequestException as exc:
    checks.append({'error': type(exc).__name__})
    raise SystemExit('Independent service request failed; no nodes will be scanned')
finally:
    Path('diagnostics').mkdir(exist_ok=True)
    Path('diagnostics/preflight.json').write_text(json.dumps(checks, indent=2), encoding='utf8')
    print(json.dumps(checks))
