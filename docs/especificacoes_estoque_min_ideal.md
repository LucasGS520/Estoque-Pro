# Especificações e Regras para Consolidação Cálculo Automático de Estoque Mínimo e Ideal

## Modelo de Revisão Mensal com Janela Móvel

---

## 1. Resumo Executivo

O sistema **não depende** de inserção manual de `estoque_minimo` e `estoque_ideal`, nem de lead times estimados ou margens de segurança arbitrárias.

**Em vez disso, funciona assim:**

1. **Durante o mês**: entradas aumentam estoque, saídas reduzem estoque, sistema opera normalmente
2. **No 1º dia do mês**: sistema revisa os últimos 3 meses de movimentação
3. **Calcula automaticamente**: consumo médio, variação, intervalo entre entradas, estoque mínimo e ideal sugeridos
4. **Aplicação inteligente**:
   - Se possui apenas os valores automáticos → valores são atualizados imediatamente
   - Se existe valores manuais → sugestão fica em paralelo, mostrando comparação
5. **Registro de origem**: sempre claro se o valor é automático ou manual

---

## 2. Conceitos Fundamentais

### 2.1 Fim do Modelo de Ciclos Fechados

**Antes (descartado)**:
```text
Entrada A → Define início de ciclo
Entrada B → Fecha ciclo anterior
Saídas dentro ciclo → Calculam consumo
```

**Agora (novo modelo)**:
```text
Entradas e saídas → Compõem histórico contínuo
1º do mês → Sistema examina janela móvel de 3 meses
Cálculo → Baseado em padrões observados, não em marcos de fechamento
```

**Por que?** Reduz complexidade, evita distorções de datas de entrada, torna o sistema mais resiliente a registros atrasados ou errados.

---

### 2.2 Janela Móvel de 3 Meses

A análise sempre usa os **últimos 3 meses fechados** como base.

**Exemplo (revisão em 01/06/2026)**:
```text
Janela analisada: 01/03/2026 a 31/05/2026
O mês 06 está aberto, não entra na análise
```

**Por que 3 meses?**
- Suficiente para identificar padrões reais
- Não tão longo que perda sazonalidade recente
- Não tão curto que sofra com meses atípicos

---

### 2.3 Papel da Entrada (Revisado)

A entrada **não fecha ciclo**, mas alimenta informações sobre reposição:

**Pergunta que responde**:
- Com que frequência esse item é reabastecido?
- As entradas são regulares ou irregulares?
- As quantidades compradas têm padrão?
- O item ficou sem reposição por tempo anormal?

---

### 2.4 Papel da Saída (Principal)

A saída **é o indicador primário de consumo**.

**Perguntas que responde**:
- Quanto esse item realmente sai?
- O consumo é estável ou variável?
- Existem períodos de pico?
- Qual a tendência?

---

## 3. Fluxo de Trabalho Mensal

### 3.1 Durante o Mês (Dia 2 a 30)

O sistema opera normalmente:

```text
✓ Registra entradas → aumenta estoque_atual
✓ Registra saídas → reduz estoque_atual
✓ Atualiza dashboards → informações em tempo real
✓ Compara alertas → usa mínimo/ideal vigentes
✓ NÃO recalcula mínimo/ideal → apenas observa movimentações
```

---

### 3.2 Revisão Mensal (1º do Mês)

No primeiro dia de cada mês, o sistema executa:

1. Buscar todos os itens ativos
2. Para cada item:
   a) Buscar histórico dos últimos 3 meses fechados
   b) Separar entradas por data
   c) Separar saídas por data e quantidade
   d) Calcular métricas de consumo
   e) Calcular métricas de reposição
   f) Gerar sugestão de mínimo e ideal
   g) Avaliar confiabilidade do cálculo
   h) Registrar revisão mensal
   i) Aplicar/Atualizar valores (automático)

---

## 4. Métricas Calculadas

### 4.1 Consumo Mensal

O sistema agrupa saídas por mês natural (01-28/29/30/31).

**Exemplo**:
```text
Dezembro: 90 unidades em 31 dias
Janeiro: 120 unidades em 31 dias
Fevereiro: 100 unidades em 28 dias
Março: 160 unidades em 31 dias
Abril: 110 unidades em 30 dias
Maio: 130 unidades em 31 dias
```

Resultado: **consumo observado por mês**

---

### 4.2 Consumo Diário por Mês

Divide consumo pelo número de dias do mês:

```text
Dezembro: 90 / 31 = 2,90 un/dia
Janeiro: 120 / 31 = 3,87 un/dia
Fevereiro: 100 / 28 = 3,57 un/dia
Março: 160 / 31 = 5,16 un/dia
Abril: 110 / 30 = 3,67 un/dia
Maio: 130 / 31 = 4,19 un/dia
```

