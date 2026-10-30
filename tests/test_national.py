import base64
import json
import os
import ssl
import subprocess
import types
import unittest
from unittest.mock import patch

from api.nfse.certificado import validate_and_encrypt, SafeError
from nfse_core import national
from tests.test_a1 import create_a1


def swagger():
    return {'openapi':'3.0.1','paths':{'/nfse':{'post':{'requestBody':{'content':{'application/json':{'schema':{'$ref':'#/components/schemas/DPS'}}}}}}},
        'components':{'schemas':{'DPS':{'type':'object','required':['dpsXmlGZipB64'],'properties':{'dpsXmlGZipB64':{'type':'string'}}}}}}


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
        with patch.object(national,'read_official',side_effect=[(200,swagger()),(200,response)]) as read:
            result=national.diagnostic_worker(self.record,self.key)
        self.assertTrue(result['contrato_recepcao_identificado'])
        self.assertFalse(result['transmitido'])
        self.assertNotIn('private-data-not-for-output',str(result))
        self.assertEqual([x.args[1] for x in read.call_args_list],[national.DOCS[0],national.CONVENIO])
    def test_egress_is_fixed_get_and_does_not_redirect(self):
        response=types.SimpleNamespace(status=302,read=lambda n:b'')
        connection=types.SimpleNamespace(request=lambda *a,**k:None,getresponse=lambda:response,close=lambda:None)
        with patch.object(national.http.client,'HTTPSConnection',return_value=connection) as constructor:
            with self.assertRaises(national.NationalError):national.read_official(ssl.create_default_context(),national.CONVENIO)
            self.assertEqual(constructor.call_args.args[0],national.HOST)
        with patch.object(national.http.client,'HTTPSConnection') as constructor:
            for path in ['https://evil.example','/nfse','/../../nfse','/dps/1','/parametros_municipais/9999999/convenio']:
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


if __name__=='__main__':unittest.main()
