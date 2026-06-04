# Especificações Ideais - Compras

Importante, a **solicitação de materiais não é demanda real de compra**. É uma intenção/pedido. A camada “Compras” precisa existir justamente para filtrar, validar, cortar excesso e juntar isso com a necessidade real do estoque.

Se ela apenas somar “o que os solicitantes pediram” + “o que está baixo no estoque”, ela vai gerar compra inflada.

## 1. Responsabilidade correta da camada “Compras”

A camada **Compras** deve ser a etapa de **triagem, consolidação e validação da necessidade de compra**.

Ela não deve ser responsável por cotar, negociar fornecedor ou fechar orçamento. Isso já pertence melhor à camada futura de **Orçamentos**, que hoje já usa a análise de compras para consolidar valores por fornecedor e cadastrar cotações. 

A responsabilidade ideal de “Compras” deve ser:

Receber demandas dos Solicitantes
+ analisar estoque atual
+ analisar mínimo/ideal vigente
+ analisar itens zerados ou críticos
+ comparar pedido com saldo disponível
+ sugerir quantidade real de compra
+ gerar lista consolidada para orçamento

Ou seja, ela responde:
- O que realmente precisa ser comprado?
- Quanto comprar?
- Por quê?
- De onde veio essa necessidade?

Ela não responde:
- De qual fornecedor comprar?
- Qual orçamento aprovar?
- Qual preço final?
- Quando será comprado?
- Compra foi recebida?

Esses pontos entram em outras camadas/responsabilidades.

### Valor que essa camada agrega ao RH

O valor não é apenas “gerar uma lista de compra”, isso o sistema já faz de forma simples hoje. O valor real é reduzir três problemas operacionais:

#### Evitar compra desnecessária

Exemplo:

```text
Gestor pede:
- 20 unidades de papel A4

Estoque atual:
- 35 unidades

Mínimo:
- 10

Ideal:
- 40

Resultado:
- Não comprar 20 automaticamente.
- Talvez comprar só 5, ou nem comprar, dependendo.
```

Sem essa análise, o RH vira apenas repassador de pedidos.

#### Consolidar demandas dispersas

Se três setores pedem o mesmo item, a camada deve consolidar corretamente oque comprar e quanto comprar:

```text
RH pediu: 10
Financeiro pediu: 5
Produção pediu: 20

Demanda bruta: 35
Estoque atual: 12
Estoque ideal: 30
```

A lista final não deve repetir o item três vezes. Ela deve mostrar uma linha consolidada, com detalhamento da origem.

#### Justificar a compra

Cada item na lista final deve ter motivo claro:
- Estoque zerado
- Abaixo do mínimo
- Pedido/Solicitação validado
- Demanda de múltiplos setores
- Reposição para voltar ao ideal
- Item sem mínimo definido, exige análise manual

Isso é importante porque a compra precisa ser defensável. Não basta dizer “o sistema sugeriu”.

---

## 2. O que o sistema deve fazer vs. o que continua manual

### O sistema deve fazer

A camada Compras deve automatizar a parte analítica:
- Receber ou registrar solicitações de materiais.
- Relacionar pedido com itens cadastrado.
- Mostrar estoque atual do item.
- Mostrar mínimo e ideal vigente.
- Mostrar status do item.
- Comparar quantidade pedida com necessidade calculada.
- Consolidar pedidos iguais.
- Sugerir quantidade final de compra.
- Sinalizar item novos/sem cadastro.
- Sinalizar item sem mínimo/ideal.
- Gerar lista final de compras.

O sistema já possui base para parte disso: os itens têm `estoque_atual`, mínimo/ideal vigente, campos automáticos/manuais e origem dos parâmetros. 

### O que deve continuar manual

Algumas decisões não devem ser automatizadas nesta etapa:
- Decidir comprar algo mesmo com estoque suficiente.
- Cortar ou aumentar uma quantidade sugerida.
- Validar pedidos novos/excepcionais de solicitantes.
- Resolver item pedido que não existe no cadastro.
- Negociar preço.
- Aprovar orçamento.
- Definir prioridade política/administrativa.

