"""Processo isolado: somente homologação; material do A1 permanece em memória."""
import base64
import http.client
import json
import re
import sys

from nfse_core.national import HOST, BASE, DOCS, decrypt_material, tls_context, inspect_contract, error_codes
from nfse_core.preparation import build_reserved_dps
from nfse_core.preflight import schema
from nfse_core.protocol import identifier, pack, seal, unseal, validate_authorization, parse_xml
from nfse_core.signature import sign_homologation_dps, verify_homologation_dps, INCLUSIVE, RSA_SHA1


class Transport:
    def __init__(self, context):
        self.context = context

    def request(self, method, path, body=None):
        valid_read = path in DOCS or bool(re.fullmatch(r'/dps/DPS1500800246167015000140[0-9]{20}|/nfse/[0-9]{50}', path))
        if not ((method == 'GET' and valid_read and body is None) or (method == 'POST' and path == '/nfse' and isinstance(body, dict) and set(body) == {'dpsXmlGZipB64'})):
            raise ValueError('Operação fora do escopo de homologação.')
        connection = http.client.HTTPSConnection(HOST, timeout=8, context=self.context)
        try:
            encoded = json.dumps(body, separators=(',', ':')).encode() if body is not None else None
            connection.request(method, BASE + path, body=encoded,
                headers={'Accept': 'application/json', 'Content-Type': 'application/json', 'User-Agent': 'W2-NFSe-Homologacao/2.11'})
            response = connection.getresponse()
            if response.status in (301, 302, 303, 307, 308):
                raise ValueError('Redirecionamento bloqueado.')
            raw = response.read(2 * 1024 * 1024 + 1)
            if len(raw) > 2 * 1024 * 1024:
                raise ValueError('Retorno fora do limite.')
            try:
                data = json.loads(raw)
                return response.status, data if isinstance(data, dict) else None
            except (ValueError, UnicodeError):
                return response.status, None
        finally:
            connection.close()

    def contract(self):
        for path in DOCS:
            status, document = self.request('GET', path)
            if status == 200 and isinstance(document, dict) and inspect_contract(document):
                paths = document.get('paths', {})
                if isinstance(paths.get('/dps/{id}', {}).get('get'), dict) and isinstance(paths.get('/nfse/{chaveAcesso}', {}).get('get'), dict):
                    return True
        return False


def envelope(row, kind):
    return {name: row[kind + '_xml_' + name] for name in ('cifrado', 'nonce', 'sha256')}


def receive(transport, response, xml, dps_id, key, http=200):
    authorized, access_key = validate_authorization(response, xml, dps_id)
    return {'estado': 'autorizada', 'http': http, 'codigos': [], 'chave': access_key, 'documento': seal(authorized, key, dps_id, 'nfse')}


def reconcile(transport, xml, dps_id, key):
    status, result = transport.request('GET', '/dps/' + identifier(dps_id))
    if status == 200 and isinstance(result, dict):
        access_key = result.get('chaveAcesso')
        if isinstance(access_key, str) and re.fullmatch(r'[0-9]{50}', access_key):
            nfse_status, nfse = transport.request('GET', '/nfse/' + access_key)
            if nfse_status == 200 and isinstance(nfse, dict):
                # Alguns GET omitem idDps no JSON. O XML é comparado integralmente.
                return receive(transport, {**nfse, 'idDps': nfse.get('idDps', dps_id)}, xml, dps_id, key)
    return {'estado': 'pendente_consulta', 'http': status, 'codigos': error_codes(result)}


