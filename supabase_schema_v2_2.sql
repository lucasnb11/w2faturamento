-- W2 Sistema de Faturamento V2.2 - autenticação e perfis
-- Execute DEPOIS do supabase_schema_v2_1.sql.

create table if not exists public.perfis (
  id uuid primary key references auth.users(id) on delete cascade,
  nome text,
  perfil text not null default 'operador',
  sistema_faturamento boolean not null default true,
  ativo boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- Compatibilidade caso a tabela perfis já exista (ex.: CheckLog).
alter table public.perfis add column if not exists nome text;
alter table public.perfis add column if not exists perfil text default 'operador';
alter table public.perfis add column if not exists sistema_faturamento boolean default true;
alter table public.perfis add column if not exists ativo boolean default true;
alter table public.perfis add column if not exists created_at timestamptz default now();
alter table public.perfis add column if not exists updated_at timestamptz default now();

alter table public.perfis enable row level security;
drop policy if exists "w2_perfil_proprio" on public.perfis;
create policy "w2_perfil_proprio" on public.perfis for select to authenticated using (id = auth.uid());

-- Cria perfil automaticamente para novos usuários do Auth.
create or replace function public.w2_criar_perfil_usuario()
returns trigger language plpgsql security definer set search_path=public as $$
begin
  insert into public.perfis (id,nome,perfil,sistema_faturamento,ativo)
  values (new.id, coalesce(new.raw_user_meta_data->>'name', split_part(new.email,'@',1)), 'operador', true, true)
  on conflict (id) do nothing;
  return new;
end; $$;

drop trigger if exists w2_auth_novo_usuario on auth.users;
create trigger w2_auth_novo_usuario after insert on auth.users
for each row execute procedure public.w2_criar_perfil_usuario();

-- IMPORTANTE: após criar seu primeiro usuário em Authentication > Users,
-- promova-o para administrador pelo e-mail:
-- update public.perfis p set perfil='administrador'
-- from auth.users u where p.id=u.id and u.email='SEU_EMAIL';
