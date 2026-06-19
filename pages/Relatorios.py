"""Relatórios — orquestrador de abas analíticas."""
import streamlit as st

from core.auth import require_admin
from core.ui import inject_tabs_css, page_header, setup_page
from views.relatorios.categoria import render as render_categoria
from views.relatorios.consumo import render as render_consumo
from views.relatorios.historico_mov import render as render_historico
from views.relatorios.item import render as render_item
from views.relatorios.setor import render as render_setor

setup_page("Relatórios", "📈")
require_admin()
page_header("Relatórios", subtitle="Consumo histórico por período, categoria, setor e item.")
inject_tabs_css()

tab_sel = st.radio(
    "Navegação",
    ["Consumo × Reposição", "Histórico de Movimentações", "Por Item", "Por Setor", "Por Categoria"],
    key="rel_tab", horizontal=True, label_visibility="collapsed",
)

if tab_sel == "Consumo × Reposição":
    render_consumo()
elif tab_sel == "Histórico de Movimentações":
    render_historico()
elif tab_sel == "Por Item":
    render_item()
elif tab_sel == "Por Setor":
    render_setor()
else:
    render_categoria()
