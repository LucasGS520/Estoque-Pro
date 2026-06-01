# Stack, escopo e organizacao

## 1. Fonte principal dos dados

A fonte principal e unica de dados do projeto e:

```text
data/estoque.db
```

As planilhas Excel nao fazem mais parte do projeto. Elas foram usadas para migracao inicial e removidas depois que os dados foram carregados no SQLite.

Fluxo operacional oficial:

```text
SQLite
  -> services/
  -> pages/
  -> documents/
```

Fluxo de importacao eventual:

```text
planilha externa temporaria
  -> migration/
  -> SQLite
```

Isso evita que Excel e banco sejam tratados como fontes concorrentes.

## 2. Stack principal

| Camada | Tecnologia | Uso no projeto |
| --- | --- | --- |
| Interface | Streamlit multipagina | Operacao, dashboards, filtros, formularios e downloads |
| Dados operacionais | SQLite + SQLAlchemy | Base principal da aplicacao |
| Importacao eventual | Excel + openpyxl + pandas | Carga avulsa de arquivos externos para o banco |
| Regra de negocio | Python puro, dataclasses, enums e typing | Calculo deterministico de reposicao |
| Visualizacao | Streamlit + Plotly | Indicadores, graficos e tabelas |
| Documentos | python-docx | Lista de compras, orcamentos e relatorios |
| Validacao | Pydantic | Schemas e validacoes auxiliares |
| Automacao | Execucao manual inicial | Futuro agendamento por Task Scheduler ou cron |

A solucao deve continuar simples: uma aplicacao Streamlit sobre uma base SQLite, com regras calculadas por Python e documentacao clara.

## 3. Escopo funcional

IN:

- Controle de estoque.
- Analise de reposicao.
- Compras recomendadas.
- Fornecedores e precos.
- Orcamentos.
- Relatorios.
- Geracao de documentos.
- Importacao eventual de planilhas externas.

OUT:

- Planilhas permanentes dentro do projeto.
- Web scraping de fornecedores.
- Carrinho de compra, pagamento ou aprovacao automatica.
- API REST separada.
- Reescrita completa de interface.
- IA decidindo compra ou calculando estoque.

## 4. Principio central

A IA, se adicionada em fase futura, deve consultar dados ja processados. Ela nao deve calcular estoque, decidir compra ou substituir a regra deterministica.

Fluxo correto:

```text
Usuario pergunta
  -> sistema consulta dados calculados no SQLite
  -> IA explica o resultado
```

## 5. Motor de analise

A regra principal fica em Python, especialmente em `core/engine.py`.

```python
if qtd_atual <= estoque_minimo:
    quantidade_comprar = estoque_ideal - qtd_atual
    status = "comprar"
else:
    quantidade_comprar = 0
    status = "ok"
```

Casos especiais:

- Sem estoque minimo definido: `sem_minimo_definido`.
- Estoque atual igual a zero com necessidade de compra: `zerado`.

## 6. Organizacao atual do projeto

```text
app.py
pages/        Interface Streamlit e navegacao
services/     Casos de uso por dominio
core/         Configuracao, banco, modelos, schemas, UI comum e engine
documents/    Geracao de documentos Word
migration/    Importacao avulsa de planilhas externas
data/
  estoque.db  Fonte principal dos dados
  uploads/    Uploads recebidos em runtime
  exports/    Documentos e relatorios gerados
docs/         Documentacao tecnica, escopo, diagnosticos e diagramas
assets/       Recursos visuais estaticos
```

Responsabilidades:

| Area | Faz | Nao faz |
| --- | --- | --- |
| `pages/` | Renderiza telas e captura comandos | Leitura direta de Excel |
| `services/` | Orquestra casos de uso | Renderizacao Streamlit |
| `core/engine.py` | Calcula status e recomendacoes | Persistencia ou UI |
| `core/database.py` | Cria engine, sessao e tabelas | Fluxo de tela |
| `documents/` | Gera `.docx` | Calcula regra de estoque |
| `migration/` | Importa arquivos externos para SQLite | Guarda fonte permanente |
| `docs/` | Documenta decisoes e arquitetura | Guarda planilhas operacionais |
| `data/estoque.db` | Armazena dados operacionais | Documentacao tecnica |

## 7. Convencoes

- Modulos Python usam `snake_case`.
- Arquivos de servico mantem o sufixo `_service.py`.
- Paginas Streamlit usam nomes claros e sem numeracao obrigatoria quando `st.navigation` controla a ordem.
- Uploads de usuario ficam em `data/uploads/`.
- Exportacoes ficam em `data/exports/`.
- Documentacao tecnica fica em `docs/`.
- Cache, arquivos gerados e planilhas temporarias nao devem entrar no versionamento.

## 8. Governanca de dados

- O SQLite e a fonte da verdade.
- Excel e apenas formato de importacao eventual.
- Nenhuma pagina deve ler Excel diretamente.
- Nenhum servico de negocio deve depender de caminho fixo de planilha.
- Importacoes avulsas devem passar por `migration/migrate.py` com caminhos explicitos.
- O arquivo importado pode ser apagado depois que a carga for validada.
- Antes de apagar `data/estoque.db`, deve haver backup ou fonte externa confiavel para remigracao.

## 9. Importacao avulsa

Quando for necessario importar uma nova planilha externa:

```powershell
python -m migration.migrate --estoque caminho\estoque.xlsx --fornecedores caminho\fornecedores.xlsx
```

Depois da validacao da carga, a planilha externa nao deve ser mantida dentro do projeto.

## 10. Fases de evolucao

1. Base SQLite consolidada como fonte principal.
2. Motor de analise deterministico.
3. Interface operacional no Streamlit.
4. Geracao de documentos.
5. Orcamentos e fornecedores.
6. Relatorios e indicadores.
7. Consulta com IA, somente como camada explicativa.
