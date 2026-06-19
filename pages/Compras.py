"""Análise de Compras — orquestrador de período e navegação entre abas."""
import calendar
import datetime

import streamlit as st

from core import tempo
from core.auth import require_admin
from data.database import get_session_factory
from core.i18n import MESES_PT_LISTA as _MESES_PT_LISTA
from core.ui import inject_tabs_css, page_header, section_title, setup_page
from services.compras_service import (
    consolidar_periodo,
    get_consolidacao_periodo,
    get_painel_reposicao,
    get_periodos_com_atividade,
    get_periodos_com_consolidacao,
    get_todas_avulsas_periodo,
    has_pending_changes,
)
from views.compras.painel_reposicao import render as render_painel
from views.compras.solicitacoes import render as render_solicitacoes
from views.compras.consolidacao import render as render_consolidacao

setup_page("Análise de Compras", "🛒")
require_admin()
page_header("Análise de Compras", subtitle="Preparação inteligente da lista de compras.")
inject_tabs_css()

SessionLocal = get_session_factory()

# ── Seletor de período ────────────────────────────────────────────────────────
section_title("Período de Referência")

hoje = tempo.hoje()

with SessionLocal() as _s_per:
    _periodos_atividade = get_periodos_com_atividade(_s_per)

_periodo_opcoes      = {f"{_MESES_PT_LISTA[p.month]}/{p.year}": p for p in _periodos_atividade}
_periodo_atual_ref   = datetime.date(hoje.year, hoje.month, 1)
_periodo_atual_label = f"{_MESES_PT_LISTA[_periodo_atual_ref.month]}/{_periodo_atual_ref.year}"
_default_idx         = (
    list(_periodo_opcoes.keys()).index(_periodo_atual_label)
    if _periodo_atual_label in _periodo_opcoes else 0
)

col_per, col_btn = st.columns([3, 2])
with col_per:
    _periodo_label_sel = st.selectbox(
        "Período",
        list(_periodo_opcoes.keys()),
        index=_default_idx,
        key="sel_periodo",
        label_visibility="collapsed",
    )

periodo       = _periodo_opcoes[_periodo_label_sel]
periodo_label = _periodo_label_sel
_periodo_tipo = (
    "futuro"  if periodo > _periodo_atual_ref else
    "passado" if periodo < _periodo_atual_ref else
    "atual"
)
_btn_help = {
    "futuro":  "Período futuro — selecione o mês atual para executar",
    "passado": "Período encerrado — somente leitura",
}.get(_periodo_tipo)

with col_btn:
    consolidar = st.button(
        "▶ Análise Mensal de Compras",
        type="primary",
        use_container_width=True,
        disabled=(_periodo_tipo != "atual"),
        help=_btn_help,
    )

# ── Dados compartilhados entre abas ──────────────────────────────────────────
with SessionLocal() as _s:
    periodos_existentes = get_periodos_com_consolidacao(_s)
    itens_lista         = get_consolidacao_periodo(_s, periodo)
    avulsas_lista       = get_todas_avulsas_periodo(_s, periodo)
    painel_lista        = get_painel_reposicao(_s)
    cat_nomes           = ["Todas"] + sorted({r.categoria for r in painel_lista if r.categoria})
    _tem_mudancas       = has_pending_changes(_s, periodo) if itens_lista else False

# ── Banner de status ──────────────────────────────────────────────────────────
_ultimo_dia    = calendar.monthrange(periodo.year, periodo.month)[1]
_janela_inicio = f"01/{periodo.month:02d}/{periodo.year}"
_janela_fim    = (
    f"hoje ({hoje.strftime('%d/%m/%Y')})"
    if _periodo_tipo == "atual"
    else f"{_ultimo_dia:02d}/{periodo.month:02d}/{periodo.year}"
)

