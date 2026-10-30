"""Diagnóstico mTLS de leitura, restrito à Sefin de homologação.

Não existe método POST para a API nacional neste módulo. O material do A1
é decifrado em processo temporário e carregado no OpenSSL através de memfd
(memória Linux), sem gravar certificado, senha ou chave privada em disco.
"""
import base64
import hashlib
import http.client
import json
import os
from pathlib import Path
import ssl
import subprocess
import sys

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.serialization import pkcs12

from api.nfse.certificado import AAD, CNPJ, SafeError, api_json, TABLE, validate_and_encrypt

HOST = 'sefin.producaorestrita.nfse.gov.br'
BASE = '/API/SefinNacional'
DOCS = ('/swagger/v1/swagger.json', '/swagger/docs/v1', '/docs/v1/swagger.json')
CONVENIO = '/parametros_municipais/1500800/convenio'
MAX_RESPONSE = 1024 * 1024


class NationalError(ValueError):
    pass


def decrypt_material(record, key):
    """Retorna somente material em memória; não deve ser chamado no navegador."""
    try:
        if record.get('cnpj') != CNPJ or record.get('key_version') != 1 or len(key) != 32:
            raise ValueError()
        encoded = record['dados_cifrados']
        if not isinstance(encoded, str) or len(encoded) > 500000:
            raise ValueError()
        nonce = base64.b64decode(record['nonce'], validate=True)
        if len(nonce) != 12:
            raise ValueError()
        raw = AESGCM(key).decrypt(nonce, base64.b64decode(encoded, validate=True), AAD)
        payload = json.loads(raw)
        # Reutiliza as verificações de CNPJ, validade, usos e correspondência.
        checked = validate_and_encrypt(payload, key)
        if checked['sha256'] != record['sha256']:
            raise ValueError()
        private_key, certificate, chain = pkcs12.load_key_and_certificates(
            base64.b64decode(payload['pfx_base64'], validate=True), payload['senha'].encode('utf-8'))
        return private_key, certificate, chain or []
    except Exception:
        raise NationalError('Não foi possível abrir o A1 cadastrado. Confira sua validade e a chave de proteção do servidor.') from None


def tls_context(material):
    if not hasattr(os, 'memfd_create'):
        raise NationalError('Este runtime não oferece o carregamento do A1 em memória.')
    private_key, cert, chain = material
    certificate = cert.public_bytes(serialization.Encoding.PEM) + b''.join(c.public_bytes(serialization.Encoding.PEM) for c in chain)
    private = private_key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    fds = []
    try:
        for label, data in [('w2-cert', certificate), ('w2-key', private)]:
            fd = os.memfd_create(label, flags=os.MFD_CLOEXEC)
            fds.append(fd)
            with os.fdopen(os.dup(fd), 'wb') as output:
                output.write(data)
        context.load_cert_chain('/proc/self/fd/' + str(fds[0]), '/proc/self/fd/' + str(fds[1]))
    except Exception:
        raise NationalError('Não foi possível preparar o A1 para a conexão segura.') from None
    finally:
        for fd in fds:
            os.close(fd)
    return context


def read_official(context, path):
    if path not in (*DOCS, CONVENIO):
        raise NationalError('Consulta fora do escopo do diagnóstico.')
    connection = http.client.HTTPSConnection(HOST, timeout=6, context=context)
    try:
        connection.request('GET', BASE + path, headers={'Accept': 'application/json', 'User-Agent': 'W2-NFSe-Homologacao/2.9'})
        response = connection.getresponse()
        if response.status in (301, 302, 303, 307, 308):
            raise NationalError('A API respondeu com redirecionamento; a consulta foi interrompida.')
        body = response.read(MAX_RESPONSE + 1)
        if len(body) > MAX_RESPONSE:
            raise NationalError('A resposta da API excedeu o limite do diagnóstico.')
        if response.status != 200:
            return response.status, None
        try:
            result = json.loads(body)
            return response.status, result if isinstance(result, dict) else None
        except (ValueError, UnicodeError):
            return response.status, None
    except NationalError:
        raise
    except Exception:
        raise NationalError('Não foi possível concluir a conexão mTLS com a API de homologação.') from None
    finally:
        connection.close()


