#!/usr/bin/env python3
"""Manual, bounded VPN Gate test. Missing evidence always remains unknown."""
import base64
import csv
import io
import ipaddress
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
import requests

ROOT = Path(__file__).resolve().parent
PUBLIC = Path(os.environ.get('PUBLIC_DIR', ROOT / 'public'))
DIAGNOSTICS = Path(os.environ.get('DIAGNOSTICS_DIR', ROOT / 'diagnostics'))
SOURCE = 'https://www.vpngate.net/api/iphone/'
HOST_RE = re.compile(r'^(?:vpn\d+|vpnv\d+|public-vpn-[a-z0-9-]+)\.opengw\.net$', re.I)
CONSUMER_ISPS = ('COMCAST', 'XFINITY', 'CHARTER', 'SPECTRUM', 'COX COMMUNICATIONS', 'AT&T', 'VERIZON', 'FRONTIER', 'CENTURYLINK', 'NTT EAST', 'NTT WEST', 'SOFTBANK', 'KDDI')

def target_countries(value=None):
    value = os.environ.get('TARGET_COUNTRIES', 'US,JP,KR,SG') if value is None else value
    codes = {code.strip().upper() for code in value.split(',') if code.strip()}
    if not codes or any(not re.fullmatch(r'[A-Z]{2}', code) for code in codes):
        raise ValueError('TARGET_COUNTRIES must contain comma-separated two-letter country codes')
    return codes

def risk_status(metadata):
    flags = [metadata.get(k) for k in ('is_proxy', 'is_vpn', 'is_tor', 'is_abuser')]
    if any(value is True for value in flags):
        return 'flagged'
    if not all(type(value) is bool for value in flags):
        return 'unknown'
    return 'no_flags_reported'  # Not a guarantee of low fraud risk or clean IP.

def eligible_exit(result):
    return (result.get('exit_crosschecked') is True and
            result.get('country_code') in target_countries() and
            result.get('risk_status') == 'no_flags_reported')

def verify_checker_health(checker):
    response = requests.get(checker.removesuffix('/check') + '/health', timeout=20, allow_redirects=False)
    if response.status_code != 200:
        raise ValueError(f'Checker health HTTP {response.status_code}; scanning blocked')
    body = response.json()
    if body.get('service') != 'gate-checker-test' or body.get('configured') is not True:
        raise ValueError('Checker health/configuration invalid; scanning blocked')
    if os.environ.get('CHECK_BACKEND') == 'node-local' and body.get('backend') != 'isolated-node-sstp':
        raise ValueError('Isolated Node backend identity invalid; scanning blocked')

def utcnow():
    return datetime.now(timezone.utc).isoformat()

def public_ip(value):
    try:
        ip = ipaddress.ip_address(value)
        return str(ip) if ip.is_global else None
    except (TypeError, ValueError):
        return None

def asn_number(value):
    try:
        return int(str(value).upper().removeprefix('AS'))
    except (ValueError, TypeError):
        return None

def classify_network(is_datacenter=None, asn_type=None, org=''):
    # Residential means consumer ISP candidate, never household or cleanliness.
    if is_datacenter is True or str(asn_type).lower() in ('hosting', 'datacenter'):
        return 'datacenter'
    if str(asn_type).lower() in ('isp', 'residential') and any(k in str(org).upper() for k in CONSUMER_ISPS):
        return 'residential'
    return 'unknown'

def parse_candidates(text):
    lines = [line for line in text.splitlines() if line.strip()]
    start = next((i for i, line in enumerate(lines) if line.lstrip('#').startswith('HostName,')), None)
    if start is None:
        raise ValueError('Official VPN Gate CSV header missing')
    reader = csv.DictReader(io.StringIO('\n'.join([lines[start].lstrip('#')] + lines[start + 1:])))
    candidates, seen = [], set()
    for row in reader:
        name, ip = row.get('HostName', ''), row.get('IP', '')
        host = name if name.endswith('.opengw.net') else name + '.opengw.net'
        if not HOST_RE.fullmatch(host) or not public_ip(ip):
            continue
        try:
            config = base64.b64decode(row.get('OpenVPN_ConfigData_Base64', ''), validate=True).decode('utf-8')
        except (ValueError, UnicodeError):
            continue
        if not re.search(r'^proto\s+tcp(?:4|6|-client)?\b', config, re.M):
            continue
        remote = re.search(r'^remote\s+\S+\s+(\d+)', config, re.M)
        if not remote or not 1 <= int(remote[1]) <= 65535:
            continue
        port = int(remote[1])
        if (host, port) in seen:
            continue
        seen.add((host, port))
        candidates.append({'host': host, 'port': port, 'entry_ip': ip, 'source_country_code': row.get('CountryShort', '').upper()})
    # Only prioritize by advertised country; assign exit country from observation.
    return sorted(candidates, key=lambda n: n['source_country_code'] not in target_countries())

