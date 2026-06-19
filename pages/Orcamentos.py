"""Orçamentos — orquestrador de abas de cotação, aprovação e histórico."""
import datetime

import streamlit as st

from core.auth import require_admin
from core.database import get_session_factory
from core.i18n import MESES_PT_LISTA as _MESES_PT
from core.ui import empty_state, inject_tabs_css, page_header, setup_page
from services.compras_service import get_periodos_com_consolidacao
from views.orcamentos.cotacoes import render as render_cotacoes
from views.orcamentos.historico import render as render_historico
from views.orcamentos.painel import render as render_painel

setup_page("Orçamentos", "💰")
require_admin()
page_header("Orçamentos", subtitle="Cotação, comparação e aprovação da compra a partir da Lista Final.")
inject_tabs_css()

SessionLocal = get_session_factory()

with SessionLocal() as _s:
    _periodos_lista = get_periodos_com_consolidacao(_s)

if not _periodos_lista:
    empty_state(
        "🛒",
        "Sem dados de compras",
        "Execute a consolidação em Análise de Compras e aprove itens na Lista Final primeiro.",
    )
    st.stop()

_periodo_opcoes = {f"{_MESES_PT[p.month]}/{p.year}": p for p in _periodos_lista}
_periodo_label = st.selectbox(
    "Período",
    list(_periodo_opcoes.keys()),
    key="orc_periodo_sel",
    label_visibility="collapsed",
)
periodo: datetime.date = _periodo_opcoes[_periodo_label]

# orc_tab_nav permite navegação programática sem violar restrição do Streamlit
_TAB_OPTIONS = ["Painel", "Cotações", "Histórico"]
_nav_request = st.session_state.pop("orc_tab_nav", None)
_tab_index = _TAB_OPTIONS.index(_nav_request) if _nav_request in _TAB_OPTIONS else 0

tab_sel = st.radio(
    "Navegação",
    _TAB_OPTIONS,
    key="orc_tab",
    horizontal=True,
    label_visibility="collapsed",
    index=_tab_index,
)

if tab_sel == "Painel":
    render_painel(periodo, _periodo_label)
elif tab_sel == "Cotações":
    render_cotacoes(periodo, _periodo_label)
else:
    render_historico(periodo, _periodo_label)
