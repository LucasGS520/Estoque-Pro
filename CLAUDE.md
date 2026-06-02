# CLAUDE.md

Este arquivo fornece orientações para o Claude Code (claude.ai/code) ao trabalhar com o código deste repositório.

## Comandos

```bash
# Install dependencies
pip install -r requirements.txt

# Executar o app
streamlit run app.py
# Disponível em http://localhost:8501

# Executar migração de dados a partir de arquivos Excel (importação única)
python -m migration.migrate --estoque path/estoque.xlsx --fornecedores path/fornecedores.xlsx
```

Nenhuma suíte de testes ou ferramenta de lint está configurada.

## Arquitetura

Aplicação Streamlit multipágina para gestão de estoque, compras e orçamentos. Usa SQLite via SQLAlchemy 2.0. O arquivo de dados fica em `data/estoque.db` (criado automaticamente na primeira execução).

**Camadas:**

- **`app.py`** — Ponto de entrada; configura a navegação do Streamlit entre as páginas/módulos.
- **`pages/`** — Camada de UI. Cada arquivo é uma página Streamlit: `Home.py`, `Visao_Geral.py`, `Estoque.py`, `Compras.py`, `Orcamentos.py`, `Relatorios.py`. As páginas chamam serviços; elas nunca acessam o banco de dados diretamente.
- **`services/`** — Lógica de negócio. As funções aqui são o único local que lê/escreve no banco de dados. Módulos principais: `estoque_service.py` (CRUD de item/categoria/movimentação), `fornecedor_service.py` (fornecedor + cotações), `compras_service.py` (executor de análises + snapshots), `orcamento_service.py` (consolidação de orçamento), `relatorio_service.py` (DataFrames para relatórios).
- **`core/`** — Infraestrutura:
  - `database.py` — Engine singleton do SQLAlchemy + `get_session_factory()`.
  - `models.py` — Modelos ORM: `Categoria`, `Item`, `Fornecedor`, `PrecoFornecedor`, `Movimentacao`, `SnapshotAnalise`, `Importacao`.
  - `schemas.py` — Schemas Pydantic para validação de entrada (usados antes da persistência).
  - `engine.py` — Motor **sem estado** de análise de reposição (`StockAnalyzer`). Sem dependências de banco de dados ou Streamlit. Recebe dataclasses tipadas e retorna `AnalysisResult`/`AnalysisSummary`. Seguro para testar diretamente com testes unitários.
  - `ui.py` — Utilitários compartilhados do Streamlit: CSS, cabeçalhos, badges, formatação BRL, tema Plotly.
  - `config.py` — Constantes de caminho (`DATA_DIR`, `EXPORTS_DIR`, `UPLOADS_DIR`).
- **`documents/`** — Geração de DOCX via python-docx (`lista_compras.py`, `orcamento.py`). Exportações salvas em `data/exports/` com timestamps.
- **`migration/`** — CLI de importação única de Excel→SQLite (parse → transform → load).

## Modelo de Dados Principal

```
Categoria 1──M Item
                 ├── M─M Fornecedor   (via item_fornecedores join table)
                 ├── 1─M Movimentacao (entry/exit/adjustment/inventory)
                 ├── 1─M PrecoFornecedor (supplier quotes, with validity)
                 └── 1─M SnapshotAnalise (replenishment recommendations)
```

`Item` possui `estoque_atual`, `estoque_minimo`, `estoque_ideal`. O `StockAnalyzer` em `core/engine.py` calcula o status (`comprar` / `ok` / `zerado` / `sem_minimo`) e a quantidade recomendada.

`get_best_price()` em `fornecedor_service.py` — prioriza fornecedor com `preferencial=True`; usa a menor cotação válida como fallback; respeita `validade_dias`.

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
1) NÃO liste árvore inteira do projeto (evite `tree`, `ls -R`, etc.). Se precisar, liste apenas pastas-alvo da FASE.
2) NÃO leia arquivos completos. Leia no máximo 120 linhas por arquivo (ou trechos específicos). Se precisar de mais contextualização, peça antes.
3) Priorize busca (rg/grep) para localizar pontos de mudança antes de abrir arquivos.
5) Não cole conteúdo integral de arquivos na resposta. Mostre apenas:
   - arquivos alterados
   - resumo do diff (o que mudou e por quê)
   - comandos executados e resultados
6) Execute somente UMA FASE por vez. Ao terminar a FASE:
   - pare e peça autorização para a próxima FASE
7) Se detectar duplicação/overreach fora do escopo, interrompa e reporte.

