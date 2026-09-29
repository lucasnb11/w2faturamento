-- W2 Sistema de Faturamento V2.2.1
-- Perfis EXCLUSIVOS do Sistema de Faturamento.
-- Este script NAO altera public.perfis, policies ou triggers do W2 CheckLog.
-- Execute depois dos schemas V2.1/V2.2 já aplicados. Ele apenas cria objetos novos do Faturamento.

create table if not exists public.perfis_faturamento (
  id uuid primary key references auth.users(id) on delete cascade,
  email text,
  nome text,
  perfil text not null default 'operador',
  ativo boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint perfis_faturamento_perfil_check
    check (perfil in ('administrador','financeiro','operador'))
);

create unique index if not exists perfis_faturamento_email_lower_uidx
  on public.perfis_faturamento (lower(email)) where email is not null;

alter table public.perfis_faturamento enable row level security;

drop policy if exists "faturamento_ler_proprio_perfil" on public.perfis_faturamento;
create policy "faturamento_ler_proprio_perfil"
  on public.perfis_faturamento
  for select to authenticated
  using (id = auth.uid());

-- Cria SOMENTE o perfil do Faturamento para novos usuários do Supabase Auth.
create or replace function public.faturamento_criar_perfil_usuario()
returns trigger
language plpgsql
security definer
set search_path=public
as $$
begin
  insert into public.perfis_faturamento (id,email,nome,perfil,ativo)
  values (
    new.id,
    new.email,
    coalesce(new.raw_user_meta_data->>'name', split_part(new.email,'@',1)),
    'operador',
    true
  )
  on conflict (id) do nothing;
  return new;
end;
$$;

drop trigger if exists faturamento_auth_novo_usuario on auth.users;
create trigger faturamento_auth_novo_usuario
after insert on auth.users
for each row execute procedure public.faturamento_criar_perfil_usuario();

-- Sincroniza usuários Auth já existentes SOMENTE para a nova tabela do Faturamento.
insert into public.perfis_faturamento (id,email,nome,perfil,ativo)
select
  u.id,
  u.email,
  coalesce(u.raw_user_meta_data->>'name', split_part(u.email,'@',1)),
  'operador',
  true
from auth.users u
on conflict (id) do nothing;

-- Para promover um usuário no FATURAMENTO, use após executar este script:
-- update public.perfis_faturamento
-- set perfil='administrador', ativo=true, updated_at=now()
-- where lower(email)=lower('SEU_EMAIL');
