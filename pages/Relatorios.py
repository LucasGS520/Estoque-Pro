""" Tela de relatórios operacionais.

Exibe gráficos e tabelas derivados do histórico de movimentações, sem alterar
dados do banco.
"""

import calendar
import datetime

from core import tempo

import pandas as pd
import streamlit as st
import plotly.express as px

from core.auth import require_admin
from core.database import get_session_factory
from core.models import Item, Movimentacao
from core.ui import setup_page, page_header, section_title, empty_state, apply_chart_theme, chart_title, DFEB_COLORS
from documents.relatorio_categoria import gerar_relatorio_categoria
from documents.relatorio_consumo   import gerar_relatorio_consumo
from documents.relatorio_historico import gerar_relatorio_historico
from documents.relatorio_item      import gerar_relatorio_item
from documents.relatorio_setor     import gerar_relatorio_setor
from services.estoque_service import get_all_itens, get_categorias, get_setores
from services.relatorio_service import (
    consumo_e_entradas_por_mes,
    consumo_por_categoria,
    consumo_por_item,
    consumo_por_setor,
    get_kpis_consumo,
    get_resumo_categoria_periodo,
    get_resumo_setor_periodo,
    get_timeline_consumo,
    get_top_itens_consumo,
    get_top_itens_entrada,
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


def _fmt_dia(dia_str: str) -> str:
    """Converte 'YYYY-MM-DD' em 'DD/Mmm' (ex: '2025-06-15' → '15/Jun')."""
    try:
        _, mes, dia = dia_str.split("-")
        return f"{dia}/{_MESES_PTBR.get(mes, mes)}"
    except Exception:
        return dia_str

setup_page("Relatórios", "📈")
require_admin()
page_header("Relatórios", subtitle="Consumo histórico por período, categoria, setor e item.")

SessionLocal = get_session_factory()


def _opcoes_periodo() -> dict[str, tuple[datetime.date, datetime.date]]:
    """Retorna as 4 opções padrão de período como (data_inicio, data_fim)."""
    hoje = tempo.hoje()
    mes_atual_inicio  = hoje.replace(day=1)
    mes_ant_fim       = mes_atual_inicio - datetime.timedelta(days=1)
    mes_ant_inicio    = mes_ant_fim.replace(day=1)
    return {
        "Mês atual":        (mes_atual_inicio,                       hoje),
        "Mês anterior":     (mes_ant_inicio,                         mes_ant_fim),
        "Últimos 3 meses":  (hoje - datetime.timedelta(days=90),     hoje),
        "Últimos 12 meses": (hoje - datetime.timedelta(days=365),    hoje),
    }


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
    ["Consumo × Reposição", "Histórico de Movimentações", "Por Item", "Por Setor", "Por Categoria"],
    key="rel_tab", horizontal=True, label_visibility="collapsed",
)

# ── Tab: Consumo Mensal ───────────────────────────────────────────────────────
if tab_sel == "Consumo × Reposição":
    # ── Bloco 1 — Filtros (linha 1) ───────────────────────────────────────────
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

    # Granularidade: dia para períodos de 1 mês, mes para multi-mês
    gran_m = "dia" if _periodo_sel_m in ("Mês atual", "Mês anterior") else "mes"
    _fmt_eixo = _fmt_dia if gran_m == "dia" else _fmt_mes
    _label_eixo = "Dia" if gran_m == "dia" else "Mês"

    # ── Fetch de dados ────────────────────────────────────────────────────────
    with SessionLocal() as session:
        df_timeline = get_timeline_consumo(session, data_inicio_m, data_fim_m, cat_m_id, setor_m_id, granularidade=gran_m)
        kpis = get_kpis_consumo(session, data_inicio_m, data_fim_m, cat_m_id, setor_m_id)
        df_top = get_top_itens_consumo(session, data_inicio_m, data_fim_m, top_n_m, cat_m_id, setor_m_id)

    st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)

    if df_top.empty:
        empty_state("📊", "Nenhum dado disponível", "Nenhuma movimentação registrada no período.")
    else:
        # ── Bloco 2 — KPIs ────────────────────────────────────────────────────
        k1, k2, k3, k4, k5 = st.columns(5)
        k1.metric("Total consumido", f"{kpis['total_saida']:,}".replace(",", "."))
        k2.metric("Total de entradas", f"{kpis['total_entrada']:,}".replace(",", "."))
        k3.metric("Item mais consumido", kpis["item_mais_consumido"])
        k4.metric("Setor com maior consumo", kpis["setor_mais_consumiu"])
        k5.metric("Nº de Movimentações", kpis["n_movimentacoes"])

        st.markdown("<div style='height:16px;'></div>", unsafe_allow_html=True)

        # ── Bloco 3 — Gráfico Primário: Barras horizontais Top N ──────────────
        chart_title(f"Top {top_n_m} Itens Mais Consumidos — {_periodo_sel_m}")
        fig_bar = px.bar(
            df_top,
            x="total_saida",
            y="item",
            orientation="h",
            color_discrete_sequence=[DFEB_COLORS["red"]],
            labels={"total_saida": "Consumo", "item": "Item"},
            text="total_saida",
        )
        fig_bar.update_traces(textposition="outside")
        fig_bar.update_yaxes(autorange="reversed")
        apply_chart_theme(fig_bar, height=max(280, len(df_top) * 45), showlegend=False)
        st.plotly_chart(fig_bar, width='stretch')

        # ── Bloco 4 — Gráfico Secundário: Linha temporal ─────────────────────
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
                color_discrete_map={"consumo": DFEB_COLORS["red"], "reposição": DFEB_COLORS["black"]},
                labels={"mes_label": _label_eixo, "quantidade": "Quantidade", "tipo": ""},
                category_orders={"mes_label": df_timeline["mes_label"].tolist()},
            )
            fig_line.update_layout(xaxis_type="category")
            apply_chart_theme(fig_line, height=300, showlegend=True)
            st.plotly_chart(fig_line, width='stretch')

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

