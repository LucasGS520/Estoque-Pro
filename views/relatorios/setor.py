"""Aba Por Setor — página Relatórios."""
import datetime

import plotly.express as px
import streamlit as st

from core import tempo
from data.database import get_session_factory
from core.ui import APP_COLORS, PLOTLY_CONFIG, apply_chart_theme, chart_title, empty_state, section_title
from documents.relatorio_setor import gerar_relatorio_setor
from services.relatorio_service import consumo_por_setor


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
    """Renderiza a aba Por Setor."""
    SessionLocal = get_session_factory()

    section_title("Filtros")
    _periodo_opts_set = _opcoes_periodo()
    _periodo_sel_set = st.selectbox("Período", list(_periodo_opts_set.keys()), index=0, key="setor_periodo")
    data_inicio_set, data_fim_set = _periodo_opts_set[_periodo_sel_set]

    with SessionLocal() as session:
        df_setor = consumo_por_setor(session, data_inicio=data_inicio_set, data_fim=data_fim_set)

    if df_setor.empty:
        empty_state(
            "🏢",
            "Nenhum dado disponível",
            "Nenhuma saída com setor registrada no período selecionado.",
        )
        return

    total_geral = df_setor["total_saida"].sum()
    sem_setor_row = df_setor[df_setor["setor"] == "Sem setor"]
    total_sem_setor = int(sem_setor_row["total_saida"].sum()) if not sem_setor_row.empty else 0
    setores_ativos = df_setor[df_setor["setor"] != "Sem setor"]["setor"].nunique()
    pct_sem_setor = (total_sem_setor / total_geral * 100) if total_geral > 0 else 0

    k1, k2, k3 = st.columns(3)
    k1.metric("Total retirado", int(total_geral))
    k2.metric("Setores com consumo", setores_ativos)
    k3.metric("% sem setor", f"{pct_sem_setor:.1f}%")

    st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)

    setor_top = df_setor.iloc[0]["setor"] if len(df_setor) > 0 else None
    bar_colors = []
    for _, row in df_setor.sort_values("total_saida").iterrows():
        if row["setor"] == "Sem setor":
            bar_colors.append(APP_COLORS["orange"])
        elif row["setor"] == setor_top:
            bar_colors.append(APP_COLORS["primary"])
        else:
            bar_colors.append(APP_COLORS["black"])

    chart_title("Consumo por setor")
    fig = px.bar(
        df_setor.sort_values("total_saida"),
        x="total_saida",
        y="setor",
        orientation="h",
        text="total_saida",
        labels={"total_saida": "Qtd. Retirada", "setor": "Setor"},
    )
    fig.update_traces(textposition="outside", marker_color=bar_colors)
    fig.update_layout(yaxis={"categoryorder": "total ascending"}, coloraxis_showscale=False)
    apply_chart_theme(fig, height=max(280, len(df_setor) * 40))
    st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)

    section_title("Detalhamento")
    df_exib = df_setor.rename(columns={
        "setor": "Setor",
        "total_saida": "Total Retirado",
        "num_movimentacoes": "Nº Movimentações",
    })
    st.dataframe(df_exib, use_container_width=True, hide_index=True)
    st.caption(f"{len(df_setor)} setor(es) com movimentações no período.")

    st.divider()
    _doc_path_set = gerar_relatorio_setor(_periodo_sel_set, df_setor)
    with open(_doc_path_set, "rb") as _f:
        st.download_button(
            "Baixar Relatório (DOCX)",
            _f.read(),
            file_name=_doc_path_set.name,
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            key="dl_setor",
        )
