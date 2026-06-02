O ponto fraco da etapa atual é este: **Setores não são apenas mais um filtro visual; eles mudam o modelo histórico da movimentação**, o sistema também parece monitorar o estoque, mas ainda não captura os dados necessários para isso.

Hoje `Movimentacao` guarda `item_id`, `tipo`, `quantidade`, saldo anterior/novo, `motivo`, `operador` e data. Não existe `setor`, então o sistema ainda não tem base histórica para consumo por setor.

* **Visão Geral:** mostra 153 itens, 153 sem limites definidos, 0 itens para comprar e “Nenhum item crítico”. Isso é enganoso. Se todos os itens estão sem mínimo/ideal, o sistema não tem base para dizer que não há criticidade.
* **Registrar Movimentação:** ainda tem `Operador`, mas não tem `Setor`. Isso impede qualquer análise séria de consumo por área.
* **Relatórios:** tem estrutura inicial, mas ainda está centrada em consumo mensal/categoria/histórico. Falta o eixo principal que você quer: **consumo por setor**.

---

# 1. Regras base e fluxo de trabalho do sistema

Antes de mexer nas páginas, precisa fechar o modelo lógico.

## Separação conceitual obrigatória

**Categoria** e **Setor** devem ser entidades diferentes.

| Conceito  | O que representa              | Exemplo                               |
| --------- | ----------------------------- | ------------------------------------- |
| Categoria | Família/classificação do item | Limpeza, Escritório, EPI, Informática |
| Setor     | Destino/área consumidora      | RH, Produção, Financeiro, Manutenção  |

Categoria responde: **“Que tipo de item é?”**
Setor responde: **“Para onde esse item saiu?”**

Essa separação é essencial porque o mesmo item da mesma categoria pode ser consumido por setores diferentes.

Exemplo:

```text
Item: Papel A4
Categoria: Escritório

Saída 1:
  Setor: RH
  Quantidade: 5

Saída 2:
  Setor: Financeiro
  Quantidade: 8
```

Se você misturar setor com categoria, perde a capacidade de medir consumo real por área.

---

## Entidades mínimas para esta etapa

### `Setor`

Criar uma nova tabela:

```text
setores
- id
- nome
- descricao
- ativo
```

Regras:

* `nome` deve ser único.
* Setor ativo aparece em novas saídas.
* Setor inativo não aparece para nova movimentação, mas continua em relatórios históricos.
* Setor com movimentações não deve ser excluído fisicamente.

---

### `Movimentacao`

Hoje a movimentação grava item, tipo, quantidade, saldo anterior, saldo novo, motivo, operador e data. A movimentação deve passar a guardar:
- id
- item_id
- tipo
- quantidade
- quantidade_anterior
- quantidade_nova
- setor
- retirado_por
- motivo
- criado_em

Mudança direta:

```text
operador → retirado_por
```

Mas com uma ressalva: **`retirado_por` não substitui `setor`**. São informações diferentes.

| Campo          | Função                             |
| -------------- | ---------------------------------- |
| `setor`        | Diz qual área consumiu o item      |
| `retirado_por` | Diz quem retirou, quando informado |
| `motivo`       | Explica contexto da movimentação   |

---

## Tipos de movimentação

Hoje o service aceita apenas `entrada` e `saida`, embora o modelo/comentários e a tela de relatórios mencionem também `ajuste` e `inventario`.  

A regra deve ser consolidada, apenas para `entrada` e `saida` assim:

| Tipo       |         Efeito no estoque | Setor obrigatório? | Uso                                          |
| ---------- | ------------------------: | -----------------: | -------------------------------------------- |
| Entrada    |             soma ao saldo |                Não | Compra, devolução ao almoxarifado, reposição |
| Saída      |          subtrai do saldo |                Sim | Retirada/consumo por setor                   |

> todas as referências aos outros tipos de movimentação devem ser removidos completamente do sistema atual.

