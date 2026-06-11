""" Serviços de relatórios baseados no histórico de movimentações.

As funções retornam `pandas.DataFrame` prontos para tabelas ou gráficos nas
páginas Streamlit. Nenhuma função deste módulo persiste alterações no banco.
"""

import datetime

from core import tempo
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


def consumo_por_categoria(session: Session, meses: Optional[int] = None) -> pd.DataFrame:
    """Agrupa a quantidade consumida por categoria de item.

    `meses=None` soma todo o histórico; qualquer inteiro restringe aos últimos N meses.
    """
    q = session.query(Movimentacao).filter(Movimentacao.tipo == "saida")
    if meses is not None:
        desde = tempo.agora() - datetime.timedelta(days=meses * 30)
        q = q.filter(Movimentacao.criado_em >= desde)
    movs = q.all()
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
    desde = tempo.agora() - datetime.timedelta(days=meses * 30)
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
    desde = tempo.agora() - datetime.timedelta(days=meses * 30)
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
    # Com setor específico, mantém detalhamento por setor.
    # Sem filtro, consolida por item para evitar duplicação no ranking.
    group_cols = ["item", "categoria", "setor"] if setor_id is not None else ["item", "categoria"]
    result = (
        df.groupby(group_cols)["quantidade"]
        .agg(total_saida="sum", num_movimentacoes="count")
        .reset_index()
    )
    if setor_id is None:
        result["setor"] = "Todos"
    return result.sort_values("total_saida", ascending=False)


def consumo_e_entradas_por_mes(session: Session, meses: int = 6) -> pd.DataFrame:
    """Retorna totais mensais consolidados de saída e entrada.

    Diferente de `consumo_por_mes()`, agrega globalmente (não por item),
    ideal para o gráfico de visão consolidada e linha de tendência.
    Retorna colunas: ["mes", "total_saida", "total_entrada"] ordenadas por mes ASC.
    """
    desde = tempo.agora() - datetime.timedelta(days=meses * 30)
    movs = (
        session.query(Movimentacao)
        .filter(
            Movimentacao.tipo.in_(["saida", "entrada"]),
            Movimentacao.criado_em >= desde,
        )
        .all()
    )

    if not movs:
        return pd.DataFrame(columns=["mes", "total_saida", "total_entrada"])

    rows = [
        {"mes": m.criado_em.strftime("%Y-%m"), "tipo": m.tipo, "quantidade": m.quantidade}
        for m in movs
    ]
    df = pd.DataFrame(rows)
    pivot = (
        df.groupby(["mes", "tipo"])["quantidade"]
        .sum()
        .unstack(fill_value=0)
        .reset_index()
    )
    # Garante que ambas as colunas existam mesmo se só houver um tipo no período
    if "saida" not in pivot.columns:
        pivot["saida"] = 0
    if "entrada" not in pivot.columns:
        pivot["entrada"] = 0
    pivot = pivot.rename(columns={"saida": "total_saida", "entrada": "total_entrada"})
    return pivot[["mes", "total_saida", "total_entrada"]].sort_values("mes")


# ---------------------------------------------------------------------------
# Funções analíticas do painel Consumo Mensal (usam data_inicio/data_fim)
# ---------------------------------------------------------------------------

def _dt_range(data_inicio: datetime.date, data_fim: datetime.date):
    """Converte datas para datetimes de início/fim do dia."""
    return (
        datetime.datetime.combine(data_inicio, datetime.time.min),
        datetime.datetime.combine(data_fim, datetime.time.max),
    )


def get_kpis_consumo(
    session: Session,
    data_inicio: datetime.date,
    data_fim: datetime.date,
    categoria_id: Optional[int] = None,
    setor_id: Optional[int] = None,
    item_id: Optional[int] = None,
) -> dict:
    """KPIs consolidados do período para o painel Consumo Mensal."""
    dt_ini, dt_fim = _dt_range(data_inicio, data_fim)
    q = (
        session.query(Movimentacao)
        .options(
            joinedload(Movimentacao.item).joinedload(Item.categoria),
            joinedload(Movimentacao.setor),
        )
        .filter(
            Movimentacao.tipo.in_(["saida", "entrada"]),
            Movimentacao.criado_em >= dt_ini,
            Movimentacao.criado_em <= dt_fim,
        )
    )
    if setor_id is not None:
        q = q.filter(Movimentacao.setor_id == setor_id)
    if item_id is not None:
        q = q.filter(Movimentacao.item_id == item_id)

    movs = q.all()
    if categoria_id is not None:
        movs = [m for m in movs if m.item and m.item.categoria_id == categoria_id]

    saidas = [m for m in movs if m.tipo == "saida"]
    entradas = [m for m in movs if m.tipo == "entrada"]

    total_saida = sum(m.quantidade for m in saidas)
    total_entrada = sum(m.quantidade for m in entradas)

    item_consumo: dict[str, int] = {}
    setor_consumo: dict[str, int] = {}
    for m in saidas:
        nome_item = m.item.nome if m.item else f"ID {m.item_id}"
        item_consumo[nome_item] = item_consumo.get(nome_item, 0) + m.quantidade
        nome_setor = m.setor.nome if m.setor else "Sem setor"
        setor_consumo[nome_setor] = setor_consumo.get(nome_setor, 0) + m.quantidade

    sem_setor = sum(1 for m in saidas if m.setor_id is None)

    return {
        "total_saida": total_saida,
        "total_entrada": total_entrada,
        "saldo": total_entrada - total_saida,
        "cobertura": round(total_entrada / total_saida, 2) if total_saida > 0 else None,
        "item_mais_consumido": max(item_consumo, key=item_consumo.get) if item_consumo else "—",
        "setor_mais_consumiu": max(setor_consumo, key=setor_consumo.get) if setor_consumo else "—",
        "pct_sem_setor": round(sem_setor / len(saidas) * 100, 1) if saidas else 0.0,
    }


