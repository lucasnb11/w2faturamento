"""Cenários sintéticos de referência; nenhuma regra contábil é atestada."""
import copy
from datetime import date, datetime, timezone
import unittest
from unittest.mock import patch

from test_preflight import fixture
from nfse_core import emission
from nfse_core.preflight import (inspect, check_draft, build_simulation, reference_mode,
                                 REFERENCE_RATE, REFERENCE_IBS, NS)


def documentary():
    row = fixture()
    row['dados_fiscais'].update({
        'homologacao_por_referencia': True, 'uso_exclusivo_homologacao': True,
        'fonte_referencia_homologacao': 'Documento sintético anterior, competência de teste.',
        'aliquota_xml': REFERENCE_RATE, 'ibscbs_tratamento': REFERENCE_IBS,
        'prestador_endereco_confirmado': False, 'tomador_confirmado': False,
        'fiscal_confirmado': False, 'consolidacao_confirmada': False,
        'competencia_confirmada': False, 'orientacao_contabil': ''})
    return row


class DocumentaryReferenceTests(unittest.TestCase):
    def test_reference_schema_valid_without_forging_attestations(self):
        row = documentary(); before = copy.deepcopy(row)
        result = inspect(row, date(2026, 10, 31))
        self.assertTrue(result['xsd_valido']); self.assertEqual(result['pendencias'], [])
        self.assertEqual(result['modo_validacao'], 'referencia_documental')
        self.assertIn('sem declarar validação contábil', result['aviso'])
        self.assertFalse(result['emissao_oficial_disponivel'])
        self.assertEqual(row, before)
        self.assertFalse(row['dados_fiscais']['fiscal_confirmado'])

    def test_documented_omissions_are_preserved_only_in_test_xml(self):
        row = documentary(); row['tpAmb'] = 1; row['ambiente'] = 'producao'
        root = build_simulation(row, datetime(2026, 10, 31, tzinfo=timezone.utc))
        ns = {'n': NS}
        self.assertEqual(root.find('n:infDPS/n:tpAmb', ns).text, '2')
        self.assertEqual(root.xpath('//*[local-name()="IBSCBS"]'), [])
        self.assertEqual(root.xpath('//*[local-name()="pAliq"]'), [])
        self.assertEqual(root.xpath('//*[local-name()="CST"]/text()'), ['06'])
        self.assertEqual(root.xpath('//*[local-name()="vDescCondIncond"]'), [])

    def test_actual_discounts_are_preserved_and_schema_valid(self):
        for unconditional, conditional in [('1,00','0,00'),('0,00','2,00'),('1,00','2,00')]:
            with self.subTest(unconditional=unconditional,conditional=conditional):
                row=documentary()
                row['dados_fiscais'].update(desconto_incondicionado=unconditional,desconto_condicionado=conditional)
                result=inspect(row,date(2026,10,31))
                self.assertTrue(result['xsd_valido']);self.assertEqual(result['pendencias'],[])
                root=build_simulation(row,datetime(2026,10,31,tzinfo=timezone.utc))
                self.assertEqual(root.xpath('//*[local-name()="vDescIncond"]/text()'),[unconditional.replace(',','.')])
                self.assertEqual(root.xpath('//*[local-name()="vDescCond"]/text()'),[conditional.replace(',','.')])

    def test_opt_in_exclusivity_and_source_are_required(self):
        for field, value in [('homologacao_por_referencia', False),
                             ('homologacao_por_referencia', 'true'),
                             ('uso_exclusivo_homologacao', False),
                             ('uso_exclusivo_homologacao', 'true'),
                             ('fonte_referencia_homologacao', ''),
                             ('fonte_referencia_homologacao', ' '),
                             ('fonte_referencia_homologacao', 'x'*1001)]:
            with self.subTest(field=field, value=value):
                row = documentary(); row['dados_fiscais'][field] = value
                self.assertFalse(reference_mode(row))
                self.assertTrue(check_draft(row))
                self.assertFalse(inspect(row)['xsd_valido'])

    def test_documentary_choices_are_not_accepted_as_fiscal_attestations(self):
        row = fixture(); row['dados_fiscais']['aliquota_xml'] = REFERENCE_RATE
        row['dados_fiscais']['ibscbs_tratamento'] = REFERENCE_IBS
        pending = {x['campo'] for x in check_draft(row)}
        self.assertIn('aliquota_xml', pending); self.assertIn('ibscbs_tratamento', pending)
        row = fixture(); row['dados_fiscais']['fiscal_confirmado'] = False
        self.assertIn('fiscal_confirmado', {x['campo'] for x in check_draft(row)})

    def test_field_coherence_remains_mandatory(self):
        for field, value in [('codigo_nacional', '11.05.01'), ('nbs', '000000000'),
                             ('iss_aliquota', '6,00'), ('pis_cofins_base', '1,00'),
                             ('irrf', '1,00'), ('desconto_condicionado', ''),
                             ('ibscbs_tratamento', 'Não aplicável conforme validação contábil'),
                             ('aliquota_xml', 'Não informar conforme regra municipal'),
                             ('cst', '000'), ('ibs', '1,00'),
                             ('tomador_cnpj', '00000000000000'), ('tomador_cep', '')]:
            with self.subTest(field=field):
                row = documentary(); row['dados_fiscais'][field] = value
                self.assertFalse(inspect(row)['xsd_valido'])
        row = documentary(); row['valor_rem'] = '-1'
        self.assertFalse(inspect(row)['xsd_valido'])

    def test_status_describes_reference_without_accessing_a1(self):
        row = documentary(); row.update(emitente_cnpj='46167015000140', updated_at='v1')
        with patch.object(emission, 'api_json', return_value=[row]), \
             patch.object(emission, 'load', return_value=None), \
             patch.object(emission, 'worker') as worker, patch.object(emission, 'rpc') as rpc:
            result = emission.operate({}, 'admin', {'acao':'status', 'rascunho_id':1, 'versao':'v1'})
        self.assertEqual(result['modo_validacao'], 'referencia_documental')
        self.assertFalse(result['emissao_oficial_disponivel'])
        worker.assert_not_called(); rpc.assert_not_called()

    def test_status_uses_reserved_snapshot_even_after_draft_mode_changes(self):
        snapshot = documentary(); row = fixture()
        row.update(emitente_cnpj='46167015000140', updated_at='v2')
        reservation = {'snapshot': snapshot, 'estado': 'pendente_consulta'}
        with patch.object(emission, 'api_json', return_value=[row]), \
             patch.object(emission, 'load', return_value=reservation):
            result = emission.operate({}, 'admin', {'acao':'status', 'rascunho_id':1, 'versao':'v2'})
        self.assertEqual(result['modo_validacao'], 'referencia_documental')


if __name__ == '__main__':
    unittest.main()
