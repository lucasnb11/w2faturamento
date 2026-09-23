# W2 Sistema de Faturamento V2.2.1

## Objetivo
Isolar completamente as permissões do Sistema de Faturamento das permissões do W2 CheckLog.

## Importante
- O Faturamento usa `public.perfis_faturamento`.
- O W2 CheckLog continua usando `public.perfis` sem alterações desta versão.
- Não altere a constraint `perfis_perfil_check` do CheckLog para configurar o Faturamento.

## Instalação
1. No Supabase SQL Editor, execute apenas `supabase_schema_v2_2_1.sql` para esta atualização.
2. Promova o seu usuário na tabela exclusiva do Faturamento:

```sql
update public.perfis_faturamento
set perfil='administrador', ativo=true, updated_at=now()
where lower(email)=lower('lucas.barros@w2transportes.com.br');
```

3. Confira:

```sql
select email,nome,perfil,ativo
from public.perfis_faturamento
where lower(email)=lower('lucas.barros@w2transportes.com.br');
```

4. Publique todos os arquivos da V2.2.1 no Vercel.
5. Faça logout/login novamente.

## Perfis do Faturamento
- administrador: acesso total
- financeiro: Dashboard, Faturamento, Pagamentos e Importações
- operador: Dashboard, CAFs e Cidades
