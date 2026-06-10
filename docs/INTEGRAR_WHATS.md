# Ciclo de Solicitações de Materiais — Funcionamento e Integração WhatsApp

Este documento descreve o funcionamento completo da camada de Solicitações de Materiais, o fluxo de execução de ponta a ponta, e o guia de configuração da integração WhatsApp via Meta Cloud API.

---

## 1. Visão Geral da Camada

A camada de Solicitações de Materiais opera sobre um **ciclo mensal** — um período delimitado em que os setores podem enviar suas necessidades de compra. O ciclo é a entidade central que controla:

- quando a coleta está aberta ou encerrada;
- quais setores participam e qual é o status de cada um;
- qual prazo está vigente;
- quais notificações já foram enviadas.

O sistema não controla o fluxo pelo WhatsApp. O WhatsApp é apenas o canal de entrega. O ciclo, os estados e as ações são gerenciados pelo banco de dados e pela interface de compras.

---

## 2. Entidades Envolvidas

```
CicloSolicitacaoMaterial          ← o ciclo mensal em si
  └── CicloSolicitacaoSetor        ← um registro por setor participante
        └── status                 ← pendente | respondido | sem_solicitacao

SolicitacaoPedido                 ← o formulário enviado pelo setor
  └── SolicitacaoMaterial          ← cada item solicitado naquele formulário

Setor                             ← o setor cadastrado no sistema
  └── whatsapp                    ← número de destino das notificações
```

### Status de `CicloSolicitacaoSetor`

| Status | Significado |
|---|---|
| `pendente` | Setor ainda não enviou formulário nem confirmou ausência de necessidade |
| `respondido` | Setor enviou ao menos um formulário |
| `sem_solicitacao` | Setor confirmou que não tem materiais a solicitar neste ciclo |

### Status de `CicloSolicitacaoMaterial`

| Status | Significado |
|---|---|
| `aberto` | Formulários podem ser enviados pelos setores |
| `encerrado` | Coleta encerrada; formulários bloqueados |

---

## 3. Fluxo de Execução Completo

### 3.1 Preparação (antes de abrir o ciclo)

**Pré-requisitos obrigatórios:**
1. Todos os setores que participarão do ciclo devem estar cadastrados em **Estoque → Setores** com `Ativo = Sim`.
2. Cada setor que receberá formulário via WhatsApp deve ter o campo **WhatsApp** preenchido com o número no formato `(XX) XXXXX-XXXX` ou `55XXXXXXXXXXX`.
3. A variável de ambiente `APP_BASE_URL` deve apontar para a URL pública da aplicação (ver seção 5).
4. As credenciais da Meta API devem estar configuradas (ver seção 5).

---

### 3.2 Abertura do Ciclo

**Onde:** Compras → Solicitações e Pendências → Envio de Solicitações → "Abrir Ciclo".

**O que acontece internamente:**

1. Um registro `CicloSolicitacaoMaterial` é criado com `status = "aberto"`.
2. Todos os setores com `ativo = True` recebem um registro `CicloSolicitacaoSetor` com `status = "pendente"`.
3. Para cada setor **com WhatsApp cadastrado**, o sistema envia automaticamente a mensagem inicial com o link do formulário personalizado.
4. Para cada setor **sem WhatsApp**, o campo `falha_envio = True` e `motivo_falha = "sem_whatsapp"` é registrado — sem erro de execução.
5. A abertura retorna contagens: `enviados`, `falhas_api`, `sem_whatsapp`.

**Link gerado por setor:**
```
{APP_BASE_URL}/solicitar?setor={setor_id}
```
O parâmetro `?setor=ID` pré-identifica o setor no formulário: o campo de seleção fica oculto e bloqueado.

---

### 3.3 Período de Coleta (ciclo aberto)

Durante o ciclo aberto, os setores acessam o formulário e têm dois caminhos:

