## Camada atual dos gráficos

A camada gráfica está concentrada principalmente em:

1. **`pages/Visao_Geral.py`**
   Responsável pelo gráfico **Status por Categoria** e pelos KPIs da visão geral. A página calcula o status ao vivo com `StockAnalyzer`, usando `estoque_minimo_vigente` e `estoque_ideal_vigente`, sem depender de snapshot salvo.  

2. **`pages/Relatorios.py`**
   Responsável pelos gráficos de **Consumo Mensal**, **Por Categoria**, **Por Setor**, **Por Item** e pela tabela de **Histórico de Movimentações**. Os gráficos são feitos com `plotly.express` e recebem um tema comum via `apply_plotly_theme(fig)`. 

3. **`core/ui.py`**
   Centraliza CSS global, componentes visuais básicos e o tema Plotly. Hoje o tema define fundo, fonte, margens, grid, colorway e legenda, mas ainda é genérico demais para resolver cada tipo de gráfico.  

4. **`services/relatorio_service.py`**
   Entrega os DataFrames dos relatórios. A regra central é: relatórios de consumo usam somente movimentações do tipo `"saida"`.  

---

## Regras operacionais já existentes

O sistema já está bem orientado por movimentações. A tabela `Movimentacao` guarda `entrada`/`saida`, quantidade anterior, quantidade nova, motivo, setor e `retirado_por`, que é essencial para os relatórios por setor e histórico. 

A Visão Geral não calcula “consumo”; ela calcula **situação atual de estoque**. O motor considera:

* `zerado`: estoque atual igual a zero e com limites definidos;
* `sem_minimo_definido`: mínimo e ideal iguais a zero;
* `comprar`: estoque atual menor ou igual ao mínimo;
* `ok`: acima do mínimo.

A recomendação de compra é calculada até o estoque ideal. 

Também existe uma camada mais recente de revisão mensal automática. Na abertura do app, o sistema verifica se já houve revisão no mês; se não houve, executa `executar_revisao_mensal`.  Essa revisão usa os últimos 3 meses fechados, gera mínimo/ideal sugeridos, respeita valores manuais e registra histórico em `RevisaoMensal`. 

---

## Diagnóstico visual dos gráficos atuais

### 1. Status por Categoria

O gráfico atual usa barras empilhadas por status, o que faz sentido conceitualmente. O problema está na apresentação.

No código, existe mapeamento para nomes amigáveis como `Comprar`, `Zerado`, `Sem Limite` e `OK`, mas o gráfico ainda colore por `status`, ou seja, pelo valor técnico interno. Por isso a legenda aparece como `sem_minimo_definido`, não como “Sem Limite”.  

Isso é ruim para uma tela operacional. O usuário não deveria ver enum interno do sistema no gráfico.

Também há outro ponto: como muitos itens estão sem limite definido, o cinza domina visualmente. Isso não é erro do gráfico, mas evidencia que a tela deveria separar melhor “cadastro incompleto” de “risco de estoque”. Hoje os dois aparecem na mesma leitura visual.

### 2. Consumo Mensal

Esse é o gráfico mais problemático.

O serviço retorna `mes` como string no formato `"YYYY-MM"`.  O gráfico usa `px.line` com `x="mes"` e `markers=True`. 

Pelo print, o eixo X está sendo interpretado como data contínua com microvariações ao redor de `Jun 1, 2026`, gerando labels como `23:59:59.999`, `00:00:00.0005`, etc. Isso destrói a leitura do gráfico. Para relatório mensal, o eixo deve ser categórico ou formatado explicitamente como mês/ano.

Além disso, com poucos pontos, linha não é a melhor escolha. Linha sugere tendência temporal; com um único mês ou poucos meses, o gráfico vira ruído. Nesse caso, barra mensal agrupada ou tabela-resumo pode ser mais honesta.

### 3. Por Categoria

O gráfico por categoria usa `color="total_saida"` com escala contínua vermelho-claro → vermelho. 

