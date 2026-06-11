"""Página de aprovação de orçamento — acessível pelo diretor via link direto.

Recebe o parâmetro `id` na URL (ex: /Aprovacao_Orcamento?id=1) e exibe o
orçamento para decisão: aprovar, aprovar parcialmente, solicitar revisão ou
reprovar. Sem sidebar — mesma filosofia do Solicitar.py.
"""

import streamlit as st

from core.database import get_session_factory
from core.models import ItemOrcamento as _ItemOrc, Orcamento as _Orc
from core.ui import _CSS, fmt_brl
from services.orcamento_service import (
    get_orcamento_por_id,
    registrar_decisao_diretor,
)
from sqlalchemy.orm import joinedload

# Oculta sidebar — página pública para o diretor
st.markdown(_CSS, unsafe_allow_html=True)
st.markdown(
    "<style>"
    "[data-testid='stSidebar']        { display: none !important; }"
    "[data-testid='collapsedControl'] { display: none !important; }"
    "</style>",
    unsafe_allow_html=True,
)

SessionLocal = get_session_factory()

_MESES_PT = [
    "", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
]

_STATUS_PT = {
    "ENVIADO_APROVACAO": "Aguardando aprovação",
    "APROVADO": "Aprovado",
    "APROVADO_PARCIAL": "Aprovado parcialmente",
    "DEVOLVIDO_REVISAO": "Devolvido para revisão",
    "REPROVADO": "Reprovado",
}


def _periodo_fmt(periodo) -> str:
    return f"{_MESES_PT[periodo.month]}/{periodo.year}"


# ── Leitura do parâmetro id ───────────────────────────────────────────────────
_id_param = st.query_params.get("id")

if not _id_param:
    st.markdown(
        "<div style='text-align:center;padding:64px 0;'>"
        "<div style='font-size:40px;'>🔗</div>"
        "<p style='font-size:18px;font-weight:600;margin:12px 0 6px;'>Link inválido</p>"
        "<p style='color:#737373;'>Nenhum orçamento foi especificado na URL.</p>"
        "</div>",
        unsafe_allow_html=True,
    )
    st.stop()

try:
    orc_id = int(_id_param)
except ValueError:
    st.error("Parâmetro `id` inválido.")
    st.stop()

with SessionLocal() as session:
    orc = (
        session.query(_Orc)
        .options(joinedload(_Orc.itens).joinedload(_ItemOrc.cotacoes))
        .filter(_Orc.id == orc_id)
        .first()
    )

if orc is None:
    st.error(f"Orçamento #{orc_id} não encontrado.")
    st.stop()

periodo_str = _periodo_fmt(orc.periodo_referencia)
status_str = _STATUS_PT.get(orc.status, orc.status)

# ── Cabeçalho ────────────────────────────────────────────────────────────────
st.markdown(
    f"<h2 style='margin-bottom:4px;'>Documento de Cotação para Aprovação</h2>"
    f"<p style='color:#737373;font-size:14px;margin-top:0;'>"
    f"DFeB Auto Parts · {periodo_str} · {orc.numero} v{orc.versao}"
    f"</p>",
    unsafe_allow_html=True,
)
st.divider()

# ── Informações gerais ────────────────────────────────────────────────────────
c1, c2, c3 = st.columns(3)
c1.markdown(f"**Responsável:** {orc.responsavel or '—'}")
c2.markdown(f"**Data envio:** {orc.enviado_em.strftime('%d/%m/%Y %H:%M') if orc.enviado_em else '—'}")
c3.markdown(f"**Status:** {status_str}")

st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)

# ── Resumo financeiro ─────────────────────────────────────────────────────────
itens_com_escolha = [i for i in orc.itens if i.cotacao_escolhida_id is not None]
total_bruto = 0.0
frete_total = 0.0
total_geral = 0.0
origens: set[str] = set()

for item in itens_com_escolha:
    cot = next((c for c in item.cotacoes if c.id == item.cotacao_escolhida_id), None)
    if cot:
        total_bruto += item.quantidade_orcada * cot.preco_unitario - cot.desconto + cot.outros_custos
        frete_total += cot.frete
        total_geral += cot.total_calculado
        origens.add(cot.origem)

m1, m2, m3, m4 = st.columns(4)
m1.metric("Itens", len(orc.itens))
m2.metric("Total bruto", fmt_brl(round(total_bruto, 2)))
m3.metric("Frete total", fmt_brl(round(frete_total, 2)))
m4.metric("Total geral", fmt_brl(round(total_geral, 2)))

st.divider()

# ── Tabela de itens ───────────────────────────────────────────────────────────
st.markdown("### Itens do Orçamento")

import pandas as pd

_STATUS_ITEM_PT = {
    "SEM_COTACAO": "Sem cotação",
    "COM_COTACAO": "Com cotação",
    "APROVADO_DIRETOR": "Aprovado",
    "REPROVADO_DIRETOR": "Reprovado",
}

