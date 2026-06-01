import streamlit as st

from core.ui import page_header, section_title

page_header(
    "Controle de Estoque — RH DFeB",
    subtitle="Sistema operacional de gestão de itens, compras e orçamentos.",
)

_PAGES = [
    ("📊", "Visão Geral",  "Dashboard com KPIs, alertas e itens críticos."),
    ("📋", "Estoque",      "Consulta, movimentações e edição de limites."),
    ("🛒", "Compras",      "Análise e lista de itens para reposição."),
    ("💰", "Orçamentos",   "Cotações por fornecedor e estimativas de valor."),
    ("📈", "Relatórios",   "Consumo mensal, por categoria e histórico."),
]

section_title("Módulos do sistema")
st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)

for chunk_start in range(0, len(_PAGES), 3):
    chunk = _PAGES[chunk_start : chunk_start + 3]
    cols = st.columns(len(chunk))
    for col, (icon, title, desc) in zip(cols, chunk):
        with col:
            st.markdown(
                f"""
                <div style="border:1px solid #E5E5E5;border-radius:8px;padding:20px 20px 16px;
                            background:#FFFFFF;box-shadow:0 1px 2px rgba(0,0,0,0.04);">
                    <div style="font-size:30px;margin-bottom:10px;">{icon}</div>
                    <p style="font-size:15px;font-weight:600;color:#0A0A0A;margin:0 0 4px;">{title}</p>
                    <p style="font-size:13px;color:#737373;margin:0;">{desc}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )
    st.markdown("<div style='height:12px;'></div>", unsafe_allow_html=True)

st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)
st.info(
    "**Primeiro acesso:** navegue até **Estoque → Editar → Itens** e defina os valores de "
    "_Estoque Mínimo_ e _Estoque Ideal_ de cada item. Sem esses valores o motor de "
    "análise não gera recomendações de compra.",
    icon="ℹ️",
)
