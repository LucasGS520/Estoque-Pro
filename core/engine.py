""" Motor puro de análise de estoque.

Recebe registros já carregados dos serviços, calcula status de reposição,
quantidades recomendadas e resumos agregados. Não acessa banco nem Streamlit.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ItemStatus(str, Enum):
    """Status possíveis para um item após a análise de reposição."""

    COMPRAR = "comprar"
    OK = "ok"
    SEM_MINIMO = "sem_minimo_definido"
    ZERADO = "zerado"


@dataclass
class ItemRecord:
    """Entrada normalizada usada pelo motor de análise."""

    item_id: int
    nome: str
    categoria: str
    qtd_atual: int
    estoque_minimo: int
    estoque_ideal: int
    preco_unitario: Optional[float] = None
    fornecedor_sugerido: Optional[str] = None
    fornecedor_sugerido_id: Optional[int] = None


@dataclass
class AnalysisResult:
    """Resultado calculado para um item analisado."""

    item_id: int
    nome: str
    categoria: str
    qtd_atual: int
    estoque_minimo: int
    estoque_ideal: int
    status: ItemStatus
    quantidade_recomendar: int
    preco_unitario: Optional[float]
    fornecedor_sugerido: Optional[str]
    fornecedor_sugerido_id: Optional[int]
    valor_estimado: Optional[float]
    tem_preco: bool
    tem_fornecedor: bool


@dataclass
class AnalysisSummary:
    """Resumo agregado dos resultados de análise."""

    total_itens: int = 0
    itens_comprar: int = 0
    itens_ok: int = 0
    itens_sem_minimo: int = 0
    itens_zerados: int = 0
    itens_sem_fornecedor: int = 0
    itens_sem_preco: int = 0
    valor_total_estimado: float = 0.0
    por_categoria: dict = field(default_factory=dict)


_STATUS_ORDER = {
    ItemStatus.ZERADO: 0,
    ItemStatus.COMPRAR: 1,
    ItemStatus.SEM_MINIMO: 2,
    ItemStatus.OK: 3,
}


class StockAnalyzer:
    """Calcula recomendações de reposição a partir dos limites de estoque."""

    def calcular_status(self, item: ItemRecord) -> AnalysisResult:
        """Calcula status, quantidade recomendada e valor estimado do item."""
        sem_limites = item.estoque_minimo == 0 and item.estoque_ideal == 0

        if item.qtd_atual == 0 and not sem_limites:
            status = ItemStatus.ZERADO
            qtd_recomendar = max(item.estoque_ideal - item.qtd_atual, 0)
        elif sem_limites:
            status = ItemStatus.SEM_MINIMO
            qtd_recomendar = 0
        elif item.qtd_atual <= item.estoque_minimo:
            status = ItemStatus.COMPRAR
            qtd_recomendar = max(item.estoque_ideal - item.qtd_atual, 0)
        else:
            status = ItemStatus.OK
            qtd_recomendar = 0

        valor_estimado = None
        if item.preco_unitario is not None and qtd_recomendar > 0:
            valor_estimado = round(item.preco_unitario * qtd_recomendar, 2)

        return AnalysisResult(
            item_id=item.item_id,
            nome=item.nome,
            categoria=item.categoria,
            qtd_atual=item.qtd_atual,
            estoque_minimo=item.estoque_minimo,
            estoque_ideal=item.estoque_ideal,
            status=status,
            quantidade_recomendar=qtd_recomendar,
            preco_unitario=item.preco_unitario,
            fornecedor_sugerido=item.fornecedor_sugerido,
            fornecedor_sugerido_id=item.fornecedor_sugerido_id,
            valor_estimado=valor_estimado,
            tem_preco=item.preco_unitario is not None,
            tem_fornecedor=item.fornecedor_sugerido is not None,
        )

    def run(self, items: list[ItemRecord]) -> list[AnalysisResult]:
        """Analisa itens e ordena os resultados por prioridade operacional."""
        results = [self.calcular_status(item) for item in items]
        results.sort(key=lambda r: (_STATUS_ORDER[r.status], r.categoria, r.nome))
        return results

    def summary(self, results: list[AnalysisResult]) -> AnalysisSummary:
        """Gera contadores e totais consolidados a partir dos resultados."""
        summary = AnalysisSummary(total_itens=len(results))
        for r in results:
            if r.status == ItemStatus.COMPRAR:
                summary.itens_comprar += 1
            elif r.status == ItemStatus.OK:
                summary.itens_ok += 1
            elif r.status == ItemStatus.SEM_MINIMO:
                summary.itens_sem_minimo += 1
            elif r.status == ItemStatus.ZERADO:
                summary.itens_zerados += 1

            if not r.tem_fornecedor:
                summary.itens_sem_fornecedor += 1
            if not r.tem_preco:
                summary.itens_sem_preco += 1
            if r.valor_estimado:
                summary.valor_total_estimado += r.valor_estimado

            cat = r.categoria
            if cat not in summary.por_categoria:
                summary.por_categoria[cat] = {"comprar": 0, "ok": 0, "sem_minimo": 0, "zerado": 0}
            summary.por_categoria[cat][r.status.value if r.status != ItemStatus.SEM_MINIMO else "sem_minimo"] += 1  # noqa: E501

        summary.valor_total_estimado = round(summary.valor_total_estimado, 2)
        return summary
