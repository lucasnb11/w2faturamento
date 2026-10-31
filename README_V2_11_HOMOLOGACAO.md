# W2 Faturamento 2.11 · fluxo de homologação

Esta versão conecta reserva, montagem, assinatura, envio, consulta e guarda do XML no ambiente de testes. Não implementa emissão de produção, cancelamento, substituição ou reenvio de uma DPS rejeitada. O DANFSe de teste continua sendo uma prévia; não é apresentado como documento autorizado.

## Antes de publicar

1. Aplicar `sql/nfse_v2_11_homologacao.sql` e depois `sql/nfse_v2_11_auditoria_privada.sql` no projeto já usado pelo Faturamento. Elas restringem as séries a 1–49999, adicionam colunas de XML cifrado/funções privadas e removem privilégios padrão excessivos do papel da aplicação. Não alteram o rascunho, as confirmações fiscais ou o A1. Se houver série fora da faixa, a migração falha sem corrigir dados silenciosamente.
2. Executar `sql/test_nfse_v2_11_homologacao.sql` em transação com ROLLBACK e conferir estado/configuração reais antes e depois. O teste não chama a API nacional nem o A1. A sequência interna do ID do rascunho pode avançar; isso não é numeração fiscal. Não repetir testes que já passaram sem uma nova alteração ou falha.
3. Conferir RLS/grants e publicar o commit aprovado. A função `api/nfse/homologacao.py` usa até 120 segundos. Não adicionar ou substituir chaves já existentes.

## Operação pelo administrador

No rascunho salvo, use **Homologação**:

- **Preparar DPS de homologação** valida os dados fiscais e o XSD antes de reservar número. Com pendências, não reserva nem abre o A1. Com dados válidos, reserva atomicamente o snapshot e assina no processo isolado, guardando o XML cifrado. Repetir a preparação não substitui uma assinatura gravada.
- **Transmitir somente em homologação** exige confirmação separada. O servidor confere a versão e disputa o estado em transação: apenas uma chamada pode iniciar o envio. Confere o contrato Swagger, consulta a existência da DPS e faz no máximo um POST para a Sefin de testes.
- **Consultar retorno** concilia por GET, sem repetir o POST. Um processo interrompido em `enviando` só pode ser conciliado após três minutos, para evitar disputar com a execução original.
- **Baixar XML de homologação** só aparece habilitado depois de autorização conferida. A abertura do arquivo é uma ação autenticada do administrador; não há link público de XML.

Nenhuma operação aceita XML, URL, CNPJ, ambiente ou valores fiscais enviados pelo navegador. O servidor obtém o rascunho e a reserva no banco; a autorização exige usuário existente e administrador ativo. Uma edição posterior bloqueia nova preparação/envio da reserva antiga, mas permite sua conciliação com o snapshot original.

## Assinatura em teste

O manual integrado oficial 1.00.02 de setembro/2022 descreve RSA-SHA1, digest SHA-1 e C14N inclusiva. O perfil foi implementado explicitamente para interoperabilidade em homologação; não se presume que o manual antigo comprove a aceitação atual. A recepção real ainda precisa validar esse perfil. O identificador e o conteúdo seguem o XSD de homologação 1.01 de 20/10/2026, e não o prefixo antigo do exemplo de 2022.

O componente anterior RSA-SHA256 permanece testado. Não há troca automática de algoritmo nem novo envio após rejeição. O teste de desafio aleatório do A1 continua sendo independente da assinatura XMLDSig.

Fonte: https://www.gov.br/nfse/pt-br/biblioteca/manuais-e-tutoriais/manual-integrado-nfse

## Retorno, proteção e limites

- Destino fixo de homologação, mTLS com verificação do servidor, sem redirecionamentos. Nenhum parâmetro habilita produção.
- DPS e NFS-e cifradas com AES-GCM e AAD vinculada ao tipo de documento e ao ID da DPS. O A1, a senha e a chave privada não chegam ao navegador ou aos logs. A chave de proteção existente também passa a proteger os XMLs; não pode ser trocada sem migração planejada.
- Respostas são limitadas; gzip/base64, entidades, DTD, IDs repetidos, ambiente de produção e referência externa são rejeitados. Antes de marcar `autorizada`, a resposta deve corresponder ao ID, chave, CNPJ, ambiente e conteúdo integral da DPS; deve passar pelo XSD e pela verificação criptográfica de integridade da assinatura da NFS-e.
- A procedência da resposta é assegurada pelo HTTPS autenticado da Sefin. A verificação local da assinatura da NFS-e não valida a cadeia ICP-Brasil nem consulta revogação de forma independente.
- Timeout, erro de contrato, retorno divergente ou falha após o início do envio ficam pendentes de consulta, sem reenvio automático. Apenas rejeições inequívocas E0714–E0718 são marcadas como rejeitadas. Mesmo após rejeição, é possível consultar e recuperar uma autorização compatível, caso exista.
- Auditoria de transições é append-only para o papel usado pela aplicação. As tabelas e as funções novas não são acessíveis por `anon` ou `authenticated`.

