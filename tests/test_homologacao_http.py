from http.server import HTTPServer
import json
import threading
import unittest
from unittest.mock import patch
from urllib import request,error

from api.nfse import homologacao as h
from api.nfse.certificado import SafeError


class HomologationHttpTests(unittest.TestCase):
    def setUp(self):
        self.patches=[patch.object(h,'settings',return_value={'origin':'https://faturamento.example'}),
            patch.object(h,'authorize',return_value='admin'),patch.object(h,'operate',return_value={'ambiente':'homologacao','emissao_oficial_disponivel':False})]
        for p in self.patches:p.start()
        self.server=HTTPServer(('127.0.0.1',0),h.handler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join()
        for p in reversed(self.patches):p.stop()
    def call(self,body=None,origin='https://faturamento.example',method='POST'):
        data=json.dumps(body or {'acao':'status','rascunho_id':2,'versao':'current'}).encode() if method=='POST' else None
        r=request.Request(f'http://127.0.0.1:{self.server.server_port}/api/nfse/homologacao',data=data,method=method,headers={'Origin':origin,'Content-Type':'application/json'})
        try:
            with request.urlopen(r) as response:return response.status,json.loads(response.read())
        except error.HTTPError as e:return e.code,json.loads(e.read())
    def test_admin_origin_and_authentication_before_actions(self):
        with patch.object(h,'operate') as operate:
            self.assertEqual(self.call(origin='https://evil.example')[0],403)
            with patch.object(h,'authorize',side_effect=SafeError(403,'ADMIN','Administrador necessário.')):
                self.assertEqual(self.call()[0],403)
            self.assertEqual(self.call(method='GET')[0],405)
            operate.assert_not_called()
    def test_cannot_supply_xml_url_cnpj_or_production(self):
        for extra in [{'xml':'private'},{'url':'https://evil.example'},{'ambiente':'producao'},{'cnpj':'other'}]:
            self.assertEqual(self.call({'acao':'preparar','rascunho_id':2,'versao':'v',**extra})[0],400)
        for bad in [True,0,'2']:
            self.assertEqual(self.call({'acao':'preparar','rascunho_id':bad,'versao':'v'})[0],400)
    def test_transmission_requires_separate_explicit_confirmation(self):
        body={'acao':'transmitir','rascunho_id':2,'versao':'current'}
        self.assertEqual(self.call(body)[0],400)
        self.assertEqual(self.call({**body,'confirmacao':'ENVIAR_PRODUCAO'})[0],400)
        self.assertEqual(self.call({**body,'confirmacao':'ENVIAR_SOMENTE_HOMOLOGACAO'})[0],200)
    def test_unexpected_errors_do_not_disclose_xml_or_private_material(self):
        with patch.object(h,'operate',side_effect=RuntimeError('private-material')):
            status,body=self.call()
        self.assertEqual(status,503);self.assertNotIn('private-material',json.dumps(body))
    def test_reserved_vercel_method_is_not_used_by_application(self):
        with patch.object(h.handler,'handle_request',side_effect=AssertionError(),create=True):
            self.assertEqual(self.call()[0],200)


if __name__=='__main__':unittest.main()
