from http.server import HTTPServer
import json
import threading
import unittest
from unittest.mock import patch
from urllib import request,error

from api.nfse import conexao
from api.nfse.certificado import SafeError


class ConnectionHttpTests(unittest.TestCase):
    def setUp(self):
        self.config={'origin':'https://faturamento.example'}
        self.patches=[patch.object(conexao,'settings',return_value=self.config),patch.object(conexao,'authorize',return_value='admin'),
            patch.object(conexao,'diagnose_connection',return_value={'transmitido':False,'emissao_oficial_disponivel':False})]
        for p in self.patches:p.start()
        self.server=HTTPServer(('127.0.0.1',0),conexao.handler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join()
        for p in reversed(self.patches):p.stop()
    def call(self,method='POST',body=None,origin='https://faturamento.example'):
        encoded=json.dumps({'acao':'testar_conexao'} if body is None else body).encode() if method=='POST' else None
        req=request.Request(f'http://127.0.0.1:{self.server.server_port}/api/nfse/conexao',data=encoded,method=method,headers={'Origin':origin,'Content-Type':'application/json'})
        try:
            with request.urlopen(req) as r:return r.status,json.loads(r.read())
        except error.HTTPError as e:return e.code,json.loads(e.read())
    def test_admin_action_only(self):
        self.assertEqual(self.call()[0],200)
        self.assertEqual(self.call(method='GET')[0],405)
        self.assertEqual(self.call(body={'acao':'emitir'})[0],400)
        self.assertEqual(self.call(body={'acao':'testar_conexao','url':'https://evil.example'})[0],400)
    def test_origin_and_authorization_before_a1(self):
        with patch.object(conexao,'diagnose_connection') as diagnostic:
            self.assertEqual(self.call(origin='https://evil.example')[0],403)
            with patch.object(conexao,'authorize',side_effect=SafeError(401,'LOGIN','Entre novamente.')):
                self.assertEqual(self.call()[0],401)
            diagnostic.assert_not_called()
    def test_error_messages_are_redacted(self):
        with patch.object(conexao,'diagnose_connection',side_effect=ValueError('private-material')):
            status,result=self.call()
        self.assertEqual(status,503)
        self.assertNotIn('private-material',str(result))
    def test_reserved_vercel_method(self):
        with patch.object(conexao.handler,'handle_request',side_effect=AssertionError(),create=True):
            self.assertEqual(self.call()[0],200)


if __name__=='__main__':unittest.main()
