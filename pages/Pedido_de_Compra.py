""" Tela de pedido de compra para uso dos setores.

Formulário simples para que qualquer setor registre sua solicitação de materiais.
Não requer conhecimento do sistema de estoque. As solicitações ficam disponíveis
para análise na camada de Compras.
"""

import datetime

import streamlit as st

from core.database import get_session_factory
from core.schemas import SolicitacaoMaterialCreate
from core.ui import page_header, section_title, setup_page
from services.compras_service import criar_solicitacao
from services.estoque_service import get_all_itens, get_setores

setup_page("Pedido de Compra", "📝")
page_header(
    "Pedido de Compra",
    subtitle="Registre aqui sua solicitação de materiais para o setor de compras.",
)

SessionLocal = get_session_factory()

MESES_PT = {
    1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril",
    5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto",
    9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro",
}

# ── Carrega dados do catálogo ──────────────────────────────────────────────────
with SessionLocal() as _s:
    itens_cat = get_all_itens(_s)
    item_opts = {i.id: f"{i.nome}  ({i.categoria.nome})" for i in itens_cat}
    setores_list = get_setores(_s)
    setor_opts = {s.id: s.nome for s in setores_list}

hoje = datetime.date.today()
anos_disponiveis = list(range(hoje.year - 1, hoje.year + 2))

# ── Formulário ────────────────────────────────────────────────────────────────
section_title("Dados da Solicitação")

with st.form("form_pedido", clear_on_submit=True):

    # Período
    col_mes, col_ano = st.columns([2, 1])
    with col_mes:
        mes_sel = st.selectbox(
            "Mês de referência*",
            options=list(MESES_PT.keys()),
            format_func=lambda m: MESES_PT[m],
            index=hoje.month - 1,
        )
    with col_ano:
        ano_sel = st.selectbox(
            "Ano*",
            options=anos_disponiveis,
            index=anos_disponiveis.index(hoje.year),
        )

    st.markdown("<div style='height:4px;'></div>", unsafe_allow_html=True)

    # Identificação
    col_setor, col_solicitante = st.columns([1, 1])
    with col_setor:
        setor_id = st.selectbox(
            "Setor*",
            options=[None] + list(setor_opts.keys()),
            format_func=lambda k: setor_opts.get(k, "— Selecione o setor —") if k else "— Selecione o setor —",
        )
    with col_solicitante:
        solicitante = st.text_input("Seu nome*", placeholder="Nome completo do solicitante")

    st.markdown("<div style='height:4px;'></div>", unsafe_allow_html=True)

    # Item
    tipo_item = st.radio(
        "O item está no catálogo de materiais?",
        ["Sim — selecionar da lista", "Não — informar o nome manualmente"],
        horizontal=True,
    )

    if tipo_item == "Sim — selecionar da lista":
        item_id = st.selectbox(
            "Item*",
            options=list(item_opts.keys()),
            format_func=lambda k: item_opts.get(k, ""),
        )
        nome_livre = None
    else:
        item_id = None
        nome_livre = st.text_input(
            "Nome do item*",
            placeholder="Descreva o material com clareza (ex: Papel A4 500 folhas)",
        )

    st.markdown("<div style='height:4px;'></div>", unsafe_allow_html=True)

    # Quantidade e observação
    col_qtd, col_obs = st.columns([1, 2])
    with col_qtd:
        quantidade = st.number_input("Quantidade*", min_value=1, value=1, step=1)
    with col_obs:
        observacao = st.text_area(
            "Observação",
            placeholder="Justificativa, urgência, especificações adicionais...",
            height=68,
        )

    st.markdown("<div style='height:4px;'></div>", unsafe_allow_html=True)
    enviado = st.form_submit_button("Enviar Solicitação", type="primary", use_container_width=True)

# ── Processamento do envio ────────────────────────────────────────────────────
if enviado:
    erros = []
    if not setor_id:
        erros.append("Selecione o setor.")
    if not solicitante.strip():
        erros.append("Informe seu nome.")
    if tipo_item == "Não — informar o nome manualmente" and not (nome_livre or "").strip():
        erros.append("Informe o nome do item.")

    if erros:
        for e in erros:
            st.error(e)
    else:
        dados = SolicitacaoMaterialCreate(
            item_id=item_id,
            nome_item_livre=(nome_livre or "").strip() or None,
            setor_id=setor_id,
            solicitante=solicitante.strip(),
            quantidade_solicitada=int(quantidade),
            observacao=(observacao or "").strip() or None,
            periodo_referencia=datetime.date(ano_sel, mes_sel, 1),
        )
        with SessionLocal() as _s:
            criar_solicitacao(_s, dados)
        st.success(
            f"Solicitação enviada com sucesso para **{MESES_PT[mes_sel]}/{ano_sel}**. "
            "O setor de compras irá analisar sua solicitação."
        )

# ── Rodapé informativo ────────────────────────────────────────────────────────
st.markdown("<div style='height:24px;'></div>", unsafe_allow_html=True)
st.caption(
    "Campos marcados com * são obrigatórios. "
    "A solicitação não garante a compra — ela será analisada junto ao estoque disponível."
)