Resultado: **padrão diário de cada mês**

---

### 4.3 Consumo Médio Diário (Mediana)

Calcula a mediana dos consumos diários dos meses analisados:

```text
Valores: [2,90, 3,87, 3,57, 5,16, 3,67, 4,19]
Ordenados: [2,90, 3,57, 3,67, 3,87, 4,19, 5,16]
Mediana: (3,67 + 3,87) / 2 = 3,77 un/dia
```

**Por que mediana?** Evita distorções. Um mês anormalmente alto ou baixo não puxa a média.

---

### 4.4 Consumo Diário Percentil 75

Calcula o 75º percentil dos consumos diários:

```text
Valores: [2,90, 3,57, 3,67, 3,87, 4,19, 5,16]
P75 ≈ 4,40 un/dia
```

**Interpretação**: consumo acima do normal, mas ainda comum.

**Uso**: base para cálculo de estoque mínimo (cenário cauteloso).

---

### 4.5 Intervalo Entre Entradas

Calcula os dias entre uma entrada e a próxima:

**Exemplo**:
```text
Entrada 02/01
Entrada 17/01 → intervalo: 15 dias
Entrada 05/02 → intervalo: 19 dias
Entrada 20/02 → intervalo: 15 dias
Entrada 10/03 → intervalo: 18 dias
```

Resultado: **intervalos observados: [15, 19, 15, 18]**

---

### 4.6 Intervalo Mediano Entre Entradas

Calcula a mediana dos intervalos:

```text
Intervalos: [15, 19, 15, 18]
Ordenados: [15, 15, 18, 19]
Mediana: (15 + 18) / 2 = 16,5 ≈ 17 dias (arredonda para cima)
```

**Interpretação**: a reposição ocorre, em média, a cada 17 dias.

---

### 4.7 Intervalo Percentil 90 Entre Entradas

Calcula o 90º percentil:

```text
P90 ≈ 18,7 ≈ 19 dias (arredonda para cima)
```

**Interpretação**: até em cenários de reposição mais lenta, o item chega em até 19 dias.

**Uso**: base para cálculo conservador, cenário de pior caso operacional.

---

## 5. Fórmulas de Cálculo

### 5.1 Estoque Mínimo (Recomendado)

```text
estoque_minimo_sugerido = consumo_diario_p75 × intervalo_mediano

Interpretação:
- Consume no ritmo acima do normal (P75)
- Até que a próxima reposição chegue (intervalo mediano)
```

**Exemplo**:
```text
consumo_diario_p75 = 4,40 un/dia
intervalo_mediano = 17 dias
estoque_minimo_sugerido = 4,40 × 17 = 74,8 → arredonda para 75 un
```

---

### 5.2 Estoque Ideal (Recomendado)

```text
estoque_ideal_sugerido = estoque_minimo_sugerido + consumo_esperado_proximo_ciclo

Onde:
consumo_esperado_proximo_ciclo = consumo_diario_mediana × intervalo_mediano
```

**Interpretação**:
- Estoque mínimo = sobreviver até a próxima entrada
- Estoque ideal = mínimo + buffer para operar com folga

**Exemplo**:
```text
estoque_minimo_sugerido = 75 un

consumo_diario_mediana = 3,77 un/dia
intervalo_mediano = 17 dias
consumo_esperado = 3,77 × 17 = 64,1 ≈ 64 un

estoque_ideal_sugerido = 75 + 64 = 139 un
```

---

### 5.3 Regra Adicional: Ideal ≥ Mínimo + Saída Típica

O ideal **nunca pode ser** menor que:

```text
estoque_ideal_sugerido >= estoque_minimo_sugerido + saida_tipica_mensal
```

Onde `saida_tipica_mensal` é a saída mediana do mês anterior ou da mediana dos 3 meses.

---

## 6. Algoritmo de Revisão Mensal

