# W2 Sistema de Faturamento — V2.4.0

## Importação real do W2 TRANSPORTES.xlsx
- Lê a aba CAFS e detecta o cabeçalho automaticamente.
- Exige CAF, AWB, peso e cidade.
- Regra de tipo: AMZC/AMZB/TXAQ = CAIXA; demais = CARTÃO.
- Tarifas: CARTÃO R$ 4,50; CAIXA até 1 kg R$ 13; até 10 kg R$ 18; acima de 10 kg R$ 30.
- Lê APURACAO e compara `Total Pagar` com o total calculado pelo sistema.
- Identifica duplicados dentro do arquivo e AWBs já existentes no Supabase por CAF + AWB.
- Calcula SHA-256 do arquivo para impedir reimportação acidental do mesmo fechamento.
- A confirmação grava primeiro no Supabase; a interface só é atualizada após sucesso no banco.
- O histórico de importações continua persistido no Supabase.

## Segurança / CheckLog
Esta versão não altera `public.perfis`. O Sistema de Faturamento continua usando `public.perfis_faturamento`.

## SQL
Não há migração obrigatória de schema para esta versão; ela utiliza as colunas já existentes em `importacoes` e `entregas`.
