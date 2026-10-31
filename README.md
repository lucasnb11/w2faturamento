# W2 Faturamento · versão 2.10.1

Sistema de faturamento e acompanhamento de entregas da W2 Transportes, com fechamentos por quinzena, importação de CAFs/AWBs, pagamentos por cidade e acesso por perfil no Supabase.

Publicado em https://faturamento-jade.vercel.app.

Inclui [validação local e assinatura da DPS](README_V2_8_INTEGRACAO.md) e [diagnóstico autenticado do A1 e controle de numeração de homologação](README_V2_9_CONEXAO.md). A transmissão e a emissão oficial continuam desabilitadas.

Consulte também a [preparação da DPS de homologação](README_V2_10_PREPARACAO.md).

A versão 2.10.1 reorganiza a prévia do DANFSe conforme o modelo recebido: cabeçalho nacional, quatro colunas, blocos tributários e rodapé de ciência em A4. Mantém aviso de teste, campos pendentes e identificação fiscal sem número, chave ou QR de autorização.

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
```

Os scripts SQL versionados documentam a estrutura. Publicar o código não executa migrações automaticamente.

Logomarca da prévia: arquivo público disponibilizado no [Portal Nacional da NFS-e](https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/logos-da-nfs-e). A interface referencia a imagem oficial por HTTPS; não publica imagens extraídas de documentos anexados pelo usuário.
