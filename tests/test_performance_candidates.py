import json
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch
import performance_candidates as candidates
import vpngate as gate


class PerformanceManifestTests(unittest.TestCase):
    def fixture(self):
        return {'format':'gate-performance-candidates-v1', 'source':gate.SOURCE,
                'tls_verified':True, 'source_sha256':'a'*64,
                'fetched_at':datetime.now(timezone.utc).isoformat(),
                'candidates':[{'host':'vpn123.opengw.net','port':443,
                               'entry_ip':'1.1.1.1','source_country_code':'CA'}]}

    def load(self, document):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve()
            folder=root/'candidates'; folder.mkdir()
            path=folder/'unit.json'
            path.write_text(json.dumps(document),encoding='utf-8')
            with patch.object(gate,'ROOT',root):
                return candidates.load_manifest(path)

    def test_six_advertised_countries_supported_without_changing_exit_gate(self):
        for country in ('US','JP','KR','SG','CA','AU'):
            data=self.fixture();data['candidates'][0]['source_country_code']=country
            self.assertEqual(self.load(data)[0]['candidate_origin'],'official_source_snapshot')

    def test_duplicate_private_non_target_and_oversize_rejected(self):
        changes=[]
        for field,value in [('entry_ip','127.0.0.1'),('source_country_code','DE'),('host','example.com'),('port',0)]:
            data=self.fixture();data['candidates'][0][field]=value;changes.append(data)
        for size in (0,2,11):
            data=self.fixture();data['candidates']*=size;changes.append(data)
        for data in changes:
            with self.assertRaises(ValueError):self.load(data)

    def test_stale_naive_or_unverified_source_rejected(self):
        for field,value in [('tls_verified',False),('source','https://example.com'),('source_sha256',''),
                            ('fetched_at',(datetime.now(timezone.utc)-timedelta(hours=7)).isoformat()),
                            ('fetched_at','2026-10-25T12:00:00')]:
            data=self.fixture();data[field]=value
            with self.assertRaises(ValueError):self.load(data)

    def test_outside_repository_path_rejected_before_reading(self):
        with self.assertRaises(ValueError):candidates.load_manifest(Path(tempfile.gettempdir())/'outside.json')
