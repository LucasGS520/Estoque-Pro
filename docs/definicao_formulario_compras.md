# Definição e Entendimento - Fluxo ideal da Solicitação de Materiais e Compras

Não vale manter `Pedido_de_Compra.py` como está.

Hoje ela é uma **tela interna do próprio sistema**, aparece no menu lateral junto com Compras/Orçamentos e grava direto em `solicitacoes_material`. Isso contradiz o fluxo operacional ideal: a solicitação deve nascer **fora do sistema**, por terceiros, e só depois entrar na camada de Compras para triagem.

O melhor fluxo e o desenho mais coerente para essa camada é transformar a “Solicitação de Materiais”, que não deve ser uma página operacional principal do sistema, em uma **fonte externa de demanda** que alimenta Compras.

Regra crucial:
> O formulário externo não pode devolver apenas “nome do item”. Ele precisa devolver um identificador rastreável do item do estoque.

Se voltar só texto livre, a consolidação quebra: “Papel A4”, “Resma A4”, “Sulfite” e “Papel sulfite” podem virar quatro demandas diferentes.

---

# Fluxo ideal

```text
Responsável pelo estoque
        ↓
Gera formulário externo baseado no periodo/mes correspondete e no catálogo atual do estoque
        ↓
Envia para os devidos setores/solicitante
        ↓
Setor preenche:
  - itens existentes (quantidade e observação opcional)
  - itens novos (nome do novo item, quantidade e observação opcional)
        ↓
Sistema recebe/importa respostas
        ↓
Sistema valida, normaliza e separa pendências
        ↓
Compras consolida com estoque atual
        ↓
Lista final segue para Orçamentos
```

Isso substitui a ideia atual de uma tela interna `Pedido de Compra`. Hoje essa página é um formulário Streamlit interno que grava direto em `solicitacoes_material`, então ela não representa bem o fluxo externo que você descreveu.  

---

# Como o formulário deve ser gerado

A tela de Compras deveria ter uma ação como:

```text
Gerar formulário de solicitação
```

O responsável informa:

```text
Período: Junho/2026
Tipo: Solicitação mensal de materiais
```

O sistema gera um “pacote de solicitação” baseado no estoque:

```text
Formulário externo
+ catálogo de itens permitidos
+ identificador dos itens
+ período de referência
+ setor destino
+ instruções de preenchimento
```

## Estrutura do formulário

O formulário deve separar claramente duas situações:
1. Solicitar item (já cadastrado no estoque)
2. Opção para item novo (produtos não eistentes no estoque)

Essa separação é obrigatória. Misturar item cadastrado e item novo no mesmo campo vai criar sujeira na consolidação.

---

# Parte 1 — Item já cadastrado

O solicitante escolhe um item da lista gerada pelo sistema.

Exemplo de opção no formulário:

```text
ID |  Cabo PP 2x2,5mm  |  Categoria: Elétrica  |  Unidade: m
```

Na importação, o sistema usa esse código para vincular a solicitação ao `item_id`.

Campos:

```text
Setor: Manutenção
Solicitante: João Silva
Período: Junho/2026
Item: Cabo PP 2x2,5mm
Quantidade: 30
Obsrvação: Reposição para manutenção preventiva
```

---

# Parte 2 — Item novo / não encontrado

Quando o item não existe no estoque, o solicitante não deve forçar um item parecido. Ele deve preencher a área de item novo.

Campos:

```text
Setor: Manutenção
Solicitante: João Silva
Período: Junho/2026
Tipo de solicitação: Item novo
Nome do item solicitado: Cabo HDMI 10m
Quantidade: 2
Observação: Necessário para instalação de monitor, especificação técnica, marca, medida, modelo etc.
```

No retorno ao sistema, isso não entra direto na lista final. Entra como:

```text
status = pendente_cadastro
```

O documento atual já define corretamente que item não cadastrado deve ficar separado e não entrar automaticamente na lista consolidada. 

---

# Como o sistema deve receber o retorno

A página Compras deveria ganhar uma aba: `Solicitações Recebidas`

É nela onde deve receber as  respostas do formulário, analisar, classificar e passar para as próximas etapas.

Tipos minimos de classificação:

| Situação                              | Status                    |
| ------------------------------------- | ------------------------- |
| Item cadastrado e quantidade válida   | `validada`                |
| Item novo                             | `pendente_cadastro`       |
| Item cadastrado, mas sem mínimo/ideal | `pendente_parametrizacao` |

---

# Como a consolidação deve funcionar depois do retorno

Depois que as respostas entram no sistema:

```text
Solicitações válidas
        ↓
Agrupar por item
        ↓
Somar quantidades por item
        ↓
Comparar com estoque atual
        ↓
Aplicar mínimo/ideal
        ↓
Separar pendências
        ↓
Gerar quantidade sugerida
```

---

# Definição final

O fluxo deve ser este:

```text
Sistema gera a coleta
    ↓
Setor preenche externamente
    ↓
Sistema importa retorno
    ↓
Sistema separa e classifica, por exemplo:
    - item cadastrado
    - item novo
    ↓
Sistema consolida somente o que é válido
    ↓
Responsável revisa quantidade final
    ↓
Lista final de Compras
```

Esse desenho atende exatamente aos quatro objetivos:
- Formulário de fácil preenchimento
- Baseado no estoque
- Separação clara entre itens existentes e novos itens
- Retorno processável pelo sistema

A única cautela: não tente fazer o sistema depender de texto livre sobre a solicitação. O formulário pode ser externo, mas a identidade dos itens precisa vir do estoque por código/ID. Sem isso, a consolidação vai ficar frágil.
