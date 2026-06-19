# Stack e Organização do Projeto — Estado Atual

## 1. Fonte de Dados

A única fonte de dados operacional do projeto é:

```
storage/estoque.db
```

Fluxo operacional:

```
SQLite
  → services/
  → pages/
  → documents/
```

Arquivos gerados em runtime ficam em `storage/`; código de persistência fica no pacote Python `data/`.

---

## 2. Stack Principal

| Camada | Tecnologia | Uso no projeto |
|---|---|---|
| Interface | Streamlit multipágina | Todas as telas operacionais, dashboards, modais e downloads |
| Dados operacionais | SQLite + SQLAlchemy 2.0 | Fonte única da verdade; sessões via `get_session_factory()` |
| Validação de entrada | Pydantic v2 | Schemas em `core/schemas.py` usados antes de qualquer persistência |
| Regra de negócio | Python puro, dataclasses, typing | Cálculo determinístico de reposição em `core/engine.py` |
| Visualização | Plotly | Gráficos de estoque, histórico e indicadores |
| Documentos | python-docx | Geração de lista de compras e orçamentos em `.docx` |
| Notificações | Meta WhatsApp Cloud API (requests) | Envio de formulários e notificações de ciclo para os setores |
| Variáveis de ambiente | python-dotenv | Carregamento de credenciais e configurações sensíveis via `.env` |

---

## 3. Organização de Arquivos

```
app.py                    Ponto de entrada; configura st.navigation e as páginas

pages/
  Home.py                 Dashboard principal e indicadores gerais
  Visao_Geral.py          Painel de visão geral do estoque
  Estoque.py              Gestão de itens, categorias, setores, fornecedores e movimentações
  Compras.py              Ciclo de solicitações, consolidação e lista final de compras
  Solicitar.py            Formulário público de solicitação de materiais (sem sidebar)
  Orcamentos.py           Gestão de orçamentos e cotações
  Pedido_de_Compra.py     Registro e acompanhamento de pedidos de compra
  Relatorios.py           Relatórios e exportações

services/
  estoque_service.py      CRUD de itens, categorias, setores, fornecedores e movimentações
  fornecedor_service.py   Cotações, preços e seleção de fornecedor preferencial
  compras_service.py      Análise de reposição, consolidação, solicitações e lista final
  ciclo_service.py        Gestão do ciclo mensal de solicitações e disparos de notificação
  notificacao_service.py  Envio de mensagens via Meta WhatsApp Cloud API
  orcamento_service.py    Consolidação de orçamentos
  relatorio_service.py    Montagem de DataFrames para relatórios
  calculos_service.py     Serviços auxiliares de cálculo

data/
  config.py               Caminhos de storage, DATABASE_URL, exports e uploads
  database.py             Engine singleton SQLAlchemy + get_session_factory() + migrações idempotentes
  models.py               Modelos ORM: todas as tabelas operacionais do banco

core/
  schemas.py              Schemas Pydantic para validação de entrada
  engine.py               Motor de análise de reposição (sem estado, testável isolado)
  calculos.py             Cálculo estatístico da revisão mensal (sem estado)
  tempo.py                Helpers de data/hora — tempo.agora() / tempo.hoje() em hora de Brasília
  ui.py                   CSS global, cabeçalhos, badges, formatação BRL, geração de links
  config.py               APP_BASE_URL, senha administrativa, credenciais WA e ntfy

documents/
  lista_compras.py        Geração do DOCX da lista de compras
  orcamento.py            Geração do DOCX de orçamento
  base_doc.py             Configurações base dos documentos Word

storage/
  estoque.db              Banco de dados operacional
  uploads/                Arquivos recebidos em runtime
  exports/                Documentos gerados (DOCX, etc.)
  backups/                Backups locais do SQLite

docs/                     Documentação técnica, especificações e diagramas
assets/                   Recursos visuais estáticos (logo, imagens)
```

---

## 4. Modelo de Dados Principal

```
Categoria 1──M Item
                ├── M─M Fornecedor         (via item_fornecedores)
                ├── 1─M PrecoFornecedor    (cotações com validade)
                ├── 1─M Movimentacao       (entradas, saídas, ajustes)
                └── 1─M SnapshotAnalise    (recomendações de reposição)

Setor
  ├── whatsapp                             (destino das notificações)
  ├── 1─M Movimentacao
  ├── 1─M SolicitacaoPedido
  └── 1─M CicloSolicitacaoSetor

CicloSolicitacaoMaterial 1──M CicloSolicitacaoSetor
SolicitacaoPedido        1──M SolicitacaoMaterial
```

---

## 5. Camada de Ciclo de Solicitações

