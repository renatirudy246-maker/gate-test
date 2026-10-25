import json
import unittest
from pathlib import Path
import performance_candidates as perf
import vpngate as gate

class PerformanceCandidateTests(unittest.TestCase):
    def test_historical_successes_are_hints_and_retested_despite_prior_risk(self):
        document=json.loads((gate.ROOT/'reports/node-scan-40136541061.json').read_text(encoding='utf8'))
        selected=perf.select(document)
        self.assertEqual(len(selected),6)
        self.assertEqual(len({gate.node_key(n) for n in selected}),6)
        self.assertTrue(all(n['candidate_origin']=='previously_measured_success' for n in selected))
        self.assertTrue(all(n['historical_risk_score']==100 for n in selected))

if __name__=='__main__':
    unittest.main()
