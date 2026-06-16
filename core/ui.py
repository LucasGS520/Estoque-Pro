""" Utilitários visuais compartilhados pelas páginas Streamlit.

Centraliza CSS, cabeçalhos, estados vazios, formatação monetária e tema Plotly
para manter a identidade visual consistente entre telas.
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

_ASSETS = Path(__file__).parent.parent / "assets"
_LOGO = _ASSETS / "logo_dfeb.png"

# ── Paleta de cores DFeB ──────────────────────────────────────────────────────
DFEB_COLORS: dict[str, str] = {
    "red":    "#E10600",
    "black":  "#262626",
    "gray":   "#9CA3AF",
    "grid":   "#E5E5E5",
    "muted":  "#737373",
    "green":  "#16A34A",
    "orange": "#F59E0B",
}

# ── CSS global injetado em cada página ───────────────────────────────────────
_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

html, body, [class*="css"], .stApp {
    font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif !important;
}

/* ── Sidebar escura ──────────────────────────────────────────────────── */
[data-testid="stSidebar"] {
    background-color: #0A0A0A !important;
    border-right: 1px solid #262626 !important;
}
[data-testid="stSidebar"] > div:first-child {
    padding-top: 1rem !important;
}
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] span:not([class*="badge"]),
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] .stMarkdown {
    color: #EBEBEB !important;
}
/* Nav links gerados automaticamente pelo Streamlit */
[data-testid="stSidebarNav"] a,
[data-testid="stSidebarNavLink"] {
    color: rgba(235,235,235,0.72) !important;
    border-radius: 0 !important;
}
[data-testid="stSidebarNav"] a:hover,
[data-testid="stSidebarNavLink"]:hover {
    background: rgba(255,255,255,0.07) !important;
    color: #EBEBEB !important;
}
[data-testid="stSidebarNav"] a[aria-current="page"],
[data-testid="stSidebarNavLink"][aria-current="page"] {
    border-left: 3px solid #E10600 !important;
    background: rgba(225,6,0,0.12) !important;
    color: #EBEBEB !important;
}

/* Botão de colapsar sidebar (seta/ícone dentro da sidebar aberta) */
[data-testid="stSidebar"] button svg {
    fill: rgba(235,235,235,0.75) !important;
    color: rgba(235,235,235,0.75) !important;
}
[data-testid="stSidebar"] button:hover svg {
    fill: #FFFFFF !important;
}

/* ── Controle de REABRIR sidebar quando está colapsada ───────────── */
/* O ícone "›" fica invisível (svg preto no fundo preto) sem esse fix */
[data-testid="stSidebarCollapsedControl"] {
    display: flex !important;
    visibility: visible !important;
    opacity: 1 !important;
    z-index: 99999 !important;
    pointer-events: all !important;
}
[data-testid="stSidebarCollapsedControl"] > div,
[data-testid="stSidebarCollapsedControl"] button {
    background: #0A0A0A !important;
    border-radius: 0 6px 6px 0 !important;
    border: 1px solid #262626 !important;
    border-left: none !important;
    box-shadow: 2px 0 8px rgba(0,0,0,0.30) !important;
}
[data-testid="stSidebarCollapsedControl"] button {
    color: #EBEBEB !important;
}
[data-testid="stSidebarCollapsedControl"] svg {
    fill: #EBEBEB !important;
    color: #EBEBEB !important;
    stroke: #EBEBEB !important;
}

/* ── Botões primários ────────────────────────────────────────────────── */
button[kind="primary"] {
    background-color: #E10600 !important;
    color: #FFFFFF !important;
    border: none !important;
    border-radius: 6px !important;
    font-weight: 600 !important;
    font-size: 14px !important;
}
button[kind="primary"]:hover {
    background-color: #B80500 !important;
}
button[kind="primary"]:disabled {
    opacity: 0.5 !important;
    cursor: not-allowed !important;
}

/* ── Botões secundários ──────────────────────────────────────────────── */
button[kind="secondary"] {
    background-color: #FFFFFF !important;
    border: 1px solid #E5E5E5 !important;
    border-radius: 6px !important;
    color: #0A0A0A !important;
    font-size: 14px !important;
}
button[kind="secondary"]:hover {
    background-color: #F4F4F5 !important;
}

/* ── Tabs ────────────────────────────────────────────────────────────── */
[data-testid="stTabs"] [role="tablist"] {
    border-bottom: 1px solid #E5E5E5 !important;
    gap: 0 !important;
}
[data-testid="stTabs"] button[role="tab"] {
    border-radius: 0 !important;
    font-size: 14px !important;
    font-weight: 500 !important;
    color: #737373 !important;
    padding: 10px 18px !important;
    border-bottom: 2px solid transparent !important;
    transition: color 0.15s ease;
}
[data-testid="stTabs"] button[aria-selected="true"] {
    color: #E10600 !important;
    border-bottom: 2px solid #E10600 !important;
    background: transparent !important;
}

/* ── Métricas / KPI cards ────────────────────────────────────────────── */
[data-testid="stMetric"] {
    background: #FFFFFF !important;
    border: 1px solid #E5E5E5 !important;
    border-radius: 8px !important;
    padding: 16px 20px !important;
    box-shadow: 0 1px 2px rgba(0,0,0,0.04) !important;
}
[data-testid="stMetricLabel"] > div {
    font-size: 11px !important;
    font-weight: 600 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.07em !important;
    color: #737373 !important;
}
[data-testid="stMetricValue"] > div {
    font-size: 26px !important;
    font-weight: 700 !important;
    color: #0A0A0A !important;
    line-height: 1.2 !important;
}
[data-testid="stMetricDelta"] {
    font-size: 12px !important;
}

/* ── Alertas ─────────────────────────────────────────────────────────── */
[data-testid="stAlert"] {
    border-radius: 6px !important;
    border-left-width: 4px !important;
    font-size: 14px !important;
}

/* ── DataFrames ──────────────────────────────────────────────────────── */
[data-testid="stDataFrame"] {
    border: 1px solid #E5E5E5 !important;
    border-radius: 8px !important;
    overflow: hidden !important;
}

/* ── Inputs, selects, numbers ────────────────────────────────────────── */
.stTextInput input,
.stNumberInput input,
.stTextArea textarea {
    border: 1px solid #E5E5E5 !important;
    border-radius: 6px !important;
    font-size: 14px !important;
}
.stTextInput input:focus,
.stNumberInput input:focus,
.stTextArea textarea:focus {
    border-color: #E10600 !important;
    box-shadow: 0 0 0 2px rgba(225,6,0,0.15) !important;
}

/* ── Divisores ───────────────────────────────────────────────────────── */
hr {
    border-color: #E5E5E5 !important;
    margin: 16px 0 !important;
}

/* ── Transição suave entre páginas ──────────────────────────────────── */
@keyframes dfeb-fade-in {
    from { opacity: 0; transform: translateY(6px); }
    to   { opacity: 1; transform: translateY(0); }
}
.main .block-container {
    animation: dfeb-fade-in 0.20s ease-out;
}


/* ── Chrome do Streamlit ─────────────────────────────────────────────── */
footer { display: none !important; }
header[data-testid="stHeader"] {
    background: transparent !important;
    border-bottom: none !important;
    box-shadow: none !important;
}

/* ── Links de navegação manuais (st.page_link) ───────────────────────── */
[data-testid="stPageLink"] a,
[data-testid="stPageLink-NavLink"] {
    color: rgba(235,235,235,0.72) !important;
    text-decoration: none !important;
    border-radius: 0 !important;
    transition: background 0.15s ease, color 0.15s ease;
}
[data-testid="stPageLink"] a:hover,
[data-testid="stPageLink-NavLink"]:hover {
    background: rgba(255,255,255,0.07) !important;
    color: #EBEBEB !important;
}
[data-testid="stPageLink"] a[aria-current="page"],
[data-testid="stPageLink-NavLink"][aria-current="page"] {
    border-left: 3px solid #E10600 !important;
    background: rgba(225,6,0,0.12) !important;
    color: #EBEBEB !important;
}
[data-testid="stPageLink"] svg {
    fill: rgba(235,235,235,0.72) !important;
}
[data-testid="stPageLink"] a[aria-current="page"] svg {
    fill: #E10600 !important;
}

/* ── Ocultar botão de fullscreen em imagens na sidebar ───────────────── */
[data-testid="stSidebar"] [data-testid="stBaseButton-elementToolbar"],
[data-testid="stSidebar"] [data-testid="stElementToolbar"],
[data-testid="stSidebar"] [data-testid="stImageFullScreen"],
[data-testid="stSidebar"] button[title*="fullscreen"],
[data-testid="stSidebar"] button[title*="Fullscreen"],
[data-testid="stSidebar"] button[title*="tela cheia"] {
    display: none !important;
}

/* ── Card title para gráficos ─────────────────────────────────────────── */
.dfeb-chart-card-title {
    border: 1px solid #E5E5E5;
    border-bottom: none;
    border-radius: 6px 6px 0 0;
    padding: 12px 16px;
    background: #FFFFFF;
    color: #0A0A0A;
    font-size: 14px;
    font-weight: 600;
    margin-bottom: 0 !important;
}
</style>
"""


