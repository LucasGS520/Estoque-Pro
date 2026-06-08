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
    criado_em = Column(DateTime, default=datetime.datetime.utcnow)

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
    criado_em = Column(DateTime, default=datetime.datetime.utcnow)
    atualizado_em = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

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
    preferencial = Column(Boolean, default=False)
    ativo = Column(Boolean, default=True)
    criado_em = Column(DateTime, default=datetime.datetime.utcnow)

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
    criado_em = Column(DateTime, default=datetime.datetime.utcnow)

    item = relationship("Item", back_populates="precos")
    fornecedor = relationship("Fornecedor", back_populates="precos")


class Setor(Base):
    """Setor ou área que realiza retiradas de estoque."""

    __tablename__ = "setores"

    id = Column(Integer, primary_key=True)
    nome = Column(String(100), nullable=False, unique=True)
    descricao = Column(Text)
    ativo = Column(Boolean, default=True)
    criado_em = Column(DateTime, default=datetime.datetime.utcnow)

    movimentacoes = relationship("Movimentacao", back_populates="setor")


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
    criado_em = Column(DateTime, default=datetime.datetime.utcnow)

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
    criado_em = Column(DateTime, default=datetime.datetime.utcnow)

    item = relationship("Item", back_populates="snapshots")
    fornecedor_sugerido = relationship("Fornecedor")


class RevisaoMensal(Base):
    """Resultado de uma revisão mensal do cálculo automático de mínimo/ideal de um item."""

    __tablename__ = "revisoes_mensais"

    id = Column(Integer, primary_key=True)
    item_id = Column(Integer, ForeignKey("itens.id"), nullable=False)
    criado_em = Column(DateTime, default=datetime.datetime.utcnow)
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
    status = Column(String(20), nullable=False, default="pendente")
    criado_em = Column(DateTime, default=datetime.datetime.utcnow)

    item = relationship("Item", back_populates="solicitacoes")
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
    criado_em = Column(DateTime, default=datetime.datetime.utcnow)
    atualizado_em = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

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
    criado_em = Column(DateTime, default=datetime.datetime.utcnow)
