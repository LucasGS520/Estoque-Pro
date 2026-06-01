import datetime

import streamlit as st
import pandas as pd

from core.database import get_session_factory
from core.ui import setup_page, page_header, section_title, empty_state, fmt_brl
from services.compras_service import get_latest_snapshot, run_analysis
from services.orcamento_service import consolidar_orcamento
from services.fornecedor_service import get_all_fornecedores, add_preco
from core.models import Item

setup_page("Orçamentos", "💰")
page_header("Orçamentos", subtitle="Estimativa de valor por fornecedor com base na análise de compras.")

SessionLocal = get_session_factory()

tab_orcamento, tab_cotacao = st.tabs(["Orçamento Atual", "Cadastrar Cotação"])

# ── Tab 1: Orçamento ──────────────────────────────────────────────────────────
with tab_orcamento:
    with SessionLocal() as session:
        snapshots = get_latest_snapshot(session)

    if not snapshots:
        empty_state(
            "📊",
            "Nenhuma análise disponível",
            "Vá até Compras e clique em Rodar Análise para gerar os dados.",
        )
        st.stop()

    with SessionLocal() as session:
        results_raw, _ = run_analysis(session)
        orcamento = consolidar_orcamento(session, results_raw)

    # KPIs
    c1, c2, c3 = st.columns(3)
    c1.metric("Itens com preço", len(orcamento.itens_com_preco))
    c2.metric("Itens sem preço", len(orcamento.itens_sem_preco))
    c3.metric("Total Estimado", fmt_brl(orcamento.total_estimado))

    st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)

    # Tabela com preço
    if orcamento.itens_com_preco:
        section_title("Itens com Cotação")
        rows = [
            {
                "Item": i.nome,
                "Categoria": i.categoria,
                "Qtd": i.quantidade,
                "Preço Unit.": fmt_brl(i.preco_unitario),
                "Total": fmt_brl(i.total),
                "Fornecedor": i.fornecedor,
                "Validade Cotação": i.validade_cotacao,
            }
            for i in orcamento.itens_com_preco
        ]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    # Por fornecedor
    if orcamento.por_fornecedor:
        section_title("Subtotal por Fornecedor")
        rows_forn = [
            {"Fornecedor": k, "Total": fmt_brl(v)}
            for k, v in orcamento.por_fornecedor.items()
        ]
        st.dataframe(pd.DataFrame(rows_forn), use_container_width=True, hide_index=True)

    # Sem preço
    if orcamento.itens_sem_preco:
        st.markdown("<div style='height:4px;'></div>", unsafe_allow_html=True)
        section_title(f"Itens sem Cotação — {len(orcamento.itens_sem_preco)} item(ns)")
        st.warning(
            f"{len(orcamento.itens_sem_preco)} item(ns) sem preço registrado não entram no total estimado.",
            icon="⚠️",
        )
        rows_sp = [
            {"Item": i.nome, "Categoria": i.categoria, "Qtd": i.quantidade}
            for i in orcamento.itens_sem_preco
        ]
        st.dataframe(pd.DataFrame(rows_sp), use_container_width=True, hide_index=True)
        st.caption("Cadastre cotações na aba **Cadastrar Cotação**.")

    # Download
    if orcamento.itens_com_preco:
        st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)
        try:
            from documents.orcamento import gerar_orcamento
            path = gerar_orcamento(orcamento)
            with open(path, "rb") as f:
                st.download_button(
                    "📄 Baixar Orçamento (.docx)",
                    data=f.read(),
                    file_name=path.name,
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
        except ImportError:
            pass

# ── Tab 2: Cadastrar Cotação ──────────────────────────────────────────────────
with tab_cotacao:
    section_title("Cadastrar cotação de preço")
    st.info("Preencha o formulário para registrar o preço de um item para um fornecedor.", icon="ℹ️")

    with SessionLocal() as session:
        fornecedores = get_all_fornecedores(session)
        forn_opcoes = {f.nome: f.id for f in fornecedores}
        from core.models import Categoria
        cats = session.query(Categoria).order_by(Categoria.nome).all()
        cat_opcoes = {c.nome: c.id for c in cats}

    col1, col2 = st.columns(2)
    with col1:
        cat_cot = st.selectbox("Categoria", list(cat_opcoes.keys()), key="cot_cat")
    with col2:
        forn_cot = st.selectbox("Fornecedor", list(forn_opcoes.keys()), key="cot_forn")

    with SessionLocal() as session:
        itens_cot = session.query(Item).filter_by(
            categoria_id=cat_opcoes[cat_cot], ativo=True
        ).order_by(Item.nome).all()
        item_opcoes_cot = {i.nome: i.id for i in itens_cot}

    with st.form("form_cotacao"):
        item_cot = st.selectbox("Item", list(item_opcoes_cot.keys()))
        col1, col2, col3 = st.columns(3)
        with col1:
            preco_cot = st.number_input("Preço Unitário (R$)", min_value=0.01, format="%.2f")
        with col2:
            data_cot = st.date_input("Data da Cotação", value=datetime.date.today())
        with col3:
            validade_cot = st.number_input("Validade (dias)", min_value=1, value=30)
        submit_cot = st.form_submit_button("Salvar Cotação", type="primary", use_container_width=True)

    if submit_cot:
        with SessionLocal() as session:
            add_preco(
                session,
                item_opcoes_cot[item_cot],
                forn_opcoes[forn_cot],
                preco_cot,
                data_cot,
                validade_cot,
            )
        st.success(f"Cotação salva: **{item_cot}** — {fmt_brl(preco_cot)} ({forn_cot})")
        st.rerun()
