"""Orquestração administrativa; não recebe XML, CNPJ, URL ou valores do cliente."""
import base64
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlencode

from api.nfse.certificado import SafeError, api_json, CNPJ, TABLE
from nfse_core.national import worker_environment
from nfse_core.preflight import inspect


def row(value):
    if isinstance(value, list) and len(value) == 1:
        value = value[0]
    if not isinstance(value, dict):
        raise SafeError(503, 'RESPOSTA_INVALIDA', 'Não foi possível conferir o estado. Atualize antes de tentar novamente.')
    return value


def rpc(config, name, payload):
    return row(api_json(config, '/rest/v1/rpc/' + name, method='POST', body=payload))


def load(config, draft_id):
    query = urlencode({'rascunho_id': 'eq.' + str(draft_id), 'select': '*', 'limit': '1'})
    records = api_json(config, '/rest/v1/nfse_homologacao_dps?' + query)
    return row(records) if records else None


def metadata(reservation):
    if not reservation:
        return {'estado': 'nao_reservada'}
    return {name: reservation.get(name) for name in ('id', 'dps_id', 'serie', 'numero', 'estado', 'chave_acesso', 'retorno_http', 'erros_codigos')}


def worker(config, reservation, action):
    payload = {'key': base64.b64encode(config['encryption_key']).decode(), 'reservation': reservation, 'action': action}
    if action != 'baixar_xml':
        payload['record'] = row(api_json(config, '/rest/v1/' + TABLE + '?cnpj=eq.' + CNPJ + '&select=cnpj,dados_cifrados,nonce,key_version,sha256&limit=1'))
    try:
        result = subprocess.run([sys.executable, str(Path(__file__).with_name('emission_worker.py'))],
            input=json.dumps(payload).encode(), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=worker_environment(), timeout=45, check=False)
        data = json.loads(result.stdout)
        if result.returncode or not isinstance(data, dict) or 'erro_codigo' in data:
            raise ValueError()
        return data
    except (ValueError, OSError, subprocess.TimeoutExpired):
        # Nunca retornar stdout/stderr ou conteúdo do documento/certificado.
        raise SafeError(503, 'PROCESSAMENTO_INTERROMPIDO', 'O processamento foi interrompido. Consulte o estado antes de continuar.') from None


def finish(config, reservation, result, author):
    state = result.get('estado')
    if state not in ('autorizada', 'rejeitada', 'pendente_consulta'):
        raise SafeError(503, 'RETORNO_INVALIDO', 'Consulte a situação desta DPS antes de continuar.')
    document = result.get('documento', {})
    return rpc(config, 'nfse_gravar_retorno_homologacao', {'p_id': reservation['id'], 'p_esperado': reservation['estado'], 'p_novo': state,
        'p_http': result.get('http'), 'p_codigos': result.get('codigos', []), 'p_chave': result.get('chave'),
        'p_cifrado': document.get('cifrado'), 'p_nonce': document.get('nonce'), 'p_sha256': document.get('sha256'), 'p_autor': author})


