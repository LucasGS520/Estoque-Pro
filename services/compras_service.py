""" Serviços de análise de compras, solicitações e lista final de compras.

Conecta o motor puro de estoque (`core.engine`) aos modelos persistidos no
banco. As funções deste módulo leem itens ativos, escolhem cotações válidas,
registram solicitações de materiais, consolidam necessidades por período e
persistem o resultado em `snapshots_analise` (legado) e `itens_lista_compra`.
"""

import datetime
from typing import Optional

from sqlalchemy import and_
from sqlalchemy.orm import Session, joinedload

from core.engine import (
    AnalysisResult, AnalysisSummary, ItemRecord, SolicitacaoRecord, StockAnalyzer,
)
from core.models import Fornecedor, Item, ItemListaCompra, SnapshotAnalise, SolicitacaoMaterial
from core.schemas import SolicitacaoMaterialCreate
from services.fornecedor_service import get_best_price


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

def _item_to_record(item: Item, session: Session) -> ItemRecord:
    """Converte um `Item` ORM em `ItemRecord` para o motor de análise."""
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


# ---------------------------------------------------------------------------
# Funções legadas — mantidas intactas para compatibilidade com Orçamentos
# ---------------------------------------------------------------------------

def run_analysis(session: Session) -> tuple[list[AnalysisResult], AnalysisSummary]:
    """Executa análise de reposição sem solicitações e substitui o snapshot anterior."""
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
    """Retorna snapshots que exigem compra ou atenção por estoque zerado."""
    return (
        session.query(SnapshotAnalise)
        .options(joinedload(SnapshotAnalise.fornecedor_sugerido))
        .filter(SnapshotAnalise.status.in_(["comprar", "zerado"]))
        .all()
    )


# ---------------------------------------------------------------------------
# Solicitações de materiais
# ---------------------------------------------------------------------------

def criar_solicitacao(
    session: Session, dados: SolicitacaoMaterialCreate
) -> SolicitacaoMaterial:
    """Registra uma nova solicitação de compra para um período."""
    sol = SolicitacaoMaterial(
        item_id=dados.item_id,
        nome_item_livre=dados.nome_item_livre,
        setor_id=dados.setor_id,
        solicitante=dados.solicitante,
        quantidade_solicitada=dados.quantidade_solicitada,
        observacao=dados.observacao,
        periodo_referencia=dados.periodo_referencia,
        status="pendente",
    )
    session.add(sol)
    session.commit()
    session.refresh(sol)
    return sol


def listar_solicitacoes(
    session: Session,
    periodo: datetime.date,
    setor_id: Optional[int] = None,
) -> list[SolicitacaoMaterial]:
    """Lista solicitações de um período, com eager load de item e setor."""
    q = (
        session.query(SolicitacaoMaterial)
        .options(
            joinedload(SolicitacaoMaterial.item).joinedload(Item.categoria),
            joinedload(SolicitacaoMaterial.setor),
        )
        .filter(SolicitacaoMaterial.periodo_referencia == periodo)
    )
    if setor_id is not None:
        q = q.filter(SolicitacaoMaterial.setor_id == setor_id)
    return q.order_by(SolicitacaoMaterial.criado_em.desc()).all()


def deletar_solicitacao(session: Session, sol_id: int) -> None:
    """Remove uma solicitação de compra pelo id."""
    sol = session.get(SolicitacaoMaterial, sol_id)
    if sol:
        session.delete(sol)
        session.commit()


