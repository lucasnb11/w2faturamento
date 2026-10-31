import base64
import copy
import json
import os
import types
import unittest
from unittest.mock import patch

from api.nfse.certificado import SafeError, validate_and_encrypt
from nfse_core import emission as e, emission_worker as w, protocol as p, national
from tests import test_preparation
from tests.test_a1 import create_a1
from tests.test_protocol import synthetic_nfse
from cryptography.hazmat.primitives.serialization import pkcs12


class EmissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.key=os.urandom(32);a1=create_a1();cls.record=validate_and_encrypt(a1,cls.key)
        cls.private,cls.certificate,_=pkcs12.load_key_and_certificates(base64.b64decode(a1['pfx_base64']),a1['senha'].encode())
    def setUp(self):
        self.r=test_preparation.PreparationTests().reservation();self.r['id']='00000000-0000-0000-0000-000000000001'
        self.body={'acao':'preparar','rascunho_id':1,'versao':self.r['rascunho_versao']}
    def prepare(self):
        return w.execute({'action':'preparar','key':base64.b64encode(self.key).decode(),'record':self.record,'reservation':self.r})['documento']
    def test_real_preparation_opens_synthetic_a1_and_returns_only_cipher(self):
        document=self.prepare()
        xml=p.unseal(document,self.key,self.r['dps_id'],'dps')
        self.assertIn(b'<Signature',xml)
        self.assertNotIn('senha',json.dumps(document));self.assertNotIn('xml_base64',document)
    def test_real_child_process_prepares_without_inheriting_server_secrets(self):
        with patch.object(e,'api_json',return_value=[self.record]),patch.dict(os.environ,{'SUPABASE_SECRET_KEY':'not-in-child'}):
            result=e.worker({'encryption_key':self.key},self.r,'preparar')
        self.assertIn(b'<Signature',p.unseal(result['documento'],self.key,self.r['dps_id'],'dps'))
        self.assertNotIn('not-in-child',json.dumps(result))
    def test_pending_fiscal_data_blocks_before_reserve_or_a1(self):
        draft=copy.deepcopy(self.r['snapshot']);draft['dados_fiscais']['fiscal_confirmado']=False
        def database(config,path,**kwargs):
            self.assertFalse(kwargs)
            self.assertNotIn('nfse_certificados_a1',path)
            return [draft] if 'nfse_rascunhos?' in path else []
        with patch.object(e,'api_json',side_effect=database),patch.object(e,'worker') as worker:
            result=e.operate({},'admin',self.body)
        self.assertTrue(result['pendencias']);self.assertEqual(result['situacao']['estado'],'nao_reservada');worker.assert_not_called()
    def test_prepare_repetition_returns_same_signed_state_without_resigning(self):
        signed={**self.r,'estado':'assinada','dps_xml_cifrado':'private'}
        with patch.object(e,'api_json',return_value=[self.r['snapshot']]),patch.object(e,'load',return_value=signed),patch.object(e,'rpc') as rpc,patch.object(e,'worker') as worker:
            result=e.operate({},'admin',self.body)
        rpc.assert_not_called();worker.assert_not_called();self.assertEqual(result['situacao']['estado'],'assinada');self.assertNotIn('private',json.dumps(result))
    def test_timeout_after_claim_becomes_pending_and_blocks_second_send(self):
        signed={**self.r,'estado':'assinada','dps_xml_cifrado':'private'}
        state={'value':signed};calls=[]
        def rpc(config,name,payload):
            calls.append(name)
            if name=='nfse_iniciar_envio_homologacao':state['value']={**signed,'estado':'enviando'}
            elif name=='nfse_gravar_retorno_homologacao':state['value']={**state['value'],'estado':payload['p_novo']}
            return state['value']
        with patch.object(e,'api_json',return_value=[self.r['snapshot']]),patch.object(e,'load',side_effect=lambda *_:state['value']),patch.object(e,'rpc',side_effect=rpc),patch.object(e,'worker',side_effect=SafeError(503,'TIMEOUT','interrompido')) as worker:
            result=e.operate({},'admin',{**self.body,'acao':'transmitir'})
            self.assertEqual(result['situacao']['estado'],'pendente_consulta')
            with self.assertRaises(SafeError):e.operate({},'admin',{**self.body,'acao':'transmitir'})
        self.assertEqual(worker.call_count,1);self.assertEqual(calls,['nfse_iniciar_envio_homologacao','nfse_gravar_retorno_homologacao'])
    def test_changed_draft_still_allows_reconciliation_of_immutable_snapshot(self):
        draft={**self.r['snapshot'],'updated_at':'changed'};pending={**self.r,'estado':'pendente_consulta'}
        with patch.object(e,'api_json',return_value=[draft]),patch.object(e,'load',return_value=pending),patch.object(e,'worker',return_value={'estado':'pendente_consulta','http':404,'codigos':[]}) as worker,patch.object(e,'finish',return_value=pending):
            result=e.operate({},'admin',{**self.body,'acao':'conciliar','versao':'changed'})
        self.assertEqual(worker.call_args.args[1]['snapshot'],self.r['snapshot']);self.assertEqual(result['situacao']['estado'],'pendente_consulta')
    def test_existing_dps_never_posts(self):
        transport=types.SimpleNamespace(contract=lambda:True,request=lambda *args:(200,{'chaveAcesso':'1'*50}))
        with patch.object(w,'reconcile',return_value={'estado':'pendente_consulta'}) as reconcile:
            result=w.transmit(transport,b'xml',self.r['dps_id'],self.key)
        self.assertEqual(result['estado'],'pendente_consulta');reconcile.assert_called_once()
    def test_transmission_uses_single_post_and_validates_authorized_xml(self):
        signed=p.unseal(self.prepare(),self.key,self.r['dps_id'],'dps');nfse,access=synthetic_nfse(signed,self.private,self.certificate)
        response={'tipoAmbiente':2,'idDps':self.r['dps_id'],'chaveAcesso':access,'nfseXmlGZipB64':p.pack(nfse)}
        calls=[]
        def request(method,path,body=None):
            calls.append((method,path,body))
            return (404,None) if method=='GET' else (201,response)
        result=w.transmit(types.SimpleNamespace(contract=lambda:True,request=request),signed,self.r['dps_id'],self.key)
        self.assertEqual(result['estado'],'autorizada');self.assertEqual([c[0] for c in calls],['GET','POST'])
        self.assertEqual(p.unpack(calls[1][2]['dpsXmlGZipB64']),signed)
        self.assertEqual(p.unseal(result['documento'],self.key,self.r['dps_id'],'nfse'),nfse)
    def test_unconfirmed_contract_or_forbidden_get_does_not_post(self):
        for contract,status in [(False,404),(True,403),(True,503)]:
            calls=[]
            def request(*args):calls.append(args);return status,None
            result=w.transmit(types.SimpleNamespace(contract=lambda:contract,request=request),b'xml',self.r['dps_id'],self.key)
            self.assertEqual(result['estado'],'pendente_consulta');self.assertFalse(any(c[0]=='POST' for c in calls))
    def test_worker_network_timeout_does_not_retry_post(self):
        document=self.prepare();reservation={**self.r,'estado':'enviando',**{'dps_xml_'+k:v for k,v in document.items()}}
        calls=[]
        def request(method,path,body=None):
            calls.append(method)
            if method=='POST':raise TimeoutError()
            return 404,None
        transport=types.SimpleNamespace(contract=lambda:True,request=request)
        with patch.object(w,'Transport',return_value=transport):
            result=w.execute({'action':'transmitir','key':base64.b64encode(self.key).decode(),'record':self.record,'reservation':reservation})
        self.assertEqual(result['estado'],'pendente_consulta');self.assertEqual(calls,['GET','POST'])
    def test_unknown_or_incomplete_error_list_is_not_final_rejection(self):
        for result,expected in [({'erros':[{'codigo':'E0714'}]},'rejeitada'),({'erros':[{'codigo':'E0714'},{'descricao':'not-a-safe-code'}]},'pendente_consulta')]:
            transport=types.SimpleNamespace(contract=lambda:True,request=lambda method,*args:(404,None) if method=='GET' else (400,result))
            self.assertEqual(w.transmit(transport,b'xml',self.r['dps_id'],self.key)['estado'],expected)
    def test_transport_is_pinned_and_does_not_follow_redirects(self):
        connection=types.SimpleNamespace(request=lambda *a,**k:None,getresponse=lambda:types.SimpleNamespace(status=302),close=lambda:None)
        with patch.object(w.http.client,'HTTPSConnection',return_value=connection) as create:
            with self.assertRaises(ValueError):w.Transport(None).request('GET',w.DOCS[0])
            self.assertEqual(create.call_args.args[0],national.HOST)
        with patch.object(w.http.client,'HTTPSConnection') as create:
            for method,path,body in [('POST','https://evil.example',{}),('GET','/nfse/'+'1'*49,None),('POST','/nfse',{'url':'evil'}),('GET','/dps/DPS-invalid',None)]:
                with self.assertRaises(ValueError):w.Transport(None).request(method,path,body)
            create.assert_not_called()


if __name__=='__main__':unittest.main()