```text
EXECUTAR NO 1º DO MÊS A 00:00 (ou via demanda do usuário)

Para cada item com status = "ativo":

  1. COLETA
     histórico = últimos 3 meses fechados
     entradas = filtrar histórico por tipo "entrada"
     saídas = filtrar histórico por tipo "saída"

  2. VALIDAÇÃO DE DADOS SUFICIENTES
     Se (não há entradas) E (não há saídas):
       status_confiabilidade = "Histórico insuficiente"
       pular para próximo item
     
  3. CÁLCULO DE CONSUMO
     para cada mês em histórico:
       consumo_mês[i] = soma das saídas do mês
       dias_mês[i] = dias do calendário do mês
       consumo_diario[i] = consumo_mês[i] / dias_mês[i]
     
     consumo_mediana = mediana(consumo_diario)
     consumo_p75 = percentil_75(consumo_diario)

  4. CÁLCULO DE REPOSIÇÃO
     Se há pelo menos 2 entradas:
       Para cada entrada[i+1]:
         intervalo[i] = data[entrada[i+1]] - data[entrada[i]]
       
       intervalo_mediano = mediana(intervalo)
       intervalo_p90 = percentil_90(intervalo)
     Senão:
       intervalo_mediano = NULL (não calcular)
       intervalo_p90 = NULL (não calcular)
       status_confiabilidade = "Sem entradas suficientes"

  5. CÁLCULO DE MÍNIMO E IDEAL
     Se (consumo_p75 existe) E (intervalo_mediano existe):
       mínimo_sugerido = CEIL(consumo_p75 × intervalo_mediano)
       
       consumo_esperado = consumo_mediana × intervalo_mediano
       ideal_sugerido = CEIL(mínimo_sugerido + consumo_esperado)
       
       Se ideal_sugerido < (mínimo_sugerido + saida_tipica):
         ideal_sugerido = mínimo_sugerido + saida_tipica
     Senão:
       mínimo_sugerido = NULL
       ideal_sugerido = NULL
       status_confiabilidade = "Dados insuficientes"

  6. ATUALIZAÇÃO DE SUGESTÕES AUTOMÁTICAS
     item.estoque_minimo_sugerido = mínimo_sugerido
     item.estoque_ideal_sugerido = ideal_sugerido
     
     (Sempre atualiza os valores sugeridos automáticos,
      independentemente de haver valores manuais ou não)

  7. REGISTRO DE REVISÃO
     registrar_revisao_mensal(
       item_id,
       periodo: "Junho/2026",
       base_analisada: "01/03 a 31/05/2026",
       consumo_mediana,
       consumo_p75,
       intervalo_mediano,
       intervalo_p90,
       minimo_sugerido,
       ideal_sugerido,
     )
```

---

## 7. Confiabilidade do Cálculo

### 7.1 Estados de Confiabilidade

O sistema deve informar ao usuário o nível de confiança do cálculo:

| Estado | Condição | Ação |
|--------|----------|------|
| **Histórico insuficiente** | Sem nenhuma movimentação, insuficiencia para ter histórico | Não aplica cálculo automático |
| **Histórico recente** | Pouco tempo de execução, dias, 1-2 meses | Sugestão com alerta ao usuário |
| **Histórico irregular** | Picos extremos que afastam mediana | Marca como irregular, mas aplica |
| **Sem consumo recente** | Há entradas, mas sem saídas | Indica possível obsolescência |
| **Sem entradas recentes** | Há saídas, mas sem entradas | Não consegue medir reposição |

---

## 8. Priorização: Manual vs. Automático

O sistema funciona com **priorização**, não com modos:

### 8.1 Lógica de Priorização

**Para cada parâmetro (mínimo ou ideal):**

```text
Se estoque_minimo_manual está definido:
  → Use estoque_minimo_manual em compras, relatórios e alertas
  
Senão:
  → Use estoque_minimo_sugerido (automático)

Se estoque_ideal_manual está definido:
  → Use estoque_ideal_manual em compras, relatórios e alertas
  
Senão:
  → Use estoque_ideal_sugerido (automático)
```

**Importante**: os valores automáticos são **sempre calculados e atualizados**, independentemente de haver manual ou não.

---

### 8.2 Campos no Sistema

```text
VALORES APLICADOS (usados para operação):
  estoque_minimo_vigente
  estoque_ideal_vigente
  origem_minimo (será "Manual" ou "Automático")
  origem_ideal (será "Manual" ou "Automático")

VALORES AUTOMÁTICOS (sempre calculados):
  estoque_minimo_sugerido
  estoque_ideal_sugerido
  
VALORES MANUAIS (opcionais, se usuario definiu):
  estoque_minimo_manual (pode ser NULL)
  estoque_ideal_manual (pode ser NULL)
  data_definicao_minimo_manual
  data_definicao_ideal_manual
```

---

### 8.3 Fluxo: Como Define Manual?

**Quando o usuário quer usar um valor manual:**

```text
1. Usuário clica "Definir valor manual" no item
2. Usuário preenche novo valor
3. Sistema salva:
   - estoque_minimo_manual = novo valor
   - estoque_ideal_manual = novo valor
   - data_definicao_minimo_manual = hoje
   - estoque_minimo_vigente = novo valor
   - origem_minimo = "Manual"

5. Na próxima revisão mensal:
   - Sistema calcula estoque_minimo_sugerido normalmente
   - MAS não sobrescreve estoque_minimo_manual
   - estoque_minimo_vigente continua usando manual
```

---

### 8.4 Fluxo: Como Remove Manual?

**Quando o usuário quer voltar a usar automático:**