def setup_page(page_title: str, page_icon: str = "📦") -> None:
    """Injeta o CSS global na página atual.

    O `page_title` e `page_icon` permanecem na assinatura por clareza de uso,
    mas a configuração global de página fica centralizada em `app.py`.
    """
    st.markdown(_CSS, unsafe_allow_html=True)


def page_header(title: str, subtitle: str | None = None) -> None:
    """Renderiza o título principal da tela e um subtítulo opcional."""
    st.title(title)
    if subtitle:
        st.markdown(
            f"<p style='color:#737373;font-size:14px;margin-top:-12px;"
            f"margin-bottom:8px;'>{subtitle}</p>",
            unsafe_allow_html=True,
        )


def section_title(text: str) -> None:
    """Renderiza um rótulo discreto para separar seções de conteúdo."""
    st.markdown(
        f"<p style='font-size:11px;font-weight:600;text-transform:uppercase;"
        f"letter-spacing:0.08em;color:#737373;margin-bottom:4px;"
        f"margin-top:4px;'>{text}</p>",
        unsafe_allow_html=True,
    )


def status_badge(status: str) -> str:
    """Retorna HTML de badge para o status de um item de estoque."""
    _MAP: dict[str, tuple[str, str, str]] = {
        "ok":                  ("#DCFCE7", "#16A34A", "OK"),
        "abaixo_minimo":       ("#FEF3C7", "#92400E", "Abaixo do Mínimo"),
        "abaixo_ideal":        ("#FEFCE8", "#92400E", "Abaixo do Ideal"),
        "zerado":              ("#FEE2E2", "#DC2626", "Zerado"),
        "sem_parametro":       ("#F4F4F5", "#737373", "Sem Parâmetro"),
        # aliases legados
        "comprar":             ("#FEF3C7", "#92400E", "Abaixo do Mínimo"),
        "sem_minimo_definido": ("#F4F4F5", "#737373", "Sem Parâmetro"),
    }
    bg, fg, label = _MAP.get(status, ("#F4F4F5", "#737373", status))
    return (
        f"<span style='background:{bg};color:{fg};padding:2px 8px;"
        f"border-radius:4px;font-size:12px;font-weight:500;"
        f"display:inline-block;line-height:1.6;'>{label}</span>"
    )


