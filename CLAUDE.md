# CLAUDE.md

Este arquivo fornece orientações para o Claude Code (claude.ai/code) ao trabalhar com o código deste repositório.

## Execução

```bash
# Instalar dependências
pip install -r requirements.txt

# Iniciar o sistema
streamlit run app.py
# Disponível em http://localhost:8501
```

O banco `storage/estoque.db` é criado automaticamente na primeira execução. Nenhuma suíte de testes ou ferramenta de lint está configurada.

### Links Públicos (gerados via APP_BASE_URL)
- Formulário de Solicitação (setores): `$APP_BASE_URL/solicitar`
- Aprovação de Orçamentos (diretor): `$APP_BASE_URL/Aprovacao_Orcamento?id={id}`

## Arquitetura

Aplicação Streamlit multipágina para gestão de estoque, compras, ciclo mensal de solicitações de materiais e orçamentos. Usa SQLite via SQLAlchemy 2.0. O arquivo de dados fica em `storage/estoque.db` (criado automaticamente na primeira execução; migrações de schema idempotentes rodam em `init_db()`).

**Camadas:**

- **`app.py`** — Ponto de entrada; configura a navegação do Streamlit e dispara a revisão mensal automática de parâmetros quando o mês vira. Registra também a rota pública `/Aprovacao_Orcamento` (sem sidebar, acessada pelo diretor via link).
- **`pages/`** — Camada de UI. Cada arquivo é uma página Streamlit. As páginas chamam serviços; elas nunca acessam o banco de dados diretamente.
  - `Home.py`, `Visao_Geral.py`, `Estoque.py`, `Compras.py`, `Relatorios.py` — páginas internas padrão.
  - `Orcamentos.py` — ciclo de cotação/aprovação. Três abas: **Painel** (métricas e ações globais), **Cotações** (entrada de cotações por item, com apoio a fornecedores via WhatsApp e links de marketplace), **Histórico** (auditoria e download de DOCX).
  - `Aprovacao_Orcamento.py` — página pública sem sidebar (URL param `?id=`), acessada pelo diretor via link WhatsApp. Permite aprovar/reprovar/devolver itens individualmente e registrar a decisão final.
  - `Solicitar.py` — formulário público que os setores recebem via WhatsApp.
  - `Pedido_de_Compra.py` — registro administrativo de solicitação.
- **`services/`** — Lógica de negócio. As funções aqui são o único local que lê/escreve no banco de dados:
  - `estoque_service.py` — CRUD de item/categoria/setor/movimentação.
  - `fornecedor_service.py` — fornecedores + cotações (`get_best_price`/`get_best_prices_bulk`: preferencial primeiro, depois menor cotação válida, respeitando `validade_dias`). `create_fornecedor` também disponível para cadastro direto durante cotação.
  - `compras_service.py` — solicitações de materiais (pedido atômico, triagem/classificação, aprovação), consolidação do período (`consolidar_periodo`), Lista Final e compras avulsas. Funções adicionadas: `has_pending_changes`, `get_periodos_com_atividade`, `resetar_quantidades_consolidacao`.
  - `ciclo_service.py` — ciclo mensal de solicitações: abertura/encerramento/prorrogação/deleção, participação por setor e disparo das notificações.
  - `notificacao_service.py` — envio WhatsApp via Meta Cloud API (templates pré-aprovados). Sem dependência de Streamlit ou banco; falha graciosamente sem credenciais. Funções adicionadas: `cotacao_configurada` (verifica credenciais) e `enviar_solicitacao_cotacao` (envia pedido de preço a fornecedor).
  - `calculos_service.py` — revisão mensal automática de mínimo/ideal (persiste `RevisaoMensal`) e overrides manuais.
  - `orcamento_service.py` — ciclo completo de orçamento a partir da Lista Final: criação de snapshot versionado, CRUD de cotações (`add_cotacao`, `editar_cotacao`, `remover_cotacao`, `escolher_cotacao`), resumo financeiro (`get_resumo`, `ResumoOrcamento`), fluxo de aprovação (`enviar_para_aprovacao`, `registrar_decisao_diretor`, `criar_nova_versao`), sincronização com Lista Final (`sincronizar_com_lista_final`) e helpers WhatsApp para solicitação de cotação a fornecedores (`gerar_mensagem_whatsapp`, `registrar_solicitacao_enviada`).
  - `relatorio_service.py` — DataFrames para relatórios.
