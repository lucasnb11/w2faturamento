"""Validação de rascunhos contra o XSD oficial de homologação de 20/10/2026.

Não reserva número, não assina e não envia DPS. Validação XSD não é autorização
fiscal nem validação das regras de negócio municipais/nacionais.
"""
from datetime import date, datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from pathlib import Path
import re

from lxml import etree

NS = 'http://www.sped.fazenda.gov.br/nfse'
CNPJ = '46167015000140'
TOMADOR = '73939449000193'
MUNICIPIO = '1500800'
BRASILIA = timezone(timedelta(hours=-3))
SCHEMA_PATH = Path(__file__).parent / 'schemas' / 'homologacao_20261020' / 'DPS_v1.01.xsd'
SCHEMA_SOURCE = 'https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/producao-restrita/esquemas_prod_restrita_20261020.zip'
REFERENCE_RATE = 'Omitir como na DPS de referência · homologação'
REFERENCE_IBS = 'Não informado na nota de referência · homologação'
REFERENCE_NOTICE = ('Cenário documental de homologação confirmado pelo usuário. '
                    'Reproduz as notas de referência sem declarar validação contábil, '
                    'não aplicabilidade de IBS/CBS ou autorização para emissão em produção.')


def reference_mode(row):
    """Opt-in salvo no snapshot; aplicável somente aos construtores de tpAmb=2."""
    f = row.get('dados_fiscais') or {}
    return (isinstance(f, dict) and f.get('homologacao_por_referencia') is True
            and f.get('uso_exclusivo_homologacao') is True
            and isinstance(f.get('fonte_referencia_homologacao'), str)
            and 1 <= len(f['fonte_referencia_homologacao'].strip()) <= 1000)


def digits(value):
    return re.sub(r'\D', '', str(value or ''))


def amount(value):
    text = str(value if value is not None else '').strip()
    if ',' in text:
        text = text.replace('.', '').replace(',', '.')
    try:
        number = Decimal(text)
        if not number.is_finite() or number < 0 or number.as_tuple().exponent < -2:
            return None
        return number
    except (InvalidOperation, ValueError):
        return None


