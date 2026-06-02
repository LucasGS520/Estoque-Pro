""" Tela de relatórios operacionais.

Exibe gráficos e tabelas derivados do histórico de movimentações, sem alterar
dados do banco.
"""

import streamlit as st
import plotly.express as px

from core.database import get_session_factory
from core.models import Item
from core.ui import setup_page, page_header, section_title, empty_state, apply_plotly_theme
from services.estoque_service import get_setores
from services.relatorio_service import (
    consumo_por_categoria,
    consumo_por_item,
    consumo_por_mes,
    consumo_por_setor,
    historico_movimentacoes,
)

setup_page("Relatórios", "📈")
page_header("Relatórios", subtitle="Consumo histórico por período, categoria, setor e item.")

SessionLocal = get_session_factory()

tab_mensal, tab_categoria, tab_setor, tab_item, tab_historico = st.tabs([
    "Consumo Mensal",
    "Por Categoria",
    "Por Setor",
    "Por Item",
    "Histórico de Movimentações",
])

# ── Tab: Consumo Mensal ───────────────────────────────────────────────────────
with tab_mensal:
    with SessionLocal() as session:
        df_mensal = consumo_por_mes(session)

    if df_mensal.empty:
        empty_state("📊", "Nenhum dado disponível", "Nenhuma movimentação de saída registrada ainda.")
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

# ── Tab: Por Categoria ────────────────────────────────────────────────────────
with tab_categoria:
    with SessionLocal() as session:
        df_cat = consumo_por_categoria(session)

    if df_cat.empty:
        empty_state("📊", "Nenhum dado disponível", "Nenhuma movimentação de saída registrada ainda.")
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

# ── Tab: Por Setor ────────────────────────────────────────────────────────────
with tab_setor:
    section_title("Filtros")
    periodo_setor = st.selectbox(
        "Período",
        options=[3, 6, 12],
        format_func=lambda m: f"Últimos {m} meses",
        index=1,
        key="setor_periodo",
    )

    with SessionLocal() as session:
        df_setor = consumo_por_setor(session, meses=periodo_setor)

    if df_setor.empty:
        empty_state(
            "🏢",
            "Nenhum dado disponível",
            "Nenhuma saída com setor registrada no período selecionado.",
        )
    else:
        fig = px.bar(
            df_setor,
            x="total_saida",
            y="setor",
            orientation="h",
            title=f"Consumo por Setor — últimos {periodo_setor} meses",
            labels={"total_saida": "Qtd. Retirada", "setor": "Setor"},
            color="total_saida",
            color_continuous_scale=["#DBEAFE", "#1D4ED8"],
            text="total_saida",
        )
        fig.update_traces(textposition="outside")
        fig.update_layout(yaxis={"categoryorder": "total ascending"}, showlegend=False)
        apply_plotly_theme(fig)
        st.plotly_chart(fig, use_container_width=True)

        section_title("Detalhamento")
        df_exib = df_setor.rename(columns={
            "setor": "Setor",
            "total_saida": "Total Retirado",
            "num_movimentacoes": "Nº Movimentações",
        })
        st.dataframe(df_exib, use_container_width=True, hide_index=True)
        st.caption(f"{len(df_setor)} setor(es) com movimentações no período.")

# ── Tab: Por Item ─────────────────────────────────────────────────────────────
with tab_item:
    section_title("Filtros")
    col1, col2 = st.columns(2)
    with col1:
        periodo_item = st.selectbox(
            "Período",
            options=[3, 6, 12],
            format_func=lambda m: f"Últimos {m} meses",
            index=1,
            key="item_periodo",
        )
    with col2:
        with SessionLocal() as session:
            setores_disp = get_setores(session, apenas_ativos=False)
        setor_opcoes = {"Todos os setores": None} | {s.nome: s.id for s in setores_disp}
        setor_sel = st.selectbox("Setor", list(setor_opcoes.keys()), key="item_setor")
        setor_id_filtro = setor_opcoes[setor_sel]

    with SessionLocal() as session:
        df_item = consumo_por_item(session, setor_id=setor_id_filtro, meses=periodo_item)

    if df_item.empty:
        empty_state(
            "📦",
            "Nenhum dado disponível",
            "Nenhuma saída registrada com os filtros selecionados.",
        )
    else:
        top20 = df_item.head(20)
        fig = px.bar(
            top20,
            x="total_saida",
            y="item",
            orientation="h",
            title=f"Top {len(top20)} Itens por Consumo — últimos {periodo_item} meses",
            labels={"total_saida": "Qtd. Retirada", "item": "Item"},
            color="total_saida",
            color_continuous_scale=["#FEF3C7", "#D97706"],
            text="total_saida",
        )
        fig.update_traces(textposition="outside")
        fig.update_layout(yaxis={"categoryorder": "total ascending"}, showlegend=False)
        apply_plotly_theme(fig)
        st.plotly_chart(fig, use_container_width=True)

        section_title("Detalhamento")
        df_exib = df_item.rename(columns={
            "item": "Item",
            "categoria": "Categoria",
            "setor": "Setor",
            "total_saida": "Total Retirado",
            "num_movimentacoes": "Nº Movimentações",
        })
        st.dataframe(df_exib, use_container_width=True, hide_index=True)
        st.caption(f"{len(df_item)} item(ns) com movimentações no período.")

# ── Tab: Histórico de Movimentações ──────────────────────────────────────────
with tab_historico:
    section_title("Filtros")
    col1, col2 = st.columns(2)
    with col1:
        filtro_tipo = st.selectbox(
            "Tipo",
            ["Todos", "entrada", "saida"],
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

        df_hist = df_hist.rename(columns={
            "data": "Data",
            "item": "Item",
            "tipo": "Tipo",
            "setor": "Setor",
            "quantidade": "Qtd.",
            "qtd_anterior": "Anterior",
            "qtd_nova": "Nova",
            "motivo": "Motivo",
            "retirado_por": "Retirado por",
        })
        st.dataframe(df_hist, use_container_width=True, hide_index=True)
        st.caption(f"{len(df_hist)} registros")