A camada deve permitir ajuste manual, se necessário.

---

## 3. Como as informações entram na camada

A lista final de compras não deve nascer de uma fonte única. Ela deve nascer do cruzamento de três blocos.

### Bloco A — Necessidade automática do estoque

Aqui entram os itens que o próprio estoque indica como problemáticos.

Exemplos:

```text
Estoque = 0
Status: zerado
```

```text
Estoque atual <= mínimo
Status: abaixo do mínimo / comprar
```

```text
Mínimo e ideal não definidos
Status: sem parâmetro
```

```text
Estoque atual > mínimo
Status: OK, mas ainda pode ser comprado dependendo
```

Esse bloco existe mesmo sem nenhuma solicitação.

Exemplo:

```text
Item: Luva descartável
Estoque atual: 4
Mínimo: 10
Ideal: 30
Solicitações: nenhuma

Quantidade sugerida: 30 - 4 = 26
Motivo: reposição automática — abaixo do mínimo
```

### Bloco B — Solicitações de Materiais

Aqui entram os pedidos de materiais para compra, mas tratados como **solicitações**.

Campos mínimos:
- Mês/período de referência
- Solicitante
- Setor
- Item solicitado
- Quantidade solicitada
- Observação
- Data da solicitação
- Data de aprovação, se existir
- Assinaturas, se fizer parte do fluxo atual

O ponto importante: o pedido deve estar vinculado ao catálogo do estoque sempre que possível.

O solicitante não deve digitar livremente “papel”, “papel A4”, “sulfite”, “resma A4” como se fossem coisas diferentes. Isso destrói a consolidação.

O ideal é:
1. Solicitante pesquisa item no catálogo
2. Seleciona item
3. Sistema preenche categoria, unidade e nome correto, conforme item selecionado
4. Solicitante informa quantidade e observação

### Bloco C — Item solicitado não cadastrado

Esse caso não pode entrar direto na lista final. Se o setor pede:
- Cabo HDMI 10m

e o item não existe no catálogo, o sistema não sabe:
- se já existe item equivalente;
- qual categoria aplicar;
- se será item recorrente ou compra avulsa;
- se deve controlar estoque;
- qual mínimo/ideal usar;
- qual fornecedor consultar.

**Regra correta**
Item solicitado não cadastrado:
- status = pendente_cadastro
- não entra na consolidação normal
- não entra automaticamente na lista final

Novo item deve entrar como `pendente_cadastro` e não ir para lista consolidada até ser cadastrado pelo responsável. 

### Bloco D - Item sem mínimo/ideal

Esse caso precisa ser dividido. O erro seria bloquear tudo ou comprar tudo.


**Situação A — Sem mínimo/ideal e sem solicitação**

```text
Item: Adaptador USB
Estoque atual: 3
Mínimo: não definido
Ideal: não definido
Solicitação: nenhuma
```

Resultado:

```text
Não entra na lista de compra.
Status: pendente_parametrizacao.
Ação: definir mínimo/ideal se o item for controlado.
```

**Situação B — Sem mínimo/ideal, mas com solicitação de compra**

```text
Item: Adaptador USB
Estoque atual: 3
Solicitação de compra: 10
Mínimo: não definido
Ideal: não definido
```

Resultado correto:

```text
Não calcular automaticamente.
Exibir na aba Pendências.
Permitir decisão manual.
```

Mas aqui há uma nuance importante: **não deve ser proibido comprar**. Pode haver um pedido legítimo.

**Regra consolidada**
- Se item não tem mínimo/ideal: sistema não calcula reposição automática.
- Se não há solicitação: apenas pendência de parametrização.
- Se há solicitação: entra como pendência de análise manual, podendo seguir para lista final apenas com decisão humana justificada.


---

## 2. Regras de Negócio — Solicitação × Estoque

