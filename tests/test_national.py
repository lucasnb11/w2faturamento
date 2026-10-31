import base64
import json
import os
import ssl
import subprocess
import sys
import tempfile
from pathlib import Path
import types
import unittest
from unittest.mock import patch

from api.nfse.certificado import validate_and_encrypt, SafeError
from nfse_core import national
from tests.test_a1 import create_a1


def swagger():
    return {'openapi':'3.0.1','paths':{'/nfse':{'post':{'requestBody':{'content':{'application/json':{'schema':{'$ref':'#/components/schemas/DPS'}}}}}}},
        'components':{'schemas':{'DPS':{'type':'object','required':['dpsXmlGZipB64'],'properties':{'dpsXmlGZipB64':{'type':'string'}}}}}}


def parameters_swagger():
    return {'openapi':'3.0.1','paths':{'/parametros_municipais/{codigoMunicipio}/convenio':{'get':{'parameters':[{'name':'codigoMunicipio','in':'path','required':True}]}}}}


class NationalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.key=os.urandom(32)
        cls.record=validate_and_encrypt(create_a1(),cls.key)
    def test_decryption_and_in_memory_tls(self):
        material=national.decrypt_material(self.record,self.key)
        context=national.tls_context(material)
        self.assertTrue(context.check_hostname)
        self.assertEqual(context.verify_mode,ssl.CERT_REQUIRED)
        self.assertEqual(context.minimum_version,ssl.TLSVersion.TLSv1_2)
    def test_no_wrong_key_or_changed_metadata(self):
        for record,key in [(self.record,os.urandom(32)),({**self.record,'sha256':'0'*64},self.key),({**self.record,'cnpj':'11111111000191'},self.key),({**self.record,'key_version':2},self.key)]:
            with self.assertRaises(national.NationalError) as e:national.decrypt_material(record,key)
            self.assertNotIn(self.record['dados_cifrados'],str(e.exception))
    def test_contract_must_explicitly_declare_required_field(self):
        self.assertTrue(national.inspect_contract(swagger()))
        changed=swagger();changed['components']['schemas']['DPS']['required']=[]
        self.assertFalse(national.inspect_contract(changed))
        changed=swagger();changed['paths']['/nfse']['post']['requestBody']['content']['application/json']['schema']={'$ref':'https://evil.example/schema'}
        self.assertFalse(national.inspect_contract(changed))
    def test_diagnostic_only_reads_and_never_returns_raw_response(self):
        response={'cnpj':'private-data-not-for-output','convenio':'test'}
        with patch.object(national,'read_official',return_value=(200,swagger())) as read,patch.object(national,'read_parameters',side_effect=[(200,parameters_swagger()),(200,response)]) as parameters:
            result=national.diagnostic_worker(self.record,self.key)
        self.assertTrue(result['contrato_recepcao_identificado'])
        self.assertTrue(result['a1_prova_assinatura_local'])
        self.assertFalse(result['perfil_assinatura_dps_validado'])
        self.assertFalse(result['transmitido'])
        self.assertNotIn('private-data-not-for-output',str(result))
        self.assertEqual([x.args[1] for x in read.call_args_list],[national.DOCS[0]])
        self.assertEqual([x.args[1] for x in parameters.call_args_list],[national.DOCS[0],national.CONVENIO])
        self.assertTrue(result['consulta_convenio_rota_confirmada'])

    def test_key_proof_is_local_and_uses_fresh_non_fiscal_challenge(self):
        material=national.decrypt_material(self.record,self.key)
        with patch.object(national.os,'urandom',wraps=os.urandom) as random:
            self.assertTrue(national.prove_signing_key(material))
            self.assertTrue(national.prove_signing_key(material))
        self.assertEqual(random.call_args_list,[((32,),),((32,),)])
        other=national.decrypt_material(validate_and_encrypt(create_a1(),self.key),self.key)
        self.assertFalse(national.prove_signing_key((material[0],other[1],[])))

    def test_municipal_summary_excludes_private_and_free_text(self):
        summary=national.parameter_summary({'situacao':'ATIVO','dataInicio':'2026-10-01','cnpj':'private',
            'responsavel':{'status':'private'},'email':'private','observacao':'private',
            'aliquotas':[{'aliquota':5,'dataInicio':'2026-01-01'}]})
        self.assertNotIn('private',str(summary))
        self.assertIn({'campo':'situacao','valor':'ATIVO'},summary)
        self.assertIn({'campo':'aliquotas[0].aliquota','valor':5},summary)

    def test_parameter_discovery_cannot_return_external_or_write_routes(self):
        doc=parameters_swagger()
        doc['paths']['https://evil.example/aliquotas']={'get':{}}
        doc['paths']['/aliquotas']={'post':{}}
        routes=national.parameter_routes(doc)
        self.assertEqual(len(routes),1)
        self.assertEqual(routes[0]['rota'],'/parametros_municipais/{codigoMunicipio}/convenio')

    def test_rate_history_is_read_only_for_fixed_service_and_declared_route(self):
        doc=parameters_swagger()
        doc['paths']['/{codigoMunicipio}/{codigoServico}/historicoaliquotas']={'get':{}}
        with patch.object(national,'read_official',return_value=(200,swagger())),patch.object(national,'read_parameters',side_effect=[
            (200,doc),(200,{}),(200,[{'aliquota':0,'dataInicio':'2026-01-01','cnpj':'private'}])]) as read:
            result=national.diagnostic_worker(self.record,self.key)
        self.assertEqual(read.call_args_list[-1].args[1],'/1500800/260101/historicoaliquotas')
        self.assertEqual(result['historico_aliquotas_http'],200)
        self.assertIn({'campo':'[0].aliquota','valor':0},result['historico_aliquotas_resumo'])
        self.assertNotIn('private',str(result))
        self.assertFalse(result['transmitido'])

    def test_parameters_route_is_declared_unique_and_needs_no_extra_query(self):
        doc=parameters_swagger()
        self.assertEqual(national.parameter_endpoint(doc),national.CONVENIO)
        doc['paths']['/parametros_municipais/{codigoMunicipio}/convenio']['get']['parameters'].append({'name':'cnpj','in':'query','required':True})
        self.assertIsNone(national.parameter_endpoint(doc))
        doc=parameters_swagger()
        doc['paths']['/municipios/{codigoMunicipio}/convenio']={'get':{}}
        self.assertIsNone(national.parameter_endpoint(doc))
        for path in ['https://evil.example/municipios/{codigoMunicipio}/convenio','//evil.example/municipios/{codigoMunicipio}/convenio','/municipios/{codigoMunicipio}/convenio?url=x','/municipios/{codigoMunicipio}/convenio/{cnpj}']:
            self.assertIsNone(national.parameter_endpoint({'paths':{path:{'get':{}}}}))

    def test_parameters_supports_local_reference_not_external_reference(self):
        doc=parameters_swagger()
        doc['components']={'parameters':{'municipio':{'name':'codigoMunicipio','in':'path','required':True}}}
        params=doc['paths']['/parametros_municipais/{codigoMunicipio}/convenio']['get']
        params['parameters']=[{'$ref':'#/components/parameters/municipio'}]
        self.assertEqual(national.parameter_endpoint(doc),national.CONVENIO)
        params['parameters']=[{'$ref':'https://evil.example/parameter'}]
        self.assertIsNone(national.parameter_endpoint(doc))

    def test_parameters_use_adn_and_preserve_only_error_codes(self):
        document={'erros':[{'codigo':'E1234','descricao':'private-content'}]}
        response=types.SimpleNamespace(status=404,read=lambda n:json.dumps(document).encode())
        calls=[]
        connection=types.SimpleNamespace(request=lambda *a,**k:calls.append(a),getresponse=lambda:response,close=lambda:None)
        with patch.object(national.http.client,'HTTPSConnection',return_value=connection) as constructor:
            status,body=national.read_parameters(ssl.create_default_context(),national.CONVENIO)
            self.assertEqual(constructor.call_args.args[0],national.PARAM_HOST)
            self.assertEqual(calls[0][:2],('GET',national.PARAM_BASE+national.CONVENIO))
        self.assertEqual(status,404)
        self.assertEqual(national.error_codes(body),['E1234'])
        with patch.object(national,'read_official',return_value=(200,swagger())),patch.object(national,'read_parameters',side_effect=[(200,parameters_swagger()),(404,body)]):
            result=national.diagnostic_worker(self.record,self.key)
        self.assertFalse(result['consulta_convenio_recebida'])
        self.assertEqual(result['consulta_convenio_erro_codigos'],['E1234'])
        self.assertNotIn('private-content',str(result))

    def test_parameters_documentation_failure_does_not_guess_route(self):
        with patch.object(national,'read_official',return_value=(200,swagger())),patch.object(national,'read_parameters',return_value=(404,None)) as read:
            result=national.diagnostic_worker(self.record,self.key)
        self.assertEqual(len(read.call_args_list),len(national.DOCS))
        self.assertIsNone(result['consulta_convenio_http'])
        self.assertFalse(result['consulta_convenio_rota_confirmada'])
        self.assertIsNone(result['consulta_convenio_rota'])
    def test_egress_is_fixed_get_and_does_not_redirect(self):
        response=types.SimpleNamespace(status=302,read=lambda n:b'')
        connection=types.SimpleNamespace(request=lambda *a,**k:None,getresponse=lambda:response,close=lambda:None)
        with patch.object(national.http.client,'HTTPSConnection',return_value=connection) as constructor:
            with self.assertRaises(national.NationalError):national.read_official(ssl.create_default_context(),national.DOCS[0])
            self.assertEqual(constructor.call_args.args[0],national.HOST)
        with patch.object(national.http.client,'HTTPSConnection') as constructor:
            for path in ['https://evil.example','/nfse','/../../nfse','/dps/1',national.CONVENIO,'/parametros_municipais/9999999/convenio']:
                with self.assertRaises(national.NationalError):national.read_official(None,path)
            constructor.assert_not_called()
    def test_worker_timeout_and_secret_environment_is_not_inherited(self):
        config={'encryption_key':self.key}
        with patch.object(national,'api_json',return_value=[self.record]),patch.dict(os.environ,{'SUPABASE_SECRET_KEY':'never-inherit-this','NFSE_A1_ENCRYPTION_KEY':'also-private'}),patch.object(national.subprocess,'run',side_effect=subprocess.TimeoutExpired('worker',40)) as run:
            with self.assertRaises(SafeError) as e:national.diagnose_connection(config)
            self.assertEqual(e.exception.status,504)
            self.assertNotIn('SUPABASE_SECRET_KEY',run.call_args.kwargs['env'])
            self.assertNotIn('NFSE_A1_ENCRYPTION_KEY',run.call_args.kwargs['env'])
            self.assertNotIn(self.record['dados_cifrados'],str(run.call_args.args[0]))
    def test_worker_output_is_whitelisted(self):
        data={'transmitido':False,'emissao_oficial_disponivel':False,'ambiente':'homologacao','dados_cifrados':'never-return','aviso':'never-return'}
        with patch.object(national,'api_json',return_value=[self.record]),patch.object(national.subprocess,'run',return_value=types.SimpleNamespace(returncode=0,stdout=json.dumps(data).encode())):
            result=national.diagnose_connection({'encryption_key':self.key})
        self.assertNotIn('never-return',str(result))

    def test_worker_preserves_runtime_dependency_paths_without_secret_env(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory,'w2_runtime_vendor_test.py').write_text('VALUE="loaded"\n')
            with patch.object(sys,'path',[directory,*sys.path]),patch.dict(os.environ,{'SUPABASE_SECRET_KEY':'not-for-child'}):
                env=national.worker_environment()
            broken={**env,'PYTHONPATH':str(Path(national.__file__).resolve().parents[1])}
            command=[sys.executable,'-c','import w2_runtime_vendor_test; print(w2_runtime_vendor_test.VALUE)']
            # Usar outra pasta para não mascarar a importação pelo cwd.
            with tempfile.TemporaryDirectory() as cwd:
                old=subprocess.run(command,cwd=cwd,env=broken,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
                fixed=subprocess.run(command,cwd=cwd,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            self.assertNotEqual(old.returncode,0)
            self.assertEqual(fixed.returncode,0)
            self.assertEqual(fixed.stdout,b'loaded\n')
            self.assertNotIn('SUPABASE_SECRET_KEY',env)

    def test_real_subprocess_decrypts_synthetic_a1_and_uses_memfd(self):
        # Processo real com mesma entrada/ambiente do worker; transporte simulado.
        wrapper='''
import http.client,json,runpy,sys
class Response:
    status=200
    def read(self,limit):
        return json.dumps({'openapi':'3.0.1','paths':{'/nfse':{'post':{'requestBody':{'content':{'application/json':{'schema':{'type':'object','required':['dpsXmlGZipB64'],'properties':{'dpsXmlGZipB64':{'type':'string'}}}}}}}},'/parametros_municipais/{codigoMunicipio}/convenio':{'get':{}}}}).encode()
class Connection:
    def __init__(self,host,**kwargs): assert host in ['sefin.producaorestrita.nfse.gov.br','adn.producaorestrita.nfse.gov.br']
    def request(self,method,path,**kwargs): assert method=='GET'
    def getresponse(self): return Response()
    def close(self): pass
http.client.HTTPSConnection=Connection
sys.argv=[sys.argv[1],'--diagnostic']
runpy.run_path(sys.argv[0],run_name='__main__')
'''
        payload=json.dumps({'record':self.record,'key':base64.b64encode(self.key).decode()}).encode()
        with tempfile.TemporaryDirectory() as cwd:
            result=subprocess.run([sys.executable,'-c',wrapper,str(Path(national.__file__).resolve())],input=payload,
                cwd=cwd,env=national.worker_environment(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10)
        self.assertEqual(result.returncode,0)
        data=json.loads(result.stdout)
        self.assertTrue(data['contrato_recepcao_identificado'])
        self.assertIs(data['transmitido'],False)
        self.assertNotIn('dados_cifrados',data)

    def test_safe_error_stage_is_reported_without_stderr_or_payload(self):
        import contextlib,io
        cases=[
            types.SimpleNamespace(returncode=1,stdout=b'',stderr=b'ModuleNotFoundError: private-error'),
            types.SimpleNamespace(returncode=1,stdout=json.dumps({'erro_codigo':'A1_PREPARO_TLS'}).encode(),stderr=b'private-error'),
            types.SimpleNamespace(returncode=1,stdout=json.dumps({'erro_codigo':'private-error'}).encode(),stderr=b'private-error')]
        expected=['PROCESSO_DEPENDENCIA','A1_PREPARO_TLS','DIAGNOSTICO_INTERNO']
        for result,code in zip(cases,expected):
            logs=io.StringIO()
            with patch.object(national,'api_json',return_value=[self.record]),patch.object(national.subprocess,'run',return_value=result),contextlib.redirect_stdout(logs):
                with self.assertRaises(SafeError) as e:national.diagnose_connection({'encryption_key':self.key})
            self.assertEqual(e.exception.code,code)
            self.assertNotIn('private-error',logs.getvalue()+e.exception.message)


if __name__=='__main__':unittest.main()
