# Explicação Profunda — Lógica e Calculo de "Parâmetros" e "Compras"

## Camada 1 — Parâmetros dos Itens (estoque_mínimo e estoque_ideal)

Todo item no sistema tem dois parâmetros que definem seus **limites operacionais**:

- `estoque_minimo` — o nível de alerta. Quando o estoque cai até aqui (ou abaixo), o sistema considera que o item precisa ser reposto.
- `estoque_ideal` — o nível alvo de reposição. Quando o sistema sugere compra, ele sugere comprar até atingir esse número.

Esses dois valores são o insumo principal de toda decisão de compra. Se estiverem errados, tudo que vem depois fica errado também.

### Estrutura de campos no banco (modelo Item)

O sistema guarda quatro versões desses valores por item, não apenas uma:

| Campo | O que é | 
| --- | --- | 
| `estoque_minimo_sugerido` | Calculado automaticamente pelo motor de revisão mensal | 
| `estoque_ideal_sugerido` | Calculado automaticamente pelo motor de revisão mensal | 
| `estoque_minimo_manual` | Definido manualmente pelo usuário (override) | 
| `estoque_ideal_manual` | Definido manualmente pelo usuário (override) | 
| `estoque_minimo_vigente` | O que o sistema usa de fato em todos os cálculos | 
| `estoque_ideal_vigente` | O que o sistema usa de fato em todos os cálculos | 
| `origem_minimo` | "Manual" ou "Automático" — de onde veio o vigente | 

A lógica de prioridade do vigente é simples:

```
vigente = manual SE manual estiver definido, SENÃO sugerido automático
```

Ou seja: o automático sempre é calculado e fica salvo, mas só vira vigente se não houver manual sobrescrevendo.

### Como o cálculo automático funciona (fundo total)

Onde: `core/calculos.py` — função `calcular_revisao_item()`
Quando roda: Automaticamente na primeira abertura do sistema em cada mês (`app.py`). Não precisa de botão; roda uma vez por mês por mês-calendário.

1. **Define a janela de análise**

```
data_ref = 1º do mês corrente
janela = últimos 3 meses fechados (não inclui o mês atual)
```

Exemplo em Junho/2026:
- Início: 01/03/2026
- Fim: 31/05/2026

Para itens novos (primeira movimentação depois do início da janela padrão), a janela se encurta para cobrir só o histórico disponível, e o resultado recebe status `historico_recente`.

2. **Coleta as movimentações da janela**

Busca no banco todas as `Movimentacao` do item no período, separando em:
- Saídas — consumo real (retiradas do estoque)
- Entradas — reposições (compras recebidas)

3. **Calcula consumo diário por mês**

Para cada mês dentro da janela:

```
consumo_diário_do_mês = total_de_saídas_do_mês / dias_efetivos_do_mês
```

"Dias efetivos" é importante: para meses parciais (item cadastrado no meio do mês), usa só os dias reais dentro da janela — evita subestimar o consumo.

Resultado: uma lista com 1 a 3 valores de consumo diário (um por mês).

4. **Extrai métricas estatísticas**

Das saídas:
- Consumo Mediana (P50) — consumo diário do mês "típico"
- Consumo P75 — consumo diário de um mês "mais pesado" (cobre variação)

Das entradas (intervalos entre reposições consecutivas):
- Intervalo Mediano (P50) — tempo típico entre uma compra e a próxima (em dias)
- Intervalo P90 — tempo máximo esperado entre compras (cobre atrasos)

5. **Calcula mínimo e ideal**

```
mínimo_sugerido = ⌈ consumo_P75 × intervalo_mediano ⌉
```

**Interpretação:** "Quanto eu consumo num ciclo de reposição, no pior cenário razoável." É o estoque de segurança — quando chegar aqui, a próxima compra já precisa estar sendo processada.

```
ideal_sugerido = ⌈ mínimo + (consumo_mediana × intervalo_mediano) ⌉
```

**Interpretação:** "O mínimo de segurança, mais o consumo típico de um ciclo inteiro." É o quanto devo ter depois de repor.

Verificação de piso do ideal:

