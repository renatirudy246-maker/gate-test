import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock
import vpngate as gate

class PipelineTests(unittest.TestCase):
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
            with patch.dict(os.environ, {'CHECK_WORKER':'https://gate-checker-test.example.workers.dev/check','CHECK_TOKEN':'unit-test-only'}), patch.object(gate,'PUBLIC',public), patch.object(gate,'DIAGNOSTICS',diag), patch.object(gate.requests,'get',return_value=response), patch.object(gate,'parse_candidates',return_value=[node]), patch.object(gate,'check_one',return_value={'success':False,'error':'test failure'}):
                self.assertEqual(gate.main(), 1)
                self.assertFalse(public.exists())
                report = json.loads((diag/'run.json').read_text(encoding='utf8'))
                self.assertEqual(report['status'], 'failed')
                self.assertNotIn('unit-test-only', json.dumps(report))

    def test_us_not_assigned_from_entry(self):
        result = {'exit': {'ip':'1.1.1.1','country_code':'JP','asn':{'asn':13335}},'source_country_code':'US'}
        with patch.object(gate.requests,'get',side_effect=gate.requests.RequestException()):
            gate.crosscheck(result)
        self.assertFalse(result['verified_us_exit'])
        self.assertEqual(result['country_code'], 'JP')
        self.assertIsNone(result['risk_score'])

if __name__ == '__main__':
    unittest.main()
