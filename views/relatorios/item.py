"""Aba Por Item — página Relatórios."""
import datetime

import plotly.express as px
import streamlit as st

from core import tempo
from core.database import get_session_factory
from core.ui import APP_COLORS, PLOTLY_CONFIG, apply_chart_theme, chart_title, empty_state, section_title
from documents.relatorio_item import gerar_relatorio_item
from services.estoque_service import get_setores
from services.relatorio_service import consumo_por_item


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
    """Renderiza a aba Por Item."""
    SessionLocal = get_session_factory()

    section_title("Filtros")
    _periodo_opts_item = _opcoes_periodo()
    col1, col2 = st.columns(2)
    with col1:
        _periodo_sel_item = st.selectbox(
            "Período", list(_periodo_opts_item.keys()), index=0, key="item_periodo",
        )
        data_inicio_item, data_fim_item = _periodo_opts_item[_periodo_sel_item]
    with col2:
        with SessionLocal() as session:
            setores_disp = get_setores(session, apenas_ativos=False)
        setor_opcoes = {"Todos os setores": None} | {s.nome: s.id for s in setores_disp}
        setor_sel = st.selectbox("Setor", list(setor_opcoes.keys()), key="item_setor")
        setor_id_filtro = setor_opcoes[setor_sel]

    with SessionLocal() as session:
        df_item = consumo_por_item(session, setor_id=setor_id_filtro, data_inicio=data_inicio_item, data_fim=data_fim_item)

    if df_item.empty:
        empty_state(
            "📦",
            "Nenhum dado disponível",
            "Nenhuma saída registrada com os filtros selecionados.",
        )
        return

    top_n = st.selectbox("Exibir top", [10, 20], index=1, key="item_top_n")
    top_df = df_item.head(top_n)

    item_top = top_df.iloc[0]["item"] if len(top_df) > 0 else None
    bar_colors_item = [
        APP_COLORS["primary"] if row["item"] == item_top else APP_COLORS["black"]
        for _, row in top_df.sort_values("total_saida").iterrows()
    ]

    chart_title(f"Top {len(top_df)} itens por consumo")
    fig = px.bar(
        top_df.sort_values("total_saida"),
        x="total_saida",
        y="item",
        orientation="h",
        text="total_saida",
        labels={"total_saida": "Qtd. Retirada", "item": "Item"},
    )
    fig.update_traces(textposition="outside", marker_color=bar_colors_item)
    fig.update_layout(yaxis={"categoryorder": "total ascending"}, coloraxis_showscale=False)
    apply_chart_theme(fig, height=max(280, len(top_df) * 36))
    st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)

    section_title("Detalhamento")
    cols_exib = ["item", "categoria", "total_saida", "num_movimentacoes"]
    if setor_id_filtro is not None:
        cols_exib.insert(2, "setor")
    df_exib = df_item[cols_exib].rename(columns={
        "item": "Item",
        "categoria": "Categoria",
        "setor": "Setor",
        "total_saida": "Total Retirado",
        "num_movimentacoes": "Nº Movimentações",
    })
    st.dataframe(df_exib, use_container_width=True, hide_index=True)
    st.caption(f"{len(df_item)} item(ns) com movimentações no período.")

    st.divider()
    _doc_path_item = gerar_relatorio_item(_periodo_sel_item, df_item, setor_sel)
    with open(_doc_path_item, "rb") as _f:
        st.download_button(
            "Baixar Relatório (DOCX)",
            _f.read(),
            file_name=_doc_path_item.name,
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            key="dl_item",
        )