**Caminho A — Enviar solicitação:**
1. O formulário exibe as seções de identificação (nome do solicitante), busca no catálogo e adição de itens novos.
2. Ao enviar, cria-se `SolicitacaoPedido` + `SolicitacaoMaterial` para cada item.
3. O status do `CicloSolicitacaoSetor` do setor passa para `respondido`.
4. Se o setor enviar um segundo formulário (complemento), um novo `SolicitacaoPedido` é criado — com aviso exibido na tela antes de prosseguir. Ambos aparecem na revisão com badge "1º Envio", "2º Envio", etc.

**Caminho B — Confirmar sem necessidade:**
1. O formulário exibe o botão "Não tenho materiais a solicitar este mês".
2. Ao confirmar, nenhum `SolicitacaoPedido` é criado.
3. O status do `CicloSolicitacaoSetor` passa para `sem_solicitacao`.
4. O setor sai da fila de pendentes e não recebe mais lembretes.

**Formulário bloqueado quando:**
- Não há ciclo aberto para o período.
- O ciclo está encerrado.
- O prazo de resposta já passou.

---

### 3.4 Notificações Durante o Ciclo

O sistema possui quatro tipos de notificação além da mensagem inicial. Todos são disparados manualmente pelo responsável de compras na interface, **exceto** o de encerramento (automático).

#### Lembrete D+2 (amarelo)
- **Quando aparece:** O banner aparece na aba "Solicitações e Pendências" quando há setores com `status = "pendente"` e `notificacao_lembrete_d2_em IS NULL`.
- **Destinatários:** Apenas setores `pendente` que ainda não receberam este lembrete.
- **Gatilho:** Botão "Enviar lembrete" no banner amarelo.
- **Template WhatsApp:** `WA_TEMPLATE_LEMBRETE` (padrão: `lembrete_solicitacao_materiais`).
- **Parâmetros do template:** `{{1}}` período, `{{2}}` nome do setor, `{{3}}` prazo.
- **Idempotência:** Após o envio, `notificacao_lembrete_d2_em` é preenchido. O banner não reaparece para quem já recebeu.

#### Aviso de Prazo Próximo (vermelho)
- **Quando aparece:** Banner vermelho quando há pendentes e `notificacao_prazo_proximo_em IS NULL`.
- **Destinatários:** Apenas setores `pendente` que ainda não receberam este aviso.
- **Gatilho:** Botão "Enviar aviso de prazo" no banner vermelho.
- **Template WhatsApp:** `WA_TEMPLATE_PRAZO` (padrão: `aviso_prazo_solicitacao`).
- **Parâmetros do template:** `{{1}}` período, `{{2}}` nome do setor, `{{3}}` prazo.

#### Notificação de Encerramento (automática)
- **Quando é disparada:** Ao clicar em "Encerrar Ciclo" — chamado automaticamente dentro de `encerrar_ciclo()`.
- **Destinatários:** Setores com `status = "pendente"` no momento do encerramento (quem não respondeu).
- **Template WhatsApp:** `WA_TEMPLATE_ENCERRAM` (padrão: `encerramento_ciclo_materiais`).
- **Parâmetros do template:** `{{1}}` período, `{{2}}` nome do setor.

#### Feedback de Aprovação (pós-consolidação)
- **Onde:** Aba "Consolidação" → seção "Feedback aos Setores" (aparece somente se as credenciais WhatsApp estiverem configuradas).
- **Destinatários:** Setores com pelo menos um item aprovado ou rejeitado na lista final.
- **Gatilho:** Botão "Enviar feedback aos setores" (manual, após consolidação concluída).
- **Template WhatsApp:** `WA_TEMPLATE_FEEDBACK` (padrão: `feedback_solicitacao_materiais`).
- **Parâmetros do template:** `{{1}}` nome do setor, `{{2}}` período, `{{3}}` itens aprovados (texto), `{{4}}` itens rejeitados (texto).

---

### 3.5 Encerramento do Ciclo

**Onde:** Compras → Solicitações e Pendências → botão "Encerrar Ciclo".

**O que acontece:**
1. `CicloSolicitacaoMaterial.status` passa para `"encerrado"`.
2. `encerrado_em` é preenchido.
3. `enviar_notificacoes_encerramento()` é chamado automaticamente — notifica os setores que não responderam.
4. O formulário público passa a bloquear novos envios para este período.

