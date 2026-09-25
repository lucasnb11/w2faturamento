W2 Dashboard CAF V1.5.3 — Normalização de Cidades

Alterações:
- Cidades são normalizadas na carga inicial e em toda nova importação.
- Comparação ignora maiúsculas/minúsculas, acentos e espaços extras.
- Nomes conhecidos são exibidos em padrão único com acentuação correta.
- Evita duplicidades como Breves/BREVES, Gurupá/GURUPA e Oeiras do Pará/OEIRAS DO PARA.
- Regras especiais de pagamento de R$ 8,00/AWB continuam válidas para Limoeiro do Ajuru, Salvaterra e Soure independentemente da grafia de origem.
- Histórico de pagamentos existente também é normalizado em memória ao carregar o sistema.