def transmit(transport, xml, dps_id, key):
    # Toda falha depois da disputa do estado é incerta; não existe repetição POST.
    if not transport.contract():
        return {'estado': 'pendente_consulta', 'http': None, 'codigos': ['CONTRATO_NAO_CONFIRMADO']}
    status, existing = transport.request('GET', '/dps/' + identifier(dps_id))
    if status == 200:
        return reconcile(transport, xml, dps_id, key)
    if status != 404:
        return {'estado': 'pendente_consulta', 'http': status, 'codigos': error_codes(existing)}
    status, result = transport.request('POST', '/nfse', {'dpsXmlGZipB64': pack(xml)})
    if status in (200, 201) and isinstance(result, dict):
        return receive(transport, result, xml, dps_id, key, http=status)
    codes = error_codes(result)
    # Apenas rejeições de assinatura inequívocas do leiaute. Duplicidade,
    # erro de transporte e demais resultados seguem para conciliação por GET.
    items = result.get('erros', result.get('Erros', [])) if isinstance(result, dict) else []
    rejected = (status in (400, 422) and bool(codes) and isinstance(items, list) and len(items) == len(codes)
        and all(c in {'E0714', 'E0715', 'E0716', 'E0717', 'E0718'} for c in codes))
    return {'estado': 'rejeitada' if rejected else 'pendente_consulta', 'http': status, 'codigos': codes}


def execute(payload):
    key = base64.b64decode(payload['key'], validate=True)
    reservation, action = payload['reservation'], payload['action']
    dps_id = identifier(reservation['dps_id'])
    if action == 'baixar_xml':
        if reservation.get('estado') != 'autorizada':
            raise ValueError('Documento não autorizado.')
        return {'xml_base64': base64.b64encode(unseal(envelope(reservation, 'nfse'), key, dps_id, 'nfse')).decode()}
    material = decrypt_material(payload['record'], key)
    if action == 'verificar_ausencia':
        rejected_signature = reservation.get('estado') == 'rejeitada' and reservation.get('retorno_http') in (400, 422) and reservation.get('erros_codigos') == ['E0714']
        if reservation.get('estado') != 'pendente_consulta' and not rejected_signature:
            raise ValueError('Estado inválido para consulta de ausência.')
        transport = Transport(tls_context(material))
        if not transport.contract():
            return {'ausente': False, 'http': None}
        status, _ = transport.request('GET', '/dps/' + dps_id)
        return {'ausente': status == 404, 'http': status}
    if action == 'preparar':
        xml = build_reserved_dps(reservation)
        signed = sign_homologation_dps(xml, material[0], material[1], expected_dps_id=dps_id, profile=INCLUSIVE, suite=RSA_SHA1)
        schema().assertValid(parse_xml(signed))
        return {'documento': seal(signed, key, dps_id, 'dps')}
    if action not in ('transmitir', 'conciliar'):
        raise ValueError('Ação inválida.')
    allowed_states = ('enviando',) if action == 'transmitir' else ('pendente_consulta', 'rejeitada')
    if reservation.get('estado') not in allowed_states:
        raise ValueError('Estado inválido para a operação.')
    xml = unseal(envelope(reservation, 'dps'), key, dps_id, 'dps')
    # Uma consulta GET deve continuar possível para o XML antigo rejeitado.
    # Sua integridade de armazenamento é conferida pelo envelope AES-GCM.
    # Antes de qualquer POST, a assinatura continua sendo obrigatória.
    if action == 'transmitir':
        verify_homologation_dps(xml, material[1], expected_dps_id=dps_id, profile=INCLUSIVE, suite=RSA_SHA1)
    transport = Transport(tls_context(material))
    try:
        return transmit(transport, xml, dps_id, key) if action == 'transmitir' else reconcile(transport, xml, dps_id, key)
    except Exception:
        return {'estado': 'pendente_consulta', 'http': None, 'codigos': ['RETORNO_NAO_CONFERIDO']}


if __name__ == '__main__':
    try:
        data = json.loads(sys.stdin.buffer.read(3500000))
        sys.stdout.write(json.dumps(execute(data)))
    except Exception:
        sys.stdout.write(json.dumps({'erro_codigo': 'OPERACAO_LOCAL_FALHOU'}))
        sys.exit(1)
