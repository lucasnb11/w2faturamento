"""Certificados sintéticos em memória; estes testes não consultam o Supabase real."""
import base64
import importlib.util
import io
import json
import os
from pathlib import Path
import threading
from datetime import datetime, timedelta, timezone
from http.server import HTTPServer
from unittest import TestCase, main
from unittest.mock import patch
from urllib import error, request

from cryptography import x509
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID, ObjectIdentifier

SPEC = importlib.util.spec_from_file_location('secure_a1', Path(__file__).parents[1] / 'api/nfse/certificado.py')
api = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(api)
UID = '11111111-2222-4333-8444-555555555555'
ADMIN = 'admin-session-token-for-local-tests'
FINANCE = 'finance-session-token-for-local-tests'
ORIGIN = 'https://faturamento.example'


def create_a1(cnpj=api.CNPJ, expired=False, include_key=True, other_name=None):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'CERTIFICADO SINTÉTICO:' + cnpj)])
    now = datetime.now(timezone.utc)
    builder = x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(days=3)).not_valid_after(now + timedelta(days=-1 if expired else 30))
    if other_name:
        encoded = b'\x0c\x0e' + other_name.encode('ascii')
        builder = builder.add_extension(x509.SubjectAlternativeName([x509.OtherName(ObjectIdentifier('2.16.76.1.3.3'), encoded)]), critical=False)
    cert = builder.sign(key, hashes.SHA256())
    password = 'Senha-Sintética-Usada-Somente-Nos-Testes'
    binary = pkcs12.serialize_key_and_certificates(b'local-test', key if include_key else None, cert, None, serialization.BestAvailableEncryption(password.encode()))
    return {'pfx_base64': base64.b64encode(binary).decode(), 'senha': password}


