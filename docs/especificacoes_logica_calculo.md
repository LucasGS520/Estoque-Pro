# Especificação consolidada — Parâmetros e Reposição

## Camada 1 — Parâmetros dos Itens

### Objetivo

Definir os limites operacionais usados pelo sistema para análise de compra:

| Parâmetro                | Novo significado                                                                  |
| ------------------------ | --------------------------------------------------------------------------------- |
| `estoque_minimo`         | Piso de segurança. Abaixo ou igual a ele, o item exige atenção forte para compra. |
| `estoque_ideal`          | Limite superior operacional. Acima dele, o item não deve ser comprado.            |
| `estoque_minimo_vigente` | Valor de mínimo realmente usado pelo sistema.                                     |
| `estoque_ideal_vigente`  | Valor de ideal realmente usado pelo sistema.                                      |

### 2. Regra para cálculo automático dos parâmetros

O cálculo automático mensal pode continuar existindo, mas deve ser interpretado corretamente:

```text
mínimo_sugerido = estoque necessário para atravessar um ciclo de consumo com segurança

ideal_sugerido = limite operacional superior recomendado
```

O `ideal_sugerido` não deve ser usado como destino obrigatório da compra.

#### Regra desejada

```text
estoque_minimo = ponto de risco
estoque_ideal = ponto máximo recomendado
```

O cálculo mensal deve continuar usando histórico de:

* saídas;
* entradas;
* consumo diário;
* variação do consumo;
* intervalo entre reposições.

Mas o resultado deve alimentar apenas os parâmetros do item.
A quantidade sugerida de compra deve ser calculada em outra camada.

### 3. Override manual

A lógica manual deve permanecer:
* se houver valor manual: usar valor manual como vigente
* senão: usar valor automático sugerido como vigente

O cálculo automático continua rodando todo mês, mas não sobrescreve o vigente manual.

---

## Camada 2 — Status de Reposição

### Problema atual

Hoje o sistema trabalha com:
- ZERADO
- SEM_PARAMETRO
- EXCESSO
- OK
- ABAIXO_MINIMO

O status `EXCESSO` deve sair da decisão de compras.

O problema dele é que ele trata estoque acima do ideal como uma condição especial negativa dentro da compra, quando na prática, para compras, isso significa apenas:
**não comprar**

### 4. Nova tabela de status

A nova classificação deve ser:

| Status          |                     Condição | Entra em compra? | Interpretação                                                                |
| --------------- | ---------------------------: | ---------------: | ---------------------------------------------------------------------------- |
| `SEM_PARAMETRO` | mínimo ou ideal não definido |              Não | Sistema não tem base segura para sugerir compra.                             |
| `ZERADO`        |            estoque atual = 0 |              Sim | Item sem saldo físico. Prioridade máxima.                                    |
| `ABAIXO_MINIMO` |              atual <= mínimo |              Sim | Item em zona crítica de reposição.                                           |
| `ABAIXO_IDEAL`  |      mínimo < atual <= ideal |    Pode aparecer | Item ainda não está crítico, mas está abaixo do limite operacional desejado. |
| `OK`            |                atual > ideal |              Não | Item está acima do limite de compra; não deve ser comprado.                  |

Observação importante: `OK` aqui significa **OK para não comprar**, não necessariamente “estoque perfeito”.

### 5. Ordem correta de avaliação

A ordem deve ser esta:

```text
1. Se mínimo ou ideal não estiver definido:
   → SEM_PARAMETRO
   → qtd_recomendar = 0

2. Se estoque_atual == 0:
   → ZERADO
   → calcular quantidade sugerida

3. Se estoque_atual <= estoque_minimo:
   → ABAIXO_MINIMO
   → calcular quantidade sugerida

4. Se estoque_atual <= estoque_ideal:
   → ABAIXO_IDEAL
   → pode aparecer na análise, mas não deve gerar compra automática obrigatória

5. Se estoque_atual > estoque_ideal:
   → OK
   → qtd_recomendar = 0
```

Essa ordem evita um erro importante: item zerado ou abaixo do mínimo deve ter prioridade sobre qualquer outra classificação.

### 6. Nova regra para quantidade sugerida

A quantidade sugerida **não deve mais ser**:

```text
estoque_ideal - estoque_atual
```

Nem:

```text
estoque_ideal - saldo
```

