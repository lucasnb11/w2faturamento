"""Cadastro do A1. Nenhuma operação neste endpoint emite notas fiscais."""
from __future__ import annotations

import base64
import binascii
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler
from urllib import error, parse, request

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import ExtensionOID, ExtendedKeyUsageOID, NameOID, ObjectIdentifier

CNPJ = '46167015000140'
MAX_PFX = 256 * 1024
MAX_BODY = 370 * 1024
AAD = ('w2-nfse-a1:v1:' + CNPJ).encode('ascii')
TABLE = 'nfse_certificados_a1'
PUBLIC_COLUMNS = 'cnpj,valido_desde,valido_ate,sha256,updated_at'


class SafeError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(code)
        self.status, self.code, self.message = status, code, message


def decode_key(value: str) -> bytes:
    try:
        key = base64.b64decode(value, validate=True)
        if len(key) != 32 or len(set(key)) < 8:
            raise ValueError()
        return key
    except (ValueError, binascii.Error):
        raise SafeError(503, 'CONFIGURACAO_PENDENTE', 'A chave de proteção do A1 ainda precisa ser configurada no servidor.') from None


def settings() -> dict:
    origin = os.environ.get('NFSE_APP_ORIGIN', '').strip().rstrip('/')
    url = os.environ.get('SUPABASE_URL', '').strip().rstrip('/')
    key = os.environ.get('SUPABASE_SECRET_KEY', '') or os.environ.get('SUPABASE_SERVICE_ROLE_KEY', '')
    origin_url, database_url = parse.urlsplit(origin), parse.urlsplit(url)
    if (origin_url.scheme != 'https' or not origin_url.netloc or origin_url.path
        or origin_url.username or origin_url.query or origin_url.fragment
        or database_url.scheme != 'https' or not database_url.hostname
        or not database_url.hostname.endswith('.supabase.co') or database_url.path
        or database_url.username or database_url.query or database_url.fragment
        or not (key.startswith('sb_secret_') or key.startswith('eyJ'))):
        raise SafeError(503, 'CONFIGURACAO_PENDENTE', 'Configure a origem HTTPS e as variáveis privadas da integração no servidor.')
    return {'origin': origin, 'url': url, 'key': key, 'encryption_key': decode_key(os.environ.get('NFSE_A1_ENCRYPTION_KEY', ''))}


class _NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def api_json(config: dict, path: str, method='GET', body=None, user_token=None, prefer=None):
    headers = {'apikey': config['key'], 'Accept': 'application/json'}
    if user_token:
        headers['Authorization'] = 'Bearer ' + user_token
    elif config['key'].startswith('eyJ'):
        headers['Authorization'] = 'Bearer ' + config['key']
    if prefer:
        headers['Prefer'] = prefer
    data = None
    if body is not None:
        headers['Content-Type'] = 'application/json'
        data = json.dumps(body, separators=(',', ':')).encode('utf-8')
    req = request.Request(config['url'] + path, data=data, headers=headers, method=method)
    try:
        with request.build_opener(_NoRedirect).open(req, timeout=8) as response:
            raw = response.read(2 * 1024 * 1024)
            return json.loads(raw) if raw else None
    except error.HTTPError as exc:
        if path == '/auth/v1/user' and exc.code in (401, 403):
            raise SafeError(401, 'SESSAO_INVALIDA', 'Entre novamente no sistema.') from None
        if exc.code == 409:
            raise SafeError(409, 'CERTIFICADO_ALTERADO', 'O cadastro mudou. Atualize a situação antes de tentar novamente.') from None
        raise SafeError(503, 'SERVICO_INDISPONIVEL', 'Não foi possível consultar ou gravar a configuração protegida do A1.') from None
    except (error.URLError, TimeoutError, ValueError):
        raise SafeError(503, 'SERVICO_INDISPONIVEL', 'O serviço de autenticação ou armazenamento não respondeu. Tente novamente.') from None


