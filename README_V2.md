# Sistema de Faturamento W2 — V2.0

## Regras implementadas
- AWB iniciado por AMZC, AMZB ou TXAQ = CAIXA.
- Qualquer outro prefixo = CARTÃO.
- CARTÃO = R$ 4,50.
- CAIXA até 1 kg = PEQUENO = R$ 13,00.
- CAIXA acima de 1 kg até 10 kg = MÉDIO = R$ 18,00.
- CAIXA acima de 10 kg = GRANDE = R$ 30,00.
- Repasse ao entregador: R$ 5,00 por AWB; Limoeiro do Ajuru, Salvaterra e Soure = R$ 8,00 por AWB.

## Parser Excel
A V2 prioriza a aba `CAFS` (e mantém compatibilidade com `CAF_Consolidado`).
Colunas obrigatórias: `cafid1`, `awb1`, `peso`, `cidade`.
A aba `APURACAO`, quando presente, é lida a partir da linha 2 e o campo `Total Pagar` é usado para auditoria do total oficial.
Duplicidade: `CAF + AWB`.

## Persistência atual
A V2 entregue neste pacote funciona imediatamente sem backend: importações adicionais e pagamentos são persistidos no `localStorage` do navegador.
O arquivo `supabase_schema_v2.sql` contém o banco da próxima etapa de persistência centralizada/multiusuário.

## Automação Outlook
Fluxo recomendado em produção:
Outlook -> Power Automate/Microsoft Graph -> endpoint/Edge Function -> parser -> Supabase.
O endpoint deve aceitar somente anexos `.xlsx/.xls`, ignorar anexos inline e registrar `email_message_id` para idempotência.

## Publicação
Pode ser publicado no Vercel como site estático, como a versão anterior.
