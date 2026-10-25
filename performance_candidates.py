"""Candidate hints only: historical real successes plus at most four fresh official candidates."""
import json
import sys
from pathlib import Path
import vpngate as gate

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
    document = json.loads(Path('reports/node-scan-40136541061.json').read_text(encoding='utf8'))
    fresh = Path(sys.argv[1]).read_text(encoding='utf8-sig') if len(sys.argv) > 1 else None
    print(json.dumps(select(document, fresh)))