Após o encerramento, o ciclo ainda pode ser **reaberto** pelo responsável de compras (botão "Reabrir Ciclo"), caso necessário.

---

### 3.6 Fluxo na Aba Consolidação

Após encerrar o ciclo (ou durante, para períodos passados):

1. **Aba Consolidação:** lista todas as solicitações classificadas por status (validada, aprovada, rejeitada, novo_item, sem_parametros, etc.).
2. O responsável de compras aprova ou rejeita cada item.
3. Ao consolidar, a lista final é gerada.
4. O documento DOCX de lista de compras pode ser exportado.
5. O **Feedback aos Setores** pode ser enviado via botão na mesma aba.

---

## 4. Diagrama de Estados do Ciclo

```
[não existe]
     │ abrir_ciclo()
     ▼
  "aberto"  ◄──── reabrir_ciclo()
     │
     │ encerrar_ciclo()
     ▼
 "encerrado"
```

```
Setor no ciclo:
  "pendente"
      ├── envia formulário    → "respondido"
      └── confirma sem nec.   → "sem_solicitacao"
```

---

## 5. Configuração da Integração WhatsApp

### 5.1 Pré-requisitos na Meta

1. **Conta no Meta Business Suite** com acesso ao WhatsApp Business.
2. **Número de telefone registrado** no WhatsApp Business API (não pode ser um número pessoal ativo no WhatsApp convencional).
3. **System User** com permissão `whatsapp_business_messaging` no Business Manager.
4. **Token de acesso permanente** gerado para o System User (não usar tokens temporários de usuário).
5. Os **5 templates de mensagem** criados e aprovados antes de uso em produção (ver seção 5.3).

### 5.2 Variáveis de Ambiente

Configure as variáveis abaixo no ambiente onde a aplicação é executada. Em desenvolvimento local, crie um arquivo `.env` na raiz do projeto (não commitar).

| Variável | Obrigatória | Descrição | Exemplo |
|---|---|---|---|
| `APP_BASE_URL` | Sim | URL pública da aplicação. Usada para montar os links dos formulários enviados nos templates. | `https://meu-app.streamlit.app` |
| `WA_ACCESS_TOKEN` | Sim | Token permanente do System User da Meta API. | `EAABcde...` |
| `WA_PHONE_NUMBER_ID` | Sim | ID numérico do número no WhatsApp Business (diferente do número de telefone). Encontrado no painel da Meta. | `123456789012345` |
| `WA_TEMPLATE_NAME` | Não | Nome do template de abertura do ciclo. Padrão: `form_solicitacoes_materiais`. | `form_solicitacoes_materiais` |
| `WA_TEMPLATE_LEMBRETE` | Não | Nome do template de lembrete D+2. Padrão: `lembrete_solicitacao_materiais`. | `lembrete_solicitacao_materiais` |
| `WA_TEMPLATE_PRAZO` | Não | Nome do template de aviso de prazo próximo. Padrão: `aviso_prazo_solicitacao`. | `aviso_prazo_solicitacao` |
| `WA_TEMPLATE_ENCERRAM` | Não | Nome do template de encerramento. Padrão: `encerramento_ciclo_materiais`. | `encerramento_ciclo_materiais` |
| `WA_TEMPLATE_FEEDBACK` | Não | Nome do template de feedback de aprovação. Padrão: `feedback_solicitacao_materiais`. | `feedback_solicitacao_materiais` |
| `WA_TEMPLATE_LANG` | Não | Código de idioma dos templates. Padrão: `pt_BR`. | `pt_BR` |

**Como definir em produção (Streamlit Cloud):**
Acesse Settings → Secrets e adicione:
```toml
APP_BASE_URL = "https://meu-app.streamlit.app"
WA_ACCESS_TOKEN = "EAABcde..."
WA_PHONE_NUMBER_ID = "123456789012345"
```

**Como definir localmente (.env):**
```
APP_BASE_URL=http://localhost:8501
WA_ACCESS_TOKEN=EAABcde...
WA_PHONE_NUMBER_ID=123456789012345
```