```
saída_típica_do_ciclo = mediana_mensal_de_saídas × (intervalo_mediano / 30,44)
SE ideal < mínimo + saída_típica_do_ciclo:
    ideal = mínimo + saída_típica_do_ciclo
```

Isso garante que o ideal nunca seja menor que consegue sustentar um ciclo de consumo típico, especialmente em itens com reposição muito frequente.

6. **Avalia confiabilidade**

| Status | Quando ocorre | 
| --- | --- | 
| ok | 2+ meses com saídas, tem entradas, consumo estável | 
| historico_recente | Item tem menos de 3 meses de história | 
| historico_insuficiente | Sem nenhuma movimentação | 
| sem_consumo_recente | Tem entradas mas sem saídas na janela | 
| sem_entradas_recentes | Tem saídas mas sem entradas na janela | 
| irregular | P75 > 3× mediana (consumo muito instável) | 

Se `historico_insuficiente`: nenhum valor é sugerido, campos ficam null.

7. **Salva e atualiza vigentes**

- Sempre grava um registro RevisaoMensal com todas as métricas e o status de confiabilidade (histórico auditável)
- Atualiza estoque_minimo_sugerido / estoque_ideal_sugerido no item
- Só atualiza o vigente se não houver manual definido:

```
if item.estoque_minimo_manual is None:
    item.estoque_minimo_vigente = resultado.minimo_sugerido or 0
```

> **Nota sobre fuso horário:** a janela de análise e os timestamps das movimentações
> operam em hora local de Brasília (`core/tempo.py`). Registros gravados em UTC antes
> de jun/2026 foram convertidos por migração única — sem isso, movimentações próximas
> da meia-noite caíam no dia/mês errado e distorciam o consumo calculado.

### Override manual

O usuário pode entrar no cadastro de um item e definir manualmente mínimo e ideal. Quando faz isso:

- estoque_minimo_manual e estoque_ideal_manual são gravados
- estoque_minimo_vigente passa a ser o manual imediatamente
- origem_minimo muda para "Manual"
- O cálculo automático continua rodando toda revisão, mas não sobrescreve o vigente

Para remover o manual e voltar ao automático, existe remover_manual() — que copia o sugerido automático de volta ao vigente.

---

## Camada 2 — Status de Reposição e Quantidade Sugerida

O motor (StockAnalyzer)

Onde: `core/engine.py`

O motor recebe um item com seus parâmetros e retorna: status + quantidade a comprar + valor estimado. É stateless — não acessa banco, não tem memória de execuções anteriores, só recebe dados e calcula.

Existem 3 variantes do motor, usadas em contextos diferentes:

### Variante A — calcular_status_puro → Painel de Reposição

Onde é usada: Aba "Painel de Reposição" na página de Compras
Pergunta que responde: "Como está o estoque agora, sem considerar nada mais?"

```
Entrada: estoque_atual, estoque_mínimo_vigente, estoque_ideal_vigente
```

Tabela de decisão em ordem de avaliação:

```
1. estoque_atual == 0
   → status: ZERADO
   → qtd_recomendar: max(0, ideal - atual)       ← compra total para repor ao ideal

2. mínimo == 0 OU ideal == 0   (parâmetros não definidos)
   → status: SEM_PARAMETRO
   → qtd_recomendar: 0                           ← não sabe quanto sugerir

3. atual > ideal
   → status: EXCESSO
   → qtd_recomendar: 0                           ← está acima do ideal, não compra

4. atual > mínimo
   → status: OK
   → qtd_recomendar: 0                           ← dentro da zona segura, não compra

5. atual <= mínimo   (condição residual)
   → status: ABAIXO_MINIMO
   → qtd_recomendar: max(0, ideal - atual)       ← compra até o ideal
```

Importante: a condição atual > mínimo não inclui == mínimo. Quando atual == mínimo, cai no caso 5 (ABAIXO_MINIMO) e entra na lista de compra. Isso é intencional — mínimo é o piso de segurança, não é seguro ficar exatamente nele.

### Variante B — calcular_status_consolidado → Análise de Compras do Período