## Validação desta entrega

83 testes Python e três conjuntos JavaScript aprovados. Incluem processo real com A1 sintético, assinatura após serialização, XSD real da NFS-e sintética, referência/digest/assinatura, vínculo do envelope, compactação malformada/bomba gzip, resultado de produção ou de outra DPS, um único POST, timeout, edição posterior do rascunho, confirmação separada e ausência de HTML dinâmico nas mensagens.

Os SQLs inicial e novo e os dois scripts transacionais passaram em PostgreSQL isolado via PGlite 0.5.13. Ao final dos testes: zero rascunhos, reservas e eventos sintéticos, configuração original restaurada. Isso não substitui a verificação da migração no Supabase antes da publicação.

Na verificação do Supabase, o teste identificou UPDATE/DELETE no histórico concedidos ao `service_role` pelos privilégios padrão do projeto. A migração adicional de auditoria revoga todos os grants desse papel nas três tabelas do fluxo e repõe somente os necessários, incluindo SELECT/INSERT no histórico. O acesso anônimo/autenticado às tabelas e funções já estava bloqueado. O teste inicial foi revertido integralmente; não consumiu número de DPS. Após a correção, o script transacional passou no Supabase. A conferência final preservou um rascunho real, zero reservas/eventos, série 1 e próximo número 1. RLS ativo, tabelas/funções inacessíveis a anon/authenticated e histórico sem UPDATE/DELETE/TRUNCATE para service_role.

Nenhum teste desta entrega abriu o A1 real, transmitiu DPS da W2 ou confirmou seu enquadramento fiscal. O rascunho 1QMAIO26 ainda contém campos fiscais pendentes. A primeira recepção real deve ser iniciada pelo administrador somente depois de conferir esses dados.

## Cenário documental 2.11.2

O usuário pode optar por reproduzir as notas anteriores exclusivamente para homologação, identificando a fonte e confirmando o uso de testes. Nesse cenário, as cinco confirmações cadastrais/contábeis e a orientação profissional permanecem como estavam: não são preenchidas nem interpretadas como aprovadas. A validação usa os dados do documento como cenário de teste, preservando as verificações de CNPJ, competência, endereço, valores, tributos suportados, coerência e XSD.

Para este modelo, pAliq e IBSCBS não constam na DPS de referência. As novas opções registram a ausência documental e omitem esses elementos somente no XML de homologação. Não representam regra municipal ou declaração de não aplicabilidade. Essas opções são rejeitadas fora do modo documental; o modo documental não aceita as opções que afirmam validação contábil de IBS/CBS ou regra municipal de alíquota.

O modo e o aviso acompanham a validação e as operações; em uma DPS já reservada, o status usa o snapshot imutável. Não há parâmetro que habilite produção. As ações de reservar, assinar e transmitir continuam separadas, administrativas, com confirmação específica para envio. Publicar o código não reserva números e não envia a DPS. Não há migração de schema nesta versão.

Validação: 90 testes Python, quatro conjuntos JavaScript e fluxo em Chromium com persistência simulada. Incluem modo desativado/incompleto, origem ausente, ausência documental versus não aplicabilidade, confirmações preservadas, coerência fiscal obrigatória, aviso com snapshot anterior, edição, reaproveitamento e prévia. A validação local do rascunho histórico 1QMAIO26 com o perfil de referência passou no XSD; nenhuma reserva, assinatura ou transmissão real foi executada por essa validação.

## Data/hora e E0008 (2.11.3)

O Anexo I de homologação 20/10/2026 define E0008 para dhEmi posterior a dhProc. O registro da tentativa retornou HTTP 400/E0008, sem autorização conferida. A DPS construída pela versão anterior representava dhEmi em UTC (+00:00). Isso não comprova isoladamente erro de fuso, relógio ou da API.

