import copy
from datetime import date, datetime, timezone
import unittest

from nfse_core.preflight import check_draft, build_simulation, inspect, NS, amount


def fixture():
    """Dados sintéticos: não representam orientação contábil da W2."""
    return {'id': 1, 'ano': 2026, 'mes': 5, 'quinzena': 1,
        'tomador_cnpj': '73939449000193', 'tomador_nome': 'TEX COURIER S.A.',
        'valor_rem': '15169.50', 'descricao': 'Serviços de teste & conferência <sem emissão>',
        'dados_fiscais': {
            'tomador_cnpj': '73.939.449/0001-93', 'tomador_nome': 'TEX COURIER S.A.',
            'prestador_endereco_confirmado': True, 'tomador_confirmado': True,
            'fiscal_confirmado': True, 'consolidacao_confirmada': True,
            'competencia_confirmada': True,
            'orientacao_contabil': 'Cenário exclusivamente sintético para teste unitário.',
            'competencia': '2026-05-01', 'prestador_im': '000000000078123',
            'prestador_municipio_ibge': '1500800', 'tomador_municipio_ibge': '3505708',
            'prestador_cep': '67015-760', 'tomador_cep': '06460-030',
            'prestador_logradouro': 'Rua de teste', 'prestador_numero': '1', 'prestador_bairro': 'Teste',
            'tomador_logradouro': 'Rua de teste', 'tomador_numero': '2', 'tomador_bairro': 'Teste',
            'local_prestacao_ibge': '1500800', 'municipio_incidencia_ibge': '1500800',
            'simples': 'Não optante', 'regime': 'Não se aplica (não optante)',
            'regime_especial': 'Nenhum', 'iss_tipo': 'Operação tributável',
            'iss_retencao': 'Não retido', 'iss_aliquota': '2,00', 'total_tributos_federais': '0,00', 'total_tributos_estaduais': '0,00', 'total_tributos_municipais': '0,00',
            'aliquota_xml': 'Não informar conforme regra municipal',
            'irrf': '0,00', 'inss': '0,00', 'pis': '0,00', 'cofins': '0,00', 'csll': '0,00',
            'pis_cofins_cst': '06', 'pis_cofins_retencao': '0 · Não retidos', 'pis_cofins_base': '15169,50',
            'pis_aliquota': '0,00', 'cofins_aliquota': '0,00', 'pis_debito': '0,00', 'cofins_debito': '0,00',
            'desconto_incondicionado': '0,00', 'desconto_condicionado': '0,00',
            'codigo_nacional': '26.01.01', 'nbs': '1.0502.29.00',
            'ibscbs_tratamento': 'Não aplicável conforme validação contábil'}}


