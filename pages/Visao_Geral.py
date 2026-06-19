"""Visão Geral — dashboard de indicadores e alertas operacionais de estoque."""
from core.auth import require_admin
from core.ui import page_header, setup_page
from views.visao_geral.painel import render

setup_page("Visão Geral", "📊")
require_admin()
page_header("Visão Geral", subtitle="Indicadores gerais e alertas operacionais de estoque.")
render()
