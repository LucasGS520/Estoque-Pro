"""Página de aprovação de orçamento — acessível pelo diretor via link direto.

Recebe o parâmetro `token` na URL (ex: /Aprovacao_Orcamento?token=...).
Sem sidebar — mesma filosofia do Solicitar.py.
"""

import base64

import pandas as pd
import streamlit as st
from sqlalchemy.orm import joinedload

from core.database import get_session_factory
from core.models import ItemOrcamento as _ItemOrc, Orcamento as _Orc
from core.ui import _CSS, _LOGO, fmt_brl
from services.orcamento_service import get_orcamento_por_token, registrar_decisao_diretor
import services.push_service as push_service

# ── CSS + sidebar oculta ──────────────────────────────────────────────────────
st.markdown(_CSS, unsafe_allow_html=True)
st.markdown(
    "<style>"
    "[data-testid='stSidebar']        { display: none !important; }"
    "[data-testid='collapsedControl'] { display: none !important; }"
    "</style>",
    unsafe_allow_html=True,
)

SessionLocal = get_session_factory()

from core.i18n import MESES_PT_LISTA as _MESES_PT

_STATUS_PT = {
    "ENVIADO_APROVACAO": "Aguardando aprovação",
    "APROVADO":          "Aprovado",
    "APROVADO_PARCIAL":  "Aprovado parcialmente",
    "DEVOLVIDO_REVISAO": "Devolvido para revisão",
    "REPROVADO":         "Reprovado",
}

_STATUS_ITEM = {
    "APROVADO_DIRETOR":  ("✅ Aprovado",          "#16a34a"),
    "REPROVADO_DIRETOR": ("❌ Reprovado",          "#dc2626"),
    "REVISAO_DIRETOR":   ("🔄 Revisão solicitada", "#b45309"),
    "COM_COTACAO":       ("—",                    "#737373"),
    "SEM_COTACAO":       ("—",                    "#737373"),
}

_DEC_ITEM = ["Aprovar", "Reprovar", "Revisar cotações"]


def _periodo_fmt(periodo) -> str:
    return f"{_MESES_PT[periodo.month]}/{periodo.year}"


def _logo_b64() -> str | None:
    if _LOGO.exists():
        with open(_LOGO, "rb") as f:
            return base64.b64encode(f.read()).decode()
    return None


# ── Token gate ────────────────────────────────────────────────────────────────
_token_param = st.query_params.get("token")

if not _token_param:
    st.markdown(
        "<div style='text-align:center;padding:64px 0;'>"
        "<div style='font-size:40px;'>🔗</div>"
        "<p style='font-size:18px;font-weight:600;margin:12px 0 6px;'>Link inválido</p>"
        "<p style='color:#737373;'>Este link não é válido ou já expirou.</p>"
        "</div>",
        unsafe_allow_html=True,
    )
    st.stop()

with SessionLocal() as _s:
    orc = get_orcamento_por_token(_s, _token_param)

if orc is None:
    st.markdown(
        "<div style='text-align:center;padding:64px 0;'>"
        "<div style='font-size:40px;'>🔗</div>"
        "<p style='font-size:18px;font-weight:600;margin:12px 0 6px;'>Link inválido</p>"
        "<p style='color:#737373;'>Este link não é válido ou já expirou.</p>"
        "</div>",
        unsafe_allow_html=True,
    )
    st.stop()

# Carregar itens aprovados para contexto read-only do diretor.
# Prioridade 1: itens APROVADO_DIRETOR da versão atual (path DEVOLVIDO_REVISAO).
# Prioridade 2: itens aprovados da versão anterior (path REVISAR, onde aprovados ficam na versão anterior).
_itens_aprov_ctx: list = []
_fonte_versao_ctx: str = ""
_itens_aprov_ctx = [i for i in orc.itens if i.status_item == "APROVADO_DIRETOR"]
if _itens_aprov_ctx:
    _fonte_versao_ctx = "mantidos desta versão"
elif orc.versao > 1:
    with SessionLocal() as _sp:
        _orc_prev = (
            _sp.query(_Orc)
            .options(joinedload(_Orc.itens))
            .filter(_Orc.numero == orc.numero, _Orc.versao == orc.versao - 1)
            .first()
        )
        if _orc_prev:
            _itens_aprov_ctx = [i for i in _orc_prev.itens if i.status_item == "APROVADO_DIRETOR"]
            _fonte_versao_ctx = f"aprovados na v{orc.versao - 1}"

periodo_str = _periodo_fmt(orc.periodo_referencia)
status_str  = _STATUS_PT.get(orc.status, orc.status)

# ── Cabeçalho escuro com logo ─────────────────────────────────────────────────
_b64 = _logo_b64()
_logo_tag = (
    f'<img src="data:image/png;base64,{_b64}" '
    f'style="max-width:170px;max-height:64px;display:block;margin:0 auto;">'
    if _b64
    else '<p style="color:#374151;font-size:26px;font-weight:700;text-align:center;margin:0;">📦 EstoquePro</p>'
)
st.markdown(
    f"<div style='background:#111827;border-radius:10px;padding:28px 32px;"
    f"text-align:center;margin-bottom:8px;'>"
    f"{_logo_tag}"
    f"<p style='color:rgba(235,235,235,0.65);font-size:13px;margin:8px 0 0;'>"
    f"</p></div>",
    unsafe_allow_html=True,
)

