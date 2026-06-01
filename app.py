import streamlit as st

from core.database import init_db
from core.config import EXPORTS_DIR, UPLOADS_DIR
from core.ui import _CSS, _LOGO

# ── Configuração global única ─────────────────────────────────────────────────
st.set_page_config(
    page_title="Controle de Estoque — DFeB",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Init ──────────────────────────────────────────────────────────────────────
init_db()
EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

# ── CSS global ────────────────────────────────────────────────────────────────
st.markdown(_CSS, unsafe_allow_html=True)

# ── Navegação: roteamento sem menu automático ────────────────────────────────
pg = st.navigation(
    [
        st.Page("pages/Home.py",       title="Início",      icon=":material/home:",          default=True),
        st.Page("pages/Visao_Geral.py", title="Visão Geral", icon=":material/dashboard:"),
        st.Page("pages/Estoque.py",    title="Estoque",     icon=":material/inventory_2:"),
        st.Page("pages/Compras.py",    title="Compras",     icon=":material/shopping_cart:"),
        st.Page("pages/Orcamentos.py", title="Orçamentos",  icon=":material/receipt_long:"),
        st.Page("pages/Relatorios.py", title="Relatórios",  icon=":material/bar_chart:"),
    ],
    position="hidden",
)

# ── Sidebar: logo → subtítulo → menu manual ───────────────────────────────────
with st.sidebar:
    if _LOGO.exists():
        st.image(str(_LOGO), width=210)
    else:
        st.markdown(
            "<p style='color:#E10600;font-size:18px;font-weight:700;"
            "margin:0 0 2px;'>⚡ DFeB</p>",
            unsafe_allow_html=True,
        )
    st.markdown(
        "<p style='color:rgba(235,235,235,0.65);font-size:13px;"
        "margin:0 0 8px;'>Controle de Estoque</p>",
        unsafe_allow_html=True,
    )
    st.markdown("---")

    st.page_link("pages/Home.py",       label="Início",      icon=":material/home:",          use_container_width=True)
    st.page_link("pages/Visao_Geral.py", label="Visão Geral", icon=":material/dashboard:",     use_container_width=True)
    st.page_link("pages/Estoque.py",    label="Estoque",     icon=":material/inventory_2:",   use_container_width=True)
    st.page_link("pages/Compras.py",    label="Compras",     icon=":material/shopping_cart:", use_container_width=True)
    st.page_link("pages/Orcamentos.py", label="Orçamentos",  icon=":material/receipt_long:",  use_container_width=True)
    st.page_link("pages/Relatorios.py", label="Relatórios",  icon=":material/bar_chart:",     use_container_width=True)

pg.run()
