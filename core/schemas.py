""" Schemas Pydantic para validar entradas do domínio.

Os modelos deste arquivo validam dados antes de chegarem aos serviços. Eles não
persistem informações nem acessam Streamlit.
"""

from datetime import date
from typing import Optional
from pydantic import BaseModel, field_validator


class ItemUpdate(BaseModel):
    """Dados permitidos para atualizar limites e observações de um item."""

    estoque_minimo: int
    estoque_ideal: int
    unidade: str = "un"
    observacoes: Optional[str] = None

    @field_validator("estoque_minimo", "estoque_ideal")
    @classmethod
    def nao_negativo(cls, v: int) -> int:
        """Garante que limites de estoque não sejam negativos."""
        if v < 0:
            raise ValueError("Valor não pode ser negativo")
        return v


class MovimentacaoCreate(BaseModel):
    """Dados necessários para registrar uma movimentação de estoque."""

    item_id: int
    tipo: str  # "entrada", "saida", "ajuste"
    quantidade: int
    motivo: Optional[str] = None
    operador: Optional[str] = None

    @field_validator("tipo")
    @classmethod
    def tipo_valido(cls, v: str) -> str:
        """Valida se o tipo informado pertence aos tipos aceitos."""
        validos = {"entrada", "saida", "ajuste", "inventario"}
        if v not in validos:
            raise ValueError(f"Tipo inválido. Use: {validos}")
        return v

    @field_validator("quantidade")
    @classmethod
    def quantidade_positiva(cls, v: int) -> int:
        """Garante que movimentações tenham quantidade positiva."""
        if v <= 0:
            raise ValueError("Quantidade deve ser maior que zero")
        return v


class PrecoCreate(BaseModel):
    """Dados necessários para cadastrar uma cotação de fornecedor."""

    item_id: int
    fornecedor_id: int
    preco_unitario: float
    data_cotacao: date
    validade_dias: int = 30

    @field_validator("preco_unitario")
    @classmethod
    def preco_positivo(cls, v: float) -> float:
        """Garante que a cotação tenha preço unitário maior que zero."""
        if v <= 0:
            raise ValueError("Preço deve ser maior que zero")
        return v
