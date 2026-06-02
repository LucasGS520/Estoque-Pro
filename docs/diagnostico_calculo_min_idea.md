# Diagnóstico — Camada de Cálculo Automático de Estoque Mínimo e Ideal

> **Estado atual do sistema** — documento de referência técnica.  
> Descreve arquitetura, lógica de cálculo, fluxo de trabalho e regras de negócio vigentes.

---

## 1. Visão Geral da Camada

O sistema não depende de inserção manual dos campos `estoque_minimo` e `estoque_ideal` para operar. Em vez disso, uma camada automática calcula sugestões mensalmente com base no histórico real de movimentações, e os valores usados em operação são determinados por uma lógica de priorização entre automático e manual.

**Três camadas de valores por item:**

```
CAMADA 1 — SUGERIDO (sempre calculado, nunca NULL após primeira revisão com dados)
  estoque_minimo_sugerido    → calculado pelo motor de revisão mensal
  estoque_ideal_sugerido     → calculado pelo motor de revisão mensal

CAMADA 2 — MANUAL (opcional, definido pelo usuário quando necessário)
  estoque_minimo_manual      → NULL enquanto o usuário não definir
  estoque_ideal_manual       → NULL enquanto o usuário não definir
  data_definicao_minimo_manual
  data_definicao_ideal_manual

CAMADA 3 — VIGENTE (usado em toda operação: compras, alertas, dashboard)
  estoque_minimo_vigente     → manual se definido, senão sugerido, senão 0
  estoque_ideal_vigente      → manual se definido, senão sugerido, senão 0
  origem_minimo              → "Manual" ou "Automático"
  origem_ideal               → "Manual" ou "Automático"
```

**Regra de priorização**: o vigente é sempre o manual se existir; caso contrário, o sugerido. Toda análise, alerta, dashboard e relatório usa exclusivamente `*_vigente`.

---

## 2. Modelo de Dados

### 2.1 Campos adicionados ao modelo `Item` (`core/models.py`)

| Campo | Tipo | Descrição |
|---|---|---|
| `estoque_minimo_sugerido` | Integer, nullable | Calculado automaticamente na revisão mensal |
| `estoque_ideal_sugerido` | Integer, nullable | Calculado automaticamente na revisão mensal |
| `estoque_minimo_manual` | Integer, nullable | Definido pelo usuário. NULL = usando automático |
| `estoque_ideal_manual` | Integer, nullable | Definido pelo usuário. NULL = usando automático |
| `data_definicao_minimo_manual` | DateTime, nullable | Quando o usuário definiu o valor manual |
| `data_definicao_ideal_manual` | DateTime, nullable | Quando o usuário definiu o valor manual |
| `estoque_minimo_vigente` | Integer, default=0 | Valor efetivo em uso em toda operação |
| `estoque_ideal_vigente` | Integer, default=0 | Valor efetivo em uso em toda operação |
| `origem_minimo` | String(20), nullable | `"Manual"` ou `"Automático"` |
| `origem_ideal` | String(20), nullable | `"Manual"` ou `"Automático"` |

Os campos legados `estoque_minimo` e `estoque_ideal` são mantidos no modelo para compatibilidade, mas não são usados em operações. Na migração inicial, seus valores foram copiados para `*_manual` e `*_vigente`.

### 2.2 Modelo `RevisaoMensal` (`core/models.py`)

Cada execução da revisão cria um registro por item com rastreabilidade completa. A combinação `(item_id, periodo_descricao)` é única no banco — um único registro por item por mês:

| Campo | Descrição |
|---|---|
| `item_id` | FK para o item |
| `periodo_descricao` | Ex: `"Junho/2026"` |
| `data_inicio_analise` | Início **real** da janela usada (pode ser mais recente que 3 meses atrás para itens novos) |
| `data_fim_analise` | Sempre o último dia do mês anterior à revisão |
| `consumo_mediana_diario` | Mediana dos consumos diários por mês |
| `consumo_p75_diario` | Percentil 75 dos consumos diários |
| `intervalo_mediano_dias` | Mediana dos intervalos entre entradas consecutivas |
| `intervalo_p90_dias` | Percentil 90 dos intervalos |
| `minimo_sugerido` | Valor calculado (pode ser NULL se dados insuficientes) |
| `ideal_sugerido` | Valor calculado (pode ser NULL se dados insuficientes) |
| `status_confiabilidade` | Estado de qualidade do cálculo (ver seção 5) |