A construção de novas DPS passa a representar o mesmo instante do relógio do servidor com offset explícito -03:00. A validação de competência usa o mesmo dia local; datetimes sem fuso são rejeitados. Não há retroação artificial de horas, alteração da competência, reconstrução de XML já assinado ou reenvio automático. A tela explica E0008 e orienta a conciliação por GET. A política de estados da tentativa existente permanece intacta.

Validação: 91 testes Python e teste JavaScript da homologação. Incluem mudança de dia 02:37 UTC para 23:37 -03:00, igualdade do instante, competência preservada, XSD, recusa de datetime sem fuso e E0008 exibido com transmissão bloqueada. A aceitação dessa representação pela API precisa de nova recepção controlada após conciliar a tentativa anterior.

Fonte: https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/producao-restrita/anexo_i-sefin_adn-dps_nfse-snnfse_prodrest-v1-01-20261020.xlsx

## Nova tentativa controlada (2.11.4)

A reserva original era única por rascunho: um retorno 404 deixava o fluxo pendente, sem caminho para testar a correção de data/hora. A migração substitui essa unicidade por (rascunho, tentativa) e uma ligação única à tentativa anterior. O botão administrativo de nova tentativa exige confirmação própria. A API valida o rascunho atual e consulta o identificador anterior por GET, com contrato e mTLS, imediatamente antes da reserva. Somente HTTP 404 permite continuar; qualquer outro retorno ou falha bloqueia nova numeração.

A transação verifica administrador ativo, versão atual do rascunho, versão da tentativa anterior, estado pendente, último retorno 404, XML assinado existente, ausência de documento autorizado e pelo menos três minutos desde o evento de envio. O bloqueio do rascunho, a checagem da última tentativa e as unicidades impedem duas reservas para a mesma origem. Cria uma linha em estado reservada, novo número e novo identificador; não altera a linha, XML, hash ou snapshot da tentativa anterior. A reserva normal permanece idempotente e passa a selecionar a tentativa mais recente.

HTTP 404 descreve o resultado da consulta naquele instante, não uma garantia geral de ausência definitiva. A funcionalidade é exclusivamente de homologação e exige uma ação explícita; não habilita produção e não repete o POST antigo. Preparar/assinar e transmitir a nova DPS continuam sendo ações separadas. Se a consulta adicional não retornar 404, é necessário conciliar a tentativa anterior.

O histórico anterior registrava transições, mas não preservava HTTP/códigos de cada resposta: por isso a consulta 404 substituiu E0008 no resumo. A partir desta migração, cada retorno grava esses metadados em eventos privados append-only. Respostas antigas não são reconstruídas nem atribuídas retrospectivamente à API.

Validação: 99 testes Python, quatro conjuntos JavaScript e testes SQL com rollback em PostgreSQL isolado/PGlite. Cobrem confirmação independente, GET adicional sem POST, bloqueio de resultado diferente de 404, estado recente ou autorizado, validação fiscal, versão desatualizada, dupla reserva, integridade completa da linha antiga, idempotência e privilégios privados. A migração não reserva números; nenhuma DPS real foi criada, assinada ou transmitida nos testes desta entrega.

## Interoperabilidade da assinatura (2.11.5)

A tentativa 2 retornou HTTP 400/E0714 (arquivo com erro na assinatura). Com a mesma construção XML e chave sintética, o verificador JSR-105 do Java rejeitou tanto o digest da referência quanto SignedInfo produzidos pela rotina antiga. A canonicalização direta de descendentes anexados, na biblioteca fixada, emitia xmlns vazio em partes do subconjunto. A conferência local anterior usava a mesma operação e não detectava a divergência.

A rotina agora serializa o subconjunto com namespaces em escopo, sem tail, e o analisa isoladamente antes de aplicar o mesmo C14N. Para C14N inclusivo, preserva atributos xml:* herdados com precedência do ancestral mais próximo. A cópia serve apenas ao digest e à assinatura; não altera o documento original nem seus dados. Não muda algoritmos, certificado, cadeia, perfil fiscal ou o XML das tentativas anteriores. O helper também é usado para conferir a integridade de respostas NFS-e.

O oráculo Java independente confere digest e RSA, bloqueia referências externas e usa somente certificados sintéticos. Passa nos perfis inclusivo/SHA1, inclusivo/SHA256 e exclusivo/SHA256 com/sem comentários em documentos sem comentários. Também cobre namespaces herdados, xml:lang e alteração de valores. O teste da rotina antiga continua reproduzindo a rejeição no ambiente fixado. Java 17 é usado somente na verificação de desenvolvimento; os testes são pulados quando o compilador Java não está disponível. Não é dependência do aplicativo.

