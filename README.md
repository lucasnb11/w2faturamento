# W2 Faturamento · versão 2.11.10

Sistema de faturamento e acompanhamento de entregas da W2 Transportes, com fechamentos por quinzena, importação de CAFs/AWBs, pagamentos por cidade e acesso por perfil no Supabase.

Publicado em https://faturamento-jade.vercel.app.

Inclui [validação local e assinatura da DPS](README_V2_8_INTEGRACAO.md) e [diagnóstico autenticado do A1 e controle de numeração de homologação](README_V2_9_CONEXAO.md). A emissão em produção continua desabilitada. O fluxo de teste está documentado em [homologação 2.11](README_V2_11_HOMOLOGACAO.md).

Consulte também a [preparação da DPS de homologação](README_V2_10_PREPARACAO.md).

A versão 2.11.0 reorganiza a prévia do DANFSe conforme o modelo recebido: cabeçalho nacional, quatro colunas, blocos tributários e rodapé de ciência em A4. Mantém aviso de teste, campos pendentes e identificação fiscal sem número, chave ou QR de autorização.

## Notas fiscais

A versão 2.7.1 inclui rascunhos, prévia de DANFSe sem validade fiscal e cadastro protegido do certificado A1 por administrador. A emissão oficial ainda depende de integração fiscal, validação contábil e homologação.

Consulte [cadastro do A1 e configuração do servidor](README_V2_7_CERTIFICADO_A1.md) e [prévia do DANFSe](README_V2_6_DANFSE.md).

## Publicação e configuração

O projeto Vercel utiliza a raiz deste repositório, framework Other, arquivos estáticos e a função Python `api/nfse/certificado.py`. Os requisitos Python estão em `requirements.txt`. As variáveis privadas devem ser cadastradas somente na Vercel; `.env.example` contém apenas exemplos.

Certificados, senhas e chaves secretas não pertencem ao repositório. Não substitua a chave de cifragem de um ambiente que já armazena A1 sem planejar o recadastro do certificado.

## Testes

```sh
python3 -m pip install -r requirements.txt
python3 -m unittest discover -s tests -v
node tests/test_a1_frontend.cjs
node tests/test_nfse_perfil.cjs
```

Os scripts SQL versionados documentam a estrutura. Publicar o código não executa migrações automaticamente.

Logomarca da prévia: arquivo público disponibilizado no [Portal Nacional da NFS-e](https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/logos-da-nfs-e). A interface referencia a imagem oficial por HTTPS; não publica imagens extraídas de documentos anexados pelo usuário.

A versão 2.11.1 corrige o reaproveitamento do cadastro fiscal: bases integrais e ISS são recalculados em centavos para o novo valor. Valores fixos não zerados, bases reduzidas e descontos diferentes de zero exigem revisão, em vez de serem copiados. A origem documental é preservada ao editar e salvar. O reaproveitamento não confirma a validação contábil nem a competência e não altera o fluxo de transmissão.

A versão 2.11.2 acrescenta um cenário documental explicitamente selecionado para homologação. Com fonte identificada e uso exclusivo de testes, a DPS pode reproduzir a ausência de pAliq e IBSCBS da nota de referência sem marcar confirmações contábeis. As demais verificações de dados e o XSD continuam obrigatórios. O servidor identifica o modo em todas as etapas; não existe emissão em produção nesta aplicação.

A versão 2.11.3 representa dhEmi com o offset explícito -03:00, preservando o instante do relógio do servidor, e explica E0008 na tela. Não subtrai horas do instante real nem altera competência, XML já assinado, reserva, histórico ou política de reenvio. A necessidade dessa representação na API ainda exige recepção real; E0008 informa data/hora posterior ao processamento, sem comprovar isoladamente a causa no relógio ou no fuso.

A versão 2.11.4 permite reservar explicitamente outra tentativa de homologação após consulta 404, confirmação do administrador, nova consulta GET 404 no servidor e intervalo mínimo de três minutos do envio anterior. Cria outra linha e outro identificador, preservando integralmente a tentativa antiga. Não assina nem transmite nessa ação. Aplicar antes a migração privada `sql/nfse_v2_11_4_tentativas.sql`.

A versão 2.11.5 corrige a canonicalização de subconjuntos XML usados na assinatura: normaliza o contexto de namespaces em uma cópia antes do C14N e preserva atributos xml:* herdados no perfil inclusivo. O XML transmitido não é reescrito depois de assinado. Mantém algoritmos e perfis existentes; não altera certificados, tributos ou documentos anteriores. Inclui testes independentes com Java 17 (somente QA, sem dependência em produção).

A retomada explícita também aceita rejeição isolada E0714/HTTP 400 ou 422, sempre após novo GET 404 no servidor e com os mesmos controles transacionais da versão anterior. Aplicar `sql/nfse_v2_11_5_assinatura.sql` antes de publicar. Não reserva nem envia automaticamente.

A versão 2.11.6 amplia o diagnóstico de leitura do convênio municipal e explica E0429 na interface. Não altera dados fiscais nem transmite DPS automaticamente.

A versão 2.11.7 consulta também o histórico de alíquotas do serviço 26.01.01 em Ananindeua, somente quando a rota GET consta no Swagger oficial. Não altera o cenário fiscal.

A versão 2.11.8 exibe a mensagem limitada da consulta municipal, removendo identificadores e tratando-a como texto. Não altera dados fiscais.

A versão 2.11.9 corrige a representação do código de consulta do histórico para 26.01.01.000. O complemento 000 identifica a consulta do serviço-base, sem inserir cTribMun no XML nem presumir ausência de especialização municipal.

A versão 2.11.10 omite o grupo opcional de descontos quando ambos os valores são zero, reproduzindo a estrutura da DPS autorizada de referência. Descontos não nulos continuam preservados. Não altera valores, tributos, ambiente ou documentos anteriores. Não presume resolução de E0429.
