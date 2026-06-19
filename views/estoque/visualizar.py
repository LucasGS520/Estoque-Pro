"""Aba Visualizar — página Estoque."""
import pandas as pd
import streamlit as st

from core.database import get_session_factory
from core.ui import colorir_linhas_status, section_title
from services import estoque_service


def render() -> None:
    """Renderiza a aba Visualizar."""
    SessionLocal = get_session_factory()

    with SessionLocal() as session:
        categorias = estoque_service.get_categorias(session)
        cat_opcoes = {"Todas": None} | {c.nome: c.id for c in categorias}

    section_title("Filtros")
    col1, col2 = st.columns([3, 2])
    with col1:
        busca = st.text_input("Buscar por nome", placeholder="Digite parte do nome...")
    with col2:
        cat_sel = st.selectbox("Filtrar por categoria", list(cat_opcoes.keys()))

    with SessionLocal() as session:
        master_rows = estoque_service.get_tabela_mestre(
            session, categoria_id=cat_opcoes[cat_sel]
        )

    busca_lower = busca.strip().lower()
    filtradas = [
        r for r in master_rows
        if not busca_lower or busca_lower in r["item"].lower()
    ]

    _STATUS_DISPLAY = {
        "zerado":        "Zerado",
        "abaixo_minimo": "Abaixo do Mínimo",
        "abaixo_ideal":  "Abaixo do Ideal",
        "sem_parametro": "Sem Parâmetro",
        "ok":            "OK",
    }
    _STATUS_SORT = {"zerado": 0, "abaixo_minimo": 1, "abaixo_ideal": 2, "ok": 3, "sem_parametro": 4}

    df = pd.DataFrame([
        {
            "ID": r["id"],
            "Categoria": r["categoria"],
            "Item": r["item"],
            "Und.": r["unidade"],
            "Status": _STATUS_DISPLAY.get(r["status"], r["status"]),
            "Atual": r["atual"],
            "Mínimo": r["minimo"],
            "Ideal": r["ideal"],
            "Ult. Movimentação": (
                r["ultima_mov_data"].strftime("%d/%m/%Y %H:%M")
                if r["ultima_mov_data"] else "-"
            ),
            "Tipo Mov.": (
                "↓ Entrada" if r["ultima_mov_tipo"] == "entrada"
                else "↑ Saída" if r["ultima_mov_tipo"] == "saida"
                else "-"
            ),
            "Setor": r["ultima_mov_setor"] or "" if r["ultima_mov_tipo"] == "saida" else "",
            "Qtd. Mov.": str(r["ultima_mov_quantidade"]) if r["ultima_mov_quantidade"] is not None else "",
            "Fornecedor(es)": r["fornecedores"],
            "Obs.": r["observacoes"],
            "_sort": _STATUS_SORT.get(r["status"], 99),
        }
        for r in filtradas
    ])
    df = df.sort_values("_sort").drop(columns=["_sort"]).reset_index(drop=True)
    styled = df.style.apply(
        lambda row: colorir_linhas_status(row, campo="Status"), axis=1
    )
    st.dataframe(styled, use_container_width=True, hide_index=True)
    total = len(master_rows)
    label = f"{len(filtradas)} itens exibidos"
    if len(filtradas) < total:
        label += f" (de {total} no total)"
    st.caption(label)
