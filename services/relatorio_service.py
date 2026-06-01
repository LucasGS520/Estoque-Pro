from typing import Optional

import pandas as pd
from sqlalchemy.orm import Session

from core.models import Movimentacao, Item, Categoria


def consumo_por_mes(session: Session, item_id: Optional[int] = None) -> pd.DataFrame:
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
    q = session.query(Movimentacao)
    if item_id:
        q = q.filter(Movimentacao.item_id == item_id)
    if tipo:
        q = q.filter(Movimentacao.tipo == tipo)
    movs = q.order_by(Movimentacao.criado_em.desc()).limit(limit).all()

    if not movs:
        return pd.DataFrame()

    rows = [
        {
            "data": m.criado_em.strftime("%d/%m/%Y %H:%M"),
            "item_id": m.item_id,
            "tipo": m.tipo,
            "quantidade": m.quantidade,
            "qtd_anterior": m.quantidade_anterior,
            "qtd_nova": m.quantidade_nova,
            "motivo": m.motivo or "",
            "operador": m.operador or "",
        }
        for m in movs
    ]
    return pd.DataFrame(rows)
