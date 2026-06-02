""" Serviços de relatórios baseados no histórico de movimentações.

As funções retornam `pandas.DataFrame` prontos para tabelas ou gráficos nas
páginas Streamlit. Nenhuma função deste módulo persiste alterações no banco.
"""

import datetime
from typing import Optional

import pandas as pd
from sqlalchemy.orm import Session, joinedload

from core.models import Categoria, Item, Movimentacao, Setor


def consumo_por_mes(session: Session, item_id: Optional[int] = None) -> pd.DataFrame:
    """Agrupa movimentações de saída por mês e item."""
    q = session.query(Movimentacao).filter(Movimentacao.tipo == "saida")
    if item_id:
        q = q.filter(Movimentacao.item_id == item_id)
    movs = q.all()

    if not movs:
        return pd.DataFrame(columns=["mes", "item", "total_saida"])

    rows = [
        {
            "mes": m.criado_em.strftime("%Y-%m"),
            "item_id": m.item_id,
            "quantidade": m.quantidade,
        }
        for m in movs
    ]
    df = pd.DataFrame(rows)
    df = df.groupby(["mes", "item_id"])["quantidade"].sum().reset_index()
    df.columns = ["mes", "item_id", "total_saida"]
    return df.sort_values("mes")


def consumo_por_categoria(session: Session) -> pd.DataFrame:
    """Agrupa a quantidade consumida por categoria de item."""
    movs = session.query(Movimentacao).filter(Movimentacao.tipo == "saida").all()
    if not movs:
        return pd.DataFrame(columns=["categoria", "total_saida"])

    item_cat: dict[int, str] = {}
    for m in movs:
        if m.item_id not in item_cat:
            item = session.query(Item).filter_by(id=m.item_id).first()
            if item and item.categoria:
                item_cat[m.item_id] = item.categoria.nome

    rows = [
        {"categoria": item_cat.get(m.item_id, "Desconhecido"), "quantidade": m.quantidade}
        for m in movs
        if m.item_id in item_cat
    ]
    if not rows:
        return pd.DataFrame(columns=["categoria", "total_saida"])

    df = pd.DataFrame(rows)
    df = df.groupby("categoria")["quantidade"].sum().reset_index()
    df.columns = ["categoria", "total_saida"]
    return df.sort_values("total_saida", ascending=False)


def historico_movimentacoes(
    session: Session,
    item_id: Optional[int] = None,
    tipo: Optional[str] = None,
    limit: int = 200,
) -> pd.DataFrame:
    """Retorna as movimentações mais recentes em formato tabular.

    Inclui coluna `setor` (nome do setor ou '—' para entradas sem setor) e
    `retirado_por` (consolida campo novo e legado `operador`).
    """
    q = session.query(Movimentacao).options(joinedload(Movimentacao.setor))
    if item_id:
        q = q.filter(Movimentacao.item_id == item_id)
    if tipo:
        q = q.filter(Movimentacao.tipo == tipo)
    movs = q.order_by(Movimentacao.criado_em.desc()).limit(limit).all()

    _COLS_HIST = ["data", "item_id", "tipo", "setor", "quantidade", "qtd_anterior", "qtd_nova", "motivo", "retirado_por"]
    if not movs:
        return pd.DataFrame(columns=_COLS_HIST)

    rows = [
        {
            "data": m.criado_em.strftime("%d/%m/%Y %H:%M"),
            "item_id": m.item_id,
            "tipo": m.tipo,
            "setor": m.setor.nome if m.setor else "—",
            "quantidade": m.quantidade,
            "qtd_anterior": m.quantidade_anterior,
            "qtd_nova": m.quantidade_nova,
            "motivo": m.motivo or "",
            "retirado_por": m.retirado_por or m.operador or "",
        }
        for m in movs
    ]
    return pd.DataFrame(rows)


def consumo_por_setor(session: Session, meses: int = 6) -> pd.DataFrame:
    """Agrega total de saídas por setor nos últimos N meses."""
    desde = datetime.datetime.utcnow() - datetime.timedelta(days=meses * 30)
    movs = (
        session.query(Movimentacao)
        .options(joinedload(Movimentacao.setor))
        .filter(Movimentacao.tipo == "saida", Movimentacao.criado_em >= desde)
        .all()
    )

    if not movs:
        return pd.DataFrame(columns=["setor", "total_saida", "num_movimentacoes"])

    rows = [
        {
            "setor": m.setor.nome if m.setor else "Sem setor",
            "quantidade": m.quantidade,
        }
        for m in movs
    ]
    df = pd.DataFrame(rows)
    result = (
        df.groupby("setor")["quantidade"]
        .agg(total_saida="sum", num_movimentacoes="count")
        .reset_index()
    )
    return result.sort_values("total_saida", ascending=False)


def consumo_por_item(
    session: Session,
    setor_id: Optional[int] = None,
    meses: int = 6,
) -> pd.DataFrame:
    """Agrega total de saídas por item (e setor) nos últimos N meses.

    Quando `setor_id` é informado, filtra apenas as saídas daquele setor.
    """
    desde = datetime.datetime.utcnow() - datetime.timedelta(days=meses * 30)
    q = (
        session.query(Movimentacao)
        .options(
            joinedload(Movimentacao.setor),
            joinedload(Movimentacao.item).joinedload(Item.categoria),
        )
        .filter(Movimentacao.tipo == "saida", Movimentacao.criado_em >= desde)
    )
    if setor_id is not None:
        q = q.filter(Movimentacao.setor_id == setor_id)
    movs = q.all()

    if not movs:
        return pd.DataFrame(
            columns=["item", "categoria", "setor", "total_saida", "num_movimentacoes"]
        )

    rows = [
        {
            "item": m.item.nome if m.item else f"ID {m.item_id}",
            "categoria": m.item.categoria.nome if (m.item and m.item.categoria) else "—",
            "setor": m.setor.nome if m.setor else "Sem setor",
            "quantidade": m.quantidade,
        }
        for m in movs
    ]
    df = pd.DataFrame(rows)
    result = (
        df.groupby(["item", "categoria", "setor"])["quantidade"]
        .agg(total_saida="sum", num_movimentacoes="count")
        .reset_index()
    )
    return result.sort_values("total_saida", ascending=False)