def operate(config, author, body):
    action = body['acao']
    query = urlencode({'id': 'eq.' + str(body['rascunho_id']), 'select': '*', 'limit': '1'})
    records = api_json(config, '/rest/v1/nfse_rascunhos?' + query)
    if not records:
        raise SafeError(404, 'RASCUNHO_AUSENTE', 'Atualize a lista de rascunhos.')
    draft = row(records)
    if draft.get('updated_at') != body['versao'] or draft.get('emitente_cnpj') != CNPJ:
        raise SafeError(409, 'RASCUNHO_ALTERADO', 'O rascunho mudou. Atualize a lista.')
    reservation = load(config, body['rascunho_id'])
    answer = {'ambiente': 'homologacao', 'emissao_oficial_disponivel': False,
        'situacao': metadata(reservation), 'pendencias': [],
        'aviso': 'Ambiente de testes. Nenhuma NFS-e de produção é emitida por esta operação.'}
    if action == 'status':
        return answer
    if action in ('preparar', 'transmitir') and reservation and reservation.get('rascunho_versao') != body['versao']:
        raise SafeError(409, 'RESERVA_OUTRA_VERSAO', 'Há DPS reservada para outra versão. Concilie a reserva antes de continuar.')
    if action in ('preparar', 'transmitir'):
        validation = inspect(draft)
        if not validation['xsd_valido'] or validation['pendencias']:
            answer['pendencias'] = validation['pendencias']
            return answer  # Sem reservar ou acessar o A1 quando há pendências fiscais.
    if action == 'preparar':
        if reservation and reservation.get('estado') not in ('reservada', 'falha_local'):
            return answer  # Repetição não gera nem substitui XML assinado.
        if not reservation:
            # Confere A1 antes de consumir número; o material só é aberto no worker.
            certs = api_json(config, '/rest/v1/' + TABLE + '?cnpj=eq.' + CNPJ + '&select=valido_desde,valido_ate&limit=1')
            if not certs:
                raise SafeError(409, 'A1_AUSENTE', 'Cadastre o A1 antes de preparar a DPS.')
            certificate = row(certs)
            now = datetime.now(timezone.utc)
            try:
                valid = datetime.fromisoformat(certificate['valido_desde'].replace('Z', '+00:00')) <= now < datetime.fromisoformat(certificate['valido_ate'].replace('Z', '+00:00'))
            except Exception:
                valid = False
            if not valid:
                raise SafeError(409, 'A1_INVALIDO', 'Cadastre o A1 válido antes de preparar a DPS.')
            reservation = rpc(config, 'nfse_reservar_homologacao', {'p_rascunho_id': body['rascunho_id'], 'p_versao': body['versao'], 'p_autor': author})
        prepared = worker(config, reservation, 'preparar')['documento']
        reservation = rpc(config, 'nfse_gravar_assinatura_homologacao', {'p_id': reservation['id'],
            'p_cifrado': prepared['cifrado'], 'p_nonce': prepared['nonce'], 'p_sha256': prepared['sha256'], 'p_autor': author})
    elif action == 'transmitir':
        if not reservation or reservation.get('estado') != 'assinada' or not reservation.get('dps_xml_cifrado'):
            raise SafeError(409, 'ESTADO_NAO_PERMITE_ENVIO', 'Prepare a DPS ou consulte seu estado. Um envio anterior não será repetido.')
        reservation = rpc(config, 'nfse_iniciar_envio_homologacao', {'p_id': reservation['id'], 'p_autor': author})
        try:
            result = worker(config, reservation, 'transmitir')
        except SafeError:
            result = {'estado': 'pendente_consulta', 'http': None, 'codigos': ['PROCESSAMENTO_INTERROMPIDO']}
        reservation = finish(config, reservation, result, author)
    elif action == 'conciliar':
        if not reservation:
            raise SafeError(409, 'RESERVA_AUSENTE', 'Nenhuma DPS reservada para consultar.')
        if reservation['estado'] == 'enviando':
            changed = datetime.fromisoformat(reservation['updated_at'].replace('Z', '+00:00'))
            if (datetime.now(timezone.utc) - changed).total_seconds() < 180:
                raise SafeError(409, 'ENVIO_EM_ANDAMENTO', 'Aguarde até três minutos antes de conciliar um envio interrompido.')
            reservation = rpc(config, 'nfse_mudar_estado_homologacao', {'p_id': reservation['id'], 'p_esperado': 'enviando', 'p_novo': 'pendente_consulta', 'p_autor': author})
        if reservation['estado'] in ('pendente_consulta', 'rejeitada'):
            result = worker(config, reservation, 'conciliar')
            if reservation['estado'] != 'rejeitada' or result.get('estado') == 'autorizada':
                reservation = finish(config, reservation, result, author)
    elif action == 'baixar_xml':
        if not reservation or reservation.get('estado') != 'autorizada':
            raise SafeError(409, 'XML_NAO_DISPONIVEL', 'Aguarde uma autorização conferida em homologação.')
        xml = worker(config, reservation, action).get('xml_base64')
        if not isinstance(xml, str):
            raise SafeError(503, 'XML_NAO_DISPONIVEL', 'Não foi possível abrir o XML protegido.')
        return {'xml_base64': xml, 'nome': reservation['dps_id'] + '-homologacao.xml'}
    else:
        raise SafeError(400, 'ACAO_INVALIDA', 'Ação não permitida.')
    answer['situacao'] = metadata(reservation)
    return answer
