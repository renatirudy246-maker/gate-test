import copy
import json
import unittest
from publish_local_snapshot import build,qualified,ROOT

class LocalSnapshotTests(unittest.TestCase):
    def fixture(self):
        rows=json.loads((ROOT/'reports/local-openvpn-diagnosis-20261025.json').read_text())['remote_dns']['results']
        return copy.deepcopy(next(r for r in rows if r.get('browser_usable')))

    def test_search_tls_final_exit_and_complete_downloads_required(self):
        node=self.fixture();self.assertTrue(qualified(node))
        for field,value in [('browser_usable',False),('temporary_process_stopped',False)]:
            altered=copy.deepcopy(node);altered[field]=value;self.assertFalse(qualified(altered))
        for status in (302,403,429):
            altered=copy.deepcopy(node);altered['web_checks'][0]['http']=status;self.assertFalse(qualified(altered))
        altered=copy.deepcopy(node);altered['last_ip_check']['ip']='1.1.1.1';self.assertFalse(qualified(altered))
        altered=copy.deepcopy(node);altered['downloads'][0]['bytes']=1024;self.assertFalse(qualified(altered))
        altered=copy.deepcopy(node);altered['checks'][1]['certificate_verified']=False;self.assertFalse(qualified(altered))

    def test_actual_failed_reconnect_blocks_publication_despite_earlier_search_success(self):
        with self.assertRaisesRegex(ValueError,'fresh-session recheck'):build()
