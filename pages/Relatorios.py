""" Tela de relatórios operacionais.

Exibe gráficos e tabelas derivados do histórico de movimentações, sem alterar
dados do banco.
"""

import streamlit as st
import plotly.express as px

from core.database import get_session_factory
from core.models import Item
from core.ui import setup_page, page_header, section_title, empty_state, apply_chart_theme, chart_title, DFEB_COLORS
from services.estoque_service import get_setores
from services.relatorio_service import (
    consumo_e_entradas_por_mes,
    consumo_por_categoria,
    consumo_por_item,
    consumo_por_setor,
    historico_movimentacoes,
)

# Meses abreviados pt-BR para formatar eixo X dos gráficos temporais
_MESES_PTBR = {
    "01": "Jan", "02": "Fev", "03": "Mar", "04": "Abr",
    "05": "Mai", "06": "Jun", "07": "Jul", "08": "Ago",
    "09": "Set", "10": "Out", "11": "Nov", "12": "Dez",
}

def _fmt_mes(mes_str: str) -> str:
    """Converte 'YYYY-MM' em 'Mmm/AA' (ex: '2025-06' → 'Jun/25')."""
    try:
        ano, mes = mes_str.split("-")
        return f"{_MESES_PTBR.get(mes, mes)}/{ano[2:]}"
    except Exception:
        return mes_str

setup_page("Relatórios", "📈")
page_header("Relatórios", subtitle="Consumo histórico por período, categoria, setor e item.")

SessionLocal = get_session_factory()

st.markdown("""
<style>
[data-testid="stRadio"] [role="radiogroup"] {
    display: flex !important;
    flex-direction: row !important;
    gap: 0 !important;
    flex-wrap: nowrap !important;
    border-bottom: 1px solid rgba(49, 51, 63, 0.2) !important;
    padding-bottom: 0 !important;
    margin-bottom: 0.75rem !important;
}
[data-testid="stRadio"] [role="radiogroup"] > label {
    display: flex !important;
    align-items: center !important;
    padding: 0.4rem 1.1rem 0.55rem 1.1rem !important;
    margin: 0 0 -1px 0 !important;
    border: none !important;
    border-bottom: 2px solid transparent !important;
    background: transparent !important;
    cursor: pointer !important;
    color: rgba(49, 51, 63, 0.6) !important;
    font-size: 0.875rem !important;
    font-weight: 400 !important;
    white-space: nowrap !important;
    transition: color 0.15s !important;
}
[data-testid="stRadio"] [role="radiogroup"] > label [data-baseweb="radio"],
[data-testid="stRadio"] [role="radiogroup"] > label input[type="radio"] {
    display: none !important;
}
[data-testid="stRadio"] [role="radiogroup"] > label:has(input:checked) {
    border-bottom: 2px solid rgb(255, 75, 75) !important;
    color: rgb(255, 75, 75) !important;
    font-weight: 600 !important;
}
[data-testid="stRadio"] [role="radiogroup"] > label:hover {
    color: rgba(49, 51, 63, 0.85) !important;
}
</style>
""", unsafe_allow_html=True)

tab_sel = st.radio(
    "Navegação",
    ["Consumo Mensal", "Por Categoria", "Por Setor", "Por Item", "Histórico de Movimentações"],
    key="rel_tab", horizontal=True, label_visibility="collapsed",
)

