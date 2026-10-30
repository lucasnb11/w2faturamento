# Integração NFS-e · etapa de validação local

Esta alteração inicia a integração fiscal; não é um emissor concluído. Nenhuma rota desta etapa assina ou transmite DPS, consulta autorização ou cancela NFS-e. A produção fiscal permanece desabilitada.

## Comportamento

O administrador usa **Validar para integração** em um rascunho salvo. A API `/api/nfse/integracao` verifica sua identidade e seu perfil ativo, lê o rascunho no Supabase e rejeita uma versão desatualizada. Não aceita dados fiscais substitutos enviados pelo navegador. Não grava no banco nem acessa o material cifrado do A1: lê somente sua identificação e datas de validade.

A resposta separa pendências de cadastro/tributação, validade do A1 e resultado XSD. Quando os dados estão preenchidos, um XML não assinado é construído apenas em memória com `tpAmb=2`, série fictícia `0` e número fictício `1`. Esses identificadores não são reservados, expostos na resposta ou transmitidos. **Não podem ser aproveitados para emitir uma nota.**

O XSD comprova somente formato, ordem, tamanho e tipos de campos. Não comprova enquadramento tributário, permissão municipal, cadeia/revogação do A1 nem aceitação pela API nacional. As marcações de validação pelo contador não substituem as regras da API.

## Documentação oficial utilizada

