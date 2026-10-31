"""Preparação local de DPS reservada. Sem assinatura, rede ou reserva de números."""
from copy import deepcopy
from datetime import datetime, timezone

from lxml import etree

from nfse_core.preflight import CNPJ, MUNICIPIO, NS, build_simulation, schema


def application_series(value):
    # A regra E0010 do leiaute PRODREST 20/10/2026 começa em 00001.
    return type(value) is int and 1 <= value <= 49999


def numbering_status(rows):
    """Somente metadados; nunca devolve snapshot, usuário ou XML."""
    row = rows[0] if isinstance(rows, list) and len(rows) == 1 and isinstance(rows[0], dict) else {}
    series, number = row.get('serie'), row.get('proximo_numero')
    configured = row.get('cnpj') == CNPJ and application_series(series)
    number_valid = type(number) is int and 1 <= number < 999999999999999
    return {'serie': series if configured else None,
        'proximo_numero': str(number) if configured and number_valid else None,
        'serie_configurada': configured, 'numeracao_pronta': configured and number_valid,
        'numeracao_reservada': False, 'faixa_serie': '1 a 49999 · aplicativo próprio'}


def build_reserved_dps(reservation, now=None):
    """Aceita apenas o snapshot imutável devolvido pela reserva no servidor.

    O chamador deve obter a reserva do banco, nunca do corpo da requisição.
    Não altera o snapshot nem usa uma versão mais recente do rascunho.
    """
    if not isinstance(reservation, dict):
        raise ValueError('Reserva de homologação inválida.')
    series, number = reservation.get('serie'), reservation.get('numero')
    snapshot = reservation.get('snapshot')
    if (not application_series(series) or type(number) is not int or not 1 <= number < 999999999999999
        or reservation.get('estado') not in ('reservada', 'falha_local') or not isinstance(snapshot, dict)
        or snapshot.get('emitente_cnpj') != CNPJ or type(snapshot.get('id')) is not int
        or snapshot.get('id') != reservation.get('rascunho_id')
        or not isinstance(snapshot.get('updated_at'), str)
        or snapshot.get('updated_at') != reservation.get('rascunho_versao')):
        raise ValueError('Reserva, série ou versão do rascunho inválida.')
    identifier = 'DPS' + MUNICIPIO + '2' + CNPJ + str(series).zfill(5) + str(number).zfill(15)
    if reservation.get('dps_id') != identifier:
        raise ValueError('Identificador da reserva divergente.')
    now = now or datetime.now(timezone.utc)
    root = build_simulation(deepcopy(snapshot), now)
    info = root.find('{' + NS + '}infDPS')
    info.set('Id', identifier)
    for name, value in [('serie', series), ('nDPS', number), ('verAplic', 'W2-2.11.10-HOMO')]:
        info.find('{' + NS + '}' + name).text = str(value)
    schema().assertValid(root)
    return etree.tostring(root, encoding='UTF-8', xml_declaration=True, pretty_print=False)
