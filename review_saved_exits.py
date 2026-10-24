"""Metadata-only review of saved real observations. Never opens an SSTP tunnel or publishes."""
import copy
import hashlib
import json
import sys
from pathlib import Path
import vpngate as gate

def validate_observations(result):
    ip = gate.public_ip((result.get('exit') or {}).get('ip'))
    observations = result.get('observations') or []
    return (bool(ip) and len(observations) == 3 and
            {o.get('observer') for o in observations} == {'ipwhois', 'ipify'} and
            all(o.get('ip') == ip and o.get('certificate_verified') is True for o in observations) and
            result.get('evidence') == 'SSTP tunnel to two certificate-validated independent HTTPS exit services')

def main():
    source = Path(sys.argv[1])
    raw = source.read_bytes()
    saved = json.loads(raw)
    results = saved.get('results')
    if (not isinstance(results, list) or not 1 <= len(results) <= 10 or
            saved.get('checked') != len(results) or not 1 <= saved.get('concurrency', 100) <= 2 or
            saved.get('source') != gate.SOURCE):
        raise ValueError('Saved run exceeds authorized budget')
    report = {'reviewed_at': gate.utcnow(), 'source_run_sha256': hashlib.sha256(raw).hexdigest(),
              'source_run': '40136541061', 'original_error': saved.get('error'), 'new_tunnel_scans': 0,
              'original_checked': saved.get('checked'), 'published': False, 'results': []}
    for item in results:
        if item.get('success') is not True:
            continue
        if not validate_observations(item):
            raise ValueError('Saved exit lacks repeated independent TLS-authenticated observations')
        result = gate.crosscheck(copy.deepcopy(item))
        report['results'].append(result)
    qualified = [r for r in report['results'] if gate.eligible_exit(r)]
    report.update(verified_exits=sum(r['exit_crosschecked'] for r in report['results']),
                  residential_candidates=sum(r['exit_crosschecked'] and r['residential'] == 'residential' for r in report['results']),
                  qualified=len(qualified), qualified_residential=sum(r['residential'] == 'residential' for r in qualified))
    output = gate.DIAGNOSTICS / 'node-exit-review.json'
    output.parent.mkdir(exist_ok=True, parents=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
    print(json.dumps({k: report[k] for k in ('new_tunnel_scans', 'original_checked', 'verified_exits', 'residential_candidates', 'qualified', 'qualified_residential')}))
    print(json.dumps([{'ip':r['exit']['ip'], 'country':r['country_code'], 'asn':r['exit']['asn'], 'residential':r['residential'], 'risk_status':r['risk_status'], 'risk_score':r['risk_score'], 'latency_ms':r['latency_ms'], 'metadata_errors':r['metadata_errors']} for r in report['results']], ensure_ascii=True, indent=2))

if __name__ == '__main__':
    main()
