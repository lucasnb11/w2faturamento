# W2 Faturamento 2.9 · diagnóstico do A1 e numeração de homologação

Esta etapa permite ao administrador testar a conexão do A1 cadastrado com a Sefin Nacional de homologação. Não habilita emissão oficial nem transmissão de DPS. O teste precisa ser executado pelo administrador autenticado no endereço oficial do Faturamento.

## Testar no sistema

1. Entre como administrador em https://faturamento-jade.vercel.app.
2. Abra **Notas fiscais → Certificado digital A1**.
3. Clique **Testar conexão nacional · homologação** e aguarde até 50 segundos.
4. Confira os códigos HTTP da documentação e dos parâmetros municipais e se o contrato de recepção foi identificado.

O botão chama `POST /api/nfse/conexao` na mesma origem. O servidor valida a sessão e o perfil de administrador ativo. As APIs nacionais recebem somente consultas GET de documentação e do convênio de Ananindeua; não recebem Supabase API keys ou o token de login do usuário. Não é necessário enviar novamente o A1 nem sua senha pelo chat.

O processo de diagnóstico recebe somente o registro cifrado do A1 e a chave de decifragem por stdin. Não herda a chave secreta do Supabase. Ele decifra, verifica o material e usa descritores anônimos `memfd` para carregar certificado e chave no OpenSSL, sem gravar arquivos de credenciais em disco. Os descritores são fechados após o carregamento e o processo é encerrado ao final ou em até 40 segundos. stderr e mensagens internas não são retornadas. O navegador recebe somente campos de diagnóstico permitidos.

Os destinos são fixos: documentação de recepção na Sefin (`sefin.producaorestrita.nfse.gov.br/API/SefinNacional`) e parâmetros municipais no ADN (`adn.producaorestrita.nfse.gov.br/parametrizacao`). Não há parâmetro de URL fornecido pelo usuário, redirecionamento ou acesso a endereços de produção. Os certificados TLS dos servidores e seus hostnames são verificados. Respostas HTTP não comprovam, por si só, habilitação fiscal ou validade da cadeia ICP-Brasil do A1.

## Numeração e auditoria

`sql/nfse_homologacao.sql` foi aplicado ao Supabase em 30/10/2026. Foram criadas três tabelas exclusivas de homologação e funções com `SECURITY INVOKER`, disponíveis somente ao `service_role`. RLS está ativo e os papéis anon/authenticated não possuem acesso direto.

A reserva trava o rascunho, confere sua versão e o administrador ativo, captura um snapshot e incrementa um contador comum sob trava de linha. Repetir a mesma solicitação retorna a mesma DPS sem incrementar o contador. Outra versão do rascunho é recusada após a reserva. A mudança de estado exige correspondência com o estado esperado; um resultado incerto não pode voltar ao estado de assinatura para reenvio automático. Eventos são acrescentados à trilha de auditoria.

A série permanece **não configurada** e o próximo número permanece **1**. Nenhuma reserva de emissão ficou gravada. A série 70000 da nota do Emissor Web não foi copiada. O fluxo de assinatura/transmissão ainda não chama essas funções, e não existe endpoint público de emissão nesta versão.

O script `sql/test_nfse_homologacao.sql` foi executado com o papel service_role e ROLLBACK. Verificou série ausente, repetição idempotente, versão desatualizada, transições inválidas, comparação de estado e bloqueio de reenvio após resultado incerto. Ao final foram conferidos zero rascunhos, reservas e eventos de teste, série nula e contador 1. O teste pode avançar o identificador interno de rascunhos, cuja sequência não representa numeração fiscal.

## Validação e próximos passos

```sh
python3 -m unittest discover -s tests -v
node tests/test_integracao_frontend.cjs
node tests/test_a1_frontend.cjs
```

Os testes locais usam A1s sintéticos. O diagnóstico com o A1 real exige a ação do administrador no site. Depois dele, ainda é necessário conferir o contrato detalhado da API e o perfil de assinatura aceito, configurar uma série própria, ligar reserva/assinatura/transmissão/reconciliação, conciliar notas já emitidas e armazenar os XMLs autorizados privadamente antes de liberar emissão oficial. A confirmação de transporte aquático foi registrada; os códigos do contrato permanecem os informados pelo usuário.

## Correção 2.9.1 do processo de diagnóstico

Após o primeiro teste autenticado retornar HTTP 503, foi encontrada uma lacuna na inicialização do processo: o PYTHONPATH do worker continha somente a raiz do projeto. Agora ele preserva os caminhos de dependências já carregados em sys.path pelo runtime, sem herdar as variáveis secretas do Supabase.

Foi acrescentado um teste que reproduz a perda de uma dependência carregada por diretório do runtime e confirma o carregamento após a correção. Outro teste executa o processo real por stdin em diretório separado, decifra um A1 sintético e carrega o TLS por memfd; somente o transporte HTTP é simulado. Isso não substitui o teste com o A1 real na Vercel.

O diagnóstico agora retorna códigos fixos para falhas de inicialização, abertura do A1, preparo TLS e conexão nacional. O log contém somente o nome do evento e o código da etapa. stderr é capturado apenas para classificar falhas anteriores ao início do worker, sem retornar ou registrar o texto bruto. O erro antigo não permite determinar retrospectivamente qual dessas etapas falhou em produção. A interface encerra a mensagem de progresso ao final da tentativa.

## Correção 2.9.2 da consulta de parâmetros

O teste real da 2.9.1 conseguiu ler o Swagger da Sefin (HTTP 200) e identificar o campo de recepção. A consulta de convênio respondeu HTTP 404. O [índice oficial de APIs](https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/apis-prod-restrita-e-producao/) aponta os parâmetros municipais para o serviço de Parametrização do ADN, separado da Sefin. A implementação anterior usava o host da Sefin também para essa consulta.

A 2.9.2 lê separadamente os Swagger da Sefin e da Parametrização do ADN, com o A1 no servidor. A rota GET de convênio é obtida do Swagger do ADN, limitada a uma operação municipal inequívoca com um único parâmetro de município, preenchido com Ananindeua (1500800). Operações obsoletas, ambíguas, referências externas, URLs absolutas e parâmetros adicionais obrigatórios são recusados. Sem rota confirmada não há tentativa de consulta por um endereço adivinhado.

A interface distingue os códigos HTTP de cada documentação e da consulta municipal, informa se a rota foi confirmada e apresenta somente códigos curtos de erros da API. Descrições e respostas brutas não são devolvidas. HTTP 404 por si só não é interpretado como falta de habilitação ou ausência de convênio de Ananindeua. A nova consulta com o A1 real ainda precisa ser realizada após a publicação.
