# Diagnostico estrutural do projeto

Projeto: RH DFeB - Controle de Estoque e Compras

Data-base: 2026-06-01

## 1. Decisao principal sobre dados

A fonte principal e unica de dados dentro do projeto e o banco SQLite:

```text
data/estoque.db
```

As planilhas Excel foram usadas apenas como insumo de migracao inicial. Depois da carga para o SQLite, elas foram removidas do projeto para eliminar ambiguidade sobre qual base alimenta a aplicacao.

Fluxo oficial a partir desta decisao:

```text
SQLite (data/estoque.db)
  -> services/
  -> pages/
  -> documents/
```

Fluxo permitido apenas em situacoes excepcionais:

```text
planilha externa temporaria
  -> migration/
  -> SQLite (data/estoque.db)
```

Nenhuma pagina ou servico operacional deve ler planilhas diretamente.

## 2. Resumo executivo

O sistema e uma aplicacao Streamlit multipagina para controle operacional de estoque, analise de compras, fornecedores, orcamentos e relatorios. A estrutura segue um monolito em camadas, com separacao entre apresentacao, servicos de aplicacao, infraestrutura, documentos e migracao eventual de dados externos.

A reorganizacao desta rodada consolidou o SQLite como base operacional. As planilhas `CONTROLE DE ESTOQUE MATERIAS.xlsx` e `FORNECEDORES.xlsx` foram migradas para o banco e removidas do repositorio/projeto.

Resultado atual da migracao:

| Entidade | Total no banco |
| --- | ---: |
| Categorias | 3 |
| Itens | 153 |
| Fornecedores | 15 |

Observacao da migracao: havia uma duplicata de `TINTA CARIMBO PRETO` na categoria `ESCRITORIO`; o transformador manteve a primeira ocorrencia.

## 3. Arquitetura-alvo

```text
app.py
  -> pages/                 Interface Streamlit e navegacao
  -> services/              Casos de uso e orquestracao de regras
  -> core/                  Configuracao, banco, modelos, schemas, UI comum e engine
  -> documents/             Geracao de documentos Word
  -> migration/             Importacao avulsa de arquivos externos para o SQLite
  -> data/
       estoque.db           Banco SQLite local: fonte principal
       uploads/             Arquivos enviados em runtime
       exports/             Documentos e relatorios gerados
  -> docs/                  Documentacao tecnica e governanca
  -> assets/                Imagens e identidade visual usadas pela aplicacao
```

## 4. Responsabilidades por camada

| Area | Responsabilidade | Nao deve conter |
| --- | --- | --- |
| `app.py` | Inicializacao Streamlit, criacao de diretorios de runtime e roteamento | Regra de negocio |
| `pages/` | Telas, filtros, formularios, exibicao de tabelas e graficos | Leitura direta de Excel ou calculos centrais |
| `core/` | Configuracao, ORM, engine deterministica, schemas e componentes comuns de UI | Orquestracao de fluxo de usuario |
| `services/` | Casos de uso: estoque, compras, fornecedores, orcamentos e relatorios | Renderizacao Streamlit |
| `documents/` | Templates e geracao de `.docx` | Consultas diretas de tela |
| `migration/` | ETL eventual de arquivos externos, separado em `parser`, `transformer`, `loader` e `migrate` | Fonte operacional permanente |
| `data/estoque.db` | Fonte principal dos dados operacionais | Documentacao ou arquivos temporarios |
| `docs/` | Escopo, diagnosticos, diagramas, decisoes e governanca | Planilhas de operacao corrente |

## 5. Inventario classificado