def classificar_solicitacoes_periodo(
    session: Session, periodo: datetime.date
) -> dict[str, int]:
    """Classifica solicitações pendentes do período, atualizando seus status.

    - item_id presente + item tem mínimo e ideal → "validada"
    - item_id presente + falta mínimo ou ideal   → "pendente_parametrizacao"
    - item_id ausente (nome livre)               → "pendente_cadastro"

    Retorna contagens por status: {validadas, pendente_cadastro, pendente_parametrizacao}.
    """
    pendentes = (
        session.query(SolicitacaoMaterial)
        .filter(
            SolicitacaoMaterial.periodo_referencia == periodo,
            SolicitacaoMaterial.status == "pendente",
        )
        .all()
    )

    contagens: dict[str, int] = {"validadas": 0, "pendente_cadastro": 0, "pendente_parametrizacao": 0}

    for sol in pendentes:
        if sol.item_id is None:
            sol.status = "pendente_cadastro"
            contagens["pendente_cadastro"] += 1
        else:
            item = session.get(Item, sol.item_id)
            tem_minimo = item is not None and item.estoque_minimo_vigente is not None
            tem_ideal = item is not None and item.estoque_ideal_vigente is not None
            if tem_minimo and tem_ideal:
                sol.status = "validada"
                contagens["validadas"] += 1
            else:
                sol.status = "pendente_parametrizacao"
                contagens["pendente_parametrizacao"] += 1

    session.commit()
    return contagens


# ---------------------------------------------------------------------------
# Consolidação do período
# ---------------------------------------------------------------------------

def consolidar_periodo(
    session: Session, periodo: datetime.date
) -> tuple[list[AnalysisResult], AnalysisSummary]:
    """Cruza estoque real com solicitações do período e persiste ItemListaCompra.

    Preserva `quantidade_final_definida`, `motivo` e `incluir_na_lista_final` de
    registros que o responsável já editou manualmente (quantidade_final_definida
    não nula). Para os demais, reescreve com o novo valor sugerido.
    """
    # Carrega itens ativos com categorias e melhores preços
    itens = (
        session.query(Item)
        .options(joinedload(Item.categoria))
        .filter(Item.ativo == True)  # noqa: E712
        .all()
    )

    # Carrega e agrupa somente solicitações validadas do período por item_id
    solicitacoes = (
        session.query(SolicitacaoMaterial)
        .options(joinedload(SolicitacaoMaterial.setor))
        .filter(
            SolicitacaoMaterial.periodo_referencia == periodo,
            SolicitacaoMaterial.status == "validada",
        )
        .all()
    )
    sols_por_item: dict[int, list[SolicitacaoRecord]] = {}
    for sol in solicitacoes:
        if sol.item_id is None:
            continue
        setor_nome = sol.setor.nome if sol.setor else (sol.solicitante or "—")
        rec = SolicitacaoRecord(
            setor=setor_nome,
            solicitante=sol.solicitante,
            quantidade=sol.quantidade_solicitada,
        )
        sols_por_item.setdefault(sol.item_id, []).append(rec)

    # Monta ItemRecords com solicitações
    records: list[ItemRecord] = []
    for item in itens:
        melhor_preco = get_best_price(session, item.id)
        rec = ItemRecord(
            item_id=item.id,
            nome=item.nome,
            categoria=item.categoria.nome,
            qtd_atual=item.estoque_atual,
            estoque_minimo=item.estoque_minimo_vigente,
            estoque_ideal=item.estoque_ideal_vigente,
            preco_unitario=melhor_preco.preco_unitario if melhor_preco else None,
            fornecedor_sugerido=melhor_preco.fornecedor.nome if melhor_preco else None,
            fornecedor_sugerido_id=melhor_preco.fornecedor_id if melhor_preco else None,
            solicitations=sols_por_item.get(item.id, []),
        )
        records.append(rec)

    analyzer = StockAnalyzer()
    results = analyzer.run_consolidado(records)
    summary = analyzer.summary(results)

    # Upsert em ItemListaCompra
    existentes: dict[int, ItemListaCompra] = {
        e.item_id: e
        for e in session.query(ItemListaCompra)
        .filter(ItemListaCompra.periodo_referencia == periodo)
        .all()
    }

    for r in results:
        editado_manualmente = (
            r.item_id in existentes
            and existentes[r.item_id].quantidade_final_definida is not None
        )

        if r.item_id in existentes:
            lista = existentes[r.item_id]
            lista.status = r.status.value
            lista.estoque_atual_snap = r.qtd_atual
            lista.estoque_minimo_snap = r.estoque_minimo
            lista.estoque_ideal_snap = r.estoque_ideal
            lista.total_solicitado = r.total_solicitado
            lista.quantidade_sugerida = r.quantidade_recomendar
            lista.valor_estimado = r.valor_estimado
            lista.fornecedor_sugerido_id = r.fornecedor_sugerido_id
            lista.atualizado_em = datetime.datetime.utcnow()
            # Preserva decisões manuais se já foram registradas
            if not editado_manualmente:
                lista.quantidade_final_definida = None
                lista.motivo = None
                lista.incluir_na_lista_final = False
        else:
            lista = ItemListaCompra(
                item_id=r.item_id,
                periodo_referencia=periodo,
                status=r.status.value,
                estoque_atual_snap=r.qtd_atual,
                estoque_minimo_snap=r.estoque_minimo,
                estoque_ideal_snap=r.estoque_ideal,
                total_solicitado=r.total_solicitado,
                quantidade_sugerida=r.quantidade_recomendar,
                valor_estimado=r.valor_estimado,
                fornecedor_sugerido_id=r.fornecedor_sugerido_id,
            )
            session.add(lista)

    session.commit()
    return results, summary


