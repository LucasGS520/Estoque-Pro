""" Dashboard de visão geral do estoque.

Monitora a situação operacional atual calculando status diretamente dos
saldos dos itens, sem depender de snapshots de análise de compras.
"""

import streamlit as st
import plotly.express as px
import pandas as pd

from core.database import get_session_factory
from core.engine import ItemRecord, ItemStatus, StockAnalyzer
from core.ui import colorir_linhas_status, setup_page, page_header, section_title, empty_state, apply_chart_theme, chart_title
from services.compras_service import get_count_pedidos_sem_triagem
from services.estoque_service import get_all_itens
from services.orcamento_service import get_count_orcamentos_aguardando

setup_page("Visão Geral", "📊")
page_header("Visão Geral", subtitle="Indicadores gerais e alertas operacionais de estoque.")

SessionLocal = get_session_factory()

# ── Cálculo live de status ────────────────────────────────────────────────────
with SessionLocal() as session:
    itens = get_all_itens(session)
    count_solicitacoes = get_count_pedidos_sem_triagem(session)
    count_orcamentos = get_count_orcamentos_aguardando(session)

if not itens:
    empty_state("📦", "Nenhum item cadastrado", "Cadastre itens na aba Estoque para começar.")
    st.stop()

analyzer = StockAnalyzer()
records = [
    ItemRecord(
        item_id=i.id,
        nome=i.nome,
        categoria=i.categoria.nome,
        qtd_atual=i.estoque_atual,
        estoque_minimo=i.estoque_minimo_vigente,
        estoque_ideal=i.estoque_ideal_vigente,
    )
    for i in itens
]
results = analyzer.run_puro(records)
sumario = analyzer.summary(results)

# ── KPIs ──────────────────────────────────────────────────────────────────────
col1, col2, col3, col4 = st.columns(4)
col1.metric("Itens Zerados", sumario.itens_zerados)
col2.metric("Abaixo do Mínimo", sumario.itens_abaixo_minimo)
col3.metric("Solicitações Pendentes", count_solicitacoes, help="Pedidos de setores no ciclo aberto aguardando análise em Compras.")
col4.metric("Orçamentos Aguardando", count_orcamentos, help="Orçamentos enviados para aprovação do diretor ou devolvidos para revisão.")

st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)

# ── Gráfico por categoria ─────────────────────────────────────────────────────

_STATUS_LABELS = {
    "zerado":              "Zerado",
    "abaixo_minimo":       "Abaixo do Mínimo",
    "abaixo_ideal":        "Abaixo do Ideal",
    "ok":                  "OK",
    "sem_parametro":       "Sem Parâmetro",
    # aliases legados
    "comprar":             "Abaixo do Mínimo",
    "sem_minimo_definido": "Sem Parâmetro",
}
# Mapeamento por label (não enum) para evitar valores técnicos na legenda
_STATUS_CORES_LABEL = {
    "Zerado":           "#E10600",
    "Abaixo do Mínimo": "#F59E0B",
    "Abaixo do Ideal":  "#FCD34D",
    "Sem Parâmetro":    "#9CA3AF",
    "OK":               "#16A34A",
}
_STATUS_ORDER = ["Zerado", "Abaixo do Mínimo", "Abaixo do Ideal", "OK", "Sem Parâmetro"]

rows_chart = [{"categoria": r.categoria, "status": r.status.value} for r in results]
df_chart = pd.DataFrame(rows_chart)
df_agg = df_chart.groupby(["categoria", "status"]).size().reset_index(name="count")
df_agg["status_label"] = df_agg["status"].map(_STATUS_LABELS).fillna(df_agg["status"])

chart_title("Distribuição de Status por Categoria")
fig = px.bar(
    df_agg,
    x="categoria",
    y="count",
    color="status_label",
    color_discrete_map=_STATUS_CORES_LABEL,
    category_orders={"status_label": _STATUS_ORDER},
    barmode="stack",
    labels={"count": "Qtd. Itens", "categoria": "Categoria", "status_label": "Status"},
)
fig.update_traces(hovertemplate="<b>%{x}</b><br>%{fullData.name}: %{y}<extra></extra>")
apply_chart_theme(fig, height=320, showlegend=True)
st.plotly_chart(fig, width='stretch')

# ── Itens críticos ────────────────────────────────────────────────────────────
criticos = [r for r in results if r.status in (
    ItemStatus.ZERADO, ItemStatus.ABAIXO_MINIMO, ItemStatus.ABAIXO_IDEAL
)]

st.markdown("<div style='height:4px;'></div>", unsafe_allow_html=True)
section_title(f"Itens Críticos — {len(criticos)} item(ns) para atenção")

if criticos:
    rows_crit = [
        {
            "Item": r.nome,
            "Categoria": r.categoria,
            "Status": _STATUS_LABELS.get(r.status.value, r.status.value),
            "Atual": r.qtd_atual,
            "Mínimo": r.estoque_minimo,
            "Comprar": r.quantidade_recomendar,
        }
        for r in criticos[:20]
    ]
    df_crit = pd.DataFrame(rows_crit)
    styled_crit = df_crit.style.apply(
        lambda row: colorir_linhas_status(row, campo="Status"), axis=1
    )
    st.dataframe(styled_crit, width='stretch', hide_index=True)
    if len(criticos) > 20:
        st.caption(f"Exibindo 20 de {len(criticos)} itens críticos — ver lista completa em **Compras**.")
    st.caption("Para fornecedores sugeridos e valores estimados, rode a análise em **Compras**.")
else:
    st.success("Nenhum item crítico no momento.", icon="✅")