Isso explica a barra gigante com uma colorbar lateral no print. Para uma única métrica quantitativa em barras, essa escala contínua não agrega muito. A própria altura/comprimento da barra já comunica o volume. A colorbar consome espaço, polui a tela e cria uma segunda codificação visual redundante.

Outro problema: o relatório por categoria não tem filtro de período na interface atual, diferente de “Por Setor” e “Por Item”. O serviço soma todas as saídas existentes.  Isso pode gerar uma leitura enganosa: o usuário vê “consumo total”, mas não sabe se está olhando tudo desde o início do sistema ou um recorte recente.

### 4. Por Setor

Esse gráfico já está melhor encaminhado: usa barra horizontal, ordena por total e exibe o valor fora da barra. 

O problema é o mesmo padrão de cor contínua com colorbar lateral. Para ranking de setores, uma barra horizontal com cor fixa ou uma paleta discreta por intensidade controlada seria suficiente. A escala azul lateral não ajuda muito na tomada de decisão.

A regra de dados está correta para o objetivo: soma saídas nos últimos N meses e agrupa por setor, usando “Sem setor” quando a saída não possui setor. 

### 5. Por Item

A escolha de barra horizontal para ranking de consumo por item é adequada. O gráfico limita visualmente ao top 20, o que evita uma lista gigante. 

Mas há um problema semântico: o serviço agrupa por `item`, `categoria` e `setor`.  Quando o filtro está em “Todos os setores”, o mesmo item pode aparecer fragmentado por setor, em vez de consolidado por item. No print, isso ainda não explode porque há poucos dados, mas em uso real pode gerar repetição de item e distorcer o “Top itens”.

Para “Por Item”, o agrupamento ideal depende do filtro:

* com setor específico: agrupar por item dentro daquele setor;
* com todos os setores: agrupar por item total, e deixar setor para detalhamento/tabela.

### 6. Histórico de Movimentações

Hoje essa aba é tabela, não gráfico. Ela permite filtrar por tipo e limite de registros. 

Isso faz sentido. Histórico transacional não precisa virar gráfico por padrão. A melhoria futura aqui seria mais de UX: filtros por período, item, categoria, setor e tipo; não necessariamente visualização gráfica.

---

## Problemas prioritários antes de mexer em estética

A ordem correta não é “trocar cores”. É esta:

1. **Corrigir semântica dos dados exibidos**
   Principalmente o gráfico “Por Item”, que pode misturar item + setor de forma inadequada.

2. **Corrigir eixo temporal do Consumo Mensal**
   O eixo atual está visualmente quebrado nos prints.

3. **Remover colorbars redundantes**
   Categoria, setor e item usam cor contínua para a mesma métrica que já está no tamanho da barra. Isso deixa a tela menos limpa sem entregar informação adicional.

4. **Padronizar legenda e labels finais para usuário**
   Nada de `sem_minimo_definido` na interface. O código já tem labels amigáveis, mas eles ainda não foram aplicados corretamente na legenda do gráfico de status.

5. **Criar um helper de gráfico mais forte em `core/ui.py`**
   Hoje `apply_plotly_theme()` resolve estilo global básico, mas cada gráfico ainda precisa configurar altura, margem, legenda, hover, rótulos, ordenação e modo de exibição manualmente. 

---

## Camada que deve ser trabalhada na próxima etapa

A intervenção deve ficar principalmente em:

* `core/ui.py`: criar padrões reutilizáveis de gráfico;
* `pages/Relatorios.py`: ajustar construção dos gráficos e filtros;
* `pages/Visao_Geral.py`: corrigir legenda/status e melhorar leitura do gráfico empilhado;
* `services/relatorio_service.py`: ajustar agregações quando necessário, principalmente “Por Item”.

Não parece necessário mexer no motor de cálculo de estoque para essa etapa. O motor de status e revisão mensal pertence à lógica operacional; os problemas identificados agora estão mais na camada de apresentação e agregação dos relatórios.