```text
1. Usuário clica "Remover valor manual" no item
2. Sistema pede confirmação: "Voltar a usar valor automático?"
3. Usuário confirma
4. Sistema remove:
   - estoque_minimo_manual = NULL
   - estoque_ideal_manual = NULL
   - data_definicao_minimo_manual = NULL
   - estoque_minimo_vigente = estoque_minimo_sugerido (atual)
   - origem_minimo = "Automático"

5. A partir de agora:
   - Sistema usa automático novamente
   - Próxima revisão mensal atualiza estoque_minimo_vigente
```

---


### 8.5 Quando o Sistema Atualiza Automáticos

**Sempre, independentemente de haver manual:**

```text
1º do mês → Executa revisão mensal

Se não há manual:
  estoque_minimo_vigente = novo_sugerido
  
Se há manual:
  estoque_minimo_vigente = continua manual
  MAS estoque_minimo_sugerido = atualiza com novo cálculo

Resultado: Usuário sempre vê a diferença atualizada
```

---

## 9. Alertas de Estoque

### 9.1 Regra de Status

```text
Se estoque_atual <= estoque_minimo:
    status = CRÍTICO
    cor = VERMELHO
    ação = "Reposição necessária"
    urgência = Alta

Se estoque_atual > estoque_minimo
   E estoque_atual < estoque_ideal:
    status = ATENÇÃO
    cor = AMARELO
    ação = "Abaixo do nível ideal"
    urgência = Média
```

---

### 9.2 Exemplos Práticos

**Exemplo 1: Crítico**
```text
Estoque atual: 70
Mínimo: 92
Ideal: 184

Resultado: CRÍTICO
Mensagem: "Estoque abaixo do mínimo. Reposição urgente necessária."
```

**Exemplo 2: Atenção**
```text
Estoque atual: 130
Mínimo: 92
Ideal: 184

Resultado: ATENÇÃO
Mensagem: "Estoque acima do mínimo, mas abaixo do ideal."
```

**Exemplo 3: Adequado**
```text
Estoque atual: 190
Mínimo: 92
Ideal: 184

Resultado: ADEQUADO
Mensagem: "Estoque em nível saudável."
```

---

## 10. Regras de Negócio Consolidadas

| Regra | Detalhe |
|-------|---------|
| **Revisão Mensal** | Ocorre automaticamente no 1º do mês ou sob demanda do usuário |
| **Janela de Análise** | Últimos 3 meses fechados (nunca inclui o mês aberto) |
| **Mediana, Não Média** | Evita distorções por meses anormais |
| **Percentis para Segurança** | P75 para consumo (acima do normal), P90 para intervalo (pior caso) |
| **Consumo = Saídas** | Indicador primário é quantidade de saída, não entrada |
| **Entrada = Contexto** | Alimenta frequência de reposição, não marca "fim de ciclo" |
| **Sempre Calcula Automático** | Valores automáticos são sempre calculados e atualizados, independentemente de haver manual |
| **Manual Tem Prioridade** | Se valor manual foi definido, ele é usado em operação (compras, alertas, relatórios) |
| **Paralelo Contínuo** | Sugestão automática é sempre calculada e exibida, mesmo que manual esteja em uso |
| **Comparação Clara** | Usuário sempre vê origem (manual vs. automático) e diferença entre eles |
| **Arredondamento** | Sempre para cima (ceil) para evitar sub-estimativa |
| **Histórico Insuficiente** | Não calcula se sem tempo ou movimentação significativa |
| **Histórico Recente** | Calculo para pouco tempo ou poucas movimentações significativas |
| **Alertas Dinâmicos** | Usam valores vigentes (manual se definido, automático caso contrário) |
| **Registro de Origem** | Toda revisão deixa rastro: quem, quando, que base, que sugestão |
| **Manual Não Bloqueia Cálculo** | Usuário pode definir manual, mas sistema continua calculando automático |
| **Remoção de Manual** | Usuário pode remover manual a qualquer momento, voltando ao automático |

---

## Conclusão

Este modelo oferece:

1. **Simplicidade operacional**: revisão mensal, janela fixa
2. **Resiliência**: não depende de marcos de fechamento
3. **Transparência**: origem e sugestão sempre visíveis
4. **Flexibilidade**: usuário define manual quando necessário, sistema sugere sempre
5. **Inteligência**: baseado em percentis, não em média cega
6. **Rastreabilidade**: histórico completo de revisões
7. **Priorização Inteligente**: manual tem prioridade, automático continua calculando
8. **Sem Modos Complexos**: apenas presença ou ausência de manual define o comportamento

O sistema faz seu trabalho de forma silenciosa e confiável:
- Calcula automaticamente sempre
- Respeita valores manuais quando definidos
- Nunca deixa de oferecer sugestão automática
- Permite remover manual e voltar ao automático em qualquer momento
