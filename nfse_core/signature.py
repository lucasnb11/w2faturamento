"""Assinatura XMLDSig local, ainda sem homologação com a Sefin Nacional.

Sem acesso ao banco, às variáveis do servidor, à rede ou a arquivos de chaves.
O chamador deverá reservar uma DPS de homologação antes de usar o componente.
O perfil de canonicalização é obrigatório: não se infere o padrão da DPS a
partir da assinatura de uma NFS-e emitida pelo Emissor Web.
"""
import base64
from datetime import datetime, timezone
import hashlib
import hmac
import re

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from lxml import etree

from api.nfse.certificado import certificate_cnpj
from nfse_core.preflight import CNPJ, MUNICIPIO, NS

DS = 'http://www.w3.org/2000/09/xmldsig#'
RSA_SHA256 = 'http://www.w3.org/2001/04/xmldsig-more#rsa-sha256'
SHA256 = 'http://www.w3.org/2001/04/xmlenc#sha256'
RSA_SHA1 = DS + 'rsa-sha1'
SHA1 = DS + 'sha1'
INCLUSIVE = 'http://www.w3.org/TR/2001/REC-xml-c14n-20010315'
ENVELOPED = DS + 'enveloped-signature'
EXCLUSIVE = 'http://www.w3.org/2001/10/xml-exc-c14n#'
EXCLUSIVE_COMMENTS = EXCLUSIVE + 'WithComments'
PROFILES = {EXCLUSIVE: (True, False), EXCLUSIVE_COMMENTS: (True, True), INCLUSIVE: (False, False)}
MAX_XML = 512 * 1024


class SignatureError(ValueError):
    """Erro sem conteúdo de XML, senha, chave ou certificado."""


def _canonical(node, profile):
    if not isinstance(profile, str) or profile not in PROFILES:
        raise SignatureError('Perfil de canonicalização não suportado.')
    exclusive, comments = PROFILES[profile]
    return etree.tostring(node, method='c14n', exclusive=exclusive, with_comments=comments)


def _algorithms(suite, profile):
    # SHA-1 restrito ao perfil legado explicitamente escolhido para homologação.
    if suite == RSA_SHA1 and profile == INCLUSIVE:
        return hashlib.sha1, hashes.SHA1(), SHA1
    if suite == RSA_SHA256 and profile in PROFILES:
        return hashlib.sha256, hashes.SHA256(), SHA256
    raise SignatureError('Conjunto de algoritmos não suportado.')


def _document(xml, expected_id, signed):
    if not isinstance(xml, bytes) or not 0 < len(xml) <= MAX_XML:
        raise SignatureError('XML ausente ou fora do limite.')
    try:
        root = etree.fromstring(xml, etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False))
        if root.getroottree().docinfo.doctype or any(isinstance(x, etree._Entity) for x in root.iter()):
            raise ValueError()
        info = root.find('{' + NS + '}infDPS')
        if root.tag != '{' + NS + '}DPS' or root.get('versao') != '1.01' or info is None:
            raise ValueError()
        wanted = ['{' + NS + '}infDPS'] + (['{' + DS + '}Signature'] if signed else [])
        if [x.tag for x in root if isinstance(x.tag, str)] != wanted:
            raise ValueError()
        if len(root.xpath('//*[local-name()="Signature"]')) != (1 if signed else 0):
            raise ValueError()
        if not isinstance(expected_id, str) or not re.fullmatch('DPS' + MUNICIPIO + '2' + CNPJ + r'[0-9]{20}', expected_id):
            raise ValueError()
        if info.get('Id') != expected_id or len(root.xpath('//*[@Id or @ID or @id]')) != 1:
            raise ValueError()
        def one(path):
            matches = info.findall(path, {'n': NS})
            if len(matches) != 1 or not matches[0].text:
                raise ValueError()
            return matches[0].text
        if one('n:tpAmb') != '2' or one('n:prest/n:CNPJ') != CNPJ or one('n:tpEmit') != '1':
            raise ValueError()
        series, number = one('n:serie'), one('n:nDPS')
        if not re.fullmatch(r'[0-9]{1,5}', series) or not re.fullmatch(r'[1-9][0-9]{0,14}', number):
            raise ValueError()
        composed = 'DPS' + one('n:cLocEmi') + '2' + CNPJ + series.zfill(5) + number.zfill(15)
        if composed != expected_id:
            raise ValueError()
        return root, info
    except (etree.XMLSyntaxError, ValueError, TypeError, KeyError):
        raise SignatureError('DPS inválida, identificação divergente ou ambiente não permitido.') from None


