# W2 Sistema de Faturamento V2.2

1. Execute `supabase_schema_v2_2.sql` no SQL Editor (depois da V2.1).
2. Em Authentication > Users, crie o primeiro usuário por e-mail/senha.
3. Promova o primeiro usuário a administrador executando o UPDATE comentado no fim do SQL, trocando `SEU_EMAIL`.
4. Publique todos os arquivos no Vercel.

Perfis:
- administrador: acesso total
- financeiro: Dashboard, Faturamento, Pagamentos e Importações
- operador: Dashboard, CAFs e Cidades

A V2.2 mantém fallback local se a leitura remota falhar. Novas importações e pagamentos autenticados são enviados ao Supabase.
