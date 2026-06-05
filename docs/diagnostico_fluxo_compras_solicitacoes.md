# Camada de Compras — Fluxo Completo e Funcionamento E2E

## Visão geral

O sistema agora opera com um ciclo de **5 etapas ordenadas**, com dois atores distintos: o **solicitante** (setor/funcionário externo ao sistema) e o **responsável de compras** (usuário interno):

```
[Solicitante]                    [Responsável de Compras]
      │                                     │
      ▼                                     │
Preenche /solicitar                         │
      │                                     │
      ▼                                     ▼
SolicitacaoMaterial          Compras → aba Solicitações
  status="pendente"            → Classificar → Consolidar
                                → Lista Final → Orçamentos
```

### Atores e pontos de entrada

| Ator | Onde acessa | O que faz | 
| --- | --- | --- | 
| Solicitante (setor) | http://localhost:8501/solicitar | Preenche e envia pedido de materiais | 
| Responsável compras | Sistema principal → Compras → aba Solicitações | Classifica, valida e consolida | 

---

## Fluxo E2E passo a passo

### Etapa 1 — Solicitante preenche o formulário externo (/solicitar)

O solicitante acessa a URL diretamente (sem sidebar, sem login). A página é limpa e focada no formulário.

* **Seção 1 — Identificação:**
  - Seleciona o setor (carregado do banco)
  - Informa o nome do solicitante
  - Seleciona o período (mês atual ou próximo, gerado automaticamente)

* **Seção 2 — Adicionar Itens (Dois filtros combinados que reduzem a lista no `st.selectbox`):**
  - Filtro de categoria (selectbox) — restringe ao grupo desejado
  - Busca por nome (text input) — refina dentro da categoria
  - O selectbox de item exibe os resultados filtrados; ao digitar dentro dele, o Streamlit filtra nativamente
Após selecionar o item:
  - Informa quantidade
  - Informa observação (opcional)
  - Clica "＋ Adicionar ao Pedido"

> O item entra em st.session_state["sol_itens"] — uma lista local de dicts mantida durante a sessão. Nada é salvo no banco ainda.

* **Seção 3 — Solicitar Novo Item (expander):**
Quando o material não existe no catálogo:
  - Preenche nome livre, quantidade e observação
  - Clica "＋ Adicionar ao Pedido"
  - Entra no mesmo session_state com item_id=None e tipo="Novo"

* **Seção 4 — Revisão e Envio:**
O solicitante vê o resumo de tudo que adicionou — badges "Catálogo" (azul) vs "Novo Item" (laranja), com opção de remover.

Ao clicar "Enviar Solicitação", o sistema percorre cada item da lista e chama criar_solicitacao() para cada um, gravando em solicitacoes_material com:
  - status = "pendente"
  - periodo_referencia = data selecionada
  - setor_id = FK para Setor
  - item_id = FK para Item (ou NULL se novo)
  - nome_item_livre = NULL (ou texto livre se novo)

> Após o envio: tela de confirmação. O session_state é limpo.

### Etapa 2 — Responsável classifica as solicitações recebidas

No sistema principal: **Compras → aba "Solicitações"**

1. **O que o responsável vê**

* **Métricas do período selecionado:**
  - ⏳ Pendentes — recém chegadas, ainda não classificadas
  - ✅ Validadas — prontas para consolidar
  - 🆕 Novos Itens — itens sem cadastro
  - ⚙️ Sem Parâmetros — itens existentes mas sem mínimo/ideal definido
* **Link da landing page para compartilhar com os setores**

2. **Ao clicar "Classificar Solicitações Pendentes":**

O sistema chama `classificar_solicitacoes_periodo(session, periodo)` que percorre todos os registros status="pendente" do período e aplica as regras:

```
item_id presente?
    ├─ item tem estoque_minimo_vigente E estoque_ideal_vigente?
    │       └─ SIM  →  status = "validada"
    │       └─ NÃO  →  status = "pendente_parametrizacao"
    └─ item_id é NULL (nome livre)
            └─  status = "pendente_cadastro"
```

> As três tabelas expandíveis mostram os itens por grupo, com botão de excluir por linha.

### Etapa 3 — Responsável consolida o período

Compras → aba "Consolidação" (fluxo existente, agora com filtro novo)

Ao clicar "Consolidar Período", consolidar_periodo() executa:

1. Carrega todos os Item.ativo=True do banco
2. Busca SolicitacaoMaterial do período filtrado por status="validada" apenas ← nova restrição
3. Para cada item, soma as quantidades de todas as solicitações validadas → total_solicitado
4. Passa para o StockAnalyzer.run_consolidado() que calcula o status e quantidade_sugerida com base em:
estoque_atual vs estoque_minimo_vigente vs estoque_ideal_vigente
total_solicitado (demanda dos setores)
5. Faz upsert em itens_lista_compra (preserva decisões manuais anteriores se já existiam)

