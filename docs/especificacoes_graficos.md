## 1. Padrão visual recomendado

O padrão dos seus mockups deve virar um **design system de gráficos**:

| Elemento        | Especificação                                                                      |
| --------------- | ---------------------------------------------------------------------------------- |
| Card do gráfico | Fundo branco, borda `#E5E5E5`, raio 6–8px, sem sombra pesada                       |
| Cabeçalho       | Título pequeno, peso 600, cor preta, com linha divisória abaixo                    |
| Área do gráfico | Fundo branco ou quase branco, sem blocos coloridos                                 |
| Grid            | Linhas pontilhadas ou leves em `#E5E5E5`                                           |
| Eixos           | Cinza discreto, labels pequenos, sem excesso de texto                              |
| Cor principal   | Vermelho DFeB `#E10600`                                                            |
| Cor comparativa | Preto/cinza escuro `#262626`                                                       |
| Cor neutra      | Cinza `#9CA3AF`                                                                    |
| Alerta          | Laranja `#F59E0B`                                                                  |
| OK              | Verde `#16A34A`                                                                    |
| Legenda         | Inferior ou superior direita, discreta, nunca colorbar lateral para barras simples |
| Tooltip         | Customizado, com mês/categoria e valores claros                                    |

O sistema já tem uma função central de tema Plotly em `core/ui.py`, então o melhor caminho é evoluir `apply_plotly_theme()` em vez de configurar cada gráfico isoladamente. Hoje ela já define fundo, fonte, colorway, margens, legenda e grid, mas ainda de forma genérica. 

---

## 2. Especificação por gráfico existente

### A. Visão Geral — Status por Categoria

Hoje o gráfico empilha status por categoria. A lógica é válida, porque a página calcula os status diretamente pelo `StockAnalyzer`, usando estoque atual, mínimo vigente e ideal vigente. 

Problemas atuais:

* legenda expõe valor técnico como `sem_minimo_definido`;
* cinza domina quando muitos itens não têm limite;
* mistura “risco de estoque” com “cadastro incompleto”.

Especificação proposta:

1. Manter um gráfico principal chamado **“Itens críticos por categoria”**.
2. Considerar críticos: `comprar`, `zerado`, etc.
3. Usar barra vertical vermelha, como no mock.
4. Exibir `Sem limite` em outro card/tabela, não misturado com crítico.
5. Tooltip:
   `Categoria: EPI`
   `Críticos: 3`
   `Comprar: 2`
   `Zerados: 1`

O gráfico empilhado pode continuar existindo, mas como visual secundário: **“Distribuição completa por status”**.

### B. Relatórios — Consumo Mensal

O gráfico atual usa linha por item. No código, ele faz `px.line()` por `item`, com `mes` no eixo X e `total_saida` no Y.  O problema é que, visualmente, isso fica ruim quando há poucos meses ou muitos itens.

Especificação proposta:

**Gráfico principal:** `Consumo mensal — visão consolidada`

* Tipo: barra agrupada.
* Eixo X: últimos 6 ou 12 meses.
* Série vermelha: consumo total.
* Série preta: entradas totais.
* Label: mês abreviado em português.
* Sem colorbar.
* Tooltip customizado.

Esse gráfico deve responder:
**“O estoque está saindo mais do que está entrando?”**

### C. Relatórios — Consumo Mensal (Consumo x Entradas)

Esse deve ser um segundo gráfico, igual ao seu mock de linhas.

* Tipo: linha com marcador.
* Vermelho: consumo.
* Preto: entradas.
* Período padrão: últimos 6 meses.
* Linha vertical opcional no mês selecionado/hover.
* Tooltip customizado.
* Legenda inferior.

Esse gráfico é útil para tendência, não para ranking.

Regra: usar linha apenas quando houver pelo menos 2 meses. Com 1 mês, mostrar card/tabela, não linha.

### D. Relatórios — Por Categoria

Hoje soma todo o histórico de saída por categoria e usa `color="total_saida"` com escala contínua vermelha.  Isso cria uma colorbar lateral desnecessária.

Especificação proposta:

* Adicionar filtro de período: últimos 3, 6, 12 meses ou todo histórico.
* Tipo: barra vertical se houver até 6 categorias.
* Tipo: barra horizontal se houver mais de 6 categorias.
* Cor fixa: vermelho.
* Ordenar por maior consumo.
* Mostrar valor no topo/final da barra.
* Remover escala contínua.

Esse gráfico deve responder:
**“Qual família de itens mais consome estoque?”**

### E. Relatórios — Por Setor

Hoje esse gráfico já está conceitualmente correto: soma saídas por setor nos últimos N meses. 

Ajustes recomendados:

* Manter barra horizontal.
* Remover colorbar lateral.
* Usar vermelho para o setor mais consumidor e cinza/preto para os demais, ou uma única cor escura.
* Destacar `Sem setor` em cinza ou laranja, porque é problema de qualidade de dado.
* Adicionar KPI acima do gráfico:
  `Total retirado`, `Setores com consumo`, `% sem setor`.

Esse gráfico deve responder:
**“Quais setores estão retirando mais itens?”**

### F. Relatórios — Por Item

Hoje o serviço agrupa por `item`, `categoria` e `setor`.  Isso pode distorcer o Top Itens quando o filtro está em “Todos os setores”, porque o mesmo item pode aparecer quebrado por setor.

Especificação correta:

* Se filtro = **Todos os setores**: agrupar por `item + categoria`.
* Se filtro = **Setor específico**: agrupar por `item + categoria + setor`.
* Gráfico: barra horizontal top 10 ou top 20.
* Cor: vermelho para maior consumo; preto/cinza para barras secundárias.
* Tabela abaixo mantém detalhamento por setor.

