import datetime

from sqlalchemy import (
    Boolean, Column, Date, DateTime, Float,
    ForeignKey, Integer, Text, String, UniqueConstraint,
)
from sqlalchemy.orm import relationship

from core.database import Base


class Categoria(Base):
    __tablename__ = "categorias"

    id = Column(Integer, primary_key=True)
    nome = Column(String(100), nullable=False, unique=True)
    descricao = Column(Text)
    criado_em = Column(DateTime, default=datetime.datetime.utcnow)

    itens = relationship("Item", back_populates="categoria")


class Item(Base):
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

    categoria = relationship("Categoria", back_populates="itens")
    precos = relationship("PrecoFornecedor", back_populates="item", cascade="all, delete-orphan")
    movimentacoes = relationship("Movimentacao", back_populates="item", cascade="all, delete-orphan")
    snapshots = relationship("SnapshotAnalise", back_populates="item", cascade="all, delete-orphan")


class Fornecedor(Base):
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


class Movimentacao(Base):
    __tablename__ = "movimentacoes"

    id = Column(Integer, primary_key=True)
    item_id = Column(Integer, ForeignKey("itens.id"), nullable=False)
    tipo = Column(String(20), nullable=False)  # "entrada", "saida", "ajuste", "inventario"
    quantidade = Column(Integer, nullable=False)
    quantidade_anterior = Column(Integer, nullable=False)
    quantidade_nova = Column(Integer, nullable=False)
    motivo = Column(Text)
    operador = Column(String(100))
    criado_em = Column(DateTime, default=datetime.datetime.utcnow)

    item = relationship("Item", back_populates="movimentacoes")


class SnapshotAnalise(Base):
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


class Importacao(Base):
    __tablename__ = "importacoes"

    id = Column(Integer, primary_key=True)
    arquivo_origem = Column(String(300), nullable=False)
    tipo = Column(String(50), nullable=False)  # "estoque", "fornecedores"
    total_linhas = Column(Integer)
    linhas_ok = Column(Integer)
    linhas_erro = Column(Integer)
    erros_json = Column(Text)
    criado_em = Column(DateTime, default=datetime.datetime.utcnow)
