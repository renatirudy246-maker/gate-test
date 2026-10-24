import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock
from collections import Counter
import vpngate as gate


def qualified_fixture(country='JP'):
    ip, asn = '1.1.1.1', 13335  # Unit fixture, never a measured/published VPN node.
    identity = {'ip': ip, 'country_code': country, 'asn': asn}
    pc = {**identity, 'type': 'Residential', 'risk': 10,
          **{key: False for key in gate.PROXYCHECK_FLAGS}}
    return {'success': True, 'host': 'vpn123.opengw.net', 'port': 443,
            'exit': {'ip': ip, 'country_code': country, 'asn': {'asn': asn}},
            'exit_crosschecked': True, 'country_code': country, 'source_country_code': 'US',
            'residential': 'residential', 'residential_evidence': gate.RESIDENTIAL_EVIDENCE,
            'risk_status': 'no_flags_reported', 'risk_score': 10, 'risk_score_source': 'proxycheck.io',
            'metadata': {'ipwhois': identity.copy(), 'proxycheck': pc}}


def candidate(number, country='JP', port=443):
    return {'host': f'vpn{number}.opengw.net', 'port': port, 'source_country_code': country}


class ResidentialGateTests(unittest.TestCase):
    def test_complete_explicit_residential_evidence_accepts_only_allowed_exits(self):
        with patch.dict(gate.os.environ, {'TARGET_COUNTRIES': 'US,JP,KR,SG'}):
            for country in ('US', 'JP', 'KR', 'SG'):
                with self.subTest(country=country):
                    self.assertTrue(gate.eligible_exit(qualified_fixture(country)))
            self.assertFalse(gate.eligible_exit(qualified_fixture('DE')))

    def test_unknown_datacenter_and_missing_residential_evidence_rejected(self):
        for classification in (None, 'unknown', 'datacenter'):
            node = qualified_fixture()
            node['residential'] = classification
            self.assertFalse(gate.eligible_exit(node))
        for evidence in (None, '', 'ISP name only'):
            node = qualified_fixture()
            node['residential_evidence'] = evidence
            self.assertFalse(gate.eligible_exit(node))
        for allocation in (None, 'Business', 'Hosting', 'Wireless'):
            node = qualified_fixture()
            node['metadata']['proxycheck']['type'] = allocation
            self.assertFalse(gate.eligible_exit(node))

    def test_every_required_raw_flag_must_be_present_and_exactly_false(self):
        for flag in gate.PROXYCHECK_FLAGS:
            for value in (None, True, 0, 'false'):
                with self.subTest(flag=flag, value=value):
                    node = qualified_fixture()
                    node['metadata']['proxycheck'][flag] = value
                    self.assertFalse(gate.eligible_exit(node))
            node = qualified_fixture()
            del node['metadata']['proxycheck'][flag]
            self.assertFalse(gate.eligible_exit(node))

    def test_proxycheck_score_bounds_and_provenance_required(self):
        for score in (0, 25):
            node = qualified_fixture()
            node['risk_score'] = node['metadata']['proxycheck']['risk'] = score
            self.assertTrue(gate.eligible_exit(node))
        for score in (None, False, '0', -1, 25.01, 100, float('nan')):
            node = qualified_fixture()
            node['risk_score'] = node['metadata']['proxycheck']['risk'] = score
            self.assertFalse(gate.eligible_exit(node))
        for change in ({'risk_score': 0}, {'risk_score_source': None}, {'risk_status': 'unknown'}):
            node = qualified_fixture()
            node.update(change)
            self.assertFalse(gate.eligible_exit(node))
        node = qualified_fixture()
        del node['metadata']['proxycheck']['risk']
        self.assertFalse(gate.eligible_exit(node))

    def test_cached_crosscheck_cannot_override_missing_or_conflicting_identity(self):
        for change in ({'exit_crosschecked': False}, {'country_code': 'US'}):
            node = qualified_fixture()
            node.update(change)
            self.assertFalse(gate.eligible_exit(node))
        for field, value in (('ip', '8.8.8.8'), ('asn', 15169), ('country_code', 'US')):
            node = qualified_fixture()
            node['metadata']['proxycheck'][field] = value
            self.assertFalse(gate.eligible_exit(node))
        node = qualified_fixture()
        del node['metadata']['ipwhois']
        self.assertFalse(gate.eligible_exit(node))

    def test_other_provider_positive_flags_veto_publication(self):
        for flag in ('is_proxy', 'is_vpn', 'is_tor', 'is_abuser', 'is_datacenter'):
            node = qualified_fixture()
            node['metadata']['ipapi'] = {**node['metadata']['ipwhois'], flag: True}
            self.assertFalse(gate.eligible_exit(node))

    def test_unknown_successful_exit_cannot_write_subscription(self):
        with tempfile.TemporaryDirectory() as directory:
            result = qualified_fixture()
            result['residential'] = 'unknown'
            response = Mock(status_code=200, text='official source fixture')
            with patch.dict(gate.os.environ, {'CHECK_WORKER':'https://test.workers.dev/check', 'CHECK_TOKEN':'unit-test-only', 'EXCLUDE_REPORTS':''}), \
                    patch.object(gate, 'PUBLIC', Path(directory)/'public'), patch.object(gate, 'DIAGNOSTICS', Path(directory)/'diagnostics'), \
                    patch.object(gate, 'verify_checker_health'), patch.object(gate.requests, 'get', return_value=response), \
                    patch.object(gate, 'parse_candidates', return_value=[candidate(123)]), \
                    patch.object(gate, 'check_one', return_value=result), patch.object(gate, 'crosscheck', side_effect=lambda r:r):
                self.assertEqual(gate.main(), 1)
                self.assertFalse((Path(directory)/'public').exists())
                report = json.loads((Path(directory)/'diagnostics/run.json').read_text())
                self.assertEqual(report['qualified'], 0)


