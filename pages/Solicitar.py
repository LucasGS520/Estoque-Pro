"""Formulário público de solicitação de materiais — acessível via /solicitar."""

import base64
import datetime

import streamlit as st

from core.database import get_session_factory
from core.schemas import SolicitacaoMaterialCreate
from core.ui import _CSS, _LOGO, section_title
from services.compras_service import criar_solicitacao
from services.estoque_service import get_all_itens, get_setores

# CSS global + ocultar sidebar
st.markdown(_CSS, unsafe_allow_html=True)
st.markdown(
    "<style>"
    "[data-testid='stSidebar']    { display: none !important; }"
    "[data-testid='collapsedControl'] { display: none !important; }"
    "</style>",
    unsafe_allow_html=True,
)

SessionLocal = get_session_factory()

MESES_PT = {
    1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril",
    5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto",
    9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro",
}


def _periodo_label(d: datetime.date) -> str:
    return f"{MESES_PT[d.month]}/{d.year}"


def _opcoes_periodo() -> list[datetime.date]:
    hoje = datetime.date.today()
    proximo_mes = hoje.month % 12 + 1
    proximo_ano = hoje.year if hoje.month < 12 else hoje.year + 1
    return [
        datetime.date(hoje.year, hoje.month, 1),
        datetime.date(proximo_ano, proximo_mes, 1),
    ]


def _logo_base64() -> str | None:
    if _LOGO.exists():
        with open(_LOGO, "rb") as f:
            return base64.b64encode(f.read()).decode()
    return None


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------

if "sol_itens" not in st.session_state:
    st.session_state["sol_itens"] = []
if "sol_enviada" not in st.session_state:
    st.session_state["sol_enviada"] = False

# ---------------------------------------------------------------------------
# Carregar catálogo (extrair para dicts antes de fechar a sessão)
# ---------------------------------------------------------------------------

with SessionLocal() as _s:
    _setores_raw = get_setores(_s)
    _itens_raw = get_all_itens(_s, apenas_ativos=True)

    setores = [(s.id, s.nome) for s in _setores_raw]
    catalogo = [
        {
            "id": i.id,
            "nome": i.nome,
            "categoria": i.categoria.nome,
            "unidade": i.unidade,
        }
        for i in _itens_raw
    ]

opcoes_periodo = _opcoes_periodo()
categorias_disponiveis = ["Todas"] + sorted({i["categoria"] for i in catalogo})

# ---------------------------------------------------------------------------
# Cabeçalho — fundo escuro com logo (padrão da sidebar)
# ---------------------------------------------------------------------------

_logo_b64 = _logo_base64()
_logo_tag = (
    f'<img src="data:image/png;base64,{_logo_b64}" '
    f'style="max-width:170px;max-height:64px;display:block;margin:0 auto;">'
    if _logo_b64
    else '<p style="color:#E10600;font-size:26px;font-weight:700;text-align:center;margin:0;">⚡ DFeB</p>'
)

st.markdown(
    f"<div style='background:#0A0A0A;border-radius:10px;padding:28px 32px;"
    f"text-align:center;margin-bottom:8px;'>"
    f"{_logo_tag}"
    f"<p style='color:rgba(235,235,235,0.65);font-size:13px;margin:8px 0 0;'>"
    f"Controle de Estoque</p></div>",
    unsafe_allow_html=True,
)