# ── Tab: Por Categoria ────────────────────────────────────────────────────────
elif tab_sel == "Por Categoria":
    section_title("Filtros")
    _periodo_opts_cat = _opcoes_periodo()
    _periodo_sel_cat = st.selectbox("Período", list(_periodo_opts_cat.keys()), index=0, key="cat_periodo")
    data_inicio_cat, data_fim_cat = _periodo_opts_cat[_periodo_sel_cat]

    with SessionLocal() as session:
        df_cat = consumo_por_categoria(session, data_inicio=data_inicio_cat, data_fim=data_fim_cat)

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
        st.plotly_chart(fig, width='stretch')

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

# ── Tab: Por Setor ────────────────────────────────────────────────────────────
elif tab_sel == "Por Setor":
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
        st.plotly_chart(fig, width='stretch')

        section_title("Detalhamento")
        df_exib = df_setor.rename(columns={
            "setor": "Setor",
            "total_saida": "Total Retirado",
            "num_movimentacoes": "Nº Movimentações",
        })
        st.dataframe(df_exib, width='stretch', hide_index=True)
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

# ── Tab: Por Item ─────────────────────────────────────────────────────────────
elif tab_sel == "Por Item":
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
        st.plotly_chart(fig, width='stretch')

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
        st.dataframe(df_exib, width='stretch', hide_index=True)
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

# ── Tab: Histórico de Movimentações ──────────────────────────────────────────
elif tab_sel == "Histórico de Movimentações":
    from core.models import Categoria as CategoriaModel

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
        _TIPO_OPTS = {
            "Todos": None,
            "Entrada": "entrada",
            "Saída": "saida",
        }
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
    else:
        with SessionLocal() as session:
            itens_obj = session.query(Item).all()
            itens_map = {i.id: i.nome for i in itens_obj}
            itens_cat_map = {i.id: (i.categoria.nome if i.categoria else None) for i in itens_obj}

        if "item_id" in df_hist.columns:
            df_hist.insert(1, "item", df_hist["item_id"].map(itens_map))
            df_hist.insert(2, "_cat", df_hist["item_id"].map(itens_cat_map))
            df_hist = df_hist.drop(columns=["item_id"])

        # Filtros client-side
        if cat_hist_id is not None:
            df_hist = df_hist[df_hist["_cat"] == cat_hist_sel]
        df_hist = df_hist.drop(columns=["_cat"], errors="ignore")
        if busca_item_hist.strip():
            _busca = busca_item_hist.strip().lower()
            df_hist = df_hist[df_hist["item"].str.lower().str.contains(_busca, na=False)]

        # .copy() garante DataFrame independente — evita KeyError por CoW do pandas 2.0+
        df_hist = df_hist.copy()

        if df_hist.empty:
            empty_state("📋", "Nenhuma movimentação encontrada para os filtros selecionados.")
        else:
            _TIPO_BADGE = {
                "entrada":   "<span style='background:#F4F4F5;color:#262626;padding:2px 8px;"
                             "border-radius:4px;font-size:12px;font-weight:500;'>Entrada</span>",
                "saida":     "<span style='background:#FEE2E2;color:#E10600;padding:2px 8px;"
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
