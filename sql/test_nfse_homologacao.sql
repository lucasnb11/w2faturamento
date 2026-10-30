-- Teste transacional: nenhum rascunho, reserva ou evento é mantido.
begin;
set local role service_role;
do $$
declare
  v_autor uuid;
  v_rascunho public.nfse_rascunhos;
  v_primeira public.nfse_homologacao_dps;
  v_segunda public.nfse_homologacao_dps;
  v_numero bigint;
begin
  select id into v_autor from public.perfis_faturamento where ativo=true and perfil='administrador' limit 1;
  if v_autor is null then raise exception 'Teste exige administrador ativo'; end if;
  insert into public.nfse_rascunhos(ano,mes,quinzena,referencia,valor_rem,descricao,criado_por)
  values (2020,1,1,'TESTE-TRANSACIONAL',1,'TESTE COM ROLLBACK; SEM EMISSAO',v_autor)
  returning * into v_rascunho;
  begin
    perform public.nfse_reservar_homologacao(v_rascunho.id,v_rascunho.updated_at,v_autor);
    raise exception 'Falha: série vazia foi aceita';
  exception when invalid_parameter_value then null;
  end;
  update public.nfse_homologacao_config set serie=1,proximo_numero=1 where cnpj='46167015000140';
  select * into v_primeira from public.nfse_reservar_homologacao(v_rascunho.id,v_rascunho.updated_at,v_autor);
  select * into v_segunda from public.nfse_reservar_homologacao(v_rascunho.id,v_rascunho.updated_at,v_autor);
  select proximo_numero into v_numero from public.nfse_homologacao_config where cnpj='46167015000140';
  if v_primeira.id <> v_segunda.id or v_numero <> 2 or v_primeira.numero <> 1 then
    raise exception 'Falha na reserva idempotente';
  end if;
  begin
    perform public.nfse_reservar_homologacao(v_rascunho.id,v_rascunho.updated_at-interval '1 second',v_autor);
    raise exception 'Falha: versão desatualizada foi aceita';
  exception when serialization_failure then null;
  end;
  begin
    perform public.nfse_mudar_estado_homologacao(v_primeira.id,'reservada','enviando',v_autor);
    raise exception 'Falha: salto de estado foi aceito';
  exception when invalid_parameter_value then null;
  end;
  perform public.nfse_mudar_estado_homologacao(v_primeira.id,'reservada','assinada',v_autor);
  begin
    perform public.nfse_mudar_estado_homologacao(v_primeira.id,'reservada','assinada',v_autor);
    raise exception 'Falha: comparação de estado não funcionou';
  exception when serialization_failure then null;
  end;
  perform public.nfse_mudar_estado_homologacao(v_primeira.id,'assinada','enviando',v_autor);
  perform public.nfse_mudar_estado_homologacao(v_primeira.id,'enviando','pendente_consulta',v_autor);
  begin
    perform public.nfse_mudar_estado_homologacao(v_primeira.id,'pendente_consulta','assinada',v_autor);
    raise exception 'Falha: reenvio após resultado incerto foi aceito';
  exception when invalid_parameter_value then null;
  end;
end;
$$;
rollback;