- [Leiaute e XSD de homologação](https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/producao-restrita/): pacote `esquemas_prod_restrita_20261020.zip`.
- [Manual do contribuinte](https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/documentacao-atual/manual-contribuintes-emissor-publico-api-sistema-nacional-nfs-e-v1-2-out2025.pdf): recepção de DPS, consulta por chave e reconciliação por identificador de DPS.
- [Endereços oficiais das APIs](https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/apis-prod-restrita-e-producao/).
- [Notas técnicas RTC](https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/rtc/).
- [Orientações de Ananindeua](https://www.ananindeua.pa.gov.br/pagina/2655/adesao-ao-emissor-nacional).

Os XSDs oficiais foram preservados em `nfse_core/schemas/homologacao_20261020`; `manifest.json` registra URL, ambiente, data de consulta e SHA-256 de cada arquivo. Esse pacote é de homologação e não deve ser usado automaticamente em produção. Os arquivos mantêm seus avisos e licenças originais.

## Cenário inicialmente contemplado

W2 como prestadora não optante pelo Simples Nacional, conforme correção do usuário; Total Express como tomadora; prestação nacional; operação tributável com incidência do ISS em Ananindeua; regime especial nenhum; sem intermediário e sem retenções federais. Descontos e retenção de ISS pelo tomador são representados na simulação. Alíquota informada ou omitida deve ser escolhida expressamente conforme a regra municipal. Outros cenários são sinalizados como pendência, sem descarte silencioso de campos.

Para IBS/CBS, a opção informada requer CST, cClassTrib, indicador e confirmação de que o destinatário é o próprio tomador. Valores IBS/CBS da prévia não são enviados como apuração: o leiaute atribui os grupos de declaração e cálculo a campos distintos. Um destinatário diferente exige implementação específica. A opção não aplicável exige validação contábil e ausência de códigos conflitantes.

Os endereços foram separados em logradouro, número, complemento, bairro, CEP e município IBGE. O XML de referência recebido posteriormente registra o número `1819` para a W2; esse dado foi transcrito para os novos rascunhos, mantendo a confirmação do endereço pelo usuário. A competência deve representar o início real da prestação; a sugestão é primeiro dia da quinzena, com confirmação separada. Competências futuras ou fora da quinzena são recusadas.

## Pendências para a integração completa

1. Obter a orientação contábil real: código nacional/municipal e NBS, local/incidência, regime de apuração, ISS, tributos aproximados, IBS/CBS, regra de consolidação e tratamento dos CT-es existentes.
2. Confirmar número do endereço da W2 e cadastro atual da tomadora.
3. Verificar a habilitação do contribuinte e parametrização municipal na API nacional usando A1, exclusivamente no backend. A consulta à documentação Swagger da Sefin retornou HTTP 503 no ambiente de desenvolvimento em 30/10/2026; o contrato detalhado de requisição/resposta ainda precisa ser conferido.
4. Implementar reserva transacional da série/número por ambiente, trilha de auditoria, idempotência e reconciliação por DPS após respostas incertas. Um timeout não autoriza gerar outra DPS para a mesma operação.
5. Homologar o perfil de assinatura aceito e conectar o componente local ao fluxo com numeração reservada; implementar mTLS, transmissão em homologação, armazenamento privado do XML retornado e validação da correspondência entre DPS enviada e NFS-e recebida.
6. Concluir homologação real e preparar leiaute de produção aplicável à competência antes de habilitar emissão oficial.

## Validação

```sh
python3 -m pip install -r requirements.txt
python3 -m unittest discover -s tests -v
node tests/test_a1_frontend.cjs
node tests/test_integracao_frontend.cjs
```

Os testes fiscais usam dados sintéticos, que não representam instrução contábil ou autorização para emissão. Não é necessária migração SQL para esta etapa: os campos adicionais utilizam `dados_fiscais` já existente.

## Correção do cadastro fiscal informada pelo usuário

A W2 foi confirmada como não optante pelo Simples Nacional. Na simulação, `opSimpNac=1` e `regApTribSN` é omitido. Os totais aproximados usam os percentuais federais, estaduais e municipais, sem percentual do Simples. O código nacional confirmado é `26.01.01` e a NBS do recorte atualizado é `1.0502.29.00`. Rascunhos antigos com optante, código 11.05.01, NBS anterior ou percentual do Simples geram pendências; não são regravados automaticamente. Alíquota, retenções e demais dados por competência continuam sujeitos à conferência.

## Conferência do XML recebido

O XML da NFS-e 10 registra ambiente de produção, competência 16/05/2026, cobrança da segunda quinzena de maio, valor R$ 50.220,00, código 260101, NBS 105022900, W2 não optante, ISS 5% não retido e PIS/COFINS CST 06, base igual ao valor dos serviços, alíquotas/débitos zerados e tipo de retenção 0. Os totais aproximados federais, estaduais e municipais estão zerados. Esses dados descrevem essa nota histórica e não confirmam automaticamente o tratamento de outras competências.

A descrição xNBS recebida é de transporte aquaviário costeiro de cargas. A combinação da NBS com o serviço de coleta/remessa/entrega deve constar na conferência fiscal do contrato; o sistema preserva o código informado pelo usuário. Não foram copiados para o repositório o XML real, a assinatura, o certificado nem os dados bancários da nota.

A simulação agora representa separadamente PIS/COFINS de apuração própria e valores retidos. O cenário inicial exige CST 06, base igual ao valor dos serviços e alíquotas/débitos zero confirmados. Esses dados não são inferidos de campos de retenção vazios.

A assinatura encontrada é da NFS-e retornada, com referência a infNFSe; a DPS incorporada não possui assinatura. O digest SHA-256 e a assinatura RSA-SHA256 conferiram com o certificado incorporado ao XML. Essa verificação de integridade não valida cadeia ICP-Brasil, revogação ou situação atual da nota. Não se deve usar a assinatura do documento retornado como prova do padrão de assinatura exigido para o envio de DPS.

Série 70000 e número 10 foram usados pelo Emissor Web nessa nota. Eles não foram adotados como sequência do integrador. Antes de permitir emissão, deve ser conciliada a existência dessa nota histórica para impedir reemissão acidental da cobrança já faturada.

A conferência com o pacote de produção publicado em 09/02/2026 encontrou rejeição do padrão da série 70000 no validador XSD utilizado. O arquivo recebido não foi modificado para fazê-lo passar. Esse resultado reforça que a homologação e a compatibilidade de produção ainda precisam ser concluídas.

## Transporte aquaviário e componente de assinatura

O usuário confirmou que o serviço inclui transporte aquático. Os códigos 26.01.01 e 1.0502.29.00 informados continuam como referência do contrato. Essa confirmação, por si só, não distingue transporte costeiro de navegação interior nem substitui a classificação contábil.

O módulo `nfse_core/signature.py` assina e verifica DPS exclusivamente de homologação, vinculando o identificador esperado ao CNPJ da W2, município, série e número. Usa RSA-SHA256 com certificado correspondente e dentro da validade, digest SHA-256, referência local e transformações XMLDSig fixas. O perfil de canonicalização é argumento obrigatório, sem seleção implícita baseada na assinatura da NFS-e de referência. Foram implementadas canonicalização exclusiva com e sem comentários para testes; a aceitação pela Sefin ainda deve ser homologada.

Referências primárias: [XML Signature 1.1](https://www.w3.org/TR/xmldsig-core1/) e [Exclusive XML Canonicalization](https://www.w3.org/TR/xml-exc-c14n/), consultadas em 30/10/2026.

O componente rejeita produção, assinatura preexistente, referências externas, entidades/DTD, identificadores duplicados, CNPJ divergente e chave incompatível. A verificação usa o certificado esperado pelo chamador, sem confiar apenas no certificado inserido no XML. Não verifica cadeia ICP-Brasil nem revogação.

Nenhuma rota chama esse módulo nesta etapa. Não foi acessado ou decifrado o A1 real da W2. Os testes usam certificados sintéticos gerados em memória, verificam digest e assinatura com primitivas independentes e validam a DPS assinada no XSD de homologação. Os números fictícios usados nos testes não foram reservados nem transmitidos. A ligação ao A1 cadastrado depende do fluxo transacional de reserva e emissão ainda pendente.
