"""Envelope e conferência de respostas da API de homologação, sem rede."""
import base64
import gzip
import hashlib
import io
import os
import re
from functools import lru_cache

from cryptography import x509
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from lxml import etree

from nfse_core.preflight import CNPJ, MUNICIPIO, NS, SCHEMA_PATH
from nfse_core.signature import DS, PROFILES, ENVELOPED, _canonical, _algorithms

MAX_XML = 512 * 1024


class ProtocolError(ValueError):
    pass


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch('DPS' + MUNICIPIO + '2' + CNPJ + r'[0-9]{20}', value):
        raise ProtocolError('Identificador fora do escopo de homologação.')
    return value


def pack(xml):
    if not isinstance(xml, bytes) or not 0 < len(xml) <= MAX_XML:
        raise ProtocolError('Documento fora do limite.')
    return base64.b64encode(gzip.compress(xml, mtime=0)).decode('ascii')


def unpack(encoded):
    try:
        if not isinstance(encoded, str) or len(encoded) > 1500000:
            raise ValueError()
        compressed = base64.b64decode(encoded, validate=True)
        with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as source:
            xml = source.read(MAX_XML + 1)
        if not 0 < len(xml) <= MAX_XML:
            raise ValueError()
        return xml
    except Exception:
        raise ProtocolError('Documento compactado inválido ou fora do limite.') from None


def seal(xml, key, dps_id, kind):
    identifier(dps_id)
    if kind not in ('dps', 'nfse') or not isinstance(xml, bytes) or not 0 < len(xml) <= MAX_XML:
        raise ProtocolError('Envelope inválido.')
    nonce = os.urandom(12)
    aad = ('w2-nfse-homologacao:v1:' + kind + ':' + dps_id).encode('ascii')
    return {'cifrado': base64.b64encode(AESGCM(key).encrypt(nonce, xml, aad)).decode('ascii'),
        'nonce': base64.b64encode(nonce).decode('ascii'), 'sha256': hashlib.sha256(xml).hexdigest()}


def unseal(envelope, key, dps_id, kind):
    try:
        identifier(dps_id)
        if kind not in ('dps', 'nfse') or len(envelope['cifrado']) > 1500000:
            raise ValueError()
        nonce = base64.b64decode(envelope['nonce'], validate=True)
        if len(nonce) != 12:
            raise ValueError()
        aad = ('w2-nfse-homologacao:v1:' + kind + ':' + dps_id).encode('ascii')
        xml = AESGCM(key).decrypt(nonce, base64.b64decode(envelope['cifrado'], validate=True), aad)
        if not 0 < len(xml) <= MAX_XML or hashlib.sha256(xml).hexdigest() != envelope['sha256']:
            raise ValueError()
        return xml
    except Exception:
        raise ProtocolError('Não foi possível conferir o documento protegido.') from None


def parse_xml(xml):
    try:
        if not isinstance(xml, bytes) or not 0 < len(xml) <= MAX_XML:
            raise ValueError()
        root = etree.fromstring(xml, etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False))
        ids = root.xpath('//@Id | //@id | //@ID')
        if root.getroottree().docinfo.doctype or any(isinstance(e, etree._Entity) for e in root.iter()) or len(set(ids)) != len(ids):
            raise ValueError()
        return root
    except Exception:
        raise ProtocolError('XML inválido.') from None


@lru_cache(maxsize=1)
def nfse_schema():
    return etree.XMLSchema(etree.parse(str(SCHEMA_PATH.parent / 'NFSe_v1.01.xsd'), etree.XMLParser(no_network=True)))


def _verify_nfse_signature(root, info):
    # A procedência vem do HTTPS autenticado da Sefin; aqui se confere integridade,
    # sem afirmar validação da cadeia ICP-Brasil ou consulta de revogação local.
    try:
        signature = root.find('{' + DS + '}Signature')
        si = signature.find('{' + DS + '}SignedInfo')
        profile, suite = si[0].get('Algorithm'), si[1].get('Algorithm')
        if profile not in PROFILES:
            raise ValueError()
        digest, algorithm, digest_uri = _algorithms(suite, profile)
        reference = si[2]
        def names(parent, expected):
            if [e.tag for e in parent] != ['{' + DS + '}' + n for n in expected]:
                raise ValueError()
        names(signature, ['SignedInfo', 'SignatureValue', 'KeyInfo'])
        names(si, ['CanonicalizationMethod', 'SignatureMethod', 'Reference'])
        names(reference, ['Transforms', 'DigestMethod', 'DigestValue'])
        names(reference[0], ['Transform', 'Transform'])
        if (reference.get('URI') != '#' + info.get('Id') or reference[1].get('Algorithm') != digest_uri
            or [e.get('Algorithm') for e in reference[0]] != [ENVELOPED, profile]):
            raise ValueError()
        if any(len(e) for e in [si[0], si[1], *reference[0], reference[1]]):
            raise ValueError()
        if digest(_canonical(info, profile)).digest() != base64.b64decode(reference[2].text, validate=True):
            raise ValueError()
        cert_node = signature.find('{' + DS + '}KeyInfo/{' + DS + '}X509Data/{' + DS + '}X509Certificate')
        cert = x509.load_der_x509_certificate(base64.b64decode(cert_node.text, validate=True))
        cert.public_key().verify(base64.b64decode(signature[1].text, validate=True), _canonical(si, profile), padding.PKCS1v15(), algorithm)
    except Exception:
        raise ProtocolError('Assinatura da resposta não conferida.') from None


def validate_authorization(response, expected_xml, expected_dps_id):
    """Somente retorno obtido da Sefin via mTLS pode ser passado pelo chamador."""
    identifier(expected_dps_id)
    try:
        if not isinstance(response, dict) or type(response.get('tipoAmbiente')) is not int or response['tipoAmbiente'] != 2:
            raise ValueError()
        if response.get('idDps') != expected_dps_id or not re.fullmatch(r'[0-9]{50}', response.get('chaveAcesso', '')):
            raise ValueError()
        xml = unpack(response['nfseXmlGZipB64'])
        root, expected = parse_xml(xml), parse_xml(expected_xml)
        nfse_schema().assertValid(root)
        info = root.find('{' + NS + '}infNFSe')
        actual_dps = info.find('{' + NS + '}DPS/{' + NS + '}infDPS')
        original_dps = expected.find('{' + NS + '}infDPS')
        def value(path):
            nodes = info.findall(path, {'n': NS})
            if len(nodes) != 1:
                raise ValueError()
            return nodes[0].text
        if (root.tag != '{' + NS + '}NFSe' or info.get('Id') != 'NFS' + response['chaveAcesso']
            or value('n:cStat') != '100' or value('n:emit/n:CNPJ') != CNPJ
            or actual_dps is None or actual_dps.get('Id') != expected_dps_id
            or actual_dps.find('{' + NS + '}tpAmb').text != '2'
            or etree.tostring(actual_dps, method='c14n', exclusive=True) != etree.tostring(original_dps, method='c14n', exclusive=True)):
            raise ValueError()
        _verify_nfse_signature(root, info)
        return xml, response['chaveAcesso']
    except Exception:
        raise ProtocolError('Retorno não comprovou a autorização desta DPS de homologação.') from None
