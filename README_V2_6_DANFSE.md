# W2 Sistema de Faturamento — V2.6.0

A aba Notas fiscais prepara a prestação e apresenta um DANFSe de teste no formato nacional, com os dados da W2 Transportes e da Total Express. A referência visual é a NFS-e nº 40 da empresa I S de Santana & M J S de Oliveira, enviada pelo usuário. O prestador, a inscrição municipal, o intermediário e os valores dessa empresa não foram copiados para a W2.

## O que está implementado

- Fechamento por quinzena, referência SE00041, REM e conferência do cálculo por AWBs.
- Cadastro fiscal por rascunho: inscrição municipal e contato da W2; cadastro do tomador; data de competência; locais da prestação e incidência; códigos nacional, municipal e NBS; intermediário opcional; regime; ISS e retenções; IBS/CBS e complementos.
- Códigos 26.01.01 e 1.0702.00.00 preenchidos como sugestões do modelo recebido, pendentes de validação para a W2.
- Tributos em branco exibidos como pendentes. Não são convertidos em zero. O líquido só é calculado quando retenções e desconto incondicionado estão preenchidos e o tratamento da retenção do ISS foi definido.
- Prévia no formato do DANFSe, com impressão para PDF. Não gera número de NFS-e, DPS sequencial, chave, assinatura, protocolo ou QR Code fiscal.
- Salvamento dos dados fiscais no Supabase, edição de rascunhos e cópia manual do cadastro do último rascunho, exigindo nova conferência das confirmações.

## Aplicação desta entrega

O projeto Supabase `recebimento-cargas` (`bdmogkdnhvstcgfuxznz`) já recebeu a coluna `dados_fiscais` e a restrição JSON; a proteção RLS permanece ativa e o acesso anônimo à tabela foi revogado. Foram conferidos o esquema e o armazenamento em teste transacional com rollback. Não é preciso executar SQL novamente nesse projeto.

Publique o conteúdo da pasta `billing-integration` no mesmo site do Faturamento, substituindo os arquivos existentes. Depois recarregue com Ctrl+F5 e abra Notas fiscais. Esta entrega não foi publicada no Vercel.

`supabase_schema_v2_6_danfse.sql` está incluído para configurar outro ambiente, após a instalação dos perfis de faturamento da V2.2.1. Não altera tabelas do CheckLog.

## O que falta para emissão oficial

1. Inscrição municipal, endereço e cadastro fiscal confirmado da W2.
2. Confirmação contábil do regime na competência, código do serviço/NBS, local da prestação, incidência e retenção do ISS, tributos federais e IBS/CBS.
3. Validação da emissão consolidada por quinzena. A Prefeitura de Ananindeua publicou orientação de adaptação da emissão consolidada para emissão por ato/operação a partir de outubro de 2026. A referência de agosto não estabelece autorização para consolidar períodos posteriores.
4. Configuração segura do certificado e credenciamento da W2 na integração de emissão nacional. Certificados e senhas devem permanecer no serviço de emissão, fora dos arquivos públicos do site.
5. Backend de emissão: numeração e assinatura da DPS, validação do XML nos XSD atuais, envio à API, tratamento de rejeições, reconciliação/idempotência, consulta de autorização, armazenamento do XML autorizado e geração do DANFSe a partir dele. Nada dessa transmissão é simulado como uma emissão oficial nesta versão.

## Fontes consultadas em 08/10/2026

- Prefeitura de Ananindeua: https://www.ananindeua.pa.gov.br/pagina/2655/adesao-ao-emissor-nacional
- Documentação nacional atual: https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/documentacao-atual
- Manual API de contribuintes: https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/documentacao-atual/manual-contribuintes-emissor-publico-api-sistema-nacional-nfs-e-v1-2-out2025.pdf/view

## Verificação

Sintaxe JavaScript; testes do preenchimento e salvamento em DOM simulado; cálculo de valores conhecidos e pendentes; escape de texto da prévia; SQL transacional de armazenamento JSON e restrição de tipo; conferência visual da exportação PDF em A4. A interface não foi testada em um navegador real nesta sessão, pois o ambiente não disponibilizou um navegador local para o projeto. Deve ser conferida no site após a publicação.
