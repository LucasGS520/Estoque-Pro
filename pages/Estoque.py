"""Estoque — orquestrador de abas de consulta, movimentação e cadastros."""
import streamlit as st

from core.auth import require_admin
from core.ui import inject_tabs_css, page_header, setup_page
from views.estoque.cadastros import render as render_cadastros
from views.estoque.devolucoes import render as render_devolucoes
from views.estoque.movimentacoes import render as render_movimentacoes
from views.estoque.visualizar import render as render_visualizar

setup_page("Estoque", "📋")
require_admin()
page_header("Estoque", subtitle="Consulta, movimentações e edição de itens, fornecedores e categorias.")
inject_tabs_css()

if _fb := st.session_state.pop("_fb", None):
    getattr(st, _fb[0])(_fb[1])

tab_sel = st.radio(
    "Navegação", ["Visualizar", "Registrar Movimentação", "Devoluções", "Editar"],
    key="estoque_tab", horizontal=True, label_visibility="collapsed"
)

if tab_sel == "Visualizar":
    render_visualizar()
elif tab_sel == "Registrar Movimentação":
    render_movimentacoes()
elif tab_sel == "Devoluções":
    render_devolucoes()
else:
    render_cadastros()
