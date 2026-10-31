-- Cenário sintético com rollback; não abre certificado nem transmite.
begin;
do $$
declare a uuid; d public.nfse_rascunhos; old public.nfse_homologacao_dps; fresh public.nfse_homologacao_dps; frozen jsonb;
begin
  select id into a from public.perfis_faturamento where ativo and perfil='administrador' limit 1;
  insert into public.nfse_rascunhos(ano,mes,quinzena,referencia,valor_rem,descricao,criado_por)
    values(2099,2,1,'TESTE-E0714-ROLLBACK',1,'Cenário sintético sem emissão',a) returning * into d;
  update public.nfse_homologacao_config set serie=1,proximo_numero=900000000000010 where cnpj='46167015000140';
  old:=public.nfse_reservar_homologacao(d.id,d.updated_at,a);
  update public.nfse_homologacao_dps set estado='rejeitada',retorno_http=400,erros_codigos='["E0715"]',
    dps_xml_cifrado=repeat('A',40),dps_xml_nonce=repeat('A',16),dps_xml_sha256=repeat('a',64)
    where id=old.id returning * into old;
  insert into public.nfse_homologacao_eventos(dps_id,tipo,estado,autor,created_at)
    values(old.id,'estado','enviando',a,clock_timestamp()-interval '5 minutes');
  begin
    perform public.nfse_nova_tentativa_homologacao(old.id,old.updated_at,d.updated_at,a);
    raise exception 'E0715 liberou retomada';
  exception when serialization_failure then null; end;
  update public.nfse_homologacao_dps set erros_codigos='["E0714","E0715"]' where id=old.id returning * into old;
  begin
    perform public.nfse_nova_tentativa_homologacao(old.id,old.updated_at,d.updated_at,a);
    raise exception 'Códigos mistos liberaram retomada';
  exception when serialization_failure then null; end;
  update public.nfse_homologacao_dps set erros_codigos='["E0714"]',retorno_http=null where id=old.id returning * into old;
  begin
    perform public.nfse_nova_tentativa_homologacao(old.id,old.updated_at,d.updated_at,a);
    raise exception 'HTTP ausente liberou retomada';
  exception when serialization_failure then null; end;
  update public.nfse_homologacao_dps set estado='pendente_consulta',erros_codigos='[]' where id=old.id returning * into old;
  begin
    perform public.nfse_nova_tentativa_homologacao(old.id,old.updated_at,d.updated_at,a);
    raise exception 'Pendência sem HTTP liberou retomada';
  exception when serialization_failure then null; end;
  update public.nfse_homologacao_dps set estado='rejeitada',erros_codigos='["E0714"]',retorno_http=400 where id=old.id returning * into old;
  frozen:=to_jsonb(old);
  fresh:=public.nfse_nova_tentativa_homologacao(old.id,old.updated_at,d.updated_at,a);
  if fresh.id=old.id or fresh.anterior_id<>old.id or fresh.tentativa<>2 or fresh.numero<>old.numero+1
    or fresh.estado<>'reservada' or fresh.dps_xml_cifrado is not null then raise exception 'Retomada inválida'; end if;
  if (select to_jsonb(x) from public.nfse_homologacao_dps x where id=old.id)<>frozen then raise exception 'DPS rejeitada foi modificada'; end if;
end $$;
rollback;
