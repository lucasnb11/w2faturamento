-- Cadastro cifrado do A1 da W2. Não cadastrar certificados ou senhas neste SQL.
-- Esta tabela é acessível apenas pelo serviço de backend autenticado.
create table if not exists public.nfse_certificados_a1 (
  cnpj text primary key check (cnpj = '46167015000140'),
  dados_cifrados text not null check (char_length(dados_cifrados) between 32 and 500000),
  nonce text not null check (char_length(nonce) = 16),
  key_version integer not null default 1 check (key_version = 1),
  valido_desde timestamptz not null,
  valido_ate timestamptz not null,
  sha256 text not null check (sha256 ~ '^[0-9a-f]{64}$'),
  cadastrado_por uuid references auth.users(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (valido_ate > valido_desde)
);
alter table public.nfse_certificados_a1 enable row level security;
revoke all on public.nfse_certificados_a1 from public, anon, authenticated;
grant select, insert, update on public.nfse_certificados_a1 to service_role;
comment on table public.nfse_certificados_a1 is 'A1 e senha cifrados com AES-256-GCM; chave externa ao banco. Sem acesso direto do navegador.';
