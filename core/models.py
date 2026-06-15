""" Modelos ORM que representam o domínio de estoque e compras.

Cada classe corresponde a uma tabela do SQLite e concentra os relacionamentos
usados pelos serviços para navegar entre itens, fornecedores, cotações,
movimentações, análises e logs de importação.
"""

import datetime

from sqlalchemy import (
    Boolean, Column, Date, DateTime, Float,
    ForeignKey, Integer, Table, Text, String, UniqueConstraint,
)
from sqlalchemy.orm import relationship

from core import tempo
from core.database import Base

# Tabela de junção para associação simples item ↔ fornecedor (sem preço/data).
item_fornecedores = Table(
    "item_fornecedores",
    Base.metadata,
    Column("item_id", Integer, ForeignKey("itens.id", ondelete="CASCADE"), primary_key=True),
    Column("fornecedor_id", Integer, ForeignKey("fornecedores.id", ondelete="CASCADE"), primary_key=True),
)


class Categoria(Base):
    """Agrupa itens de estoque por família operacional."""

    __tablename__ = "categorias"

    id = Column(Integer, primary_key=True)
    nome = Column(String(100), nullable=False, unique=True)
    descricao = Column(Text)
    criado_em = Column(DateTime, default=tempo.agora)

    itens = relationship("Item", back_populates="categoria")


class Item(Base):
    """Produto ou material controlado no estoque."""

    __tablename__ = "itens"

    id = Column(Integer, primary_key=True)
    categoria_id = Column(Integer, ForeignKey("categorias.id"), nullable=False)
    nome = Column(String(200), nullable=False)
    nome_normalizado = Column(String(200), nullable=False)
    unidade = Column(String(20), default="un")
    estoque_atual = Column(Integer, nullable=False, default=0)
    estoque_minimo = Column(Integer, nullable=False, default=0)
    estoque_ideal = Column(Integer, nullable=False, default=0)
    observacoes = Column(Text)
    ativo = Column(Boolean, default=True)
    criado_em = Column(DateTime, default=tempo.agora)
    atualizado_em = Column(DateTime, default=tempo.agora, onupdate=tempo.agora)

    # --- Camada automática de mínimo/ideal ---
    # Valores calculados pelo motor de revisão mensal (sempre atualizados)
    estoque_minimo_sugerido = Column(Integer, nullable=True)
    estoque_ideal_sugerido = Column(Integer, nullable=True)
    # Valores definidos manualmente pelo usuário (override opcional)
    estoque_minimo_manual = Column(Integer, nullable=True)
    estoque_ideal_manual = Column(Integer, nullable=True)
    data_definicao_minimo_manual = Column(DateTime, nullable=True)
    data_definicao_ideal_manual = Column(DateTime, nullable=True)
    # Valores vigentes: manual se definido, senão sugerido (usados em toda operação)
    estoque_minimo_vigente = Column(Integer, nullable=False, default=0)
    estoque_ideal_vigente = Column(Integer, nullable=False, default=0)
    # Origem dos valores vigentes: "Manual" ou "Automático"
    origem_minimo = Column(String(20), nullable=True)
    origem_ideal = Column(String(20), nullable=True)

    categoria = relationship("Categoria", back_populates="itens")
    precos = relationship("PrecoFornecedor", back_populates="item", cascade="all, delete-orphan")
    movimentacoes = relationship("Movimentacao", back_populates="item", cascade="all, delete-orphan")
    snapshots = relationship("SnapshotAnalise", back_populates="item", cascade="all, delete-orphan")
    revisoes_mensais = relationship("RevisaoMensal", back_populates="item", cascade="all, delete-orphan")
    fornecedores_associados = relationship(
        "Fornecedor", secondary=item_fornecedores, order_by="Fornecedor.nome"
    )
    solicitacoes = relationship("SolicitacaoMaterial", back_populates="item", cascade="all, delete-orphan")
    itens_lista_compra = relationship("ItemListaCompra", back_populates="item", cascade="all, delete-orphan")


class Fornecedor(Base):
    """Fornecedor usado em cotações e sugestões de compra."""

    __tablename__ = "fornecedores"

    id = Column(Integer, primary_key=True)
    nome = Column(String(200), nullable=False, unique=True)
    contato_nome = Column(String(100))
    telefone = Column(String(50))
    email = Column(String(100))
    website = Column(String(500))
    preferencial = Column(Boolean, default=False)
    ativo = Column(Boolean, default=True)
    criado_em = Column(DateTime, default=tempo.agora)

    precos = relationship("PrecoFornecedor", back_populates="fornecedor")


