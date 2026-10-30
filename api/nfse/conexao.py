"""Diagnóstico autenticado de leitura. Não transmite DPS."""
import json

from api.nfse.certificado import SafeError, settings, authorize
from api.nfse.integracao import handler as ValidationHandler
from nfse_core.national import diagnose_connection


class handler(ValidationHandler):
    def _prevalidate(self, writing=False):
        try:
            if not writing:
                raise SafeError(405, 'METODO_INVALIDO', 'Use o botão de teste da conexão no sistema.')
            config = settings()
            if self.headers.get('Origin') != config['origin']:
                raise SafeError(403, 'ORIGEM_INVALIDA', 'Use o endereço oficial do Faturamento.')
            authorize(config, self.headers)
            if self.headers.get('Content-Type', '').split(';')[0].strip() != 'application/json':
                raise SafeError(415, 'FORMATO_INVALIDO', 'Use o botão de teste da conexão.')
            length = self.headers.get('Content-Length', '')
            if not length.isdigit() or not 0 < int(length) <= 256:
                raise SafeError(413, 'DADOS_INVALIDOS', 'Requisição inválida.')
            try:
                body = json.loads(self.rfile.read(int(length)))
            except (ValueError, UnicodeError):
                raise SafeError(400, 'DADOS_INVALIDOS', 'Requisição inválida.') from None
            if body != {'acao': 'testar_conexao'}:
                raise SafeError(400, 'DADOS_INVALIDOS', 'Apenas o diagnóstico de leitura é permitido.')
            self._respond_json(200, diagnose_connection(config))
        except SafeError as exc:
            self._respond_json(exc.status, {'code': exc.code, 'message': exc.message})
        except Exception:
            self._respond_json(503, {'code': 'CONEXAO_INDISPONIVEL', 'message': 'Não foi possível concluir o diagnóstico. Nenhuma DPS foi enviada.'})