---

## 3. Motor de Cálculo (`core/calculos.py`)

Módulo **completamente stateless** — sem acesso a banco de dados ou Streamlit. Recebe listas de tuplas e retorna um `ResultadoRevisao`. Testável isoladamente.

### 3.1 Janela de Análise — Adaptativa

A janela de análise é determinada por dois fatores: a data de referência e o histórico disponível do item.

**Janela padrão (3 meses fechados):**
```python
def calcular_janela(data_ref: date) -> tuple[date, date]:
    # data_ref = 01/06/2026 → retorna (01/03/2026, 31/05/2026)
```
O mês corrente nunca entra. Sempre são os 3 meses imediatamente anteriores, completamente fechados.

**Janela adaptativa (itens com histórico curto):**

Quando o item tem menos de 3 meses de história, a janela se adapta ao histórico disponível:

```
inicio_padrao, fim = calcular_janela(data_ref)   # ex: 01/03 a 31/05

Se data_primeira_movimentacao > inicio_padrao:
    inicio_efetivo = data_primeira_movimentacao  # ex: 10/05/2026
    janela_curta = True
Senão:
    inicio_efetivo = inicio_padrao               # item antigo: 3 meses completos
    janela_curta = False
```

**Por que isso importa**: sem adaptação, um item registrado há 3 semanas usaria uma janela de 3 meses onde 2 meses e 1 semana estariam vazios. O motor teria poucos dados, calcularia consumo diário errado (dividindo por 31 dias quando o item existia há 10), e retornaria `None` mesmo com dados reais disponíveis.

### 3.2 Cálculo de Consumo por Mês

Para cada mês com saídas dentro da janela efetiva:

```
consumo_diario[mês] = total_saidas_do_mês / dias_efetivos_do_mês_na_janela
```

**`dias_efetivos`** é o número de dias do mês que estão dentro da janela:
- Para meses completos na janela: igual aos dias totais do mês (28/29/30/31)
- Para meses parciais (início ou fim da janela): apenas os dias dentro do intervalo

```
Exemplo: item criado em 10/05, janela começa em 10/05
  Dias de maio na janela: 10/05 a 31/05 = 22 dias
  Saídas em maio: 12 unidades
  consumo_diario[maio] = 12 / 22 = 0,55 un/dia  ← correto
  (Antes: 12 / 31 = 0,39 un/dia ← subestimado)
```

Resultado: lista de consumos diários, um por mês com dados.

### 3.3 Métricas de Consumo

A partir da lista `consumos_diarios`:

```
consumo_mediana = mediana(consumos_diarios)   → consumo típico, robusto a outliers
consumo_p75     = percentil_75(consumos_diarios)  → consumo "acima do normal"
```

**Por que mediana e não média?** Um mês atípico (compra emergencial, evento pontual) não distorce o resultado. A mediana é resistente a extremos.

**Por que P75 para o mínimo?** O mínimo precisa aguentar até a próxima reposição mesmo em meses de consumo elevado — não apenas no mês típico. P75 representa "acima da metade dos meses, mas ainda dentro do padrão operacional normal".

### 3.4 Métricas de Reposição

A partir das datas de entrada na janela efetiva:

```
Entradas: [02/03, 17/03, 05/04, 20/04, 10/05]
Intervalos entre consecutivas: [15, 19, 15, 18]

intervalo_mediano = ceil(mediana([15, 19, 15, 18])) = ceil(16,5) = 17 dias
intervalo_p90     = ceil(percentil_90([15, 19, 15, 18])) = ceil(18,7) = 19 dias
```

Requer **pelo menos 2 entradas** na janela para calcular intervalos. Com menos de 2 entradas, `intervalo_mediano = None` e o cálculo de mínimo/ideal não pode ser completado.