class PrecoFornecedor(Base):
    """Cotação de preço de um item em um fornecedor específico."""

    __tablename__ = "precos_fornecedor"
    __table_args__ = (
        UniqueConstraint("item_id", "fornecedor_id", "data_cotacao", name="uq_item_forn_data"),
    )

    id = Column(Integer, primary_key=True)
    item_id = Column(Integer, ForeignKey("itens.id"), nullable=False)
    fornecedor_id = Column(Integer, ForeignKey("fornecedores.id"), nullable=False)
    preco_unitario = Column(Float, nullable=False)
    data_cotacao = Column(Date, nullable=False)
    validade_dias = Column(Integer, default=30)
    ativo = Column(Boolean, default=True)
    criado_em = Column(DateTime, default=tempo.agora)

    item = relationship("Item", back_populates="precos")
    fornecedor = relationship("Fornecedor", back_populates="precos")


class Setor(Base):
    """Setor ou área que realiza retiradas de estoque."""

    __tablename__ = "setores"

    id = Column(Integer, primary_key=True)
    nome = Column(String(100), nullable=False, unique=True)
    descricao = Column(Text)
    whatsapp = Column(String(50), nullable=True)
    ativo = Column(Boolean, default=True)
    criado_em = Column(DateTime, default=tempo.agora)

    movimentacoes = relationship("Movimentacao", back_populates="setor")
    pedidos = relationship("SolicitacaoPedido", back_populates="setor")


class Movimentacao(Base):
    """Registro histórico de entrada ou saída que altera o saldo do item."""

    __tablename__ = "movimentacoes"

    id = Column(Integer, primary_key=True)
    item_id = Column(Integer, ForeignKey("itens.id"), nullable=False)
    tipo = Column(String(20), nullable=False)  # "entrada", "saida"
    quantidade = Column(Integer, nullable=False)
    quantidade_anterior = Column(Integer, nullable=False)
    quantidade_nova = Column(Integer, nullable=False)
    motivo = Column(Text)
    operador = Column(String(100))  # legado — mantido para compatibilidade com registros anteriores
    retirado_por = Column(String(200))
    setor_id = Column(Integer, ForeignKey("setores.id"), nullable=True)
    criado_em = Column(DateTime, default=tempo.agora)

    item = relationship("Item", back_populates="movimentacoes")
    setor = relationship("Setor", back_populates="movimentacoes")


class SnapshotAnalise(Base):
    """Resultado persistido da última análise de reposição por item."""

    __tablename__ = "snapshots_analise"

    id = Column(Integer, primary_key=True)
    item_id = Column(Integer, ForeignKey("itens.id"), nullable=False)
    status = Column(String(30), nullable=False)
    quantidade_recomendar = Column(Integer, nullable=False, default=0)
    valor_estimado = Column(Float)
    fornecedor_sugerido_id = Column(Integer, ForeignKey("fornecedores.id"))
    criado_em = Column(DateTime, default=tempo.agora)

    item = relationship("Item", back_populates="snapshots")
    fornecedor_sugerido = relationship("Fornecedor")


class RevisaoMensal(Base):
    """Resultado de uma revisão mensal do cálculo automático de mínimo/ideal de um item."""

    __tablename__ = "revisoes_mensais"

    id = Column(Integer, primary_key=True)
    item_id = Column(Integer, ForeignKey("itens.id"), nullable=False)
    criado_em = Column(DateTime, default=tempo.agora)
    periodo_descricao = Column(String(50))          # ex: "Junho/2026"
    data_inicio_analise = Column(DateTime)
    data_fim_analise = Column(DateTime)
    consumo_mediana_diario = Column(Float)
    consumo_p75_diario = Column(Float)
    intervalo_mediano_dias = Column(Integer)
    intervalo_p90_dias = Column(Integer)
    minimo_sugerido = Column(Integer)
    ideal_sugerido = Column(Integer)
    # ok / historico_insuficiente / historico_recente / sem_consumo_recente / sem_entradas_recentes / irregular
    status_confiabilidade = Column(String(50))

    item = relationship("Item", back_populates="revisoes_mensais")


