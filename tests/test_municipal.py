"""Cenários sintéticos: competência, bloqueio antes de numeração e histórico."""
import base64
import copy
import unittest
from unittest.mock import patch

from nfse_core import municipal as m, emission as e, emission_worker as w
from tests import test_preparation as preparation
from tests import test_emission as synthetic

CODE = '26.01.01.000'


def history():
    return {'aliquotas': {CODE: [
        {'DtIni':'2026-01-26T00:00:00','DtFim':None,'Incidencia':'NÃO','Aliq':None},
        {'DtIni':'2025-09-24T00:00:00','DtFim':'2026-01-25T00:00:00','Incidencia':'SIM','Aliq':5}]}}


class MunicipalTests(unittest.TestCase):
    def draft(self, competence='2026-05-01'):
        draft=copy.deepcopy(preparation.PreparationTests().reservation()['snapshot'])
        draft['dados_fiscais']['competencia']=competence
        draft['dados_fiscais']['iss_aliquota']='5,00'
        return draft

    def test_chooses_competence_instead_of_latest_or_first_record(self):
        for competence, allowed in [('2026-01-25',True),('2026-01-26',False),('2026-05-01',False),('2026-10-01',False)]:
            result=m.evaluate_history(history(),self.draft(competence))
            self.assertEqual(result['liberado'],allowed)
            self.assertEqual(result['competencia'],competence)
        self.assertIsNone(m.evaluate_history(history(),self.draft())['aliquota'])

    def test_missing_overlapping_malformed_or_different_service_is_not_permission(self):
        cases=[{}, {'aliquotas':{CODE:[]}}, {'aliquotas':{'26.01.01.001':history()['aliquotas'][CODE]}}]
        overlap=history();overlap['aliquotas'][CODE].append(copy.deepcopy(overlap['aliquotas'][CODE][0]));cases.append(overlap)
        malformed=history();malformed['aliquotas'][CODE][0]['DtIni']='bad';cases.append(malformed)
        missing=history();del missing['aliquotas'][CODE][0]['DtFim'];cases.append(missing)
        for case in cases:
            self.assertFalse(m.evaluate_history(case,self.draft())['liberado'])
        self.assertFalse(m.evaluate_history(history(),self.draft('2025-09-23'))['liberado'])
        for http in [400,403,404,429,500,None]:
            self.assertFalse(m.evaluate_history(history(),self.draft('2026-01-25'),http)['liberado'])

    def test_zero_is_not_null_and_rate_difference_does_not_rewrite_draft(self):
        draft=self.draft();before=copy.deepcopy(draft)
        for value in [0,None,2,'NaN',True]:
            record=history();record['aliquotas'][CODE][0].update(Incidencia='SIM',Aliq=value)
            self.assertFalse(m.evaluate_history(record,draft)['liberado'])
        self.assertEqual(before,draft)

    def test_only_declared_get_for_fixed_municipality_and_server_service(self):
        doc={'paths':{m.HISTORY:{'get':{'parameters':[
            {'name':'codigoMunicipio','in':'path','required':True},
            {'name':'codigoServico','in':'path','required':True}]}}}}
        with patch.object(m,'read_parameters',side_effect=[(200,doc),(200,history())]) as read:
            self.assertFalse(m.validate_municipal(None,self.draft())['liberado'])
        self.assertEqual(read.call_args_list[-1].args[1],'/1500800/'+CODE+'/historicoaliquotas')
        doc['paths'][m.HISTORY]['get']['parameters'].append({'name':'token','in':'query','required':True})
        with patch.object(m,'read_parameters',return_value=(200,doc)) as read:
            self.assertFalse(m.validate_municipal(None,self.draft())['liberado'])
        self.assertEqual(read.call_count,1)
        with patch.object(m,'read_parameters',side_effect=TimeoutError()):
            self.assertFalse(m.validate_municipal(None,self.draft())['liberado'])
        draft=self.draft();draft['dados_fiscais']['codigo_municipal']='../secret'
        with self.assertRaises(ValueError):m.context_for(draft)

    def test_all_mutations_block_before_rpc_on_conflict(self):
        reservation=preparation.PreparationTests().reservation()
        draft=reservation['snapshot'];reservation.update(id='test-id',created_at='2026-01-01T00:00:00Z',dps_xml_cifrado='opaque')
        for action,state,reserved in [('preparar','reservada',False),('transmitir','assinada',True),('nova_tentativa','pendente_consulta',True)]:
            current={**reservation,'estado':state,'retorno_http':404}
            body={'acao':action,'rascunho_id':draft['id'],'versao':draft['updated_at'],'confirmacao':'NOVA_DPS_SOMENTE_HOMOLOGACAO'}
            with patch.object(e,'api_json',return_value=[draft]),patch.object(e,'load',return_value=current if reserved else None),patch.object(e,'municipal_check',return_value={'liberado':False,'situacao':'divergente'}) as check,patch.object(e,'rpc') as rpc,patch.object(e,'worker') as worker:
                result=e.operate({},'admin',body)
            self.assertTrue(result['bloqueio_parametros']);check.assert_called_once();rpc.assert_not_called();worker.assert_not_called()

    def test_worker_diagnostic_cannot_sign_reserve_or_transmit(self):
        synthetic.EmissionTests.setUpClass.__func__(self.__class__)
        with patch.object(w,'validate_municipal',return_value={'liberado':False}) as validate,patch.object(w,'sign_homologation_dps') as sign,patch.object(w,'Transport') as transport:
            result=w.execute({'action':'validar_parametros','reservation':{'snapshot':self.draft()},'key':base64.b64encode(self.key).decode(),'record':self.record})
        self.assertFalse(result['parametros_iss']['liberado']);validate.assert_called_once();sign.assert_not_called();transport.assert_not_called()

    def test_submission_error_survives_later_404_and_private_fields_are_removed(self):
        events=[{'estado':'enviando'}, {'estado':'pendente_consulta','created_at':'2026-01-01T00:00:00Z','detalhes':{'http':400,'codigos':['E0429'],'xml':'private'}}, {'estado':'pendente_consulta','detalhes':{'http':404,'codigos':[]}}]
        with patch.object(e,'api_json',return_value=events):
            result=e.submission_result({}, {'id':'test-id'})
        self.assertEqual(result['http'],400);self.assertEqual(result['codigos'],['E0429']);self.assertNotIn('private',str(result))
        events[1]['detalhes']={}
        with patch.object(e,'api_json',return_value=events):
            self.assertIsNone(e.submission_result({}, {'id':'test-id'}))
