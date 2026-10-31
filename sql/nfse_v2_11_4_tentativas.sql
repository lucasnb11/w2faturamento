-- Novas tentativas explícitas, somente de homologação. Não cria reservas ao aplicar.
alter table public.nfse_homologacao_dps
  add column tentativa integer not null default 1 check(tentativa>0),
  add column anterior_id uuid unique references public.nfse_homologacao_dps(id) on delete restrict,
  add constraint nfse_homologacao_dps_sem_autorreferencia check(anterior_id is distinct from id);
alter table public.nfse_homologacao_dps drop constraint nfse_homologacao_dps_rascunho_id_key;
alter table public.nfse_homologacao_dps add constraint nfse_homologacao_dps_rascunho_tentativa_key unique(rascunho_id,tentativa);
alter table public.nfse_homologacao_eventos add column detalhes jsonb not null default '{}'::jsonb check(jsonb_typeof(detalhes)='object');

create or replace function public.nfse_reservar_homologacao(p_rascunho_id bigint, p_versao timestamptz, p_autor uuid)
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
  select * into v_existente from public.nfse_homologacao_dps where rascunho_id=p_rascunho_id order by tentativa desc limit 1;
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

create or replace function public.nfse_gravar_retorno_homologacao(p_id uuid,p_esperado text,p_novo text,p_http integer,p_codigos jsonb,
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
  insert into public.nfse_homologacao_eventos(dps_id,tipo,estado,autor,detalhes) values(p_id,'estado',p_novo,p_autor,jsonb_build_object('http',p_http,'codigos',p_codigos));
  return v;
end;
$$;
revoke all on function public.nfse_gravar_retorno_homologacao(uuid,text,text,integer,jsonb,text,text,text,text,uuid) from public,anon,authenticated;
grant execute on function public.nfse_gravar_retorno_homologacao(uuid,text,text,integer,jsonb,text,text,text,text,uuid) to service_role;


create function public.nfse_nova_tentativa_homologacao(p_anterior uuid,p_anterior_versao timestamptz,p_versao timestamptz,p_autor uuid)
returns public.nfse_homologacao_dps language plpgsql security invoker set search_path=''
as $$
declare d public.nfse_rascunhos; a public.nfse_homologacao_dps; n public.nfse_homologacao_dps; c public.nfse_homologacao_config;
begin
  if not exists(select 1 from public.perfis_faturamento where id=p_autor and ativo and perfil='administrador') then
    raise exception 'Administrador ativo necessário' using errcode='42501';
  end if;
  select * into d from public.nfse_rascunhos where id=(select rascunho_id from public.nfse_homologacao_dps where id=p_anterior) for update;
  if not found or d.updated_at is distinct from p_versao then raise exception 'Rascunho alterado' using errcode='40001'; end if;
  if d.emitente_cnpj<>'46167015000140' or d.tomador_cnpj<>'73939449000193' then raise exception 'Contrato fora do escopo' using errcode='22023'; end if;
  select * into a from public.nfse_homologacao_dps where rascunho_id=d.id order by tentativa desc limit 1 for update;
  if a.id is distinct from p_anterior or a.updated_at is distinct from p_anterior_versao
    or a.estado<>'pendente_consulta' or a.retorno_http is distinct from 404
    or a.dps_xml_cifrado is null or a.chave_acesso is not null or a.nfse_xml_cifrado is not null then
    raise exception 'Tentativa alterada ou sem consulta 404; atualizar situação' using errcode='40001';
  end if;
  if not exists(select 1 from public.nfse_homologacao_eventos where dps_id=a.id and estado='enviando')
    or (select max(created_at) from public.nfse_homologacao_eventos where dps_id=a.id and estado='enviando')>clock_timestamp()-interval '3 minutes' then
    raise exception 'Envio recente; aguarde antes de criar outra tentativa' using errcode='40001';
  end if;
  select * into c from public.nfse_homologacao_config where cnpj='46167015000140' for update;
  if not found or c.serie is null or c.serie not between 1 and 49999 or c.proximo_numero>=999999999999999 then
    raise exception 'Numeração indisponível' using errcode='22023';
  end if;
  insert into public.nfse_homologacao_dps(rascunho_id,rascunho_versao,snapshot,serie,numero,dps_id,criado_por,tentativa,anterior_id)
    values(d.id,p_versao,to_jsonb(d),c.serie,c.proximo_numero,
      'DPS1500800246167015000140'||lpad(c.serie::text,5,'0')||lpad(c.proximo_numero::text,15,'0'),p_autor,a.tentativa+1,a.id)
    returning * into n;
  update public.nfse_homologacao_config set proximo_numero=proximo_numero+1,updated_at=clock_timestamp() where cnpj=c.cnpj;
  -- O servidor chamou GET novamente imediatamente antes desta transação.
  -- A linha e o XML antigos ficam intactos; registra-se a consulta adicional.
  insert into public.nfse_homologacao_eventos(dps_id,tipo,estado,autor,detalhes)
    values(a.id,'estado',a.estado,p_autor,jsonb_build_object('acao','consulta_ausencia_antes_nova_tentativa','http',404,'nova_tentativa',n.id));
  insert into public.nfse_homologacao_eventos(dps_id,tipo,estado,autor,detalhes)
    values(n.id,'reserva','reservada',p_autor,jsonb_build_object('acao','nova_tentativa_explicita','anterior',a.id));
  return n;
end;
$$;
revoke all on function public.nfse_nova_tentativa_homologacao(uuid,timestamptz,timestamptz,uuid) from public,anon,authenticated;
grant execute on function public.nfse_nova_tentativa_homologacao(uuid,timestamptz,timestamptz,uuid) to service_role;