A nova tentativa pode ser reservada após E0714 isolado/HTTP 400 ou 422, mediante confirmação e um novo GET 404 com mTLS. E0715, outros códigos, códigos mistos, HTTP ausente e autorização prévia não liberam esse caminho. A função privada mantém bloqueios, versões, intervalo de três minutos e preservação da linha/XML anteriores. Não há reenvio automático. Uma consulta GET a tentativa antiga não depende de revalidar a assinatura rejeitada; continua exigindo integridade AES-GCM do XML armazenado, e qualquer autorização retornada é confrontada com o documento esperado. Todo POST continua exigindo assinatura válida antes de criar o transporte.

Validação: 108 testes Python (incluindo o oráculo Java), quatro conjuntos JavaScript e scripts SQL com rollback em PostgreSQL isolado/PGlite. A integridade da assinatura externa da NFS-e fornecida anteriormente também passou; isso não valida sua cadeia de certificados. Nenhuma DPS real foi reservada, assinada novamente ou transmitida por estes testes. A aceitação do XML corrigido pela API ainda depende de uma recepção controlada.

Fontes: Anexo I de homologação 20/10/2026 (E0714) e Canonical XML 1.0, https://www.w3.org/TR/2001/REC-xml-c14n-20010315 .

## Diagnóstico de ISS (2.11.6)

O botão de conexão passa a apresentar um resumo limitado dos parâmetros públicos de convênio municipal e metadados das rotas GET de alíquotas declaradas pelo Swagger do ADN. Não retorna documentos, A1, dados de contribuinte ou texto livre da resposta. Mantém os destinos de homologação, mTLS e somente leitura. A tela explica E0429 como código fiscal, distinto de HTTP 429.

Esta versão de diagnóstico não corrige nem presume a causa da rejeição E0429 da tentativa 3. Os parâmetros de município e competência ainda precisam ser confrontados com o cenário documental. Não altera tributos, rascunhos, reservas ou XMLs históricos e não transmite automaticamente.

A versão 2.11.7 acrescenta GET ao histórico de alíquotas do serviço 260101 no município 1500800, por rota observada no Swagger do ADN. A resposta é resumida e não altera dados, reserva ou transmissão. Lista JSON também é aceita somente no leitor de parâmetros municipais.

A versão 2.11.8 apresenta a mensagem de erro da consulta de parâmetros com limite de tamanho e remoção de identificadores; não registra respostas brutas ou dados do A1.

A versão 2.11.9 corrige o código usado somente na consulta GET do histórico: 26.01.01.000 (serviço-base do cenário sem cTribMun). A resposta real anterior exigiu nove dígitos. O Guia do Painel Municipal v1.2, seção 3.5.3, descreve os seis dígitos nacionais separados por pontos e complemento 000 para serviço sem desdobramento. A consulta não declara que o município não possui especializações e não altera XML ou tributação. Fonte: https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/documentacao-atual/guia-do-painel-administrativo-municipal-nfs-e-v1-2-out2025.pdf

Conferência real do diagnóstico: HTTP 200 no histórico do serviço-base 26.01.01.000 em Ananindeua; alíquota 5 com vigência 24/09/2025–25/01/2026 e alíquota null desde 26/01/2026, sem data final. Isso não comprova isoladamente a causa completa de E0429 e não autoriza substituir a alíquota da API. A incidência com acentos é preservada no resumo; null não é convertido em 0. O cenário fiscal e as três DPS continuam preservados.

## Omissão do grupo de descontos sem valores (2.11.10)

O XML autorizado de referência (NFS-e 10, competência 16/05/2026, serviço 260101, sem cTribMun, ISS aplicado de 5%) não contém vDescCondIncond. A construção anterior adicionava esse grupo com ambos os valores 0.00. A nova construção omite o grupo opcional quando ambos são zero e preserva integralmente descontos não nulos. O XSD e a validação dos dados continuam obrigatórios. Não altera o regime, alíquota, base, competência, valores, confirmações fiscais, assinaturas ou documentos anteriores.

A influência dessa diferença em E0429 é uma hipótese a verificar por uma única recepção controlada. O histórico municipal de homologação continua divergente da referência de produção; a alteração não declara resolvida essa divergência e não habilita emissão em produção. O PDF 1QMAI26 já identifica NFS-e 7 gerada para 01/05/2026 e R$ 15.169,50; o rascunho deste período continua exclusivamente de teste para evitar duplicidade.
