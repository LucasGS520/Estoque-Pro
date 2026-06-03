""" Serviços de análise de compras e snapshots de reposição.

Conecta o motor puro de estoque (`core.engine`) aos modelos persistidos no
banco. As funções deste módulo leem itens ativos, escolhem cotações válidas e
persistem o resultado da análise em `snapshots_analise`.
"""

from sqlalchemy.orm import Session, joinedload

from core.engine import StockAnalyzer, ItemRecord, AnalysisResult, AnalysisSummary
from core.models import Item, SnapshotAnalise, Fornecedor
from services.fornecedor_service import get_best_price


def _item_to_record(item: Item, session: Session) -> ItemRecord:
    """Converte um `Item` ORM em `ItemRecord` para o motor de análise.

    Consulta a melhor cotação válida do item para preencher preço e fornecedor
    sugerido. Não persiste alterações.
    """
    melhor_preco = get_best_price(session, item.id)
    return ItemRecord(
        item_id=item.id,
        nome=item.nome,
        categoria=item.categoria.nome,
        qtd_atual=item.estoque_atual,
        estoque_minimo=item.estoque_minimo_vigente,
        estoque_ideal=item.estoque_ideal_vigente,
        preco_unitario=melhor_preco.preco_unitario if melhor_preco else None,
        fornecedor_sugerido=melhor_preco.fornecedor.nome if melhor_preco else None,
        fornecedor_sugerido_id=melhor_preco.fornecedor_id if melhor_preco else None,
    )


def run_analysis(session: Session) -> tuple[list[AnalysisResult], AnalysisSummary]:
    """
    Executa a análise de reposição e substitui o snapshot anterior.

    Lê todos os itens ativos, calcula resultados com `StockAnalyzer`, apaga os
    snapshots antigos e grava os novos em uma única transação. Retorna a lista
    de resultados calculados e o resumo agregado.
    """
    itens = (
        session.query(Item)
        .options(joinedload(Item.categoria))
        .filter(Item.ativo == True)  # noqa: E712
        .all()
    )
    records = [_item_to_record(item, session) for item in itens]

    analyzer = StockAnalyzer()
    results = analyzer.run(records)
    summary = analyzer.summary(results)

    # Persiste snapshot (apaga snapshots anteriores para manter apenas o mais recente)
    session.query(SnapshotAnalise).delete()
    for r in results:
        snap = SnapshotAnalise(
            item_id=r.item_id,
            status=r.status.value,
            quantidade_recomendar=r.quantidade_recomendar,
            valor_estimado=r.valor_estimado,
            fornecedor_sugerido_id=r.fornecedor_sugerido_id,
        )
        session.add(snap)
    session.commit()

    return results, summary


def get_latest_snapshot(session: Session) -> list[SnapshotAnalise]:
    """Retorna os snapshots atualmente persistidos, do mais recente ao antigo."""
    return (
        session.query(SnapshotAnalise)
        .options(joinedload(SnapshotAnalise.fornecedor_sugerido))
        .order_by(SnapshotAnalise.criado_em.desc())
        .all()
    )


def get_purchase_list(session: Session) -> list[SnapshotAnalise]:
    """Retorna apenas snapshots que exigem compra ou atenção por estoque zerado."""
    return (
        session.query(SnapshotAnalise)
        .options(joinedload(SnapshotAnalise.fornecedor_sugerido))
        .filter(SnapshotAnalise.status.in_(["comprar", "zerado"]))
        .all()
    )
