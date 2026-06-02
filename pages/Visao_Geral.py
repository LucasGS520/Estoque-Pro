""" Dashboard de visão geral do estoque.

Monitora a situação operacional atual calculando status diretamente dos
saldos dos itens, sem depender de snapshots de análise de compras.
"""

import streamlit as st
import plotly.express as px
import pandas as pd

from core.database import get_session_factory
from core.engine import ItemRecord, ItemStatus, StockAnalyzer
from core.ui import setup_page, page_header, section_title, empty_state, apply_plotly_theme
from services.estoque_service import get_all_itens

setup_page("Visão Geral", "📊")
page_header("Visão Geral", subtitle="Indicadores gerais e alertas operacionais de estoque.")

SessionLocal = get_session_factory()

# ── Cálculo live de status ────────────────────────────────────────────────────
with SessionLocal() as session:
    itens = get_all_itens(session)

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
        estoque_minimo=i.estoque_minimo,
        estoque_ideal=i.estoque_ideal,
    )
    for i in itens
]
results = analyzer.run(records)
sumario = analyzer.summary(results)

# ── KPIs ──────────────────────────────────────────────────────────────────────
col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Total de Itens", sumario.total_itens)
col2.metric("Com Limites", sumario.total_itens - sumario.itens_sem_minimo)
col3.metric("Sem Limites", sumario.itens_sem_minimo)
col4.metric("A Comprar", sumario.itens_comprar)
col5.metric("Zerados", sumario.itens_zerados)

st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)

# ── Gráfico por categoria ─────────────────────────────────────────────────────
section_title("Status por Categoria")

_STATUS_CORES = {
    "comprar":             "#E10600",
    "zerado":              "#F59E0B",
    "sem_minimo_definido": "#9CA3AF",
    "ok":                  "#16A34A",
}
_STATUS_LABELS = {
    "comprar":             "Comprar",
    "zerado":              "Zerado",
    "sem_minimo_definido": "Sem Limite",
    "ok":                  "OK",
}

rows_chart = [{"categoria": r.categoria, "status": r.status.value} for r in results]
df_chart = pd.DataFrame(rows_chart)
df_agg = df_chart.groupby(["categoria", "status"]).size().reset_index(name="count")
df_agg["status_label"] = df_agg["status"].map(_STATUS_LABELS).fillna(df_agg["status"])

fig = px.bar(
    df_agg,
    x="categoria",
    y="count",
    color="status",
    color_discrete_map=_STATUS_CORES,
    barmode="stack",
    labels={"count": "Qtd. Itens", "categoria": "Categoria", "status": "Status"},
    title="Distribuição de Status por Categoria",
    custom_data=["status_label"],
)
fig.update_traces(hovertemplate="%{customdata[0]}: %{y}<extra></extra>")
apply_plotly_theme(fig)
st.plotly_chart(fig, use_container_width=True)

# ── Itens críticos ────────────────────────────────────────────────────────────
criticos = [r for r in results if r.status in (ItemStatus.COMPRAR, ItemStatus.ZERADO)]

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
    st.dataframe(pd.DataFrame(rows_crit), use_container_width=True, hide_index=True)
    if len(criticos) > 20:
        st.caption(f"Exibindo 20 de {len(criticos)} itens críticos — ver lista completa em **Compras**.")
    st.caption("Para fornecedores sugeridos e valores estimados, rode a análise em **Compras**.")
else:
    st.success("Nenhum item crítico no momento.", icon="✅")
