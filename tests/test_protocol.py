import base64
import copy
import hashlib
import os
import unittest

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import pkcs12
from lxml import etree

from nfse_core import protocol as p
from nfse_core.preparation import build_reserved_dps
from nfse_core.preflight import NS, CNPJ, element
from nfse_core.signature import DS, INCLUSIVE, RSA_SHA1, EXCLUSIVE, RSA_SHA256, SHA256, ENVELOPED, sign_homologation_dps, verify_homologation_dps
from tests.test_a1 import create_a1
from tests import test_preparation


def synthetic_nfse(dps, private_key, certificate):
    """NFS-e inteiramente sintética, com assinatura sintética, para verificar XSD."""
    key = '15008002' + CNPJ + '0' * 28
    root = etree.Element('{' + NS + '}NFSe', nsmap={None: NS}, versao='1.01')
    info = element(root, 'infNFSe');info.set('Id', 'NFS' + key)
    for name, value in [('xLocEmi','Cidade teste'),('xLocPrestacao','Cidade teste'),('nNFSe','1'),('xTribNac','Servico teste'),
        ('verAplic','teste'),('ambGer','2'),('tpEmis','1'),('cStat','100'),('dhProc','2026-10-30T12:00:00-03:00'),('nDFSe','1')]:
        element(info,name,value)
    provider=element(info,'emit');element(provider,'CNPJ',CNPJ);element(provider,'xNome','Empresa sintetica')
    address=element(provider,'enderNac')
    for name,value in [('xLgr','Rua teste'),('nro','1'),('xBairro','Bairro teste'),('cMun','1500800'),('UF','PA'),('CEP','67015760')]:element(address,name,value)
    element(element(info,'valores'),'vLiq','15169.50')
    info.append(etree.fromstring(dps))
    signature=etree.SubElement(root,'{'+DS+'}Signature',nsmap={None:DS})
    def add(parent,name,text=None,**attrs):
        node=etree.SubElement(parent,'{'+DS+'}'+name,**attrs);node.text=text;return node
    canonical=lambda n:etree.tostring(n,method='c14n',exclusive=True,with_comments=False)
    si=add(signature,'SignedInfo');add(si,'CanonicalizationMethod',Algorithm=EXCLUSIVE);add(si,'SignatureMethod',Algorithm=RSA_SHA256)
    ref=add(si,'Reference',URI='#'+info.get('Id'));trans=add(ref,'Transforms')
    add(trans,'Transform',Algorithm=ENVELOPED);add(trans,'Transform',Algorithm=EXCLUSIVE);add(ref,'DigestMethod',Algorithm=SHA256)
    add(ref,'DigestValue',base64.b64encode(hashlib.sha256(canonical(info)).digest()).decode())
    add(signature,'SignatureValue',base64.b64encode(private_key.sign(canonical(si),padding.PKCS1v15(),hashes.SHA256())).decode())
    add(add(add(signature,'KeyInfo'),'X509Data'),'X509Certificate',base64.b64encode(certificate.public_bytes(serialization.Encoding.DER)).decode())
    return etree.tostring(root),key


class ProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        a1=create_a1();cls.private,cls.cert,_=pkcs12.load_key_and_certificates(base64.b64decode(a1['pfx_base64']),a1['senha'].encode())
    def setUp(self):
        self.reservation=test_preparation.PreparationTests().reservation()
        xml=build_reserved_dps(self.reservation)
        self.dps=sign_homologation_dps(xml,self.private,self.cert,expected_dps_id=self.reservation['dps_id'],profile=INCLUSIVE,suite=RSA_SHA1)
        self.nfse,self.access=synthetic_nfse(self.dps,self.private,self.cert)
        self.response={'tipoAmbiente':2,'idDps':self.reservation['dps_id'],'chaveAcesso':self.access,'nfseXmlGZipB64':p.pack(self.nfse)}
    def test_legacy_signature_is_explicit_and_verifies_after_serialization(self):
        self.assertTrue(verify_homologation_dps(self.dps,self.cert,expected_dps_id=self.reservation['dps_id'],profile=INCLUSIVE,suite=RSA_SHA1))
        self.assertNotIn(b'<ds:',self.dps)
        with self.assertRaises(ValueError):verify_homologation_dps(self.dps,self.cert,expected_dps_id=self.reservation['dps_id'],profile=EXCLUSIVE)
        signature=etree.fromstring(self.dps).find('{'+DS+'}Signature')
        self.cert.public_key().verify(base64.b64decode(signature.find('{'+DS+'}SignatureValue').text),
            etree.tostring(signature.find('{'+DS+'}SignedInfo'),method='c14n',exclusive=False,with_comments=False),padding.PKCS1v15(),hashes.SHA1())
    def test_authorization_matches_signed_dps_and_official_xsd(self):
        p.nfse_schema().assertValid(etree.fromstring(self.nfse))
        xml,key=p.validate_authorization(self.response,self.dps,self.reservation['dps_id'])
        self.assertEqual(xml,self.nfse);self.assertEqual(key,self.access)
    def test_cipher_is_bound_to_kind_id_key_and_digest(self):
        key=os.urandom(32);identity=self.reservation['dps_id'];sealed=p.seal(self.dps,key,identity,'dps')
        self.assertEqual(p.unseal(sealed,key,identity,'dps'),self.dps)
        for changed,wrong_key,wrong_id,kind in [(sealed,os.urandom(32),identity,'dps'),(sealed,key,identity,'nfse'),(sealed,key,identity[:-1]+'9','dps'),({**sealed,'sha256':'0'*64},key,identity,'dps')]:
            with self.assertRaises(p.ProtocolError):p.unseal(changed,wrong_key,wrong_id,kind)
        self.assertNotEqual(sealed['nonce'],p.seal(self.dps,key,identity,'dps')['nonce'])
    def test_gzip_bombs_malformed_base64_and_entities_are_blocked(self):
        self.assertEqual(p.unpack(p.pack(self.dps)),self.dps)
        for value in ['bad',base64.b64encode(b'not-gzip').decode(),base64.b64encode(__import__('gzip').compress(b'x'*(p.MAX_XML+1))).decode()]:
            with self.assertRaises(p.ProtocolError):p.unpack(value)
        with self.assertRaises(p.ProtocolError):p.parse_xml(b'<!DOCTYPE x [<!ENTITY a SYSTEM "file:///etc/passwd">]><x>&a;</x>')
    def test_foreign_production_or_mismatched_authorization_never_passes(self):
        for changes in [{'tipoAmbiente':1},{'tipoAmbiente':True},{'idDps':'wrong'},{'chaveAcesso':'1'*50},{'nfseXmlGZipB64':p.pack(b'<NFSe/>')}]:
            with self.assertRaises(p.ProtocolError):p.validate_authorization({**self.response,**changes},self.dps,self.reservation['dps_id'])
        for old,new in [(b'15169.50',b'15169.51'),(b'<cStat>100</cStat>',b'<cStat>101</cStat>')]:
            with self.assertRaises(p.ProtocolError):p.validate_authorization({**self.response,'nfseXmlGZipB64':p.pack(self.nfse.replace(old,new))},self.dps,self.reservation['dps_id'])


if __name__=='__main__':unittest.main()