def check_one(node, checker, token):
    result = {**node, 'checked_at': utcnow(), 'success': False}
    try:
        response = requests.get(checker, params={'sstp': f"vpn:vpn@{node['host']}:{node['port']}"}, headers={'Authorization': f'Bearer {token}'}, timeout=180 if os.environ.get('CHECK_BACKEND') == 'node-local' else 45, allow_redirects=False)
        if response.status_code != 200:
            result['error'] = f'Checker HTTP {response.status_code}'
            return result
        payload = response.json()
        if payload.get('success') is not True:
            result['error'] = str(payload.get('error', 'SSTP check failed'))[:300]
            if os.environ.get('CHECK_BACKEND') == 'node-local':
                result['observations'] = payload.get('observations', [])
            return result
        exit_info = payload.get('exit') or {}
        expected_evidence = ('SSTP tunnel to two certificate-validated independent HTTPS exit services'
                             if os.environ.get('CHECK_BACKEND') == 'node-local'
                             else 'SSTP tunnel to nonce-bound HMAC-authenticated Cloudflare echo')
        if not public_ip(exit_info.get('ip')) or payload.get('evidence') != expected_evidence:
            result['error'] = 'Missing authenticated public exit IP'
            return result
        if os.environ.get('CHECK_BACKEND') == 'node-local':
            observations = payload.get('observations') or []
            if (len(observations) != 3 or {o.get('observer') for o in observations} != {'ipwhois', 'ipify'} or
                    any(o.get('ip') != exit_info['ip'] or o.get('certificate_verified') is not True for o in observations)):
                result['error'] = 'Missing independent certificate-verified repeated tunnel observations'
                return result
            result.update(observations=observations, stability=payload.get('stability'))
        result.update(success=True, exit=exit_info, latency_ms=payload.get('responseTime'), evidence=payload['evidence'], residential='unknown', risk_score=None, household_device='unknown', ip_cleanliness='unknown')
    except (requests.RequestException, ValueError) as exc:
        result['error'] = type(exc).__name__
    return result

def crosscheck(result):
    ip = result['exit']['ip']
    evidence, errors = {}, []
    for name, url in [('ipwhois', f'https://ipwho.is/{ip}'), ('ipapi', f'https://api.ipapi.is/?q={ip}')]:
        try:
            response = requests.get(url, timeout=20, allow_redirects=False)
            response.raise_for_status()
            data = response.json()
            if data.get('ip') != ip or data.get('success') is False or data.get('error'):
                raise ValueError('Metadata query unsuccessful')
            if name == 'ipwhois':
                evidence[name] = {'ip': ip, 'country_code': data.get('country_code'), 'asn': asn_number((data.get('connection') or {}).get('asn')), 'isp': (data.get('connection') or {}).get('isp')}
            else:
                asn = data.get('asn') or {}
                evidence[name] = {'ip': ip, 'country_code': (data.get('location') or {}).get('country_code'), 'asn': asn_number(asn.get('asn')), 'org': asn.get('org'), 'type': asn.get('type'), 'is_datacenter': data.get('is_datacenter'), 'is_proxy': data.get('is_proxy'), 'is_vpn': data.get('is_vpn'), 'is_tor': data.get('is_tor'), 'is_abuser': data.get('is_abuser'), 'abuser_score': (data.get('company') or {}).get('abuser_score')}
        except (requests.RequestException, ValueError) as exc:
            errors.append(f'{name}: {type(exc).__name__}')
    result['metadata'], result['metadata_errors'] = evidence, errors
    observed_asn = asn_number((result['exit'].get('asn') or {}).get('asn'))
    country = result['exit'].get('country_code')
    result['exit_crosschecked'] = (len(evidence) == 2 and bool(country) and observed_asn is not None and all(e['country_code'] == country and e['asn'] == observed_asn for e in evidence.values()))
    result['verified_us_exit'] = result['exit_crosschecked'] and country == 'US'
    ipapi = evidence.get('ipapi', {})
    result['residential'] = classify_network(ipapi.get('is_datacenter'), ipapi.get('type'), ipapi.get('org', ''))
    result['country_code'] = country
    result['target_country_allowed'] = country in target_countries()
    result['verified_target_exit'] = result['exit_crosschecked'] and result['target_country_allowed']
    result['risk_status'] = risk_status(ipapi)
    result['risk_score'] = None  # Provider abuser_score is not a fraud score.
    return result