| Caminho | Funcao | Acao |
| --- | --- | --- |
| `app.py` | Entrada Streamlit e navegacao | Manter |
| `requirements.txt` | Dependencias Python | Manter |
| `.streamlit/config.toml` | Tema Streamlit | Manter |
| `assets/logo_dfeb.png` | Identidade visual | Manter |
| `core/config.py` | Caminhos e constantes | Manter; sem caminhos fixos para planilhas |
| `core/database.py` | Engine e sessao SQLAlchemy | Manter |
| `core/models.py` | Modelos ORM | Manter |
| `core/engine.py` | Motor deterministico de estoque | Manter |
| `core/schemas.py` | Schemas e validacoes | Manter |
| `core/ui.py` | Componentes e CSS compartilhados | Manter |
| `services/*_service.py` | Casos de uso por dominio | Manter |
| `pages/*.py` | Paginas Streamlit | Manter |
| `documents/*.py` | Geracao de documentos | Manter |
| `migration/*.py` | Pipeline de importacao avulsa | Manter |
| `data/estoque.db` | Fonte principal operacional | Manter localmente |
| `data/uploads/.gitkeep` | Mantem pasta de uploads | Manter |
| `data/exports/.gitkeep` | Mantem pasta de exports | Manter |
| `data/exports/*.docx` | Saidas geradas em runtime | Nao versionar |
| `docs/stack_escopo.md` | Stack, escopo e decisoes | Manter |
| `docs/diagrama_fases.svg` | Diagrama de fases | Manter |
| `docs/Design_System.docx` | Documento de design system | Manter em docs enquanto for material de referencia |
| `__pycache__/`, `*.pyc` | Cache Python | Remover quando encontrado |
| `data/sources/*.xlsx` | Antigas planilhas-fonte | Removidas apos migracao |

## 6. Matriz de decisao

| Condicao | Acao padrao |
| --- | --- |
| Dado operacional usado pela aplicacao | Persistir no SQLite |
| Planilha recebida para importacao | Usar temporariamente e importar para o SQLite |
| Arquivo operacional gerado pela aplicacao | Guardar em `data/exports/` e nao tratar como fonte |
| Upload de usuario | Guardar em `data/uploads/` apenas durante o fluxo necessario |
| Documento tecnico, decisao, diagrama ou escopo | Manter em `docs/` |
| Cache, build, pyc ou export recriavel | Remover quando nao necessario |

## 7. Regras de governanca dos dados

- O SQLite e a fonte da verdade do projeto.
- Excel nao e base operacional.
- Novas importacoes devem vir de arquivos externos, nao de planilhas fixas dentro do projeto.
- Paginas e servicos devem consultar `services/` e banco, nunca planilhas.
- A migracao deve registrar origem em `importacoes`, mas o arquivo de origem nao precisa permanecer no projeto.
- Antes de apagar o banco, deve existir backup ou plano de remigracao.

## 8. Areas criticas

- `data/estoque.db`: fonte principal dos dados.
- `app.py`: ponto de entrada e roteamento Streamlit.
- `core/database.py`: inicializacao do banco e tabelas.
- `core/engine.py`: regra deterministica de analise de estoque.
- `core/config.py`: caminhos oficiais de dados, uploads e exports.
- `services/`: contratos usados pelas paginas.
- `pages/`: navegacao e experiencia operacional.
- `migration/`: importacao eventual de arquivos externos.

## 9. Mudancas executadas nesta rodada

- Executada migracao das planilhas existentes para `data/estoque.db`.
- Confirmados no banco: 3 categorias, 153 itens e 15 fornecedores.
- Removido o diretorio `data/sources/` com as planilhas migradas.
- Removidos de `core/config.py` os caminhos fixos `SOURCES_DIR`, `ESTOQUE_XLSX` e `FORNECEDORES_XLSX`.
- Removida de `app.py` a criacao de `data/sources/`.
- Atualizado `migration/migrate.py` para exigir caminhos explicitos de planilhas externas.
- Mantida a migracao apenas como ferramenta avulsa, nao como fonte permanente do sistema.

## 10. Definition of Done da reorganizacao

- Banco SQLite definido como fonte principal.
- Dados das planilhas migrados para o banco.
- Planilhas removidas do projeto.
- Codigo sem dependencia de caminhos fixos para planilhas internas.
- Documentacao atualizada com regras de governanca de dados.
- Validacao sintatica executada apos as alteracoes.