def check_draft(row, today=None):
    today = today or datetime.now(BRASILIA).date()
    f = row.get('dados_fiscais')
    if not isinstance(f, dict):
        f = {}
    reference = reference_mode(row)
    pending = []

    def need(code, label, valid):
        if not valid:
            pending.append({'campo': code, 'mensagem': label})

    need('emitente_cnpj', 'O prestador deve ser a W2 Transportes.', row.get('emitente_cnpj', CNPJ) == CNPJ)
    need('tomador_cnpj', 'Confira o CNPJ da Total Express.', digits(row.get('tomador_cnpj')) == TOMADOR and digits(f.get('tomador_cnpj')) == TOMADOR)
    need('tomador_nome', 'Confira a razão social do tomador no rascunho e no cadastro fiscal.', bool(row.get('tomador_nome')) and row.get('tomador_nome') == f.get('tomador_nome'))
    if f.get('homologacao_por_referencia') is True:
        need('homologacao_por_referencia', 'Identifique a nota de referência e confirme o uso exclusivo em homologação.', reference)
    for key, label in [
        ('prestador_endereco_confirmado', 'Confirme endereço e número da W2.'),
        ('tomador_confirmado', 'Confirme o cadastro da Total Express.'),
        ('fiscal_confirmado', 'Registre a validação fiscal do contador.'),
        ('competencia_confirmada', 'Confirme a data real de início da prestação.'),
        ('consolidacao_confirmada', 'Confirme a regra contábil para esta cobrança por quinzena.'),
    ]:
        need(key, label, reference or f.get(key) is True)
    need('orientacao_contabil', 'Registre a referência da orientação contábil (responsável, data e fundamento da consolidação).', reference or bool(str(f.get('orientacao_contabil', '')).strip()))
    try:
        competence = date.fromisoformat(f.get('competencia', ''))
        valid_date = competence <= today and competence.year == int(row['ano']) and competence.month == int(row['mes']) and (1 if competence.day <= 15 else 2) == int(row['quinzena'])
    except (ValueError, TypeError, KeyError):
        valid_date = False
    need('competencia', 'Informe a data real de início da prestação, dentro da quinzena do rascunho e sem data futura.', valid_date)
    need('descricao', 'Informe uma descrição dos serviços com até 2.000 caracteres.', isinstance(row.get('descricao'), str) and 1 <= len(row['descricao'].strip()) <= 2000)
    # vServ vem de uma coluna numérica do banco; não é uma quantia localizada.
    value = amount(row.get('valor_rem'))
    need('valor_rem', 'Informe valor dos serviços positivo, com até 2 casas decimais.', value is not None and Decimal('0') < value <= Decimal('9999999999999.99'))
    need('prestador_im', 'Confira a inscrição municipal, preservando os zeros iniciais.', isinstance(f.get('prestador_im'), str) and bool(re.fullmatch(r'[0-9]{1,15}', f['prestador_im'])))
    need('simples', 'A W2 foi confirmada como não optante pelo Simples. Corrija o cadastro deste rascunho.', f.get('simples') == 'Não optante')
    need('regime', 'Para a W2 não optante, o regime de apuração pelo Simples não se aplica.', f.get('regime') == 'Não se aplica (não optante)')
    need('regime_especial', 'Confirme o regime especial. Esta etapa atende somente Nenhum.', f.get('regime_especial') == 'Nenhum')
    need('iss_tipo', 'Esta etapa atende somente operação tributável de ISS.', f.get('iss_tipo') == 'Operação tributável')
    need('iss_retencao', 'Confirme se o ISS é retido pelo tomador ou não retido.', f.get('iss_retencao') in ['Não retido', 'Retido pelo tomador'])
    need('aliquota_xml', 'Defina o preenchimento da alíquota na DPS; a reprodução documental exige o modo de referência de homologação.', (not reference and f.get('aliquota_xml') in ['Informar na DPS', 'Não informar conforme regra municipal']) or (reference and f.get('aliquota_xml') == REFERENCE_RATE))
    rate = amount(f.get('iss_aliquota'))
    need('iss_aliquota', 'Informe a alíquota do ISS confirmada pelo contador, entre 0 e 5%.', rate is not None and rate <= 5)
    need('total_tributos_sn', 'Remova o percentual do Simples: a W2 não é optante.', not str(f.get('total_tributos_sn', '')).strip())
    for key, label in [('total_tributos_federais', 'federais'), ('total_tributos_estaduais', 'estaduais'), ('total_tributos_municipais', 'municipais')]:
        approx = amount(f.get(key))
        need(key, f'Confirme o percentual aproximado de tributos {label}, entre 0 e 100%, inclusive se for zero.', approx is not None and approx <= 100)
    for key in ['irrf', 'inss', 'pis', 'cofins', 'csll']:
        need(key, f'{key.upper()}: esta etapa exige valor zero confirmado; retenções federais precisam de adaptação.', amount(f.get(key)) == 0)
    need('pis_cofins_cst', 'Confirme o CST 06 de PIS/COFINS usado no XML de referência; outros cenários exigem adaptação.', f.get('pis_cofins_cst') == '06')
    need('pis_cofins_retencao', 'Confirme PIS/COFINS/CSLL não retidos, como no XML de referência.', f.get('pis_cofins_retencao') == '0 · Não retidos')
    need('pis_cofins_base', 'Confirme a base de PIS/COFINS igual ao valor dos serviços, como neste cenário de referência.', value is not None and amount(f.get('pis_cofins_base')) == value)
    for key, label in [('pis_aliquota', 'Alíquota PIS'), ('cofins_aliquota', 'Alíquota COFINS'), ('pis_debito', 'PIS apuração própria'), ('cofins_debito', 'COFINS apuração própria')]:
        need(key, f'{label}: confirme zero para este cenário de CST 06.', amount(f.get(key)) == 0)
    for key in ['desconto_incondicionado', 'desconto_condicionado']:
        discount = amount(f.get(key))
        need(key, f'Confirme {key.replace("_", " ")}, inclusive quando for zero.', discount is not None)
    unconditional = amount(f.get('desconto_incondicionado'))
    conditional = amount(f.get('desconto_condicionado'))
    if value is not None and unconditional is not None and conditional is not None:
        need('descontos', 'Os descontos não podem alcançar ou superar o valor dos serviços.', unconditional + conditional < value)
    for key in ['codigo_nacional', 'nbs']:
        size = 6 if key == 'codigo_nacional' else 9
        raw = str(f.get(key, ''))
        need(key, f'Confirme {key}: são necessários {size} dígitos.', bool(re.fullmatch(r'[0-9.]+', raw)) and len(digits(raw)) == size)
    need('codigo_nacional', 'Use o código nacional 26.01.01 informado para este contrato.', digits(f.get('codigo_nacional')) == '260101')
    need('nbs', 'Use a NBS 1.0502.29.00 informada no modelo atualizado.', digits(f.get('nbs')) == '105022900')
    need('codigo_municipal', 'O código municipal, quando aplicável, deve ter 3 dígitos.', not f.get('codigo_municipal') or bool(re.fullmatch(r'[0-9]{3}', str(f['codigo_municipal']))))
    for prefix, label in [('prestador', 'W2'), ('tomador', 'Total Express')]:
        for suffix, caption in [('logradouro', 'logradouro'), ('numero', 'número'), ('bairro', 'bairro')]:
            need(f'{prefix}_{suffix}', f'Informe {caption} de {label} em campo separado.', bool(str(f.get(f'{prefix}_{suffix}', '')).strip()))
        need(f'{prefix}_cep', f'Confira o CEP de {label}.', len(digits(f.get(f'{prefix}_cep'))) == 8)
        need(f'{prefix}_municipio_ibge', f'Informe o código IBGE de {label}, com 7 dígitos.', bool(re.fullmatch(r'[0-9]{7}', str(f.get(f'{prefix}_municipio_ibge', '')))))
    need('prestador_municipio_ibge', 'O município emissor da W2 deve ser Ananindeua (1500800).', f.get('prestador_municipio_ibge') == MUNICIPIO)
    need('local_prestacao_ibge', 'Informe o código IBGE do local real da prestação, com 7 dígitos.', bool(re.fullmatch(r'[0-9]{7}', str(f.get('local_prestacao_ibge', '')))))
    need('municipio_incidencia_ibge', 'Esta etapa contempla somente incidência do ISS em Ananindeua. A incidência será verificada também pelas regras da API.', f.get('municipio_incidencia_ibge') == MUNICIPIO)
    need('intermediario', 'Esta etapa contempla somente operação sem intermediário.', not any(f.get(k) for k in ['intermediario_nome', 'intermediario_documento', 'intermediario_email']))
    treatment = f.get('ibscbs_tratamento')
    need('ibscbs_tratamento', 'Confirme o tratamento de IBS/CBS na competência; a ausência documental só é aceita no modo de referência de homologação.', (not reference and treatment in ['Informado conforme validação contábil', 'Não aplicável conforme validação contábil']) or (reference and treatment == REFERENCE_IBS))
    if treatment == 'Informado conforme validação contábil':
        for key, size in [('cst', 3), ('cclass', 6), ('indicador_operacao', 6)]:
            need(key, f'Confirme {key}: são necessários {size} dígitos.', bool(re.fullmatch(r'[0-9]{' + str(size) + r'}', str(f.get(key, '')))))
        need('destinatario_proprio', 'Confirme que o destinatário é o próprio tomador; destinatário distinto exige adaptação.', f.get('destinatario_proprio') is True)
    else:
        need('ibscbs_coerencia', 'Remova códigos e valores IBS/CBS incompatíveis com a opção não aplicável.', not any(f.get(k) for k in ['cst', 'cclass', 'indicador_operacao']) and all(amount(f.get(k)) in (None, Decimal(0)) for k in ['ibs', 'cbs']))
    return pending