---

## Regra para saída

A tela atual de movimentação tem Categoria, Item, Tipo, Quantidade, Motivo e Operador.  Essa estrutura é aproveitável, mas precisa ser dinâmica por tipo de movimentação.

A regra atual usa `max(qtd_anterior - quantidade, 0)`, ou seja, se tentar retirar mais do que existe, o sistema simplesmente zera o estoque. 

Isso é ruim. Deve bloquear.

Regra correta:

```text
Se quantidade de saída > estoque atual:
    bloquear movimentação
    informar erro
```

Exemplo:

```text
Estoque atual: 3
Saída solicitada: 10
Resultado correto: erro

Não deve virar estoque 0 silenciosamente.
```

---

## Fluxo operacional recomendado

### Entrada

Uso:

```text
Reposição de material no estoque.
```

Campos:

```text
Categoria
Item
Tipo = Entrada
Quantidade
Motivo / observação opcional
```

Regra:

```text
quantidade > 0
novo_saldo = saldo_atual + quantidade
```

Não pedir Setor. Entrada não é consumo.

---

### Saída / retirada

Uso:

```text
Retirada/consumo de item por algum setor.
```

Campos:

```text
Categoria
Item
Tipo = Saída
Quantidade
Setor
Retirado por, opcional
Motivo / observação, opcional
```

Regra:

```text
quantidade > 0
setor obrigatório
quantidade <= saldo_atual
novo_saldo = saldo_atual - quantidade
```

A regra atual zera estoque silenciosamente se a saída for maior que o saldo, usando `max(qtd_anterior - quantidade, 0)`.  Isso deve ser corrigido. Se há 1 unidade e o usuário tenta retirar 5, o sistema deve bloquear.


**Esse é o fluxo que alimenta:**
* consumo por setor;
* consumo por categoria;
* consumo por item;
* rankings de maiores consumidores;
* relatórios históricos;
* dashboards de consumo recente.

---

## 2. Página Estoque

A página Estoque deve ser a página operacional. Ela deve permitir consultar, movimentar e manter cadastros básicos.

Hoje ela já está organizada em três abas: `Visualizar`, `Registrar Movimentação` e `Editar`.  Essa divisão é boa. O ajuste é na responsabilidade de cada aba.

---

### Aba Visualizar

Responsabilidade:

```text
Mostrar a situação atual dos itens.
```

Não é relatório histórico. Não é dashboard completo. É a tabela operacional do estoque.

#### Filtros recomendados

```text
Buscar por nome
Categoria
Status
```

Status deveria permitir:

```text
Todos
OK
Comprar / abaixo do mínimo
Zerado
Sem limite definido
```

#### Tabela Mestre recomendada

A tabela atual já monta ID, categoria, item, unidade, atual, mínimo, ideal, última movimentação, tipo, fornecedores e observações. 

O ideal para esse sistema, é que não exista uma coluna exibindo `Status`, embora o service já calcule. Mas sim pelas cores das linhas na tabela, correspondendo ao status ideal de cada linha. 

Tabela ideal:

| Coluna              |       Obrigatória? | Observação                             |
| ------------------- | -----------------: | -------------------------------------- |
| ID                  |                Sim | Rastreabilidade                        |
| Categoria           |                Sim | Agrupamento                            |
| Item                |                Sim | Principal                              |
| Unidade             |                Sim | Contexto da quantidade                 |
| Atual               |                Sim | Saldo real                             |
| Mínimo              |                Sim | Base de alerta                         |
| Ideal               |                Sim | Base de reposição                      |
| Repor               |                Sim | `max(ideal - atual, 0)` quando crítico |
| Última movimentação |                Sim | Data/hora                              |
| Tipo última mov.    |                Sim | Entrada, saída, ajuste, inventário     |
| Setor última saída  | Sim, quando houver | Ajuda contexto                         |
| Fornecedor(es)      |           Opcional | Útil, mas não deve dominar a tela      |
| Observações         |           Opcional | Melhor como coluna final               |