- **`data/`** — Persistência:
  - `config.py` — Caminhos de storage (`STORAGE_DIR`, `DB_PATH`, `DATABASE_URL`, `EXPORTS_DIR`, `UPLOADS_DIR`).
  - `database.py` — Engine singleton do SQLAlchemy, `get_session_factory()`, `init_db()` e `run_schema_migrations()` (ALTERs idempotentes por fase numerada, saneamento de pedidos órfãos e migração única de timestamps UTC→hora local, com backup automático e marcador em `schema_meta`).
  - `models.py` — Modelos ORM: `Categoria`, `Item`, `Fornecedor` (+ campo `website`), `PrecoFornecedor`, `Setor`, `Movimentacao`, `SnapshotAnalise`, `RevisaoMensal`, `CicloSolicitacaoMaterial`, `CicloSolicitacaoSetor`, `SolicitacaoPedido`, `SolicitacaoMaterial`, `CompraAvulsa`, `ItemListaCompra`. **Camada de orçamentos:** `Orcamento`, `ItemOrcamento`, `CotacaoOrcamento`, `SolicitacaoCotacaoFornecedor`.
- **`core/`** — Infraestrutura de aplicação:
  - `schemas.py` — Schemas Pydantic para validação de entrada (usados antes da persistência).
  - `engine.py` — Motor **sem estado** de análise de reposição (`StockAnalyzer`). Sem dependências de banco de dados ou Streamlit. Três variantes: `calcular_status_puro` (Painel de Reposição), `calcular_status_consolidado` (Análise de Compras, cruza estoque com solicitações aprovadas) e `calcular_status` (legada). Seguro para testar diretamente com testes unitários.
  - `calculos.py` — Cálculo estatístico da revisão mensal (mediana/percentis de consumo, janela de análise). Também sem estado.
  - `tempo.py` — Helpers de data/hora: `tempo.agora()` e `tempo.hoje()`. **Política de fuso: todo o sistema opera em hora local de Brasília (America/Sao_Paulo), naive.** Nunca usar `utcnow()`, `now()` ou `date.today()` diretos.
  - `ui.py` — Utilitários compartilhados do Streamlit: CSS, cabeçalhos, badges, formatação BRL, tema Plotly, link do formulário público.
  - `config.py` — Variáveis de ambiente da aplicação: `APP_BASE_URL` (links do formulário e aprovação), senha administrativa, credenciais WhatsApp `WA_ACCESS_TOKEN`, `WA_PHONE_NUMBER_ID`, `WA_TEMPLATE_*`, `WA_TEMPLATE_LANG` e ntfy.
- **`documents/`** — Geração de DOCX via python-docx. Exportações salvas em `storage/exports/` com timestamps.
  - `lista_compras.py` — documento da Lista Final de Compras.
  - `orcamento.py` — `gerar_documento_cotacao`: documento de cotação para aprovação do diretor, com resumo financeiro, tabela por categoria e cotações alternativas.
  - `relatorio_categoria.py`, `relatorio_consumo.py`, `relatorio_historico.py`, `relatorio_item.py`, `relatorio_setor.py` — geradores DOCX para cada aba da página de Relatórios.
- **`storage/`** — Artefatos runtime ignorados pelo Git: banco SQLite, uploads, exports e backups.

## Modelo de Dados Principal

```
Categoria 1──M Item
                 ├── M─M Fornecedor   (via item_fornecedores join table; Fornecedor agora tem campo website)
                 ├── 1─M Movimentacao (entrada/saida, com setor e retirado_por)
                 ├── 1─M PrecoFornecedor (cotações, com validade)
                 ├── 1─M SnapshotAnalise (recomendações de reposição)
                 ├── 1─M RevisaoMensal (histórico do cálculo automático de mínimo/ideal)
                 ├── 1─M SolicitacaoMaterial (pedidos dos setores)
                 └── 1─M ItemListaCompra (consolidação por período)
                              └── 1─M ItemOrcamento (snapshot no orçamento)

CicloSolicitacaoMaterial 1──M CicloSolicitacaoSetor (participação/notificações por setor)
                         1──M SolicitacaoPedido (cabeçalho atômico do formulário)
                                  └── 1─M SolicitacaoMaterial
                                            └── 1─M CompraAvulsa (item fora do catálogo)
                                                       └── 1─M ItemOrcamento (snapshot no orçamento)

Orcamento 1──M ItemOrcamento
                   └── 1─M CotacaoOrcamento  (cotações registradas por item)
Orcamento 1──M SolicitacaoCotacaoFornecedor  (rastreia envios WhatsApp a fornecedores)
Fornecedor 1──M SolicitacaoCotacaoFornecedor

Setor 1──M Movimentacao / SolicitacaoPedido
```

`Item` possui `estoque_minimo_vigente`/`estoque_ideal_vigente` (manual tem prioridade sobre o sugerido pela revisão mensal). O `StockAnalyzer` calcula status (`zerado` / `abaixo_minimo` / `abaixo_ideal` / `ok` / `sem_parametro`) e quantidade sugerida (demanda líquida vs. reposição ao ideal).

