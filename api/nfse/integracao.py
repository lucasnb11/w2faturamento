"""Pré-validação administrativa da integração. Não existe rota de transmissão."""
import json
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler
from urllib import parse

from api.nfse.certificado import SafeError, settings, authorize, api_json, public_status
from nfse_core.preflight import inspect
from nfse_core.preparation import numbering_status


class handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def _respond_json(self, status, body):
        encoded = json.dumps(body, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(encoded)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Cross-Origin-Resource-Policy', 'same-origin')
        self.end_headers()
        self.wfile.write(encoded)

    def _prevalidate(self, writing=False):
        try:
            config = settings()
            origin = self.headers.get('Origin')
            if (writing and origin != config['origin']) or (origin and origin != config['origin']):
                raise SafeError(403, 'ORIGEM_INVALIDA', 'Use o endereço oficial do Faturamento.')
            authorize(config, self.headers)
            cert = public_status(config)
            valid = False
            if cert:
                try:
                    now = datetime.now(timezone.utc)
                    valid = datetime.fromisoformat(cert['valido_desde'].replace('Z', '+00:00')) <= now < datetime.fromisoformat(cert['valido_ate'].replace('Z', '+00:00'))
                except (ValueError, TypeError, KeyError):
                    pass
            if not writing:
                numbering = numbering_status(api_json(config, '/rest/v1/nfse_homologacao_config?cnpj=eq.46167015000140&select=cnpj,serie,proximo_numero&limit=1'))
                drafts = api_json(config, '/rest/v1/nfse_rascunhos?emitente_cnpj=eq.46167015000140&tomador_cnpj=eq.73939449000193&select=id&limit=1')
                return self._respond_json(200, {'ambiente': 'homologacao', 'etapa': 'validacao_local',
                    'a1_cadastrado': bool(cert), 'a1_dentro_validade': valid,
                    'numeracao': numbering, 'possui_rascunho': isinstance(drafts, list) and bool(drafts),
                    'emissao_oficial_disponivel': False, 'transmissao_disponivel': False})
            if self.headers.get('Content-Type', '').split(';')[0].strip() != 'application/json':
                raise SafeError(415, 'FORMATO_INVALIDO', 'Use o formulário do sistema.')
            length = self.headers.get('Content-Length', '')
            if not length.isdigit() or not 0 < int(length) <= 2048:
                raise SafeError(413, 'REQUISICAO_INVALIDA', 'Requisição inválida.')
            try:
                body = json.loads(self.rfile.read(int(length)))
            except (ValueError, UnicodeError):
                raise SafeError(400, 'DADOS_INVALIDOS', 'Requisição inválida.') from None
            if not isinstance(body, dict) or set(body) != {'rascunho_id', 'versao'}:
                raise SafeError(400, 'DADOS_INVALIDOS', 'Selecione um rascunho salvo.')
            draft_id = body['rascunho_id']
            if isinstance(draft_id, bool) or not isinstance(draft_id, int) or draft_id <= 0 or not isinstance(body['versao'], str):
                raise SafeError(400, 'DADOS_INVALIDOS', 'Selecione um rascunho salvo.')
            query = parse.urlencode({'id': 'eq.' + str(draft_id), 'select': '*', 'limit': '1'})
            rows = api_json(config, '/rest/v1/nfse_rascunhos?' + query)
            if not isinstance(rows, list) or not rows:
                raise SafeError(404, 'RASCUNHO_NAO_ENCONTRADO', 'Atualize a lista de rascunhos.')
            row = rows[0]
            if row.get('updated_at') != body['versao']:
                raise SafeError(409, 'RASCUNHO_ALTERADO', 'O rascunho mudou. Atualize a lista antes de validar.')
            result = inspect(row)
            result['rascunho_id'] = draft_id
            result['versao'] = row['updated_at']
            result['a1_dentro_validade'] = valid
            result['transmissao_disponivel'] = False
            if not valid:
                result['pendencias'].insert(0, {'campo': 'a1', 'mensagem': 'Cadastre um A1 da W2 dentro da validade.'})
            result['proximas_etapas'] = ['Conferir enquadramento e regras de negócio municipais/nacionais.',
                'Implementar reserva atômica de numeração, assinatura e transmissão com reconciliação por DPS.',
                'Concluir homologação antes de habilitar produção.']
            self._respond_json(200, result)
        except SafeError as exc:
            self._respond_json(exc.status, {'code': exc.code, 'message': exc.message})
        except Exception:
            self._respond_json(500, {'code': 'VALIDACAO_INDISPONIVEL', 'message': 'Não foi possível concluir a validação local. Nenhuma DPS foi transmitida.'})

    def do_GET(self):
        self._prevalidate()

    def do_POST(self):
        self._prevalidate(writing=True)

    def do_OPTIONS(self):
        self._respond_json(405, {'code': 'METODO_INVALIDO', 'message': 'Método não permitido.'})

    do_DELETE = do_PUT = do_PATCH = do_HEAD = do_OPTIONS