Essa regra atual força compra até o ideal e pode gerar excesso, compra inflada.

A nova regra deve usar um alvo calculado interno:

```text
alvo_reposicao = mínimo + margem_operacional
```

Com trava:

```text
alvo_reposicao nunca pode passar do estoque_ideal
```

Então:

```text
alvo_reposicao = min(estoque_ideal, estoque_minimo + margem_operacional)
```

E a quantidade:

```text
qtd_recomendar = max(0, alvo_reposicao - saldo_base)
```

Onde `saldo_base` pode ser:

| Contexto                              | Saldo usado                              |
| ------------------------------------- | ---------------------------------------- |
| Painel de Reposição                   | `estoque_atual`                          |
| Lista de Compras / Análise do Período | `estoque_atual - solicitações_aprovadas` |

### 7. Margem operacional

A margem operacional deve vir preferencialmente do cálculo mensal.

Regra ideal:

```text
margem_operacional = consumo_mediano_diario × intervalo_mediano_reposicao
```

Ou seja:

```text
quanto o item normalmente consome em um ciclo típico de reposição
```

Isso é melhor que usar multiplicador fixo, como:

```text
ideal = 2 × mínimo
```

ou:

```text
comprar sempre até o ideal
```

### 8. Painel de Reposição

O Painel de Reposição deve responder:

```text
Como está o estoque agora?
```

Regra:

```text
saldo_base = estoque_atual
```

Decisão:
- SEM_PARAMETRO: não sugerir compra
- ZERADO: sugerir compra até o alvo_reposicao
- ABAIXO_MINIMO: sugerir compra até o alvo_reposicao
- ABAIXO_IDEAL: pode ser exibido, com ressalvas (sem compra obrigatória)
- OK: não exibir na lista de compra principal

---

## Lista de Compras / Análise do Período

A Lista de Compras deve responder:
> Depois de atender as solicitações aprovadas, o estoque ficará em qual situação?

Regra:

```text
saldo_projetado = estoque_atual - total_solicitado_aprovado
```

A classificação deve ser feita sobre o `saldo_projetado`, não apenas sobre o estoque atual.

* se saldo_projetado <= mínimo: ABAIXO_MINIMO
* se mínimo < saldo_projetado <= ideal: ABAIXO_IDEAL
* se saldo_projetado > ideal: OK

A quantidade sugerida deve ser:

```text
qtd_recomendar = max(0, alvo_reposicao - saldo_projetado)
```

### 9. Comportamento do `ABAIXO_IDEAL`

Esse status é intermediário.

Ele não deve ser tratado como compra obrigatória.

Uso correto:
- pode aparecer na análise;
- deve ter prioridade menor que ZERADO e ABAIXO_MINIMO;
- pode ser usado para alertar tendência de queda;
- só deve gerar compra se houver solicitação aprovada, recorrência, ou regra operacional específica.

Ordenação recomendada na tela:
1. ZERADO
2. ABAIXO_MINIMO
3. ABAIXO_IDEAL com solicitações aprovadas
4. ABAIXO_IDEAL sem solicitação
5. SEM_PARAMETRO
6. OK

### 10. O que deve mudar no sistema

#### Remover

```text
status EXCESSO da lógica de decisão de compras
```

#### Ajustar

```text
OK passa a representar atual > ideal
ABAIXO_IDEAL passa a representar mínimo < atual <= ideal
ABAIXO_MINIMO permanece atual <= mínimo
```

#### Corrigir

```text
quantidade sugerida não pode mais ser ideal - saldo
```

#### Criar internamente

```text
alvo_reposicao_calculado
```

Esse valor não precisa virar campo obrigatório no banco no primeiro momento. Pode ser calculado dentro do motor.

#### Nova regra central

```text
comprar somente o necessário para sair da zona crítica e manter margem operacional,
sem usar o estoque_ideal como alvo automático.
```

### 11. Resultado esperado

Com essa mudança:

```text
estoque_minimo = define risco
estoque_ideal = define limite máximo de compra
alvo_reposicao = define quanto comprar
status = define prioridade operacional
```

A camada de compras passa a trabalhar assim:
- não comprar até o ideal;
- comprar conforme necessidade real;
- respeitar solicitações aprovadas;
- priorizar zerados e abaixo do mínimo;
- mostrar abaixo do ideal como atenção, não como compra automática;
- não sugerir compra para itens acima do ideal.
