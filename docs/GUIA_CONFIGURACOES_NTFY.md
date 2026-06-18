# Sistema de Push Notifications — Documentação Completa

## 1. O que foi implementado

O sistema adiciona uma **camada de push notifications** ao app de controle de estoque. Quando eventos importantes acontecem — especialmente em páginas públicas onde o responsável de estoque não está presente — uma notificação chega instantaneamente no celular dele.

**Arquivos criados ou modificados:**

| Arquivo | Tipo | O que fez | 
| --- | --- | --- | 
| `docker-compose.yml` | Modificado | Adicionou o container `ntfy-dfeb` e volume persistente `ntfy_data` | 
| `nginx/nginx.conf` | Modificado | Adicionou rota `/ntfy/` que direciona ao container ntfy | 
| `ntfy/server.yml` | Criado | Configuração do servidor ntfy (auth, cache, iOS relay) | 
| `core/config.py` | Modificado | Adicionou 3 variáveis de ambiente: `NTFY_SERVER`, `NTFY_TOPIC`, `NTFY_TOKEN` | 
| `services/push_service.py` | Criado | Serviço Python que publica notificações via ntfy | 
| `pages/Solicitar.py` | Modificado | Trigger: envia push quando setor envia formulário | 
| `pages/Aprovacao_Orcamento.py´ | Modificado | Trigger: envia push quando diretor registra decisão de orçamento | 
| `services/estoque_service.py` | Modificado | Trigger: envia push quando movimentação causa item zerado ou abaixo do mínimo | 

---

## 2. A ferramenta: ntfy

`ntfy` é um servidor de push notifications open-source, gratuito, escrito em Go. Funciona via HTTP simples — publicar uma notificação é apenas um POST.

**Como ntfy funciona internamente**

O ntfy trabalha com o conceito de tópico — um canal nomeado. Qualquer cliente que assinar o tópico recebe as mensagens publicadas nele.

* **Publicar** → `POST http://servidor/topico` com o texto da mensagem no body
* **Assinar** → o app do celular abre uma conexão persistente (WebSocket ou SSE) com o servidor e fica "ouvindo" o tópico
* Quando uma mensagem é publicada, o servidor empurra instantaneamente para todos os clientes conectados

**Autenticação configurada**

O servidor está configurado com `auth-default-access: deny-all` — ninguém acessa sem credencial. Dois tipos de acesso existirão:

* **Token de publicação** (usado pelo Streamlit internamente): enviado no header `Authorization: Bearer <token>` a cada POST
* **Usuário/senha** (usado no app ntfy do celular): para se conectar ao servidor e assinar o tópico

**Cache de 12 horas**

Se o celular estiver offline quando uma notificação for enviada, o servidor guarda a mensagem por 12 horas. Quando o app ntfy reconectar, ele recebe todas as mensagens perdidas no período.

**Relay iOS (linha `upstream-base-url`)**

iPhones precisam de APNs (Apple Push Notification Service) para receber push quando o app está em segundo plano — um requisito da Apple. O ntfy resolve isso usando o servidor público `ntfy.sh` como relay intermediário: seu servidor auto-hospedado repassa ao `ntfy.sh`, que aciona a APNs da Apple, que entrega ao iPhone. Para Android isso não é necessário.

---

## 3. Arquitetura de comunicação

```
[Celular do admin]
       ↕  WebSocket persistente
[nginx :80 → /ntfy/]
       ↕  proxy interno Docker
[Container ntfy-dfeb :80]
       ↑  POST interno Docker
[Container estoque-dfeb (Streamlit)]
```

O ponto importante: **Streamlit fala com ntfy diretamente pela rede interna Docker** (`http://ntfy:80`) — sem passar pelo nginx, sem ir para a internet. É uma comunicação privada dentro do servidor.

O celular do admin acessa o ntfy por fora via `http://201.76.56.247/ntfy/` — o nginx na porta 80 recebe e encaminha para o container ntfy. `Nenhuma porta nova foi aberta no firewall do VPS`.

---

## 4. O serviço Python: push_service.py

**Estrutura**
`configurado()` — verifica se `NTFY_TOPIC` e `NTFY_TOKEN` estão definidos no `.env`. Se não estiver configurado, nenhuma função tenta enviar nada. O sistema funciona normalmente sem o ntfy configurado.

`enviar(titulo, mensagem, prioridade, tags, link)` — função base. Faz o POST para o ntfy com timeout de 5 segundos. Se falhar (ntfy offline, credencial errada, timeout), registra um `warning` no log e retorna `False` — **nunca lança exceção, nunca quebra o fluxo do app**.

**4 helpers semânticos** — chamados pelos triggers nos eventos:

| Função | Prioridade ntfy | Tags (emoji no app) | 
| --- | --- | --- | 
| `notificar_formulario_recebido` | 4 (high) | 📋 clipboard | 
| `notificar_decisao_orcamento` | 4 ou 5 (urgente se devolvido) | ✅ / 🔄 / ❌ | 
| `notificar_estoque_zerado` | 5 (urgent/max) | 🚨 rotating_light | 
| `notificar_estoque_abaixo_minimo` | 4 (high) | ⚠️ warning | 

As **prioridades do ntfy** controlam como o app do celular exibe a notificação:

* `3` = padrão, silenciosa
* `4` = alta, toca som
* `5` = urgente, rompe o modo "não perturbe" (use com moderação)

---

## 5. Os 4 triggers

### Trigger 1 — Formulário recebido (`Solicitar.py`)

**Quando dispara:** setor submete o formulário público e o pedido é salvo com sucesso no banco.