def get_timeline_consumo(
    session: Session,
    data_inicio: datetime.date,
    data_fim: datetime.date,
    categoria_id: Optional[int] = None,
    setor_id: Optional[int] = None,
    item_id: Optional[int] = None,
) -> pd.DataFrame:
    """Timeline mensal enriquecida para o gráfico principal do painel Consumo Mensal.

    Além de total_saida/total_entrada, retorna n_movimentacoes, top_item e
    top_setor por mês para uso nos tooltips do gráfico.
    """
    COLS = ["mes", "total_saida", "total_entrada", "n_movimentacoes", "top_item", "top_setor"]
    dt_ini, dt_fim = _dt_range(data_inicio, data_fim)
    q = (
        session.query(Movimentacao)
        .options(
            joinedload(Movimentacao.item).joinedload(Item.categoria),
            joinedload(Movimentacao.setor),
        )
        .filter(
            Movimentacao.tipo.in_(["saida", "entrada"]),
            Movimentacao.criado_em >= dt_ini,
            Movimentacao.criado_em <= dt_fim,
        )
    )
    if setor_id is not None:
        q = q.filter(Movimentacao.setor_id == setor_id)
    if item_id is not None:
        q = q.filter(Movimentacao.item_id == item_id)

    movs = q.all()
    if categoria_id is not None:
        movs = [m for m in movs if m.item and m.item.categoria_id == categoria_id]

    if not movs:
        return pd.DataFrame(columns=COLS)

    meses: dict[str, dict] = {}
    for m in movs:
        mes = m.criado_em.strftime("%Y-%m")
        if mes not in meses:
            meses[mes] = {"saida": 0, "entrada": 0, "n": 0, "itens": {}, "setores": {}}
        d = meses[mes]
        d["n"] += 1
        if m.tipo == "saida":
            d["saida"] += m.quantidade
            nome_item = m.item.nome if m.item else f"ID {m.item_id}"
            d["itens"][nome_item] = d["itens"].get(nome_item, 0) + m.quantidade
            nome_setor = m.setor.nome if m.setor else "Sem setor"
            d["setores"][nome_setor] = d["setores"].get(nome_setor, 0) + m.quantidade
        else:
            d["entrada"] += m.quantidade

    rows = []
    for mes, d in sorted(meses.items()):
        rows.append({
            "mes": mes,
            "total_saida": d["saida"],
            "total_entrada": d["entrada"],
            "n_movimentacoes": d["n"],
            "top_item": max(d["itens"], key=d["itens"].get) if d["itens"] else "—",
            "top_setor": max(d["setores"], key=d["setores"].get) if d["setores"] else "—",
        })
    return pd.DataFrame(rows)


def get_top_itens_consumo(
    session: Session,
    data_inicio: datetime.date,
    data_fim: datetime.date,
    top_n: int = 5,
    categoria_id: Optional[int] = None,
    setor_id: Optional[int] = None,
    item_id: Optional[int] = None,
) -> pd.DataFrame:
    """Top N itens mais consumidos no período."""
    COLS = ["item", "categoria", "total_saida", "num_movimentacoes", "setor_principal"]
    dt_ini, dt_fim = _dt_range(data_inicio, data_fim)
    q = (
        session.query(Movimentacao)
        .options(
            joinedload(Movimentacao.item).joinedload(Item.categoria),
            joinedload(Movimentacao.setor),
        )
        .filter(
            Movimentacao.tipo == "saida",
            Movimentacao.criado_em >= dt_ini,
            Movimentacao.criado_em <= dt_fim,
        )
    )
    if setor_id is not None:
        q = q.filter(Movimentacao.setor_id == setor_id)
    if item_id is not None:
        q = q.filter(Movimentacao.item_id == item_id)

    movs = q.all()
    if categoria_id is not None:
        movs = [m for m in movs if m.item and m.item.categoria_id == categoria_id]

    if not movs:
        return pd.DataFrame(columns=COLS)

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
    agg = (
        df.groupby(["item", "categoria"])
        .agg(total_saida=("quantidade", "sum"), num_movimentacoes=("quantidade", "count"))
        .reset_index()
    )
    setor_mode = (
        df.groupby("item")["setor"]
        .agg(lambda x: x.mode().iloc[0] if not x.empty else "—")
        .reset_index()
        .rename(columns={"setor": "setor_principal"})
    )
    result = agg.merge(setor_mode, on="item")
    return result.sort_values("total_saida", ascending=False).head(top_n).reset_index(drop=True)