class PreflightTests(unittest.TestCase):
    def test_schema_provenance_hashes(self):
        import hashlib
        import json
        from nfse_core.preflight import SCHEMA_PATH
        manifest=json.loads((SCHEMA_PATH.parent/'manifest.json').read_text())
        for name,digest in manifest['sha256'].items():
            self.assertEqual(hashlib.sha256((SCHEMA_PATH.parent/name).read_bytes()).hexdigest(),digest)

    def test_official_schema_and_no_fiscal_effect(self):
        result = inspect(fixture(), date(2026, 10, 30))
        self.assertEqual(result['pendencias'], [])
        self.assertTrue(result['xsd_valido'])
        for key in ['transmitido', 'numeracao_reservada', 'emissao_oficial_disponivel']:
            self.assertIs(result[key], False)

    def test_xml_namespace_order_id_and_escaping(self):
        from lxml import etree
        root = build_simulation(fixture(), datetime(2026, 10, 30, tzinfo=timezone.utc))
        ns = {'n': NS}
        self.assertEqual(root.find('n:infDPS/n:tpAmb', ns).text, '2')
        self.assertEqual(len(root[0].get('Id')), 45)
        self.assertEqual(root.find('n:infDPS/n:prest/n:IM', ns).text, '000000000078123')
        self.assertEqual(root.find('n:infDPS/n:prest/n:regTrib/n:opSimpNac', ns).text, '1')
        self.assertIsNone(root.find('n:infDPS/n:prest/n:regTrib/n:regApTribSN', ns))
        self.assertIsNone(root.find('n:infDPS/n:valores/n:trib/n:totTrib/n:pTotTribSN', ns))
        self.assertEqual(root.find('n:infDPS/n:serv/n:cServ/n:cTribNac', ns).text, '260101')
        self.assertEqual(root.find('n:infDPS/n:serv/n:cServ/n:cNBS', ns).text, '105022900')
        self.assertIn(b'&amp;', etree.tostring(root))
        self.assertEqual(len(root.xpath('//*[local-name()="Signature"]')), 0)

    def test_ibs_cbs_structure(self):
        row = fixture()
        row['dados_fiscais'].update(ibscbs_tratamento='Informado conforme validação contábil',
            cst='000', cclass='000001', indicador_operacao='100301', destinatario_proprio=True)
        self.assertTrue(inspect(row, date(2026, 10, 30))['xsd_valido'])
        row['dados_fiscais']['destinatario_proprio'] = False
        self.assertIn('destinatario_proprio', [x['campo'] for x in check_draft(row)])

    def test_old_fiscal_registration_is_rejected(self):
        for key,value in [('simples','Optante · ME/EPP'), ('total_tributos_sn','0,00'),
                          ('codigo_nacional','11.05.01'), ('nbs','1.0702.00.00')]:
            row=fixture();row['dados_fiscais'][key]=value
            self.assertIn(key,[x['campo'] for x in check_draft(row)])

    def test_pis_cofins_own_tax_is_distinct_from_withholding(self):
        ns={'n':NS}
        row=fixture()
        xml=build_simulation(row)
        group=xml.find('n:infDPS/n:valores/n:trib/n:tribFed/n:piscofins',ns)
        self.assertEqual(group.find('n:CST',ns).text,'06')
        self.assertEqual(group.find('n:vBCPisCofins',ns).text,'15169.50')
        self.assertEqual(group.find('n:tpRetPisCofins',ns).text,'0')
        for key,value in [('pis_cofins_base',''),('pis_cofins_cst','01'),('pis_debito','1,00'),('cofins_aliquota','NaN')]:
            wrong=fixture();wrong['dados_fiscais'][key]=value
            self.assertIn(key,[x['campo'] for x in check_draft(wrong)])

    def test_unknown_zero_and_unsupported_tax_are_not_silently_omitted(self):
        for key, value in [('irrf', ''), ('pis', '1,00'), ('desconto_condicionado', ''), ('total_tributos_federais', 'NaN')]:
            row = fixture();row['dados_fiscais'][key] = value
            result = inspect(row)
            self.assertFalse(result['xsd_valido'])
            self.assertIn(key, [x['campo'] for x in result['pendencias']])

    def test_competence_cannot_be_future_or_outside_period(self):
        for value in ['2026-05-16', '2026-06-01', '2027-05-01', 'invalid']:
            row = fixture();row['dados_fiscais']['competencia'] = value
            self.assertIn('competencia', [x['campo'] for x in check_draft(row, date(2026, 10, 30))])

    def test_official_schema_rejects_length_and_no_content_leak(self):
        row = fixture();row['dados_fiscais']['tomador_numero'] = 'segredo-nao-retornar-' * 20
        result = inspect(row)
        self.assertFalse(result['xsd_valido'])
        self.assertEqual(result['pendencias'][0]['campo'], 'xsd')
        self.assertNotIn('segredo', str(result))

    def test_draft_unchanged_and_decimal_precision(self):
        row = fixture();original = copy.deepcopy(row)
        inspect(row)
        self.assertEqual(row, original)
        self.assertEqual(str(amount('15.169,50')), '15169.50')
        for value in ['', 'NaN', 'Infinity', '-1', '0.001']:
            self.assertIsNone(amount(value))


if __name__ == '__main__':
    unittest.main()
