# 1. Responsabilidade correta da camada de Compras

A camada de **Compras** (renomear para **Análise de Compras**) deve ser responsável por:

**Analisar necessidade de reposição**
+ receber solicitações de materiais de outros setores
+ consolidar demanda real com necessidade de estoque
+ sugerir quantidade de compra
+ permitir ajuste humano da quantidade final
+ gerar lista final para Orçamento
+ preservar histórico mensal

## Delimitação Ideal de Responsabilidades

A delimitação que eu recomendo é esta:

- **Painel de Reposição:** resultados retornados pelo **motor de análise**, deve ser apenas leitura e navegação. Serve para enxergar o estado do estoque, informações e buscas trazidas automaticamente pelo sistema, fácil visualização, entendimento e navegação. Uma aba para a visão geral do Estado do Estoque atual nesse período, não deve classificar solicitações nem aprovar itens.

- **Solicitações e Pendências:** deve ser a fila de entrada e saneamento de **formulários com solicitações e pedidos de compra**. Aqui o responsável vê o que chegou, classifica, corrige exceções e resolve pendências de cadastro ou parametrização. Não deve calcular quantidade de compra nem aprovar nada para a lista final, mas sim uma camada anterior, que aprova solicitações para a consolidação final.

- **Consolidação:** ponto de encontro entre **Dados analisados/Gerados automaticamente e Solicitações Aprovadas**, deve ser o ponto de transformação da demanda (revisão, edição se necessária) em lista de compra definitiva. Aqui entram só as solicitações aprovadas e a sugestão do motor para uma revisão e inclusão da quantidade final usada para exportar e alimentar orçamentos posteriormente.


Ela **não** deve ser responsável por:
- cotação detalhada
- comparação de fornecedores
- pedido real de compra
- aprovação financeira
- compra realizada

Esses pontos pertencem à próxima camada, **Orçamento**, ou a uma futura camada de **Recebimento**.


---

## Estrutura de status ideal

O ideal é manter poucos status visíveis, totalmente alinhados com oque já possuimos, mas para a "Consolidação" da lista final, e oque deve entrar para compras deve seguir o mapeamento a seguir.

### Status técnico 

Esse status é usado pelo motor para explicar a situação real do item.
- SEM_PARAMETRO
- ZERADO
- ABAIXO_MINIMO
- ABAIXO_IDEAL
- OK

## Mapeamento correto

| Status técnico                               | Interpretação                                 |
| -------------------------------------------- | --------------------------------------------- |
| `SEM_PARAMETRO`                              | Sistema não consegue recomendar com segurança |
| `ZERADO`                                     | Compra altamente recomendada                  |
| `ABAIXO_MINIMO`                              | Compra recomendada                            |
| `ABAIXO_IDEAL` com demanda/consumo relevante | Compra sugerida com ressalva                  |
| `ABAIXO_IDEAL` sem demanda/consumo relevante | Apenas monitorar                              |
| `OK`                                         | Não comprar                                   |

Esse desenho mantém a tela clara, alinhada com os status existentes, mas preserva a inteligência interna do sistema.

---

# 4. Regra principal para `ABAIXO_IDEAL`

Esse é o ponto mais sensível.

Não dá para dizer que todo item abaixo do ideal deve ser comprado. Isso inflaria a lista e faria o sistema sugerir compras desnecessárias.

A regra ideal:

```text
ABAIXO_IDEAL só vira comprar se houver sinal operacional de necessidade.
```

Sinais que devem pesar:
1. houve solicitação aprovada para o item
2. houve consumo recente relevante
3. o estoque atual está muito próximo do mínimo
4. a quantidade atual não cobre o consumo médio esperado até a próxima revisão

Caso contrário:

```text
ABAIXO_IDEAL vira ok, com motivo "abaixo do ideal, mas sem demanda suficiente para compra"
```

Exemplo:

```text
Item A
atual = 8
mínimo = 5
ideal = 15
sem solicitação
sem consumo recente

status técnico: ABAIXO_IDEAL
status final: ok
quantidade sugerida: 0
motivo: abaixo do ideal, mas sem demanda recente
```

Outro exemplo:

```text
Item B
atual = 8
mínimo = 5
ideal = 15
solicitação aprovada = 10
consumo recente alto

status técnico: ABAIXO_IDEAL
status final: comprar
quantidade sugerida: 7 ou mais, conforme regra de consolidação
motivo: abaixo do ideal com demanda aprovada/consumo relevante
```

---

# 5. Regra de quantidade sugerida

A quantidade sugerida não deve ser simplesmente:

```text
ideal - atual
```

Essa regra é limitada. Ela ignora solicitações, consumo e contexto.

A regra ideal deve considerar três forças:
* necessidade de reposição
* demanda aprovada
* proteção mínima do estoque

## 5.1. Campos base

Para cada item:
- estoque atual
- estoque mínimo vigente
- estoque ideal vigente
- quantidade solicitada aprovada
- consumo recente estimado
- quantidade sugerida pelo sistema
- quantidade final definida pelo responsável

