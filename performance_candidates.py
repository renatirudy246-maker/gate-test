"""Candidate hints only: historical real successes plus at most four fresh official candidates."""
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
import vpngate as gate

PERFORMANCE_COUNTRIES = {'US','JP','KR','SG','CA','AU'}

def load_manifest(path):
    resolved = Path(path).resolve()
    if not resolved.is_relative_to(gate.ROOT/'candidates'):
        raise ValueError('Performance manifests must be inside the test repository candidates folder')
    document = json.loads(resolved.read_text(encoding='utf-8'))
    rows = document.get('candidates')
    if document.get('format') != 'gate-performance-candidates-v1' or document.get('source') != gate.SOURCE or document.get('tls_verified') is not True:
        raise ValueError('Invalid official-source manifest provenance')
    if not re.fullmatch(r'[a-f0-9]{64}', document.get('source_sha256','')):
        raise ValueError('Missing official-source snapshot hash')
    fetched = datetime.fromisoformat(document['fetched_at'])
    if fetched.tzinfo is None:
        raise ValueError('Official source timestamp must include timezone')
    age = (datetime.now(timezone.utc)-fetched).total_seconds()
    if not -60 <= age <= 6*3600:
        raise ValueError('Official candidate snapshot is stale or future dated')
    if not isinstance(rows,list) or not 1 <= len(rows) <= 10:
        raise ValueError('Manifest candidate budget exceeded')
    keys = [gate.node_key(row) for row in rows]
    if len(set(keys)) != len(keys) or any(not gate.public_ip(row.get('entry_ip')) or row.get('source_country_code') not in PERFORMANCE_COUNTRIES for row in rows):
        raise ValueError('Manifest contains duplicate, private or non-target candidates')
    return [{**row,'candidate_origin':'official_source_snapshot'} for row in rows]

def select(document, fresh=None):
    selected, seen = [], set()
    for row in document.get('results', []):
        if row.get('success') is not True or len(row.get('observations', [])) != 3:
            continue
        key = gate.node_key(row)
        if key in seen:
            continue
        seen.add(key)
        selected.append({k:row[k] for k in ('host','port','source_country_code')})
        selected[-1].update(candidate_origin='previously_measured_success', previous_exit_ip=row['exit']['ip'],
                            historical_risk_score=row.get('risk_score'), historical_risk_checked_at=row.get('metadata_checked_at'))
    if len(selected) > 10:
        raise ValueError('Candidate budget exceeded')
    if fresh:
        excluded = {gate.node_key(row) for row in document['tested_nodes']}
        extra, _ = gate.select_candidates(gate.parse_candidates(fresh), min(4, 10-len(selected)), excluded | seen)
        selected.extend({**row, 'candidate_origin':'fresh_official_feed'} for row in extra)
    return selected

if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--manifest':
        print(json.dumps(load_manifest(sys.argv[2])))
    else:
        document = json.loads(Path('reports/node-scan-40136541061.json').read_text(encoding='utf8'))
        fresh = Path(sys.argv[1]).read_text(encoding='utf-8-sig') if len(sys.argv) > 1 else None
        print(json.dumps(select(document, fresh)))
