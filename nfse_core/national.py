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
import re
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
PARAM_HOST = 'adn.producaorestrita.nfse.gov.br'
PARAM_BASE = '/parametrizacao'
MAX_RESPONSE = 1024 * 1024
ERRORS = {
    'A1_ABERTURA': 'Não foi possível abrir o A1 cadastrado. Confira sua validade e a proteção do servidor.',
    'A1_MEMORIA': 'O runtime não permite carregar o A1 em memória.',
    'A1_PREPARO_TLS': 'Não foi possível preparar o A1 para a conexão TLS.',
    'API_REDIRECIONAMENTO': 'A API retornou um redirecionamento e a consulta foi interrompida.',
    'API_RESPOSTA_GRANDE': 'A resposta da API excedeu o limite do diagnóstico.',
    'API_CONEXAO_TLS': 'A conexão TLS com a API de homologação não foi concluída.',
    'PROCESSO_DEPENDENCIA': 'O processo de diagnóstico não conseguiu carregar uma biblioteca do servidor.',
    'PROCESSO_ARQUIVO_AUSENTE': 'O processo de diagnóstico não encontrou seu arquivo no servidor.',
    'PROCESSO_RESPOSTA': 'O processo de diagnóstico não devolveu uma resposta válida.',
    'DIAGNOSTICO_INTERNO': 'O diagnóstico foi interrompido por uma falha interna.',
}


class NationalError(ValueError):
    def __init__(self, message, code='DIAGNOSTICO_INTERNO'):
        super().__init__(message)
        self.code = code if code in ERRORS else 'DIAGNOSTICO_INTERNO'


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
        raise NationalError(ERRORS['A1_ABERTURA'], 'A1_ABERTURA') from None


def tls_context(material):
    if not hasattr(os, 'memfd_create'):
        raise NationalError(ERRORS['A1_MEMORIA'], 'A1_MEMORIA')
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
        raise NationalError(ERRORS['A1_PREPARO_TLS'], 'A1_PREPARO_TLS') from None
    finally:
        for fd in fds:
            os.close(fd)
    return context


def _read_service(context, path, service):
    if service not in ('sefin', 'parametros'):
        raise NationalError('Serviço fora do escopo do diagnóstico.')
    parameter_path = (isinstance(path, str) and bool(re.fullmatch(r'/[A-Za-z0-9_/-]{1,180}', path))
        and '//' not in path and bool(re.search(r'(^|/)1500800(/|$)', path))
        and any(word in path.lower() for word in ('municip', 'conven')))
    if path not in DOCS and not (service == 'parametros' and parameter_path):
        raise NationalError('Consulta fora do escopo do diagnóstico.')
    host, prefix = (HOST, BASE) if service == 'sefin' else (PARAM_HOST, PARAM_BASE)
    connection = http.client.HTTPSConnection(host, timeout=6, context=context)
    try:
        full_path = path if path.startswith(prefix + '/') else prefix + path
        connection.request('GET', full_path, headers={'Accept': 'application/json', 'User-Agent': 'W2-NFSe-Homologacao/2.9.2'})
        response = connection.getresponse()
        if response.status in (301, 302, 303, 307, 308):
            raise NationalError(ERRORS['API_REDIRECIONAMENTO'], 'API_REDIRECIONAMENTO')
        body = response.read(MAX_RESPONSE + 1)
        if len(body) > MAX_RESPONSE:
            raise NationalError(ERRORS['API_RESPOSTA_GRANDE'], 'API_RESPOSTA_GRANDE')
        try:
            result = json.loads(body)
            return response.status, result if isinstance(result, dict) else None
        except (ValueError, UnicodeError):
            return response.status, None
    except NationalError:
        raise
    except Exception:
        raise NationalError(ERRORS['API_CONEXAO_TLS'], 'API_CONEXAO_TLS') from None
    finally:
        connection.close()


def read_official(context, path):
    return _read_service(context, path, 'sefin')


def read_parameters(context, path):
    return _read_service(context, path, 'parametros')