st.markdown(
    f"<h2 style='color:#111827;margin:16px 0 4px;'>Documento de Orçamento para Aprovação</h2>"
    f"<p style='color:#737373;font-size:14px;margin:0 0 20px;'>"
    f"EstoquePro · {periodo_str} · {orc.numero} v{orc.versao}</p>",
    unsafe_allow_html=True,
)

# ── Metadados ─────────────────────────────────────────────────────────────────
c1, c2, c3 = st.columns(3)
c1.markdown(f"**Responsável:** {orc.responsavel or '—'}")
c2.markdown(
    f"**Data envio:** "
    f"{orc.enviado_em.strftime('%d/%m/%Y %H:%M') if orc.enviado_em else '—'}"
)
c3.markdown(f"**Status:** {status_str}")

st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)

# ── Resumo financeiro ─────────────────────────────────────────────────────────
_total_bruto = 0.0
_frete_total = 0.0
_total_geral = 0.0
for _it in orc.itens:
    if not _it.cotacoes:
        continue
    _cm = min(_it.cotacoes, key=lambda c: c.total_calculado)
    _total_bruto += _it.quantidade_orcada * _cm.preco_unitario - _cm.desconto + _cm.outros_custos
    _frete_total += _cm.frete
    _total_geral += _cm.total_calculado

m1, m2, m3, m4 = st.columns(4)
m1.metric("Itens",        len(orc.itens))
m2.metric("Total bruto",  fmt_brl(round(_total_bruto, 2)))
m3.metric("Frete total",  fmt_brl(round(_frete_total, 2)))
m4.metric("Total geral",  fmt_brl(round(_total_geral, 2)))

st.divider()

# ── Decisão já registrada — exibe resultado e para ───────────────────────────
if orc.status != "ENVIADO_APROVACAO":
    _bg = {"APROVADO": "#dcfce7", "APROVADO_PARCIAL": "#dcfce7",
           "DEVOLVIDO_REVISAO": "#fef3c7", "REPROVADO": "#fee2e2"}.get(orc.status, "#f4f4f5")
    _fg = {"APROVADO": "#16a34a", "APROVADO_PARCIAL": "#16a34a",
           "DEVOLVIDO_REVISAO": "#b45309", "REPROVADO": "#dc2626"}.get(orc.status, "#737373")
    st.markdown(
        f"<div style='background:{_bg};border-radius:8px;padding:16px 20px;'>"
        f"<p style='color:{_fg};font-size:16px;font-weight:700;margin:0 0 6px;'>"
        f"Decisão registrada: {status_str}</p>"
        + (f"<p style='margin:0;color:#444;'>Observação: {orc.observacao_diretor}</p>"
           if orc.observacao_diretor else "")
        + (f"<p style='margin:4px 0 0;color:#737373;font-size:12px;'>"
           f"Em: {orc.decidido_em.strftime('%d/%m/%Y %H:%M')}</p>"
           if orc.decidido_em else "")
        + "</div>",
        unsafe_allow_html=True,
    )
    st.divider()
    st.markdown("### Itens do Orçamento")
    for _item in sorted(orc.itens, key=lambda i: (i.categoria_nome or "", i.nome_item)):
        _lbl, _cor = _STATUS_ITEM.get(_item.status_item, ("—", "#737373"))
        st.markdown(
            f"<span style='font-weight:600;'>{_item.nome_item}</span>"
            f"<span style='color:#737373;font-size:13px;'>"
            f" · {_item.categoria_nome or '—'} · Qtd {_item.quantidade_orcada}</span>"
            f"&nbsp;&nbsp;<span style='color:{_cor};font-size:13px;'>{_lbl}</span>",
            unsafe_allow_html=True,
        )
    st.stop()

# ── Cotações por item ─────────────────────────────────────────────────────────

if _itens_aprov_ctx:
    with st.expander(
        f"✅ {len(_itens_aprov_ctx)} item(ns) já aprovado(s) — {_fonte_versao_ctx}",
        expanded=False,
    ):
        st.caption("Estes itens foram aprovados e não estão sujeitos a nova decisão.")
        for _ip in sorted(_itens_aprov_ctx, key=lambda i: (i.categoria_nome or "", i.nome_item)):
            st.markdown(
                f"✅ **{_ip.nome_item}** · {_ip.categoria_nome or '—'} · Qtd: {_ip.quantidade_orcada}",
            )

st.markdown("### Cotações por Item")
st.caption("★ indica o menor preço. Selecione a decisão para cada item na linha do seu título.")

sorted_itens = sorted(
    [i for i in orc.itens if i.status_item != "APROVADO_DIRETOR"],
    key=lambda i: (i.categoria_nome or "", i.nome_item),
)

