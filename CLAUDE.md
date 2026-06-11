# CLAUDE.md

Este arquivo fornece orientações para o Claude Code (claude.ai/code) ao trabalhar com o código deste repositório.

## Comandos

```bash
# Install dependencies
pip install -r requirements.txt

# Executar o app
streamlit run app.py
# Disponível em http://localhost:8501
```

Nenhuma suíte de testes ou ferramenta de lint está configurada.

## Arquitetura

Aplicação Streamlit multipágina para gestão de estoque, compras, ciclo mensal de solicitações de materiais e orçamentos. Usa SQLite via SQLAlchemy 2.0. O arquivo de dados fica em `data/estoque.db` (criado automaticamente na primeira execução; migrações de schema idempotentes rodam em `init_db()`).

**Camadas:**

- **`app.py`** — Ponto de entrada; configura a navegação do Streamlit e dispara a revisão mensal automática de parâmetros quando o mês vira.
- **`pages/`** — Camada de UI. Cada arquivo é uma página Streamlit: `Home.py`, `Visao_Geral.py`, `Estoque.py`, `Compras.py`, `Orcamentos.py`, `Relatorios.py`, `Solicitar.py` (formulário público que os setores recebem via WhatsApp), `Pedido_de_Compra.py` (registro administrativo de solicitação). As páginas chamam serviços; elas nunca acessam o banco de dados diretamente.
- **`services/`** — Lógica de negócio. As funções aqui são o único local que lê/escreve no banco de dados:
  - `estoque_service.py` — CRUD de item/categoria/setor/movimentação.
  - `fornecedor_service.py` — fornecedores + cotações (`get_best_price`/`get_best_prices_bulk`: preferencial primeiro, depois menor cotação válida, respeitando `validade_dias`).
  - `compras_service.py` — solicitações de materiais (pedido atômico, triagem/classificação, aprovação), consolidação do período (`consolidar_periodo`), Lista Final e compras avulsas.
  - `ciclo_service.py` — ciclo mensal de solicitações: abertura/encerramento/prorrogação/deleção, participação por setor e disparo das notificações.
  - `notificacao_service.py` — envio WhatsApp via Meta Cloud API (templates pré-aprovados). Sem dependência de Streamlit ou banco; falha graciosamente sem credenciais.
  - `calculos_service.py` — revisão mensal automática de mínimo/ideal (persiste `RevisaoMensal`) e overrides manuais.
  - `orcamento_service.py` — consolidação de orçamento.
  - `relatorio_service.py` — DataFrames para relatórios.
- **`core/`** — Infraestrutura:
  - `database.py` — Engine singleton do SQLAlchemy, `get_session_factory()`, `init_db()` e `run_schema_migrations()` (ALTERs idempotentes, saneamento de pedidos órfãos e migração única de timestamps UTC→hora local, com backup automático e marcador em `schema_meta`).
  - `models.py` — Modelos ORM: `Categoria`, `Item`, `Fornecedor`, `PrecoFornecedor`, `Setor`, `Movimentacao`, `SnapshotAnalise`, `RevisaoMensal`, `CicloSolicitacaoMaterial`, `CicloSolicitacaoSetor`, `SolicitacaoPedido`, `SolicitacaoMaterial`, `CompraAvulsa`, `ItemListaCompra`, `Importacao`.
  - `schemas.py` — Schemas Pydantic para validação de entrada (usados antes da persistência).
  - `engine.py` — Motor **sem estado** de análise de reposição (`StockAnalyzer`). Sem dependências de banco de dados ou Streamlit. Três variantes: `calcular_status_puro` (Painel de Reposição), `calcular_status_consolidado` (Análise de Compras, cruza estoque com solicitações aprovadas) e `calcular_status` (legada). Seguro para testar diretamente com testes unitários.
  - `calculos.py` — Cálculo estatístico da revisão mensal (mediana/percentis de consumo, janela de análise). Também sem estado.
  - `tempo.py` — Helpers de data/hora: `tempo.agora()` e `tempo.hoje()`. **Política de fuso: todo o sistema opera em hora local de Brasília (America/Sao_Paulo), naive.** Nunca usar `utcnow()`, `now()` ou `date.today()` diretos.
  - `ui.py` — Utilitários compartilhados do Streamlit: CSS, cabeçalhos, badges, formatação BRL, tema Plotly, link do formulário público.
  - `config.py` — Constantes de caminho (`DATA_DIR`, `EXPORTS_DIR`, `UPLOADS_DIR`) e variáveis de ambiente: `APP_BASE_URL` (links do formulário) e credenciais WhatsApp `WA_ACCESS_TOKEN`, `WA_PHONE_NUMBER_ID`, `WA_TEMPLATE_*`, `WA_TEMPLATE_LANG`.