**Por que P90?** Registrado na `RevisaoMensal` para análise futura. Representa o pior caso operacional de atraso na reposição.

### 3.5 Fórmulas de Mínimo e Ideal

**Estoque Mínimo Sugerido:**
```
minimo = ceil( consumo_p75 × intervalo_mediano )
```
*"Se consumir no ritmo acima do normal (P75), quanto preciso ter para sobreviver até a próxima reposição (intervalo mediano)?"*

**Estoque Ideal Sugerido:**
```
consumo_esperado = consumo_mediana × intervalo_mediano
ideal = ceil( minimo + consumo_esperado )
```
*"Mínimo de segurança mais o que vou consumir no próximo ciclo típico — pedir com conforto, sem urgência."*

**Regra de garantia:**
```
saida_tipica_mensal = mediana( totais de saída por mês na janela )
saida_tipica_ciclo  = ceil( saida_tipica_mensal × intervalo_mediano / 30,44 )

Se ideal < minimo + saida_tipica_ciclo:
    ideal = minimo + saida_tipica_ciclo
```
Garante que o ideal nunca seja irreal: sempre ao menos mínimo + o consumo típico do ciclo de reposição.

A saída típica mensal é **escalada para a duração real do ciclo** (`× intervalo / 30,44 dias`), evitando que itens com reposição frequente (ciclos < 30 dias) fiquem com ideal inflado por uma comparação em escala mensal. Para ciclos longos (> 30 dias) o resultado é equivalente ao piso mensal.

**Arredondamento:** sempre `math.ceil` em todos os valores calculados. Nunca subestima.

### 3.6 Retorno: `ResultadoRevisao`

```python
@dataclass
class ResultadoRevisao:
    minimo_sugerido:        Optional[int]
    ideal_sugerido:         Optional[int]
    consumo_mediana_diario: Optional[float]
    consumo_p75_diario:     Optional[float]
    intervalo_mediano_dias: Optional[int]
    intervalo_p90_dias:     Optional[int]
    status_confiabilidade:  str       # ver seção 5
    data_inicio_efetiva:    Optional[date]
    # None  → janela padrão de 3 meses (item antigo)
    # date  → janela curta (item novo, início real do histórico)
```

---

## 4. Serviço de Orquestração (`services/calculos_service.py`)

Conecta o motor (stateless) com o banco de dados. Todas as funções fazem `commit` explícito.

### 4.1 `executar_revisao_mensal(session, item_id=None)`

Fluxo completo para cada item ativo:

```
1. data_ref = 1º do mês corrente
   inicio_padrao, fim = calcular_janela(data_ref)   → janela padrão de 3 meses

2. Para cada item ativo:

   a) Consulta primeira movimentação comercial (tipo "entrada" ou "saida"):
      data_primeira_mov = MIN(Movimentacao.criado_em)
                          WHERE item_id = item.id AND tipo IN ("entrada", "saida")

   b) Busca movimentações na janela padrão [inicio_padrao, fim]:
      saidas  = [(data, qtd) para tipo="saida"]
      entradas = [(data, qtd) para tipo="entrada"]

   c) Chama o motor:
      resultado = calcular_revisao_item(saidas, entradas, data_ref,
                                        data_primeira_mov=data_primeira_mov)
      → Motor adapta janela se data_primeira_mov > inicio_padrao

   d) SEMPRE atualiza sugestões automáticas:
      item.estoque_minimo_sugerido = resultado.minimo_sugerido
      item.estoque_ideal_sugerido  = resultado.ideal_sugerido

   e) SÓ atualiza vigente se não há manual:
      if item.estoque_minimo_manual is None:
          item.estoque_minimo_vigente = resultado.minimo_sugerido or 0
          item.origem_minimo = "Automático" (ou None se sem sugestão)
      # Se há manual: vigente permanece o valor manual

   f) Registra RevisaoMensal com data_inicio_analise = real (efetiva)

3. Retorna: {processados, atualizados, sem_historico}
```