def build_nodes_text(results, edge):
    if not re.fullmatch(r'(?:[a-zA-Z0-9.-]+|\[[a-fA-F0-9:]+\]):443', edge):
        raise ValueError('Invalid test edge endpoint')
    labels = {'residential': '住宅ISP候选', 'datacenter': '机房', 'unknown': '未知'}
    return ''.join(f"{edge}#{r['country_code']}-{labels[r['residential']]}-{i:02d}$sstp://vpn:vpn@{r['host']}:{r['port']}\n" for i, r in enumerate(results, 1))

def main():
    report = {'started_at': utcnow(), 'status': 'failed', 'results': [], 'published': False}
    try:
        report['target_countries'] = sorted(target_countries())
        checker, token = os.environ.get('CHECK_WORKER', ''), os.environ.get('CHECK_TOKEN', '')
        parsed = urlsplit(checker)
        remote_worker = parsed.scheme == 'https' and parsed.hostname and parsed.hostname.endswith('.workers.dev')
        isolated_node = (os.environ.get('CHECK_BACKEND') == 'node-local' and
                         os.environ.get('GITHUB_ACTIONS') == 'true' and sys.platform == 'linux' and
                         parsed.scheme == 'http' and parsed.hostname == '127.0.0.1' and parsed.port is not None)
        if not (remote_worker or isolated_node) or parsed.path != '/check' or parsed.query or parsed.username or parsed.fragment or not token:
            raise ValueError('Missing or invalid independent checker configuration')
        if any(PUBLIC.glob('*')):
            raise ValueError('Output directory must be fresh; refusing stale results')
        limit, concurrency = int(os.environ.get('MAX_CHECK_NODES', '10')), int(os.environ.get('CHECK_CONCURRENCY', '2'))
        if not 1 <= limit <= 10 or not 1 <= concurrency <= 2:
            raise ValueError('Manual test budget exceeded')
        verify_checker_health(checker)
        response = requests.get(SOURCE, timeout=30, allow_redirects=False)
        response.raise_for_status()
        all_candidates = parse_candidates(response.text)
        candidates = all_candidates[:limit]
        report.update(source=SOURCE, source_candidates=len(all_candidates), checked=len(candidates), concurrency=concurrency)
        if not candidates:
            raise ValueError('No valid official SSTP candidates')
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            report['results'] = list(pool.map(lambda n: check_one(n, checker, token), candidates))
        successful = [r for r in report['results'] if r['success']]
        if not successful:
            raise ValueError('All SSTP checks failed; no result will be published')
        for result in successful:
            crosscheck(result)
        verified = [r for r in successful if eligible_exit(r)]
        if not verified:
            raise ValueError('No crosschecked target-country exits with complete unflagged risk indicators; publication blocked')
        text = build_nodes_text(verified, os.environ.get('EDGE_HOSTS', ''))
        if not text.strip():
            raise ValueError('Empty nodes output')
        report.update(status='success', checked_at=utcnow(), success=len(successful), crosschecked=sum(r['exit_crosschecked'] for r in successful), qualified=len(verified), qualified_residential=sum(r['residential']=='residential' for r in verified), verified_us=sum(r['verified_us_exit'] for r in verified))
        PUBLIC.mkdir(parents=True, exist_ok=True)
        (PUBLIC / 'nodes.txt').write_text(text, encoding='utf-8')
        (PUBLIC / 'data.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        (PUBLIC / 'index.html').write_text((ROOT / 'web' / 'index.html').read_text(encoding='utf-8'), encoding='utf-8')
        print(json.dumps({k: report[k] for k in ('status', 'checked', 'success', 'crosschecked', 'verified_us')}))
        return 0
    except Exception as exc:
        report['error'] = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
        print('FAILED: ' + report['error'])
        return 1
    finally:
        report['finished_at'] = utcnow()
        DIAGNOSTICS.mkdir(parents=True, exist_ok=True)
        (DIAGNOSTICS / 'run.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')

if __name__ == '__main__':
    sys.exit(main())
