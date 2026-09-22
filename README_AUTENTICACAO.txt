W2 DASHBOARD CAF V1.5.1 — AUTENTICAÇÃO CENTRALIZADA COM CHECKLOG

Esta versão reutiliza o mesmo Supabase Auth e a mesma tabela public.perfis do W2 CheckLog.

Campos já utilizados pelo CheckLog: id, nome, email, perfil e ativo.
A V1.5.1 adiciona somente: acesso_dashboard (boolean).

CONFIGURAÇÃO
1. Use em supabase-config.js a MESMA URL e a MESMA chave pública/anon do projeto CheckLog.
2. Nunca use a service_role no navegador.
3. No SQL Editor do Supabase, execute SUPABASE_PERFIS_DASHBOARD.sql uma única vez.
4. Para cada usuário autorizado, marque acesso_dashboard = true na tabela perfis.
5. Publique todos os arquivos desta pasta na Vercel.

VALIDAÇÃO DO LOGIN
- Supabase Auth valida e-mail/senha.
- O Dashboard procura public.perfis.id = auth.uid().
- Sem perfil: acesso negado.
- ativo = false: acesso negado.
- acesso_dashboard diferente de true: acesso negado.
- autorizado: exibe nome e perfil no cabeçalho e libera o sistema.

Os perfis existentes do CheckLog, como supervisor e entregador, são preservados. A permissão de entrada no Dashboard é independente através de acesso_dashboard.
