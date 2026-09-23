# W2 Sistema de Faturamento V2.1

Base funcional: V2.0.4 validada.

## O que esta versão adiciona
- Cliente Supabase no frontend (`supabase.js`).
- Configuração isolada (`supabase-config.js`).
- SQL definitivo inicial (`supabase_schema_v2_1.sql`).
- Tabelas: importacoes, entregas, fechamentos e pagamentos_entregadores.
- UNIQUE(caf_id, awb) para impedir AWB duplicado dentro da mesma CAF.
- RLS habilitado: a anon key não consegue ler/gravar dados operacionais.
- Adaptador preparado para carregar entregas/importações/pagamentos e persistir importações/pagamentos quando houver sessão autenticada.

## Configuração
1. No Supabase SQL Editor, execute `supabase_schema_v2_1.sql`.
2. Em `supabase-config.js`, informe a Project URL e a anon/publishable key.
3. Publique todos os arquivos no Vercel.

## Importante
A V2.1 NÃO abre o banco para usuários anônimos. Até a V2.2 (login/perfis), o dashboard continua usando a base local validada na V2.0.4. Isso evita expor dados de faturamento publicamente.

Na V2.2, após login, o mesmo adaptador passa a usar o Supabase e será feita a migração dos dados históricos.
