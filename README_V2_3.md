# W2 Sistema de Faturamento — V2.3.0

## Objetivo
Migrar a base histórica do `data.js` para o Supabase de forma controlada e idempotente.

## Novidades
- Migração histórica disponível somente para perfil `administrador`.
- Envio em lotes para `public.entregas`.
- Deduplicação pela constraint única `(caf_id, awb)`.
- Progresso visual e resumo de novos/duplicados.
- Registro da execução em `public.importacoes` com origem `migracao`.
- Reexecução segura: uma migração concluída não é executada novamente.
- Carregamento paginado do Supabase (corrige o limite padrão de 1.000 linhas e permite carregar toda a base histórica).
- `public.perfis` do W2 CheckLog não é alterada; autenticação do Faturamento continua usando `public.perfis_faturamento`.

## Como usar
1. Publique todos os arquivos da V2.3.0 no Vercel.
2. Entre com um usuário `administrador` do Sistema de Faturamento.
3. Abra **Importações**.
4. Em **Migração da base histórica**, confira os totais e clique em **Migrar base histórica**.
5. Não feche a página durante a transferência.
6. Ao final, confira o total informado pelo painel e o Dashboard.

## Importante
Esta versão mantém `data.js` propositalmente como fonte da migração e contingência. Depois de confirmar a migração completa no Supabase, ele poderá ser removido em uma versão posterior sem risco de perder a base histórica.