- **`documents/`** — Geração de DOCX via python-docx (`lista_compras.py`, `orcamento.py`). Exportações salvas em `data/exports/` com timestamps.
- **`migration/`** — CLI de importação única de Excel→SQLite (parse → transform → load).
- **`docs/`** — Documentação detalhada: `STACK_PROJETO.md` (stack e organização), `LOGICAS_CALCULOS.md` (fórmulas de parâmetros e reposição), `INTEGRAR_WHATS.md` (ciclo de solicitações + integração WhatsApp).

## Modelo de Dados Principal

```
Categoria 1──M Item
                 ├── M─M Fornecedor   (via item_fornecedores join table)
                 ├── 1─M Movimentacao (entrada/saida, com setor e retirado_por)
                 ├── 1─M PrecoFornecedor (cotações, com validade)
                 ├── 1─M SnapshotAnalise (recomendações de reposição)
                 ├── 1─M RevisaoMensal (histórico do cálculo automático de mínimo/ideal)
                 ├── 1─M SolicitacaoMaterial (pedidos dos setores)
                 └── 1─M ItemListaCompra (consolidação por período)

CicloSolicitacaoMaterial 1──M CicloSolicitacaoSetor (participação/notificações por setor)
                         1──M SolicitacaoPedido (cabeçalho atômico do formulário)
                                  └── 1─M SolicitacaoMaterial
                                            └── 1─M CompraAvulsa (item fora do catálogo)
Setor 1──M Movimentacao / SolicitacaoPedido
```

`Item` possui `estoque_minimo_vigente`/`estoque_ideal_vigente` (manual tem prioridade sobre o sugerido pela revisão mensal). O `StockAnalyzer` calcula status (`zerado` / `abaixo_minimo` / `abaixo_ideal` / `ok` / `sem_parametro`) e quantidade sugerida (demanda líquida vs. reposição ao ideal).

## Fluxo do Ciclo de Solicitações (resumo)

1. Usuário de estoque abre o ciclo do período em **Compras** (`abrir_ciclo`) — cria participantes por setor ativo e notifica via WhatsApp com link do formulário.
2. Setores respondem pelo formulário **Solicitar** (`criar_pedido_solicitacao` — exige ciclo aberto e prazo vigente, validados na camada de serviço) ou marcam "sem necessidade" (bloqueado se o setor já enviou pedido).
3. Triagem em **Compras**: `classificar_solicitacoes_periodo` → aprovação/rejeição/vinculação/compra avulsa.
4. `consolidar_periodo` cruza estoque com solicitações **aprovadas** e persiste `ItemListaCompra` (preserva edições manuais em re-consolidações).
5. Itens aprovados (`incluir_na_lista_final`) seguem para Lista Final → Orçamentos.

## Sessões

Os serviços usam `get_session_factory()` de `core/database.py`. Padrão:

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
3) **NÃO execute ações, mudanças ou qualquer outro tipo de refatoração em UI/UX, lógica ou que possam afetar diretamente no fluxo de navegação do usuario**, a menos que não tenha sido claramente aprovado ou bem planejado.
4) Está totalmente liberado **sugerir, propor e recomendar mudanças e melhorias** que possam arrumar ou evoluir o sistema, porém elas devem ser aprovadas e bem explicadas para mim, antes de ocorrer a implementação/execução das mesmas.
5) Priorize busca (rg/grep) para localizar pontos de mudança antes de abrir arquivos.
6) **Não cole conteúdo integral de arquivos na resposta.** Mostre apenas:
   - arquivos alterados
   - resumo do diff (o que mudou e por quê)
   - comandos executados e resultados
7) Execute somente **UMA FASE por vez**. Ao terminar a FASE:
   - pare e peça autorização para a próxima FASE
8) Se detectar duplicação/overreach fora do escopo, **interrompa e reporte**.
