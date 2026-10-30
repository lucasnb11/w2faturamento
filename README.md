# W2 Faturamento · versão 2.7.1

Sistema de faturamento e acompanhamento de entregas da W2 Transportes, com fechamentos por quinzena, importação de CAFs/AWBs, pagamentos por cidade e acesso por perfil no Supabase.

Publicado em https://faturamento-jade.vercel.app.

Em desenvolvimento: [validação local da integração fiscal](README_V2_8_INTEGRACAO.md), com XSD oficial de homologação e pendências por rascunho. Esta etapa não habilita transmissão.

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
