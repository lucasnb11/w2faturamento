-- W2 Faturamento: corrigir grafias históricas das cidades.
-- Execute uma vez no SQL Editor do mesmo projeto Supabase do sistema.
-- Não exclui CAFs, AWBs, pagamentos nem altera seus valores.

begin;

create temp table w2_city_names on commit drop as
select distinct btrim(regexp_replace(cidade, '[[:space:]]+', ' ', 'g')) as nome
from (
  select cidade from public.entregas
  union all
  select cidade from public.pagamentos_entregadores
) cidades
where cidade is not null and btrim(cidade) <> '';

create temp table w2_city_map on commit drop as
with candidates as (
  select nome,
    translate(lower(nome), 'áàâãäéèêëíìîïóòôõöúùûüç', 'aaaaaeeeeiiiiooooouuuuc') as chave,
    char_length(lower(nome)) - char_length(translate(lower(nome), 'áàâãäéèêëíìîïóòôõöúùûüç', '')) as acentos
  from w2_city_names
), preferred as (
  select chave, nome,
    row_number() over (partition by chave order by acentos desc, (nome = initcap(lower(nome))) desc, nome) as posicao
  from candidates
)
select chave,
  replace(replace(replace(replace(replace(replace(
    initcap(lower(nome)),
    ' De ', ' de '), ' Da ', ' da '), ' Do ', ' do '),
    ' Das ', ' das '), ' Dos ', ' dos '), ' E ', ' e ') as nome_padrao
from preferred
where posicao = 1;

-- Mapeamento das grafias escolhidas (mesma transação da atualização).
select chave, nome_padrao from w2_city_map order by nome_padrao;

update public.entregas e
set cidade = m.nome_padrao
from w2_city_map m
where translate(lower(btrim(regexp_replace(e.cidade, '[[:space:]]+', ' ', 'g'))),
  'áàâãäéèêëíìîïóòôõöúùûüç', 'aaaaaeeeeiiiiooooouuuuc') = m.chave
  and e.cidade is distinct from m.nome_padrao;

update public.pagamentos_entregadores p
set cidade = m.nome_padrao
from w2_city_map m
where translate(lower(btrim(regexp_replace(p.cidade, '[[:space:]]+', ' ', 'g'))),
  'áàâãäéèêëíìîïóòôõöúùûüç', 'aaaaaeeeeiiiiooooouuuuc') = m.chave
  and p.cidade is distinct from m.nome_padrao;

-- Conferência: cada variante agora aponta para um nome único.
select cidade, count(*) as awbs
from public.entregas
where cidade is not null
group by cidade
order by cidade;

commit;