def authorize(config: dict, headers) -> str:
    match = re.fullmatch(r'Bearer ([^\s]{20,8192})', headers.get('Authorization', ''))
    if not match:
        raise SafeError(401, 'LOGIN_NECESSARIO', 'Entre com uma conta administradora para configurar o A1.')
    user = api_json(config, '/auth/v1/user', user_token=match.group(1))
    uid = user.get('id', '') if isinstance(user, dict) else ''
    if not re.fullmatch(r'[0-9a-fA-F-]{36}', uid):
        raise SafeError(401, 'SESSAO_INVALIDA', 'Entre novamente no sistema.')
    profiles = api_json(config, '/rest/v1/perfis_faturamento?' + parse.urlencode({'id': 'eq.' + uid, 'select': 'perfil,ativo'}))
    if not isinstance(profiles, list) or len(profiles) != 1 or profiles[0].get('perfil') != 'administrador' or profiles[0].get('ativo') is not True:
        raise SafeError(403, 'ACESSO_RESTRITO', 'Somente administradores ativos podem configurar o A1.')
    return uid


def public_status(config: dict):
    rows = api_json(config, '/rest/v1/' + TABLE + '?' + parse.urlencode({'cnpj': 'eq.' + CNPJ, 'select': PUBLIC_COLUMNS}))
    if not isinstance(rows, list) or len(rows) > 1:
        raise SafeError(503, 'CONFIGURACAO_INVALIDA', 'Confira a instalação do armazenamento protegido.')
    if not rows:
        return None
    return {key: rows[0].get(key) for key in PUBLIC_COLUMNS.split(',')}


def _der_text(value: bytes, depth=0) -> list[str]:
    """Decodifica apenas o pequeno valor DER do OtherName CNPJ ICP-Brasil."""
    if depth > 6 or len(value) > 256 or len(value) < 2:
        raise ValueError('DER inválido')
    tag, size, offset = value[0], value[1], 2
    if size & 0x80:
        count = size & 0x7f
        if count == 0 or count > 2 or len(value) < 2 + count:
            raise ValueError('DER inválido')
        size = int.from_bytes(value[2:2 + count], 'big')
        offset += count
    if offset + size != len(value):
        raise ValueError('DER inválido')
    data = value[offset:]
    if tag & 0x20:
        return _der_text(data, depth + 1)
    if tag in (0x0c, 0x04, 0x12, 0x13, 0x16):
        try:
            return [data.decode('utf-8').strip()]
        except UnicodeDecodeError:
            return []
    return []


def certificate_cnpj(cert) -> str:
    found = set()
    try:
        san = cert.extensions.get_extension_for_oid(ExtensionOID.SUBJECT_ALTERNATIVE_NAME).value
        for item in san.get_values_for_type(x509.OtherName):
            if item.type_id == ObjectIdentifier('2.16.76.1.3.3'):
                values = [value for value in _der_text(item.value) if re.fullmatch(r'\d{14}', value)]
                if not values:
                    raise ValueError('CNPJ OtherName inválido')
                found.update(values)
    except x509.ExtensionNotFound:
        pass
    if len(found) == 1:
        return next(iter(found))
    if not found:
        for item in cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME):
            match = re.search(r':\s*(\d{14})\s*$', item.value)
            if match:
                found.add(match.group(1))
    if len(found) != 1:
        raise SafeError(422, 'CNPJ_NAO_IDENTIFICADO', 'Não foi possível identificar um CNPJ único no A1.')
    return next(iter(found))


