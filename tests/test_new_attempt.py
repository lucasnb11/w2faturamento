"""Nova numeração explícita em homologação; não repete o POST anterior."""
import base64
import copy
from datetime import datetime, timezone
import unittest
from unittest.mock import patch
import types

from api.nfse.certificado import SafeError
from nfse_core import emission as e, emission_worker as w
from tests import test_emission as synthetic


class NewAttemptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        synthetic.EmissionTests.setUpClass.__func__(cls)
    def setUp(self):
        synthetic.EmissionTests.setUp(self)
    def pending(self):
        return {**self.r,'estado':'pendente_consulta','retorno_http':404,
                'dps_xml_cifrado':'opaque','created_at':'2026-01-01T00:00:00Z',
                'updated_at':'old-version','tentativa':1}
    def retry_body(self):
        return {**self.body,'acao':'nova_tentativa','confirmacao':'NOVA_DPS_SOMENTE_HOMOLOGACAO'}
    def test_retry_eligibility_excludes_other_states_and_recent_records(self):
        pending=self.pending();self.assertTrue(e.retry_available(pending))
        for change in [{'estado':'enviando'},{'estado':'autorizada'},{'retorno_http':400},
                       {'chave_acesso':'1'*50},{'nfse_xml_cifrado':'opaque'},
                       {'created_at':datetime.now(timezone.utc).isoformat()},
                       {'created_at':'invalid'},{'dps_xml_cifrado':None}]:
            self.assertFalse(e.retry_available({**pending,**change}))
    def test_explicit_retry_rechecks_absence_then_only_reserves(self):
        pending=self.pending();original=copy.deepcopy(pending)
        new={**self.r,'id':'new-id','estado':'reservada','numero':24,'tentativa':2,'anterior_id':pending['id']}
        with patch.object(e,'api_json',return_value=[self.r['snapshot']]),patch.object(e,'load',return_value=pending),\
             patch.object(e,'worker',return_value={'ausente':True,'http':404}) as worker,patch.object(e,'rpc',return_value=new) as rpc:
            result=e.operate({},'admin',self.retry_body())
        self.assertEqual(worker.call_count,1);self.assertEqual(worker.call_args.args[2],'verificar_ausencia')
        self.assertEqual(rpc.call_args.args[1],'nfse_nova_tentativa_homologacao')
        self.assertEqual(rpc.call_args.args[2]['p_anterior_versao'],'old-version')
        self.assertEqual(result['situacao']['tentativa'],2);self.assertFalse(result['nova_tentativa_disponivel'])
        self.assertEqual(pending,original)
    def test_no_confirmation_does_not_open_a1_or_allocate_number(self):
        body=self.retry_body();body.pop('confirmacao')
        with patch.object(e,'api_json',return_value=[self.r['snapshot']]),patch.object(e,'load',return_value=self.pending()),\
             patch.object(e,'worker') as worker,patch.object(e,'rpc') as rpc:
            with self.assertRaises(SafeError):e.operate({},'admin',body)
        worker.assert_not_called();rpc.assert_not_called()
    def test_any_other_get_result_blocks_new_number(self):
        for absence in [{'ausente':False,'http':200},{'ausente':False,'http':500},{'ausente':True,'http':200},{}]:
            with patch.object(e,'api_json',return_value=[self.r['snapshot']]),patch.object(e,'load',return_value=self.pending()),\
                 patch.object(e,'worker',return_value=absence),patch.object(e,'rpc') as rpc:
                with self.assertRaises(SafeError):e.operate({},'admin',self.retry_body())
            rpc.assert_not_called()
    def test_invalid_draft_blocks_even_the_read_only_a1_query(self):
        draft=copy.deepcopy(self.r['snapshot']);draft['dados_fiscais']['irrf']='1,00'
        with patch.object(e,'api_json',return_value=[draft]),patch.object(e,'load',return_value=self.pending()),\
             patch.object(e,'worker') as worker,patch.object(e,'rpc') as rpc:
            result=e.operate({},'admin',self.retry_body())
        self.assertTrue(result['pendencias']);worker.assert_not_called();rpc.assert_not_called()
    def test_absence_worker_is_get_only_and_does_not_open_old_xml(self):
        calls=[];transport=types.SimpleNamespace(contract=lambda:True,request=lambda *args:(calls.append(args) or (404,None)))
        with patch.object(w,'Transport',return_value=transport),patch.object(w,'unseal',side_effect=AssertionError('não abrir XML')):
            result=w.execute({'action':'verificar_ausencia','key':base64.b64encode(self.key).decode(),
                              'record':self.record,'reservation':self.pending()})
        self.assertEqual(result,{'ausente':True,'http':404})
        self.assertEqual(calls,[('GET','/dps/'+self.r['dps_id'])])
    def test_latest_attempt_is_selected_without_disclosing_older_envelopes(self):
        with patch.object(e,'api_json',return_value=[self.pending()]) as api:
            e.load({},1)
        self.assertIn('order=tentativa.desc',api.call_args.args[1])
        self.assertNotIn('opaque',str(e.metadata(self.pending())))


    def rejected_signature(self):
        return {**self.pending(),'estado':'rejeitada','retorno_http':400,'erros_codigos':['E0714']}
    def test_only_isolated_e0714_allows_controlled_retry_after_rejection(self):
        rejected=self.rejected_signature();self.assertTrue(e.retry_available(rejected))
        for change in [{'erros_codigos':['E0715']},{'erros_codigos':['E0714','E0715']},
                       {'erros_codigos':[]},{'retorno_http':None},{'retorno_http':500},
                       {'estado':'enviando'}]:
            self.assertFalse(e.retry_available({**rejected,**change}))
    def test_e0714_absence_query_remains_get_only(self):
        calls=[];transport=types.SimpleNamespace(contract=lambda:True,request=lambda *args:(calls.append(args) or (404,None)))
        with patch.object(w,'Transport',return_value=transport),patch.object(w,'unseal',side_effect=AssertionError('não abrir XML')):
            result=w.execute({'action':'verificar_ausencia','key':base64.b64encode(self.key).decode(),
                              'record':self.record,'reservation':self.rejected_signature()})
        self.assertTrue(result['ausente']);self.assertEqual(calls,[('GET','/dps/'+self.r['dps_id'])])
    def test_known_rejected_xml_can_be_queried_without_requiring_a_valid_signature(self):
        document=synthetic.EmissionTests.prepare(self)
        reservation={**self.rejected_signature(),**{'dps_xml_'+k:v for k,v in document.items()}}
        calls=[];transport=types.SimpleNamespace(request=lambda *args:(calls.append(args) or (404,None)))
        with patch.object(w,'Transport',return_value=transport),patch.object(w,'verify_homologation_dps',side_effect=AssertionError('GET não depende da assinatura rejeitada')):
            result=w.execute({'action':'conciliar','key':base64.b64encode(self.key).decode(),
                              'record':self.record,'reservation':reservation})
        self.assertEqual(result['http'],404);self.assertEqual(calls,[('GET','/dps/'+self.r['dps_id'])])
    def test_transmission_still_rejects_modified_signature_before_any_network(self):
        from nfse_core import protocol as protocol
        document=synthetic.EmissionTests.prepare(self)
        xml=protocol.unseal(document,self.key,self.r['dps_id'],'dps').replace(b'15169.50',b'15169.51')
        document=protocol.seal(xml,self.key,self.r['dps_id'],'dps')
        reservation={**self.r,'estado':'enviando',**{'dps_xml_'+k:v for k,v in document.items()}}
        with patch.object(w,'Transport') as transport:
            with self.assertRaises(ValueError):
                w.execute({'action':'transmitir','key':base64.b64encode(self.key).decode(),
                           'record':self.record,'reservation':reservation})
        transport.assert_not_called()