rows_tab = []
for item in sorted(orc.itens, key=lambda i: (i.categoria_nome, i.nome_item)):
    cot_esc = next((c for c in item.cotacoes if c.id == item.cotacao_escolhida_id), None)
    rows_tab.append({
        "Item": item.nome_item,
        "Categoria": item.categoria_nome,
        "Qtd": item.quantidade_orcada,
        "Tipo": "Avulsa" if item.tipo == "AVULSA" else "Estoque",
        "Fornecedor/Origem": cot_esc.origem if cot_esc else "—",
        "Unitário": fmt_brl(cot_esc.preco_unitario) if cot_esc else "—",
        "Total": fmt_brl(cot_esc.total_calculado) if cot_esc else "—",
        "Frete": fmt_brl(cot_esc.frete) if cot_esc and cot_esc.frete else "—",
    })

st.dataframe(pd.DataFrame(rows_tab), use_container_width=True, hide_index=True)

# Alternativas por item (expandível)
with st.expander("Ver cotações alternativas por item"):
    for item in sorted(orc.itens, key=lambda i: (i.categoria_nome, i.nome_item)):
        if len(item.cotacoes) <= 1:
            continue
        st.markdown(f"**{item.nome_item}** — Qtd: {item.quantidade_orcada}")
        cotacoes_ord = sorted(item.cotacoes, key=lambda c: c.total_calculado)
        for idx, cot in enumerate(cotacoes_ord[:3], 1):
            escolhida = " ← escolhida" if cot.id == item.cotacao_escolhida_id else ""
            st.markdown(
                f"{idx}. **{cot.origem}** — {fmt_brl(cot.preco_unitario)} unit. "
                f"— Total: **{fmt_brl(cot.total_calculado)}**"
                + (f" (frete: {fmt_brl(cot.frete)})" if cot.frete else "")
                + escolhida
            )

st.divider()

# ── Formulário de decisão (só para ENVIADO_APROVACAO) ────────────────────────
if orc.status != "ENVIADO_APROVACAO":
    # Já decidido — mostra resultado
    bg_map = {
        "APROVADO": "#dcfce7", "APROVADO_PARCIAL": "#dcfce7",
        "DEVOLVIDO_REVISAO": "#fef3c7", "REPROVADO": "#fee2e2",
    }
    fg_map = {
        "APROVADO": "#16a34a", "APROVADO_PARCIAL": "#16a34a",
        "DEVOLVIDO_REVISAO": "#b45309", "REPROVADO": "#dc2626",
    }
    bg = bg_map.get(orc.status, "#f4f4f5")
    fg = fg_map.get(orc.status, "#737373")
    st.markdown(
        f"<div style='background:{bg};border-radius:8px;padding:16px 20px;'>"
        f"<p style='color:{fg};font-size:16px;font-weight:700;margin:0 0 6px;'>Decisão registrada: {status_str}</p>"
        + (f"<p style='margin:0;color:#444;'>Observação: {orc.observacao_diretor}</p>" if orc.observacao_diretor else "")
        + (f"<p style='margin:4px 0 0;color:#737373;font-size:12px;'>Em: {orc.decidido_em.strftime('%d/%m/%Y %H:%M')}</p>" if orc.decidido_em else "")
        + "</div>",
        unsafe_allow_html=True,
    )
    st.stop()

# Formulário de decisão
st.markdown("### Decisão")

decisao_opcoes = {
    "Aprovar orçamento completo": "APROVADO",
    "Aprovar parcialmente (reprovar itens selecionados)": "APROVADO_PARCIAL",
    "Solicitar revisão de cotações": "DEVOLVIDO_REVISAO",
    "Reprovar orçamento inteiro": "REPROVADO",
}

decisao_label = st.radio(
    "Decisão",
    list(decisao_opcoes.keys()),
    key="dir_decisao",
    label_visibility="collapsed",
)
decisao_val = decisao_opcoes[decisao_label]

itens_reprovados_ids: list[int] = []

if decisao_val == "APROVADO_PARCIAL":
    st.markdown("**Selecione os itens a reprovar:**")
    for item in sorted(orc.itens, key=lambda i: (i.categoria_nome, i.nome_item)):
        if st.checkbox(
            f"{item.nome_item} ({item.categoria_nome}) — Qtd {item.quantidade_orcada}",
            key=f"repr_{item.id}",
        ):
            itens_reprovados_ids.append(item.id)

obs_dir = st.text_area(
    "Observação (opcional)",
    placeholder="Motivo da decisão, itens com ressalvas, etc.",
    key="dir_obs",
)

col_btn, _ = st.columns([2, 3])
with col_btn:
    if st.button("Registrar decisão", type="primary", use_container_width=True):
        if decisao_val == "APROVADO_PARCIAL" and not itens_reprovados_ids:
            st.error("Selecione pelo menos um item a reprovar para aprovação parcial.", icon="⚠️")
        else:
            try:
                with SessionLocal() as session:
                    registrar_decisao_diretor(
                        session,
                        orcamento_id=orc_id,
                        decisao=decisao_val,
                        observacao_diretor=obs_dir.strip() if obs_dir.strip() else None,
                        itens_reprovados=itens_reprovados_ids if itens_reprovados_ids else None,
                    )
                st.success("Decisão registrada com sucesso.")
                st.rerun()
            except ValueError as e:
                st.error(str(e), icon="⚠️")