Onde é usada: Aba "Lista de Compras" na página de Compras, ao clicar em "Analisar Período"
Pergunta que responde: "Se eu atender todas as solicitações aprovadas deste período, como fica o estoque? O que preciso comprar para cobrir isso tudo?"

```
Entrada: estoque_atual, mínimo, ideal + lista de solicitações aprovadas do período
```

Fórmula central:

```
total_solicitado = soma das quantidades de todas solicitações aprovadas do item no período
saldo = estoque_atual - total_solicitado
```

O saldo representa o estoque projetado após atender todo mundo que pediu. A decisão de compra é feita sobre esse saldo, não sobre o estoque atual:

```
1. estoque_atual == 0   (zerado de verdade, antes mesmo de atender)
   → status: ZERADO
   → qtd_recomendar: max(0, ideal - saldo)       ← pode ser > que o usual

2. mínimo == 0 OU ideal == 0
   → status: SEM_PARAMETRO
   → qtd_recomendar: 0

3. estoque_atual > ideal   (excesso no físico)
   → status: EXCESSO
   → qtd_recomendar: 0

4. saldo <= mínimo   ← chave! usa saldo, não atual
   → status: ABAIXO_MINIMO
   → qtd_recomendar: max(0, ideal - saldo)

5. saldo > mínimo
   → status: OK
   → qtd_recomendar: 0
```

Exemplo concreto:

```
Item X: atual=50, mínimo=20, ideal=80. Solicitações aprovadas: 40 unidades.
saldo = 50 - 40 = 10
saldo(10) <= mínimo(20) → ABAIXO_MINIMO
qtd_recomendar = max(0, 80 - 10) = 70
```

- Sem as solicitações: atual(50) > mínimo(20) → o painel diria OK, não compraria.
- Com as solicitações: o sistema já vê que vai precisar de 70 unidades.

### Variante C — calcular_status (legada)

Onde é usada: run_analysis() que alimenta Orçamentos (aba Orçamentos)

Lógica mais simples, sem o gradiente de status puro:

```
atual == 0 e tem parâmetros → ZERADO
ambos == 0                  → SEM_MINIMO (legado)
atual <= mínimo             → COMPRAR
demais                      → OK
```

Não distingue ABAIXO_MINIMO de EXCESSO. É mantida para não quebrar o fluxo de Orçamentos que depende dos status "comprar" e "zerado".

**Cálculo do valor estimado**

Em qualquer variante, se qtd_recomendar > 0 e há cotação válida:

```
valor_estimado = round(preco_unitario × quantidade_recomendar, 2)
```

O preco_unitario vem de get_best_price() — que já selecionou o melhor fornecedor seguindo a hierarquia: preferencial válido > menor preço válido.

Se não há cotação válida: valor_estimado = None, tem_preco = False.

---

## Fluxo Real de Trabalho — E2E

**Ciclo mensal completo**

━━━ INÍCIO DO MÊS (automático) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[1] Revisão Mensal Automática  ← dispara na 1ª abertura do app no mês
    app.py → executar_revisao_mensal()
    - Calcula mínimo/ideal sugerido para todos os itens ativos
    - Atualiza vigentes (onde não há manual)
    - Grava histórico em revisoes_mensais

━━━ DURANTE O MÊS (operacional) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[2] Movimentações de Estoque
    Página Estoque → entradas / saídas do dia a dia
    - Alteram estoque_atual do item

[3] Painel de Reposição (tempo real, sem clique)
    Página Compras → Aba "Painel de Reposição"
    - Motor calcular_status_puro roda em memória
    - Sempre reflete o estoque atual naquele momento
    - Mostra: ZERADO / ABAIXO_MINIMO / OK / EXCESSO / SEM_PARAMETRO

[4] Solicitações de Materiais
    Setores enviam formulário externo (Google Forms)
    → registradas como status "pendente"

━━━ FECHAMENTO DO PERÍODO (decisão) ━━━━━━━━━━━━━━━━━━━━━━━━

[5] Triagem das Solicitações
    Página Compras → Aba "Solicitações"
    - Classificar → muda pendentes para: validada / novo_item / sem_parametros
    - Aprovar individualmente: validada → aprovada
    - Rejeitar: qualquer → rejeitada