#### Regra visual

Cores/labels:

```text
Zerado              → crítico
Comprar             → atenção
Sem limite definido → pendência cadastral
OK                  → normal
Inativo             → não mostrar/fora da operação
```

Ponto importante: **Sem limite definido não é OK**. Ele deve aparecer como pendência, não como ausência de problema.

---

### Aba Registrar Movimentação

Essa é a tela do segundo print. Ela deve ser ajustada sem reinventar o layout.

#### Estrutura mantida

Continuar com:

```text
Selecionar item
Dados da movimentação
Botão principal
```

#### Mudança principal

O campo atual:

```text
Operador (opcional)
```

deve virar:

```text
Retirado por (opcional)
```

Mas só deve aparecer para `Saída`.

Além disso, adicionar:

```text
Setor
```

também só para `Saída`, obrigatório.

---

### Especificação da tela por tipo

#### Quando Tipo = Entrada

Mostrar:
- Categoria
- Item
- Tipo
- Quantidade
- Motivo / observação

Não mostrar:
- Setor
- Retirado por

Botão:
- Registrar movimentação

Prévia recomendada:

```text
Saldo atual: 1
Novo saldo: 2
```

---

#### Quando Tipo = Saída

Mostrar:
- Categoria
- Item
- Tipo
- Quantidade
- Setor
- Retirado por (opcional)
- Motivo / observação (opcional)

Botão:
- Registrar movimentação

Validação:

```text
Se setor vazio:
    erro: Informe o setor de destino.

Se quantidade > estoque atual:
    erro: Saída maior que o estoque disponível.
```

Prévia:

```text
Saldo atual: 10
Novo saldo: 7
Setor: Financeiro
```

---

### Aba Editar

Hoje a aba Editar concentra Itens, Fornecedores e Categorias. 

Para a etapa atual, eu ajustaria para:
- Itens
- Categorias
- Setores
- Fornecedores

Com prioridade funcional assim:

1. Itens
2. Categorias
3. Setores
4. Fornecedores

Fornecedores são apoio. Setores viram essenciais por causa dos relatórios e dashboard.

#### Sub-aba Setores

Tabela:
- ID
- Nome
- Descrição
- Ativo

Deve permitir:
- Cadastrar setor
- Editar setor

Regra:
- Não excluir setor com movimentações.

---

## 3. Página Relatórios

A página de Relatórios deve ser **histórica, analítica e filtrável**. Ela não deve corrigir estoque, gerar compra nem alterar dados.

Hoje ela já segue parcialmente essa direção: `Consumo Mensal`, `Por Categoria` e `Histórico de Movimentações` sem alterar banco.  O `relatorio_service.py` também declara que retorna DataFrames para telas/gráficos e não persiste alterações. 

O problema é que os relatórios atuais ainda são pobres para monitoramento real.

### Responsabilidade da página

A página Relatórios deve responder perguntas como:
- O que foi consumido?
- Quanto foi consumido?
- Quando foi consumido?
- Qual categoria teve maior saída?
- Qual setor consumiu mais?
- Qual setor consumiu determinado item?
- Quem retirou, quando informado?
- Quais movimentações ocorreram em determinado período?
- Como o consumo evoluiu no tempo?

Ela não deve responder primariamente:
- O que preciso comprar agora?
- Qual fornecedor comprar?
- Qual valor estimado de compra?
- Qual orçamento gerar?

Isso fica em Compras/Orçamentos.

---

### Estrutura recomendada da página Relatórios

#### Aba 1 — Histórico de Movimentações

Gráficos e Tabelas completos e filtráveis.

Filtros:
- Período
- Tipo de movimentação
- Categoria
- Item
- Setor

Filtros avançados:
- Somente entradas
- Somente saídas

