"""Conferência independente da assinatura em Java; não usa o A1 real."""
import base64
import copy
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives.serialization import pkcs12, Encoding
from lxml import etree
from nfse_core import signature as s
from nfse_core.preflight import NS
from nfse_core.preparation import build_reserved_dps
from tests.test_a1 import create_a1
from tests import test_preparation


@unittest.skipUnless(shutil.which('java'), 'Oráculo independente requer Java 17 com jdk.compiler')
class SignatureInteropTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        modules = subprocess.run(['java', '--list-modules'], capture_output=True, text=True)
        if modules.returncode or 'jdk.compiler@' not in modules.stdout:
            raise unittest.SkipTest('Java com compilador necessário para executar o oráculo')
        a = create_a1()
        cls.key, cls.cert, _ = pkcs12.load_key_and_certificates(base64.b64decode(a['pfx_base64']), a['senha'].encode())
        cls.oracle = Path(__file__).parent / 'java' / 'VerifyDps.java'
    def setUp(self):
        self.reservation = test_preparation.PreparationTests().reservation()
        self.xml = build_reserved_dps(self.reservation)
    def sign(self, xml=None, profile=s.INCLUSIVE, suite=s.RSA_SHA1):
        return s.sign_homologation_dps(xml or self.xml, self.key, self.cert,
            expected_dps_id=self.reservation['dps_id'], profile=profile, suite=suite)
    def oracle_result(self, xml):
        with tempfile.TemporaryDirectory() as directory:
            d = Path(directory); (d/'dps.xml').write_bytes(xml)
            (d/'cert.pem').write_bytes(self.cert.public_bytes(Encoding.PEM))
            result = subprocess.run(['java', str(self.oracle), str(d/'dps.xml'), str(d/'cert.pem')],
                                    capture_output=True, text=True, timeout=20, check=True)
        return dict(line.split('=', 1) for line in result.stdout.strip().splitlines())
    def test_inclusive_legacy_signature_passes_independent_digest_and_rsa(self):
        self.assertEqual(self.oracle_result(self.sign()), {'core':'true','signature':'true','reference':'true'})
    def test_sha256_profiles_remain_interoperable(self):
        for profile in [s.INCLUSIVE, s.EXCLUSIVE, s.EXCLUSIVE_COMMENTS]:
            with self.subTest(profile=profile):
                self.assertEqual(self.oracle_result(self.sign(profile=profile, suite=s.RSA_SHA256))['core'], 'true')
    def test_old_attached_subtree_canonicalization_is_detected(self):
        def old(node, profile):
            exclusive, comments = s.PROFILES[profile]
            return etree.tostring(node, method='c14n', exclusive=exclusive, with_comments=comments)
        with patch.object(s, '_canonical', side_effect=old):
            bad = self.sign()
        self.assertEqual(self.oracle_result(bad)['core'], 'false')
        with self.assertRaises(s.SignatureError):
            s.verify_homologation_dps(bad,self.cert,expected_dps_id=self.reservation['dps_id'],profile=s.INCLUSIVE,suite=s.RSA_SHA1)
    def test_inherited_namespaces_and_xml_language_are_preserved(self):
        old = etree.fromstring(self.xml)
        root = etree.Element(old.tag,nsmap={None:NS,'audit':'urn:synthetic:audit'})
        root.attrib.update(old.attrib);root.set('{http://www.w3.org/XML/1998/namespace}lang','pt-BR')
        root.extend(copy.deepcopy(list(old)))
        self.assertEqual(self.oracle_result(self.sign(etree.tostring(root)))['core'], 'true')
    def test_changed_service_fails_independent_reference_verification(self):
        root=etree.fromstring(self.sign());root.xpath('//*[local-name()="vServ"]')[0].text='1.00'
        self.assertEqual(self.oracle_result(etree.tostring(root))['reference'],'false')