Esse gráfico deve responder:
**“Quais itens mais saem do estoque?”**

### G. Histórico de Movimentações

A aba atual é tabela, e isso está correto. Histórico transacional não precisa virar gráfico por padrão.

Melhorias recomendadas:

* Filtro por período.
* Filtro por item.
* Filtro por categoria.
* Filtro por setor.
* Filtro por tipo: entrada, saída, todos.
* Badge visual para tipo:
  * Entrada: preto/cinza;
  * Saída: vermelho;
  * Sem setor: laranja/cinza.

---

## 4. Novos gráficos que fazem sentido para o sistema - Aba "Consumo Mensal"

Eu quero alinhar o existente e adicionaria este:

### 1. Consumo mensal consolidado

Prioridade alta.
É o gráfico mais importante para a página de Relatórios.

Mostra:
* consumo total mensal;
* entradas totais mensais.

### 2. Consumo x Entradas

Prioridade alta.
Serve para ver tendência e desequilíbrio.

Regra visual:

* vermelho = consumo;
* preto = entrada;
* tooltip claro;
* últimos 6 meses por padrão.

---

## 5. Ajustes técnicos recomendados

### Criar helpers em `core/ui.py`

Em vez de repetir `fig.update_layout()` em cada página, crie funções como:

```python
DFEB_COLORS = {
    "red": "#E10600",
    "black": "#262626",
    "gray": "#9CA3AF",
    "grid": "#E5E5E5",
    "muted": "#737373",
    "green": "#16A34A",
    "orange": "#F59E0B",
}

def apply_chart_theme(fig, height=320, showlegend=False):
    fig.update_layout(
        height=height,
        paper_bgcolor="#FFFFFF",
        plot_bgcolor="#FFFFFF",
        font=dict(family="Inter, system-ui, sans-serif", size=12, color="#262626"),
        margin=dict(t=24, r=20, b=36, l=48),
        showlegend=showlegend,
        xaxis=dict(
            gridcolor="#E5E5E5",
            zeroline=False,
            tickfont=dict(size=11, color="#737373"),
        ),
        yaxis=dict(
            gridcolor="#E5E5E5",
            zeroline=False,
            tickfont=dict(size=11, color="#737373"),
        ),
    )
```

### Criar wrapper visual para card de gráfico

Hoje os gráficos aparecem dentro do fluxo padrão do Streamlit. Para chegar no visual do mock, o ideal é ter um componente visual tipo:

```python
def chart_title(title: str):
    st.markdown(
        f"""
        <div class="dfeb-chart-card-title">{title}</div>
        """,
        unsafe_allow_html=True,
    )
```

E no CSS global:

```css
.dfeb-chart-card-title {
    border: 1px solid #E5E5E5;
    border-bottom: none;
    border-radius: 6px 6px 0 0;
    padding: 12px 16px;
    background: #FFFFFF;
    color: #0A0A0A;
    font-size: 14px;
    font-weight: 600;
}
```

O Streamlit dificulta encapsular totalmente o `st.plotly_chart()` dentro de uma div, mas dá para simular bem com título/card + gráfico logo abaixo.

### Remover `color_continuous_scale` dos rankings

Nos gráficos de categoria, setor e item, o ideal é parar de usar escala contínua para o mesmo valor da barra. Hoje isso acontece em “Por Categoria”, “Por Setor” e “Por Item”.   

Trocar por:

```python
fig.update_traces(marker_color="#E10600")
fig.update_layout(coloraxis_showscale=False)
```

### Corrigir labels técnicos

No gráfico de status, a interface não deve exibir `sem_minimo_definido`. O código já possui `_STATUS_LABELS`, mas a legenda ainda usa o campo técnico `status`. 

O gráfico deve colorir e legendar por `status_label`, ou então usar `category_orders` e `legendgroup` manualmente.

---

## 6. Nova organização ideal da página Relatórios

Eu reorganizaria a página assim:

### Aba 1 — Consumo Mensal

Conteúdo:

1. Filtros: período, categoria opcional, item opcional.
2. Card grande: **Consumo mensal — visão consolidada**.
3. Dois cards menores:
   * **Consumo x Entradas**
4. Tabela resumida por mês.

### Aba 2 — Por Categoria

Conteúdo:

1. Filtro período.
2. Gráfico ranking de categorias.
3. Tabela com total, nº de itens movimentados e % do consumo.

### Aba 3 — Por Setor

Conteúdo:

1. Filtro período.
2. KPI: total retirado, setores ativos, sem setor.
3. Ranking por setor.
4. Detalhamento por setor.

### Aba 4 — Por Item

Conteúdo:

1. Filtro período.
2. Filtro setor.
3. Top itens por consumo.
4. Tabela detalhada.

### Aba 5 — Histórico

Conteúdo:

1. Filtros operacionais.
2. Tabela limpa.
3. Exportação futura.

## 7. Critérios de aceite para a etapa de gráficos

Para considerar essa etapa bem implementada:

* Nenhum gráfico deve exibir enum técnico como `sem_minimo_definido`.
* Nenhum ranking simples deve ter colorbar lateral.
* Todo gráfico deve ter título claro e responder uma pergunta operacional.
* Todo gráfico temporal deve ter eixo mensal legível.
* Vermelho deve significar consumo, crítico ou ação prioritária — não decoração aleatória.
* “Por Item” não deve duplicar item por setor quando o filtro estiver em “Todos os setores”.
* Os gráficos devem usar um helper visual central, não estilos soltos em cada página.