for item in sorted_itens:
    tipo_str = "Compra Avulsa" if item.tipo == "AVULSA" else "Estoque"

    st.markdown(
        f"<div style='margin-top:18px;'>"
        f"<span style='font-weight:700;font-size:15px;'>{item.nome_item}</span>"
        f"<span style='color:#737373;font-size:13px;'>"
        f" · {item.categoria_nome or '—'} · Qtd: {item.quantidade_orcada} · {tipo_str}"
        f"</span></div>",
        unsafe_allow_html=True,
    )
    if orc.versao > 1:
        st.caption("🔄 Item em revisão — reavalie as cotações e registre sua decisão.")

    if item.cotacoes:
        _min_id = min(item.cotacoes, key=lambda c: c.total_calculado).id
        _rows = [
            {
                "Fornecedor / Origem": ("★ " if c.id == _min_id else "") + c.origem,
                "Unit.":    fmt_brl(c.preco_unitario),
                "Frete":    fmt_brl(c.frete) if c.frete else "—",
                "Desconto": fmt_brl(c.desconto) if c.desconto else "—",
                "Total":    fmt_brl(c.total_calculado),
                "Data":     c.data_cotacao.strftime("%d/%m/%Y") if c.data_cotacao else "—",
            }
            for c in sorted(item.cotacoes, key=lambda c: c.total_calculado)
        ]
        st.dataframe(pd.DataFrame(_rows), hide_index=True, use_container_width=True)
    else:
        st.caption("_Sem cotações registradas._")

    _col_dec, _ = st.columns([3, 4])
    with _col_dec:
        st.radio(
            f"dec_{item.id}",
            _DEC_ITEM,
            horizontal=True,
            key=f"item_dec_{item.id}",
            label_visibility="collapsed",
        )

st.divider()

# ── Decisão final ─────────────────────────────────────────────────────────────
_reprovados = [
    item.id for item in sorted_itens
    if st.session_state.get(f"item_dec_{item.id}", "Aprovar") == "Reprovar"
]
_revisao = [
    item.id for item in sorted_itens
    if st.session_state.get(f"item_dec_{item.id}", "Aprovar") == "Revisar cotações"
]
_tem_flags = bool(_reprovados or _revisao)

st.markdown("### Decisão Final")

if _tem_flags:
    _n_apr = len(sorted_itens) - len(_reprovados) - len(_revisao)
    _chips = []
    if _n_apr > 0:
        _chips.append(
            f"<span style='background:#dcfce7;color:#16a34a;padding:4px 12px;"
            f"border-radius:12px;font-size:13px;font-weight:600;'>"
            f"✅ {_n_apr} aprovado{'s' if _n_apr > 1 else ''}</span>"
        )
    if _reprovados:
        _chips.append(
            f"<span style='background:#fee2e2;color:#dc2626;padding:4px 12px;"
            f"border-radius:12px;font-size:13px;font-weight:600;'>"
            f"❌ {len(_reprovados)} reprovado{'s' if len(_reprovados) > 1 else ''}</span>"
        )
    if _revisao:
        _chips.append(
            f"<span style='background:#fef3c7;color:#b45309;padding:4px 12px;"
            f"border-radius:12px;font-size:13px;font-weight:600;'>"
            f"🔄 {len(_revisao)} para revisão</span>"
        )
    st.markdown(
        "<p style='color:#444;font-size:14px;margin-bottom:10px;'>"
        "Há itens com decisões individuais. A decisão será "
        "<strong>Aprovar Parcialmente</strong>.</p>"
        + "&nbsp;&nbsp;".join(_chips),
        unsafe_allow_html=True,
    )
    _decisao_val = "APROVADO_PARCIAL"
    if st.checkbox(
        "Reprovar orçamento inteiro (ignorar todas as seleções acima)",
        key="reprovar_tudo_flag",
    ):
        _decisao_val = "REPROVADO"
else:
    _dec_label = st.radio(
        "Decisão geral",
        ["✅  Aprovar orçamento completo", "❌  Reprovar orçamento inteiro"],
        horizontal=True,
        key="dec_global",
        label_visibility="collapsed",
    )
    _decisao_val = "APROVADO" if "Aprovar" in _dec_label else "REPROVADO"

st.markdown("<div style='height:12px;'></div>", unsafe_allow_html=True)

_obs = st.text_area(
    "Observação (opcional)",
    placeholder="Motivo da decisão, itens com ressalvas, etc.",
    key="dir_obs",
)

st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)

_col_btn, _ = st.columns([2, 3])
with _col_btn:
    if st.button("Registrar decisão", type="primary", use_container_width=True):
        try:
            with SessionLocal() as _sess:
                registrar_decisao_diretor(
                    _sess,
                    orcamento_id=orc.id,
                    decisao=_decisao_val,
                    observacao_diretor=_obs.strip() if _obs.strip() else None,
                    itens_reprovados=_reprovados if _reprovados else None,
                    itens_revisao=_revisao if _revisao else None,
                )
            push_service.notificar_decisao_orcamento(orc.numero, _decisao_val, periodo_str)
            st.success("Decisão registrada com sucesso.")
            st.rerun()
        except ValueError as e:
            st.error(str(e), icon="⚠️")