st.markdown(
    "<h2 style='color:#262626;margin:16px 0 4px;'>Solicitação de Materiais</h2>"
    "<p style='color:#737373;font-size:15px;margin:0 0 20px;'>"
    "Preencha os campos abaixo e envie sua solicitação ao setor de compras.</p>",
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Tela de confirmação pós-envio
# ---------------------------------------------------------------------------

if st.session_state["sol_enviada"]:
    st.success(
        "**Solicitação enviada com sucesso!**  \n"
        "O setor de Compras receberá e processará os itens solicitados. "
        "Você pode fechar esta página ou enviar uma nova solicitação."
    )
    if st.button("Fazer nova solicitação", type="secondary"):
        st.session_state["sol_itens"] = []
        st.session_state["sol_enviada"] = False
        st.rerun()
    st.stop()

# ---------------------------------------------------------------------------
# Seção 1 — Identificação do solicitante
# ---------------------------------------------------------------------------

st.markdown("### 1. Identificação")

col1, col2, col3 = st.columns([2, 2, 1])

with col1:
    setor_opts = {nome: sid for sid, nome in setores}
    setor_nome = st.selectbox(
        "Setor *",
        options=[nome for _, nome in setores],
        index=None,
        placeholder="Selecione o setor responsável...",
        key="sel_setor",
    )
    setor_id = setor_opts.get(setor_nome) if setor_nome else None

with col2:
    solicitante = st.text_input("Nome do Solicitante *", placeholder="Nome completo", key="inp_solicitante")

with col3:
    periodo_sel = st.selectbox(
        "Período *",
        options=opcoes_periodo,
        format_func=_periodo_label,
        key="sel_periodo",
    )

st.markdown("---")

# ---------------------------------------------------------------------------
# Seção 2 — Buscar e adicionar itens do catálogo
# ---------------------------------------------------------------------------

st.markdown("### 2. Adicionar Itens")

section_title("Filtros")
col_busca, col_cat = st.columns([3, 1])

with col_busca:
    busca = st.text_input(
        "Buscar por nome",
        placeholder="Digite parte do nome...",
        key="sol_busca",
    )

with col_cat:
    cat_sel = st.selectbox(
        "Filtrar por categoria",
        options=categorias_disponiveis,
        key="sol_cat",
    )

# Filtragem combinada: categoria + texto
busca_lower = busca.strip().lower()
itens_base = catalogo if cat_sel == "Todas" else [i for i in catalogo if i["categoria"] == cat_sel]
itens_filtrados = (
    [i for i in itens_base if busca_lower in i["nome"].lower()]
    if busca_lower
    else itens_base
)

# Selectbox + formulário de adição
if itens_filtrados:
    n = len(itens_filtrados)
    st.caption(
        f"**{n}** {'item' if n == 1 else 'itens'}"
        + (f" em **{cat_sel}**" if cat_sel != "Todas" else "")
        + (f' — filtrado por "{busca.strip()}"' if busca_lower else "")
    )

    item_label_map = {
        f"{i['nome']}  ({i['categoria']} · {i['unidade']})": i
        for i in itens_filtrados
    }

    item_label_sel = st.selectbox(
        "Selecione o item *",
        options=list(item_label_map.keys()),
        placeholder="Selecione ou comece a digitar para buscar...",
        key="sol_item",
        label_visibility="collapsed",
    )
    item_sel = item_label_map.get(item_label_sel) if item_label_sel else None

    if item_sel:
        col_qtd, col_obs = st.columns([1, 3])
        with col_qtd:
            qtd_item = st.number_input(
                "Quantidade *",
                min_value=1,
                value=1,
                step=1,
                key="sol_qtd",
            )
        with col_obs:
            obs_item = st.text_input(
                "Observação (opcional)",
                placeholder="Justificativa, urgência, especificação técnica...",
                key="sol_obs",
            )

        if st.button("＋ Adicionar ao Pedido", type="primary", key="btn_add"):
            ja_existe = any(e["item_id"] == item_sel["id"] for e in st.session_state["sol_itens"])
            if ja_existe:
                st.warning(
                    f"**{item_sel['nome']}** já está na lista. "
                    "Remova-o na seção de revisão abaixo para alterar a quantidade."
                )
            else:
                st.session_state["sol_itens"].append({
                    "tipo": "Existente",
                    "item_id": item_sel["id"],
                    "nome": item_sel["nome"],
                    "categoria": item_sel["categoria"],
                    "unidade": item_sel["unidade"],
                    "quantidade": int(qtd_item),
                    "observacao": obs_item.strip() or None,
                })
                st.rerun()
else:
    st.info(
        "Nenhum item encontrado com os filtros atuais. "
        "Tente outra categoria ou outro termo de busca. "
        "Se o material não existe no catálogo, use a seção abaixo."
    )

st.markdown("")

# ---------------------------------------------------------------------------
# Seção 3 — Item novo (não encontrado no catálogo)
# ---------------------------------------------------------------------------

with st.expander("Solicitar Novo Item"):
    st.caption(
        "Use esta seção quando o material não existir no catálogo. "
        "O setor de Compras avaliará e cadastrará antes de incluir na lista final."
    )

    col_n1, col_n2 = st.columns([3, 1])
    with col_n1:
        nome_novo = st.text_input(
            "Nome do item *",
            placeholder="Descreva com clareza: marca, modelo, medida, especificação...",
            key="inp_novo_nome",
        )
    with col_n2:
        qtd_novo = st.number_input("Quantidade *", min_value=1, value=1, step=1, key="inp_novo_qtd")

    obs_novo = st.text_input(
        "Observação / Justificativa",
        placeholder="Para que será usado? Há urgência? Referência de onde encontrar?",
        key="inp_novo_obs",
    )

    if st.button("＋ Adicionar ao Pedido", type="primary", key="btn_add_novo"):
        if not nome_novo.strip():
            st.error("Informe o nome do item.")
        else:
            st.session_state["sol_itens"].append({
                "tipo": "Novo",
                "item_id": None,
                "nome": nome_novo.strip(),
                "categoria": "Item Novo",
                "unidade": "—",
                "quantidade": int(qtd_novo),
                "observacao": obs_novo.strip() or None,
            })
            st.rerun()

st.markdown("---")

# ---------------------------------------------------------------------------
# Seção 4 — Revisão e envio
# ---------------------------------------------------------------------------

st.markdown("### 3. Revisão e Envio")

itens_lista: list[dict] = st.session_state["sol_itens"]

if not itens_lista:
    st.markdown(
        "<p style='color:#737373;font-size:14px;'>Nenhum item adicionado ainda. "
        "Use as seções acima para montar sua solicitação.</p>",
        unsafe_allow_html=True,
    )
else:
    for idx, item in enumerate(itens_lista):
        with st.container(border=True):
            c_info, c_rm = st.columns([11, 1])
            with c_info:
                if item["tipo"] == "Novo":
                    badge = (
                        "<span style='background:#F59E0B;color:#fff;font-size:11px;"
                        "font-weight:600;padding:2px 8px;border-radius:10px;margin-left:6px;'>Novo Item</span>"
                    )
                else:
                    badge = (
                        "<span style='background:#3B82F6;color:#fff;font-size:11px;"
                        "font-weight:600;padding:2px 8px;border-radius:10px;margin-left:6px;'>Catálogo</span>"
                    )
                st.markdown(f"**{item['nome']}**{badge}", unsafe_allow_html=True)

                c_cat, c_qtd, c_obs = st.columns([2, 1, 4])
                c_cat.markdown(
                    f"<span style='color:#737373;font-size:13px;'>{item['categoria']}</span>",
                    unsafe_allow_html=True,
                )
                c_qtd.markdown(f"**{item['quantidade']}** {item['unidade']}")
                c_obs.markdown(
                    f"<span style='color:#737373;font-size:13px;'>{item.get('observacao') or '—'}</span>",
                    unsafe_allow_html=True,
                )
            with c_rm:
                if st.button("✕", key=f"rm_{idx}", help="Remover item"):
                    st.session_state["sol_itens"].pop(idx)
                    st.rerun()

    st.markdown("")

    identificacao_ok = bool(setor_id and solicitante.strip())
    if not identificacao_ok:
        st.warning("Preencha o **Setor** e o **Nome do Solicitante** na Seção 1 antes de enviar.")

    submitted = st.button(
        f"Enviar Solicitação ({len(itens_lista)} {'item' if len(itens_lista) == 1 else 'itens'})",
        disabled=not identificacao_ok,
        type="primary",
        use_container_width=True,
        key="btn_enviar",
    )

    if submitted:
        with SessionLocal() as _s:
            for item in itens_lista:
                dados = SolicitacaoMaterialCreate(
                    item_id=item["item_id"],
                    nome_item_livre=item["nome"] if item["item_id"] is None else None,
                    setor_id=setor_id,
                    solicitante=solicitante.strip(),
                    quantidade_solicitada=item["quantidade"],
                    observacao=item.get("observacao"),
                    periodo_referencia=periodo_sel,
                )
                criar_solicitacao(_s, dados)

        st.session_state["sol_enviada"] = True
        st.rerun()
