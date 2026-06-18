# Guia de Credenciais — WhatsApp Cloud API (Meta)

> Este guia cobre o passo a passo para obter as credenciais do WhatsApp Business Cloud API e configurar os templates necessários para o sistema DFeB funcionar com notificações automáticas aos setores.

---

## Pré-requisitos

Antes de começar, você precisa ter:

- **Conta Meta Business Manager** verificada (com CNPJ ou documento da empresa) — [business.facebook.com](https://business.facebook.com)
- **Número de telefone dedicado** para o WhatsApp Business da empresa (não pode estar ativo no WhatsApp pessoal ou em outra conta Business)
- Acesso de **administrador** ao Meta Business Manager da organização

---

## Parte 1 — Configurar o App no Meta for Developers

### Passo 1: Criar o App

1. Acesse [developers.facebook.com](https://developers.facebook.com) com a conta Meta vinculada ao Business Manager da empresa
2. Clique em **"Meus Apps"** → **"Criar App"**
3. Selecione o tipo **"Business"** (não escolha Consumer nem Jogos)
4. Preencha o nome do app (ex: `DFeB-Notificacoes`) e associe ao Business Manager da empresa
5. Clique em **"Criar App"**

### Passo 2: Adicionar o produto WhatsApp

1. No painel do app recém-criado, clique em **"Adicionar produto"**
2. Localize **"WhatsApp"** e clique em **"Configurar"**
3. O produto WhatsApp Business Platform será adicionado ao menu lateral

---

## Parte 2 — Configurar o Número de Telefone

### Passo 3: Adicionar o número

1. No menu lateral, vá em **"WhatsApp" → "Configurações de API"**
2. Em **"Adicionar número de telefone"**, clique em **"Adicionar número"**
3. Preencha os dados da empresa e o número de telefone no formato internacional (ex: `+55 11 99999-9999`)
4. Verifique o número via **SMS** ou **ligação**

### Passo 4: Copiar o Phone Number ID

1. Após verificar, volte em **"WhatsApp" → "Configurações de API"**
2. No card do número adicionado, copie o **Phone Number ID** (um número longo, ex: `123456789012345`)
3. Este valor será usado em `WA_PHONE_NUMBER_ID` no `.env`

> ⚠️ O número de telefone verificado precisa estar em um **Business Manager verificado** para poder enviar mensagens fora da janela de 24h (usando templates). A verificação do Business Manager pode exigir documentos da empresa.

---

## Parte 3 — Gerar o Access Token Permanente

Existem dois tipos de token. **Use System User** em produção — tokens de usuário pessoal expiram em 60 dias.

### Passo 5: Criar um System User

1. No **Meta Business Manager**, acesse **"Configurações de negócios"** (ícone de engrenagem)
2. No menu lateral, clique em **"Usuários" → "Usuários do sistema"**
3. Clique em **"Adicionar"**
4. Dê um nome (ex: `DFeB-API`) e selecione o papel **"Administrador"**
5. Clique em **"Criar usuário do sistema"**

### Passo 6: Conceder acesso ao App

1. Com o System User criado, clique em **"Conceder acesso"**
2. Selecione o **App** criado no Passo 1
3. Habilite as permissões:
   - `whatsapp_business_messaging`
   - `whatsapp_business_management`
4. Salve

### Passo 7: Gerar o token

1. Na página do System User, clique em **"Gerar novo token"**
2. Selecione o App criado e as mesmas permissões acima
3. Em **Expiração do token**, escolha **"Nunca"**
4. Clique em **"Gerar token"**
5. **Copie o token imediatamente** — ele só é exibido uma vez. Guarde em local seguro.
6. Este valor será usado em `WA_ACCESS_TOKEN` no `.env`

---

## Parte 4 — Criar os Templates de Mensagem

Os templates precisam ser aprovados pelo Meta antes de poder ser usados (prazo típico: 24-72h úteis). Crie-os com antecedência.

### Onde criar

1. Acesse [business.facebook.com](https://business.facebook.com) → **"WhatsApp Manager"**
2. Selecione a conta WhatsApp Business da empresa
3. Clique em **"Ferramentas da conta" → "Modelos de mensagem"**
4. Clique em **"Criar modelo"**

### Configurações comuns para todos os templates

- **Categoria:** `UTILITY`
- **Idioma:** `Português (BR)`
- **Tipo de conteúdo:** Texto simples (sem cabeçalho de mídia)
- **Rodapé:** deixar em branco (opcional)
- **Botões:** deixar em branco

---

### Template 1 — Abertura de ciclo (link do formulário)

**Nome:** `form_solicitacoes_materiais`

**Conteúdo do corpo:**
```
Olá! O ciclo de solicitação de materiais para *{{1}}* está aberto.
Setor: *{{2}}*
Prazo para resposta: *{{3}}*
Acesse o formulário pelo link abaixo e registre suas solicitações:
{{4}}
```

**Mapeamento dos parâmetros:**
| Parâmetro | Valor enviado pelo sistema |
|-----------|---------------------------|
| `{{1}}` | Período (ex: "Junho/2026") |
| `{{2}}` | Nome do setor |
| `{{3}}` | Data do prazo (ex: "07/06/2026") |
| `{{4}}` | Link do formulário com token único do setor |

---

### Template 2 — Lembrete D+2

**Nome:** `lembrete_solicitacao_materiais`

**Conteúdo do corpo:**
```
Lembrete: o prazo para solicitação de materiais de *{{1}}* ainda está aberto.
Setor: *{{2}}*
Prazo: *{{3}}*
Não esqueça de acessar o formulário e registrar seus pedidos!
```

**Mapeamento dos parâmetros:**
| Parâmetro | Valor enviado pelo sistema |
|-----------|---------------------------|
| `{{1}}` | Período (ex: "Junho/2026") |
| `{{2}}` | Nome do setor |
| `{{3}}` | Data do prazo (ex: "07/06/2026") |

---

### Template 3 — Aviso de prazo próximo

**Nome:** `aviso_prazo_solicitacao`

**Conteúdo do corpo:**
```
⚠️ Atenção! O prazo para solicitação de materiais de *{{1}}* vence amanhã.
Setor: *{{2}}*
Prazo: *{{3}}*
Acesse o formulário o quanto antes para registrar seus pedidos.
```

**Mapeamento dos parâmetros:**
| Parâmetro | Valor enviado pelo sistema |
|-----------|---------------------------|
| `{{1}}` | Período (ex: "Junho/2026") |
| `{{2}}` | Nome do setor |
| `{{3}}` | Data do prazo (ex: "07/06/2026") |

---

### Template 4 — Encerramento do ciclo

**Nome:** `encerramento_ciclo_materiais`

**Conteúdo do corpo:**
```
O ciclo de solicitação de materiais de *{{1}}* foi encerrado.
Setor: *{{2}}*
Caso não tenha enviado sua solicitação, entre em contato com o responsável de estoque.
```

**Mapeamento dos parâmetros:**
| Parâmetro | Valor enviado pelo sistema |
|-----------|---------------------------|
| `{{1}}` | Período (ex: "Junho/2026") |
| `{{2}}` | Nome do setor |

---

## Parte 5 — Configurar o `.env` na VPS

Após obter o token e o Phone Number ID, edite o arquivo `.env` na raiz do projeto na VPS:

```bash
# Na VPS
nano /caminho/do/projeto/.env
```

Preencha com os valores obtidos:

```env
APP_BASE_URL=http://201.76.56.247
ADMIN_PASSWORD=<defina-uma-senha-forte>

# WhatsApp Cloud API
WA_ACCESS_TOKEN=<token-do-system-user-gerado-no-passo-7>
WA_PHONE_NUMBER_ID=<phone-number-id-copiado-no-passo-4>

# Nomes dos templates (devem corresponder exatamente ao nome aprovado no Meta)
WA_TEMPLATE_NAME=form_solicitacoes_materiais
WA_TEMPLATE_LEMBRETE=lembrete_solicitacao_materiais
WA_TEMPLATE_PRAZO=aviso_prazo_solicitacao
WA_TEMPLATE_ENCERRAM=encerramento_ciclo_materiais
WA_TEMPLATE_COTACAO=
WA_TEMPLATE_LANG=pt_BR
```

Após editar, reinicie o container para carregar as novas variáveis:

```bash
docker compose restart estoque-dfeb
```

---

## Parte 6 — Verificar se está funcionando

### Teste rápido via sistema

1. Acesse o sistema em http://201.76.56.247/
2. Navegue até **Análise de Compras**
3. Clique em **"Enviar solicitações"** para abrir um ciclo de teste
4. Verifique se o WhatsApp chegou nos setores cadastrados com número

### Verificar status dos templates

No **WhatsApp Manager**, em **"Modelos de mensagem"**, cada template deve estar com status **"Ativo"** (verde) antes de poder ser usado. Se estiver em revisão ou rejeitado, o envio falha silenciosamente (o sistema registra `falha_api` no participante, sem travar).

### Causas comuns de falha no envio

| Sintoma | Causa provável |
|---------|---------------|
| Todas as notificações falham | `WA_ACCESS_TOKEN` ou `WA_PHONE_NUMBER_ID` incorretos |
| Apenas alguns setores recebem | Número do setor sem o código do país (deve ser `5511999999999`, não `11999999999`) |
| Template rejeitado pelo Meta | Conteúdo com links externos não confiáveis ou tom promocional — revisar e resubmeter |
| Mensagem entregue mas formatação errada | Parâmetros em ordem diferente dos mapeados — verificar a ordem dos `{{1}}` a `{{4}}` no template aprovado |

---

## Referências

- [Meta for Developers — WhatsApp Cloud API](https://developers.facebook.com/docs/whatsapp/cloud-api)
- [Guia de templates de mensagem](https://developers.facebook.com/docs/whatsapp/message-templates/guidelines)
- [System Users no Meta Business Manager](https://www.facebook.com/business/help/503306463479099)
- Documentação interna do sistema: `docs/INTEGRAR_WHATS.md`