**Regra:**
- Relatórios de consumo usam apenas tipo = saída.
- Histórico pode mostrar todos os tipos.


Informações:
- Data
- Tipo
- Categoria
- Item
- Quantidade
- Saldo anterior
- Saldo novo
- Setor
- Retirado por
- Motivo

Essa aba é a auditoria operacional do estoque, deve mostrar entradas, saídas, ajustes e inventários.

Empty state correto:

```text
Nenhuma movimentação encontrada no período.
```

Não usar “nenhuma saída registrada” nessa aba, porque uma entrada também é movimentação.

---

#### Aba 2 — Consumo por Setor

Essa deve virar uma das abas principais e mais importantes.

Objetivo: Medir consumo por setor.

Dados considerados: Apenas movimentações tipo = saída

Filtros:
- Período
- Setor
- Categoria
- Item

Indicadores/KPIs:
- Total consumido / Total consumido no período
- Quantidade de retiradas
- Setor com maior consumo
- Itens consumidos
- Categoria mais consumida

Gráficos:
- Barra horizontal: consumo total por setor
- Barra empilhada: consumo por setor e categoria
- Tabela: setor x item x quantidade

Tabela:
- Setor
- Item
- Categoria
- Total consumido
- Quantidade de retiradas
- Última retirada

Essa aba nasce diretamente da nova exigência de monitorar saídas por setor.

---

#### Aba 3 — Consumo por Categoria

Já existe algo próximo no sistema: `consumo_por_categoria` soma movimentações de saída por categoria. 

Mas deve evoluir para incluir filtros e comparação com setor.

Objetivo: Mostrar quais famílias de item são mais consumidas.

Gráfico:
- Consumo total por categoria

Tabela:
- Categoria
- Total consumido
- Itens diferentes consumidos
- Setor que mais consumiu
- Item mais consumido

Campos úteis:
- Categoria
- Total consumido
- Quantidade de itens diferentes consumidos
- Setor que mais consumiu essa categoria

---

#### Aba 4 — Consumo por Item

Objetivo: identificar itens de maior giro.

Gráficos:
- Top 10 itens mais consumidos
- Evolução mensal dos itens mais consumidos

Tabela:
- Item
- Categoria
- Unidade
- Total consumido
- Quantidade de saídas
- Média por saída
- Última saída
- Setor que mais consumiu

---

#### Aba 5 — Evolução Mensal

A tela atual já tem consumo mensal por item. 

Objetivo: Mostrar tendência de consumo ao longo do tempo.

Gráficos:
- Linha: consumo mensal total
- categoria selecionada
- setor selecionado
- item selecionado

Filtros:
- Ano
- Mês inicial/final
- Categoria
- Setor
- Item

---

### O que Relatórios não deve fazer

Não deve:
- Registrar movimentação
- Editar item
- Alterar saldo
- Rodar análise de compras
- Gerar snapshot
- Decidir fornecedor

Relatórios lê o passado.
Visão Geral mostra o presente.
Compras sugere reposição.

---

## 4. Página Visão Geral

A Visão Geral deve ser o **painel operacional atual** do estoque.

Hoje ela depende de `get_latest_snapshot` e exibe dados vindos da análise de compras.  Isso cria o problema já citado: se o estoque muda por movimentação, mas ninguém roda a análise de compras, o dashboard pode ficar defasado.

Para monitoramento de estoque, isso deve mudar.

### Responsabilidade da Visão Geral

Ela deve responder de maneira rapida e direta:
- Como está o estoque agora?
- Quantos itens estão críticos?
- Quantos estão zerados?
- Quais categorias concentram risco?
- Quais itens tiveram maior saída recente?
- Quais setores mais consumiram recentemente?
- Quais itens precisam de atenção operacional?
- Quais movimentações aconteceram por último?

A tela deve ser alimentada por:
- itens atuais
- limites de estoque
- movimentações recentes
- setores
- categorias