class CicloSolicitacaoMaterial(Base):
    """Registro de um ciclo mensal de coleta de solicitações de materiais."""

    __tablename__ = "ciclos_solicitacao_material"

    id = Column(Integer, primary_key=True)
    periodo_referencia = Column(Date, nullable=False)
    abertura_em = Column(DateTime, nullable=False)
    prazo_resposta_em = Column(DateTime, nullable=True)
    encerrado_em = Column(DateTime, nullable=True)
    status = Column(String(20), nullable=False, default="aberto")  # "aberto" | "encerrado"
    criado_em = Column(DateTime, default=tempo.agora)

    participantes = relationship("CicloSolicitacaoSetor", back_populates="ciclo")
    pedidos = relationship("SolicitacaoPedido", back_populates="ciclo")


class CicloSolicitacaoSetor(Base):
    """Rastreia a participação de cada setor dentro de um ciclo de solicitações."""

    __tablename__ = "ciclo_solicitacao_setores"

    id = Column(Integer, primary_key=True)
    ciclo_id = Column(Integer, ForeignKey("ciclos_solicitacao_material.id"), nullable=False)
    setor_id = Column(Integer, ForeignKey("setores.id"), nullable=False)
    status = Column(String(30), nullable=False, default="pendente")  # pendente | respondido | sem_solicitacao
    respondido_em = Column(DateTime, nullable=True)
    # Rastreamento de entrega da notificação inicial (abertura do ciclo)
    envio_notificado_em = Column(DateTime, nullable=True)   # preenchido quando o envio foi bem-sucedido
    falha_envio         = Column(Boolean, default=False)    # True se o último envio falhou
    motivo_falha        = Column(String(200), nullable=True) # "sem_whatsapp" | "api_error:400" | etc.
    # Rastreamento dos demais eventos de notificação (para evitar reenvios duplicados)
    notificacao_lembrete_d2_em    = Column(DateTime, nullable=True)
    notificacao_prazo_proximo_em  = Column(DateTime, nullable=True)
    notificacao_encerramento_em   = Column(DateTime, nullable=True)
    notificacao_feedback_em       = Column(DateTime, nullable=True)

    __table_args__ = (UniqueConstraint("ciclo_id", "setor_id", name="uq_ciclo_setor"),)

    ciclo = relationship("CicloSolicitacaoMaterial", back_populates="participantes")
    setor = relationship("Setor")


class SolicitacaoPedido(Base):
    """Cabeçalho atômico de um formulário de solicitação — agrupa todos os itens de uma submissão."""

    __tablename__ = "solicitacoes_pedido"

    id = Column(Integer, primary_key=True)
    setor_id = Column(Integer, ForeignKey("setores.id"), nullable=True)
    solicitante = Column(String(100), nullable=False)
    periodo_referencia = Column(Date, nullable=False)
    ciclo_id = Column(Integer, ForeignKey("ciclos_solicitacao_material.id"), nullable=True)
    status = Column(String(30), nullable=False, default="enviado")
    criado_em = Column(DateTime, default=tempo.agora)

    setor = relationship("Setor", back_populates="pedidos")
    itens = relationship("SolicitacaoMaterial", back_populates="pedido")
    ciclo = relationship("CicloSolicitacaoMaterial", back_populates="pedidos")


class SolicitacaoMaterial(Base):
    """Pedido de compra registrado por um setor para um período de referência."""

    __tablename__ = "solicitacoes_material"

    id = Column(Integer, primary_key=True)
    item_id = Column(Integer, ForeignKey("itens.id"), nullable=True)
    nome_item_livre = Column(String(200), nullable=True)
    setor_id = Column(Integer, ForeignKey("setores.id"), nullable=True)
    solicitante = Column(String(100), nullable=False)
    quantidade_solicitada = Column(Integer, nullable=False)
    observacao = Column(Text, nullable=True)
    urgente = Column(Boolean, nullable=False, default=False)
    periodo_referencia = Column(Date, nullable=False)
    status = Column(String(30), nullable=False, default="pendente")
    pedido_id = Column(Integer, ForeignKey("solicitacoes_pedido.id"), nullable=True)
    criado_em = Column(DateTime, default=tempo.agora)

    item = relationship("Item", back_populates="solicitacoes")
    setor = relationship("Setor")
    compras_avulsas = relationship("CompraAvulsa", back_populates="solicitacao", cascade="all, delete-orphan")
    pedido = relationship("SolicitacaoPedido", back_populates="itens")