def validate_and_encrypt(payload: dict, key: bytes):
    encoded, password = payload.get('pfx_base64'), payload.get('senha')
    if not isinstance(encoded, str) or not isinstance(password, str) or not password or len(password) > 1024 or '\0' in password:
        raise SafeError(400, 'DADOS_INVALIDOS', 'Selecione um A1 e informe sua senha.')
    try:
        binary = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error):
        raise SafeError(400, 'ARQUIVO_INVALIDO', 'O arquivo do A1 não foi recebido corretamente.') from None
    if not binary or len(binary) > MAX_PFX:
        raise SafeError(413, 'ARQUIVO_GRANDE', 'O A1 deve ter no máximo 256 KB.')
    try:
        private_key, cert, _chain = pkcs12.load_key_and_certificates(binary, password.encode('utf-8'))
    except Exception:
        raise SafeError(422, 'A1_OU_SENHA_INVALIDOS', 'Arquivo A1 ou senha inválidos. Confira os dados e tente novamente.') from None
    if cert is None or private_key is None:
        raise SafeError(422, 'CHAVE_AUSENTE', 'O arquivo precisa conter o certificado e sua chave privada.')
    format_args = (serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    if private_key.public_key().public_bytes(*format_args) != cert.public_key().public_bytes(*format_args):
        raise SafeError(422, 'CHAVE_DIVERGENTE', 'A chave privada não corresponde ao certificado.')
    if certificate_cnpj(cert) != CNPJ:
        raise SafeError(422, 'CNPJ_DIVERGENTE', 'O A1 precisa pertencer à W2 Transportes, CNPJ 46.167.015/0001-40.')
    now = datetime.now(timezone.utc)
    if not cert.not_valid_before_utc <= now < cert.not_valid_after_utc:
        raise SafeError(422, 'A1_FORA_DA_VALIDADE', 'O A1 está vencido ou ainda não está dentro do período de validade.')
    try:
        if cert.extensions.get_extension_for_oid(ExtensionOID.BASIC_CONSTRAINTS).value.ca:
            raise SafeError(422, 'A1_INVALIDO', 'Selecione o certificado da empresa, não um certificado de autoridade certificadora.')
    except x509.ExtensionNotFound:
        pass
    try:
        usage = cert.extensions.get_extension_for_oid(ExtensionOID.KEY_USAGE).value
        if not usage.digital_signature:
            raise SafeError(422, 'ASSINATURA_NAO_PERMITIDA', 'O certificado não permite assinatura digital.')
    except x509.ExtensionNotFound:
        pass
    try:
        eku = cert.extensions.get_extension_for_oid(ExtensionOID.EXTENDED_KEY_USAGE).value
        if ExtendedKeyUsageOID.CLIENT_AUTH not in eku:
            raise SafeError(422, 'AUTENTICACAO_NAO_PERMITIDA', 'O certificado não permite autenticação de cliente.')
    except x509.ExtensionNotFound:
        pass
    nonce = os.urandom(12)
    plaintext = json.dumps({'pfx_base64': encoded, 'senha': password}, separators=(',', ':'), ensure_ascii=False).encode('utf-8')
    encrypted = AESGCM(key).encrypt(nonce, plaintext, AAD)
    return {'cnpj': CNPJ, 'dados_cifrados': base64.b64encode(encrypted).decode('ascii'),
            'nonce': base64.b64encode(nonce).decode('ascii'), 'key_version': 1,
            'valido_desde': cert.not_valid_before_utc.isoformat(), 'valido_ate': cert.not_valid_after_utc.isoformat(),
            'sha256': cert.fingerprint(hashes.SHA256()).hex()}


def isolated_validation(payload: dict, key: bytes):
    # O parser e a derivação da senha têm limite de tempo e não recebem as chaves do Supabase.
    data = {'payload': {'pfx_base64': payload.get('pfx_base64'), 'senha': payload.get('senha')}, 'key': base64.b64encode(key).decode('ascii')}
    env = {k: os.environ[k] for k in ('PATH', 'PYTHONPATH', 'PYTHONHOME', 'LD_LIBRARY_PATH', 'LANG') if k in os.environ}
    try:
        result = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--validate-a1'],
                                input=json.dumps(data).encode('utf-8'), stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, timeout=8, env=env, check=False)
        output = json.loads(result.stdout)
        if output.get('error'):
            err = output['error']
            raise SafeError(err['status'], err['code'], err['message'])
        if result.returncode != 0 or not isinstance(output.get('record'), dict):
            raise ValueError()
        return output['record']
    except subprocess.TimeoutExpired:
        raise SafeError(422, 'A1_NAO_PROCESSADO', 'O A1 excedeu o tempo de leitura. Confira o arquivo com o responsável pelo certificado.') from None
    except (ValueError, KeyError, OSError):
        raise SafeError(503, 'LEITURA_INDISPONIVEL', 'Não foi possível processar o A1 neste servidor.') from None


