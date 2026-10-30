# Preparação da DPS de homologação · 2.10.0

Após o diagnóstico 2.9.2, o administrador confirmou HTTP 200 na documentação da Sefin, na documentação de Parametrização do ADN e na consulta do convênio de Ananindeua. Esses retornos não confirmam a habilitação individual da W2.

## Operações disponíveis

- **Verificar preparação da DPS:** leitura administrativa da configuração de numeração e da existência de rascunho W2/Total Express. Mostra a série, o próximo número e as pendências, sem reservar números ou devolver os dados fiscais do rascunho.
- **Testar conexão nacional:** além das consultas existentes, executa assinatura RSA-SHA256 e verificação sobre desafio aleatório de 32 bytes em memória, com a chave do A1 e a chave pública correspondente. Não assina XML/DPS; não verifica cadeia ICP-Brasil, revogação, perfil XMLDSig aceito ou habilitação fiscal. Não retorna desafio, assinatura ou certificado.
- **Componente interno `build_reserved_dps`:** monta XML a partir do snapshot da reserva obtida pelo servidor. Confere emitente, versão, série, número, estado e identificador; aplica as validações fiscais e XSD oficiais existentes. Não busca uma versão nova do rascunho, não altera o snapshot e não reconstrói estados assinada/enviando/pendente_consulta/autorizada/rejeitada. Ainda não está ligado a uma rota de reserva, assinatura ou envio.

O GET de preparação exige o administrador ativo validado no banco. Consulta somente as tabelas já existentes, com colunas e filtros fixos. Não há nova migração, alteração de grants ou política RLS.

## Série do aplicativo

Fonte: [documentação oficial de homologação](https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/producao-restrita), anexo `ANEXO_I-SEFIN_ADN-DPS_NFSe-SNNFSe-PRODREST-v1.01-20261020`, regra E0010. Ela delimita aplicativo próprio em 00001–49999. O campo de leiaute menciona 0–49999; a preparação usa a interseção mais restrita, 1–49999. A série web 70000 não deve ser copiada para esta integração.

O SQL inicial 2.9 admite 0–89999 para comportar as faixas gerais do leiaute. O componente de preparação e a consulta de situação rejeitam valores fora de 1–49999 para o aplicativo. Antes de disponibilizar uma rota de reserva será necessário aplicar essa restrição também à função SQL, com teste transacional. A versão atual não oferece configuração ou reserva pela tela.

Consulta de situação feita em 30/10/2026: série nula, próximo número 1, zero rascunhos e zero reservas. Nenhum dado foi escrito nessa consulta. Não se assume que o número 1 esteja livre em outros emissores.

## Pendências para a primeira transmissão

1. Definir uma série e próximo número livres em homologação, verificando eventual uso por outro aplicativo.
2. Escolher e salvar o rascunho de homologação com os dados e confirmações fiscais necessários. Não recriar automaticamente as notas históricas já emitidas.
3. Confirmar o perfil XMLDSig aceito na recepção, sem inferi-lo da assinatura externa da NFS-e de exemplo. Conectar reserva atômica, montagem, assinatura e armazenamento protegido.
4. Implementar recepção e conciliação por identificador da DPS, conferir o XML autorizado e homologar o fluxo completo antes de liberar emissão de produção.

## Validação

61 testes Python e dois conjuntos de testes JavaScript aprovados. Incluem montagem com snapshot e ID reservados, XSD oficial, bloqueio de série web e versões divergentes, ausência de mutação, desafio aleatório novo, chave incompatível, leitura sem escrita e restrição administrativa. Os testes usam A1 sintético; o novo teste com o A1 real será executado pelo administrador após publicação.

Nenhuma DPS foi assinada com o A1 real ou transmitida nesta entrega. A emissão oficial permanece indisponível.