class CompraAvulsa(Base):
    """Item de compra pontual que não entra no cadastro principal de estoque."""

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
    criado_em = Column(DateTime, default=tempo.agora)

    solicitacao = relationship("SolicitacaoMaterial", back_populates="compras_avulsas")
    setor = relationship("Setor")


class ItemListaCompra(Base):
    """Resultado consolidado de análise de compra por item e período.

    Carrega os campos editáveis de governança (quantidade_final_definida, observacao)
    e a flag de aprovação para envio ao Orçamentos. `motivo_sugestao` é gerado
    automaticamente pelo engine para auditoria; `observacao` é preenchida pelo responsável.
    """

    __tablename__ = "itens_lista_compra"
    __table_args__ = (
        UniqueConstraint("item_id", "periodo_referencia", name="uq_item_lista_periodo"),
    )

    id = Column(Integer, primary_key=True)
    item_id = Column(Integer, ForeignKey("itens.id"), nullable=False)
    periodo_referencia = Column(Date, nullable=False)
    status = Column(String(30), nullable=False)
    estoque_atual_snap = Column(Integer, nullable=False, default=0)
    estoque_minimo_snap = Column(Integer, nullable=False, default=0)
    estoque_ideal_snap = Column(Integer, nullable=False, default=0)
    total_solicitado = Column(Integer, nullable=False, default=0)
    quantidade_sugerida = Column(Integer, nullable=False, default=0)
    quantidade_final_definida = Column(Integer, nullable=True)
    observacao = Column(Text, nullable=True)
    motivo_sugestao = Column(Text, nullable=True)
    incluir_na_lista_final = Column(Boolean, default=False)
    valor_estimado = Column(Float, nullable=True)
    fornecedor_sugerido_id = Column(Integer, ForeignKey("fornecedores.id"), nullable=True)
    criado_em = Column(DateTime, default=tempo.agora)
    atualizado_em = Column(DateTime, default=tempo.agora, onupdate=tempo.agora)

    item = relationship("Item", back_populates="itens_lista_compra")
    fornecedor_sugerido = relationship("Fornecedor")


class Importacao(Base):
    """Log de uma execução de importação de planilhas externas."""

    __tablename__ = "importacoes"

    id = Column(Integer, primary_key=True)
    arquivo_origem = Column(String(300), nullable=False)
    tipo = Column(String(50), nullable=False)  # "estoque", "fornecedores"
    total_linhas = Column(Integer)
    linhas_ok = Column(Integer)
    linhas_erro = Column(Integer)
    erros_json = Column(Text)
    criado_em = Column(DateTime, default=tempo.agora)


# ---------------------------------------------------------------------------
# Camada de Orçamentos
# ---------------------------------------------------------------------------

class Orcamento(Base):
    """Orçamento de compra gerado a partir da Lista Final de Compras.

    Cada orçamento é um snapshot versionado do processo de cotação para um
    período. Versões anteriores ficam bloqueadas para auditoria quando o
    diretor solicita revisão.
    """

    __tablename__ = "orcamentos"
    __table_args__ = (
        UniqueConstraint("periodo_referencia", "versao", name="uq_orcamento_periodo_versao"),
    )

    id = Column(Integer, primary_key=True)
    periodo_referencia = Column(Date, nullable=False)
    numero = Column(String(20), nullable=False)          # ORC-YYYY-MM-NNN
    versao = Column(Integer, nullable=False, default=1)
    # Estados: RASCUNHO | EM_COTACAO | PRONTO_PARA_APROVACAO | ENVIADO_APROVACAO
    #          APROVADO | APROVADO_PARCIAL | DEVOLVIDO_REVISAO | REPROVADO | CANCELADO
    status = Column(String(30), nullable=False, default="RASCUNHO")
    responsavel = Column(String(100), nullable=False)
    observacao_geral = Column(Text, nullable=True)
    enviado_em = Column(DateTime, nullable=True)
    decidido_em = Column(DateTime, nullable=True)
    observacao_diretor = Column(Text, nullable=True)
    criado_em = Column(DateTime, default=tempo.agora)
    atualizado_em = Column(DateTime, default=tempo.agora, onupdate=tempo.agora)

    itens = relationship(
        "ItemOrcamento",
        back_populates="orcamento",
        cascade="all, delete-orphan",
    )