**Ponto crítico**: os valores sugeridos são sempre recalculados e salvos, mesmo para itens com manual definido. Isso garante que o usuário sempre veja a diferença atualizada entre automático e manual.

### 4.2 `aplicar_minimo_ideal_manual(session, item_id, minimo, ideal)`

Ativado quando o usuário define um valor manual na UI:

```
item.estoque_minimo_manual       = minimo
item.estoque_ideal_manual        = ideal
item.data_definicao_*_manual     = agora
item.estoque_minimo_vigente      = minimo   ← vigente passa a ser manual
item.estoque_ideal_vigente       = ideal
item.origem_minimo               = "Manual"
item.origem_ideal                = "Manual"
```

### 4.3 `remover_manual(session, item_id)`

Ativado quando o usuário remove o override manual:

```
item.estoque_minimo_manual       = None
item.estoque_ideal_manual        = None
item.data_definicao_*_manual     = None
item.estoque_minimo_vigente      = item.estoque_minimo_sugerido or 0
item.estoque_ideal_vigente       = item.estoque_ideal_sugerido  or 0
item.origem_minimo               = "Automático" (ou None se sem sugestão)
```

### 4.4 `get_revisoes_item(session, item_id, limit=12)`

Retorna as últimas N revisões do item, ordenadas da mais recente para a mais antiga. Usada pela UI para exibir badge de confiabilidade.

### 4.5 `get_ultima_revisao_global(session)`

Retorna `MAX(criado_em)` da tabela `revisoes_mensais`. Usada por `app.py` para verificar se já rodou revisão no mês corrente.

---

## 5. Status de Confiabilidade

O motor avalia a qualidade dos dados antes e durante o cálculo:

| Status | Condição | `minimo_sugerido` | Badge na UI |
|---|---|---|---|
| `ok` | Janela completa (3 meses), dados estáveis | Calculado | ✅ verde |
| `historico_recente` | Item com < 3 meses de história (janela adaptativa) | Calculado se ≥ 2 entradas, senão NULL | 🕐 amarelo |
| `irregular` | P75 > 3× mediana (consumo errático) | Calculado com ressalva | ⚠️ laranja |
| `sem_consumo_recente` | Entradas existem, sem saídas no período | NULL | ℹ️ azul |
| `sem_entradas_recentes` | Saídas existem, sem entradas no período | NULL | ℹ️ azul |
| `historico_insuficiente` | Sem nenhuma movimentação | NULL | ❌ vermelho |

**Observação importante sobre `historico_recente`**: este status não interrompe o cálculo. O motor prossegue normalmente com os dados disponíveis. Somente `historico_insuficiente` interrompe o cálculo antes de produzir qualquer valor.

### Como `janela_curta` determina `historico_recente`

```python
def _avaliar_confiabilidade(saidas, entradas, consumos_diarios, janela_curta=False):
    if not saidas and not entradas:
        return "historico_insuficiente"   # sem dado algum → para aqui

    if janela_curta:
        return "historico_recente"        # tem dados mas < 3 meses → marca e continua

    # Verificações adicionais apenas para janela completa:
    if meses_com_saida == 0 and entradas:   return "sem_consumo_recente"
    if meses_com_saida > 0 and not entradas: return "sem_entradas_recentes"
    if meses_com_saida < 2:                  return "historico_recente"
    if p75 > 3 * mediana:                    return "irregular"
    return "ok"
```

---

## 6. Auto-trigger Mensal (`app.py`)

A revisão é **exclusivamente automática**. Não há botão de demanda exposto ao usuário.

```python
# app.py — executado a cada inicialização do Streamlit
_hoje = datetime.date.today()
_revisao_key = f"revisao_executada_{_hoje.year}_{_hoje.month}"
if not st.session_state.get(_revisao_key):
    from services.calculos_service import executar_revisao_mensal, get_ultima_revisao_global
    SessionLocal = get_session_factory()
    with SessionLocal() as _sess:
        _ultima = get_ultima_revisao_global(_sess)
        _ja_rodou = (
            _ultima is not None
            and _ultima.year == _hoje.year
            and _ultima.month == _hoje.month
        )
        if not _ja_rodou:
            executar_revisao_mensal(_sess)
            st.toast("Revisão mensal de estoque executada automaticamente.", icon="📊")
    st.session_state[_revisao_key] = True
```