def colorir_linhas_status(row: "pd.Series", campo: str = "status") -> list[str]:
    """Retorna lista de estilos CSS para Pandas Styler, colorindo por status operacional.

    Aceita tanto valores brutos ('zerado', 'comprar') quanto rótulos de exibição
    ('Zerado', 'A Comprar'), pois normaliza para minúsculas antes de comparar.
    """
    s = str(row.get(campo, "")).lower()
    if s in ("zerado",):
        return ["background-color: #ffdddd"] * len(row)
    if s in ("abaixo_minimo", "abaixo do mínimo", "comprar", "a comprar"):
        return ["background-color: #fffbcc"] * len(row)
    if s in ("sem_parametro", "sem parâmetro", "sem_minimo", "sem limite", "sem_limite", "sem_minimo_definido"):
        return ["background-color: #f5f5f5"] * len(row)
    return [""] * len(row)


def empty_state(icon: str, title: str, description: str = "") -> None:
    """Renderiza um estado vazio centralizado com ícone, título e descrição."""
    desc_html = (
        f"<p style='font-size:13px;color:#737373;margin:0;'>{description}</p>"
        if description else ""
    )
    st.markdown(
        f"""
        <div style='text-align:center;padding:48px 0;'>
            <div style='font-size:40px;color:#737373;margin-bottom:12px;'>{icon}</div>
            <p style='font-size:16px;font-weight:600;color:#262626;
                      margin:0 0 6px;'>{title}</p>
            {desc_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def fmt_brl(value: float) -> str:
    """Formata um número como moeda brasileira, por exemplo `R$ 1.234,56`."""
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def limpar_telefone(valor: str | None) -> str | None:
    """Normaliza número de WhatsApp/telefone para armazenamento.

    Aceita DDD + número (10-11 dígitos) e adiciona o DDI 55 automaticamente.
    Também aceita o número completo com DDI 55 (12-13 dígitos).
    Lança ValueError se o resultado não puder ser normalizado.
    """
    if not valor:
        return None
    digitos = "".join(c for c in valor if c.isdigit())
    if not digitos:
        return None
    if len(digitos) in (10, 11):
        digitos = "55" + digitos
    if len(digitos) not in (12, 13) or not digitos.startswith("55"):
        raise ValueError(
            "Número inválido. Informe DDD + número, ex: (11) 99999-9999."
        )
    return digitos


def formatar_telefone(digitos: str) -> str:
    """Formata dígitos de telefone armazenados para exibição: (DDD) NNNNN-NNNN."""
    if not digitos:
        return ""
    local = digitos[2:] if digitos.startswith("55") and len(digitos) in (12, 13) else digitos
    ddd = local[:2]
    num = local[2:]
    if len(num) == 9:
        return f"({ddd}) {num[:5]}-{num[5:]}"
    if len(num) == 8:
        return f"({ddd}) {num[:4]}-{num[4:]}"
    return digitos


def apply_plotly_theme(fig) -> None:
    """Aplica paleta e estilo visual DFeB a uma figura Plotly recebida."""
    fig.update_layout(
        paper_bgcolor="#FFFFFF",
        plot_bgcolor="#FAFAFA",
        font=dict(
            family="Inter, system-ui, -apple-system, sans-serif",
            color="#0A0A0A",
            size=12,
        ),
        colorway=["#E10600", "#262626", "#16A34A", "#F59E0B", "#737373"],
        margin=dict(t=40, b=20, l=10, r=10),
        title_font=dict(size=14, color="#262626"),
        legend=dict(
            bgcolor="rgba(0,0,0,0)",
            bordercolor="rgba(0,0,0,0)",
            font=dict(size=12),
        ),
        xaxis=dict(
            gridcolor="#E5E5E5",
            linecolor="#E5E5E5",
            tickfont=dict(size=11),
        ),
        yaxis=dict(
            gridcolor="#E5E5E5",
            linecolor="#E5E5E5",
            tickfont=dict(size=11),
        ),
    )


def apply_chart_theme(fig, height: int = 320, showlegend: bool = False) -> None:
    """Aplica tema padronizado DFeB a gráficos Plotly (versão refinada).

    Fundo totalmente branco, margens controladas, grid cinza discreto.
    Use este helper nos gráficos novos/refatorados; apply_plotly_theme()
    permanece para retrocompatibilidade.
    """
    fig.update_layout(
        height=height,
        paper_bgcolor="#FFFFFF",
        plot_bgcolor="#FFFFFF",
        font=dict(
            family="Inter, system-ui, -apple-system, sans-serif",
            color="#262626",
            size=12,
        ),
        margin=dict(t=24, r=20, b=36, l=48),
        showlegend=showlegend,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=-0.25,
            xanchor="left",
            x=0,
            bgcolor="rgba(0,0,0,0)",
            bordercolor="rgba(0,0,0,0)",
            font=dict(size=12, color="#262626"),
        ),
        xaxis=dict(
            gridcolor="#E5E5E5",
            zeroline=False,
            linecolor="#E5E5E5",
            tickfont=dict(size=11, color="#737373"),
        ),
        yaxis=dict(
            gridcolor="#E5E5E5",
            zeroline=False,
            linecolor="#E5E5E5",
            tickfont=dict(size=11, color="#737373"),
        ),
    )


def chart_title(title: str) -> None:
    """Renderiza o cabeçalho visual de um card de gráfico."""
    st.markdown(
        f'<div class="dfeb-chart-card-title">{title}</div>',
        unsafe_allow_html=True,
    )


def gerar_link_formulario(setor_id: int) -> str:
    """Retorna a URL pública do formulário de solicitação pré-definido para um setor."""
    from core.config import APP_BASE_URL
    return f"{APP_BASE_URL}/solicitar?setor={setor_id}"


def gerar_link_formulario_generico() -> str:
    """Retorna a URL do formulário sem setor pré-definido (link manual)."""
    from core.config import APP_BASE_URL
    return f"{APP_BASE_URL}/solicitar"