class ItemOrcamento(Base):
    """Linha de um orçamento: snapshot de um item da Lista Final.

    Pode referenciar um ItemListaCompra (item de estoque) ou uma CompraAvulsa
    (item fora do catálogo). Os campos nome_item/categoria_nome são snapshots
    gravados no momento da criação do orçamento para garantir imutabilidade.
    """

    __tablename__ = "itens_orcamento"

    id = Column(Integer, primary_key=True)
    orcamento_id = Column(Integer, ForeignKey("orcamentos.id"), nullable=False)
    item_lista_id = Column(Integer, ForeignKey("itens_lista_compra.id"), nullable=True)
    compra_avulsa_id = Column(Integer, ForeignKey("compras_avulsas.id"), nullable=True)
    nome_item = Column(String(200), nullable=False)
    categoria_nome = Column(String(100), nullable=False, default="")
    tipo = Column(String(10), nullable=False)             # ESTOQUE | AVULSA
    quantidade_lista = Column(Integer, nullable=False)    # snapshot da Lista Final
    quantidade_orcada = Column(Integer, nullable=False)   # pode diferir com motivo
    motivo_alteracao_qtd = Column(Text, nullable=True)
    # Não é FK formal para evitar dependência circular com CotacaoOrcamento.
    cotacao_escolhida_id = Column(Integer, nullable=True)
    # Estados: SEM_COTACAO | COM_COTACAO | APROVADO_DIRETOR | REPROVADO_DIRETOR
    status_item = Column(String(30), nullable=False, default="SEM_COTACAO")
    observacao_diretor = Column(Text, nullable=True)

    orcamento = relationship("Orcamento", back_populates="itens")
    item_lista = relationship("ItemListaCompra")
    compra_avulsa = relationship("CompraAvulsa")
    cotacoes = relationship(
        "CotacaoOrcamento",
        back_populates="item_orcamento",
        cascade="all, delete-orphan",
    )


class CotacaoOrcamento(Base):
    """Cotação registrada para um item de orçamento.

    Uma cotação pode vir de pesquisa manual (link, marketplace) ou de um
    fornecedor cadastrado (fornecedor_id, preparado para Fluxo B de envio
    automático). O total_calculado é persistido para evitar recalcular na
    geração de documentos.
    """

    __tablename__ = "cotacoes_orcamento"

    id = Column(Integer, primary_key=True)
    item_orcamento_id = Column(Integer, ForeignKey("itens_orcamento.id"), nullable=False)
    origem = Column(String(200), nullable=False)          # nome do fornecedor ou marketplace
    fornecedor_id = Column(Integer, ForeignKey("fornecedores.id"), nullable=True)  # prep Fluxo B
    link = Column(String(500), nullable=True)
    preco_unitario = Column(Float, nullable=False)
    frete = Column(Float, nullable=False, default=0.0)
    desconto = Column(Float, nullable=False, default=0.0)
    outros_custos = Column(Float, nullable=False, default=0.0)
    # qty * preco_unitario - desconto + outros_custos + frete
    total_calculado = Column(Float, nullable=False)
    data_cotacao = Column(Date, nullable=False)
    observacao = Column(Text, nullable=True)
    criado_em = Column(DateTime, default=tempo.agora)

    item_orcamento = relationship("ItemOrcamento", back_populates="cotacoes")
    fornecedor = relationship("Fornecedor")


class SolicitacaoCotacaoFornecedor(Base):
    """Rastreia solicitações de cotação enviadas por WhatsApp a fornecedores.

    Criada quando o responsável de compras envia uma mensagem WhatsApp a um
    fornecedor pedindo preços de um conjunto de itens do orçamento.
    """

    __tablename__ = "solicitacoes_cotacao_fornecedor"

    id = Column(Integer, primary_key=True)
    orcamento_id = Column(Integer, ForeignKey("orcamentos.id"), nullable=False)
    fornecedor_id = Column(Integer, ForeignKey("fornecedores.id"), nullable=False)
    itens_json = Column(Text, nullable=False)   # JSON: [{"nome_item": str, "quantidade": int}]
    prazo_resposta = Column(Date, nullable=True)
    enviado_em = Column(DateTime, default=tempo.agora)
    wamid = Column(String(100), nullable=True)  # ID da mensagem WhatsApp (auditoria)
    status = Column(String(20), nullable=False, default="ENVIADO")  # ENVIADO | RESPONDIDO

    orcamento = relationship("Orcamento")
    fornecedor = relationship("Fornecedor")