[6] Análise do Período (botão "Analisar Período")
    - Motor calcular_status_consolidado roda
    - Cruza estoque atual × solicitações aprovadas
    - Gera/atualiza ItemListaCompra para o período

[7] Revisão da Lista de Compras
    Página Compras → Aba "Lista de Compras"
    - Mostra todos os itens com status e quantidade sugerida
    - Responsável pode: aprovar qtd sugerida / ajustar quantidade / incluir ou excluir
    - Quando ajusta qtd: motivo é obrigatório se diferir do sugerido

[8] Lista Final → Orçamento
    Página Compras → Aba "Lista Final"
    - Apenas itens com incluir_na_lista_final = True
    - Página Orçamentos consolida por fornecedor com totais
    - Pode gerar documento DOCX

---

## Cenários e Casos de Uso

**Cenário 1 — Item com histórico estável (status: ok)**

```
Papel A4: 3 meses de saídas regulares ~10 resmas/mês, reposições a cada ~30 dias.

Consumo P75: 0,38/dia → Mínimo sugerido: ⌈0,38 × 30⌉ = 12
Consumo mediana: 0,33/dia → Ideal: ⌈12 + (0,33 × 30)⌉ = 22
Estoque atual: 18 → 18 > mínimo(12) e 18 < ideal(22) → OK, qtd = 0
Se 2 setores pedem 10 resmas: saldo = 8 → 8 <= mínimo(12) → ABAIXO_MINIMO, qtd = 14
```

**Cenário 2 — Item novo (menos de 3 meses de histórico)**

```
Caneta azul, cadastrada há 6 semanas.

Janela encurtada para cobrir só as 6 semanas disponíveis
status_confiabilidade: historico_recente
Mínimo/ideal calculados com menos dados → valores menos precisos
Sugestão é exibida, mas com badge de confiabilidade para o usuário saber que é parcial
```

**Cenário 3 — Item sem entradas recentes**

```
Material de limpeza específico, sem reposição nos últimos 3 meses mas com saídas.

status_confiabilidade: sem_entradas_recentes
intervalo_mediano = None → não há ciclo de reposição calculável
mínimo_sugerido = None, ideal_sugerido = None
Vigente = 0 (ou o manual se houver)
Motor classifica como SEM_PARAMETRO → não entra na lista de compras automaticamente
```

**Cenário 4 — Override manual necessário**

```
Item sazonal: no período analisado foi mês de baixo uso. O automático calculou mínimo=3, ideal=8. Mas o gestor sabe que no mês de pico precisa de 20.

Usuário entra no cadastro do item → define mínimo=10, ideal=25 manualmente
origem_minimo = "Manual", vigente passa a usar os valores definidos
No próximo mês o automático calcula novo sugerido, mas não sobrescreve
Usuário pode remover o manual quando quiser voltar ao automático
```

**Cenário 5 — Item em excesso**

```
Toner importado comprado em grande quantidade no mês passado.

estoque_atual(80) > ideal_vigente(30) → EXCESSO, qtd = 0
Mesmo que um setor solicite 5 unidades: saldo = 75 → ainda > ideal → EXCESSO
Não entra na lista de compras do período
```

---

## Resumo das Fórmulas Centrais

━━━ Parâmetros automáticos (core/calculos.py) ━━━━━━━━━━━

mínimo_sugerido = ⌈ consumo_P75_diário × intervalo_mediano_dias ⌉
ideal_sugerido  = ⌈ mínimo + (consumo_mediana_diário × intervalo_mediano_dias) ⌉
ideal_sugerido  = max(ideal, mínimo + saída_típica_do_ciclo)   ← piso

━━━ Quantidade sugerida para compra (core/engine.py) ━━━━

qtd_recomendar = max(0, ideal_vigente - estoque_atual)         ← modo puro
qtd_recomendar = max(0, ideal_vigente - saldo_pós_solicitações) ← modo consolidado

saldo = estoque_atual - total_solicitado_no_período

━━━ Valor estimado ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

valor_estimado = melhor_preço_unitário × qtd_recomendar