# ---------------------------------------------------------------------------
# Gestão da Lista Final
# ---------------------------------------------------------------------------

def get_consolidacao_periodo(
    session: Session, periodo: datetime.date
) -> list[ItemListaCompra]:
    """Retorna todos os itens consolidados de um período, ordenados por status."""
    _STATUS_SORT = {
        "zerado": 0, "comprar": 1, "abaixo_minimo": 2,
        "sem_minimo_definido": 3, "excesso": 4, "ok": 5,
    }
    items = (
        session.query(ItemListaCompra)
        .options(
            joinedload(ItemListaCompra.item).joinedload(Item.categoria),
            joinedload(ItemListaCompra.fornecedor_sugerido),
        )
        .filter(ItemListaCompra.periodo_referencia == periodo)
        .all()
    )
    items.sort(key=lambda x: (
        _STATUS_SORT.get(x.status, 9),
        x.item.categoria.nome if x.item and x.item.categoria else "",
        x.item.nome if x.item else "",
    ))
    return items


def get_lista_final(
    session: Session, periodo: datetime.date
) -> list[ItemListaCompra]:
    """Retorna apenas os itens aprovados para orçamento no período."""
    return (
        session.query(ItemListaCompra)
        .options(
            joinedload(ItemListaCompra.item).joinedload(Item.categoria),
            joinedload(ItemListaCompra.fornecedor_sugerido),
        )
        .filter(
            and_(
                ItemListaCompra.periodo_referencia == periodo,
                ItemListaCompra.incluir_na_lista_final == True,  # noqa: E712
            )
        )
        .all()
    )


def aprovar_item(
    session: Session,
    lista_id: int,
    qtd_final: int,
    motivo: Optional[str] = None,
) -> ItemListaCompra:
    """Aprova um item para a lista final com quantidade e motivo definidos.

    Motivo é obrigatório quando qtd_final difere de quantidade_sugerida.
    """
    lista = session.get(ItemListaCompra, lista_id)
    if lista is None:
        raise ValueError(f"ItemListaCompra {lista_id} não encontrado")
    if qtd_final != lista.quantidade_sugerida and not motivo:
        raise ValueError("Motivo é obrigatório quando a quantidade final difere da sugerida")
    lista.quantidade_final_definida = qtd_final
    lista.motivo = motivo
    lista.incluir_na_lista_final = True
    lista.atualizado_em = datetime.datetime.utcnow()
    session.commit()
    session.refresh(lista)
    return lista


def remover_da_lista(session: Session, lista_id: int) -> ItemListaCompra:
    """Remove um item da lista final (mantém o registro, apenas desmarca a flag)."""
    lista = session.get(ItemListaCompra, lista_id)
    if lista is None:
        raise ValueError(f"ItemListaCompra {lista_id} não encontrado")
    lista.incluir_na_lista_final = False
    lista.atualizado_em = datetime.datetime.utcnow()
    session.commit()
    session.refresh(lista)
    return lista


def get_periodos_com_consolidacao(session: Session) -> list[datetime.date]:
    """Retorna os períodos que já possuem consolidação registrada."""
    rows = (
        session.query(ItemListaCompra.periodo_referencia)
        .distinct()
        .order_by(ItemListaCompra.periodo_referencia.desc())
        .all()
    )
    return [r[0] for r in rows]
