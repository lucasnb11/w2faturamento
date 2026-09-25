W2 Dashboard CAF V2.0 - Persistência Supabase

1. No mesmo projeto Supabase do CheckLog, abra SQL Editor.
2. Execute TODO o conteúdo de SUPABASE_V2.sql uma única vez.
3. Confirme que seu usuário possui ativo=true e acesso_dashboard=true na tabela perfis.
4. Publique todos os arquivos deste pacote na Vercel.
5. Faça login normalmente.
6. No primeiro acesso, se dashboard_cafs estiver vazia, o sistema migra automaticamente a base inicial de 11.812 registros para o Supabase. Aguarde a mensagem de sincronização terminar.
7. A partir daí, novas importações ficam persistidas no Supabase e permanecem após atualizar, sair ou acessar em outro dispositivo.

IMPORTANTE:
- Não use service_role no frontend.
- O arquivo supabase-config.js usa somente a chave pública/publishable.
- A combinação CAF + AWB é única no banco, impedindo duplicidade.
- O histórico de importações e os pagamentos também passam a ser persistidos.
