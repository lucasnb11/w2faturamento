-- W2 Dashboard CAF V1.5.1
-- Execute uma única vez no SQL Editor do MESMO projeto Supabase usado pelo CheckLog.

-- Mantém a tabela perfis existente e apenas adiciona a permissão do Dashboard.
alter table public.perfis
  add column if not exists acesso_dashboard boolean not null default false;

-- Exemplo para liberar um usuário já cadastrado no CheckLog:
-- update public.perfis set acesso_dashboard = true where email = 'usuario@empresa.com';

-- Para retirar o acesso sem excluir o usuário:
-- update public.perfis set acesso_dashboard = false where email = 'usuario@empresa.com';

-- A V1.5.1 continua respeitando o campo ativo já usado pelo CheckLog.
-- O login só é liberado quando: existe perfil + ativo não é false + acesso_dashboard = true.