> O sistema verifica `WA_ACCESS_TOKEN` e `WA_PHONE_NUMBER_ID` antes de qualquer envio. Se estiverem vazios, a integração é desabilitada silenciosamente — a interface mostra um aviso, mas não quebra.

### 5.3 Templates Necessários no Meta Business Suite

Cada template deve ser criado em **Meta Business Suite → WhatsApp → Templates de Mensagem**, com idioma `Português (BR)` e categoria **UTILITY**.

Após criar, aguardar aprovação da Meta (geralmente 24–48h). Templates rejeitados precisam ser revisados e reenviados.

---

#### Template 1 — Abertura do Ciclo
**Nome:** `form_solicitacoes_materiais`
**Variável de ambiente:** `WA_TEMPLATE_NAME`

Corpo sugerido:
```
Solicitações de materiais — {{1}}

O período para envio do setor *{{2}}* está aberto.
Prazo: {{4}}

Acesse o formulário pelo link:
{{3}}
```

| Parâmetro | Valor enviado pelo sistema |
|---|---|
| `{{1}}` | Período (ex: `Junho/2026`) |
| `{{2}}` | Nome do setor (ex: `Manutenção`) |
| `{{3}}` | Link do formulário com `?setor=ID` |
| `{{4}}` | Prazo de resposta (ex: `07/06/2026`) |

---

#### Template 2 — Lembrete D+2
**Nome:** `lembrete_solicitacao_materiais`
**Variável de ambiente:** `WA_TEMPLATE_LEMBRETE`

Corpo sugerido:
```
Lembrete: solicitação de materiais — {{1}}

O setor *{{2}}* ainda não enviou a solicitação deste mês.
Prazo de envio: {{3}}.

Acesse o link enviado anteriormente para preencher.
```

| Parâmetro | Valor enviado |
|---|---|
| `{{1}}` | Período |
| `{{2}}` | Nome do setor |
| `{{3}}` | Prazo de resposta |

---

#### Template 3 — Aviso de Prazo Próximo
**Nome:** `aviso_prazo_solicitacao`
**Variável de ambiente:** `WA_TEMPLATE_PRAZO`

Corpo sugerido:
```
Atenção — prazo de solicitações se encerrando

O prazo para envio das solicitações de *{{2}}* referentes a {{1}} encerra em {{3}}.

Caso não precise solicitar materiais neste mês, acesse o formulário e confirme.
```

| Parâmetro | Valor enviado |
|---|---|
| `{{1}}` | Período |
| `{{2}}` | Nome do setor |
| `{{3}}` | Prazo de resposta |

---

#### Template 4 — Encerramento do Ciclo
**Nome:** `encerramento_ciclo_materiais`
**Variável de ambiente:** `WA_TEMPLATE_ENCERRAM`

Corpo sugerido:
```
O ciclo de solicitações de materiais de {{1}} foi encerrado.

O setor *{{2}}* não enviou solicitação neste período. Caso necessário, entre em contato com o setor de compras.
```

| Parâmetro | Valor enviado |
|---|---|
| `{{1}}` | Período |
| `{{2}}` | Nome do setor |

---

#### Template 5 — Feedback de Aprovação
**Nome:** `feedback_solicitacao_materiais`
**Variável de ambiente:** `WA_TEMPLATE_FEEDBACK`

Corpo sugerido:
```
Resultado da análise de compras — {{2}}

Setor: *{{1}}*

✅ Itens aprovados para compra: {{3}}

❌ Itens não incluídos neste ciclo: {{4}}
```

| Parâmetro | Valor enviado |
|---|---|
| `{{1}}` | Nome do setor |
| `{{2}}` | Período |
| `{{3}}` | Lista de itens aprovados (separados por vírgula, ou "nenhum") |
| `{{4}}` | Lista de itens rejeitados (separados por vírgula, ou "nenhum") |