def get_top_itens_entrada(
    session: Session,
    data_inicio: datetime.date,
    data_fim: datetime.date,
    top_n: int = 5,
    categoria_id: Optional[int] = None,
) -> pd.DataFrame:
    """Top N itens com mais entradas no período."""
    COLS = ["item", "categoria", "total_entrada", "num_entradas"]
    dt_ini, dt_fim = _dt_range(data_inicio, data_fim)
    q = (
        session.query(Movimentacao)
        .options(joinedload(Movimentacao.item).joinedload(Item.categoria))
        .filter(
            Movimentacao.tipo == "entrada",
            Movimentacao.criado_em >= dt_ini,
            Movimentacao.criado_em <= dt_fim,
        )
    )
    movs = q.all()
    if categoria_id is not None:
        movs = [m for m in movs if m.item and m.item.categoria_id == categoria_id]

    if not movs:
        return pd.DataFrame(columns=COLS)

    rows = [
        {
            "item": m.item.nome if m.item else f"ID {m.item_id}",
            "categoria": m.item.categoria.nome if (m.item and m.item.categoria) else "—",
            "quantidade": m.quantidade,
        }
        for m in movs
    ]
    df = pd.DataFrame(rows)
    agg = (
        df.groupby(["item", "categoria"])
        .agg(total_entrada=("quantidade", "sum"), num_entradas=("quantidade", "count"))
        .reset_index()
    )
    return agg.sort_values("total_entrada", ascending=False).head(top_n).reset_index(drop=True)


def get_resumo_setor_periodo(
    session: Session,
    data_inicio: datetime.date,
    data_fim: datetime.date,
) -> pd.DataFrame:
    """Breakdown de saídas por setor no período."""
    COLS = ["setor", "total_saida", "num_movimentacoes", "pct"]
    dt_ini, dt_fim = _dt_range(data_inicio, data_fim)
    movs = (
        session.query(Movimentacao)
        .options(joinedload(Movimentacao.setor))
        .filter(
            Movimentacao.tipo == "saida",
            Movimentacao.criado_em >= dt_ini,
            Movimentacao.criado_em <= dt_fim,
        )
        .all()
    )
    if not movs:
        return pd.DataFrame(columns=COLS)

    rows = [
        {"setor": m.setor.nome if m.setor else "Sem setor", "quantidade": m.quantidade}
        for m in movs
    ]
    df = pd.DataFrame(rows)
    result = (
        df.groupby("setor")["quantidade"]
        .agg(total_saida="sum", num_movimentacoes="count")
        .reset_index()
        .sort_values("total_saida", ascending=False)
    )
    total = result["total_saida"].sum()
    result["pct"] = (result["total_saida"] / total * 100).round(1) if total > 0 else 0.0
    return result.reset_index(drop=True)


def get_resumo_categoria_periodo(
    session: Session,
    data_inicio: datetime.date,
    data_fim: datetime.date,
    setor_id: Optional[int] = None,
    item_id: Optional[int] = None,
) -> pd.DataFrame:
    """Breakdown de saídas por categoria no período."""
    COLS = ["categoria", "total_saida", "num_itens_movimentados", "pct"]
    dt_ini, dt_fim = _dt_range(data_inicio, data_fim)
    q = (
        session.query(Movimentacao)
        .options(joinedload(Movimentacao.item).joinedload(Item.categoria))
        .filter(
            Movimentacao.tipo == "saida",
            Movimentacao.criado_em >= dt_ini,
            Movimentacao.criado_em <= dt_fim,
        )
    )
    if setor_id is not None:
        q = q.filter(Movimentacao.setor_id == setor_id)
    if item_id is not None:
        q = q.filter(Movimentacao.item_id == item_id)

    movs = q.all()
    if not movs:
        return pd.DataFrame(columns=COLS)

    rows = [
        {
            "categoria": m.item.categoria.nome if (m.item and m.item.categoria) else "—",
            "item_id": m.item_id,
            "quantidade": m.quantidade,
        }
        for m in movs
    ]
    df = pd.DataFrame(rows)
    result = (
        df.groupby("categoria")
        .agg(total_saida=("quantidade", "sum"), num_itens_movimentados=("item_id", "nunique"))
        .reset_index()
        .sort_values("total_saida", ascending=False)
    )
    total = result["total_saida"].sum()
    result["pct"] = (result["total_saida"] / total * 100).round(1) if total > 0 else 0.0
    return result.reset_index(drop=True)
