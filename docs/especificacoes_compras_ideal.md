# Especificações e Alinhamento Ideal - Compras e Solicitações

A leitura do código mostra que a lógica já está separada corretamente nos serviços: `classificar_solicitacoes_periodo` trata só da triagem dos pedidos e `consolidar_periodo` processa apenas solicitações validadas. Isso aparece em `compras_service.py`. O ponto que ainda está confuso é a experiência da página de Compras, porque as abas misturam visão, triagem, consolidação e aprovação no mesmo contexto em `Compras.py`.

## Delimitação Ideal de Responsabilidades

A delimitação que eu recomendo é esta:

- **Painel de Reposição:** deve ser apenas leitura e análise. Serve para enxergar o estado do estoque, informações e buscas trazidas automaticamente pelo sistema, fácil visualização, entendimento e navegação. Uma aba para a visão geral do Estado do Estoque atual nesse período, não deve classificar solicitações nem aprovar itens.

- **Solicitações:** renomeado para **Solicitações e Pendências**, deve ser a fila de entrada e saneamento. Aqui o responsável vê o que chegou, classifica, corrige exceções e resolve pendências de cadastro ou parametrização. Não deve calcular quantidade de compra nem aprovar nada para a lista final.

- **Consolidação:** ponto de encontro entre **Dados analisados e gerados automaticamente e Solicitações validas**, deve ser o ponto de transformação da demanda (revisão, edição se necessária) em lista de compra definitiva. Aqui entram só as solicitações validadas, a soma por item, a sugestão do motor e a revisão da quantidade final e do motivo, o ideal é que nessa etapa, também seja possível gerar e visualizar a lista final, usada para exportar e alimentar orçamentos.

> OBS: nessa nova delimitação e modelo, a "Lista Final" deve ser REMOVIDA, a funcão de gerar documento e visualizar lista final passa a ser cargo de "Consolidação".
