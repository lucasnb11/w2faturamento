"""Assinatura com A1s sintéticos. Sem leitura do certificado real da W2."""
import base64
import hashlib
import unittest

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import pkcs12
from lxml import etree

from nfse_core.preflight import build_simulation, schema
from nfse_core.signature import sign_homologation_dps, verify_homologation_dps, SignatureError, DS, EXCLUSIVE, EXCLUSIVE_COMMENTS
from tests.test_a1 import create_a1
from tests.test_preflight import fixture


class SignatureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pfx=create_a1()
        cls.key,cls.cert,_=pkcs12.load_key_and_certificates(base64.b64decode(pfx['pfx_base64']),pfx['senha'].encode())
        other=create_a1()
        cls.other_key,cls.other_cert,_=pkcs12.load_key_and_certificates(base64.b64decode(other['pfx_base64']),other['senha'].encode())
    def setUp(self):
        self.document=build_simulation(fixture())
        self.xml=etree.tostring(self.document)
        self.identifier=self.document[0].get('Id')
    def sign(self, xml=None, profile=EXCLUSIVE):
        return sign_homologation_dps(xml or self.xml,self.key,self.cert,expected_dps_id=self.identifier,profile=profile)
    def verify(self, xml, cert=None, profile=EXCLUSIVE):
        return verify_homologation_dps(xml,cert or self.cert,expected_dps_id=self.identifier,profile=profile)
    def test_both_profiles_roundtrip_and_official_xsd(self):
        for profile in [EXCLUSIVE,EXCLUSIVE_COMMENTS]:
            signed=self.sign(profile=profile)
            self.assertTrue(self.verify(signed,profile=profile))
            schema().assertValid(etree.fromstring(signed))
            self.assertEqual(self.xml,etree.tostring(self.document))
    def test_signature_and_digest_with_independent_primitives(self):
        signed=etree.fromstring(self.sign())
        ns={'ds':DS}
        signature=signed.find('ds:Signature',ns)
        signed_info=signature.find('ds:SignedInfo',ns)
        calculated=hashlib.sha256(etree.tostring(signed[0],method='c14n',exclusive=True,with_comments=False)).digest()
        self.assertEqual(calculated,base64.b64decode(signed_info.find('ds:Reference/ds:DigestValue',ns).text))
        self.cert.public_key().verify(base64.b64decode(signature.find('ds:SignatureValue',ns).text),etree.tostring(signed_info,method='c14n',exclusive=True,with_comments=False),padding.PKCS1v15(),hashes.SHA256())
    def test_altered_service_is_detected(self):
        signed=etree.fromstring(self.sign())
        signed.xpath('//*[local-name()="vServ"]')[0].text='1.00'
        with self.assertRaises(SignatureError):self.verify(etree.tostring(signed))
    def test_pinned_certificate_and_key_pair(self):
        with self.assertRaises(SignatureError):self.verify(self.sign(),cert=self.other_cert)
        with self.assertRaises(SignatureError):
            sign_homologation_dps(self.xml,self.other_key,self.cert,expected_dps_id=self.identifier,profile=EXCLUSIVE)
    def test_no_production_repeated_signature_or_wrong_id(self):
        for xml in [self.xml.replace(b'<tpAmb>2</tpAmb>',b'<tpAmb>1</tpAmb>'),self.sign()]:
            with self.assertRaises(SignatureError):self.sign(xml)
        with self.assertRaises(SignatureError):
            sign_homologation_dps(self.xml,self.key,self.cert,expected_dps_id=self.identifier[:-1]+'9',profile=EXCLUSIVE)
    def test_no_wrapping_entities_external_references_or_unknown_algorithms(self):
        root=etree.fromstring(self.xml)
        root.append(etree.fromstring(etree.tostring(root[0])))
        with self.assertRaises(SignatureError):self.sign(etree.tostring(root))
        with self.assertRaises(SignatureError):self.sign(b'<!DOCTYPE DPS [<!ENTITY x SYSTEM "file:///etc/passwd">]>'+self.xml)
        for profile in ['http://attacker.example/algorithm','http://www.w3.org/2000/09/xmldsig#rsa-sha1']:
            with self.assertRaises(SignatureError):self.sign(profile=profile)
        signed=etree.fromstring(self.sign())
        signed.xpath('//*[local-name()="Reference"]')[0].set('URI','https://attacker.example/data')
        with self.assertRaises(SignatureError):self.verify(etree.tostring(signed))
    def test_comments_and_profile_are_bound_to_signature(self):
        root=etree.fromstring(self.xml);root[0].append(etree.Comment('original'))
        signed=self.sign(etree.tostring(root),profile=EXCLUSIVE_COMMENTS)
        changed=signed.replace(b'<!--original-->',b'<!--changed-->')
        with self.assertRaises(SignatureError):self.verify(changed,profile=EXCLUSIVE_COMMENTS)
        with self.assertRaises(SignatureError):self.verify(signed,profile=EXCLUSIVE)
    def test_identity_of_company_is_checked(self):
        pfx=create_a1(cnpj='11111111000191')
        key,cert,_=pkcs12.load_key_and_certificates(base64.b64decode(pfx['pfx_base64']),pfx['senha'].encode())
        with self.assertRaises(SignatureError):
            sign_homologation_dps(self.xml,key,cert,expected_dps_id=self.identifier,profile=EXCLUSIVE)


if __name__=='__main__':unittest.main()