def element(parent, name, text=None):
    child = etree.SubElement(parent, '{' + NS + '}' + name)
    if text is not None:
        child.text = str(text).strip()
    return child


def build_simulation(row, now=None):
    """XML não assinado com numeração fictícia, exclusivamente para validar XSD."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError('A data de emissão exige fuso horário explícito.')
    local_now = now.astimezone(BRASILIA)
    issues = check_draft(row, local_now.date())
    if issues:
        raise ValueError('Dados fiscais pendentes')
    f = row['dados_fiscais']
    root = etree.Element('{' + NS + '}DPS', nsmap={None: NS}, versao='1.01')
    info = element(root, 'infDPS')
    info.set('Id', 'DPS' + MUNICIPIO + '2' + CNPJ + '00000' + '000000000000001')
    for name, text in [('tpAmb', '2'), ('dhEmi', local_now.isoformat(timespec='seconds')), ('verAplic', 'W2-2.8-preflight'), ('serie', '0'), ('nDPS', '1'), ('dCompet', f['competencia']), ('tpEmit', '1'), ('finNFSe', '0'), ('cLocEmi', MUNICIPIO)]:
        element(info, name, text)

    def address(person, prefix):
        end = element(person, 'end')
        national = element(end, 'endNac')
        element(national, 'cMun', f[prefix + '_municipio_ibge'])
        element(national, 'CEP', digits(f[prefix + '_cep']))
        for name, suffix in [('xLgr', 'logradouro'), ('nro', 'numero'), ('xCpl', 'complemento'), ('xBairro', 'bairro')]:
            if f.get(prefix + '_' + suffix):
                element(end, name, f[prefix + '_' + suffix])

    provider = element(info, 'prest')
    element(provider, 'CNPJ', CNPJ)
    element(provider, 'IM', f['prestador_im'])
    # Não enviar nome/endereço do prestador emitente: o cadastro nacional é a fonte.
    regime = element(provider, 'regTrib')
    element(regime, 'opSimpNac', '1')
    element(regime, 'regEspTrib', '0')
    customer = element(info, 'toma')
    element(customer, 'CNPJ', TOMADOR)
    element(customer, 'xNome', row['tomador_nome'])
    address(customer, 'tomador')
    if f.get('tomador_email'):
        element(customer, 'email', f['tomador_email'])
    service = element(info, 'serv')
    element(element(service, 'locPrest'), 'cLocPrestacao', f['local_prestacao_ibge'])
    code = element(service, 'cServ')
    element(code, 'cTribNac', digits(f['codigo_nacional']))
    if f.get('codigo_municipal'):
        element(code, 'cTribMun', f['codigo_municipal'])
    element(code, 'cNBS', digits(f['nbs']))
    element(code, 'xDescServ', row['descricao'])
    if f.get('complementares'):
        element(element(service, 'infoCompl'), 'xInfComp', f['complementares'])
    values = element(info, 'valores')
    element(element(values, 'vServPrest'), 'vServ', f"{amount(row['valor_rem']):.2f}")
    discounts = element(values, 'vDescCondIncond')
    for key, name in [('desconto_incondicionado', 'vDescIncond'), ('desconto_condicionado', 'vDescCond')]:
        element(discounts, name, f"{amount(f[key]):.2f}")
    tax = element(values, 'trib')
    municipal = element(tax, 'tribMun')
    element(municipal, 'tribISSQN', '1')
    element(municipal, 'tpRetISSQN', '1' if f['iss_retencao'] == 'Não retido' else '2')
    if f['aliquota_xml'] == 'Informar na DPS':
        element(municipal, 'pAliq', f"{amount(f['iss_aliquota']):.2f}")
    federal = element(tax, 'tribFed')
    pis_cofins = element(federal, 'piscofins')
    element(pis_cofins, 'CST', f['pis_cofins_cst'])
    for key, name in [('pis_cofins_base', 'vBCPisCofins'), ('pis_aliquota', 'pAliqPis'), ('cofins_aliquota', 'pAliqCofins'), ('pis_debito', 'vPis'), ('cofins_debito', 'vCofins')]:
        element(pis_cofins, name, f"{amount(f[key]):.2f}")
    element(pis_cofins, 'tpRetPisCofins', '0')
    approximate = element(element(tax, 'totTrib'), 'pTotTrib')
    for key, name in [('total_tributos_federais', 'pTotTribFed'), ('total_tributos_estaduais', 'pTotTribEst'), ('total_tributos_municipais', 'pTotTribMun')]:
        element(approximate, name, f"{amount(f[key]):.2f}")
    if f['ibscbs_tratamento'] == 'Informado conforme validação contábil':
        ibs = element(info, 'IBSCBS')
        element(ibs, 'cIndOp', f['indicador_operacao'])
        element(ibs, 'indDest', '0')
        trib = element(element(ibs, 'valores'), 'trib')
        element(trib, 'CST', f['cst'])
        element(trib, 'cClassTrib', f['cclass'])
    return root


@lru_cache(maxsize=1)
def schema():
    parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False)
    return etree.XMLSchema(etree.parse(str(SCHEMA_PATH), parser))


def inspect(row, today=None):
    pending = check_draft(row, today)
    result = {'ambiente': 'homologacao', 'etapa': 'validacao_local', 'transmitido': False,
              'emissao_oficial_disponivel': False, 'numeracao_reservada': False,
              'schema': '1.01-homologacao-20261020', 'schema_fonte': SCHEMA_SOURCE,
              'pendencias': pending, 'xsd_valido': False,
              'aviso': 'Validação local com numeração fictícia. Não assina, não transmite e não autoriza NFS-e.'}
    result['modo_validacao'] = 'referencia_documental' if reference_mode(row) else 'confirmacoes_fiscais'
    if reference_mode(row):
        result['aviso'] += ' ' + REFERENCE_NOTICE
    if pending:
        return result
    try:
        now = datetime.now(timezone.utc) if today is None else datetime.combine(today, datetime.min.time(), BRASILIA)
        document = build_simulation(row, now)
        validator = schema()
        validator.assertValid(document)
        result['xsd_valido'] = True
    except etree.DocumentInvalid as exc:
        # Mensagens retornadas não contêm valores do XML nem dados do certificado.
        result['pendencias'] = [{'campo': 'xsd', 'mensagem': f'Estrutura inválida no XSD oficial (linha {e.line}, regra {e.type_name}).'} for e in list(exc.error_log)[:20]]
    return result