**Como funciona a idempotência em duas camadas:**

1. **Session state** (`revisao_executada_YYYY_M`): impede re-execução durante a mesma sessão Streamlit ativa, sem consultar o banco.
2. **Check de banco** (`get_ultima_revisao_global`): ao iniciar uma nova sessão, consulta o `MAX(criado_em)` da tabela `revisoes_mensais`. Se já existe um registro com `ano == hoje.year` e `mes == hoje.month`, a revisão não roda novamente.

**Por que não há restrição de dia:** A janela de análise é determinada por `data_ref = hoje.replace(day=1)`, que aponta sempre para o 1º do mês corrente — independente do dia em que a revisão roda. Portanto rodar no dia 5 ou no dia 1 produz exatamente o mesmo resultado. As duas camadas de idempotência garantem que rode apenas uma vez por mês, sem duplicatas.

---

## 7. UI — Seção "Estoque Mínimo e Ideal" (`pages/Estoque.py`)

No painel de edição do item (aba Editar → sub-tab Itens), a seção exibe:

```
┌─────────────────────────────────────────────────────┐
│ Estoque Mínimo e Ideal                              │
│                                                     │
│  Mínimo vigente: 80    │  Ideal vigente: 152        │
│  Automático: 80        │  Automático: 152           │
│  Manual: —             │  Manual: —                 │
│                                                     │
│  ✅ Cálculo confiável — 3 meses de dados            │
│  Última revisão: 01/06/2026                         │
│                                                     │
│  [Definir valor manual]                             │
└─────────────────────────────────────────────────────┘
```

Para um item com override manual ativo e histórico curto:
```
┌─────────────────────────────────────────────────────┐
│ Estoque Mínimo e Ideal                              │
│                                                     │
│  Mínimo vigente: 100   │  Ideal vigente: 200        │
│  Automático: 36        │  Automático: 68            │
│  Manual: 100           │  Manual: 200               │
│                                                     │
│  🕐 Dados recentes — menos de 3 meses de histórico  │
│  Última revisão: 01/06/2026                         │
│                                                     │
│  [Definir valor manual]  [Remover manual]           │
└─────────────────────────────────────────────────────┘
```

**"Remover manual"** aparece somente quando há manual definido.

### Formulário de cadastro de item

O formulário de novo item tem um expander colapsável **"Valores manuais de estoque (opcional)"** com inputs para mínimo e ideal manual. Deixar em 0 significa "usar cálculo automático após a próxima revisão mensal". O item é criado sem vigente até a primeira revisão processar seu histórico.

---

## 8. Fluxo de Trabalho Completo

### Dia a dia (dia 2 a 30/31 do mês)
```
Usuário registra saída
→ estoque_atual diminui
→ Sistema compara estoque_atual com estoque_minimo_VIGENTE
→ Status: ok / comprar / zerado / sem_minimo
→ Dashboard e alertas em tempo real
→ NÃO recalcula mínimo/ideal
```

### Primeira abertura do mês (automático)
```
app.py inicializa
→ verifica: já rodou revisão este mês? (session state + check de banco)
→ se não: executa revisao_mensal para todos os itens ativos
  → para cada item:
    - consulta data da primeira movimentação comercial (entrada ou saída)
    - define janela: padrão (3 meses) ou adaptativa (desde primeira mov)
    - calcula métricas de consumo e reposição
    - gera minimo_sugerido e ideal_sugerido
    - atualiza vigente (se sem manual)
    - registra RevisaoMensal com período real
→ exibe toast de confirmação
```

### Item novo (< 3 meses de histórico)
```
Meses 1-2:
  → janela_curta = True, status = "historico_recente"
  → Se ≥ 2 entradas: minimo_sugerido calculado (menor confiança)
  → Se < 2 entradas: minimo_sugerido = None (sem intervalo)
  → badge: 🕐 "Dados recentes"

A partir do 4º mês após a primeira movimentação:
  → data_primeira_mov < inicio_padrao
  → janela_curta = False, análise completa
  → status potencialmente "ok"
  → badge: ✅ "Cálculo confiável"
```