Essas são as regras que a camada Compras deve aplicar ao cruzar os dois blocos:

**Regra 1 — Solicitação dentro da folga de estoque**
```
Se (estoque_atual - quantidade_solicitada) >= minimo:
    Não gera necessidade de compra por este pedido.
    Status: "Atendido pelo estoque atual"
```
O estoque absorve a demanda sem necessidade de reposição.

**Regra 2 — Solicitação pressiona abaixo do mínimo**
```
Se (estoque_atual - quantidade_solicitada) < minimo
    E (estoque_atual - quantidade_solicitada) >= 0:
    Gera necessidade de reposição para voltar ao ideal.
    Status: "Compra necessária — estoque mínimo pressionado"
    quantidade_recomendada = ideal - (estoque_atual - quantidade_solicitada)
```

**Regra 3 — Solicitação maior que o estoque**
```
Se quantidade_solicitada > estoque_atual:
    Parte do pedido não pode ser atendida com estoque atual.
    Status: "Compra necessária — saldo insuficiente"
    quantidade_recomendada = max(ideal - estoque_atual, quantidade_solicitada - estoque_atual)
```

**Regra 4 — Item já abaixo do mínimo, sem solicitação**
```
Se estoque_atual <= minimo E não há pedido:
    Entra pela lógica automática (Bloco A).
    Status: "Reposição automática"
    quantidade_recomendada = ideal - estoque_atual
```

**Regra 5 — Item zerado para produtos ativos**
```
Se estoque_atual = 0:
    Entra independente de pedido.
    Status: "Zerado"
    quantidade_recomendada = mínimo (ou ideal, mas recomendo para itens zerados comprar até o mínimo, isso se não houver solicitações)
```

**Regra 6 — Pedido sem parâmetros definidos**
```
Se item não tem minimo/ideal definido:
    Não é possível calcular automaticamente.
    Status: "Sem parâmetro — análise manual"
    Sinaliza como pendência de parametrização.
```

**Regra de consolidação entre setores:**
Quando múltiplos setores pedem o mesmo item, as quantidades são somadas antes de aplicar qualquer regra acima. O sistema mostra o detalhamento por setor, mas opera sobre a demanda consolidada.

---

### 3. Lógica da Quantidade Final Sugerida

Esse é o cálculo central da camada. Ele deve combinar três fontes em uma lógica hierárquica:

```
quantidade_necessaria_estoque = max(0, ideal - estoque_atual)
quantidade_solicitada = soma de todos os pedidos do período
quantidade_solicitada_liquida  = max(0, quantidade_solicitada - estoque_disponivel)

quantidade_sugerida = max(quantidade_necessaria_estoque, quantidade_demandada)
```

Em linguagem prática:

| Cenário | Fórmula aplicada |
|---|---|
| Só estoque baixo, sem pedido | `ideal − estoque_atual` |
| Pedido dentro do estoque OK | `0` (não comprar) |
| Pedido pressiona mínimo | `ideal − (estoque − pedido)` |
| Estoque zerado + pedido alto | `max(ideal, pedido_total)` |
| Pedido > ideal | `pedido_total` (respeita a demanda real) |

O campo `quantidade_final_definida` é sempre editável manualmente. O sistema sugere, o responsável decide e registra o motivo da alteração quando muda o valor sugerido.

---

### 4. Status dos Produtos — Definição Completa

O sistema atual tem: `comprar`, `zerado`, `ok`, `sem_minimo_definido`. Esses quatro precisam ser refinados para cobrir os cenários criados pela camada de solicitações.

**Status revisados e ampliados:**

| Status | Código | Condição |
|---|---|---|
| Zerado | `zerado` | `estoque = 0` |
| Abaixo do mínimo | `abaixo_minimo` | `0 < estoque <= minimo` |
| Reposição necessária | `comprar` | `estoque > minimo` mas pedido pressiona abaixo |
| Estoque OK | `ok` | `estoque > minimo` e nenhum pedido pressiona |
| Sem parâmetro | `sem_minimo` | mínimo/ideal não definido |
| Pendente de cadastro | `pendente_cadastro` | item novo solicitado, não vinculado |
| Excesso sinalizado | `excesso` | `estoque > ideal * 1.5` |

