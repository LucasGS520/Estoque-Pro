# Definição e Entendimento - Camada de Compras

Um risco central, sobre essa funcionalidade é: **se a camada Compras virar apenas uma soma entre “pedido dos solicitantes” + “estoque baixo”, ela vai gerar compra inflada**. Os pedidos/solicitações de materiais são uma **solicitação de compra**.

A função da camada é filtrar, validar, consolidar e transformar dados dispersos em uma lista defensável para orçamento, a consolidação correta deve partir destas premissas:
- Solicitação de compra ≠ compra aprovada
- Solicitação de compra ≠ saída de estoque
- Estoque abaixo do ideal ≠ necessidade automática de compra
- Estoque abaixo do mínimo = alerta forte de reposição
- Estoque zerado = alerta crítico
- Lista final = somente o que passou pela análise

Portanto, ela não baixa estoque, não movimenta item e não deve gerar compra automática. Ela serve como um dado de intenção, prioridade e justificativa. A camada Compras deve cruzar essa intenção com o estoque real para decidir se faz sentido comprar ou não. Isso está alinhado com a definição de que Compras é uma camada de validação da necessidade, não de orçamento, recebimento ou aprovação final. 

## 1. O que é a camada “Compras”

A camada **Compras** deve ser entendida como uma camada de **inteligência de reposição/compras**.

Ela não é:
* módulo financeiro;
* módulo de orçamento;
* módulo de recebimento;
* módulo de fornecedor;
* módulo de pedido de compra completo;
* aprovação final da compra.

Ela é a etapa que responde:
> “Com base no estoque atual, nos parâmetros mínimos/ideais e nas solicitações dos setores, o que realmente precisa ser comprado?”

O limite correto é este:
* Compras = define necessidade
* Orçamentos = pesquisa preço / fornecedor / cotação
* Estoque = registra entrada e saída real

Se essa separação não for respeitada, o módulo cresce demais e começa a misturar responsabilidades diferentes.

### Regra estrutural da camada Compras

A camada Compras deve operar com três grupos separados:
1. Itens que realmente devem ser avaliados para compra
2. Itens que estão pendentes de decisão/cadastro/parametrização
3. Itens que estão apenas em alerta, mas não entram na lista final

O erro seria colocar tudo em uma única lista chamada “comprar”.

A estrutura correta é:

```text
Solicitações dos setores
+ Situação real do estoque (Estoque atual)
+ Regras de mínimo/ideal
+ Itens críticos/zerados
+ Pendências de cadastro
        ↓
Análise inteligente
        ↓        
Camada Compras
+ Lista preliminar
+ Pendências
+ Alertas
        ↓
Lista final para Orçamentos
```

A própria especificação já indica que a lista final não deve nascer de uma única origem e que itens como não cadastrados, sem mínimo/ideal, pedido excepcional, precisam aparecer como pendências ou exceções para decisão humana. 

---

## 2. Ideia central da funcionalidade

A regra mental deve ser:
> Solicitação não é compra definitiva. Solicitação é uma entrada para análise.

Exemplo simples:

```
Setor pede: 20 unidades
Estoque atual: 35
Mínimo: 10
Ideal: 40
```

O sistema não deve comprar 20.

Ele deve perguntar:
- Se eu atender esse pedido, o estoque vai para 55.
- Se compra, o valor ultrapassa o ideal, e ele está acima do mínimo mesmo sem compra.
- Então a compra não é obrigatória, mas pode ser analisada se compra 5 ou mais para chegar ao ideal.

### Nova regra principal: o ideal não é gatilho automático

Esse ponto precisa ficar fechado.

#### Errado

```text
Estoque atual: 25
Mínimo: 10
Ideal: 40

Como está abaixo do ideal, comprar 15.
```

Isso gera compra inflada.

#### Correto

```text
Estoque atual: 25
Mínimo: 10
Ideal: 40
Solicitações de compra: nenhuma

Resultado:
Não entra automaticamente na lista de compra.
Status: OK abaixo do ideal / monitoramento.
```

O **mínimo** é o limite de segurança.

O **ideal** é uma referência de recomposição quando já existe motivo real para comprar.

Então:

```text
Estoque acima do mínimo e abaixo do ideal: Não comprar automaticamente.

Estoque abaixo ou igual ao mínimo: Entra em análise de reposição.

Estoque zerado: Entra em análise crítica.

Pedido de compra validado: Pode justificar compra mesmo com estoque acima do mínimo.
```

### Quando usar mínimo e quando usar ideal

Essa decisão precisa ser política de negócio.

#### Comprar até o mínimo

Usar quando:
- Produtos Zerados, mas Pedidos
- Item comum
- Baixo giro
- Compra não urgente
- Estoque apenas levemente abaixo do mínimo

#### Comprar até o ideal

Usar quando:
- Item de alto consumo
- Item ficou zerado recentemente
- Item ficou abaixo do mínimo várias vezes
- Pedido recorrente de vários setores
- Compra é feita constantemente

### Regra consolidada

Se há necessidade de compra, o sistema calcula e sugere com base nos status do produto.

Depois:
- sugerir quantidade-base.
- sugerir recomposição até o ideal.
- Se pedido excepcional aprovado: respeitar quantidade aprovada.

Isso resolve seu ponto: **não é porque o item está abaixo do ideal que ele deve ser comprado**, mas quando ele já precisa ser comprado por outro motivo, o ideal pode orientar quanto comprar.

---


## 3. Responsabilidades e Fluxo ideal de execução

O fluxo ideal deve manter a decisão rastreável.

A pergunta deixa de ser:
> “Quem pediu isso?”

E passa a ser:
> “Esse item realmente precisa ser comprado? Se sim, por qual motivo e em qual quantidade?”

A lógica geral pode ser esta, para cada item no período:

1. Consolidar solicitações de compra dos itens.
2. Verificar se o item está cadastrado.
3. Verificar mínimo/ideal.
4. Consultar estoque atual.
5. Calcular necessidade por solicitação.
6. Calcular necessidade por mínimo.
7. Avaliar pedidos/solicitações.
8. Gerar status.
9. Gerar quantidade sugerida.
10. Exigir revisão manual quando necessário.
11. Gerar lista final apenas após validação.

**Não deve fazer**

1. escolher fornecedor final;
2. negociar preço;
3. aprovar orçamento;
4. registrar entrada física da mercadoria;
5. controlar pagamento;
6. controlar recebimento;
7. substituir decisão humana em casos excepcionais.

Isso é importante porque “Compras”, neste estágio, não é um ERP completo de purchasing. É uma camada de **validação da necessidade de compra**.

---

## 4. Diferença entre quantidade sugerida e quantidade final

Esse ponto é essencial.

### Quantidade sugerida

É calculada pelo sistema.

Exemplo:
- Sistema sugere comprar 26 unidades.

### Quantidade final definida

É a quantidade que o responsável realmente decide mandar para orçamento.

Exemplo:
- Sistema sugeriu: 26
- Responsável definiu: 20
- Motivo: há compra em andamento de 6 unidades

Ou:
- Sistema sugeriu: 0
- Responsável definiu: 10
- Motivo: evento excepcional no mês

A quantidade final deve ser editável, mas qualquer alteração deve exigir motivo.

Sem motivo, o sistema perde rastreabilidade.

---

## 5. Definição consolidada

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
