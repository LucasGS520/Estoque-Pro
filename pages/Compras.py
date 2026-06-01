import streamlit as st
import pandas as pd
from sqlalchemy.orm import joinedload

from core.database import get_session_factory
from core.ui import setup_page, page_header, section_title, empty_state, fmt_brl
from services.compras_service import run_analysis, get_latest_snapshot

setup_page("Compras", "🛒")
page_header("Compras", subtitle="Análise de reposição e lista de itens para compra.")

SessionLocal = get_session_factory()

# ── Faixa de ação — Rodar Análise ─────────────────────────────────────────────
col_btn, col_info = st.columns([1, 3])
with col_btn:
    rodar = st.button("▶ Rodar Análise", type="primary", use_container_width=True)
with col_info:
    with SessionLocal() as session:
        snaps = get_latest_snapshot(session)
    if snaps:
        ultima = snaps[0].criado_em.strftime("%d/%m/%Y %H:%M")
        st.info(f"Última análise: **{ultima}**", icon="🕐")
    else:
        st.warning("Nenhuma análise realizada ainda.", icon="⚠️")

if rodar:
    with st.spinner("Calculando..."):
        with SessionLocal() as session:
            results, summary = run_analysis(session)
    st.success(
        f"Análise concluída: **{summary.itens_comprar}** para comprar · "
        f"**{summary.itens_zerados}** zerados · "
        f"**{summary.itens_sem_minimo}** sem mínimo definido"
    )
    st.rerun()

st.divider()

# ── Carregar resultados ───────────────────────────────────────────────────────
with SessionLocal() as session:
    snapshots = get_latest_snapshot(session)
    if snapshots:
        from core.models import Item
        item_data = {
            i.id: i
            for i in session.query(Item).options(joinedload(Item.categoria)).all()
        }

if not snapshots:
    empty_state(
        "🛒",
        "Nenhuma análise disponível",
        "Clique em Rodar Análise para gerar as recomendações de compra.",
    )
    st.stop()

# Separar por status
comprar   = [s for s in snapshots if s.status == "comprar"]
zerados   = [s for s in snapshots if s.status == "zerado"]
ok        = [s for s in snapshots if s.status == "ok"]
sem_minimo = [s for s in snapshots if s.status == "sem_minimo_definido"]

# ── KPIs rápidos ──────────────────────────────────────────────────────────────
c1, c2, c3, c4 = st.columns(4)
c1.metric("Comprar", len(comprar))
c2.metric("Zerados", len(zerados))
c3.metric("OK", len(ok))
c4.metric("Sem Mínimo", len(sem_minimo))

st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)

tab_comprar, tab_zerado, tab_ok, tab_sem_min = st.tabs(
    ["🔴 Comprar", "🟠 Zerados", "🟢 OK", "⚪ Sem Mínimo Definido"]
)


def _gerar_doc_compras(df: pd.DataFrame) -> None:
    try:
        from documents.lista_compras import gerar_lista_compras
        path = gerar_lista_compras(df)
        with open(path, "rb") as f:
            st.download_button(
                label="📄 Baixar Lista de Compras (.docx)",
                data=f.read(),
                file_name=path.name,
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
    except ImportError:
        st.info("Módulo de documentos ainda não disponível.")


def _snaps_to_df(snaps, item_data: dict) -> pd.DataFrame:
    rows = []
    for s in snaps:
        item = item_data.get(s.item_id)
        if not item:
            continue
        rows.append({
            "Item": item.nome,
            "Categoria": item.categoria.nome,
            "Atual": item.estoque_atual,
            "Mínimo": item.estoque_minimo,
            "Ideal": item.estoque_ideal,
            "Comprar": s.quantidade_recomendar,
            "Fornecedor": (s.fornecedor_sugerido.nome if s.fornecedor_sugerido else "—"),
            "Valor Est.": (fmt_brl(s.valor_estimado) if s.valor_estimado else "—"),
        })
    return pd.DataFrame(rows)


with tab_comprar:
    df_comprar = _snaps_to_df(comprar, item_data)
    if df_comprar.empty:
        empty_state("✅", "Nenhum item para comprar", "Todos os itens estão dentro dos limites.")
    else:
        st.dataframe(df_comprar, use_container_width=True, hide_index=True)
        _gerar_doc_compras(df_comprar)

with tab_zerado:
    df_zerado = _snaps_to_df(zerados, item_data)
    if df_zerado.empty:
        empty_state("✅", "Nenhum item zerado")
    else:
        st.dataframe(df_zerado, use_container_width=True, hide_index=True)

with tab_ok:
    df_ok = _snaps_to_df(ok, item_data)
    if df_ok.empty:
        empty_state("📋", "Nenhum item com status OK")
    else:
        st.dataframe(df_ok, use_container_width=True, hide_index=True)

with tab_sem_min:
    df_sem = _snaps_to_df(sem_minimo, item_data)
    if df_sem.empty:
        empty_state("✅", "Todos os itens têm limites definidos")
    else:
        st.dataframe(df_sem, use_container_width=True, hide_index=True)
        st.caption("Acesse **Estoque → Editar → Itens** para definir os valores mínimo e ideal.")
