import copy
from datetime import datetime, timedelta, timezone
from http.server import HTTPServer
import json
import threading
import unittest
from unittest.mock import patch
from urllib import error, request

from api.nfse import integracao
from api.nfse.certificado import SafeError
from tests.test_preflight import fixture


class IntegrationHttpTests(unittest.TestCase):
    def setUp(self):
        self.config={'origin':'https://faturamento-jade.vercel.app'}
        self.row=fixture();self.row['updated_at']='2026-10-30T20:00:00+00:00'
        now=datetime.now(timezone.utc)
        self.certificate={'valido_desde':(now-timedelta(days=1)).isoformat(),'valido_ate':(now+timedelta(days=1)).isoformat()}
        self.calls=[]
        def query(config,path,*args,**kwargs):
            self.calls.append((path,args,kwargs))
            if path.startswith('/rest/v1/nfse_homologacao_config?'):
                return [{'cnpj':'46167015000140','serie':None,'proximo_numero':1}]
            self.assertTrue(path.startswith('/rest/v1/nfse_rascunhos?'))
            self.assertFalse(args)
            return [copy.deepcopy(self.row)]
        self.patchers=[patch.object(integracao,'settings',return_value=self.config),
            patch.object(integracao,'authorize',return_value='administrator-id'),
            patch.object(integracao,'public_status',return_value=self.certificate),
            patch.object(integracao,'api_json',side_effect=query)]
        for p in self.patchers:p.start()
        self.server=HTTPServer(('127.0.0.1',0),integracao.handler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join()
        for p in reversed(self.patchers):p.stop()
    def call(self,body=None,method='POST',origin='https://faturamento-jade.vercel.app'):
        headers={'Content-Type':'application/json','Origin':origin}
        data=json.dumps(body or {'rascunho_id':1,'versao':self.row['updated_at']}).encode() if method=='POST' else None
        req=request.Request(f'http://127.0.0.1:{self.server.server_port}/api/nfse/integracao',data=data,method=method,headers=headers)
        try:
            with request.urlopen(req) as r:return r.status,json.loads(r.read()),r.headers
        except error.HTTPError as e:return e.code,json.loads(e.read()),e.headers
    def test_validates_saved_data_without_write_or_certificate_access(self):
        status,body,headers=self.call()
        self.assertEqual(status,200)
        self.assertTrue(body['xsd_valido'])
        self.assertTrue(body['a1_dentro_validade'])
        self.assertFalse(body['transmissao_disponivel'])
        self.assertFalse(body['numeracao_reservada'])
        self.assertEqual(len(self.calls),1)
        self.assertNotIn('xml',body)
        self.assertEqual(headers['Cache-Control'],'no-store')
    def test_blocks_bad_origin_unauthorized_and_stale_draft(self):
        self.assertEqual(self.call(origin='https://evil.example')[0],403)
        with patch.object(integracao,'authorize',side_effect=SafeError(403,'ACESSO_RESTRITO','Somente administradores.')):
            self.assertEqual(self.call()[0],403)
        self.assertEqual(self.call({'rascunho_id':1,'versao':'old'})[0],409)
    def test_no_client_supplied_fiscal_override(self):
        self.assertEqual(self.call({'rascunho_id':1,'versao':self.row['updated_at'],'dados_fiscais':{}})[0],400)
        self.assertEqual(self.call({'rascunho_id':True,'versao':self.row['updated_at']})[0],400)
    def test_expired_certificate_is_a_blocker_even_with_valid_structure(self):
        self.certificate['valido_ate']='2020-01-01T00:00:00+00:00'
        body=self.call()[1]
        self.assertFalse(body['a1_dentro_validade'])
        self.assertEqual(body['pendencias'][0]['campo'],'a1')
    def test_unexpected_failure_does_not_disclose_data(self):
        with patch.object(integracao,'inspect',side_effect=RuntimeError('private-value')):
            status,body,_=self.call()
        self.assertEqual(status,500);self.assertNotIn('private-value',str(body))
    def test_reserved_runtime_method_does_not_recurse(self):
        with patch.object(integracao.handler,'handle_request',side_effect=AssertionError(),create=True):
            self.assertEqual(self.call(method='GET')[0],200)

    def test_preparation_only_reads_and_does_not_expose_draft_or_certificate(self):
        status,body,_=self.call(method='GET')
        self.assertEqual(status,200)
        self.assertFalse(body['numeracao']['numeracao_pronta'])
        self.assertFalse(body['numeracao']['numeracao_reservada'])
        self.assertTrue(body['possui_rascunho'])
        self.assertNotIn('descricao',json.dumps(body))
        self.assertNotIn('dados_fiscais',json.dumps(body))
        self.assertEqual(len(self.calls),2)
        self.assertTrue(all(not args and not kwargs for _,args,kwargs in self.calls))
        self.calls.clear()
        with patch.object(integracao,'authorize',side_effect=SafeError(403,'ACESSO_RESTRITO','Administrador necessário.')):
            self.assertEqual(self.call(method='GET')[0],403)
        self.assertEqual(self.calls,[])


if __name__=='__main__':unittest.main()
