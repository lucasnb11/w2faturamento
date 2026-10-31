"""Ações explícitas, administrativas e restritas ao ambiente de homologação."""
import json

from api.nfse.certificado import SafeError, settings, authorize
from api.nfse.integracao import handler as JsonHandler
from nfse_core.emission import operate


class handler(JsonHandler):
    def _prevalidate(self, writing=False):
        try:
            if not writing:
                raise SafeError(405, 'METODO_INVALIDO', 'Use as ações de homologação do rascunho.')
            config = settings()
            if self.headers.get('Origin') != config['origin']:
                raise SafeError(403, 'ORIGEM_INVALIDA', 'Use o endereço oficial do Faturamento.')
            author = authorize(config, self.headers)
            if self.headers.get('Content-Type', '').split(';')[0].strip() != 'application/json':
                raise SafeError(415, 'FORMATO_INVALIDO', 'Use o formulário do sistema.')
            length = self.headers.get('Content-Length', '')
            if not length.isdigit() or not 0 < int(length) <= 2048:
                raise SafeError(413, 'DADOS_INVALIDOS', 'Requisição inválida.')
            try:
                body = json.loads(self.rfile.read(int(length)))
            except Exception:
                raise SafeError(400, 'DADOS_INVALIDOS', 'Requisição inválida.') from None
            actions = {'status', 'preparar', 'transmitir', 'conciliar', 'baixar_xml', 'nova_tentativa'}
            if not isinstance(body, dict) or not isinstance(body.get('acao'), str) or body['acao'] not in actions:
                raise SafeError(400, 'ACAO_INVALIDA', 'Ação não permitida.')
            confirmations = {'transmitir': 'ENVIAR_SOMENTE_HOMOLOGACAO', 'nova_tentativa': 'NOVA_DPS_SOMENTE_HOMOLOGACAO'}
            expected = {'acao', 'rascunho_id', 'versao'} | ({'confirmacao'} if body['acao'] in confirmations else set())
            if (set(body) != expected or type(body.get('rascunho_id')) is not int or body['rascunho_id'] < 1
                or not isinstance(body.get('versao'), str) or not 1 <= len(body['versao']) <= 64
                or body['acao'] in confirmations and body.get('confirmacao') != confirmations[body['acao']]):
                raise SafeError(400, 'DADOS_INVALIDOS', 'Confirme a ação sobre o rascunho salvo.')
            self._respond_json(200, operate(config, author, body))
        except SafeError as exc:
            self._respond_json(exc.status, {'code': exc.code, 'message': exc.message})
        except Exception:
            self._respond_json(503, {'code': 'HOMOLOGACAO_INTERROMPIDA', 'message': 'Consulte a situação da DPS antes de continuar. Nenhum reenvio automático será realizado.'})
