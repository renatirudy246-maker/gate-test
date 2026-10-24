import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock
import vpngate as gate

class PipelineTests(unittest.TestCase):
    def test_target_country_configuration(self):
        self.assertEqual(gate.target_countries(' us, jp,KR,sg '), {'US','JP','KR','SG'})
        for value in ['', 'USA', 'JP,123']:
            with self.assertRaises(ValueError): gate.target_countries(value)

    def test_publication_requires_actual_target_country_and_risk_evidence(self):
        with patch.dict(os.environ, {'TARGET_COUNTRIES':'US,JP,KR,SG'}):
            node = {'exit_crosschecked':True,'country_code':'JP','source_country_code':'US','risk_status':'no_flags_reported','residential':'unknown'}
            self.assertTrue(gate.eligible_exit(node))
            self.assertFalse(gate.eligible_exit({**node,'country_code':'DE'}))
            self.assertFalse(gate.eligible_exit({**node,'country_code':None}))
            self.assertFalse(gate.eligible_exit({**node,'risk_status':'unknown'}))
            self.assertFalse(gate.eligible_exit({**node,'risk_status':'flagged'}))
            self.assertFalse(gate.eligible_exit({**node,'exit_crosschecked':False}))
        self.assertEqual(gate.risk_status({}), 'unknown')
        self.assertEqual(gate.risk_status({'is_abuser':False}), 'unknown')
        self.assertEqual(gate.risk_status({'is_abuser':True}), 'flagged')
    def test_unknown_is_not_residential(self):
        self.assertEqual(gate.classify_network(), 'unknown')
        self.assertEqual(gate.classify_network(False), 'unknown')
        self.assertEqual(gate.classify_network(False, 'hosting', 'Comcast'), 'datacenter')
        self.assertEqual(gate.classify_network(False, 'isp', 'Comcast Cable'), 'residential')
        self.assertEqual(gate.classify_network(False, 'business', 'Verizon'), 'unknown')

    def test_unknown_label_preserved(self):
        result = {'country_code': 'US', 'residential': 'unknown', 'host': 'vpn123456.opengw.net', 'port': 443}
        self.assertIn('US-未知', gate.build_nodes_text([result], 'edgetunnel-test.pages.dev:443'))
        self.assertNotIn('机房', gate.build_nodes_text([result], 'edgetunnel-test.pages.dev:443'))

    def test_private_or_missing_exit_rejected(self):
        for ip in [None, '', '127.0.0.1', '10.1.2.3', '192.0.2.1']:
            self.assertIsNone(gate.public_ip(ip))

    def test_all_checks_failed_leaves_only_diagnostics(self):
        with tempfile.TemporaryDirectory() as temp:
            public, diag = Path(temp) / 'public', Path(temp) / 'diagnostics'
            node = {'host': 'vpn123456.opengw.net', 'port': 443}
            response = Mock(text='source')
            response.status_code = 200
            response.json.return_value = {'service':'gate-checker-test','configured':True}
            with patch.dict(os.environ, {'CHECK_WORKER':'https://gate-checker-test.example.workers.dev/check','CHECK_TOKEN':'unit-test-only'}), patch.object(gate,'PUBLIC',public), patch.object(gate,'DIAGNOSTICS',diag), patch.object(gate.requests,'get',return_value=response), patch.object(gate,'parse_candidates',return_value=[node]), patch.object(gate,'check_one',return_value={'success':False,'error':'test failure'}):
                self.assertEqual(gate.main(), 1)
                self.assertFalse(public.exists())
                report = json.loads((diag/'run.json').read_text(encoding='utf8'))
                self.assertEqual(report['status'], 'failed')
                self.assertNotIn('unit-test-only', json.dumps(report))

    def test_health_failure_prevents_candidate_fetch_and_scanning(self):
        with tempfile.TemporaryDirectory() as temp:
            response = Mock(status_code=500)
            with patch.dict(os.environ, {'CHECK_WORKER':'https://gate-checker-test.example.workers.dev/check','CHECK_TOKEN':'unit-test-only'}), patch.object(gate,'PUBLIC',Path(temp)/'public'), patch.object(gate,'DIAGNOSTICS',Path(temp)/'diagnostics'), patch.object(gate.requests,'get',return_value=response) as get, patch.object(gate,'parse_candidates') as parse, patch.object(gate,'check_one') as check:
                self.assertEqual(gate.main(),1)
                self.assertEqual(get.call_count,1)
                self.assertTrue(get.call_args.args[0].endswith('/health'))
                parse.assert_not_called()
                check.assert_not_called()

    def test_us_not_assigned_from_entry(self):
        result = {'exit': {'ip':'1.1.1.1','country_code':'JP','asn':{'asn':13335}},'source_country_code':'US'}
        with patch.object(gate.requests,'get',side_effect=gate.requests.RequestException()):
            gate.crosscheck(result)
        self.assertFalse(result['verified_us_exit'])
        self.assertEqual(result['country_code'], 'JP')
        self.assertIsNone(result['risk_score'])

if __name__ == '__main__':
    unittest.main()
