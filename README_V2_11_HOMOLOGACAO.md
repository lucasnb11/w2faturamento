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