# ── Tab: Consumo Mensal ───────────────────────────────────────────────────────
if tab_sel == "Consumo Mensal":
    section_title("Filtros")
    periodo_mensal = st.selectbox(
        "Período",
        options=[3, 6, 12],
        format_func=lambda m: f"Últimos {m} meses",
        index=1,
        key="mensal_periodo",
    )

    with SessionLocal() as session:
        df_consol = consumo_e_entradas_por_mes(session, meses=periodo_mensal)

    if df_consol.empty:
        empty_state("📊", "Nenhum dado disponível", "Nenhuma movimentação registrada no período.")
    else:
        df_consol["mes_label"] = df_consol["mes"].apply(_fmt_mes)

        # Gráfico 1 — Barras agrupadas: consumo x entradas
        chart_title("Consumo mensal — visão consolidada")
        df_bar = df_consol.melt(
            id_vars="mes_label",
            value_vars=["total_saida", "total_entrada"],
            var_name="tipo",
            value_name="quantidade",
        )
        df_bar["tipo"] = df_bar["tipo"].map({"total_saida": "Consumo", "total_entrada": "Entradas"})
        fig_bar = px.bar(
            df_bar,
            x="mes_label",
            y="quantidade",
            color="tipo",
            barmode="group",
            color_discrete_map={"Consumo": DFEB_COLORS["red"], "Entradas": DFEB_COLORS["black"]},
            labels={"mes_label": "Mês", "quantidade": "Quantidade", "tipo": ""},
            category_orders={"mes_label": df_consol["mes_label"].tolist()},
        )
        fig_bar.update_layout(xaxis_type="category")
        apply_chart_theme(fig_bar, height=300, showlegend=True)
        st.plotly_chart(fig_bar, use_container_width=True)

        # Gráfico 2 — Linhas: tendência consumo x entradas (apenas com ≥ 2 meses)
        st.markdown("<div style='height:16px;'></div>", unsafe_allow_html=True)
        if len(df_consol) >= 2:
            chart_title("Consumo × Entradas — tendência")
            df_line = df_consol.melt(
                id_vars="mes_label",
                value_vars=["total_saida", "total_entrada"],
                var_name="tipo",
                value_name="quantidade",
            )
            df_line["tipo"] = df_line["tipo"].map({"total_saida": "Consumo", "total_entrada": "Entradas"})
            fig_line = px.line(
                df_line,
                x="mes_label",
                y="quantidade",
                color="tipo",
                markers=True,
                color_discrete_map={"Consumo": DFEB_COLORS["red"], "Entradas": DFEB_COLORS["black"]},
                labels={"mes_label": "Mês", "quantidade": "Quantidade", "tipo": ""},
                category_orders={"mes_label": df_consol["mes_label"].tolist()},
            )
            fig_line.update_layout(xaxis_type="category")
            apply_chart_theme(fig_line, height=260, showlegend=True)
            st.plotly_chart(fig_line, use_container_width=True)
        else:
            st.info("Dados de apenas 1 mês disponíveis — gráfico de tendência requer pelo menos 2 meses.")

# ── Tab: Por Categoria ────────────────────────────────────────────────────────
elif tab_sel == "Por Categoria":
    section_title("Filtros")
    _PERIODO_CAT_OPTS = {"Últimos 3 meses": 3, "Últimos 6 meses": 6, "Últimos 12 meses": 12, "Todo histórico": None}
    periodo_cat_label = st.selectbox("Período", list(_PERIODO_CAT_OPTS.keys()), index=1, key="cat_periodo")
    periodo_cat = _PERIODO_CAT_OPTS[periodo_cat_label]

    with SessionLocal() as session:
        df_cat = consumo_por_categoria(session, meses=periodo_cat)

    if df_cat.empty:
        empty_state("📊", "Nenhum dado disponível", "Nenhuma movimentação de saída registrada no período.")
    else:
        n_cats = len(df_cat)
        # Orientação auto: vertical ≤ 6 categorias, horizontal se mais
        if n_cats <= 6:
            chart_title("Consumo por categoria")
            fig = px.bar(
                df_cat,
                x="categoria",
                y="total_saida",
                text="total_saida",
                labels={"categoria": "Categoria", "total_saida": "Qtd. Consumida"},
            )
            fig.update_traces(marker_color=DFEB_COLORS["red"], textposition="outside")
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
            fig.update_traces(marker_color=DFEB_COLORS["red"], textposition="outside")
            fig.update_layout(yaxis={"categoryorder": "total ascending"})
            apply_chart_theme(fig, height=max(320, n_cats * 36))
        fig.update_layout(coloraxis_showscale=False)
        st.plotly_chart(fig, use_container_width=True)

