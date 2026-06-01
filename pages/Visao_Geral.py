import streamlit as st
import plotly.express as px
import pandas as pd

from core.database import get_session_factory
from core.engine import ItemStatus
from core.ui import setup_page, page_header, section_title, empty_state, fmt_brl, apply_plotly_theme
from services.estoque_service import get_kpis_basicos
from services.compras_service import get_latest_snapshot, run_analysis

setup_page("Visão Geral", "📊")
page_header("Visão Geral", subtitle="Indicadores gerais e alertas de estoque.")

SessionLocal = get_session_factory()

# ── KPIs de base ──────────────────────────────────────────────────────────────
with SessionLocal() as session:
    kpis = get_kpis_basicos(session)
    snapshots = get_latest_snapshot(session)

col1, col2, col3, col4 = st.columns(4)
col1.metric("Total de Itens", kpis["total_itens"])
col2.metric("Com Limites Definidos", kpis["itens_com_minimo"])
col3.metric("Sem Limites Definidos", kpis["itens_sem_minimo_definido"])

if snapshots:
    comprar = sum(1 for s in snapshots if s.status in ("comprar", "zerado"))
    valor_total = sum(s.valor_estimado or 0 for s in snapshots)
    col4.metric("Itens p/ Comprar", comprar)
    st.metric("Valor Total Estimado", fmt_brl(valor_total))
else:
    col4.metric("Itens p/ Comprar", "—")

st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)

# ── Estado vazio ──────────────────────────────────────────────────────────────
if not snapshots:
    empty_state(
        "🛒",
        "Nenhuma análise disponível",
        "Vá até Compras e clique em Rodar Análise para gerar os dados.",
    )
    st.stop()

# ── Gráfico por categoria ─────────────────────────────────────────────────────
section_title("Status por Categoria")

with SessionLocal() as session:
    from core.models import Item, Categoria
    itens_map = {
        i.id: i.categoria.nome
        for i in session.query(Item).all()
    }

rows = [
    {"categoria": itens_map.get(s.item_id, "?"), "status": s.status}
    for s in snapshots
]
df = pd.DataFrame(rows)
df_agg = df.groupby(["categoria", "status"]).size().reset_index(name="count")

status_cores = {
    "comprar":             "#E10600",
    "zerado":              "#F59E0B",
    "sem_minimo_definido": "#737373",
    "ok":                  "#16A34A",
}
status_labels = {
    "comprar":             "Comprar",
    "zerado":              "Zerado",
    "sem_minimo_definido": "Sem Mínimo",
    "ok":                  "OK",
}
df_agg["status_label"] = df_agg["status"].map(status_labels).fillna(df_agg["status"])

fig = px.bar(
    df_agg,
    x="categoria",
    y="count",
    color="status",
    color_discrete_map=status_cores,
    barmode="stack",
    labels={"count": "Qtd. Itens", "categoria": "Categoria", "status": "Status"},
    title="Distribuição de Status por Categoria",
)
apply_plotly_theme(fig)
st.plotly_chart(fig, use_container_width=True)

# ── Itens críticos ────────────────────────────────────────────────────────────
criticos = [s for s in snapshots if s.status in ("comprar", "zerado")]

st.markdown("<div style='height:4px;'></div>", unsafe_allow_html=True)
section_title(f"Itens Críticos — {len(criticos)} item(ns) para atenção")

if criticos:
    rows_crit = []
    with SessionLocal() as session:
        from core.models import Item
        for s in criticos[:20]:
            item = session.query(Item).filter_by(id=s.item_id).first()
            if item:
                rows_crit.append({
                    "Item": item.nome,
                    "Categoria": item.categoria.nome,
                    "Status": s.status,
                    "Atual": item.estoque_atual,
                    "Mínimo": item.estoque_minimo,
                    "Comprar": s.quantidade_recomendar,
                    "Fornecedor": (s.fornecedor_sugerido.nome if s.fornecedor_sugerido else "—"),
                    "Valor Est.": (fmt_brl(s.valor_estimado) if s.valor_estimado else "—"),
                })
    st.dataframe(pd.DataFrame(rows_crit), use_container_width=True, hide_index=True)
    if len(criticos) > 20:
        st.caption(f"Exibindo 20 de {len(criticos)} itens críticos — ver lista completa em **Compras**.")
else:
    st.success("Nenhum item crítico no momento.", icon="✅")