**O que acontece antes:** criar_pedido_solicitacao valida ciclo aberto, prazo vigente, e persiste o pedido atomicamente. Só após isso, no bloco else (sucesso), o push é enviado.

**Notificação no celular:**

```
📋 Formulário recebido
Manutenção enviou as solicitações do período Junho/2026.
Acesse Análise de Compras para triagem.
```

**Por que é importante:** o formulário é uma página pública, o admin não está presente. Sem notificação, ele só saberia quando abrisse o app por conta própria.

### Trigger 2 — Decisão de orçamento (Aprovacao_Orcamento.py`)

**Quando dispara:** o diretor clica em "Registrar decisão" e registrar_decisao_diretor é executado com sucesso.

**O que acontece antes:** a decisão por item (aprovar/reprovar/revisar) já está registrada no banco. O push vem imediatamente antes do st.success.

**Notificação no celular (exemplos):**

```
✅ Orçamento aprovado
ORC-2026-06-001 — Aprovado. Período: Junho/2026.
Acesse Orçamentos para ver a decisão do diretor.
```

```
🔄 Orçamento devolvido para revisão   ← prioridade urgente
ORC-2026-06-001 — Devolvido para revisão. Período: Junho/2026.
Acesse Orçamentos para ver a decisão do diretor.
```

**Por que é importante:** o processo de aprovação pode levar dias. O admin manda o link ao diretor e aguarda. Sem notificação, fica consultando o app manualmente para saber se voltou.

### Trigger 3 — Item zerado (`estoque_service.py`)

**Quando dispara:** uma saída registrada em Estoque → Movimentar faz estoque_atual ir de qualquer valor positivo para ≤ 0.

**Edge detection:** nova_qtd <= 0 AND qtd_anterior > 0 — só dispara na transição. Se o item já estava zerado e outra saída for registrada, não dispara de novo.

**Notificação no celular:**

```
🚨 Estoque zerado
Papel A4 chegou a zero unidades.
Verifique a necessidade de reposição urgente.
```

### Trigger 4 — Item abaixo do mínimo (estoque_service.py)

**Quando dispara:** uma saída faz estoque_atual cruzar abaixo de estoque_minimo_vigente.

**Edge detection:** nova_qtd < minimo AND qtd_anterior >= minimo — só dispara na transição de "ok" para "abaixo do mínimo". Não dispara se item já estava abaixo.

**Notificação no celular:**

```
⚠️ Abaixo do mínimo
Caneta Azul: estoque atual 3 (mínimo 10).
Considere abrir pedido de reposição.
```

---

## 6. Variáveis de ambiente necessárias

No arquivo `.env` do VPS, três variáveis controlam o sistema:

```
# NTFY_SERVER não precisa ir no .env — o padrão já é o endereço Docker correto
# NTFY_SERVER=http://ntfy:80   ← valor padrão em config.py

NTFY_TOPIC=dfeb-estoque
NTFY_TOKEN=tk_xxxxxxxxxxxxxxxxxxxxxxxx
```

`NTFY_SERVER` tem `http://ntfy:80` como padrão em `core/config.py`, que é o endereço correto dentro do Docker. Só precisa ser alterado se o container tiver outro nome.

---

## 7. O que fazer agora para funcionar

São 4 passos depois do deploy. Execute na ordem:

1. **Passo 1 — Commit e deploy**

```
# Local: commit das mudanças
git add .
git commit -m "feat: camada de push notifications via ntfy"
git push

# VPS: atualizar e subir containers
git pull
docker compose up -d --build
```

2. **Passo 2 — Verificar se ntfy subiu**

```
# Na VPS: verificar se o container está rodando
docker ps | grep ntfy

# Testar o health check (deve retornar {"healthy":true})
curl http://localhost/ntfy/v1/health
```

3. **Passo 3 — Criar usuário e token**

```
# Criar usuário admin do ntfy
# (vai pedir uma senha — guarde ela para usar no app do celular)
docker exec -it ntfy-dfeb ntfy user add --role=admin admin

# Gerar token de publicação para o Streamlit
docker exec -it ntfy-dfeb ntfy token add admin
# Saída exemplo:
# token tk_AgQdq763PAke3zEfe2OwdhzpvMtPP5Xl5zXXXXX

# Copie o token gerado
```

4. **Passo 4 — Configurar o .env da VPS**

```
# Editar o .env
nano .env

# Adicionar no final:
NTFY_TOPIC=dfeb-estoque
NTFY_TOKEN=tk_AgQdq763PAke3zEfe2OwdhzpvMtPP5Xl5zXXXXX

# Reiniciar o Streamlit para carregar as novas vars
docker compose restart estoque-dfeb
```

5. **Passo 5 — Configurar o app ntfy no celular**

- Instalar o app ntfy (Android: Play Store ou F-Droid / iOS: App Store) — gratuito
- Abrir o app → menu → Manage accounts → Add account
- Servidor: http://201.76.56.247/ntfy
- Usuário: admin / Senha: a que você definiu no Passo 3
- Voltar para a tela principal → Subscribe to topic
- Tópico: dfeb-estoque

A partir deste momento, qualquer notificação publicada pelo sistema chegará no celular.

---

8. Comportamento sem configuração

Se `NTFY_TOPIC` ou `NTFY_TOKEN` não estiverem no `.env`, a função `configurado()` retorna `False` e **nada é enviado**. O app funciona normalmente. Os triggers existem no código mas são no-op. Isso garante que o sistema não quebra em ambientes locais de desenvolvimento.