`Orcamento` é um snapshot versionado (`numero` = `ORC-YYYY-MM-NNN`, `versao` incremental). Estados: `RASCUNHO` → `EM_COTACAO` → `PRONTO_PARA_APROVACAO` → `ENVIADO_APROVACAO` → `APROVADO` / `APROVADO_PARCIAL` / `DEVOLVIDO_REVISAO` / `REPROVADO` / `CANCELADO`. `ItemOrcamento.cotacao_escolhida_id` aponta para a cotação vencedora (sem FK formal para evitar circularidade). `CotacaoOrcamento.total_calculado` é persistido como `qty * unit - desconto + outros + frete`.

## Fluxo do Ciclo de Solicitações (resumo)

1. Usuário de estoque abre o ciclo do período em **Compras** (`abrir_ciclo`) — cria participantes por setor ativo e notifica via WhatsApp com link do formulário.
2. Setores respondem pelo formulário **Solicitar** (`criar_pedido_solicitacao` — exige ciclo aberto e prazo vigente, validados na camada de serviço) ou marcam "sem necessidade" (bloqueado se o setor já enviou pedido).
3. Triagem em **Compras**: `classificar_solicitacoes_periodo` → aprovação/rejeição/vinculação/compra avulsa.
4. `consolidar_periodo` cruza estoque com solicitações **aprovadas** e persiste `ItemListaCompra` (preserva edições manuais em re-consolidações).
5. Itens aprovados (`incluir_na_lista_final`) seguem para Lista Final → **Orçamentos**.

## Fluxo de Orçamentos (resumo)

6. Em **Orçamentos**, `criar_orcamento` gera snapshot versionado da Lista Final — congela nome, categoria e quantidade de cada `ItemListaCompra` / `CompraAvulsa` em `ItemOrcamento`.
7. Responsável coleta cotações por item (`add_cotacao`) e escolhe a vencedora (`escolher_cotacao`). Pode solicitar preços a fornecedores cadastrados via WhatsApp (`registrar_solicitacao_enviada` + `enviar_solicitacao_cotacao`).
8. Quando todos os itens têm cotação escolhida, `enviar_para_aprovacao` bloqueia edição e gera link para o diretor (`/Aprovacao_Orcamento?id=...`).
9. Diretor acessa a página pública `Aprovacao_Orcamento.py`, decide por item (aprovar / reprovar / revisar) e registra decisão via `registrar_decisao_diretor` → status `APROVADO`, `APROVADO_PARCIAL` ou `DEVOLVIDO_REVISAO`.
10. Se devolvido, `criar_nova_versao` congela o orçamento anterior (para auditoria) e abre uma nova versão em `RASCUNHO`, com itens ainda bloqueados já com suas cotações preservadas.
11. Em qualquer ponto, `sincronizar_com_lista_final` adiciona itens novos que entraram na Lista Final depois da criação do orçamento.

## Sessões

Os serviços usam `get_session_factory()` de `data/database.py`. Padrão:

```python
SessionLocal = get_session_factory()
with SessionLocal() as session:
    ...
```

---

## Regras e Instruções de Execução
**Regras obrigatórias de economia (NÃO IGNORAR)**
1) **NÃO liste árvore inteira do projeto (evite `tree`, `ls -R`, etc.)**. Se precisar, liste apenas pastas-alvo da FASE.
2) **NÃO leia arquivos completos.** Leia no máximo 120 linhas por arquivo (ou trechos específicos). Se precisar de mais contextualização, peça antes.
3) **NÃO execute ações, mudanças ou qualquer outro tipo de refatoração em UI/UX, lógica ou que possam afetar diretamente no fluxo de navegação do usuario**, a menos que não tenha sido claramente aprovado e bem planejado.
4) Está totalmente liberado **sugerir, propor e recomendar mudanças e melhorias** que possam arrumar ou evoluir o sistema, porém elas devem ser aprovadas e bem explicadas antes da implementação/execução.
5) Priorize busca (grep) para localizar pontos de mudança antes de abrir arquivos.
6) **Não cole conteúdo integral de arquivos na resposta.** Mostre apenas:
   - arquivos alterados
   - resumo do diff (o que mudou e por quê)
   - comandos executados e resultados
7) Execute somente **UMA FASE por vez**. Ao terminar a FASE, pare e peça autorização para a próxima FASE.
8) Se detectar duplicação/overreach fora do escopo, **interrompa e reporte**.
9) **Todas as mudanças devem ser validadas rodando `streamlit run app.py` localmente** antes de considerar concluídas.
