"""Aba Histórico de Movimentações — página Relatórios."""
import datetime

import streamlit as st

from core import tempo
from data.database import get_session_factory
from data.models import Categoria as CategoriaModel, Item
from core.ui import empty_state, section_title
from documents.relatorio_historico import gerar_relatorio_historico
from services.estoque_service import get_setores
from services.relatorio_service import historico_movimentacoes


def _opcoes_periodo() -> dict[str, tuple[datetime.date, datetime.date]]:
    hoje = tempo.hoje()
    mes_atual_inicio = hoje.replace(day=1)
    mes_ant_fim      = mes_atual_inicio - datetime.timedelta(days=1)
    mes_ant_inicio   = mes_ant_fim.replace(day=1)
    return {
        "Mês atual":        (mes_atual_inicio,                    hoje),
        "Mês anterior":     (mes_ant_inicio,                      mes_ant_fim),
        "Últimos 3 meses":  (hoje - datetime.timedelta(days=90),  hoje),
        "Últimos 12 meses": (hoje - datetime.timedelta(days=365), hoje),
    }


def render() -> None:
    """Renderiza a aba Histórico de Movimentações."""
    SessionLocal = get_session_factory()

    section_title("Filtros")
    _periodo_opts_hist = _opcoes_periodo()

    with SessionLocal() as session:
        cats_hist = session.query(CategoriaModel).all()
        setores_hist = get_setores(session, apenas_ativos=False)

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        _periodo_sel_hist = st.selectbox("Período", list(_periodo_opts_hist.keys()), index=0, key="hist_periodo")
        data_inicio_hist, data_fim_hist = _periodo_opts_hist[_periodo_sel_hist]
    with col2:
        _TIPO_OPTS = {"Todos": None, "Entrada": "entrada", "Saída": "saida"}
        filtro_tipo = st.selectbox("Tipo", list(_TIPO_OPTS.keys()), key="hist_tipo")
        tipo_filtro = _TIPO_OPTS[filtro_tipo]
    with col3:
        cat_opcoes_hist = {"Todas as categorias": None} | {c.nome: c.id for c in cats_hist}
        cat_hist_sel = st.selectbox("Categoria", list(cat_opcoes_hist.keys()), key="hist_cat")
        cat_hist_id = cat_opcoes_hist[cat_hist_sel]
    with col4:
        setor_opcoes_hist = {"Todos os setores": None} | {s.nome: s.id for s in setores_hist}
        setor_hist_sel = st.selectbox("Setor", list(setor_opcoes_hist.keys()), key="hist_setor")
        setor_hist_id = setor_opcoes_hist[setor_hist_sel]

    col_busca, col_lim = st.columns([3, 1])
    with col_busca:
        busca_item_hist = st.text_input("Buscar por item", placeholder="Digite parte do nome...", key="hist_busca_item")
    with col_lim:
        limite = st.number_input("Limite de registros", min_value=10, max_value=1000, value=200, key="hist_limite")

    with SessionLocal() as session:
        df_hist = historico_movimentacoes(
            session,
            tipo=tipo_filtro,
            setor_id=setor_hist_id,
            limit=int(limite),
            data_inicio=data_inicio_hist,
            data_fim=data_fim_hist,
        )

    if df_hist.empty:
        empty_state("📋", "Nenhuma movimentação encontrada")
        return

    with SessionLocal() as session:
        itens_obj = session.query(Item).all()
        itens_map = {i.id: i.nome for i in itens_obj}
        itens_cat_map = {i.id: (i.categoria.nome if i.categoria else None) for i in itens_obj}

    if "item_id" in df_hist.columns:
        df_hist.insert(1, "item", df_hist["item_id"].map(itens_map))
        df_hist.insert(2, "_cat", df_hist["item_id"].map(itens_cat_map))
        df_hist = df_hist.drop(columns=["item_id"])

    if cat_hist_id is not None:
        df_hist = df_hist[df_hist["_cat"] == cat_hist_sel]
    df_hist = df_hist.drop(columns=["_cat"], errors="ignore")
    if busca_item_hist.strip():
        _busca = busca_item_hist.strip().lower()
        df_hist = df_hist[df_hist["item"].str.lower().str.contains(_busca, na=False)]

    df_hist = df_hist.copy()

    if df_hist.empty:
        empty_state("📋", "Nenhuma movimentação encontrada para os filtros selecionados.")
        return

    _TIPO_BADGE = {
        "entrada":   "<span style='background:#F4F4F5;color:#111827;padding:2px 8px;"
                     "border-radius:4px;font-size:12px;font-weight:500;'>Entrada</span>",
        "saida":     "<span style='background:#FEE2E2;color:#DC2626;padding:2px 8px;"
                     "border-radius:4px;font-size:12px;font-weight:500;'>Saída</span>",
        "devolucao": "<span style='background:#FEF3C7;color:#92400E;padding:2px 8px;"
                     "border-radius:4px;font-size:12px;font-weight:500;'>Devolução</span>",
    }
    df_hist["tipo_badge"] = df_hist["tipo"].map(_TIPO_BADGE).fillna(df_hist["tipo"])

    df_exib = df_hist.drop(columns=["tipo"]).rename(columns={
        "data": "Data",
        "item": "Item",
        "tipo_badge": "Tipo",
        "setor": "Setor",
        "quantidade": "Qtd.",
        "qtd_anterior": "Anterior",
        "qtd_nova": "Nova",
        "motivo": "Motivo",
        "retirado_por": "Retirado por",
    })
    st.write(df_exib.to_html(escape=False, index=False), unsafe_allow_html=True)
    st.caption(f"{len(df_exib)} registros")

    st.divider()
    _df_doc_hist = df_hist.drop(columns=["tipo_badge"], errors="ignore")
    _doc_path_hist = gerar_relatorio_historico(_periodo_sel_hist, _df_doc_hist)
    with open(_doc_path_hist, "rb") as _f:
        st.download_button(
            "Baixar Relatório (DOCX)",
            _f.read(),
            file_name=_doc_path_hist.name,
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            key="dl_historico",
        )