if _periodo_tipo == "futuro":
    st.error(
        f"**Período futuro** — não é possível executar análises para **{periodo_label}**. "
        "Selecione o mês atual.",
        icon="🚫",
    )
elif periodo in periodos_existentes:
    _ultima_analise = max((x.atualizado_em for x in itens_lista), default=None)
    _n_total        = len(itens_lista)
    _n_sem_min      = sum(1 for x in itens_lista if x.status in {"sem_parametro", "sem_minimo_definido"})
    _n_lista_final  = (
        sum(1 for x in itens_lista if x.incluir_na_lista_final)
        + sum(1 for ca in avulsas_lista if ca.incluir_na_lista_final)
    )
    _data_str    = _ultima_analise.strftime("%d/%m/%Y às %H:%M") if _ultima_analise else "—"
    _sem_min_str = f" · ⚠️ {_n_sem_min} sem mínimo/ideal" if _n_sem_min else ""
    _lock_str    = "  \n🔒 Período encerrado — somente leitura" if _periodo_tipo == "passado" else ""
    st.info(
        f"**Análise Mensal — {periodo_label}**  \n"
        f"📅 Janela: {_janela_inicio} – {_janela_fim} · Última análise: {_data_str}  \n"
        f"🔢 {_n_total} item(ns) analisado(s) · ✅ {_n_lista_final} aprovado(s) na lista final{_lock_str}",
        icon="⚠️" if _n_sem_min else "✅",
    )
else:
    if _periodo_tipo == "passado":
        st.info(f"Sem análise registrada para **{periodo_label}**.", icon="📋")
    else:
        st.warning(
            f"Nenhuma análise para **{periodo_label}** — clique em **Análise Mensal de Compras**."
            f"  \n📅 Janela: {_janela_inicio} – {_janela_fim}",
            icon="⚠️",
        )

# ── Auto-consolidação ─────────────────────────────────────────────────────────
_aba_sel      = st.session_state.get("compras_aba", "Painel de Reposição")
_aba_anterior = st.session_state.get("_compras_aba_anterior")
_navegou_para_consolidacao = _aba_sel == "Consolidação" and _aba_anterior != "Consolidação"
st.session_state["_compras_aba_anterior"] = _aba_sel

if _periodo_tipo == "atual" and (_navegou_para_consolidacao or not itens_lista or _tem_mudancas) and not consolidar:
    with st.spinner("Atualizando análise..."):
        with SessionLocal() as _s:
            consolidar_periodo(_s, periodo)
    with SessionLocal() as _s:
        itens_lista   = get_consolidacao_periodo(_s, periodo)
        avulsas_lista = get_todas_avulsas_periodo(_s, periodo)

if consolidar:
    _aba_atual = st.session_state.get("compras_aba", "Painel de Reposição")
    with st.spinner("Recalculando análise..."):
        with SessionLocal() as _s:
            results, summary = consolidar_periodo(_s, periodo)
    st.session_state["compras_aba"] = _aba_atual
    st.session_state["_compras_aba_anterior"] = _aba_atual
    st.success(
        f"Análise de **{periodo_label}** concluída — "
        f"{summary.itens_zerados} zerado(s) · "
        f"{summary.itens_abaixo_minimo} abaixo do mínimo · "
        f"{summary.itens_abaixo_ideal} abaixo do ideal"
    )
    st.rerun()

# ── Navegação por abas ────────────────────────────────────────────────────────
aba = st.radio(
    "Navegação",
    ["Painel de Reposição", "Solicitações e Pendências", "Consolidação"],
    horizontal=True,
    label_visibility="collapsed",
    key="compras_aba",
)

if aba == "Painel de Reposição":
    render_painel(painel_lista, cat_nomes, periodo_label)
elif aba == "Solicitações e Pendências":
    render_solicitacoes(periodo, periodo_label, _periodo_tipo)
else:
    render_consolidacao(periodo, periodo_label, _periodo_tipo, itens_lista, avulsas_lista)