Ela não deve depender de botão “Rodar Análise”, snapshot de compras.

O botão de análise pertence a Compras. Hoje `Compras.py` executa `run_analysis` e grava snapshots.  Isso faz sentido para compras, não para o dashboard principal.

---

### Layout recomendado da Visão Geral

#### Linha 1 — KPIs principais

Cards:
- Total de itens ativos
- Itens OK
- Itens abaixo do mínimo
- Itens zerados
- Itens sem limite definido

Hoje o sistema calcula apenas total de itens, itens sem mínimo e itens com mínimo. Isso é insuficiente para dashboard, a tela atual já tem cards, então é só trocar semântica e cálculo.

#### Linha 2 — KPIs de movimento recente

Novo bloco:
- Saídas nos últimos 30 dias
- Quantidade total consumida
- Setor com maior consumo
- Item mais consumido

Filtro no topo:
- Período: 7 dias / 30 dias / 90 dias

#### Linha 3 — Alertas operacionais

Status recomendados:
- Zerado
- Comprar
- Sem limite definido
- OK

---

### Gráfico com Diferentes Opções 

#### 1 — Status por Categoria

Esse gráfico já existe em parte na Visão Geral, mas hoje ele usa snapshot e agrupa por categoria/status. 

Deve usar status calculado diretamente dos itens atuais.

O desenho ideal:

```text
Eixo X: Categoria
Eixo Y: Quantidade de itens
Cor: Status operacional
Tipo: barra empilhada
```

Status:
- OK
- Abaixo do mínimo
- Zerado
- Sem limite definido

Objetivo: mostrar quais categorias estão concentrando risco com labels amigáveis, não nomes internos como `sem_minimo_definido`.

---

#### 2 — Consumo por Setor

Novo gráfico essencial, mostrar quais setores estão consumindo mais.

```text
Eixo X: Setor
Eixo Y: Quantidade consumida
Filtro padrão: últimos 30 dias
Tipo: barra horizontal
```

Sem isso, a Visão Geral não atende ao objetivo de monitoramento por setor.

---

#### 3 — Top Itens Consumidos

```text
Tipo: barra horizontal
Período padrão: últimos 30 dias
```

Colunas:
- Item
- Categoria
- Total consumido
- Nº de saídas
- Principal setor consumidor

Esse bloco ajuda a detectar itens de alto giro.

---

### Bloco — Itens de atenção

Separar em duas listas diferentes.

#### Lista 1: Críticos de estoque

Entram:
- Zerados
- Abaixo do mínimo

Colunas:
- Item
- Categoria
- Atual
- Mínimo
- Ideal
- Última movimentação

#### Lista 2: Pendências cadastrais

Entram:
- Sem limite definido
- Itens sem categoria válida, se acontecer
- Itens sem unidade, se acontecer

Colunas:
- Pendência
- Item
- Categoria
- Atual
- Ação sugerida

No cenário, essa lista teria 153 itens sem limite definido. Isso é mais honesto do que mostrar “Nenhum item crítico”.

---

### O que deve conter na Visão Geral

Minha recomendação final para a página:
1. KPIs de situação atual
2. Gráfico de status por categoria
3. Lista de itens críticos
4. Consumo por setor nos últimos dias
5. Top itens consumidos nos últimos dias

Não colocaria gráfico de fornecedor, cotação ou valor estimado nessa página neste momento. Isso puxa a tela de volta para Compras.

---

## 5. Regras e lógica gerais do controle de estoque

### Regra de status operacional

Centralizar uma única função de status.

Hoje a tabela mestre recalcula status dentro de `estoque_service.get_tabela_mestre`, enquanto o motor de análise também calcula status em `StockAnalyzer`.  

Isso deve ser unificado.

Regra recomendada:

