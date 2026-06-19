"""Pedido de Compra — formulário de solicitação de materiais por setor."""
from core.auth import require_admin
from core.ui import page_header, setup_page
from views.pedido_compra.form import render

setup_page("Pedido de Compra", "📝")
require_admin()
page_header(
    "Pedido de Compra",
    subtitle="Registre aqui sua solicitação de materiais para o setor de compras.",
)
render()