def _certificate(cert):
    try:
        now = datetime.now(timezone.utc)
        if not isinstance(cert, x509.Certificate) or certificate_cnpj(cert) != CNPJ:
            raise ValueError()
        if not cert.not_valid_before_utc <= now < cert.not_valid_after_utc:
            raise ValueError()
        key = cert.public_key()
        if not isinstance(key, rsa.RSAPublicKey) or key.key_size < 2048:
            raise ValueError()
        try:
            if not cert.extensions.get_extension_for_class(x509.KeyUsage).value.digital_signature:
                raise ValueError()
        except x509.ExtensionNotFound:
            pass
        return key
    except Exception:
        raise SignatureError('Certificado incompatível com a assinatura da DPS da W2.') from None


def _add(parent, name, text=None, **attributes):
    el = etree.SubElement(parent, '{' + DS + '}' + name, **attributes)
    if text is not None:
        el.text = text
    return el


def sign_homologation_dps(xml, private_key, certificate, *, expected_dps_id, profile, suite=RSA_SHA256):
    """Assina apenas DPS de homologação; não constitui reserva ou transmissão."""
    root, info = _document(xml, expected_dps_id, signed=False)
    public_key = _certificate(certificate)
    if not isinstance(private_key, rsa.RSAPrivateKey) or private_key.public_key().public_numbers() != public_key.public_numbers():
        raise SignatureError('A chave não corresponde ao certificado informado.')
    digest_function, hash_algorithm, digest_uri = _algorithms(suite, profile)
    digest = base64.b64encode(digest_function(_canonical(info, profile)).digest()).decode('ascii')
    signature = etree.SubElement(root, '{' + DS + '}Signature', nsmap={None: DS})
    signed_info = _add(signature, 'SignedInfo')
    _add(signed_info, 'CanonicalizationMethod', Algorithm=profile)
    _add(signed_info, 'SignatureMethod', Algorithm=suite)
    ref = _add(signed_info, 'Reference', URI='#' + expected_dps_id)
    transforms = _add(ref, 'Transforms')
    _add(transforms, 'Transform', Algorithm=ENVELOPED)
    _add(transforms, 'Transform', Algorithm=profile)
    _add(ref, 'DigestMethod', Algorithm=digest_uri)
    _add(ref, 'DigestValue', digest)
    value = private_key.sign(_canonical(signed_info, profile), padding.PKCS1v15(), hash_algorithm)
    _add(signature, 'SignatureValue', base64.b64encode(value).decode('ascii'))
    data = _add(_add(signature, 'KeyInfo'), 'X509Data')
    _add(data, 'X509Certificate', base64.b64encode(certificate.public_bytes(serialization.Encoding.DER)).decode('ascii'))
    encoded = etree.tostring(root, encoding='UTF-8', xml_declaration=True, pretty_print=False)
    verify_homologation_dps(encoded, certificate, expected_dps_id=expected_dps_id, profile=profile, suite=suite)
    return encoded


def verify_homologation_dps(xml, trusted_certificate, *, expected_dps_id, profile, suite=RSA_SHA256):
    """Confere integridade com certificado esperado, sem validar cadeia ou revogação."""
    root, info = _document(xml, expected_dps_id, signed=True)
    key = _certificate(trusted_certificate)
    digest_function, hash_algorithm, digest_uri = _algorithms(suite, profile)
    try:
        signature = root.find('{' + DS + '}Signature')
        signed_info = signature.find('{' + DS + '}SignedInfo')
        def nodes(parent, names):
            if [x.tag for x in parent] != ['{' + DS + '}' + name for name in names]:
                raise ValueError()
        nodes(signature, ['SignedInfo', 'SignatureValue', 'KeyInfo'])
        nodes(signed_info, ['CanonicalizationMethod', 'SignatureMethod', 'Reference'])
        if signed_info[0].get('Algorithm') != profile or signed_info[1].get('Algorithm') != suite:
            raise ValueError()
        ref = signed_info[2]
        nodes(ref, ['Transforms', 'DigestMethod', 'DigestValue'])
        nodes(ref[0], ['Transform', 'Transform'])
        if ref.get('URI') != '#' + expected_dps_id or [x.get('Algorithm') for x in ref[0]] != [ENVELOPED, profile] or ref[1].get('Algorithm') != digest_uri:
            raise ValueError()
        # Não executar XPath, URLs ou transformações fornecidas pelo XML.
        if any(len(el) for el in [signed_info[0], signed_info[1], *ref[0], ref[1]]):
            raise ValueError()
        actual = digest_function(_canonical(info, profile)).digest()
        if not hmac.compare_digest(actual, base64.b64decode(ref[2].text, validate=True)):
            raise ValueError()
        cert_data = signature.find('{' + DS + '}KeyInfo/{' + DS + '}X509Data/{' + DS + '}X509Certificate')
        if cert_data is None or base64.b64decode(cert_data.text, validate=True) != trusted_certificate.public_bytes(serialization.Encoding.DER):
            raise ValueError()
        key.verify(base64.b64decode(signature[1].text, validate=True), _canonical(signed_info, profile), padding.PKCS1v15(), hash_algorithm)
        return True
    except Exception:
        raise SignatureError('Assinatura inválida ou perfil divergente.') from None
