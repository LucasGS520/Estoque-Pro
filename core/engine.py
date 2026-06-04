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
    # Status do motor consolidado (camada de Compras)
    ABAIXO_MINIMO = "abaixo_minimo"
    EXCESSO = "excesso"


@dataclass
class SolicitacaoRecord:
    """Pedido de compra de um setor, entrada para o motor consolidado."""

    setor: str
    solicitante: str
    quantidade: int


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
    solicitations: list[SolicitacaoRecord] = field(default_factory=list)


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
    total_solicitado: int = 0
    saldo_pos_atendimento: int = 0


@dataclass
class AnalysisSummary:
    """Resumo agregado dos resultados de análise."""

    total_itens: int = 0
    itens_comprar: int = 0
    itens_ok: int = 0
    itens_sem_minimo: int = 0
    itens_zerados: int = 0
    itens_abaixo_minimo: int = 0
    itens_excesso: int = 0
    itens_sem_fornecedor: int = 0
    itens_sem_preco: int = 0
    valor_total_estimado: float = 0.0
    por_categoria: dict = field(default_factory=dict)


_STATUS_ORDER = {
    ItemStatus.ZERADO: 0,
    ItemStatus.COMPRAR: 1,
    ItemStatus.ABAIXO_MINIMO: 2,
    ItemStatus.SEM_MINIMO: 3,
    ItemStatus.EXCESSO: 4,
    ItemStatus.OK: 5,
}


class StockAnalyzer:
    """Calcula recomendações de reposição a partir dos limites de estoque."""

    def calcular_status(self, item: ItemRecord) -> AnalysisResult:
        """Calcula status sem solicitações (análise pura de estoque).

        Mantido sem alteração para compatibilidade com run_analysis() e SnapshotAnalise.
        """
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

    def calcular_status_consolidado(self, item: ItemRecord) -> AnalysisResult:
        """Aplica as 6 regras de negócio cruzando estoque com solicitações do período."""
        sem_limites = item.estoque_minimo == 0 and item.estoque_ideal == 0
        qtd_total = sum(s.quantidade for s in item.solicitations)
        saldo = item.qtd_atual - qtd_total

        has_solicitations = len(item.solicitations) > 0

        # Excesso: sinalização prioritária (sem compra)
        if not sem_limites and item.estoque_ideal > 0 and item.qtd_atual > item.estoque_ideal * 1.5:
            status = ItemStatus.EXCESSO
            qtd_recomendar = 0

        elif sem_limites:
            status = ItemStatus.SEM_MINIMO
            qtd_recomendar = 0

        elif item.qtd_atual == 0:
            # Regra 5: zerado — até o mínimo sem pedido; max(min, pedido) com pedido
            status = ItemStatus.ZERADO
            qtd_recomendar = max(item.estoque_minimo, qtd_total) if qtd_total > 0 else item.estoque_minimo

        elif has_solicitations:
            # Regras baseadas em solicitações têm prioridade sobre o check automático de mínimo
            if saldo < 0:
                # Regra 3: pedido excede o estoque disponível
                status = ItemStatus.COMPRAR
                qtd_recomendar = max(item.estoque_ideal - item.qtd_atual, abs(saldo))
            elif saldo < item.estoque_minimo:
                # Regra 2: pedido pressiona abaixo do mínimo
                status = ItemStatus.COMPRAR
                qtd_recomendar = max(item.estoque_ideal - saldo, 0)
            else:
                # Regra 1: pedido absorvido pelo estoque atual
                status = ItemStatus.OK
                qtd_recomendar = 0

        elif item.qtd_atual <= item.estoque_minimo:
            # Regra 4: abaixo do mínimo sem solicitação — reposição automática
            status = ItemStatus.ABAIXO_MINIMO
            qtd_recomendar = max(item.estoque_ideal - item.qtd_atual, 0)

        else:
            # Estoque OK sem pressão de solicitações
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
            total_solicitado=qtd_total,
            saldo_pos_atendimento=saldo,
        )

    def run(self, items: list[ItemRecord]) -> list[AnalysisResult]:
        """Analisa itens sem solicitações e ordena por prioridade operacional."""
        results = [self.calcular_status(item) for item in items]
        results.sort(key=lambda r: (_STATUS_ORDER[r.status], r.categoria, r.nome))
        return results

    def run_consolidado(self, items: list[ItemRecord]) -> list[AnalysisResult]:
        """Analisa itens com solicitações do período e ordena por prioridade."""
        results = [self.calcular_status_consolidado(item) for item in items]
        results.sort(key=lambda r: (_STATUS_ORDER[r.status], r.categoria, r.nome))
        return results

    def summary(self, results: list[AnalysisResult]) -> AnalysisSummary:
        """Gera contadores e totais consolidados a partir dos resultados."""
        s = AnalysisSummary(total_itens=len(results))
        for r in results:
            if r.status == ItemStatus.COMPRAR:
                s.itens_comprar += 1
            elif r.status == ItemStatus.OK:
                s.itens_ok += 1
            elif r.status == ItemStatus.SEM_MINIMO:
                s.itens_sem_minimo += 1
            elif r.status == ItemStatus.ZERADO:
                s.itens_zerados += 1
            elif r.status == ItemStatus.ABAIXO_MINIMO:
                s.itens_abaixo_minimo += 1
            elif r.status == ItemStatus.EXCESSO:
                s.itens_excesso += 1

            if not r.tem_fornecedor:
                s.itens_sem_fornecedor += 1
            if not r.tem_preco:
                s.itens_sem_preco += 1
            if r.valor_estimado:
                s.valor_total_estimado += r.valor_estimado

            cat = r.categoria
            if cat not in s.por_categoria:
                s.por_categoria[cat] = {
                    "comprar": 0, "ok": 0, "sem_minimo": 0, "zerado": 0,
                    "abaixo_minimo": 0, "excesso": 0,
                }
            status_key = r.status.value if r.status != ItemStatus.SEM_MINIMO else "sem_minimo"
            if status_key in s.por_categoria[cat]:
                s.por_categoria[cat][status_key] += 1

        s.valor_total_estimado = round(s.valor_total_estimado, 2)
        return s
