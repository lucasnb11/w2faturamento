# W2 Faturamento — V2.7.1 · cadastro protegido do A1

Esta versão acrescenta a etapa de cadastro do certificado A1 ao Faturamento. A emissão fiscal continua indisponível: a integração de assinatura/transmissão da DPS, consulta de autorização e armazenamento do XML oficial ainda não foi implementada.

## Dados da W2 preenchidos

- Inscrição municipal informada pelo usuário: `000000000078123`, preservada como texto.
- Simples Nacional: optante ME/EPP, conforme informação do usuário e porte ME do documento. A apuração do ISS e a situação em cada competência ainda devem ser confirmadas.
- Endereço, CEP, e-mail e telefone transcritos do documento W2.pdf. O número está registrado como `18 19` e exige conferência; não foi adivinhado.
- O tipo A1 foi informado pelo usuário. Nenhum certificado real ou senha foi recebido nesta entrega.

## O que mudou

Na aba Notas fiscais, o administrador encontra o painel Certificado digital A1. Primeiro usa Verificar configuração; o formulário só é habilitado quando o servidor HTTPS responde e valida sua sessão e seu perfil administrador ativo.

O arquivo `.pfx`/`.p12` e a senha são enviados apenas à função do próprio sistema, sem redirecionamentos. A senha e a seleção do arquivo são limpas da tela ao final da tentativa. Os dados não são gravados em localStorage, nos rascunhos fiscais, em arquivos temporários ou nos arquivos públicos do site.

O servidor verifica senha, presença da chave privada, correspondência entre chave e certificado, CNPJ da W2, validade e usos declarados no certificado. O parser roda em um processo com limite de tempo. Certificados de terceiros, vencidos, sem chave ou com senha inválida são rejeitados. A aceitação local não comprova cadeia ICP-Brasil, revogação ou habilitação na API nacional; essas verificações continuam pendentes para a integração oficial.

O arquivo e a senha são cifrados juntos com AES-256-GCM e nonce aleatório. O banco recebe somente o conteúdo cifrado, nonce e metadados; a chave de cifragem fica nas variáveis privadas do servidor. A interface recebe apenas CNPJ, validade, identificação criptográfica e data de atualização. Uma substituição exige confirmação e a versão atual do cadastro, para evitar sobrescrever alterações simultâneas.

## Banco já configurado

A tabela `nfse_certificados_a1` foi criada no mesmo Supabase do Faturamento. RLS está ativo. Anônimos e usuários autenticados não têm acesso direto à tabela; o backend usa a chave de serviço e verifica a identidade e o perfil em toda requisição.

A ausência de políticas de liberação nessa tabela é intencional: nenhum acesso direto do navegador é permitido. A chave de serviço bypassa RLS e nunca deve ser inserida no código público.

A estrutura do banco foi conferida em 30/10/2026. Não é necessário executar novamente o SQL nesse projeto. O script incluído serve para configurar outro ambiente do Faturamento. A situação atual do certificado deve ser consultada pelo administrador na interface.

## Publicação no Vercel

1. Use a raiz deste repositório no projeto do Faturamento, incluindo `index.html`, arquivos JS/CSS, `api/`, `requirements.txt` e `vercel.json`. Não publique apenas o HTML.
2. Mantenha o projeto como framework Other. Esta versão possui uma função Python além dos arquivos estáticos; a publicação precisa reconhecer `api/nfse/certificado.py` e instalar `requirements.txt`.
3. No projeto atual, as quatro variáveis abaixo já foram cadastradas em Production em 30/10/2026. Para outro ambiente, configure todas elas. Não use prefixos públicos e não cole valores secretos no chat ou no GitHub.
4. Faça novo deploy. As variáveis só passam a valer na função publicada após a nova implantação.
5. Entre como administrador, abra Notas fiscais → Certificado digital A1 → Verificar configuração. Somente depois de o formulário ser habilitado selecione o arquivo e informe a senha diretamente no site HTTPS.

| Variável | Conteúdo |
| --- | --- |
| `SUPABASE_URL` | URL do projeto Supabase já usado no Faturamento |
| `SUPABASE_SECRET_KEY` | Chave secreta do servidor do mesmo Supabase (`sb_secret_...`) |
| `NFSE_APP_ORIGIN` | Endereço HTTPS exato do site, sem barra final ou caminho; por exemplo `https://faturamento-jade.vercel.app` |
| `NFSE_A1_ENCRYPTION_KEY` | Chave aleatória de 32 bytes, codificada em Base64, gerada por você |

Se estiver usando a chave legada de serviço do Supabase, use `SUPABASE_SERVICE_ROLE_KEY` no lugar de `SUPABASE_SECRET_KEY`. A chave anon/publishable do frontend não serve para essa etapa.

A chave de proteção já foi gerada e cadastrada como segredo no projeto atual. Não a substitua depois de cadastrar um certificado, pois o A1 cifrado depende dela. Para um NOVO ambiente, uma chave pode ser gerada em um terminal da sua confiança:

```sh
python3 -c "import secrets,base64; print(base64.b64encode(secrets.token_bytes(32)).decode())"
```

Copie o resultado apenas para a variável privada do Vercel e guarde uma cópia em um gerenciador seguro. A chave não é incluída neste pacote. Se ela for perdida ou trocada, será necessário recadastrar o A1; não há recuperação sem a chave original.

A senha do A1 é digitada no formulário do administrador; não é uma variável de ambiente. Não habilite captura de corpos de requisição em ferramentas de observabilidade para essa rota.

## Verificações realizadas

- Testes de leitura de PFX sintético, senha errada, validade, CNPJ de outra empresa e ausência de chave.
- Validação do OtherName de CNPJ e associação do CNPJ ao material cifrado.
- Cifragem, decifragem de teste, nonce independente e falha de autenticação com chave ou contexto divergentes.
- API HTTP local com requisições reais: bloqueio sem sessão, perfil financeiro e administrador inativo, origem divergente, substituição não confirmada e erros sem exposição de segredos.
- Teste de limpeza dos campos e do envio à mesma origem em DOM simulado.
- Verificação dos privilégios e RLS no Supabase.

Os testes usam certificados e senhas sintéticos em memória, sem gravação no banco real. A versão 2.7.1 foi publicada em Production na Vercel em 30/10/2026: a página respondeu HTTP 200 e a API sem autenticação respondeu HTTP 401 com `LOGIN_NECESSARIO`. A validação autenticada do certificado real deve ser feita pelo administrador na interface. Não houve teste com a API nacional ou emissão de nota.

Para executar os testes localmente após instalar os requisitos:

```sh
python3 -m unittest discover -s tests -v
node tests/test_a1_frontend.cjs
```

## Próximos passos fiscais

Depois do cadastro do A1, permanecem pendentes o enquadramento do serviço, a incidência e a retenção do ISS, os demais tributos e a validação contábil da consolidação por quinzena. Em seguida vem o backend de emissão e a homologação do fluxo completo.

## Correção de compatibilidade com o Vercel

O método interno do endpoint foi renomeado para evitar conflito com `handle_request`, utilizado pelo adaptador Python do Vercel. Foi acrescentado um teste de regressão simulando esse comportamento do runtime.