> Itens pendente_cadastro e pendente_parametrizacao não entram aqui — ficam registrados mas isolados.

### Etapa 4 — Responsável revisa e aprova itens

Compras → aba "Painel de Reposição":
- KPIs de status: Zerados, Abaixo do Mínimo, Comprar, Excesso, Sem Mínimo
- Tabelas filtráveis por status e categoria

Compras → aba "Consolidação":
- Tabela editável com quantidade_final_definida e motivo (override manual)
- Botão de aprovação por item → flag incluir_na_lista_final = True
- Botão de remover da lista → incluir_na_lista_final = False

### Etapa 5 — Lista final e orçamentos

Compras → aba "Lista Final":
- Exibe apenas os ItemListaCompra com incluir_na_lista_final=True
- Fonte direta para a geração de documentos (DOCX)

### Tabelas do banco afetadas por etapa

| Etapa | Tabela | Operação | 
| --- | --- | --- | 
| 1 — Envio do formulário | solicitacoes_material | INSERT (status=pendente) | 
| 2 — Classificação | solicitacoes_material | UPDATE status | 
| 3 — Consolidação | itens_lista_compra | UPSERT (preserva edições manuais) | 
| 4 — Aprovação | itens_lista_compra | UPDATE incluir_na_lista_final, qtd_final, motivo | 
| 5 — Orçamento | snapshots_analise | Leitura / atualização via run_analysis | 

---

## Cenários de negócio e como o sistema responde

### Cenário A — Solicitação normal (item com parâmetros)

**Setor envia "Papel A4 Resma, qtd 5, Escritório"**

1. Grava status="pendente", item_id=7
2. Classificação: item 7 tem estoque_minimo_vigente=10, estoque_ideal_vigente=30 → status="validada"
3. Consolidação: total_solicitado=5 entra no cálculo do StockAnalyzer
4. Resultado: quantidade_sugerida considera tanto a demanda quanto o nível de estoque

### Cenário B — Item sem mínimo/ideal configurado

**Setor envia "Rolo de Fita Silver, qtd 2, Manutenção"**

1. Grava status="pendente", item_id=34
2. Classificação: item 34 tem estoque_minimo_vigente=NULL → status="pendente_parametrizacao"
3. Não entra na consolidação
4. Aparece na aba Solicitações → expander "⚙️ Sem Parâmetros"
5. Ação necessária: responsável configura mínimo/ideal em Estoque, reclassifica o período

### Cenário C — Item novo (não está no catálogo)

**Setor envia "Cabo HDMI 10m" (texto livre)**

1. Grava status="pendente", item_id=NULL, nome_item_livre="Cabo HDMI 10m"
2. Classificação: item_id é NULL → status="pendente_cadastro"
3. Não entra na consolidação
4. Aparece na aba Solicitações → expander "🆕 Novos Itens"
5. Ação necessária: responsável cadastra o item em Estoque, definir corretamente oque ocorre posteriormente.

### Cenário D — Mesmo item pedido por múltiplos setores

**Setor A pede "Detergente 5L, qtd 3" e Setor B pede "Detergente 5L, qtd 5"**

1. Dois registros em solicitacoes_material com o mesmo item_id, ambos status="validada"
2. Em consolidar_periodo(): o agrupamento soma total_solicitado = 3 + 5 = 8
3. O StockAnalyzer considera total_solicitado=8 junto com o estoque atual
4. ItemListaCompra tem um único registro por (item_id, periodo_referencia) com o total agregado

### Cenário E — Reconsolidação após mudança

**Responsável recebeu mais solicitações após a primeira consolidação**

1. Mais itens chegam via /solicitar com status="pendente"
2. Responsável classifica novamente (só os "pendentes" são processados)
3. Clica "Consolidar Período" novamente
4. O upsert preserva quantidade_final_definida e motivo de itens que já foram editados manualmente, atualizando apenas os dados de estoque e total_solicitado

---

## Regras de negócio críticas

| Regra | Onde está | 
| --- | --- | 
| Item novo nunca entra na consolidação automática | classificar_solicitacoes_periodo() → status="pendente_cadastro" não é consolidado | 
| Sem mínimo/ideal = sem consolidação | classificar_solicitacoes_periodo() → status="pendente_parametrizacao" | 
| Consolidação só processa "validada" | consolidar_periodo() → filtro status == "validada" | 
| Edições manuais do responsável são preservadas em re-consolidações | consolidar_periodo() → upsert com if not editado_manualmente: | 
| Formulário externo não expõe nenhuma tela interna | Solicitar.py registrado sem link no sidebar; sidebar oculta por CSS | 
