""" Serviços para consolidar orçamento preliminar de compras.

Transforma resultados de análise em itens orçamentários, separando itens com e
sem cotação válida e somando subtotais por fornecedor.
"""

from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy.orm import Session

from core.engine import AnalysisResult, ItemStatus
from services.fornecedor_service import get_best_price


@dataclass
class OrcamentoItem:
    """Linha consolidada de orçamento para um item recomendado para compra."""

    item_id: int
    nome: str
    categoria: str
    quantidade: int
    preco_unitario: Optional[float]
    total: Optional[float]
    fornecedor: Optional[str]
    validade_cotacao: Optional[str]
    tem_preco: bool


@dataclass
class OrcamentoConsolidado:
    """Resultado agregado do orçamento preliminar."""

    itens_com_preco: list[OrcamentoItem] = field(default_factory=list)
    itens_sem_preco: list[OrcamentoItem] = field(default_factory=list)
    total_estimado: float = 0.0
    por_fornecedor: dict = field(default_factory=dict)


def consolidar_orcamento(
    session: Session,
    results: list[AnalysisResult],
) -> OrcamentoConsolidado:
    """Consolida orçamento a partir dos resultados de análise de compras.

    Consulta a melhor cotação de cada item crítico, calcula totais e separa os
    itens sem preço para exibição específica na tela.
    """
    orcamento = OrcamentoConsolidado()

    compras = [r for r in results if r.status in (ItemStatus.COMPRAR, ItemStatus.ZERADO)]

    for r in compras:
        melhor = get_best_price(session, r.item_id)
        if melhor:
            total = round(melhor.preco_unitario * r.quantidade_recomendar, 2)
            item = OrcamentoItem(
                item_id=r.item_id,
                nome=r.nome,
                categoria=r.categoria,
                quantidade=r.quantidade_recomendar,
                preco_unitario=melhor.preco_unitario,
                total=total,
                fornecedor=melhor.fornecedor.nome,
                validade_cotacao=str(melhor.data_cotacao),
                tem_preco=True,
            )
            orcamento.itens_com_preco.append(item)
            orcamento.total_estimado += total

            forn_nome = melhor.fornecedor.nome
            if forn_nome not in orcamento.por_fornecedor:
                orcamento.por_fornecedor[forn_nome] = 0.0
            orcamento.por_fornecedor[forn_nome] += total
        else:
            item = OrcamentoItem(
                item_id=r.item_id,
                nome=r.nome,
                categoria=r.categoria,
                quantidade=r.quantidade_recomendar,
                preco_unitario=None,
                total=None,
                fornecedor=None,
                validade_cotacao=None,
                tem_preco=False,
            )
            orcamento.itens_sem_preco.append(item)

    orcamento.total_estimado = round(orcamento.total_estimado, 2)
    orcamento.por_fornecedor = {
        k: round(v, 2) for k, v in sorted(orcamento.por_fornecedor.items(), key=lambda x: -x[1])
    }
    return orcamento
