# Especificações e Comportamento Ideal - Envio e Formato Solicitações Materiais

O formulário de "Solicitações de Materiais" ainda não está adequado ao público final de uso. O problema principal não é apenas a aparência, mas também a quantidade de decisões e mecanismos expostos ao solicitante. Hoje ele precisa preencher diversos casos manualmente, compreender busca, filtro, catálogo, categoria, item novo, revisão e correção por remoção.

Além disso, o sistema precisa funcionar de maneira mais "Automatizada", deixar de ser apenas um sistema para controle, mas realmente algo que agrega valor e reduz o trabalho sobre as partes afetadas. 

**Sugestões e Ideai Proposta:** Transformar a entrega em algo automatizado, bem completo e funcional, melhorando a operação e fluxo de execução sobre essas camadas, melhorando ambas as partes (setores/solicitantes e responsável pelo estoque)

O ponto fraco da proposta é simples: **o sistema não consegue enviar algo “para o setor” sem existir um destino de comunicação associado ao setor**.

Hoje, `Setor` possui apenas nome, descrição, situação ativa e data de criação; os serviços de cadastro seguem a mesma estrutura. A evolução correta não é simplesmente “automatizar mensagens”. É criar um **Ciclo Mensal de Solicitações**, no qual o WhatsApp seja apenas o canal de comunicação.

---

## 1. Responsabilidade da nova camada

A camada deve ser responsável por:
* abrir a janela mensal de solicitações;
* identificar quais setores precisam responder;
* gerar um formulário específico para cada setor;
* enviar o formulário pelo canal configurado;
* acompanhar acesso e envio;
* lembrar apenas quem ainda não respondeu;
* registrar falhas de comunicação;
* encerrar a janela;
* notificar resultados relevantes da análise.

O WhatsApp não deve controlar o fluxo. O sistema controla o fluxo e envia mensagens quando determinados eventos acontecem.

## 2. Conceito central: Ciclo de Solicitações

Cada mês deve possuir um registro próprio:

```text
CicloSolicitacaoMaterial
- id
- periodo_referencia
- abertura_em
- prazo_resposta_em
- encerrado_em
- status
- criado_em
```

Exemplo:

```text
Ciclo: Junho/2026
Abertura: 01/06/2026
Prazo: 07/06/2026
Status: Aberto
Setores esperados: 12
Respondidos: 9
Pendentes: 3
```

O ciclo passa a ser a origem oficial do período. O formulário não deve calcular sozinho o mês apenas com `date.today()`.

Isso também evita problemas caso:
* a coleta de julho seja aberta ainda em junho;
* o prazo seja prorrogado;
* seja necessário reabrir um período;
* um setor precise enviar uma complementação;
* o responsável queira consultar campanhas anteriores.

## 3. Cadastro mínimo dos setores

A interface, cadadstro dos setores precisa ter:

```text
Nome do setor *
Descrição

WhatsApp
[ Apenas número ]

[ ] Ativo
```

Esse número WhatsApp, é o número **que o formulário relacionado a esse setor** será direcionado. Na interface, isso ainda aparece como apenas um campo. A separação é interna e permite futuramente usar e-mail ou outro canal sem alterar `Setor`.

## 4. Link personalizado por setor

O sistema deve gerar um link diferente para cada combinação de ciclo e setor, deve identificar internamente, por exemplo:

```text
Ciclo Junho/2026
Setor Manutenção
Prazo 07/06/2026
```

Ao abrir o formulário:
* o setor já estará definido;
* o período já estará definido;
* ambos ficarão bloqueados;
* o usuário preencherá somente seu nome e os materiais;
* o formulário saberá a qual campanha pertence.

Atualmente, o usuário precisa selecionar manualmente o setor. Isso reduz erros e impede que alguém, por exemplo, do setor Manutenção envie acidentalmente como Financeiro.

## 5. Fluxo mensal automatizado

### Abertura

No dia definido:

1. o sistema abre o ciclo;
2. carrega todos os setores `ativos`, os que recebem solicitações;
3. cria um `CicloSolicitacaoSetor` para cada um;
4. gera as notificações de convite;
5. o serviço de mensagens executa os envios.

Mensagem:

> Solicitações de materiais — Junho/2026
> O período para envio do setor Manutenção está aberto.
> Prazo: 07/06/2026.
>
> [Preencher solicitação]

**Observação importante:** O formulário atual não possui uma entidade real de formulário: a tela administrativa reconstrói agrupamentos usando setor e solicitante. Isso pode fundir envios diferentes da mesma pessoa. 

Portanto, a criação do cabeçalho `SolicitacaoPedido` continua sendo necessária.

## 6. Política de lembretes

O sistema não deve enviar mensagens diariamente. Isso gera ruído, custo e tendência de bloqueio ou desconsideração.

Política inicial recomendada:

```text
Abertura:
Mensagem inicial com formulário

Após 2 dias:
lembrete somente para quem não enviou

Um dia antes do prazo:
lembrete final somente para pendentes

Após o prazo:
alerta interno para o responsável pelo estoque
```

## 7. Notificações sobre a análise

Aqui há outro risco: o solicitante não deve receber uma mensagem a cada aprovação ou rejeição individual feita pelo responsável.

Isso geraria várias mensagens para um mesmo formulário e exporia estados internos difíceis de interpretar.

### Status interno não deve ser status público

O sistema possui estados como:

```text
validada
aprovada
rejeitada
novo_item
sem_parametros
compra_avulsa_aprovada
```

Esses estados servem à operação interna.

Em especial, `aprovada` significa aprovada para consolidação, não que a compra foi realizada. Enviar “seu item foi aprovado” criaria uma expectativa incorreta.

### Estados apresentados ao solicitante

Use uma camada pública mais simples:

| Estado público             | Significado                                                         |
| -------------------------- | ------------------------------------------------------------------- |
| Recebida - em análise      | O sistema registrou a solicitação e o responsável começou a análise |
| Análise concluída          | Todos os itens foram avaliados                                      |

A mensagem de conclusão deve ser consolidada e com clareza sobre os itens.

Uma notificação deve ser produzida quando **o formulário por completo for concluido**, e não a cada ação realizada sobre os itens individuais.

## 8. Nova área em Compras

Na aba `Solicitações e Pendências`, o atual bloco com o endereço local fixo deve ser substituído. Hoje a página mostra diretamente um endereço `localhost`, que não é utilizável externamente. 

A nova área deve começar com:

```text
Ciclo de Solicitações — Junho/2026

Status: Aberto
Prazo: 07/06/2026

12 setores esperados
9 respondidos
3 não acessaram/pendentes
0 falhas de comunicação
```

Ações:

```text
Enviar solitações pendentes
Reenviar falhas
Prorrogar prazo
Encerrar ciclo
```

Caso o setor não precise solicitar itens nesse periodo, Nesse caso, o ideal é pelo formulário uma ação simples:

```text
Sem solicitação de materiais neste período
```

Isso deve contar como resposta válida, evitando lembretes desnecessários.

---

## Observações Técnicas Importantes

### Streamlit não deve executar o agendador

O projeto atual usa Streamlit com SQLite local. 

Rotinas permanentes de lembrete não devem depender de uma página aberta, de `st.session_state` ou do rerun do Streamlit.

No mínimo, deve existir um processo separado:

```text
cron/agendador
    ↓
processar notificações pendentes
    ↓
API do WhatsApp
```
