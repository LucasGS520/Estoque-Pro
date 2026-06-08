""" Motor puro de análise de estoque.

Recebe registros já carregados dos serviços, calcula status de reposição,
quantidades recomendadas e resumos agregados. Não acessa banco nem Streamlit.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ItemStatus(str, Enum):
    """Status possíveis para um item após a análise de reposição."""

    ZERADO = "zerado"
    ABAIXO_MINIMO = "abaixo_minimo"
    ABAIXO_IDEAL = "abaixo_ideal"
    OK = "ok"
    SEM_PARAMETRO = "sem_parametro"
    # Legado — mantidos para compatibilidade com run_analysis() / SnapshotAnalise / Orçamentos
    COMPRAR = "comprar"
    SEM_MINIMO = "sem_minimo_definido"


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
    margem_operacional: Optional[float] = None
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
    alvo_reposicao: Optional[int] = None
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
    itens_abaixo_ideal: int = 0
    itens_sem_fornecedor: int = 0
    itens_sem_preco: int = 0
    valor_total_estimado: float = 0.0
    por_categoria: dict = field(default_factory=dict)


_STATUS_ORDER = {
    ItemStatus.ZERADO:        0,
    ItemStatus.ABAIXO_MINIMO: 1,
    ItemStatus.ABAIXO_IDEAL:  2,
    ItemStatus.SEM_PARAMETRO: 3,
    ItemStatus.OK:            4,
    # Legado
    ItemStatus.COMPRAR:       1,
    ItemStatus.SEM_MINIMO:    3,
}


def _calcular_alvo(minimo: int, ideal: int, margem: Optional[float]) -> int:
    """Calcula o alvo de reposição com base na margem operacional.

    Se margem disponível: alvo = min(ideal, minimo + margem_arredondada).
    Sem margem (item sem histórico): alvo = ideal (comportamento anterior preservado).
    """
    if margem is None:
        return ideal
    return min(ideal, minimo + max(1, round(margem)))


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

    def calcular_status_puro(self, item: ItemRecord) -> AnalysisResult:
        """Calcula status de estoque sem solicitações. Usado pelo Painel de Reposição.

        Ordem de avaliação:
        1. SEM_PARAMETRO — mínimo ou ideal não definido
        2. ZERADO        — estoque zerado (prioridade máxima)
        3. ABAIXO_MINIMO — atual <= mínimo (zona crítica)
        4. ABAIXO_IDEAL  — mínimo < atual <= ideal (atenção, sem compra obrigatória)
        5. OK            — atual > ideal (não comprar)
        """
        sem_parametro = item.estoque_minimo == 0 or item.estoque_ideal == 0

        if sem_parametro:
            return self._build_result(item, ItemStatus.SEM_PARAMETRO, 0, None)

        alvo = _calcular_alvo(item.estoque_minimo, item.estoque_ideal, item.margem_operacional)

        if item.qtd_atual == 0:
            qtd = max(0, alvo - item.qtd_atual)
            return self._build_result(item, ItemStatus.ZERADO, qtd, alvo)

        if item.qtd_atual <= item.estoque_minimo:
            qtd = max(0, alvo - item.qtd_atual)
            return self._build_result(item, ItemStatus.ABAIXO_MINIMO, qtd, alvo)

        if item.qtd_atual <= item.estoque_ideal:
            return self._build_result(item, ItemStatus.ABAIXO_IDEAL, 0, alvo)

        return self._build_result(item, ItemStatus.OK, 0, alvo)

    def calcular_status_consolidado(self, item: ItemRecord) -> AnalysisResult:
        """Cruza estoque com solicitações do período.

        Ordem de avaliação idêntica ao modo puro, mas a classificação e a
        quantidade sugerida são calculadas sobre o saldo projetado após atender
        todas as solicitações aprovadas do período.
        """
        sem_parametro = item.estoque_minimo == 0 or item.estoque_ideal == 0
        qtd_total = sum(s.quantidade for s in item.solicitations)
        saldo = item.qtd_atual - qtd_total
        tem_solicits = qtd_total > 0

        if sem_parametro:
            return self._build_result(item, ItemStatus.SEM_PARAMETRO, 0, None,
                                      total_solicitado=qtd_total, saldo=saldo)

        alvo = _calcular_alvo(item.estoque_minimo, item.estoque_ideal, item.margem_operacional)

        if item.qtd_atual == 0:
            qtd = max(0, alvo - saldo)
            return self._build_result(item, ItemStatus.ZERADO, qtd, alvo,
                                      total_solicitado=qtd_total, saldo=saldo)

        if saldo <= item.estoque_minimo:
            qtd = max(0, alvo - saldo)
            return self._build_result(item, ItemStatus.ABAIXO_MINIMO, qtd, alvo,
                                      total_solicitado=qtd_total, saldo=saldo)

        if saldo <= item.estoque_ideal:
            # ABAIXO_IDEAL: só gera quantidade se houver solicitações aprovadas
            qtd = max(0, alvo - saldo) if tem_solicits else 0
            return self._build_result(item, ItemStatus.ABAIXO_IDEAL, qtd, alvo,
                                      total_solicitado=qtd_total, saldo=saldo)

        return self._build_result(item, ItemStatus.OK, 0, alvo,
                                  total_solicitado=qtd_total, saldo=saldo)

    def _build_result(
        self,
        item: ItemRecord,
        status: ItemStatus,
        qtd_recomendar: int,
        alvo: Optional[int],
        total_solicitado: int = 0,
        saldo: Optional[int] = None,
    ) -> AnalysisResult:
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
            alvo_reposicao=alvo,
            total_solicitado=total_solicitado,
            saldo_pos_atendimento=saldo if saldo is not None else item.qtd_atual,
        )

    def run(self, items: list[ItemRecord]) -> list[AnalysisResult]:
        """Analisa itens sem solicitações e ordena por prioridade operacional."""
        results = [self.calcular_status(item) for item in items]
        results.sort(key=lambda r: (_STATUS_ORDER.get(r.status, 9), r.categoria, r.nome))
        return results

    def run_puro(self, items: list[ItemRecord]) -> list[AnalysisResult]:
        """Analisa itens com status puro (sem solicitações) para o Painel de Reposição."""
        results = [self.calcular_status_puro(item) for item in items]
        results.sort(key=lambda r: (_STATUS_ORDER.get(r.status, 9), r.categoria, r.nome))
        return results

    def run_consolidado(self, items: list[ItemRecord]) -> list[AnalysisResult]:
        """Analisa itens com solicitações do período e ordena por prioridade."""
        results = [self.calcular_status_consolidado(item) for item in items]
        results.sort(key=lambda r: (_STATUS_ORDER.get(r.status, 9), r.categoria, r.nome))
        return results

    def summary(self, results: list[AnalysisResult]) -> AnalysisSummary:
        """Gera contadores e totais consolidados a partir dos resultados."""
        s = AnalysisSummary(total_itens=len(results))
        for r in results:
            if r.status == ItemStatus.COMPRAR:
                s.itens_comprar += 1
            elif r.status == ItemStatus.OK:
                s.itens_ok += 1
            elif r.status in (ItemStatus.SEM_MINIMO, ItemStatus.SEM_PARAMETRO):
                s.itens_sem_minimo += 1
            elif r.status == ItemStatus.ZERADO:
                s.itens_zerados += 1
            elif r.status == ItemStatus.ABAIXO_MINIMO:
                s.itens_abaixo_minimo += 1
            elif r.status == ItemStatus.ABAIXO_IDEAL:
                s.itens_abaixo_ideal += 1

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
                    "abaixo_minimo": 0, "abaixo_ideal": 0,
                }
            status_key = r.status.value
            if r.status == ItemStatus.SEM_MINIMO:
                status_key = "sem_minimo"
            if status_key in s.por_categoria[cat]:
                s.por_categoria[cat][status_key] += 1

        s.valor_total_estimado = round(s.valor_total_estimado, 2)
        return s