```text
Se estoque_minimo = 0 e estoque_ideal = 0:
    status = sem_limite

Senão, se estoque_atual = 0:
    status = zerado

Senão, se estoque_atual <= estoque_minimo:
    status = comprar

Senão:
    status = ok
```

Sugestão de reposição:

```text
Se status em [zerado, comprar]:
    sugestao = max(estoque_ideal - estoque_atual, 0)
Senão:
    sugestao = 0
```

---

### Regra de limites

Validar sempre:

```text
estoque_minimo >= 0
estoque_ideal >= 0
estoque_ideal >= estoque_minimo
```

Hoje a tela já valida ideal menor que mínimo em alguns formulários.  Essa regra deve sair da tela e também existir no service, para não depender só da interface.

---

### Regra de item ativo/inativo

A regra ideal:

```text
Item ativo:
    aparece em movimentações
    aparece na tabela mestre padrão
    entra nos dashboards operacionais

Item inativo:
    não aparece para novas movimentações
    continua aparecendo em relatórios históricos
```

Evitaria exclusão física de item com histórico. Hoje `delete_item` remove permanentemente o item e registros dependentes em cascade.  Para controle de estoque, isso é perigoso porque apaga rastreabilidade histórica.

Melhor:

```text
Remover item = inativar item
Excluir definitivamente = apenas se nunca teve movimentação
```

---

### Regra de setor ativo/inativo

Mesma lógica:

```text
Setor ativo:
    aparece em novas saídas

Setor inativo:
    não aparece em novas saídas
    continua nos relatórios antigos
```

Não excluir setor que tem movimentação vinculada.

---

### Regra de movimentação

#### Entrada

```text
quantidade > 0
setor = null
retirado_por = null ou ignorado
estoque_atual += quantidade
```

#### Saída

```text
quantidade > 0
setor obrigatório
retirado_por opcional
quantidade <= estoque_atual
estoque_atual -= quantidade
```

---

### Regra para relatórios

Relatórios devem considerar:

```text
Movimentações de saída = consumo
Movimentações de entrada = reposição
```

Portanto:

```text
Consumo por setor deve usar apenas tipo = saida
Consumo por categoria deve usar apenas tipo = saida
Consumo mensal deve usar apenas tipo = saida
```

Ajuste negativo não deve entrar como consumo, senão os relatórios ficam contaminados.

---

### Regra para dashboard

Dashboard deve usar dois grupos de dados:

```text
Estado atual:
    itens
    estoque_atual
    estoque_minimo
    estoque_ideal
    categoria

Histórico recente:
    movimentações dos últimos 7/30 dias
    setores
    saídas
```

Não deve depender de snapshot de compras.

---

## 6. Consolidação final da lógica

Precisa existir uma regra única usada por:
- Tabela Mestre
- Visão Geral
- Relatórios
- Compras, quando necessário

Hoje há duplicidade: `StockAnalyzer` calcula status, e `get_tabela_mestre` recalcula status manualmente.  

Observação: `sem_limite_definido` não gera sugestão de compra porque o sistema não sabe qual seria o mínimo ou ideal.

**A arquitetura correta para esta etapa é:**

```text
Movimentações
    ↓
Atualizam saldo do item
    ↓
Geram histórico operacional
    ↓
Alimentam Relatórios
    ↓
Alimentam Dashboard / Visão Geral
    ↓
Opcionalmente alimentam Compras
```

Separação final:

| Página      | Papel                                                                     |
| ----------- | ------------------------------------------------------------------------- |
| Estoque     | Operar saldo, cadastrar itens/categorias/setores, registrar movimentações |
| Relatórios  | Analisar histórico de consumo e movimentações                             |
| Visão Geral | Monitorar situação atual e alertas operacionais                           |
| Compras     | Gerar recomendações de reposição, fornecedor e valor estimado             |

A mudança mais importante agora é **gravar setor na saída**. Sem isso, todo o restante sobre consumo por setor vira aproximação manual ou dado perdido.
