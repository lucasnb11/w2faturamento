-- Teste isolado com rollback; não consome numeração nem transmite.
begin;
do $$
declare a uuid; d public.nfse_rascunhos; old public.nfse_homologacao_dps; fresh public.nfse_homologacao_dps; again public.nfse_homologacao_dps; frozen jsonb; before_number bigint;
begin
  select id into a from public.perfis_faturamento where ativo and perfil='administrador' limit 1;
  if a is null then raise exception 'Administrador de teste necessário'; end if;
  insert into public.nfse_rascunhos(ano,mes,quinzena,referencia,valor_rem,descricao,criado_por)
    values(2099,1,1,'TESTE-TENTATIVAS-ROLLBACK',1,'Cenário sintético sem emissão',a) returning * into d;
  update public.nfse_homologacao_config set serie=1,proximo_numero=900000000000000 where cnpj='46167015000140';
  old:=public.nfse_reservar_homologacao(d.id,d.updated_at,a);
  update public.nfse_homologacao_dps set estado='pendente_consulta',retorno_http=400,
    dps_xml_cifrado=repeat('A',40),dps_xml_nonce=repeat('A',16),dps_xml_sha256=repeat('a',64)
    where id=old.id returning * into old;
  begin
    perform public.nfse_nova_tentativa_homologacao(old.id,old.updated_at,d.updated_at,a);
    raise exception 'HTTP 400 liberou nova tentativa';
  exception when serialization_failure then null; end;
  update public.nfse_homologacao_dps set retorno_http=404 where id=old.id returning * into old;
  begin
    perform public.nfse_nova_tentativa_homologacao(old.id,old.updated_at,d.updated_at,a);
    raise exception 'Ausência de envio liberou nova tentativa';
  exception when serialization_failure then null; end;
  insert into public.nfse_homologacao_eventos(dps_id,tipo,estado,autor,created_at)
    values(old.id,'estado','enviando',a,clock_timestamp());
  begin
    perform public.nfse_nova_tentativa_homologacao(old.id,old.updated_at,d.updated_at,a);
    raise exception 'Envio recente liberou nova tentativa';
  exception when serialization_failure then null; end;
  -- Relógio sintético no ambiente transacional de teste, nunca em dados reais.
  update public.nfse_homologacao_eventos set created_at=clock_timestamp()-interval '5 minutes' where dps_id=old.id and estado='enviando';
  begin
    perform public.nfse_nova_tentativa_homologacao(old.id,old.updated_at,d.updated_at+interval '1 second',a);
    raise exception 'Versão incorreta foi aceita';
  exception when serialization_failure then null; end;
  frozen:=to_jsonb(old);
  fresh:=public.nfse_nova_tentativa_homologacao(old.id,old.updated_at,d.updated_at,a);
  if fresh.id=old.id or fresh.dps_id=old.dps_id or fresh.tentativa<>2 or fresh.anterior_id<>old.id
    or fresh.numero<>old.numero+1 or fresh.estado<>'reservada' or fresh.dps_xml_cifrado is not null
    or fresh.snapshot<>old.snapshot then raise exception 'Nova tentativa incorreta'; end if;
  if (select to_jsonb(x) from public.nfse_homologacao_dps x where id=old.id)<>frozen then raise exception 'DPS antiga alterada'; end if;
  select proximo_numero into before_number from public.nfse_homologacao_config where cnpj='46167015000140';
  begin
    perform public.nfse_nova_tentativa_homologacao(old.id,old.updated_at,d.updated_at,a);
    raise exception 'Dupla criação foi aceita';
  exception when serialization_failure then null; end;
  again:=public.nfse_reservar_homologacao(d.id,d.updated_at,a);
  if again.id<>fresh.id or (select proximo_numero from public.nfse_homologacao_config where cnpj='46167015000140')<>before_number then raise exception 'Reserva não idempotente'; end if;
  if not exists(select 1 from public.nfse_homologacao_eventos where dps_id=old.id and detalhes->>'http'='404') then raise exception 'Consulta não auditada'; end if;
  begin
    perform public.nfse_nova_tentativa_homologacao(fresh.id,fresh.updated_at,d.updated_at,'00000000-0000-0000-0000-000000000000');
    raise exception 'Não administrador foi aceito';
  exception when insufficient_privilege then null; end;
  if has_function_privilege('anon','public.nfse_nova_tentativa_homologacao(uuid,timestamptz,timestamptz,uuid)','execute')
    or has_function_privilege('authenticated','public.nfse_nova_tentativa_homologacao(uuid,timestamptz,timestamptz,uuid)','execute')
    or has_table_privilege('service_role','public.nfse_homologacao_eventos','update') then raise exception 'Grants indevidos'; end if;
end $$;
rollback;
