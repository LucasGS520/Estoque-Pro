import streamlit as st
import plotly.express as px

from core.database import get_session_factory
from core.ui import setup_page, page_header, section_title, empty_state, apply_plotly_theme
from services.relatorio_service import (
    consumo_por_mes,
    consumo_por_categoria,
    historico_movimentacoes,
)
from core.models import Item

setup_page("Relatórios", "📈")
page_header("Relatórios", subtitle="Consumo histórico por período, categoria e movimentações.")

SessionLocal = get_session_factory()

tab_mensal, tab_categoria, tab_historico = st.tabs(
    ["Consumo Mensal", "Por Categoria", "Histórico de Movimentações"]
)

with tab_mensal:
    with SessionLocal() as session:
        df_mensal = consumo_por_mes(session)

    if df_mensal.empty:
        empty_state(
            "📊",
            "Nenhum dado disponível",
            "Nenhuma movimentação de saída registrada ainda.",
        )
    else:
        with SessionLocal() as session:
            itens_map = {i.id: i.nome for i in session.query(Item).all()}
        df_mensal["item"] = df_mensal["item_id"].map(itens_map)
        fig = px.line(
            df_mensal,
            x="mes",
            y="total_saida",
            color="item",
            markers=True,
            title="Consumo Mensal por Item",
            labels={"mes": "Mês", "total_saida": "Qtd. Consumida", "item": "Item"},
        )
        apply_plotly_theme(fig)
        st.plotly_chart(fig, use_container_width=True)

with tab_categoria:
    with SessionLocal() as session:
        df_cat = consumo_por_categoria(session)

    if df_cat.empty:
        empty_state(
            "📊",
            "Nenhum dado disponível",
            "Nenhuma movimentação de saída registrada ainda.",
        )
    else:
        fig = px.bar(
            df_cat,
            x="categoria",
            y="total_saida",
            title="Consumo Total por Categoria",
            labels={"categoria": "Categoria", "total_saida": "Qtd. Consumida"},
            color="total_saida",
            color_continuous_scale=["#FEE2E2", "#E10600"],
        )
        apply_plotly_theme(fig)
        st.plotly_chart(fig, use_container_width=True)

with tab_historico:
    section_title("Filtros")
    col1, col2 = st.columns(2)
    with col1:
        filtro_tipo = st.selectbox(
            "Tipo",
            ["Todos", "entrada", "saida", "ajuste", "inventario"],
            key="hist_tipo",
        )
    with col2:
        limite = st.number_input("Limite de registros", min_value=10, max_value=1000, value=100)

    tipo_filtro = None if filtro_tipo == "Todos" else filtro_tipo

    with SessionLocal() as session:
        df_hist = historico_movimentacoes(session, tipo=tipo_filtro, limit=limite)

    if df_hist.empty:
        empty_state("📋", "Nenhuma movimentação encontrada")
    else:
        with SessionLocal() as session:
            itens_map = {i.id: i.nome for i in session.query(Item).all()}
        if "item_id" in df_hist.columns:
            df_hist.insert(1, "item", df_hist["item_id"].map(itens_map))
            df_hist = df_hist.drop(columns=["item_id"])
        st.dataframe(df_hist, use_container_width=True, hide_index=True)
        st.caption(f"{len(df_hist)} registros")