> **Importante:** A Meta pode rejeitar templates que contenham listas muito longas em um único parâmetro. Se a solicitação de um setor for muito extensa, o envio pode ser truncado ou rejeitado pela API. Monitore as primeiras execuções em produção.

---

### 5.4 Formato do Número de Telefone nos Setores

O sistema normaliza o número antes de enviar à API, removendo caracteres não-numéricos e adicionando o prefixo `55` se necessário.

**Formatos aceitos no cadastro do setor:**
```
(11) 99999-9999        → normalizado para 5511999999999
11 999999999           → normalizado para 5511999999999
5511999999999          → mantido como está
+55 11 99999-9999      → normalizado para 5511999999999
```

Usar sempre o número do **responsável do setor** que receberá e encaminhará o link — não o número institucional geral.

---

## 6. Observações Operacionais Importantes

### Streamlit não executa agendamentos automáticos

Os disparos de notificação (lembrete D+2, aviso de prazo) **não ocorrem automaticamente por tempo**. Eles dependem de ação manual pelo responsável de compras na interface.

Para automatização real em produção, seria necessário um processo externo (cron job, task scheduler, worker) que chame as funções de disparo:
```python
from services.ciclo_service import enviar_lembretes_pendentes, enviar_avisos_prazo_proximo

with SessionLocal() as session:
    enviar_lembretes_pendentes(session, ciclo_id)
```

Enquanto não houver esse processo, o responsável de compras deve verificar manualmente os banners de notificação na aba "Solicitações e Pendências" e acionar os envios pelos botões disponíveis.

### Idempotência dos envios

Cada tipo de notificação possui um campo de timestamp no banco (`notificacao_lembrete_d2_em`, `notificacao_prazo_proximo_em`, etc.). Uma vez preenchido, o setor não recebe mais aquele tipo de mensagem, mesmo que o botão seja acionado novamente. Isso evita duplicidade acidental.

### Setores sem WhatsApp cadastrado

Setores sem o campo WhatsApp preenchido não recebem notificações — sem erro, sem interrupção do fluxo. Eles aparecem como `sem_whatsapp` nas contagens de resultado. O formulário ainda pode ser preenchido manualmente pelo link genérico (`/solicitar`) ou pelo responsável.

### Falhas de API

Falhas de comunicação com a Meta API são registradas em `motivo_falha` do participante. A interface exibe a contagem de falhas após a abertura do ciclo e permite reenvio individual por setor na tabela de participantes.

### Migração de banco de dados

Os campos de rastreamento de notificação (`notificacao_lembrete_d2_em`, etc.) foram adicionados à tabela `ciclo_solicitacao_setores` via `ALTER TABLE`. Em um banco existente, a migração deve ser executada manualmente antes de iniciar a aplicação com as novas versões do código:

```sql
ALTER TABLE ciclo_solicitacao_setores ADD COLUMN notificacao_lembrete_d2_em DATETIME;
ALTER TABLE ciclo_solicitacao_setores ADD COLUMN notificacao_prazo_proximo_em DATETIME;
ALTER TABLE ciclo_solicitacao_setores ADD COLUMN notificacao_encerramento_em DATETIME;
ALTER TABLE ciclo_solicitacao_setores ADD COLUMN notificacao_feedback_em DATETIME;
```

Em um banco novo (primeira execução), `create_all()` cria as colunas automaticamente.

---

## 7. Checklist de Configuração para Produção

- [ ] Setores cadastrados com `Ativo = Sim` e WhatsApp correto
- [ ] `APP_BASE_URL` configurada com a URL pública real da aplicação
- [ ] `WA_ACCESS_TOKEN` gerado para o System User permanente (não token de usuário)
- [ ] `WA_PHONE_NUMBER_ID` copiado do painel da Meta (campo "Phone number ID")
- [ ] 5 templates criados no Meta Business Suite e com status **Aprovado**
- [ ] Nomes dos templates conferidos com as variáveis de ambiente (`WA_TEMPLATE_*`)
- [ ] Migração das 4 colunas executada se o banco já existia antes desta versão
- [ ] Primeiro ciclo aberto com apenas 1–2 setores para validar o envio antes de escalar
