# EstoquePro — Controle de Estoque, Análise de Compras e Orçamentos

Aplicação web (Streamlit + SQLite/SQLAlchemy 2.0) para gestão de estoque, ciclo mensal de solicitações de materiais, análise de compras e orçamentos.

## Principais funcionalidades

- **Estoque** — itens, categorias, setores, fornecedores, movimentações de entrada/saída e parâmetros mínimo/ideal (manuais ou calculados automaticamente por revisão mensal).
- **Ciclo de Solicitações** — abertura mensal de coleta por setor, com notificação via WhatsApp (Meta Cloud API) contendo o link do formulário público (`Solicitar`); lembretes, aviso de prazo, encerramento e feedback.
- **Análise de Compras** — triagem das solicitações, consolidação do período (cruza estoque real com demanda aprovada) e governança da Lista Final.
- **Orçamentos e Relatórios** — cotações por fornecedor, melhor preço, consolidação de orçamento e relatórios de consumo; exportações em DOCX (`data/exports/`).

## Como executar

```bash
pip install -r requirements.txt
streamlit run app.py
# Disponível em http://localhost:8501
```

O banco `data/estoque.db` é criado automaticamente na primeira execução. Migrações de schema são idempotentes e rodam na inicialização (backups automáticos em `data/*.bak` quando há migração de dados).

## Variáveis de ambiente

| Variável | Uso | Padrão |
|---|---|---|
| `APP_BASE_URL` | URL pública do app — gera os links dos formulários enviados aos setores | `http://localhost:8501` |
| `WA_ACCESS_TOKEN` | Token permanente do System User (Meta Business Suite) | — (sem ele, notificações não são enviadas) |
| `WA_PHONE_NUMBER_ID` | ID do número no WhatsApp Business | — |
| `WA_TEMPLATE_NAME` / `WA_TEMPLATE_LEMBRETE` / `WA_TEMPLATE_PRAZO` / `WA_TEMPLATE_ENCERRAM` / `WA_TEMPLATE_FEEDBACK` | Nomes dos templates aprovados | ver `core/config.py` |
| `WA_TEMPLATE_LANG` | Idioma dos templates | `pt_BR` |

Sem credenciais WhatsApp configuradas, o sistema funciona normalmente — os envios falham de forma controlada e ficam registrados como pendentes de notificação.

## Convenções importantes

- **Camadas**: `pages/` (UI) → `services/` (lógica e banco) → `core/` (infra, modelos, motor de análise). Páginas nunca acessam o banco diretamente.
- **Fuso horário**: todo o sistema opera em hora local de Brasília via `core/tempo.py` (`tempo.agora()` / `tempo.hoje()`). Não usar `datetime.now()`/`utcnow()`/`date.today()` diretos.

## Documentação

- [docs/STACK_PROJETO.md](docs/STACK_PROJETO.md) — stack, organização de arquivos e modelo de dados.
- [docs/LOGICAS_CALCULOS.md](docs/LOGICAS_CALCULOS.md) — fórmulas de parâmetros (mínimo/ideal) e do motor de reposição.
- [docs/INTEGRAR_WHATS.md](docs/INTEGRAR_WHATS.md) — ciclo de solicitações ponta a ponta e configuração da integração WhatsApp.
- [CLAUDE.md](CLAUDE.md) — guia de arquitetura para desenvolvimento assistido.
