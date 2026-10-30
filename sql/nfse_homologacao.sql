-- Somente homologação. Não numera nem emite NFS-e de produção.
create table public.nfse_homologacao_config (
  cnpj text primary key default '46167015000140' check (cnpj = '46167015000140'),
  serie integer check (serie between 0 and 89999),
  proximo_numero bigint not null default 1 check (proximo_numero between 1 and 999999999999999),
  updated_at timestamptz not null default now()
);
insert into public.nfse_homologacao_config (cnpj) values ('46167015000140');

create table public.nfse_homologacao_dps (
  id uuid primary key default gen_random_uuid(),
  rascunho_id bigint not null unique references public.nfse_rascunhos(id) on delete restrict,
  rascunho_versao timestamptz not null,
  snapshot jsonb not null check (jsonb_typeof(snapshot) = 'object'),
  serie integer not null check (serie between 0 and 89999),
  numero bigint not null check (numero between 1 and 999999999999999),
  dps_id text not null unique check (dps_id ~ '^DPS1500800246167015000140[0-9]{20}$'),
  estado text not null default 'reservada' check (estado in ('reservada','assinada','enviando','pendente_consulta','autorizada','rejeitada','falha_local')),
  criado_por uuid not null references auth.users(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (serie,numero)
);
create index nfse_homologacao_dps_criado_por_idx on public.nfse_homologacao_dps(criado_por);

create table public.nfse_homologacao_eventos (
  id bigint generated always as identity primary key,
  dps_id uuid not null references public.nfse_homologacao_dps(id) on delete restrict,
  tipo text not null check (tipo in ('reserva','estado')),
  estado text not null,
  autor uuid not null references auth.users(id),
  created_at timestamptz not null default now()
);
create index nfse_homologacao_eventos_dps_idx on public.nfse_homologacao_eventos(dps_id);
create index nfse_homologacao_eventos_autor_idx on public.nfse_homologacao_eventos(autor);

alter table public.nfse_homologacao_config enable row level security;
alter table public.nfse_homologacao_dps enable row level security;
alter table public.nfse_homologacao_eventos enable row level security;
revoke all on public.nfse_homologacao_config, public.nfse_homologacao_dps, public.nfse_homologacao_eventos from public, anon, authenticated;
grant select, insert, update on public.nfse_homologacao_config, public.nfse_homologacao_dps to service_role;
grant select, insert on public.nfse_homologacao_eventos to service_role;
revoke all on sequence public.nfse_homologacao_eventos_id_seq from public, anon, authenticated;
grant usage, select on sequence public.nfse_homologacao_eventos_id_seq to service_role;

create function public.nfse_reservar_homologacao(p_rascunho_id bigint, p_versao timestamptz, p_autor uuid)
returns public.nfse_homologacao_dps
language plpgsql security invoker set search_path = ''
as $$
declare
  v_rascunho public.nfse_rascunhos;
  v_existente public.nfse_homologacao_dps;
  v_config public.nfse_homologacao_config;
  v_resultado public.nfse_homologacao_dps;
begin
  if not exists (select 1 from public.perfis_faturamento where id=p_autor and ativo=true and perfil='administrador') then
    raise exception 'Administrador ativo necessário' using errcode='42501';
  end if;
  select * into v_rascunho from public.nfse_rascunhos where id=p_rascunho_id for update;
  if not found then raise exception 'Rascunho não encontrado' using errcode='P0002'; end if;
  if v_rascunho.updated_at is distinct from p_versao then
    raise exception 'Versão do rascunho alterada' using errcode='40001';
  end if;
  if v_rascunho.emitente_cnpj <> '46167015000140' or v_rascunho.tomador_cnpj <> '73939449000193' then
    raise exception 'Contrato fora do escopo' using errcode='22023';
  end if;
  select * into v_existente from public.nfse_homologacao_dps where rascunho_id=p_rascunho_id;
  if found then
    if v_existente.rascunho_versao is distinct from p_versao then
      raise exception 'DPS já reservada para outra versão. Concilie antes de continuar.' using errcode='40001';
    end if;
    return v_existente;
  end if;
  select * into v_config from public.nfse_homologacao_config where cnpj='46167015000140' for update;
  if not found or v_config.serie is null then
    raise exception 'Série de homologação não configurada' using errcode='22023';
  end if;
  if v_config.proximo_numero >= 999999999999999 then
    raise exception 'Numeração esgotada' using errcode='22003';
  end if;
  insert into public.nfse_homologacao_dps(rascunho_id,rascunho_versao,snapshot,serie,numero,dps_id,criado_por)
  values (p_rascunho_id,p_versao,to_jsonb(v_rascunho),v_config.serie,v_config.proximo_numero,
    'DPS1500800246167015000140'||lpad(v_config.serie::text,5,'0')||lpad(v_config.proximo_numero::text,15,'0'),p_autor)
  returning * into v_resultado;
  update public.nfse_homologacao_config set proximo_numero=proximo_numero+1,updated_at=clock_timestamp()
  where cnpj='46167015000140';
  insert into public.nfse_homologacao_eventos(dps_id,tipo,estado,autor)
  values (v_resultado.id,'reserva','reservada',p_autor);
  return v_resultado;
end;
$$;
revoke all on function public.nfse_reservar_homologacao(bigint,timestamptz,uuid) from public, anon, authenticated;
grant execute on function public.nfse_reservar_homologacao(bigint,timestamptz,uuid) to service_role;

create function public.nfse_mudar_estado_homologacao(p_id uuid,p_esperado text,p_novo text,p_autor uuid)
returns public.nfse_homologacao_dps
language plpgsql security invoker set search_path = ''
as $$
declare v_resultado public.nfse_homologacao_dps;
begin
  if not exists (select 1 from public.perfis_faturamento where id=p_autor and ativo=true and perfil='administrador') then
    raise exception 'Administrador ativo necessário' using errcode='42501';
  end if;
  if not ((p_esperado='reservada' and p_novo in ('assinada','falha_local'))
    or (p_esperado='falha_local' and p_novo='assinada')
    or (p_esperado='assinada' and p_novo='enviando')
    or (p_esperado='enviando' and p_novo in ('pendente_consulta','autorizada','rejeitada'))
    or (p_esperado='pendente_consulta' and p_novo in ('autorizada','rejeitada'))) then
    raise exception 'Transição não permitida' using errcode='22023';
  end if;
  update public.nfse_homologacao_dps set estado=p_novo,updated_at=clock_timestamp()
  where id=p_id and estado=p_esperado returning * into v_resultado;
  if not found then raise exception 'Estado alterado; consulte antes de tentar novamente' using errcode='40001'; end if;
  insert into public.nfse_homologacao_eventos(dps_id,tipo,estado,autor) values (p_id,'estado',p_novo,p_autor);
  return v_resultado;
end;
$$;
revoke all on function public.nfse_mudar_estado_homologacao(uuid,text,text,uuid) from public, anon, authenticated;
grant execute on function public.nfse_mudar_estado_homologacao(uuid,text,text,uuid) to service_role;