def inspect_contract(document):
    """Reconhece o campo de recepção apenas se declarado no Swagger oficial."""
    def resolve(value):
        for _ in range(6):
            if not isinstance(value, dict):
                return {}
            ref = value.get('$ref')
            if not ref:
                return value
            if not isinstance(ref, str) or not ref.startswith('#/'):
                return {}
            value = document
            for token in ref[2:].split('/'):
                value = value.get(token.replace('~1', '/').replace('~0', '~'), {}) if isinstance(value, dict) else {}
        return {}
    try:
        operation = document['paths']['/nfse']['post']
        content = resolve(operation.get('requestBody', {})).get('content', {})
        schema = content.get('application/json', {}).get('schema')
        if schema is None:
            bodies = [p for p in operation.get('parameters', []) if p.get('in') == 'body']
            schema = bodies[0]['schema'] if len(bodies) == 1 else None
        schema = resolve(schema)
        field = resolve(schema.get('properties', {}).get('dpsXmlGZipB64'))
        return field.get('type') == 'string' and 'dpsXmlGZipB64' in schema.get('required', [])
    except (KeyError, TypeError, AttributeError):
        return False


def diagnostic_worker(record, key):
    context = tls_context(decrypt_material(record, key))
    document = None
    docs_status = None
    for path in DOCS:
        docs_status, candidate = read_official(context, path)
        if candidate and ('openapi' in candidate or 'swagger' in candidate):
            document = candidate
            break
    status, convenio = read_official(context, CONVENIO)
    return {'ambiente': 'homologacao', 'conexao_tls_respondeu': True,
        'documentacao_http': docs_status, 'contrato_recepcao_identificado': bool(document and inspect_contract(document)),
        'contrato_sha256': hashlib.sha256(json.dumps(document, sort_keys=True, separators=(',', ':')).encode()).hexdigest() if document else None,
        'consulta_convenio_http': status, 'consulta_convenio_recebida': convenio is not None,
        'transmitido': False, 'emissao_oficial_disponivel': False,
        'aviso': 'Diagnóstico de leitura. A resposta HTTP não comprova habilitação fiscal. Nenhuma DPS foi assinada ou enviada.'}


def diagnose_connection(config):
    rows = api_json(config, '/rest/v1/' + TABLE + '?cnpj=eq.' + CNPJ + '&select=cnpj,dados_cifrados,nonce,key_version,sha256&limit=1')
    if not isinstance(rows, list) or len(rows) != 1:
        raise SafeError(409, 'A1_AUSENTE', 'Cadastre o A1 antes de testar a conexão.')
    payload = {'record': rows[0], 'key': base64.b64encode(config['encryption_key']).decode('ascii')}
    env = {k: os.environ[k] for k in ('PATH', 'PYTHONHOME', 'LD_LIBRARY_PATH', 'LANG') if k in os.environ}
    env['PYTHONPATH'] = str(Path(__file__).resolve().parents[1])
    try:
        result = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--diagnostic'],
            input=json.dumps(payload).encode(), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            env=env, timeout=40, check=False)
        data = json.loads(result.stdout)
        if result.returncode != 0 or not isinstance(data, dict) or data.get('transmitido') is not False or data.get('emissao_oficial_disponivel') is not False:
            raise ValueError()
        allowed = ['ambiente','conexao_tls_respondeu','documentacao_http','contrato_recepcao_identificado','contrato_sha256','consulta_convenio_http','consulta_convenio_recebida','transmitido','emissao_oficial_disponivel']
        clean = {name: data.get(name) for name in allowed}
        clean['aviso'] = 'Diagnóstico de leitura. A resposta HTTP não comprova habilitação fiscal. Nenhuma DPS foi assinada ou enviada.'
        return clean
    except subprocess.TimeoutExpired:
        raise SafeError(504, 'CONEXAO_TEMPO_ESGOTADO', 'O diagnóstico excedeu o tempo de resposta. Nenhuma DPS foi enviada.') from None
    except (OSError, ValueError):
        raise SafeError(503, 'CONEXAO_INDISPONIVEL', 'Não foi possível testar o A1 na API de homologação. Nenhuma DPS foi enviada.') from None


if __name__ == '__main__' and '--diagnostic' in sys.argv:
    try:
        data = json.loads(sys.stdin.buffer.read(600000))
        output = diagnostic_worker(data['record'], base64.b64decode(data['key'], validate=True))
        sys.stdout.write(json.dumps(output))
    except Exception:
        # Nunca incluir exceção, XML, credenciais ou resposta bruta da API.
        sys.stdout.write(json.dumps({'transmitido': False, 'emissao_oficial_disponivel': False, 'erro': 'Falha no diagnóstico seguro do A1.'}))
        sys.exit(1)