def store_record(config: dict, record: dict, uid: str, current, body: dict):
    record = {**record, 'cadastrado_por': uid, 'updated_at': datetime.now(timezone.utc).isoformat()}
    if current:
        if body.get('substituir') is not True or body.get('versao_anterior') != current.get('updated_at'):
            raise SafeError(409, 'SUBSTITUICAO_NAO_CONFIRMADA', 'Atualize a situação e confirme a substituição do A1 existente.')
        query = parse.urlencode({'cnpj': 'eq.' + CNPJ, 'updated_at': 'eq.' + current['updated_at'], 'select': PUBLIC_COLUMNS})
        result = api_json(config, '/rest/v1/' + TABLE + '?' + query, 'PATCH', record, prefer='return=representation')
    else:
        result = api_json(config, '/rest/v1/' + TABLE + '?select=' + PUBLIC_COLUMNS, 'POST', record, prefer='return=representation')
    if not isinstance(result, list) or len(result) != 1:
        raise SafeError(409, 'CERTIFICADO_ALTERADO', 'O cadastro mudou. Atualize a situação e tente novamente.')
    return {key: result[0].get(key) for key in PUBLIC_COLUMNS.split(',')}


class handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass  # Nunca registrar corpo, senha, token ou arquivo.

    def respond(self, status, body):
        data = json.dumps(body, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Cross-Origin-Resource-Policy', 'same-origin')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _process_a1_request(self, writing=False):
        try:
            config = settings()
            origin = self.headers.get('Origin')
            if (writing and origin != config['origin']) or (origin and origin != config['origin']):
                raise SafeError(403, 'ORIGEM_INVALIDA', 'Use a configuração do A1 pelo endereço oficial do sistema.')
            uid = authorize(config, self.headers)
            current = public_status(config)
            if not writing:
                return self.respond(200, {'servidor_pronto': True, 'certificado': current, 'emissao_oficial_disponivel': False})
            if self.headers.get('Content-Type', '').split(';')[0].strip() != 'application/json':
                raise SafeError(415, 'FORMATO_INVALIDO', 'Envie o certificado pelo formulário do sistema.')
            length = self.headers.get('Content-Length', '')
            if not length.isdigit() or not 0 < int(length) <= MAX_BODY:
                raise SafeError(413, 'REQUISICAO_INVALIDA', 'O arquivo do A1 excedeu o limite permitido.')
            try:
                body = json.loads(self.rfile.read(int(length)))
            except (ValueError, UnicodeError):
                raise SafeError(400, 'FORMATO_INVALIDO', 'Não foi possível ler os dados enviados.') from None
            if not isinstance(body, dict):
                raise SafeError(400, 'FORMATO_INVALIDO', 'Envie o certificado pelo formulário do sistema.')
            if current and (body.get('substituir') is not True or body.get('versao_anterior') != current.get('updated_at')):
                raise SafeError(409, 'SUBSTITUICAO_NAO_CONFIRMADA', 'Atualize a situação e confirme a substituição do A1 existente.')
            record = isolated_validation(body, config['encryption_key'])
            saved = store_record(config, record, uid, current, body)
            self.respond(200, {'servidor_pronto': True, 'certificado': saved, 'emissao_oficial_disponivel': False})
        except SafeError as exc:
            self.respond(exc.status, {'code': exc.code, 'message': exc.message})
        except Exception:
            self.respond(500, {'code': 'ERRO_INTERNO', 'message': 'Falha ao configurar o A1. Nenhum detalhe sensível foi retornado.'})

    def do_GET(self):
        self._process_a1_request()

    def do_POST(self):
        self._process_a1_request(writing=True)

    def do_OPTIONS(self):
        self.respond(405, {'code': 'METODO_INVALIDO', 'message': 'Método não permitido.'})

    do_DELETE = do_PUT = do_PATCH = do_HEAD = do_OPTIONS


if __name__ == '__main__' and '--validate-a1' in sys.argv:
    try:
        data = json.loads(sys.stdin.buffer.read(MAX_BODY + 2048))
        record = validate_and_encrypt(data['payload'], decode_key(data['key']))
        sys.stdout.write(json.dumps({'record': record}))
    except SafeError as exc:
        sys.stdout.write(json.dumps({'error': {'status': exc.status, 'code': exc.code, 'message': exc.message}}))
    except Exception:
        sys.stdout.write(json.dumps({'error': {'status': 422, 'code': 'A1_INVALIDO', 'message': 'Não foi possível validar o A1 informado.'}}))