def parameter_endpoint(document):
    """Escolhe somente GET de convênio municipal declarado no Swagger oficial."""
    candidates = []
    paths = document.get('paths', {})
    if not isinstance(paths, dict):
        return None
    for template, operations in paths.items():
        if not isinstance(template, str) or not isinstance(operations, dict):
            continue
        operation = operations.get('get')
        if not isinstance(operation, dict) or operation.get('deprecated') is True:
            continue
        names = re.findall(r'\{([A-Za-z][A-Za-z0-9_]*)\}', template)
        semantic = (template + ' ' + str(operation.get('summary', ''))).lower()
        if len(names) != 1 or 'municip' not in semantic or 'conv' not in semantic:
            continue
        shared, specific = operations.get('parameters', []), operation.get('parameters', [])
        if not isinstance(shared, list) or not isinstance(specific, list):
            continue
        parameters = []
        for parameter in shared + specific:
            for _ in range(6):
                if not isinstance(parameter, dict) or '$ref' not in parameter:
                    break
                ref = parameter.get('$ref')
                if not isinstance(ref, str) or not ref.startswith('#/'):
                    parameter = None
                    break
                parameter = document
                for name in ref[2:].split('/'):
                    parameter = parameter.get(name.replace('~1', '/').replace('~0', '~')) if isinstance(parameter, dict) else None
            parameters.append(parameter)
        if any(not isinstance(p, dict) or '$ref' in p or (p.get('in') == 'query' and p.get('required') is True) for p in parameters):
            continue
        path = template.replace('{' + names[0] + '}', '1500800')
        if not re.fullmatch(r'/[A-Za-z0-9_/-]{1,180}', path) or '//' in path:
            continue
        if not re.search(r'(^|/)1500800(/|$)', path) or not any(w in path.lower() for w in ('municip', 'conven')):
            continue
        candidates.append(path)
    return candidates[0] if len(candidates) == 1 else None


def error_codes(response):
    """Somente códigos curtos; não devolver descrições ou respostas brutas."""
    if not isinstance(response, dict):
        return []
    items = response.get('erros', response.get('Erros', []))
    if not isinstance(items, list):
        return []
    codes = []
    for item in items[:5]:
        if isinstance(item, dict):
            code = item.get('codigo', item.get('Codigo'))
            if isinstance(code, str) and re.fullmatch(r'[A-Za-z0-9_.-]{1,40}', code):
                codes.append(code)
    return codes


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
        if docs_status == 200 and candidate and ('openapi' in candidate or 'swagger' in candidate):
            document = candidate
            break
    parameters_document = None
    parameters_docs_status = None
    for path in DOCS:
        parameters_docs_status, candidate = read_parameters(context, path)
        if parameters_docs_status == 200 and candidate and ('openapi' in candidate or 'swagger' in candidate):
            parameters_document = candidate
            break
    route = parameter_endpoint(parameters_document) if parameters_document else None
    status, convenio = read_parameters(context, route) if route else (None, None)
    return {'ambiente': 'homologacao', 'conexao_tls_respondeu': True,
        'documentacao_http': docs_status, 'contrato_recepcao_identificado': bool(document and inspect_contract(document)),
        'contrato_sha256': hashlib.sha256(json.dumps(document, sort_keys=True, separators=(',', ':')).encode()).hexdigest() if document else None,
        'parametros_servico': 'ADN · Parametrização',
        'parametros_documentacao_http': parameters_docs_status,
        'consulta_convenio_rota': route,
        'consulta_convenio_rota_confirmada': route is not None,
        'consulta_convenio_erro_codigos': error_codes(convenio) if status != 200 else [],
        'consulta_convenio_http': status, 'consulta_convenio_recebida': status == 200 and convenio is not None,
        'transmitido': False, 'emissao_oficial_disponivel': False,
        'aviso': 'Diagnóstico de leitura. A resposta HTTP não comprova habilitação fiscal. Nenhuma DPS foi assinada ou enviada.'}