## 5.2. Reposição até o ideal

```text
reposicao_ideal = max(IDEAL - estoque_atual, 0)
```

Essa é a necessidade bruta para voltar ao ideal.

---

## 5.3. Demanda aprovada

```text
demanda_aprovada = soma das solicitações aprovadas do item na competência
```

Essa demanda precisa entrar no cálculo porque a compra não deve olhar apenas estoque mínimo/ideal.

---

## 5.4. Quantidade sugerida base

A regra mais segura é:

```text
quantidade_sugerida = max(reposicao_ideal, demanda_aprovada)
```

Mas isso ainda pode ser excessivo em alguns casos.

Uma versão mais equilibrada:

```text
quantidade_sugerida = max(
  reposicao_ideal,
  demanda_aprovada - estoque_disponivel_acima_do_minimo
)
```

Onde:

```text
estoque_disponivel_acima_do_minimo = max(estoque_atual - estoque_minimo, 0)
```

Essa regra evita comprar tudo que foi solicitado quando o estoque já consegue absorver parte da demanda sem ficar abaixo do mínimo.

---

## 5.5. Exemplo correto

```text
Estoque atual: 20
Mínimo: 10
Ideal: 30
Solicitação aprovada: 8
```

Cálculo:

```text
reposicao_ideal = 30 - 20 = 10
estoque disponível acima do mínimo = 20 - 10 = 10
demanda líquida = max(8 - 10, 0) = 0
quantidade sugerida = max(10, 0) = 10
```

Resultado:

```text
comprar 10
```

Agora outro caso:

```text
Estoque atual: 12
Mínimo: 10
Ideal: 30
Solicitação aprovada: 15
```

Cálculo:

```text
reposicao_ideal = 18
estoque disponível acima do mínimo = 2
demanda líquida = 15 - 2 = 13
quantidade sugerida = max(18, 13) = 18
```

Resultado:

```text
comprar 18
```

Outro caso:

```text
Estoque atual: 40
Mínimo: 10
Ideal: 30
Solicitação aprovada: 15
```

Cálculo:

```text
reposicao_ideal = 0
estoque disponível acima do mínimo = 30
demanda líquida = max(15 - 30, 0) = 0
quantidade sugerida = 0
```

Resultado:

```text
não comprar
```

Mesmo havendo solicitação, o estoque já cobre.

---

# 6. Substituir o botão manual por análise automática controlada

O ideal:

## 6.1. Análise automática (e/ou acessar a página)

A análise deve ser recalculada automaticamente quando houver mudança relevante:
- nova movimentação de entrada
- nova movimentação de saída
- alteração de mínimo/ideal
- solicitações aprovada
- solicitações recusada
- alteração de itens

## 6.2. Botão opcional

O botão pode existir como:

```text
Recalcular Analise de Compras
```

Mas não como única forma de atualizar a análise.

Ele deve mostrar:
- última atualização
- quantidade de itens analisados
- alertas encontrados

---

# Fluxo de trabalho ideal

1. Início da competência mensal

No primeiro acesso do mês, ou quando o mês muda, o sistema atualiza o "Periodo de Referência":

```text
Junho | 2026
status: aberta
```

O motor executa a análise inicial.

Resultado:

```text
pré-lista automática de compras
```


2. Entrada de solicitações

Os setores preenchem solicitações de materiais (o ideal é que o envio dos formulários também sejam enviados com o "Periodo" sempre pré-definido e conforme o mês atual e sem possibilidade de alterar, assim o controle dos formulários fica mais claro).
**Importante: No formulário e no sistema, deve ter campos de "Prioridade", que o solicitante pode selecionar aos itens, e o responsável pelo estoque pode navegar pela prioridade deles**


3. Consolidação automática

O sistema cruza as informações automáticas e solicitações:
- estoque atual
- parâmetros do item
- históricos
- solicitações aprovadas


4. Revisão humana

O responsável vê a tabela, pode editar e incluir a lista final:
- quantidade final
- observação

Mas o sistema mantém:
- quantidade sugerida (gerada auto/original)
- motivo da sugestão
- status

Isso é essencial para auditoria.


5. Fechamento da lista

Quando a análise estiver revisada:
- Decidir oque Incluir a lista final
- Salvar Alterações

A partir daí:
- quantidades finais e itens incluidos aparecem na visualização da lista final aprovada
- é possível ser exportada
- a camada porterior de Orçamento passa a consumir essa lista

---

# Especificação final resumida

A camada de **Compras** deve ser o módulo de **preparação inteligente da compra**, não o módulo de compra em si.

Ela deve responder com clareza:
- O que precisa comprar?
- Por que precisa comprar?
- Quanto o sistema sugere?
- Quanto foi solicitado?
- Quanto o responsável decidiu comprar?
- O que vai para orçamento?
- Qual era a lista de cada mês?

Essa é a base correta para a próxima etapa natural: **Orçamento**.
