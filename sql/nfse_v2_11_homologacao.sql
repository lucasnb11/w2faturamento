-- Amplia somente o fluxo privado de homologação. Aplicar antes da versão 2.11.
alter table public.nfse_homologacao_config drop constraint nfse_homologacao_config_serie_check;
alter table public.nfse_homologacao_config add constraint nfse_homologacao_config_serie_check check (serie between 1 and 49999);
alter table public.nfse_homologacao_dps drop constraint nfse_homologacao_dps_serie_check;
alter table public.nfse_homologacao_dps add constraint nfse_homologacao_dps_serie_check check (serie between 1 and 49999);
alter table public.nfse_homologacao_dps
  add column dps_xml_cifrado text,
  add column dps_xml_nonce text,
  add column dps_xml_sha256 text,
  add column nfse_xml_cifrado text,
  add column nfse_xml_nonce text,
  add column nfse_xml_sha256 text,
  add column chave_acesso text check (chave_acesso ~ '^[0-9]{50}$'),
  add column retorno_http integer check (retorno_http between 100 and 599),
  add column erros_codigos jsonb not null default '[]'::jsonb check (jsonb_typeof(erros_codigos)='array' and jsonb_array_length(erros_codigos)<=5);

create function public.nfse_gravar_assinatura_homologacao(p_id uuid,p_cifrado text,p_nonce text,p_sha256 text,p_autor uuid)
returns public.nfse_homologacao_dps language plpgsql security invoker set search_path=''
as $$
declare v public.nfse_homologacao_dps;
begin
  if not exists(select 1 from public.perfis_faturamento where id=p_autor and ativo and perfil='administrador') then
    raise exception 'Administrador ativo necessário' using errcode='42501';
  end if;
  if p_cifrado is null or length(p_cifrado) not between 40 and 1500000 or p_cifrado !~ '^[A-Za-z0-9+/=]+$'
    or p_nonce is null or p_nonce !~ '^[A-Za-z0-9+/]{16}$' or p_sha256 is null or p_sha256 !~ '^[a-f0-9]{64}$' then
    raise exception 'Envelope inválido' using errcode='22023';
  end if;
  select * into v from public.nfse_homologacao_dps where id=p_id for update;
  if not found then raise exception 'Reserva ausente' using errcode='P0002'; end if;
  if v.estado='assinada' and v.dps_xml_cifrado is not null then return v; end if;
  if v.estado not in ('reservada','falha_local') or v.dps_xml_cifrado is not null then
    raise exception 'Estado alterado' using errcode='40001';
  end if;
  update public.nfse_homologacao_dps set dps_xml_cifrado=p_cifrado,dps_xml_nonce=p_nonce,dps_xml_sha256=p_sha256,
    estado='assinada',updated_at=clock_timestamp() where id=p_id returning * into v;
  insert into public.nfse_homologacao_eventos(dps_id,tipo,estado,autor) values(p_id,'estado','assinada',p_autor);
  return v;
end;
$$;
revoke all on function public.nfse_gravar_assinatura_homologacao(uuid,text,text,text,uuid) from public,anon,authenticated;
grant execute on function public.nfse_gravar_assinatura_homologacao(uuid,text,text,text,uuid) to service_role;

create function public.nfse_iniciar_envio_homologacao(p_id uuid,p_autor uuid)
returns public.nfse_homologacao_dps language plpgsql security invoker set search_path=''
as $$
declare v public.nfse_homologacao_dps; v_versao timestamptz;
begin
  if not exists(select 1 from public.perfis_faturamento where id=p_autor and ativo and perfil='administrador') then
    raise exception 'Administrador ativo necessário' using errcode='42501';
  end if;
  select updated_at into v_versao from public.nfse_rascunhos
    where id=(select rascunho_id from public.nfse_homologacao_dps where id=p_id) for update;
  update public.nfse_homologacao_dps set estado='enviando',updated_at=clock_timestamp()
    where id=p_id and estado='assinada' and dps_xml_cifrado is not null and rascunho_versao=v_versao returning * into v;
  if not found then raise exception 'Estado ou rascunho alterado; consultar antes de continuar' using errcode='40001'; end if;
  insert into public.nfse_homologacao_eventos(dps_id,tipo,estado,autor) values(p_id,'estado','enviando',p_autor);
  return v;
end;
$$;
revoke all on function public.nfse_iniciar_envio_homologacao(uuid,uuid) from public,anon,authenticated;
grant execute on function public.nfse_iniciar_envio_homologacao(uuid,uuid) to service_role;

create function public.nfse_gravar_retorno_homologacao(p_id uuid,p_esperado text,p_novo text,p_http integer,p_codigos jsonb,
  p_chave text,p_cifrado text,p_nonce text,p_sha256 text,p_autor uuid)
returns public.nfse_homologacao_dps language plpgsql security invoker set search_path=''
as $$
declare v public.nfse_homologacao_dps;
begin
  if not exists(select 1 from public.perfis_faturamento where id=p_autor and ativo and perfil='administrador') then
    raise exception 'Administrador ativo necessário' using errcode='42501';
  end if;
  if p_esperado not in ('enviando','pendente_consulta','rejeitada') or p_novo not in ('pendente_consulta','autorizada','rejeitada')
    or (p_esperado='rejeitada' and p_novo<>'autorizada')
    or p_codigos is null or jsonb_typeof(p_codigos)<>'array' or jsonb_array_length(p_codigos)>5 then
    raise exception 'Retorno inválido' using errcode='22023';
  end if;
  if p_novo='autorizada' then
    if p_chave is null or p_chave !~ '^[0-9]{50}$' or p_cifrado is null or length(p_cifrado) not between 40 and 1500000
      or p_cifrado !~ '^[A-Za-z0-9+/=]+$' or p_nonce is null or p_nonce !~ '^[A-Za-z0-9+/]{16}$'
      or p_sha256 is null or p_sha256 !~ '^[a-f0-9]{64}$' then
      raise exception 'Documento autorizado ausente' using errcode='22023';
    end if;
  elsif p_chave is not null or p_cifrado is not null or p_nonce is not null or p_sha256 is not null then
    raise exception 'Documento incompatível com estado' using errcode='22023';
  end if;
  update public.nfse_homologacao_dps set estado=p_novo,retorno_http=p_http,erros_codigos=p_codigos,
    chave_acesso=p_chave,nfse_xml_cifrado=p_cifrado,nfse_xml_nonce=p_nonce,nfse_xml_sha256=p_sha256,updated_at=clock_timestamp()
    where id=p_id and estado=p_esperado and dps_xml_cifrado is not null returning * into v;
  if not found then raise exception 'Estado alterado; consultar antes de continuar' using errcode='40001'; end if;
  insert into public.nfse_homologacao_eventos(dps_id,tipo,estado,autor) values(p_id,'estado',p_novo,p_autor);
  return v;
end;
$$;
revoke all on function public.nfse_gravar_retorno_homologacao(uuid,text,text,integer,jsonb,text,text,text,text,uuid) from public,anon,authenticated;
grant execute on function public.nfse_gravar_retorno_homologacao(uuid,text,text,integer,jsonb,text,text,text,text,uuid) to service_role;

-- Colunas novas permanecem sob os grants/RLS privados da tabela existente.
revoke all on public.nfse_homologacao_dps from public,anon,authenticated;
alter table public.nfse_homologacao_dps enable row level security;
