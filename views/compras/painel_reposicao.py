"""Aba Painel de Reposição — página Compras."""
import pandas as pd
import streamlit as st

from core.ui import empty_state, fmt_brl, section_title

_STATUS_LABEL = {
    "zerado":              "Zerado",
    "abaixo_minimo":       "Abaixo do Mínimo",
    "abaixo_ideal":        "Abaixo do Ideal",
    "ok":                  "OK",
    "sem_parametro":       "Sem Parâmetro",
    "comprar":             "Abaixo do Mínimo",
    "sem_minimo_definido": "Sem Parâmetro",
    "excesso":             "OK",
}


def render(painel_lista: list, cat_nomes: list, periodo_label: str) -> None:
    """Renderiza a aba Painel de Reposição."""
    if not painel_lista:
        empty_state(
            "🛒",
            "Sem itens ativos no estoque",
            "Cadastre itens em Estoque para visualizar o painel de reposição.",
        )
        return

    zerados           = [r for r in painel_lista if r.status.value == "zerado"]
    abaixo_min        = [r for r in painel_lista if r.status.value == "abaixo_minimo"]
    abaixo_ideal_list = [r for r in painel_lista if r.status.value == "abaixo_ideal"]
    ok_list           = [r for r in painel_lista if r.status.value == "ok"]
    sem_param         = [r for r in painel_lista if r.status.value == "sem_parametro"]

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Zerados",         len(zerados))
    c2.metric("Abaixo do Mín.",  len(abaixo_min))
    c3.metric("Abaixo do Ideal", len(abaixo_ideal_list))
    c4.metric("OK",              len(ok_list))
    c5.metric("Sem Parâmetro",   len(sem_param))

    st.markdown("<div style='height:12px;'></div>", unsafe_allow_html=True)

    section_title("Filtros")
    col_busca, col_cat, col_status = st.columns([3, 2, 2])
    with col_busca:
        busca = st.text_input("Buscar item", placeholder="Digite parte do nome...", key="painel_busca")
    with col_cat:
        cat_sel = st.selectbox("Categoria", cat_nomes, key="painel_cat")
    with col_status:
        status_opcoes = {
            "Todos os alertas": None,
            "Zerado": "zerado",
            "Abaixo do Mínimo": "abaixo_minimo",
            "Abaixo do Ideal": "abaixo_ideal",
            "Sem Parâmetro": "sem_parametro",
            "OK": "ok",
        }
        status_sel = st.selectbox("Status", list(status_opcoes.keys()), key="painel_status")

    STATUS_PAINEL = {"zerado", "abaixo_minimo", "abaixo_ideal", "sem_parametro", "ok"}
    itens_painel = [r for r in painel_lista if r.status.value in STATUS_PAINEL]

    busca_lower = busca.strip().lower()
    status_code = status_opcoes[status_sel]
    if status_code:
        itens_painel = [r for r in itens_painel if r.status.value == status_code]
    if cat_sel != "Todas":
        itens_painel = [r for r in itens_painel if r.categoria == cat_sel]
    if busca_lower:
        itens_painel = [r for r in itens_painel if busca_lower in r.nome.lower()]

    if not itens_painel:
        empty_state("✅", "Nenhum item encontrado para os filtros selecionados.")
        return

    rows = []
    for r in itens_painel:
        rows.append({
            "Status":      _STATUS_LABEL.get(r.status.value, r.status.value),
            "Item":        r.nome,
            "Categoria":   r.categoria,
            "Estoque":     r.qtd_atual,
            "Mínimo":      r.estoque_minimo,
            "Ideal":       r.estoque_ideal,
            "Qtd Sugerida": r.quantidade_recomendar,
            "Fornecedor":  r.fornecedor_sugerido or "—",
            "Valor Est.":  fmt_brl(r.valor_estimado) if r.valor_estimado else "—",
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