**O status `excesso`** é novo e relevante: quando o estoque está muito acima do ideal (ex: 2× o ideal), isso também é um problema operacional — capital parado, produto com validade, ou compra duplicada. Não entra na lista de compras, mas deve aparecer como sinalização na aba de Painel de Reposição.

---

## 5. Tela ideal da camada Compras

A página Compras deveria deixar de ser apenas “Rodar Análise” e passar a ter algo como:

```text
1. Painel de Reposição
2. Consolidação
3. Lista Final
```

### Ajustes na Estrutura de Abas

Sugestão de ajuste com base nas regras acima:

**Aba 1 — Painel de Reposição**
Exibe o status automático de todos os itens. Filtros rápidos por status. Deve incluir a sinalização de `excesso` como um grupo separado dos itens que precisam de compra.

**Aba 2 — Consolidação**
Cruza os dois blocos anteriores. Por item, mostra:
- Estoque atual / mínimo / ideal / status
- Pedidos consolidados (com detalhe por setor expansível)
- Quantidade sugerida pelo sistema
- Campo editável: quantidade final definida (preenchida automaticamente, mas devendo ser revisada ou ajustada)
- Campo editável: motivo (preenchido automaticamente, ajustável)

**Aba 3 — Lista Final**
Somente os itens com `quantidade_final_definida`. Limpa, pronta para orçamento. Deve incluir o campo "motivo" para cada linha — a compra precisa ser defensável, como o documento original já aponta.

---

## 6. Limite correto desta etapa

Para esta etapa, não deve ser criado um módulo completo de “Pedido de Compra” com recebimento, aprovação e status financeiro. Isso aumentaria demais o escopo.

O escopo correto agora é:
- Compras = geração inteligente da necessidade de compra.
- Orçamentos = pesquisa/cotação/estimativa.
- Estoque = entrada/saída real.

A camada Compras deve terminar quando a lista final estiver pronta para orçamento.

---

## 7. Definição consolidada

**A regra final da camada Compras deve ser:**

A camada Compras não compra porque alguém pediu.
A camada Compras não compra porque está abaixo do ideal.

A camada Compras sugere compra quando há necessidade validada:
- reposição ideal;
- estoque abaixo do mínimo;
- estoque zerado;
- solicitação de compra;
- compra avulsa aprovada.

E deve bloquear ou separar:
- item não cadastrado;
- solicitações/pedido sem aprovação;
- itens sem necessidade atual;
- estoque apenas abaixo do ideal.

A lógica mais saudável para o sistema é esta:

1. O mínimo define risco.
2. O ideal define alvo, não obrigação.
3. A solicitação define intenção.
4. Auxiliar na validação.
5. A lista final só contém decisão validada.

Essa camada, bem implementada, deixa de ser uma tela de “gerar compra” e passa a ser uma camada de **governança da necessidade de compra**.

### Pontos de atenção adicionais que o documento original não cobre

**Período de referência da solicitação:** Uma solicitação deve ter mês/período de referência claro. O sistema não deve misturar pedidos de períodos diferentes na mesma consolidação.

**Histórico de criticidade:** O documento menciona isso, mas não define o que é. Uma sugestão pragmática: registrar simplesmente quantas vezes nos últimos N ciclos o item ficou `zerado` ou `abaixo_minimo`. Com isso, é possível sinalizar itens com padrão de ruptura recorrente, mesmo quando o estoque atual está OK.

**Itens sem fornecedor vinculado:** O documento lista como sinalização. Vale definir que esses itens entram na lista final com uma flag específica (`sem_fornecedor`) para que a camada de Orçamentos já saiba que precisará de cotação aberta, não apenas consultar fornecedores cadastrados.