class CertificateTests(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.good = create_a1()
        cls.key = os.urandom(32)

    def test_encrypt_roundtrip_and_nonce(self):
        record = api.validate_and_encrypt(self.good, self.key)
        raw = AESGCM(self.key).decrypt(base64.b64decode(record['nonce']), base64.b64decode(record['dados_cifrados']), api.AAD)
        self.assertEqual(json.loads(raw), self.good)
        self.assertNotIn(self.good['senha'], json.dumps(record))
        self.assertNotIn(self.good['pfx_base64'], json.dumps(record))
        self.assertNotEqual(record['nonce'], api.validate_and_encrypt(self.good, self.key)['nonce'])
        with self.assertRaises(InvalidTag):
            AESGCM(os.urandom(32)).decrypt(base64.b64decode(record['nonce']), base64.b64decode(record['dados_cifrados']), api.AAD)
        with self.assertRaises(InvalidTag):
            AESGCM(self.key).decrypt(base64.b64decode(record['nonce']), base64.b64decode(record['dados_cifrados']), b'outro-cnpj')

    def test_configuration_and_redirect_protection(self):
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(api.SafeError) as caught:
            api.settings()
        self.assertEqual(caught.exception.code, 'CONFIGURACAO_PENDENTE')
        self.assertIsNone(api._NoRedirect().redirect_request(None, None, 302, '', {}, 'https://outro.example'))

    def test_bad_password(self):
        with self.assertRaises(api.SafeError) as caught:
            api.validate_and_encrypt({**self.good, 'senha': 'senha errada'}, self.key)
        self.assertEqual(caught.exception.code, 'A1_OU_SENHA_INVALIDOS')

    def test_expired_other_company_and_missing_key(self):
        for payload, code in [(create_a1(expired=True), 'A1_FORA_DA_VALIDADE'), (create_a1(cnpj='11111111000191'), 'CNPJ_DIVERGENTE'), (create_a1(include_key=False), 'CHAVE_AUSENTE')]:
            with self.subTest(code=code), self.assertRaises(api.SafeError) as caught:
                api.validate_and_encrypt(payload, self.key)
            self.assertEqual(caught.exception.code, code)

    def test_icp_othername_is_preferred_to_commonname(self):
        valid = create_a1(cnpj='11111111000191', other_name=api.CNPJ)
        self.assertEqual(api.validate_and_encrypt(valid, self.key)['cnpj'], api.CNPJ)
        invalid = create_a1(other_name='11111111000191')
        with self.assertRaises(api.SafeError) as caught:
            api.validate_and_encrypt(invalid, self.key)
        self.assertEqual(caught.exception.code, 'CNPJ_DIVERGENTE')

    def test_empty_invalid_large_and_weak_configuration(self):
        for body in [{}, {'pfx_base64':'abc', 'senha':'secret'}, {'pfx_base64':base64.b64encode(b'x'*(api.MAX_PFX+1)).decode(), 'senha':'secret'}]:
            with self.subTest(), self.assertRaises(api.SafeError):
                api.validate_and_encrypt(body, self.key)
        for value in ['', 'not-base64', base64.b64encode(bytes(32)).decode()]:
            with self.subTest(), self.assertRaises(api.SafeError):
                api.decode_key(value)

    def test_worker_isolated_validation(self):
        result = api.isolated_validation(self.good, self.key)
        self.assertEqual(result['cnpj'], api.CNPJ)
        self.assertNotIn('senha', result)
        self.assertNotIn('pfx_base64', result)


class HttpTests(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = create_a1()

    def setUp(self):
        self.rows = []
        self.config = {'origin':ORIGIN, 'url':'https://example.supabase.co', 'key':'sb_secret_test', 'encryption_key':os.urandom(32)}
        self.settings_patch = patch.object(api, 'settings', return_value=self.config)
        self.transport_patch = patch.object(api, 'api_json', side_effect=self.transport)
        self.settings_patch.start(); self.transport_patch.start()
        self.server = HTTPServer(('127.0.0.1', 0), api.handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True);self.thread.start()
        self.url = 'http://127.0.0.1:' + str(self.server.server_port) + '/api/nfse/certificado'

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join()
        self.settings_patch.stop();self.transport_patch.stop()

    def transport(self, config, path, method='GET', body=None, user_token=None, prefer=None):
        if path == '/auth/v1/user':
            if user_token not in (ADMIN, FINANCE):
                raise api.SafeError(401, 'SESSAO_INVALIDA', 'Entre novamente no sistema.')
            self.token = user_token
            return {'id':UID}
        if '/perfis_faturamento?' in path:
            return [{'perfil':'administrador' if self.token==ADMIN else 'financeiro','ativo':True}]
        if method == 'GET':
            return [{k:r[k] for k in api.PUBLIC_COLUMNS.split(',')} for r in self.rows]
        if method in ('POST','PATCH'):
            self.rows = [{**body}]
            return [{k:body[k] for k in api.PUBLIC_COLUMNS.split(',')}]
        raise AssertionError('Unexpected request')

    def call(self, method='GET', payload=None, token=ADMIN, origin=ORIGIN, content_type='application/json'):
        headers = {'Origin':origin, 'Content-Type':content_type}
        if token:headers['Authorization'] = 'Bearer ' + token
        data = json.dumps(payload).encode() if payload is not None else (b'' if method=='POST' else None)
        req = request.Request(self.url, data=data, headers=headers, method=method)
        try:
            response=request.urlopen(req)
        except error.HTTPError as err:
            response=err
        with response:
            return response.status, json.loads(response.read()), response.headers

    def test_access_origin_and_content_type(self):
        self.assertEqual(self.call(token=None)[0],401)
        self.assertEqual(self.call(token=FINANCE)[0],403)
        self.assertEqual(self.call(method='POST',payload=self.payload,origin='https://outro.example')[0],403)
        self.assertEqual(self.call(method='POST',payload=self.payload,content_type='text/plain')[0],415)
        self.assertFalse(self.rows)

    def test_upload_status_and_explicit_replacement(self):
        status,result,headers=self.call(method='POST',payload=self.payload)
        self.assertEqual(status,200)
        self.assertEqual(headers['Cache-Control'],'no-store')
        self.assertFalse(result['emissao_oficial_disponivel'])
        self.assertNotIn('dados_cifrados',result['certificado'])
        self.assertNotIn('nonce',result['certificado'])
        self.assertNotIn(self.payload['senha'],json.dumps(result))
        self.assertEqual(self.call(method='POST',payload=self.payload)[0],409)
        status,result,_=self.call()
        version=result['certificado']['updated_at']
        self.assertEqual(self.call(method='POST',payload={**self.payload,'substituir':True,'versao_anterior':'outdated'})[0],409)
        self.assertEqual(self.call(method='POST',payload={**self.payload,'substituir':True,'versao_anterior':version})[0],200)
        self.assertEqual(len(self.rows),1)
        self.assertNotIn('senha',self.rows[0])

    def test_inactive_administrator_is_denied(self):
        def transport(config, path, **kwargs):
            if path == '/auth/v1/user': return {'id':UID}
            return [{'perfil':'administrador','ativo':False}]
        with patch.object(api,'api_json',side_effect=transport):
            self.assertEqual(self.call()[0],403)
        self.assertFalse(self.rows)

    def test_vercel_runtime_reserved_method_does_not_recurse(self):
        # O adaptador Vercel acrescenta handle_request à classe em tempo de execução.
        with patch.object(api.handler,'handle_request',side_effect=AssertionError('Método reservado do runtime'),create=True):
            status,result,_=self.call()
        self.assertEqual(status,200)
        self.assertTrue(result['servidor_pronto'])

    def test_unexpected_failure_is_redacted(self):
        with patch.object(api,'isolated_validation',side_effect=RuntimeError('segredo que não pode sair')):
            status,result,_=self.call(method='POST',payload=self.payload)
        self.assertEqual(status,500)
        self.assertNotIn('segredo',json.dumps(result))
        self.assertFalse(self.rows)


if __name__=='__main__': main()
