import copy
from datetime import datetime, timezone
import unittest

from lxml import etree

from nfse_core.preflight import CNPJ, NS, schema
from nfse_core.preparation import application_series, numbering_status, build_reserved_dps
from tests.test_preflight import fixture


class PreparationTests(unittest.TestCase):
    def reservation(self):
        row = fixture()
        row.update(emitente_cnpj=CNPJ, updated_at='2026-10-30T20:00:00+00:00')
        return {'snapshot': row, 'rascunho_id': row['id'], 'rascunho_versao': row['updated_at'],
            'serie': 1, 'numero': 23, 'estado': 'reservada',
            'dps_id': 'DPS150080024616701500014000001000000000000023'}

    def test_only_application_series_and_no_boolean_numbers(self):
        for value in [0, 50000, 70000, 89999, True, False, '1', None, -1]:
            self.assertFalse(application_series(value))
        for value in [1, 49999]:
            self.assertTrue(application_series(value))

    def test_numbering_metadata_does_not_reserve_or_disclose_rows(self):
        row = {'cnpj': CNPJ, 'serie': 1, 'proximo_numero': 23, 'snapshot': 'private'}
        status = numbering_status([row])
        self.assertTrue(status['numeracao_pronta'])
        self.assertEqual(status['proximo_numero'], '23')
        self.assertFalse(status['numeracao_reservada'])
        self.assertNotIn('private', str(status))
        for changes in [{'serie': 70000}, {'cnpj': 'wrong'}, {'proximo_numero': True}, {'proximo_numero': 999999999999999}]:
            self.assertFalse(numbering_status([{**row, **changes}])['numeracao_pronta'])
        for rows in [None, [], [None], [row, row]]:
            self.assertFalse(numbering_status(rows)['numeracao_pronta'])

    def test_reserved_snapshot_builds_valid_xml_without_mutating_input(self):
        reservation = self.reservation()
        before = copy.deepcopy(reservation)
        xml = build_reserved_dps(reservation, datetime(2026, 10, 30, tzinfo=timezone.utc))
        root = etree.fromstring(xml)
        schema().assertValid(root)
        self.assertEqual(root[0].get('Id'), reservation['dps_id'])
        self.assertEqual(root[0].find('{' + NS + '}nDPS').text, '23')
        self.assertEqual(root[0].find('{' + NS + '}serie').text, '1')
        self.assertEqual(root[0].find('{' + NS + '}tpAmb').text, '2')
        self.assertFalse(root.xpath('//*[local-name()="Signature"]'))
        self.assertEqual(reservation, before)

    def test_no_rebuilding_transmitted_reservation_or_stale_version(self):
        for changes in [{'serie': 70000}, {'numero': True}, {'dps_id': 'DPS-wrong'},
                        {'rascunho_versao': 'old'}, {'rascunho_id': 2},
                        *[{'estado': state} for state in ['assinada', 'enviando', 'pendente_consulta', 'autorizada', 'rejeitada']]]:
            with self.assertRaises(ValueError):
                build_reserved_dps({**self.reservation(), **changes})
        reservation = self.reservation()
        reservation['snapshot']['emitente_cnpj'] = 'wrong'
        with self.assertRaises(ValueError):
            build_reserved_dps(reservation)

    def test_fiscal_validation_still_blocks_reserved_draft(self):
        reservation = self.reservation()
        reservation['snapshot']['dados_fiscais']['codigo_nacional'] = '11.05.01'
        with self.assertRaises(ValueError):
            build_reserved_dps(reservation)


if __name__ == '__main__':
    unittest.main()
