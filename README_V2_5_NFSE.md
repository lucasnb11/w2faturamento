# W2 Sistema de Faturamento — V2.5.0

## Área Notas fiscais

- Integrada ao menu do Sistema de Faturamento V2.4.5.
- Visível aos perfis `administrador` e `financeiro`; indisponível para `operador`.
- Uma cobrança por tomador e quinzena, com valor REM informado pela Total Express.
- Exibe em separado o cálculo estimado por AWB importado para conferência; não o usa automaticamente como valor da nota.
- Registra referência da quinzena, código informado pelo contratante, descrição, CT-e existente e observação.
- Salva, edita e exclui rascunhos no mesmo Supabase do Faturamento.
- Botão para carregar como rascunho os oito valores recebidos de maio a agosto de 2026, totalizando R$ 170.707,00. A operação não duplica quinzenas já cadastradas.
- Botão **Emitir NFS de teste** exibe e permite imprimir uma prévia claramente marcada **SEM VALIDADE FISCAL**.

## Instalação

1. Execute `supabase_schema_v2_5_nfse.sql` no SQL Editor do projeto Supabase usado pelo Faturamento. Ele cria a tabela de rascunhos e restringe o acesso aos perfis financeiro e administrador.
2. Publique todos os arquivos desta pasta juntos na instalação atual do Sistema de Faturamento, incluindo `nfse.js`, `index.html`, `app.js`, `style.css` e `supabase.js`.
3. Entre com um usuário financeiro ou administrador e abra **Notas fiscais**. O perfil operador não verá a aba.

O SQL da V2.5 deve ser executado uma vez. Sem ele, a área mostra uma mensagem de erro e o restante do sistema continua operando.

## Limite fiscal

Esta versão **não transmite nem emite NFS-e**, inclusive em ambiente de homologação. O código `SE00041` foi fornecido pela Total Express e é armazenado como referência do contratante, sem presunção de que seja o código tributário da NFS-e. A descrição e o enquadramento precisam de validação contábil. O CT-e de R$ 50.220,00 referente à 2ª quinzena de maio já foi emitido e deve ser tratado antes de qualquer emissão fiscal para a mesma cobrança.
