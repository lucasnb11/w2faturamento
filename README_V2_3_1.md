# W2 Sistema de Faturamento V2.3.1

## Objetivo
Operação 100% baseada no Supabase após a migração histórica concluída.

## Alterações
- Remove `data.js` do pacote e da página.
- Remove o painel de migração histórica da interface.
- A base operacional (`entregas`) é carregada exclusivamente do Supabase.
- Se o Supabase falhar, o sistema informa o erro e não usa silenciosamente uma base histórica local.
- Mantém autenticação e perfis isolados em `perfis_faturamento`; não altera `public.perfis` do W2 CheckLog.
- Mantém importação manual XLSX e histórico de importações.
- Mantém carregamento paginado para suportar mais de 1.000 registros.

## Banco de dados
Esta versão não exige SQL adicional quando a V2.2.1/V2.3.0 já foi configurada e a migração histórica foi concluída.

## Publicação
Substitua todos os arquivos da versão anterior pelos arquivos deste pacote no deploy. Não publique o antigo `data.js`.
