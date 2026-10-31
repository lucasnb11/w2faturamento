-- Amplia somente a retomada explícita após E0714. Preserva XML e estado anteriores.
create or replace function public.nfse_nova_tentativa_homologacao(p_anterior uuid,p_anterior_versao timestamptz,p_versao timestamptz,p_autor uuid)
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
    or not coalesce(((a.estado='pendente_consulta' and a.retorno_http=404)
      or (a.estado='rejeitada' and a.retorno_http in (400,422) and a.erros_codigos='["E0714"]'::jsonb)),false)
    or a.dps_xml_cifrado is null or a.chave_acesso is not null or a.nfse_xml_cifrado is not null then
    raise exception 'Tentativa alterada ou sem condição de retomada; atualizar situação' using errcode='40001';
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
