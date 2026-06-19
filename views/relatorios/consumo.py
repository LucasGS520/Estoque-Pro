"""Aba Consumo × Reposição — página Relatórios."""
import datetime

import plotly.express as px
import streamlit as st

from core import tempo
from core.database import get_session_factory
from core.i18n import MESES_ABREV as _MESES_PTBR
from core.ui import APP_COLORS, PLOTLY_CONFIG, apply_chart_theme, chart_title, empty_state, section_title
from documents.relatorio_consumo import gerar_relatorio_consumo
from services.estoque_service import get_categorias, get_setores
from services.relatorio_service import (
    get_kpis_consumo,
    get_timeline_consumo,
    get_top_itens_consumo,
)


def _fmt_mes(mes_str: str) -> str:
    try:
        ano, mes = mes_str.split("-")
        return f"{_MESES_PTBR.get(mes, mes)}/{ano[2:]}"
    except Exception:
        return mes_str


def _fmt_dia(dia_str: str) -> str:
    try:
        _, mes, dia = dia_str.split("-")
        return f"{dia}/{_MESES_PTBR.get(mes, mes)}"
    except Exception:
        return dia_str


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
    """Renderiza a aba Consumo × Reposição."""
    SessionLocal = get_session_factory()

    section_title("Filtros")

    with SessionLocal() as session:
        cats_disp = get_categorias(session)
        setores_disp_m = get_setores(session, apenas_ativos=False)

    cat_opcoes_m = {"Todas as categorias": None} | {c.nome: c.id for c in cats_disp}
    setor_opcoes_m = {"Todos os setores": None} | {s.nome: s.id for s in setores_disp_m}

    _periodo_opts_m = _opcoes_periodo()
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        _periodo_sel_m = st.selectbox(
            "Período", list(_periodo_opts_m.keys()), index=0, key="mensal_periodo",
        )
        data_inicio_m, data_fim_m = _periodo_opts_m[_periodo_sel_m]
    with c2:
        cat_m_sel = st.selectbox("Categoria", list(cat_opcoes_m.keys()), key="mensal_cat")
        cat_m_id = cat_opcoes_m[cat_m_sel]
    with c3:
        setor_m_sel = st.selectbox("Setor", list(setor_opcoes_m.keys()), key="mensal_setor")
        setor_m_id = setor_opcoes_m[setor_m_sel]
    with c4:
        top_n_m = st.slider("Itens no ranking", min_value=3, max_value=20, value=10, step=1, key="mensal_topn")

    gran_m = "dia" if _periodo_sel_m in ("Mês atual", "Mês anterior") else "mes"
    _fmt_eixo = _fmt_dia if gran_m == "dia" else _fmt_mes
    _label_eixo = "Dia" if gran_m == "dia" else "Mês"

    with SessionLocal() as session:
        df_timeline = get_timeline_consumo(session, data_inicio_m, data_fim_m, cat_m_id, setor_m_id, granularidade=gran_m)
        kpis = get_kpis_consumo(session, data_inicio_m, data_fim_m, cat_m_id, setor_m_id)
        df_top = get_top_itens_consumo(session, data_inicio_m, data_fim_m, top_n_m, cat_m_id, setor_m_id)

    st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)

    if df_top.empty:
        empty_state("📊", "Nenhum dado disponível", "Nenhuma movimentação registrada no período.")
        return

    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Total consumido", f"{kpis['total_saida']:,}".replace(",", "."))
    k2.metric("Total de entradas", f"{kpis['total_entrada']:,}".replace(",", "."))
    k3.metric("Item mais consumido", kpis["item_mais_consumido"])
    k4.metric("Setor com maior consumo", kpis["setor_mais_consumiu"])
    k5.metric("Nº de Movimentações", kpis["n_movimentacoes"])

    st.markdown("<div style='height:16px;'></div>", unsafe_allow_html=True)

    chart_title(f"Top {top_n_m} Itens Mais Consumidos — {_periodo_sel_m}")
    fig_bar = px.bar(
        df_top,
        x="total_saida",
        y="item",
        orientation="h",
        color_discrete_sequence=[APP_COLORS["primary"]],
        labels={"total_saida": "Consumo", "item": "Item"},
        text="total_saida",
    )
    fig_bar.update_traces(textposition="outside")
    fig_bar.update_yaxes(autorange="reversed")
    apply_chart_theme(fig_bar, height=max(280, len(df_top) * 45), showlegend=False)
    st.plotly_chart(fig_bar, use_container_width=True, config=PLOTLY_CONFIG)

    if not df_timeline.empty:
        st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)
        df_timeline["mes_label"] = df_timeline["mes"].apply(_fmt_eixo)
        chart_title(f"Consumo × Reposição — {_periodo_sel_m}")
        df_line = df_timeline.melt(
            id_vars="mes_label",
            value_vars=["total_saida", "total_entrada"],
            var_name="tipo",
            value_name="quantidade",
        )
        df_line["tipo"] = df_line["tipo"].map({"total_saida": "consumo", "total_entrada": "reposição"})
        fig_line = px.line(
            df_line,
            x="mes_label",
            y="quantidade",
            color="tipo",
            markers=True,
            color_discrete_map={"consumo": APP_COLORS["primary"], "reposição": APP_COLORS["black"]},
            labels={"mes_label": _label_eixo, "quantidade": "Quantidade", "tipo": ""},
            category_orders={"mes_label": df_timeline["mes_label"].tolist()},
        )
        fig_line.update_layout(xaxis_type="category")
        apply_chart_theme(fig_line, height=300, showlegend=True)
        st.plotly_chart(fig_line, use_container_width=True, config=PLOTLY_CONFIG)

    st.divider()
    _doc_path_m = gerar_relatorio_consumo(_periodo_sel_m, kpis, df_timeline)
    with open(_doc_path_m, "rb") as _f:
        st.download_button(
            "Baixar Relatório (DOCX)",
            _f.read(),
            file_name=_doc_path_m.name,
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            key="dl_consumo",
        )