def worker_environment():
    # Vercel pode carregar dependências por sys.path em diretórios do bundle.
    # Não substituir esses caminhos apenas pela raiz do projeto.
    env = {k: os.environ[k] for k in ('PATH', 'PYTHONHOME', 'LD_LIBRARY_PATH', 'LANG') if k in os.environ}
    root = str(Path(__file__).resolve().parents[1])
    paths = [root] + [p for p in sys.path if isinstance(p, str) and p]
    env['PYTHONPATH'] = os.pathsep.join(dict.fromkeys(paths))
    return env


def _worker_failure(code):
    code = code if isinstance(code, str) and code in ERRORS else 'DIAGNOSTICO_INTERNO'
    # Somente enumeração fixa: nunca registrar stderr, payload ou exceção.
    print(json.dumps({'evento': 'nfse_conexao_falha', 'etapa': code}), flush=True)
    return SafeError(503, code, ERRORS[code] + ' Nenhuma DPS foi enviada. Código: ' + code + '.')


def diagnose_connection(config):
    rows = api_json(config, '/rest/v1/' + TABLE + '?cnpj=eq.' + CNPJ + '&select=cnpj,dados_cifrados,nonce,key_version,sha256&limit=1')
    if not isinstance(rows, list) or len(rows) != 1:
        raise SafeError(409, 'A1_AUSENTE', 'Cadastre o A1 antes de testar a conexão.')
    payload = {'record': rows[0], 'key': base64.b64encode(config['encryption_key']).decode('ascii')}
    env = worker_environment()
    try:
        result = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--diagnostic'],
            input=json.dumps(payload).encode(), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=env, timeout=40, check=False)
        try:
            data = json.loads(result.stdout)
        except (ValueError, UnicodeError):
            # Ler apenas para classificar erros anteriores ao try do worker.
            # O texto bruto nunca é exibido, registrado ou retornado.
            stderr = getattr(result, 'stderr', b'') or b''
            if b'ModuleNotFoundError' in stderr or b'ImportError' in stderr:
                raise _worker_failure('PROCESSO_DEPENDENCIA') from None
            if b"can't open file" in stderr:
                raise _worker_failure('PROCESSO_ARQUIVO_AUSENTE') from None
            raise _worker_failure('PROCESSO_RESPOSTA') from None
        if result.returncode != 0 and isinstance(data, dict):
            raise _worker_failure(data.get('erro_codigo'))
        if result.returncode != 0 or not isinstance(data, dict) or data.get('transmitido') is not False or data.get('emissao_oficial_disponivel') is not False:
            raise _worker_failure('PROCESSO_RESPOSTA')
        allowed = ['ambiente','conexao_tls_respondeu','documentacao_http','contrato_recepcao_identificado','contrato_sha256','consulta_convenio_http','consulta_convenio_recebida','transmitido','emissao_oficial_disponivel',
            'parametros_servico','parametros_documentacao_http','consulta_convenio_rota','consulta_convenio_rota_confirmada','consulta_convenio_erro_codigos']
        clean = {name: data.get(name) for name in allowed}
        clean['aviso'] = 'Diagnóstico de leitura. A resposta HTTP não comprova habilitação fiscal. Nenhuma DPS foi assinada ou enviada.'
        return clean
    except subprocess.TimeoutExpired:
        raise SafeError(504, 'CONEXAO_TEMPO_ESGOTADO', 'O diagnóstico excedeu o tempo de resposta. Nenhuma DPS foi enviada.') from None
    except (OSError, ValueError):
        raise _worker_failure('PROCESSO_RESPOSTA') from None


if __name__ == '__main__' and '--diagnostic' in sys.argv:
    try:
        data = json.loads(sys.stdin.buffer.read(600000))
        output = diagnostic_worker(data['record'], base64.b64decode(data['key'], validate=True))
        sys.stdout.write(json.dumps(output))
    except Exception as exc:
        # Nunca incluir exceção, XML, credenciais ou resposta bruta da API.
        code = exc.code if isinstance(exc, NationalError) else 'DIAGNOSTICO_INTERNO'
        sys.stdout.write(json.dumps({'transmitido': False, 'emissao_oficial_disponivel': False, 'erro_codigo': code}))
        sys.exit(1)
