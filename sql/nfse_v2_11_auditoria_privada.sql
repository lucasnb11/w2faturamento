-- Supabase pode conceder ALL ao service_role por privilégios padrão.
-- Um GRANT mais restrito não remove permissões já existentes.
revoke all on public.nfse_homologacao_config,public.nfse_homologacao_dps,public.nfse_homologacao_eventos from service_role;
grant select,insert,update on public.nfse_homologacao_config,public.nfse_homologacao_dps to service_role;
grant select,insert on public.nfse_homologacao_eventos to service_role;
revoke all on sequence public.nfse_homologacao_eventos_id_seq from service_role;
grant usage,select on sequence public.nfse_homologacao_eventos_id_seq to service_role;
