import json
import unittest
from pathlib import Path
from openvpn_candidates import convert_profile,ROOT

class DirectOpenVPNTests(unittest.TestCase):
    def fixture(self):
        entry=json.loads((ROOT/'candidates/direct-openvpn-20261025.json').read_text())['candidates'][0]
        p=entry['proxy'];m=entry['expected']
        text=f"dev tun\nproto tcp\nremote {p['server']} {p['port']}\ncipher AES-128-CBC\nauth SHA1\n"
        for name in ('ca','cert','key'):text+=f"<{name}>\n{p[name]}\n</{name}>\n"
        return text,{'IP':p['server']},m

    def test_current_core_profile_uses_userspace_stack_and_explicit_ca(self):
        proxy=convert_profile(*self.fixture())
        self.assertEqual(proxy['type'],'openvpn')
        self.assertEqual(proxy['ip-stack'],{'mode':'gvisor'})
        self.assertTrue(proxy['ca'].startswith('-----BEGIN CERTIFICATE-----'))
        self.assertNotIn('skip-cert-verify',proxy)
        for key in ('tun','dns','mixed-port','external-controller','interface-name'):self.assertNotIn(key,proxy)

    def test_remote_private_ports_and_executable_directives_cannot_be_imported(self):
        text,row,m=self.fixture()
        for change in (text+'\nup attacker.sh\n',text.replace('proto tcp','proto udp'),text.replace('remote '+row['IP'],'remote 127.0.0.1'),text.replace('<ca>','<absent>')):
            with self.assertRaises(ValueError):convert_profile(change,row,m)
        for port in (0,65536,m['port']+1):
            altered={**m,'port':port}
            with self.assertRaises(ValueError):convert_profile(text,row,altered)

    def test_candidates_only_embed_official_public_profiles_and_distinct_measured_exits(self):
        doc=json.loads((ROOT/'candidates/direct-openvpn-20261025.json').read_text())
        self.assertEqual(len(doc['candidates']),35)
        self.assertEqual(len({n['expected']['exit_ip'] for n in doc['candidates']}),35)
        self.assertTrue(all(n['proxy']['type']=='openvpn' and n['expected']['country'] in {'US','JP','KR','SG','CA','AU'} for n in doc['candidates']))
