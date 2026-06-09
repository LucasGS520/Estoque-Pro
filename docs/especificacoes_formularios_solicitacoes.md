Hoje o botão de `novo_item` e `sem_parametros` apenas navega para `pages/Estoque.py`, via `st.switch_page`, sem carregar uma resolução vinculada à solicitação. Isso aparece diretamente nos botões atuais da aba **Solicitações e Pendências**. Para `novo_item`, o sistema muda `session_state` e leva para Estoque > Editar > Itens; para `sem_parametros`, faz a mesma coisa. 

Esse é exatamente o problema de “pós-resolução”: o usuário até pode cadastrar ou editar algo no Estoque, mas a solicitação original não sabe necessariamente o que aconteceu, além do UX ser extremamente ruim para o usuário.

---

# Decisão recomendada

Transformar esses botões em **botões de resolução**, abrindo modal na própria página de Compras.

A regra deve ser:

Solicitação pendente
→ usuário abre modal
→ usuário resolve no modal
→ sistema atualiza o necessário na mesma transação
→ tela recarrega já consistente

Não recomendo deixar o usuário sair da página para resolver esses casos.

---

# Modal 1 — Novo Item

Esse modal deve ter três caminhos, não apenas “cadastrar item”.

## Caminho A — Vincular a item existente

Uso quando o solicitante escreveu algo como:

```text
Durex
Fita Transparente
Fita Colante Transparente
```

mas o item já existe no estoque.

### Ação do usuário

Seleciona um item existente.

### Ação do sistema

```text
1. Busca a solicitação pelo id
2. Define solicitacao.item_id = item_existente.id
3. Mantém solicitacao.nome_item_livre como histórico
4. Reclassifica a solicitação:
   - se item tem mínimo/ideal vigente > 0 → validada
   - senão → sem_parametros
5. Salva, e Já pode ser Aprovado/Rejeitado.
```

A classificação atual já considera que uma solicitação com `item_id` e parâmetros válidos vira `validada`, e com `item_id` mas sem mínimo/ideal vira `sem_parametros`.  O problema é que hoje falta a ação explícita que preenche esse `item_id` a partir da pendência.

---

## Caminho B — Criar novo produto de estoque

Uso quando o item realmente precisa entrar no estoque principal.

O sistema já tem um padrão bom para criação de item: `create_item()` valida categoria, normaliza nome, bloqueia duplicidade por nome normalizado dentro da categoria, cria item e inicializa mínimo/ideal manual quando informado. 

Então o modal não deve duplicar regra de criação. Deve **chamar o serviço existente**.

### Campos do modal

```text
Nome oficial do produto
Categoria
Unidade
Estoque atual inicial
Mínimo manual
Ideal manual
Fornecedores
Observações
Ativo
```

Esses campos batem com o formulário atual de cadastro em Estoque, que já usa categoria, unidade, estoque atual, mínimo manual, ideal manual, fornecedores, observações e ativo. 

### Regra importante

Depois de criar o item, o sistema precisa vincular automaticamente a solicitação ao item criado.

Fluxo:

```text
Novo Item pendente
→ Criar produto
→ item criado
→ solicitacao.item_id = item_criado.id
→ se mínimo/ideal definidos → validada
→ se mínimo/ideal não definidos → sem_parametros
```

Sem essa vinculação automática, o problema original continua.

O fluxo também para Aprovar/Rejeitar também deve estar atrelado a esse modal, se não usuário além disso, teria que aprovar ou rejeitar novamente em um fluxo manual.

---

## Caminho C — Compra Avulsa / Item Pontual

Aqui precisa cuidado. Não trate compra avulsa como `novo_item` resolvido. São coisas diferentes.

### Definição operacional

Compra avulsa é um item que:
- não entra no cadastro principal de estoque
- não terá mínimo/ideal
- não entra no motor de reposição
- não gera status de reposição
- mas precisa aparecer na lista de compra/orçamento

Exemplos:
- material para evento pontual
- peça específica para manutenção
- item comprado uma única vez
- serviço ou item não controlado em estoque

### O erro a evitar

Não recomendo cadastrar item avulso como item de estoque só para ele aparecer na lista de compras.

Isso polui o estoque com itens que não terão controle real, não terão histórico útil, não terão mínimo/ideal e depois vão gerar ruído em análises futuras.

Hoje `SolicitacaoMaterial` permite `item_id = nullable`, então ela já consegue representar uma solicitação sem item de estoque.  Porém, `ItemListaCompra` exige `item_id` obrigatório.  Além disso, a consolidação atual ignora solicitações aprovadas sem `item_id`. 

### Alternativa recomendada

Criar uma tabela auxiliar simples, sem mexer na base principal de estoque:

```python
class CompraAvulsa(Base):
    __tablename__ = "compras_avulsas"

    id = Column(Integer, primary_key=True)
    solicitacao_id = Column(Integer, ForeignKey("solicitacoes_material.id"), nullable=True)
    periodo_referencia = Column(Date, nullable=False)
    nome_item = Column(String(200), nullable=False)
    unidade = Column(String(20), default="un")
    quantidade = Column(Integer, nullable=False)
    setor_id = Column(Integer, ForeignKey("setores.id"), nullable=True)
    solicitante = Column(String(100), nullable=False)
    observacao = Column(Text, nullable=True)
    urgente = Column(Boolean, default=False)
    incluir_na_lista_final = Column(Boolean, default=True)
    criado_em = Column(DateTime, default=datetime.datetime.utcnow)
```

Isso não altera a lógica do estoque principal, não obriga `item_id`, não polui cadastro de itens e permite que Orçamentos consuma essas compras avulsas de forma limpa.

Ações:
- Aprovar como compra avulsa
- Rejeitar solicitação
- Voltar e vincular a item existente
- Voltar e cadastrar como item de estoque

Regra:
- compra avulsa aprovada não passa por mínimo/ideal
não vira validada
- não entra no motor de reposição
- entra direto na lista de consolidação com clareza no `status` e `motivo do sistema`

Status sugerido na solicitação original:

```text
compra_avulsa_aprovada
```

Assim a solicitação deixa de aparecer como pendência.

---

# Modal 2 — Sem Parâmetros

Esse modal deve ser mais simples.

Hoje o sistema já possui uma lógica correta para mínimo/ideal manual em `calculos_service.aplicar_minimo_ideal_manual()`: ela grava mínimo e ideal manuais, atualiza mínimo/ideal vigentes e marca a origem como `Manual`. 

A tela de Estoque já mostra mínimo/ideal vigente, automático e manual, além de confiabilidade da última revisão.  Esse mesmo bloco pode ser reaproveitado de forma reduzida no modal.

## Validação

```text
mínimo >= 0
ideal >= 0
se ideal > 0, mínimo também deve ser > 0
ideal >= mínimo
```

Essas validações já existem na tela de Estoque ao salvar valores manuais. 

Melhoria adicional: após definir parâmetros para um item, reclassificar todas as solicitações `sem_parametros` daquele mesmo item no período, não apenas a solicitação clicada.

---