O ciclo mensal é controlado pelas entidades `CicloSolicitacaoMaterial` e `CicloSolicitacaoSetor`. O fluxo passa por:

```
abrir_ciclo()
  → cria CicloSolicitacaoSetor por setor ativo
  → envia formulário WhatsApp a cada setor com WhatsApp cadastrado

[ciclo aberto]
  → setores acessam /solicitar?setor=ID
  → enviam SolicitacaoPedido + SolicitacaoMaterial
  → ou confirmam "sem necessidade" (sem criar pedido)

encerrar_ciclo()
  → status = "encerrado"
  → envia notificação automática a quem não respondeu

[pós-encerramento]
  → consolidação na aba Consolidação
  → aprovação/rejeição de itens
  → geração da lista final de compras
  → envio opcional de feedback WhatsApp por setor
```

Notificações disponíveis: abertura, lembrete D+2, aviso de prazo próximo, encerramento, feedback de aprovação.

---

## 6. Integração WhatsApp

Gerenciada por `services/notificacao_service.py`. Usa a Meta WhatsApp Cloud API com templates pré-aprovados.

Credenciais lidas de `core/config.py` via variáveis de ambiente:

| Variável | Finalidade |
|---|---|
| `APP_BASE_URL` | URL pública da aplicação (monta links dos formulários) |
| `WA_ACCESS_TOKEN` | Token permanente do System User da Meta |
| `WA_PHONE_NUMBER_ID` | ID do número no WhatsApp Business |
| `WA_TEMPLATE_NAME` | Template de abertura do ciclo |
| `WA_TEMPLATE_LEMBRETE` | Template de lembrete D+2 |
| `WA_TEMPLATE_PRAZO` | Template de aviso de prazo próximo |
| `WA_TEMPLATE_ENCERRAM` | Template de encerramento |
| `WA_TEMPLATE_FEEDBACK` | Template de feedback pós-consolidação |

Se `WA_ACCESS_TOKEN` ou `WA_PHONE_NUMBER_ID` estiverem vazios, a integração é desabilitada silenciosamente. A interface exibe aviso, mas não interrompe a operação.

---

## 7. Motor de Análise (`core/engine.py`)

Sem estado. Recebe dataclasses tipadas, retorna `AnalysisResult` / `AnalysisSummary`. Sem dependências de banco ou Streamlit — pode ser testado isoladamente.

Lógica central:

```python
if estoque_atual <= estoque_minimo:
    quantidade_comprar = estoque_ideal - estoque_atual
    status = "comprar"    # ou "zerado" se estoque_atual == 0
else:
    status = "ok"

# sem estoque_minimo definido → status = "sem_minimo"
```

---

## 8. Convenções

- Módulos Python usam `snake_case`.
- Arquivos de serviço têm sufixo `_service.py`.
- Páginas Streamlit usam nomes legíveis; a ordem de navegação é definida em `app.py` via `st.navigation`.
- `pages/` nunca acessa o banco diretamente — apenas chama serviços.
- `services/` nunca renderiza Streamlit — apenas lógica e banco.
- Uploads em `storage/uploads/`, exportações em `storage/exports/`.
- **Fuso horário**: todo o sistema (gravação, comparação e exibição) opera em hora local de Brasília (America/Sao_Paulo), como datetime naive. Usar sempre `tempo.agora()` / `tempo.hoje()` de `core/tempo.py` — nunca `datetime.utcnow()`, `datetime.now()` ou `date.today()` diretos. Timestamps antigos gravados em UTC são convertidos por migração única (marcador `tz_local_migrada` em `schema_meta`, com backup `storage/estoque_pre_tz_*.bak`).

---

## 9. Governança de Dados

- `storage/estoque.db` é a fonte da verdade.
- Nenhuma página lê Excel diretamente.
- Nenhum serviço depende de caminho fixo de planilha.
- Não há fluxo de importação Excel legado no código atual.
- Fazer backup de `storage/estoque.db` antes de qualquer migração destrutiva.

---

## 10. Escopo Funcional Atual

**Dentro do escopo:**
- Controle de estoque (CRUD, movimentações, inventário)
- Análise de reposição determinística
- Ciclo mensal de solicitações de materiais
- Notificações WhatsApp via Meta Cloud API
- Consolidação e lista final de compras
- Orçamentos e cotações de fornecedores
- Pedidos de compra
- Relatórios e exportações
- Geração de documentos Word

**Fora do escopo:**
- Planilhas como fonte de dados concorrente ou fluxo legado de importação
- API REST separada
- Agendamento automático de notificações (disparos são manuais pela interface)
- Aprovação automática de compras
- Web scraping de fornecedores
