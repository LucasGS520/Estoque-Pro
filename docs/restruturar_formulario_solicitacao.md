# Restruturar e Alinhar Formulário de Solicitações

O formulário ainda não está adequado ao público descrito. O problema principal não é a aparência: é a quantidade de decisões e mecanismos expostos ao solicitante. Hoje ele precisa compreender busca, filtro, catálogo, categoria, item novo, revisão e correção por remoção. Isso transfere para o usuário parte da lógica interna do sistema.

## 1. Problemas estruturais identificados

### Urgência global

O banco já armazena `urgente` em cada `SolicitacaoMaterial`, portanto a estrutura atual suporta urgência individual. O erro está no formulário: o checkbox fica na identificação e o mesmo valor é copiado para todos os itens durante o envio.   

A correção mínima é incluir a urgência dentro de cada item mantido em `st.session_state["sol_itens"]`, somente mover o checkbox não resolve o fluxo completo.

Atualmente, a urgência:
* ordena as solicitações;
* aparece em métricas e indicadores;
* é preservada quando o item vira compra avulsa.

Ela não participa da consolidação porque `SolicitacaoRecord`, usado pelo motor, transporta apenas setor, solicitante e quantidade.

### Urgência individual

Urgência não deve:
* aprovar automaticamente o pedido;
* ignorar o estoque disponível;
* aumentar artificialmente a quantidade sugerida;
* pular pendências de cadastro ou parametrização.

Urgência deve:
* colocar o item no topo da fila de revisão;
* permitir filtro específico;
* destacar setor;
* ser preservada na consolidação;
* aparecer na lista final e na futura camada de Orçamentos.

### O “formulário” não existe como entidade

Cada item enviado vira um registro independente de `SolicitacaoMaterial`. Na tela de Compras, o sistema reconstrói um suposto formulário agrupando registros por setor e solicitante. 

Isso pode juntar indevidamente:
* dois envios feitos pela mesma pessoa no mesmo mês;
* uma solicitação comum e outra complementar;
* pedidos enviados em dias diferentes.

Sem isso, “aprovar formulário”, “excluir formulário”, protocolo e rastreabilidade continuarão sendo aproximações.

### Envio não atômico

O formulário percorre os itens e chama `criar_solicitacao` separadamente. Essa função faz `commit` em cada item. Se houver falha no terceiro item, os dois primeiros podem permanecer gravados, produzindo um pedido parcial.  

O envio deve ocorrer em uma única transação:

```text
criar cabeçalho
criar todas as linhas
commit único
```

Em caso de erro, nenhuma linha deve ser persistida.

### Item não encontrado

O atual “Solicitar Novo Item” fica visualmente escondido em um expander. Para usuários pouco familiarizados, deve ser uma ação evidente:

```text
Não encontrou o material?
[ Solicitar um material diferente ]
```

Campos mínimos, padrão já existente. A resolução final é responsabilidade do setor de estoque.

### Revisão e Envio

Cada item deve permitir:
* Editar (alterar quantidade, alterar observação)
* marcar ou desmarcar prioridade;
* remover.

A regra atual, que obriga remover o item para alterar a quantidade, deve ser eliminada.

---

## Resumo Final

A mudança mais crítica não é visual. É deixar de tratar o pedido como uma coleção de registros independentes e passar a tratá-lo corretamente. Sem isso, o formulário pode ficar mais simples, mas a rastreabilidade e a governança continuarão frágeis.
