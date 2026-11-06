"""Compatibilidade do ISS por competência; somente GET em homologação."""
from datetime import date, datetime, time
import re

from nfse_core.national import DOCS, read_parameters
from nfse_core.preflight import amount, digits

HISTORY = '/{codigoMunicipio}/{codigoServico}/historicoaliquotas'


def history_declared(document):
    if not isinstance(document, dict):
        return False
    item = document.get('paths', {}).get(HISTORY, {})
    operation = item.get('get') if isinstance(item, dict) else None
    if not isinstance(operation, dict):
        return False
    params = item.get('parameters', []) + operation.get('parameters', [])
    if any(not isinstance(p, dict) or '$ref' in p or (p.get('in') == 'query' and p.get('required')) for p in params):
        return False
    names = {p.get('name') for p in params if p.get('in') == 'path'}
    return names == {'codigoMunicipio', 'codigoServico'}


def calendar_date(value):
    if not isinstance(value, str):
        raise ValueError('Data ausente')
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.time() != time():
        raise ValueError('Vigência parcial não suportada')
    return parsed.date()


def context_for(draft):
    f = draft.get('dados_fiscais') or {}
    competence = date.fromisoformat(f.get('competencia', ''))
    if competence.isoformat() != f.get('competencia'):
        raise ValueError('Competência inválida')
    suffix = f.get('codigo_municipal') or '000'
    if (f.get('municipio_incidencia_ibge') != '1500800' or digits(f.get('codigo_nacional')) != '260101'
            or not re.fullmatch(r'[0-9]{3}', suffix) or f.get('codigo_municipal') == '000'
            or f.get('iss_tipo') != 'Operação tributável' or amount(f.get('iss_aliquota')) is None):
        raise ValueError('Cenário não suportado')
    return competence, '26.01.01.' + suffix, amount(f['iss_aliquota'])


def evaluate_history(document, draft, http=200):
    competence, code, expected = context_for(draft)
    answer = {'competencia': competence.isoformat(), 'codigo_servico': code,
              'fonte': 'ADN · homologação', 'http': http, 'liberado': False,
              'situacao': 'indisponivel', 'mensagem': 'Não foi possível confirmar os parâmetros de ISS para esta competência. Nenhuma nova numeração será reservada.'}
    if http != 200 or not isinstance(document, dict):
        return answer
    records = document.get('aliquotas', {}).get(code) if isinstance(document.get('aliquotas'), dict) else None
    if not isinstance(records, list) or not records or len(records) > 500:
        return answer
    matching = []
    try:
        for record in records:
            if not isinstance(record, dict) or not {'DtIni', 'DtFim', 'Incidencia', 'Aliq'} <= record.keys():
                return answer
            start = calendar_date(record['DtIni'])
            end = calendar_date(record['DtFim']) if record['DtFim'] is not None else None
            if end is not None and end < start:
                return answer
            if start <= competence and (end is None or competence <= end):
                matching.append((record, start, end))
    except (ValueError, TypeError):
        return answer
    if len(matching) != 1:
        return answer  # Lacuna ou sobreposição: nunca escolher silenciosamente.
    record, start, end = matching[0]
    incidence = record['Incidencia']
    rate = amount(record['Aliq'])
    if incidence not in ('SIM', 'NÃO', 'NAO') or (record['Aliq'] is not None and (rate is None or rate > 5)):
        return answer
    answer.update(incidencia=incidence, aliquota=f'{rate:.2f}' if rate is not None else None,
                  aliquota_rascunho=f'{expected:.2f}', vigencia_inicio=start.isoformat(),
                  vigencia_fim=end.isoformat() if end else None)
    if incidence == 'SIM' and rate is not None and rate > 0 and rate == expected:
        answer.update(liberado=True, situacao='compativel',
                      mensagem='Incidência e alíquota municipais compatíveis com o rascunho nesta competência. A autorização ainda depende da API de homologação.')
    else:
        answer.update(situacao='divergente', mensagem='Os parâmetros municipais desta competência divergem do rascunho. Confira a incidência e a alíquota com o município; os dados fiscais não serão alterados automaticamente.')
    return answer


def validate_municipal(context, draft):
    _, code, _ = context_for(draft)
    unavailable = evaluate_history(None, draft, None)
    try:
        document = None
        for path in DOCS:
            status, candidate = read_parameters(context, path)
            if status == 200 and isinstance(candidate, dict):
                document = candidate
                break
        if not history_declared(document):
            return unavailable
        status, response = read_parameters(context, '/1500800/' + code + '/historicoaliquotas')
        return evaluate_history(response, draft, status)
    except Exception:
        return unavailable  # Sem resposta, não reservar, assinar ou transmitir.