# ── Tab: Por Setor ────────────────────────────────────────────────────────────
elif tab_sel == "Por Setor":
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
        # KPIs acima do gráfico
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

        # Coloração semântica: top setor = vermelho, "Sem setor" = laranja, demais = preto
        setor_top = df_setor.iloc[0]["setor"] if len(df_setor) > 0 else None
        bar_colors = []
        for _, row in df_setor.sort_values("total_saida").iterrows():
            if row["setor"] == "Sem setor":
                bar_colors.append(DFEB_COLORS["orange"])
            elif row["setor"] == setor_top:
                bar_colors.append(DFEB_COLORS["red"])
            else:
                bar_colors.append(DFEB_COLORS["black"])

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
elif tab_sel == "Por Item":
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
        top_n = st.selectbox("Exibir top", [10, 20], index=1, key="item_top_n")
        top_df = df_item.head(top_n)

        # 1ª barra (maior consumo) = vermelho; demais = preto
        item_top = top_df.iloc[0]["item"] if len(top_df) > 0 else None
        bar_colors_item = [
            DFEB_COLORS["red"] if row["item"] == item_top else DFEB_COLORS["black"]
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
        st.plotly_chart(fig, use_container_width=True)

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

# ── Tab: Histórico de Movimentações ──────────────────────────────────────────
elif tab_sel == "Histórico de Movimentações":
    from core.models import Categoria as CategoriaModel

    section_title("Filtros")
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        filtro_tipo = st.selectbox(
            "Tipo",
            ["Todos", "entrada", "saida"],
            format_func=lambda t: {"Todos": "Todos", "entrada": "Entrada", "saida": "Saída"}.get(t, t),
            key="hist_tipo",
        )
    with col2:
        _PERIODO_HIST_OPTS = {"Últimos 30 dias": 1, "Últimos 3 meses": 3, "Últimos 6 meses": 6, "Todo histórico": None}
        periodo_hist_label = st.selectbox("Período", list(_PERIODO_HIST_OPTS.keys()), index=3, key="hist_periodo")
        periodo_hist = _PERIODO_HIST_OPTS[periodo_hist_label]
    with col3:
        with SessionLocal() as session:
            cats_hist = session.query(CategoriaModel).all()
        cat_opcoes_hist = {"Todas as categorias": None} | {c.nome: c.id for c in cats_hist}
        cat_hist_sel = st.selectbox("Categoria", list(cat_opcoes_hist.keys()), key="hist_cat")
        cat_hist_id = cat_opcoes_hist[cat_hist_sel]
    with col4:
        limite = st.number_input("Limite de registros", min_value=10, max_value=1000, value=100)

    tipo_filtro = None if filtro_tipo == "Todos" else filtro_tipo

    with SessionLocal() as session:
        df_hist = historico_movimentacoes(session, tipo=tipo_filtro, limit=limite)

    if df_hist.empty:
        empty_state("📋", "Nenhuma movimentação encontrada")
    else:
        with SessionLocal() as session:
            itens_obj = session.query(Item).all()
            itens_map = {i.id: i.nome for i in itens_obj}
            itens_cat_map = {i.id: (i.categoria.nome if i.categoria else None) for i in itens_obj}

        if "item_id" in df_hist.columns:
            df_hist.insert(1, "item", df_hist["item_id"].map(itens_map))
            df_hist.insert(2, "_cat", df_hist["item_id"].map(itens_cat_map))
            df_hist = df_hist.drop(columns=["item_id"])

        # Filtro por categoria (client-side após fetch)
        if cat_hist_id is not None:
            cat_nome = cat_hist_sel
            df_hist = df_hist[df_hist["_cat"] == cat_nome]

        # Filtro por período (client-side)
        if periodo_hist is not None:
            import datetime as _dt
            corte = _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None) - _dt.timedelta(days=periodo_hist * 30)
            try:
                df_hist = df_hist[
                    df_hist["data"].apply(
                        lambda d: _dt.datetime.strptime(d, "%d/%m/%Y %H:%M") >= corte
                    )
                ]
            except Exception:
                pass

        # .copy() garante DataFrame independente — evita KeyError por CoW do pandas 2.0+
        df_hist = df_hist.drop(columns=["_cat"], errors="ignore").copy()

        if df_hist.empty:
            empty_state("📋", "Nenhuma movimentação encontrada para os filtros selecionados.")
        else:
            # Badge HTML para coluna Tipo
            _TIPO_BADGE = {
                "entrada": "<span style='background:#F4F4F5;color:#262626;padding:2px 8px;"
                           "border-radius:4px;font-size:12px;font-weight:500;'>Entrada</span>",
                "saida":   "<span style='background:#FEE2E2;color:#E10600;padding:2px 8px;"
                           "border-radius:4px;font-size:12px;font-weight:500;'>Saída</span>",
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