class SecondBatchSelectionTests(unittest.TestCase):
    def test_excludes_previous_failures_case_insensitively_and_balances_four_countries(self):
        nodes = [{**candidate(1, 'US'), 'host':'VPN1.OPENGW.NET'}, candidate(1, 'US', 444)]
        for index, country in enumerate(('US', 'JP', 'KR', 'SG')):
            nodes += [candidate(100*index+n+10, country) for n in range(10)]
        selected, available = gate.select_candidates(nodes, 10, {('vpn1.opengw.net', 443)})
        self.assertEqual(len(selected), 10)
        self.assertNotIn(('vpn1.opengw.net',443), {gate.node_key(n) for n in selected})
        self.assertIn(('vpn1.opengw.net',444), {gate.node_key(n) for n in selected})
        counts = Counter(n['source_country_code'] for n in selected)
        self.assertEqual(counts, {'US':3, 'JP':3, 'KR':2, 'SG':2})
        self.assertEqual(available['KR'], 10)

    def test_missing_country_is_not_fabricated_or_filled_with_non_target(self):
        selected, available = gate.select_candidates([candidate(n,'KR') for n in range(3)]+[candidate(99,'DE')], 10, set())
        self.assertEqual(len(selected), 3)
        self.assertEqual({n['source_country_code'] for n in selected}, {'KR'})
        self.assertEqual(available, {'US':0,'JP':0,'KR':3,'SG':0})

    def test_incomplete_prior_report_is_rejected_and_full_manifest_keeps_failed_nodes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'history.json'
            path.write_text(json.dumps({'original_checked':2, 'results':[candidate(1)]}))
            with self.assertRaises(ValueError):
                gate.load_excluded_nodes([path])
            path.write_text(json.dumps({'original_checked':2, 'results':[candidate(1)],
                                        'tested_nodes':[candidate(1), {**candidate(2),'success':False}]}))
            self.assertEqual(gate.load_excluded_nodes([path]), {('vpn1.opengw.net',443),('vpn2.opengw.net',443)})

    def test_real_first_batch_manifest_contains_all_ten_attempts(self):
        excluded = gate.load_excluded_nodes([gate.ROOT/'reports/node-scan-40136541061.json'])
        self.assertEqual(len(excluded), 10)
        self.assertIn(('vpn622613092.opengw.net',1496), excluded)  # Failed in batch one.
        self.assertIn(('vpn258563631.opengw.net',1423), excluded)  # Failed TLS in batch one.


if __name__ == '__main__':
    unittest.main()
