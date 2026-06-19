"""Aba Por Categoria — página Relatórios."""
import datetime

import plotly.express as px
import streamlit as st

from core import tempo
from core.database import get_session_factory
from core.ui import APP_COLORS, PLOTLY_CONFIG, apply_chart_theme, chart_title, empty_state, section_title
from documents.relatorio_categoria import gerar_relatorio_categoria
from services.relatorio_service import consumo_por_categoria


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
    """Renderiza a aba Por Categoria."""
    SessionLocal = get_session_factory()

    section_title("Filtros")
    _periodo_opts_cat = _opcoes_periodo()
    _periodo_sel_cat = st.selectbox("Período", list(_periodo_opts_cat.keys()), index=0, key="cat_periodo")
    data_inicio_cat, data_fim_cat = _periodo_opts_cat[_periodo_sel_cat]

    with SessionLocal() as session:
        df_cat = consumo_por_categoria(session, data_inicio=data_inicio_cat, data_fim=data_fim_cat)

    if df_cat.empty:
        empty_state("📊", "Nenhum dado disponível", "Nenhuma movimentação de saída registrada no período.")
        return

    n_cats = len(df_cat)
    if n_cats <= 6:
        chart_title("Consumo por categoria")
        fig = px.bar(
            df_cat,
            x="categoria",
            y="total_saida",
            text="total_saida",
            labels={"categoria": "Categoria", "total_saida": "Qtd. Consumida"},
        )
        fig.update_traces(marker_color=APP_COLORS["primary"], textposition="outside")
        apply_chart_theme(fig, height=320)
    else:
        chart_title("Consumo por categoria")
        fig = px.bar(
            df_cat.sort_values("total_saida"),
            x="total_saida",
            y="categoria",
            orientation="h",
            text="total_saida",
            labels={"categoria": "Categoria", "total_saida": "Qtd. Consumida"},
        )
        fig.update_traces(marker_color=APP_COLORS["primary"], textposition="outside")
        fig.update_layout(yaxis={"categoryorder": "total ascending"})
        apply_chart_theme(fig, height=max(320, n_cats * 36))

    fig.update_layout(coloraxis_showscale=False)
    st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)

    st.divider()
    _doc_path_cat = gerar_relatorio_categoria(_periodo_sel_cat, df_cat)
    with open(_doc_path_cat, "rb") as _f:
        st.download_button(
            "Baixar Relatório (DOCX)",
            _f.read(),
            file_name=_doc_path_cat.name,
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            key="dl_categoria",
        )