### Usuário define manual
```
Clica "Definir valor manual" → preenche mínimo e ideal
→ vigente = manual, origem = "Manual"
→ Na próxima revisão: sugerido é recalculado normalmente
  MAS vigente permanece manual
→ UI mostra: Vigente: 100 [Manual] | Automático: 80
```

### Usuário remove manual
```
Clica "Remover manual" → confirmação
→ manual = None, vigente = sugerido, origem = "Automático"
→ A partir de agora: revisões mensais atualizam o vigente automaticamente
```

---

## 9. Regras de Negócio Consolidadas

| Regra | Implementação |
|---|---|
| Revisão na primeira abertura do mês | Auto-trigger em `app.py`, sem botão de demanda; idempotente via session state + check de banco |
| Janela padrão: 3 meses fechados | `calcular_janela()` em `core/calculos.py` |
| Janela adaptativa para itens novos | `data_primeira_mov` passado ao motor; `inicio_efetivo = max(inicio_padrao, primeira_mov)` |
| Consumo diário proporcional a dias efetivos | `_consumo_por_mes()` usa `max(inicio_mes, inicio_janela)` como denominador |
| Mediana (não média) para consumo | `_percentil(consumos_diarios, 50)` |
| P75 para mínimo (cenário acima do normal) | `_percentil(consumos_diarios, 75)` |
| P90 para intervalo (pior caso, rastreado) | Salvo em `RevisaoMensal.intervalo_p90_dias` |
| Arredondamento sempre para cima | `math.ceil()` em todos os valores calculados |
| Sugerido sempre calculado | `executar_revisao_mensal` atualiza `*_sugerido` mesmo com manual ativo |
| Manual tem prioridade sobre vigente | `if item.estoque_minimo_manual is None` guarda o vigente |
| Paralelo contínuo | UI exibe Automático e Manual simultaneamente |
| `historico_recente` não bloqueia cálculo | Somente `historico_insuficiente` retorna antes do cálculo |
| Rastreabilidade de janela | `data_inicio_efetiva` em `ResultadoRevisao`; `data_inicio_analise` reflete início real |
| Badge de confiabilidade na UI | Lê `RevisaoMensal.status_confiabilidade` da última revisão do item |
| Ideal ≥ mínimo + saída típica do ciclo | Regra de garantia proporcional ao ciclo: `saida_tipica_mensal × intervalo / 30,44` em `calcular_revisao_item()` |
| `data_primeira_mov` filtra apenas movimentações comerciais | Query em `calculos_service.py` filtra `tipo IN ("entrada", "saida")` |
| Unicidade de revisões por item/período no banco | Índice único `(item_id, periodo_descricao)` em `revisoes_mensais`; migração com deduplicação prévia em `run_schema_migrations()` |

---

## 10. Arquivos do Sistema

| Arquivo | Responsabilidade |
|---|---|
| `core/calculos.py` | Motor stateless: janela adaptativa, métricas, fórmulas, confiabilidade |
| `core/models.py` | ORM: campos `*_vigente`, `*_sugerido`, `*_manual`, `origem_*` em `Item`; modelo `RevisaoMensal` |
| `core/database.py` | `init_db()` + `run_schema_migrations()`: ADD COLUMN idempotente + migração de dados legados + deduplicação e índice único em `revisoes_mensais` |
| `services/calculos_service.py` | Orquestração: revisão mensal, manual, histórico de revisões |
| `services/estoque_service.py` | CRUD de itens usando `*_vigente` em status e tabela mestre |
| `services/compras_service.py` | `_item_to_record()` usa `*_vigente` para análise de reposição |
| `pages/Estoque.py` | UI: seção mínimo/ideal com badge, formulário manual, sem botão de demanda |
| `app.py` | Auto-trigger na primeira abertura do mês (qualquer dia); idempotente via session state + banco |
