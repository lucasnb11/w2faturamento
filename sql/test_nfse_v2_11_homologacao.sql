-- Executar após a migração. Somente dados sintéticos e ROLLBACK; sem rede/A1.
begin;
set local role service_role;
do $$
declare
  a uuid; d public.nfse_rascunhos; r public.nfse_homologacao_dps; other public.nfse_homologacao_dps;
  test_series integer;
begin
  select id into a from public.perfis_faturamento where ativo and perfil='administrador' limit 1;
  if a is null then raise exception 'Administrador de teste ausente'; end if;
  select series into test_series from generate_series(49999,1,-1) series
    where not exists(select 1 from public.nfse_homologacao_dps where serie=series) limit 1;
  update public.nfse_homologacao_config set serie=test_series,proximo_numero=1 where cnpj='46167015000140';
  begin
    update public.nfse_homologacao_config set serie=70000 where cnpj='46167015000140';
    raise exception 'Série web foi aceita';
  exception when check_violation then null;
  end;
  insert into public.nfse_rascunhos(ano,mes,quinzena,referencia,valor_rem,descricao,criado_por)
    values(2020,2,1,'SINTETICO-ROLLBACK',1,'SINTETICO; SEM ENVIO',a) returning * into d;
  select * into r from public.nfse_reservar_homologacao(d.id,d.updated_at,a);
  select * into other from public.nfse_reservar_homologacao(d.id,d.updated_at,a);
  if r.id<>other.id then raise exception 'Reserva repetida gerou outro ID'; end if;
  begin
    perform public.nfse_iniciar_envio_homologacao(r.id,a);
    raise exception 'Envio sem documento assinado foi aceito';
  exception when serialization_failure then null;
  end;
  select * into r from public.nfse_gravar_assinatura_homologacao(r.id,repeat('A',40),repeat('A',16),repeat('a',64),a);
  select * into other from public.nfse_gravar_assinatura_homologacao(r.id,repeat('B',40),repeat('B',16),repeat('b',64),a);
  if other.dps_xml_sha256<>repeat('a',64) then raise exception 'XML assinado foi sobrescrito'; end if;
  update public.nfse_rascunhos set updated_at=updated_at+interval '1 second' where id=d.id;
  begin
    perform public.nfse_iniciar_envio_homologacao(r.id,a);
    raise exception 'Envio de rascunho alterado foi aceito';
  exception when serialization_failure then null;
  end;
  update public.nfse_rascunhos set updated_at=d.updated_at where id=d.id;
  select * into r from public.nfse_iniciar_envio_homologacao(r.id,a);
  begin
    perform public.nfse_iniciar_envio_homologacao(r.id,a);
    raise exception 'Segundo envio foi aceito';
  exception when serialization_failure then null;
  end;
  select * into r from public.nfse_gravar_retorno_homologacao(r.id,'enviando','pendente_consulta',null,'[]',null,null,null,null,a);
  begin
    perform public.nfse_iniciar_envio_homologacao(r.id,a);
    raise exception 'Reenvio após incerteza foi aceito';
  exception when serialization_failure then null;
  end;
  begin
    perform public.nfse_gravar_retorno_homologacao(r.id,'pendente_consulta','autorizada',200,'[]',null,null,null,null,a);
    raise exception 'Autorização sem XML foi aceita';
  exception when invalid_parameter_value then null;
  end;
  select * into r from public.nfse_gravar_retorno_homologacao(r.id,'pendente_consulta','autorizada',200,'[]',repeat('1',50),repeat('A',40),repeat('A',16),repeat('a',64),a);
  if r.estado<>'autorizada' then raise exception 'Conciliação não finalizou'; end if;
  if (select count(*) from public.nfse_homologacao_eventos where dps_id=r.id)<>5 then
    raise exception 'Auditoria de transições divergente';
  end if;
  if has_table_privilege('anon','public.nfse_homologacao_dps','SELECT')
    or has_table_privilege('authenticated','public.nfse_homologacao_dps','SELECT')
    or has_function_privilege('authenticated','public.nfse_iniciar_envio_homologacao(uuid,uuid)','EXECUTE')
    or has_function_privilege('anon','public.nfse_gravar_assinatura_homologacao(uuid,text,text,text,uuid)','EXECUTE')
    or has_table_privilege('service_role','public.nfse_homologacao_eventos','UPDATE')
    or has_table_privilege('service_role','public.nfse_homologacao_eventos','DELETE') then
    raise exception 'Acesso público indevido';
  end if;
end;
$$;
rollback;
