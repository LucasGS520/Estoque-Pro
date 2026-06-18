""" Tela da camada de Compras — governança da necessidade de compra.

Fluxo: seleção de período → solicitações (formulário externo /solicitar) →
classificar → consolidar → revisar painel → lista final.
"""

import calendar
import datetime

from core import tempo
from collections import defaultdict

import pandas as pd
import streamlit as st

from core.auth import require_admin
from core.database import get_session_factory
from core.ui import (
    empty_state,
    fmt_brl,
    gerar_link_formulario_generico,
    page_header,
    section_title,
    setup_page,
)
from services.compras_service import (
    aplicar_parametros_e_reclassificar,
    aprovar_item,
    aprovar_solicitacao,
    atualizar_compra_avulsa,
    criar_item_e_vincular,
    desfazer_compra_avulsa,
    get_compras_avulsas_periodo,
    get_todas_avulsas_periodo,
    rejeitar_solicitacao,
    registrar_compra_avulsa,
    revertir_solicitacao,
    classificar_solicitacoes_periodo,
    consolidar_periodo,
    deletar_solicitacao,
    get_consolidacao_periodo,
    get_lista_final,
    has_pending_changes,
    get_painel_reposicao,
    get_periodos_com_atividade,
    get_periodos_com_consolidacao,
    listar_solicitacoes,
    remover_da_lista,
    resetar_quantidades_consolidacao,
    vincular_item_existente,
)
from documents.lista_compras import gerar_lista_compras
from services import notificacao_service
from services.ciclo_service import (
    abrir_ciclo,
    adicionar_setor_ao_ciclo,
    deletar_ciclo,
    encerrar_ciclo,
    enviar_avisos_prazo_proximo,
    enviar_feedbacks_aprovacao,
    enviar_lembretes_pendentes,
    get_ciclo_por_periodo,
    prorrogar_ciclo,
    reabrir_ciclo,
    reenviar_notificacao_setor,
)
from services.estoque_service import atualizar_fornecedores_item, get_all_itens, get_categorias, get_setores
from services.fornecedor_service import get_all_fornecedores

setup_page("Análise de Compras", "🛒")
require_admin()
page_header("Análise de Compras", subtitle="Preparação inteligente da lista de compras.")

# ── CSS: st.radio como abas (mesmo padrão de todas as outras páginas) ──────────
st.markdown("""
<style>
[data-testid="stRadio"] [role="radiogroup"] {
    display: flex !important;
    flex-direction: row !important;
    gap: 0 !important;
    flex-wrap: nowrap !important;
    border-bottom: 1px solid rgba(49, 51, 63, 0.2) !important;
    padding-bottom: 0 !important;
    margin-bottom: 0.75rem !important;
}
[data-testid="stRadio"] [role="radiogroup"] > label {
    display: flex !important;
    align-items: center !important;
    padding: 0.4rem 1.1rem 0.55rem 1.1rem !important;
    margin: 0 0 -1px 0 !important;
    border: none !important;
    border-bottom: 2px solid transparent !important;
    background: transparent !important;
    cursor: pointer !important;
    color: rgba(49, 51, 63, 0.6) !important;
    font-size: 0.875rem !important;
    font-weight: 400 !important;
    white-space: nowrap !important;
    transition: color 0.15s !important;
}
[data-testid="stRadio"] [role="radiogroup"] > label [data-baseweb="radio"],
[data-testid="stRadio"] [role="radiogroup"] > label input[type="radio"] {
    display: none !important;
}
[data-testid="stRadio"] [role="radiogroup"] > label:has(input:checked) {
    border-bottom: 2px solid rgb(255, 75, 75) !important;
    color: rgb(255, 75, 75) !important;
    font-weight: 600 !important;
}
[data-testid="stRadio"] [role="radiogroup"] > label:hover {
    color: rgba(49, 51, 63, 0.85) !important;
}

/* Mobile: tabs viram chips que quebram linha */
@media (max-width: 768px) {
    [data-testid="stRadio"] [role="radiogroup"] {
        flex-wrap: wrap !important;
        border-bottom: none !important;
        gap: 4px !important;
        overflow-x: visible !important;
        margin-bottom: 0.5rem !important;
    }
    [data-testid="stRadio"] [role="radiogroup"] > label {
        padding: 0.25rem 0.7rem !important;
        font-size: 0.78rem !important;
        border: 1px solid rgba(49, 51, 63, 0.2) !important;
        border-bottom: 1px solid rgba(49, 51, 63, 0.2) !important;
        border-radius: 4px !important;
        margin: 0 !important;
        flex-shrink: 0 !important;
        white-space: nowrap !important;
    }
    [data-testid="stRadio"] [role="radiogroup"] > label:has(input:checked) {
        border-color: #E10600 !important;
        color: #E10600 !important;
        background: rgba(225, 6, 0, 0.08) !important;
    }
}
</style>
""", unsafe_allow_html=True)

SessionLocal = get_session_factory()


@st.dialog("Resolver: Novo Item", width="large")
def _modal_novo_item(sol, periodo, exp_key: str) -> None:
    """Modal overlay para resolver solicitações classificadas como 'novo_item'."""
    st.caption(
        f"Solicitante: **{sol.solicitante}** · "
        f"Quantidade solicitada: **{sol.quantidade_solicitada}**"
    )

    _aba = st.radio(
        "aba_novo",
        ["Criar novo item", "Compra avulsa", "Vincular a existente"],
        horizontal=True,
        label_visibility="collapsed",
        key=f"aba_novo_{sol.id}",
    )

    st.markdown("<div style='height:4px;'></div>", unsafe_allow_html=True)

    # ── Aba 1: Criar novo item ────────────────────────────────────────────
    if _aba == "Criar novo item":
        with SessionLocal() as _ds:
            _cats     = get_categorias(_ds)
            _forn_all = get_all_fornecedores(_ds)
        _cat_map  = {c.nome: c.id for c in _cats}
        _forn_map = {f.nome: f.id for f in _forn_all}

        _dc1, _dc2 = st.columns(2)
        _d_nome = _dc1.text_input(
            "Nome do item",
            value=sol.nome_item_livre or "",
            key=f"d_nome_{sol.id}",
        )
        _d_cat = _dc2.selectbox(
            "Categoria",
            list(_cat_map.keys()),
            index=None,
            placeholder="Selecione uma categoria...",
            key=f"d_cat_{sol.id}",
        )
        _dc3, _dc4 = st.columns(2)
        _d_unid    = _dc3.text_input("Unidade", value="un", key=f"d_unid_{sol.id}")
        _d_est_ini = _dc4.number_input("Estoque Atual", min_value=0, value=0, step=1, key=f"d_est_{sol.id}")

        with st.expander("Valores manuais de estoque (opcional)", expanded=False):
            st.caption("Deixe em 0 para usar o cálculo automático após a próxima revisão mensal.")
            _de1, _de2 = st.columns(2)
            _d_min   = _de1.number_input("Mínimo manual", min_value=0, value=0, step=1, key=f"d_min_{sol.id}")
            _d_ideal = _de2.number_input("Ideal manual",  min_value=max(0, _d_min), value=max(0, _d_min) if _d_min > 0 else 0, step=1, key=f"d_ideal_{sol.id}")

        _d_forn  = st.multiselect("Fornecedores", list(_forn_map.keys()), placeholder="Selecione os fornecedores...", key=f"d_forn_{sol.id}")
        _d_obs   = st.text_area("Observações", key=f"d_obs_{sol.id}")
        _d_ativo = st.checkbox("Ativo", value=True, key=f"d_ativo_{sol.id}")

        _erros_criar = []
        if not _d_nome.strip():
            _erros_criar.append("Informe o nome do item.")
        if _d_cat is None:
            _erros_criar.append("Selecione uma categoria.")
        if _d_ideal > 0 and _d_min == 0:
            _erros_criar.append("Se ideal > 0, mínimo também deve ser > 0.")
        if _d_ideal > 0 and _d_ideal < _d_min:
            _erros_criar.append("Ideal deve ser ≥ mínimo.")

        # Exibe avisos apenas quando o formulário foi parcialmente preenchido
        _form_tocado = bool(_d_nome.strip()) or _d_cat is not None or _d_min > 0 or _d_ideal > 0
        if _form_tocado and _erros_criar:
            st.warning("  \n".join(_erros_criar))

        if st.button("Criar e Vincular", key=f"d_criar_{sol.id}", type="primary", disabled=bool(_erros_criar), use_container_width=True):
            try:
                with SessionLocal() as _ds2:
                    criar_item_e_vincular(
                        _ds2, sol.id,
                        categoria_id=_cat_map[_d_cat],
                        nome=_d_nome.strip(),
                        unidade=_d_unid,
                        estoque_atual=_d_est_ini,
                        minimo=_d_min if _d_min > 0 else None,
                        ideal=_d_ideal if _d_ideal > 0 else None,
                        observacoes=_d_obs.strip() or None,
                        ativo=_d_ativo,
                        fornecedor_ids=[_forn_map[n] for n in _d_forn] or None,
                    )
                st.session_state[exp_key] = True
                st.rerun()
            except ValueError as _e:
                st.error(str(_e))

    # ── Aba 2: Compra avulsa ──────────────────────────────────────────────
    elif _aba == "Compra avulsa":
        st.info("Compras de itens que não devem entrar no Controle do Estoque.")
        _ca1, _ca2 = st.columns(2)
        _ca_nome = _ca1.text_input("Nome do item", value=sol.nome_item_livre or "", key=f"ca_nome_{sol.id}")
        _ca_unid = _ca2.text_input("Unidade", value="un", key=f"ca_unid_{sol.id}")
        _ca3, _ca4 = st.columns(2)
        _ca_qtd = _ca3.number_input("Quantidade", min_value=1, value=int(sol.quantidade_solicitada), step=1, key=f"ca_qtd_{sol.id}")
        _ca_urg = _ca4.checkbox("Urgente", value=bool(sol.urgente), key=f"ca_urg_{sol.id}")
        _ca_obs  = st.text_area("Observação", value=sol.observacao or "", key=f"ca_obs_{sol.id}")
        _ca_incl = st.checkbox("Incluir na lista final de compras", value=True, key=f"ca_incl_{sol.id}")

        if not _ca_nome.strip():
            st.warning("Informe o nome do item.")
        elif st.button("Aprovar como compra avulsa", key=f"ca_aprovar_{sol.id}", type="primary", use_container_width=True):
            with SessionLocal() as _ds2:
                registrar_compra_avulsa(
                    _ds2, sol.id,
                    nome_item=_ca_nome.strip(),
                    unidade=_ca_unid,
                    quantidade=_ca_qtd,
                    urgente=_ca_urg,
                    observacao=_ca_obs.strip() or None,
                    incluir_na_lista_final=_ca_incl,
                )
            st.session_state[exp_key] = True
            st.rerun()

    # ── Aba 3: Vincular a existente ───────────────────────────────────────
    else:
        with SessionLocal() as _ds:
            _todos_cats  = get_categorias(_ds)
            _todos_itens = get_all_itens(_ds, apenas_ativos=False)

        _vcat_opts = ["Todas as categorias"] + [c.nome for c in _todos_cats]
        _vcat_sel  = st.selectbox("Filtrar por categoria", _vcat_opts, key=f"v_cat_{sol.id}")

        _itens_filtrados = (
            _todos_itens if _vcat_sel == "Todas as categorias"
            else [i for i in _todos_itens if i.categoria.nome == _vcat_sel]
        )

        if _itens_filtrados:
            _item_map = {
                f"{i.nome}  (atual: {i.estoque_atual}  |  mín: {i.estoque_minimo_vigente or 0}  |  ideal: {i.estoque_ideal_vigente or 0})": i.id
                for i in _itens_filtrados
            }
            _v_sel = st.selectbox("Selecione o item", list(_item_map.keys()), key=f"v_item_{sol.id}")
            if st.button("Vincular", key=f"v_vincular_{sol.id}", type="primary", use_container_width=True):
                with SessionLocal() as _ds2:
                    vincular_item_existente(_ds2, sol.id, _item_map[_v_sel])
                st.session_state[exp_key] = True
                st.rerun()
        else:
            st.info("Nenhum item encontrado para a categoria selecionada.")


MESES_PT = {
    1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril",
    5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto",
    9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro",
}

_STATUS_LABEL = {
    "zerado":              "Zerado",
    "abaixo_minimo":       "Abaixo do Mínimo",
    "abaixo_ideal":        "Abaixo do Ideal",
    "ok":                  "OK",
    "sem_parametro":       "Sem Parâmetro",
    # Legado (registros antigos no banco)
    "comprar":             "Abaixo do Mínimo",
    "sem_minimo_definido": "Sem Parâmetro",
    "excesso":             "OK",
}

# ── Seletor de período ────────────────────────────────────────────────────────
section_title("Período de Referência")

hoje = tempo.hoje()
_MESES_PT_LISTA = [
    "", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
]

with SessionLocal() as _s_per:
    _periodos_atividade = get_periodos_com_atividade(_s_per)

_periodo_opcoes     = {f"{_MESES_PT_LISTA[p.month]}/{p.year}": p for p in _periodos_atividade}
_periodo_atual_ref  = datetime.date(hoje.year, hoje.month, 1)
_periodo_atual_label = f"{_MESES_PT_LISTA[_periodo_atual_ref.month]}/{_periodo_atual_ref.year}"
_default_idx        = (
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

with SessionLocal() as _s:
    periodos_existentes = get_periodos_com_consolidacao(_s)
    itens_lista  = get_consolidacao_periodo(_s, periodo)
    avulsas_lista = get_todas_avulsas_periodo(_s, periodo)
    painel_lista = get_painel_reposicao(_s)
    cats = get_categorias(_s)
    cat_nomes = ["Todas"] + sorted({r.categoria for r in painel_lista if r.categoria})
    _tem_mudancas = has_pending_changes(_s, periodo) if itens_lista else False

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
    _ultima_analise  = max((x.atualizado_em for x in itens_lista), default=None)
    _n_total         = len(itens_lista)
    _n_comprar       = sum(1 for x in itens_lista if x.status in {"zerado", "abaixo_minimo", "comprar"})
    _n_sem_min       = sum(1 for x in itens_lista if x.status in {"sem_parametro", "sem_minimo_definido"})
    _n_avulsas       = len(avulsas_lista)
    _n_lista_final   = (
        sum(1 for x in itens_lista if x.incluir_na_lista_final)
        + sum(1 for ca in avulsas_lista if ca.incluir_na_lista_final)
    )
    _data_str        = _ultima_analise.strftime("%d/%m/%Y às %H:%M") if _ultima_analise else "—"
    _sem_min_str     = f" · ⚠️ {_n_sem_min} sem mínimo/ideal" if _n_sem_min else ""
    _avulsas_str     = f" · 🛒 {_n_avulsas} compra(s) avulsa(s)" if _n_avulsas else ""
    _lock_str        = "  \n🔒 Período encerrado — somente leitura" if _periodo_tipo == "passado" else ""
    _banner_icon     = "⚠️" if _n_sem_min else "✅"
    st.info(
        f"**Análise Mensal — {periodo_label}**  \n"
        f"📅 Janela: {_janela_inicio} – {_janela_fim} · Última análise: {_data_str}  \n"
        f"🔢 {_n_total} item(ns) analisado(s) · ✅ {_n_lista_final} aprovado(s) na lista final{_lock_str}",
        icon=_banner_icon,
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

# Auto-consolidação baseada em navegação de aba:
# - Navegar PARA "Consolidação" → recalcula imediatamente
# - Sem dados no período atual → recalcula imediatamente
# - Interações dentro da aba (salvar, filtrar) → não recalcula
_aba_sel = st.session_state.get("compras_aba", "Painel de Reposição")
_aba_anterior = st.session_state.get("_compras_aba_anterior")
_navegou_para_consolidacao = (
    _aba_sel == "Consolidação" and _aba_anterior != "Consolidação"
)
# Atualiza _aba_anterior antes de qualquer branch para preservar estado correto
st.session_state["_compras_aba_anterior"] = _aba_sel

if _periodo_tipo == "atual" and (_navegou_para_consolidacao or not itens_lista or _tem_mudancas) and not consolidar:
    with st.spinner("Atualizando análise..."):
        with SessionLocal() as _s:
            consolidar_periodo(_s, periodo)
    # Recarrega inline — sem st.rerun() para não resetar o state do radio widget
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

# =============================================================================
# ABA 1 — PAINEL DE REPOSIÇÃO
# =============================================================================
if aba == "Painel de Reposição":

    if not painel_lista:
        empty_state(
            "🛒",
            "Sem itens ativos no estoque",
            "Cadastre itens em Estoque para visualizar o painel de reposição.",
        )
    else:
        zerados         = [r for r in painel_lista if r.status.value == "zerado"]
        abaixo_min      = [r for r in painel_lista if r.status.value == "abaixo_minimo"]
        abaixo_ideal_list = [r for r in painel_lista if r.status.value == "abaixo_ideal"]
        ok_list         = [r for r in painel_lista if r.status.value == "ok"]
        sem_param       = [r for r in painel_lista if r.status.value == "sem_parametro"]

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Zerados",          len(zerados))
        c2.metric("Abaixo do Mín.",   len(abaixo_min))
        c3.metric("Abaixo do Ideal",  len(abaixo_ideal_list))
        c4.metric("OK",               len(ok_list))
        c5.metric("Sem Parâmetro",    len(sem_param))

        st.markdown("<div style='height:12px;'></div>", unsafe_allow_html=True)

        section_title("Filtros")
        col_busca, col_cat, col_status = st.columns([3, 2, 2])
        with col_busca:
            busca = st.text_input("Buscar item", placeholder="Digite parte do nome...", key="painel_busca")
        with col_cat:
            cat_sel = st.selectbox("Categoria", cat_nomes, key="painel_cat")
        with col_status:
            status_opcoes = {
                "Todos os alertas": None,
                "Zerado": "zerado",
                "Abaixo do Mínimo": "abaixo_minimo",
                "Abaixo do Ideal": "abaixo_ideal",
                "Sem Parâmetro": "sem_parametro",
                "OK": "ok",
            }
            status_sel = st.selectbox("Status", list(status_opcoes.keys()), key="painel_status")

        STATUS_PAINEL = {"zerado", "abaixo_minimo", "abaixo_ideal", "sem_parametro", "ok"}
        itens_painel = [r for r in painel_lista if r.status.value in STATUS_PAINEL]

        busca_lower = busca.strip().lower()
        status_code = status_opcoes[status_sel]
        if status_code:
            itens_painel = [r for r in itens_painel if r.status.value == status_code]
        if cat_sel != "Todas":
            itens_painel = [r for r in itens_painel if r.categoria == cat_sel]
        if busca_lower:
            itens_painel = [r for r in itens_painel if busca_lower in r.nome.lower()]

        if not itens_painel:
            empty_state("✅", "Nenhum item encontrado para os filtros selecionados.")
        else:
            rows = []
            for r in itens_painel:
                rows.append({
                    "Status": _STATUS_LABEL.get(r.status.value, r.status.value),
                    "Item": r.nome,
                    "Categoria": r.categoria,
                    "Estoque": r.qtd_atual,
                    "Mínimo": r.estoque_minimo,
                    "Ideal": r.estoque_ideal,
                    "Qtd Sugerida": r.quantidade_recomendar,
                    "Fornecedor": r.fornecedor_sugerido or "—",
                    "Valor Est.": fmt_brl(r.valor_estimado) if r.valor_estimado else "—",
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


# =============================================================================
# ABA 2 — SOLICITAÇÕES
# =============================================================================
elif aba == "Solicitações e Pendências":

    # ── Envio de Solicitações ─────────────────────────────────────────────────
    with SessionLocal() as _cs:
        _ciclo_periodo = get_ciclo_por_periodo(_cs, periodo)
        if _ciclo_periodo:
            _ciclo_id        = _ciclo_periodo.id
            _ciclo_status    = _ciclo_periodo.status
            _ciclo_prazo     = _ciclo_periodo.prazo_resposta_em
            _ciclo_abertura  = _ciclo_periodo.abertura_em
            _ciclo_encerrado = _ciclo_periodo.encerrado_em
            _participantes   = list(_ciclo_periodo.participantes)
            _total_set       = len(_participantes)
            _respondidos     = sum(1 for p in _participantes if p.status in {"respondido", "sem_solicitacao"})
            _pendentes       = _total_set - _respondidos
        else:
            _ciclo_id = None
            _ciclo_status = None

    section_title("Envio de Solicitações")

    _ultimo_dia_mes = datetime.date(
        periodo.year, periodo.month, calendar.monthrange(periodo.year, periodo.month)[1]
    )

    if _ciclo_id is None:
        # Estado 1 — Preparação
        if _periodo_tipo == "atual":
            with SessionLocal() as _cs2:
                _setores_ativos = get_setores(_cs2, apenas_ativos=True)
                _setores_ativos_count = len(_setores_ativos)
                _setores_com_wpp = sum(1 for s in _setores_ativos if s.whatsapp)
                _setores_sem_wpp = _setores_ativos_count - _setores_com_wpp

            # Aviso se as credenciais WhatsApp não estão configuradas
            if not notificacao_service.credenciais_configuradas():
                st.warning(
                    "**Notificações WhatsApp não configuradas.** "
                    "Configure as credenciais necessárias nas variáveis de ambiente "
                    "para habilitar o envio automático dos formulários.",
                    icon="⚠️",
                )

            with st.container(border=True):
                st.markdown(f"**Envio de Solicitação de Materiais — {periodo_label}**")

                if _setores_ativos_count > 0:
                    _plural = "es" if _setores_ativos_count != 1 else ""
                    if _setores_sem_wpp > 0:
                        st.caption(
                            f"{_setores_ativos_count} setor{_plural} ativo{_plural}: "
                            f"**{_setores_com_wpp}** receberão notificação automática · "
                            f"**{_setores_sem_wpp}** sem WhatsApp cadastrado (link manual disponível)."
                        )
                    else:
                        st.caption(f"{_setores_ativos_count} setor{_plural} ativo{_plural} receberão notificação automática.")
                else:
                    st.info("Nenhum setor ativo cadastrado. Cadastre setores antes de enviar.")

                _prazo_default = min(hoje + datetime.timedelta(days=7), _ultimo_dia_mes)
                _prazo_input = st.date_input(
                    "Prazo de resposta",
                    value=_prazo_default,
                    min_value=hoje,
                    max_value=_ultimo_dia_mes,
                    format="DD/MM/YYYY",
                    key="env_prazo_input",
                )
                if _prazo_input.day >= 28:
                    st.warning(
                        "⚠️ Prazo próximo ao fim do mês. Quanto mais cedo o envio e mais dias "
                        "os setores tiverem para responder, melhor."
                    )

                _, _env_btn_col = st.columns([3, 1])
                with _env_btn_col:
                    if st.button(
                        "Enviar solicitações",
                        type="primary",
                        key="btn_enviar_solicitacao",
                        use_container_width=True,
                        disabled=(_setores_ativos_count == 0),
                    ):
                        try:
                            _prazo_dt = datetime.datetime.combine(_prazo_input, datetime.time(23, 59))
                            with SessionLocal() as _s:
                                _res_abertura = abrir_ciclo(_s, periodo, _prazo_dt)
                            st.session_state["_ciclo_abertura_result"] = {
                                "enviados": _res_abertura.enviados,
                                "falhas_api": _res_abertura.falhas_api,
                                "sem_whatsapp": _res_abertura.sem_whatsapp,
                            }
                            st.rerun()
                        except ValueError as _ve:
                            st.error(str(_ve))
        else:
            st.caption(f"Nenhum envio de solicitações registrado para **{periodo_label}**.")

    elif _ciclo_status == "aberto":
        # Estado 2 — Coleta aberta

        # Toast com resultado do envio se o ciclo acabou de ser aberto
        _abertura_result = st.session_state.pop("_ciclo_abertura_result", None)
        if _abertura_result:
            _partes = []
            if _abertura_result["enviados"]:
                _partes.append(f"✅ {_abertura_result['enviados']} notificado(s)")
            if _abertura_result["falhas_api"]:
                _partes.append(f"❌ {_abertura_result['falhas_api']} com falha de API")
            if _abertura_result["sem_whatsapp"]:
                _partes.append(f"⚠️ {_abertura_result['sem_whatsapp']} sem WhatsApp")
            if _partes:
                st.success(f"Ciclo aberto — {' · '.join(_partes)}")
            else:
                st.success("Ciclo aberto com sucesso.")

        _prazo_atual  = _ciclo_prazo.date() if _ciclo_prazo else (hoje + datetime.timedelta(days=7))
        _abertura_txt = _ciclo_abertura.strftime("%d/%m/%Y") if _ciclo_abertura else "—"
        _prazo_txt    = _prazo_atual.strftime("%d/%m/%Y")
        _prazo_vencido = _ciclo_prazo is not None and tempo.agora() > _ciclo_prazo
        _concluido_pct = int(_respondidos / _total_set * 100) if _total_set else 0

        @st.dialog(f"Encerrar coleta de {periodo_label}?")
        def _modal_encerrar_coleta():
            if _pendentes > 0:
                st.warning(f"{_pendentes} setor{'es' if _pendentes != 1 else ''} ainda não responderam.")
            _msg_enc = (
                f"Novas respostas serão bloqueadas. "
                f"As {_respondidos} resposta{'s' if _respondidos != 1 else ''} recebidas serão preservadas"
            )
            if _pendentes > 0:
                _msg_enc += f" e {_pendentes} setor{'es' if _pendentes != 1 else ''} permanecerão sem resposta"
            _msg_enc += ". A coleta poderá ser reaberta posteriormente."
            st.markdown(_msg_enc)
            _mc1, _mc2 = st.columns(2)
            with _mc1:
                if st.button("Cancelar", key="btn_modal_cancel_enc", use_container_width=True):
                    st.rerun()
            with _mc2:
                if st.button("Encerrar coleta", type="primary", key="btn_modal_confirm_enc", use_container_width=True):
                    with SessionLocal() as _s:
                        encerrar_ciclo(_s, _ciclo_id)
                    st.rerun()

        @st.dialog(f"Remover ciclo de {periodo_label}?")
        def _modal_remover_ciclo():
            st.error(
                f"Esta ação excluirá permanentemente este ciclo e "
                f"**{_respondidos} formulário{'s' if _respondidos != 1 else ''}** já recebido{'s' if _respondidos != 1 else ''}. "
                "Esta ação não pode ser desfeita."
            )
            _mr1, _mr2 = st.columns(2)
            with _mr1:
                if st.button("Cancelar", key="btn_modal_cancel_rem", use_container_width=True):
                    st.rerun()
            with _mr2:
                if st.button("Remover ciclo", type="primary", key="btn_modal_confirm_rem", use_container_width=True):
                    with SessionLocal() as _s:
                        deletar_ciclo(_s, _ciclo_id)
                    st.rerun()

        with st.container(border=True):
            # Cabeçalho
            _badge_bg  = "#D97706" if _prazo_vencido else "#16A34A"
            _badge_txt = "PRAZO EXPIRADO" if _prazo_vencido else "COLETA ABERTA"
            st.markdown(
                f"**{periodo_label}**&nbsp;"
                f"<span style='background:{_badge_bg};color:#fff;font-size:11px;"
                f"font-weight:600;padding:2px 8px;border-radius:10px;margin-left:4px;'>{_badge_txt}</span>"
                f"&nbsp;&nbsp;<span style='font-size:13px;color:#6B7280;'>"
                f"Enviado em {_abertura_txt} · Prazo em {_prazo_txt}</span>",
                unsafe_allow_html=True,
            )
            if _prazo_vencido:
                st.warning(
                    "O prazo de resposta expirou. "
                    "Os formulários dos setores estão bloqueados para novas respostas. "
                    "Clique em **Encerrar coleta** para finalizar formalmente este ciclo."
                )

            # Indicadores
            _ind1, _ind2, _ind3, _ind4 = st.columns(4)
            _ind1.metric("Setores", _total_set)
            _ind2.metric("Respondidos", _respondidos)
            _ind3.metric("Pendentes", _pendentes)
            _ind4.metric("Concluído", f"{_concluido_pct}%")
            st.progress(_concluido_pct / 100)

            st.markdown("")

            # Prazo — exibição normal ou edição in-place
            if st.session_state.get("_editando_prazo"):
                _ep1, _ep2, _ep3 = st.columns([3, 1, 1])
                with _ep1:
                    _novo_prazo = st.date_input(
                        "Prazo de resposta",
                        value=min(max(_prazo_atual, hoje), _ultimo_dia_mes),
                        min_value=hoje,
                        max_value=_ultimo_dia_mes,
                        format="DD/MM/YYYY",
                        key="prazo_ciclo_aberto",
                    )
                with _ep2:
                    st.markdown("<div style='padding-top:28px;'>", unsafe_allow_html=True)
                    if st.button("Cancelar", key="btn_cancel_prazo_edit"):
                        st.session_state.pop("_editando_prazo", None)
                        st.rerun()
                    st.markdown("</div>", unsafe_allow_html=True)
                with _ep3:
                    st.markdown("<div style='padding-top:28px;'>", unsafe_allow_html=True)
                    if st.button("Atualizar", type="primary", key="btn_salvar_prazo"):
                        _novo_dt = datetime.datetime.combine(_novo_prazo, datetime.time(23, 59))
                        with SessionLocal() as _s:
                            prorrogar_ciclo(_s, _ciclo_id, _novo_dt)
                        st.session_state.pop("_editando_prazo", None)
                        st.rerun()
                    st.markdown("</div>", unsafe_allow_html=True)
            else:
                _pp1, _pp2 = st.columns([4, 1])
                with _pp1:
                    st.markdown(
                        f"<span style='font-size:12px;color:#6B7280;'>Prazo de resposta</span><br>"
                        f"<span style='font-size:15px;font-weight:600;'>{_prazo_txt}</span>",
                        unsafe_allow_html=True,
                    )
                with _pp2:
                    if st.button("Alterar prazo", key="btn_alterar_prazo", use_container_width=True):
                        st.session_state["_editando_prazo"] = True
                        st.rerun()

            st.markdown("")

            # Barra de ações
            _, _ac1, _ac2 = st.columns([2, 1, 1])
            with _ac1:
                if st.button("Encerrar coleta", key="btn_encerrar_coleta", use_container_width=True):
                    _modal_encerrar_coleta()
            with _ac2:
                if st.button("Remover ciclo", key="btn_remover_ciclo", use_container_width=True, type="secondary"):
                    _modal_remover_ciclo()

            # ── Banners de notificações automáticas ──────────────────────────
            if not _prazo_vencido and notificacao_service.credenciais_configuradas() and _pendentes > 0:
                _agora_banner = tempo.agora()
                _dias_desde_abertura = (_agora_banner - _ciclo_abertura).days if _ciclo_abertura else 0

                # Verifica se algum pendente ainda não recebeu lembrete D+2
                with SessionLocal() as _nb:
                    _participantes_sem_lembrete = [
                        p for p in _participantes
                        if p.status == "pendente" and p.notificacao_lembrete_d2_em is None
                    ]
                    _participantes_sem_prazo = [
                        p for p in _participantes
                        if p.status == "pendente" and p.notificacao_prazo_proximo_em is None
                    ]

                if _dias_desde_abertura >= 2 and _participantes_sem_lembrete:
                    _nb_col1, _nb_col2 = st.columns([4, 1])
                    with _nb_col1:
                        st.warning(
                            f"⏰ **{len(_participantes_sem_lembrete)} setor(es)** pendente(s) há mais de 2 dias. "
                            "Envie um lembrete para quem ainda não respondeu.",
                            icon="⏰",
                        )
                    with _nb_col2:
                        st.markdown("<div style='padding-top:8px;'>", unsafe_allow_html=True)
                        if st.button("Enviar lembrete", key="btn_lembrete_d2", use_container_width=True):
                            with SessionLocal() as _sl:
                                _res_lem = enviar_lembretes_pendentes(_sl, _ciclo_id)
                            st.success(
                                f"Lembretes enviados: ✅ {_res_lem['enviados']} · "
                                f"❌ {_res_lem['falhas_api']} falhas · "
                                f"⚠️ {_res_lem['sem_whatsapp']} sem WhatsApp"
                            )
                            st.rerun()
                        st.markdown("</div>", unsafe_allow_html=True)

                _dias_para_prazo = (_prazo_atual - hoje).days if _prazo_atual else 99
                if _dias_para_prazo <= 1 and _participantes_sem_prazo:
                    _vence_hoje = _dias_para_prazo <= 0
                    _prazo_msg  = "**vence hoje**" if _vence_hoje else "**vence amanhã**"
                    _nb2_col1, _nb2_col2 = st.columns([4, 1])
                    with _nb2_col1:
                        st.error(
                            f"🚨 Prazo {_prazo_msg}. "
                            f"{len(_participantes_sem_prazo)} setor(es) ainda não responderam.",
                            icon="🚨",
                        )
                    with _nb2_col2:
                        st.markdown("<div style='padding-top:8px;'>", unsafe_allow_html=True)
                        if st.button("Enviar aviso de prazo", key="btn_aviso_prazo", use_container_width=True):
                            with SessionLocal() as _sp2:
                                _res_prazo = enviar_avisos_prazo_proximo(_sp2, _ciclo_id)
                            st.success(
                                f"Avisos enviados: ✅ {_res_prazo['enviados']} · "
                                f"❌ {_res_prazo['falhas_api']} falhas · "
                                f"⚠️ {_res_prazo['sem_whatsapp']} sem WhatsApp"
                            )
                            st.rerun()
                        st.markdown("</div>", unsafe_allow_html=True)

            # ── Status de notificações por setor ─────────────────────────────
            st.markdown("<hr style='margin:16px 0 12px;opacity:0.15;'>", unsafe_allow_html=True)
            section_title("Status por Setor")

            _participantes_ord = sorted(_participantes, key=lambda p: p.setor.nome if p.setor else "")
            _sh1, _sh2, _sh3, _sh4 = st.columns([3, 2, 4, 1])
            _sh1.caption("Setor")
            _sh2.caption("Resposta")
            _sh3.caption("Notificação")
            _sh4.caption("Ação")

            for _p in _participantes_ord:
                _pnome = _p.setor.nome if _p.setor else "—"

                # Badge de resposta
                if _p.status == "respondido":
                    _resp_txt = "✅ Respondido"
                elif _p.status == "sem_solicitacao":
                    _resp_txt = "✓ Sem pedido"
                else:
                    _resp_txt = "⏳ Pendente"

                # Badge de notificação
                if _p.falha_envio and _p.motivo_falha == "sem_whatsapp":
                    _notif_txt   = "⚠️ Sem WhatsApp cadastrado"
                    _notif_color = "#D97706"
                elif _p.falha_envio:
                    _motivo_curto = (_p.motivo_falha or "erro").replace("api_error:", "")[:40]
                    _notif_txt   = f"❌ {_motivo_curto}"
                    _notif_color = "#DC2626"
                elif _p.envio_notificado_em:
                    _notif_txt   = f"✅ Enviado em {_p.envio_notificado_em.strftime('%d/%m')}"
                    _notif_color = "#16A34A"
                else:
                    _notif_txt   = "— Não enviado"
                    _notif_color = "#6B7280"

                _pc1, _pc2, _pc3, _pc4 = st.columns([3, 2, 4, 1])
                _pc1.markdown(f"🏢 **{_pnome}**")
                _pc2.markdown(_resp_txt)
                _pc3.markdown(
                    f"<span style='color:{_notif_color};font-size:13px;'>{_notif_txt}</span>",
                    unsafe_allow_html=True,
                )
                with _pc4:
                    if _p.motivo_falha != "sem_whatsapp":
                        if st.button("Reenviar", key=f"reenviar_{_p.id}", use_container_width=True):
                            try:
                                with SessionLocal() as _rs:
                                    reenviar_notificacao_setor(_rs, _ciclo_id, _p.setor_id)
                                st.rerun()
                            except ValueError as _rve:
                                st.error(str(_rve))

        # ── Link do Formulário de Solicitação ────────────────────────────────
        _link_form = gerar_link_formulario_generico()
        st.markdown("---")
        st.caption("Link do Formulário:")
        st.code(_link_form, language=None)

        # ── Setores não incluídos neste ciclo ────────────────────────────────
        with SessionLocal() as _snc:
            _ids_no_ciclo = {p.setor_id for p in _participantes}
            _todos_ativos_ciclo = get_setores(_snc, apenas_ativos=True)
            _setores_fora = [s for s in _todos_ativos_ciclo if s.id not in _ids_no_ciclo]

        if _setores_fora:
            st.markdown("---")
            section_title("Setores não incluídos neste ciclo")
            for _sf in _setores_fora:
                _sf_col1, _, _sf_col3 = st.columns([3, 1, 1])
                _sf_col1.markdown(f"🏢 **{_sf.nome}**")
                if not _sf.whatsapp:
                    _sf_col1.caption("⚠️ Sem WhatsApp")
                _sf_btn_key = f"enviar_setor_{_sf.id}"
                if _sf_col3.button(
                    "Adicionar ao ciclo",
                    key=_sf_btn_key,
                    use_container_width=True,
                ):
                    try:
                        with SessionLocal() as _s2:
                            _p_novo = adicionar_setor_ao_ciclo(_s2, _ciclo_id, _sf.id)
                        if not _p_novo.falha_envio:
                            st.success(f"✅ **{_sf.nome}** adicionado e notificado.")
                        elif _p_novo.motivo_falha == "sem_whatsapp":
                            st.warning(f"⚠️ **{_sf.nome}** adicionado, mas sem WhatsApp cadastrado.")
                        else:
                            st.error(f"**{_sf.nome}** adicionado. Falha no envio: {_p_novo.motivo_falha}")
                        st.rerun()
                    except ValueError as _ve:
                        st.error(str(_ve))

    else:
        # Estado 4 — Coleta encerrada
        _enc_txt = _ciclo_encerrado.strftime("%d/%m/%Y") if _ciclo_encerrado else "—"
        _concluido_pct_enc = int(_respondidos / _total_set * 100) if _total_set else 0

        @st.dialog(f"Reabrir coleta de {periodo_label}?")
        def _modal_reabrir_coleta():
            st.markdown(
                f"Os setores poderão voltar a enviar formulários. "
                f"As {_respondidos} resposta{'s' if _respondidos != 1 else ''} já recebidas serão preservadas."
            )
            _rr1, _rr2 = st.columns(2)
            with _rr1:
                if st.button("Cancelar", key="btn_modal_cancel_reabrir", use_container_width=True):
                    st.rerun()
            with _rr2:
                if st.button("Reabrir coleta", type="primary", key="btn_modal_confirm_reabrir", use_container_width=True):
                    with SessionLocal() as _s:
                        reabrir_ciclo(_s, _ciclo_id)
                    st.rerun()

        @st.dialog(f"Remover ciclo de {periodo_label}?")
        def _modal_remover_ciclo_enc():
            st.error(
                f"Esta ação excluirá permanentemente este ciclo e "
                f"**{_respondidos} formulário{'s' if _respondidos != 1 else ''}** recebido{'s' if _respondidos != 1 else ''}. "
                "Esta ação não pode ser desfeita."
            )
            _mre1, _mre2 = st.columns(2)
            with _mre1:
                if st.button("Cancelar", key="btn_modal_cancel_rem_enc", use_container_width=True):
                    st.rerun()
            with _mre2:
                if st.button("Remover ciclo", type="primary", key="btn_modal_confirm_rem_enc", use_container_width=True):
                    with SessionLocal() as _s:
                        deletar_ciclo(_s, _ciclo_id)
                    st.rerun()

        with st.container(border=True):
            # Cabeçalho
            st.markdown(
                f"**{periodo_label}**&nbsp;"
                f"<span style='background:#6B7280;color:#fff;font-size:11px;"
                f"font-weight:600;padding:2px 8px;border-radius:10px;margin-left:4px;'>ENCERRADA</span>"
                f"&nbsp;&nbsp;<span style='font-size:13px;color:#6B7280;'>Encerrada em {_enc_txt}</span>",
                unsafe_allow_html=True,
            )

            # Indicadores
            _ind1, _ind2, _ind3, _ind4 = st.columns(4)
            _ind1.metric("Setores", _total_set)
            _ind2.metric("Respondidos", _respondidos)
            _ind3.metric("Sem resposta", _pendentes)
            _ind4.metric("Concluído", f"{_concluido_pct_enc}%")
            st.progress(_concluido_pct_enc / 100)

            st.markdown("")
            st.caption("Solicitações encerradas. Os dados estão disponíveis para consolidação.")
            st.markdown("")

            # Barra de ações
            _, _ac1, _ac2 = st.columns([2, 1, 1])
            with _ac1:
                if _periodo_tipo == "atual":
                    if st.button("Reabrir coleta", key="btn_reabrir_ciclo", use_container_width=True):
                        _modal_reabrir_coleta()
            with _ac2:
                if st.button("Remover ciclo", key="btn_remover_ciclo_enc", use_container_width=True, type="secondary"):
                    _modal_remover_ciclo_enc()

    st.markdown("---")

    _sol_readonly = (_periodo_tipo != "atual")
    if _sol_readonly:
        _lock_icon = "🚫" if _periodo_tipo == "futuro" else "🔒"
        _lock_msg  = "Período futuro" if _periodo_tipo == "futuro" else "Período encerrado"
        st.warning(f"{_lock_msg} — solicitações em modo somente leitura.", icon=_lock_icon)

    # ── Auto-classificação: só executa no período atual ───────────────────────
    with SessionLocal() as _s:
        _raw = listar_solicitacoes(_s, periodo)
        if not _sol_readonly and any(s.status in {
            "pendente", "sem_parametros", "novo_item",
            "pendente_parametrizacao", "pendente_cadastro",  # legado
        } for s in _raw):
            classificar_solicitacoes_periodo(_s, periodo)
        todas_sols = listar_solicitacoes(_s, periodo)

    if not todas_sols:
        empty_state("📝", "Nenhuma pendência", f"Nenhuma solicitação ou item sem parâmetros para {periodo_label}.")
    else:
        # ── Agrupamento por pedido ────────────────────────────────────────────
        grupos: dict = defaultdict(list)
        for sol in todas_sols:
            _gk = sol.pedido_id if sol.pedido_id is not None else f"leg_{sol.setor_id}_{sol.solicitante}"
            grupos[_gk].append(sol)

        # Ordena grupos por data de criação do primeiro item
        grupos_ordenados = sorted(
            grupos.items(),
            key=lambda kv: min(s.criado_em for s in kv[1]),
        )

        # Conta quantos pedidos cada setor tem (para badge "2º Envio", "3º Envio"...)
        _setor_pedido_count: dict[str, list] = defaultdict(list)
        for _gk2, _gs2 in grupos_ordenados:
            _sn2 = _gs2[0].setor.nome if _gs2[0].setor else "—"
            _setor_pedido_count[_sn2].append(_gk2)

        # ── KPIs ──────────────────────────────────────────────────────────────
        n_formularios = len(grupos)
        n_prontos     = sum(1 for s in todas_sols if s.status == "validada")
        n_aprovadas   = sum(1 for s in todas_sols if s.status == "aprovada")
        n_rejeitadas  = sum(1 for s in todas_sols if s.status == "rejeitada")
        n_novos       = sum(1 for s in todas_sols if s.status in {"novo_item", "pendente_cadastro"})
        n_sem_param   = sum(1 for s in todas_sols if s.status in {"sem_parametros", "pendente_parametrizacao"})

        n_urgentes = sum(1 for s in todas_sols if s.urgente)
        col_m1, col_m2, col_m3, col_m4, col_m5, col_m6, col_m7 = st.columns(7)
        col_m1.metric("📋 Formulários",      n_formularios)
        col_m2.metric("🔴 Urgentes",         n_urgentes)
        col_m3.metric("⏳ Para revisar",     n_prontos)
        col_m4.metric("✅ Aprovadas",        n_aprovadas)
        col_m5.metric("❌ Rejeitadas",       n_rejeitadas)
        col_m6.metric("🆕 Novos Itens",      n_novos)
        col_m7.metric("⚙️ Sem Parâmetros",   n_sem_param)

        if n_aprovadas > 0 and not _sol_readonly:
            st.info(
                f"{n_aprovadas} solicitação(ões) aprovada(s) aguardando Consolidação. "
                "Execute **Análise Mensal de Compras** para incluí-las.",
                icon="ℹ️",
            )

        # ── Helpers ───────────────────────────────────────────────────────────
        _STATUS_BADGE_MAP = {
            "validada":                ("⏳ Para Revisar",   "#17a2b8"),
            "aprovada":                ("✅ Aprovada",       "#28a745"),
            "rejeitada":               ("❌ Rejeitada",      "#dc3545"),
            "pendente":                ("⏳ Pendente",       "#6c757d"),
            "novo_item":               ("🆕 Novo Item",      "#fd7e14"),
            "sem_parametros":          ("⚙️ Sem Parâmetros", "#6f42c1"),
            "pendente_cadastro":       ("🆕 Novo Item",      "#fd7e14"),       # legado
            "pendente_parametrizacao": ("⚙️ Sem Parâmetros", "#6f42c1"),      # legado
            "compra_avulsa_aprovada":  ("🛒 Compra Avulsa",  "#20c997"),
        }

        def _badge(status: str) -> str:
            label, cor = _STATUS_BADGE_MAP.get(status, (status, "#6c757d"))
            return (
                f"<span style='background:{cor}22;color:{cor};padding:2px 8px;"
                f"border-radius:4px;font-size:12px;font-weight:600;'>{label}</span>"
            )

        def _resumo_grupo(sols: list) -> str:
            partes = []
            n_u = sum(1 for s in sols if s.urgente)
            n_v = sum(1 for s in sols if s.status == "validada")
            n_a = sum(1 for s in sols if s.status == "aprovada")
            n_r = sum(1 for s in sols if s.status == "rejeitada")
            n_n = sum(1 for s in sols if s.status in {"novo_item", "pendente_cadastro"})
            n_s = sum(1 for s in sols if s.status in {"sem_parametros", "pendente_parametrizacao"})
            n_p = sum(1 for s in sols if s.status == "pendente")
            if n_u: partes.append(f"🔴 {n_u} urgente(s)")
            if n_v: partes.append(f"⏳ {n_v} p/ revisar")
            if n_a: partes.append(f"✅ {n_a} aprovado(s)")
            if n_r: partes.append(f"❌ {n_r} rejeitado(s)")
            if n_n: partes.append(f"🆕 {n_n} novo(s)")
            if n_s: partes.append(f"⚙️ {n_s} sem parâm.")
            if n_p: partes.append(f"⏳ {n_p} pendente(s)")
            return " · ".join(partes) if partes else "—"

        # ── Documentos ────────────────────────────────────────────────────────
        if todas_sols:
            section_title("Formulários Recebidos")

        for _gkey, sols in grupos_ordenados:
            setor_nome  = sols[0].setor.nome if sols[0].setor else "—"
            solicitante = sols[0].solicitante
            data_doc    = max(s.criado_em for s in sols).strftime("%d/%m/%Y")
            n_itens     = len(sols)
            resumo      = _resumo_grupo(sols)
            _PENDENTE_STATUS = {
                "validada", "novo_item", "sem_parametros", "pendente",
                "pendente_cadastro", "pendente_parametrizacao",
            }
            pendentes_grupo = any(s.status in _PENDENTE_STATUS for s in sols)
            aprovadas_grupo = [s for s in sols if s.status == "aprovada"]
            concluido       = not pendentes_grupo
            sufixo_label    = "  · ✅ Concluído" if concluido else ""

            # Badge de envio múltiplo (aparece só quando o setor enviou mais de uma vez)
            _pedidos_setor = _setor_pedido_count.get(setor_nome, [])
            _envio_idx     = _pedidos_setor.index(_gkey) + 1 if _gkey in _pedidos_setor else 1
            _badge_envio   = f"  ·  {_envio_idx}º Envio" if len(_pedidos_setor) > 1 else ""

            if concluido:
                label_exp = (
                    f"{setor_nome}  ·  {solicitante}  ·  {data_doc}"
                    f"  —  {n_itens} item(ns)  ·  ✅ Concluído{_badge_envio}"
                )
            else:
                label_exp = (
                    f"{setor_nome}  ·  {solicitante}  ·  {data_doc}"
                    f"  —  {n_itens} item(ns)  ·  {resumo}{_badge_envio}"
                )

            _exp_key = f"exp_open_{_gkey}"
            with st.expander(label_exp, expanded=st.session_state.get(_exp_key, False)):
                # ── Caption de estado ─────────────────────────────────────────
                if concluido:
                    st.caption("✅ Revisão concluída. Execute Análise Mensal para incluir as aprovações.")
                else:
                    st.caption("⚠️ Revise cada item solicitado para uma aprovação mais precisa e confiável.")

                st.markdown("<div style='height:4px;'></div>", unsafe_allow_html=True)

                if _sol_readonly:
                    ch1, ch2, ch3, ch4 = st.columns([4, 1, 3, 2])
                else:
                    ch1, ch2, ch3, ch4, _, _ = st.columns([4, 1, 3, 2, 1, 1])
                ch1.caption("Item")
                ch2.caption("Qtd")
                ch3.caption("Observação")
                ch4.caption("Status")

                for sol in sols:
                    nome_item    = sol.item.nome if sol.item else (sol.nome_item_livre or "—")
                    obs          = sol.observacao or "—"
                    urgente_html = (
                        " <span style='color:#dc2626;font-size:11px;font-weight:700;'>🔴 URGENTE</span>"
                        if sol.urgente else ""
                    )
                    if _sol_readonly:
                        c1, c2, c3, c4 = st.columns([4, 1, 3, 2])
                    else:
                        c1, c2, c3, c4, c_acao, c_rm = st.columns([4, 1, 3, 2, 1, 1])
                    c1.markdown(f"**{nome_item}**{urgente_html}", unsafe_allow_html=True)
                    c2.markdown(str(sol.quantidade_solicitada))
                    c3.caption(obs if obs != "—" else "")
                    c4.markdown(_badge(sol.status), unsafe_allow_html=True)

                    if not _sol_readonly:
                        if sol.status == "validada":
                            if c_acao.button("✓", key=f"aceitar_sol_{sol.id}", help="Aprovar esta solicitação", use_container_width=True):
                                with SessionLocal() as _s:
                                    aprovar_solicitacao(_s, sol.id)
                                st.session_state[_exp_key] = True
                                st.rerun()
                            if c_rm.button("✗", key=f"rejeitar_sol_{sol.id}", help="Rejeitar esta solicitação", use_container_width=True):
                                with SessionLocal() as _s:
                                    rejeitar_solicitacao(_s, sol.id)
                                st.session_state[_exp_key] = True
                                st.rerun()
                        elif sol.status in {"aprovada", "rejeitada"}:
                            if c_acao.button("↩", key=f"desfazer_sol_{sol.id}", help="Desfazer — reverter para revisão", use_container_width=True):
                                with SessionLocal() as _s:
                                    revertir_solicitacao(_s, sol.id)
                                st.session_state[_exp_key] = True
                                st.rerun()
                            if c_rm.button("🗑️", key=f"del_sol_doc_{sol.id}", help="Remover este item", use_container_width=True):
                                with SessionLocal() as _s:
                                    deletar_solicitacao(_s, sol.id)
                                st.session_state[_exp_key] = True
                                st.rerun()
                        else:
                            if sol.status in {"novo_item", "pendente_cadastro"}:
                                if c_acao.button("📝", key=f"abrir_novo_{sol.id}", help=f'Resolver: cadastrar ou vincular "{sol.nome_item_livre or nome_item}"', use_container_width=True):
                                    _modal_novo_item(sol, periodo, _exp_key)
                            elif sol.status in {"sem_parametros", "pendente_parametrizacao"}:
                                _mk_sp = f"modal_sp_{sol.id}"
                                if c_acao.button("⚙️", key=f"abrir_sp_{sol.id}", help=f'Definir mínimo/ideal para "{nome_item}"', use_container_width=True):
                                    st.session_state[_mk_sp] = True
                                    st.session_state[_exp_key] = True
                                    st.rerun()
                            elif sol.status == "compra_avulsa_aprovada":
                                if c_acao.button("↩", key=f"desfazer_avulsa_{sol.id}", help="Desfazer compra avulsa — voltar como Novo Item", use_container_width=True):
                                    with SessionLocal() as _s:
                                        desfazer_compra_avulsa(_s, sol.id)
                                    st.session_state[_exp_key] = True
                                    st.rerun()
                            if c_rm.button("🗑️", key=f"del_sol_doc_{sol.id}", help="Remover este item", use_container_width=True):
                                with SessionLocal() as _s:
                                    deletar_solicitacao(_s, sol.id)
                                st.session_state[_exp_key] = True
                                st.rerun()

                    # ── Modal: Definir Parâmetros (Sem Parâmetros) ────────────
                    if not _sol_readonly and sol.status in {"sem_parametros", "pendente_parametrizacao"} and st.session_state.get(f"modal_sp_{sol.id}"):
                        with st.container(border=True):
                            st.markdown(f"**Definir parâmetros para: {nome_item}**")
                            _sp1, _sp2 = st.columns(2)
                            _sp_min   = _sp1.number_input("Estoque mínimo", min_value=0, value=0, step=1, key=f"sp_min_{sol.id}")
                            _sp_ideal = _sp2.number_input("Estoque ideal",  min_value=max(0, _sp_min), value=max(0, _sp_min) if _sp_min > 0 else 0, step=1, key=f"sp_ideal_{sol.id}")
                            _erros_sp = []
                            if _sp_ideal > 0 and _sp_min == 0:
                                _erros_sp.append("Se ideal > 0, mínimo deve ser > 0.")
                            if _sp_ideal > 0 and _sp_ideal < _sp_min:
                                _erros_sp.append("Ideal deve ser ≥ mínimo.")
                            if _erros_sp:
                                st.warning("  \n".join(_erros_sp))
                            _col_sp_ok, _col_sp_can, _ = st.columns([1, 1, 4])
                            _sem_valor = _sp_min == 0 and _sp_ideal == 0
                            if _col_sp_ok.button("Salvar Parâmetros", key=f"sp_salvar_{sol.id}", type="primary", disabled=bool(_erros_sp) or _sem_valor):
                                with SessionLocal() as _s2:
                                    _n = aplicar_parametros_e_reclassificar(_s2, sol.item_id, _sp_min, _sp_ideal, periodo)
                                st.success(f"Parâmetros salvos e {_n} solicitação(ões) aprovada(s).")
                                st.session_state.pop(f"modal_sp_{sol.id}", None)
                                st.session_state[_exp_key] = True
                                st.rerun()
                            if _col_sp_can.button("Cancelar", key=f"sp_can_{sol.id}"):
                                st.session_state.pop(f"modal_sp_{sol.id}", None)
                                st.session_state[_exp_key] = True
                                st.rerun()

                # ── Ações do formulário (apenas no período atual) ─────────────
                if not _sol_readonly:
                    validadas_grupo  = [s for s in sols if s.status == "validada"]
                    _confirm_key     = f"confirm_del_{_gkey}"
                    _aguard_confirm  = st.session_state.get(_confirm_key, False)

                    st.markdown("<div style='height:6px;'></div>", unsafe_allow_html=True)
                    col_apr_doc, col_del_doc, _ = st.columns([2, 2, 2])

                    with col_apr_doc:
                        if validadas_grupo:
                            if st.button(
                                "Aprovar Pedidos",
                                key=f"apr_doc_{_gkey}",
                                type="primary",
                                use_container_width=True,
                                help="Aprova todos os itens validados deste formulário",
                            ):
                                with SessionLocal() as _s:
                                    for sol_v in validadas_grupo:
                                        aprovar_solicitacao(_s, sol_v.id)
                                st.session_state[_exp_key] = True
                                st.rerun()
                        elif aprovadas_grupo:
                            st.success("✅ Pedidos aprovados")

                    with col_del_doc:
                        if not _aguard_confirm:
                            if st.button(
                                "Excluir Formulário",
                                key=f"del_doc_{_gkey}",
                                use_container_width=True,
                                help="Remove todos os itens deste formulário permanentemente",
                            ):
                                st.session_state[_confirm_key] = True
                                st.session_state[_exp_key] = True
                                st.rerun()
                        else:
                            st.caption("▼ Confirme abaixo")

                    if _aguard_confirm:
                        n_total = len(sols)
                        n_aprov = len(aprovadas_grupo)
                        _aviso  = (
                            f"Esta ação removerá **{n_total} item(ns)** permanentemente "
                            "e **não poderá ser desfeita**."
                        )
                        if n_aprov:
                            _aviso += f" **{n_aprov} item(ns) aprovado(s) serão perdidos.**"
                        st.warning(_aviso, icon="⚠️")
                        c_conf, c_canc, _ = st.columns([2, 2, 2])
                        if c_conf.button(
                            "Sim, excluir tudo",
                            key=f"confirm_yes_{_gkey}",
                            type="primary",
                            use_container_width=True,
                        ):
                            with SessionLocal() as _s:
                                for sol in sols:
                                    deletar_solicitacao(_s, sol.id)
                            st.session_state.pop(_confirm_key, None)
                            st.rerun()
                        if c_canc.button(
                            "Cancelar",
                            key=f"confirm_no_{_gkey}",
                            use_container_width=True,
                        ):
                            st.session_state[_confirm_key] = False
                            st.session_state[_exp_key] = True
                            st.rerun()


# =============================================================================
# ABA 3 — CONSOLIDAÇÃO
# =============================================================================
elif aba == "Consolidação":

    with SessionLocal() as _cs_conso_ciclo:
        _ciclo_conso = get_ciclo_por_periodo(_cs_conso_ciclo, periodo)
        _ciclo_id = _ciclo_conso.id if _ciclo_conso else None

    if _periodo_tipo == "futuro":
        empty_state(
            "🚫",
            "Período futuro",
            "Não é possível analisar ou visualizar consolidações de períodos futuros. "
            "Selecione o mês atual.",
        )
        st.stop()

    _consolidacao_readonly = (_periodo_tipo == "passado")
    if _consolidacao_readonly:
        st.info("🔒 Período encerrado — visualização somente leitura.", icon="🔒")

    with SessionLocal() as _s_conso:
        _sols_conso = listar_solicitacoes(_s_conso, periodo)
    _n_sols_pendentes = sum(
        1 for s in _sols_conso if s.status in {
            "novo_item", "sem_parametros",
            "pendente_cadastro", "pendente_parametrizacao",  # legado
        }
    )

    # ── Tabela de consolidação ────────────────────────────────────────────────
    if not itens_lista:
        empty_state(
            "🔗",
            "Sem análise para este período",
            "Clique em 'Análise Mensal de Compras' para cruzar estoque e solicitações.",
        )
    else:
        para_compra     = [x for x in itens_lista if (x.quantidade_sugerida or 0) > 0]
        sem_param_conso = [x for x in itens_lista if x.status in {"sem_parametro", "sem_minimo_definido"}]

        avulsas_periodo = avulsas_lista

        if para_compra or avulsas_periodo:
            section_title("Itens para Decisão de Compra")
            _avisos_conso = []
            if sem_param_conso:
                _avisos_conso.append(f"{len(sem_param_conso)} item(ns) sem parâmetros")
            if _n_sols_pendentes:
                _avisos_conso.append(f"{_n_sols_pendentes} solicitação(ões) pendente(s)")
            if _avisos_conso:
                st.caption(
                    f"⚠️ {' · '.join(_avisos_conso)} — "
                    f"resolva em **Editar** ou **Solicitações e Pendências** e rode novamente a análise."
                )
            st.caption(
                "Edite 'Qtd Final' para compra, quando necessário. "
                "Marque 'Incluir na Lista' e clique em Salvar para aprovar."
                "O campo 'Motivo do Sistema' explica o raciocínio por trás da quantidade sugerida. "
            )

            rows_ed = []
            for x in para_compra:
                rows_ed.append({
                    "_id":  x.id,
                    "_tipo": "lista",
                    "Status": _STATUS_LABEL.get(x.status, x.status),
                    "Item": x.item.nome if x.item else "—",
                    "Estoque": x.estoque_atual_snap,
                    "Mín.": x.estoque_minimo_snap,
                    "Ideal": x.estoque_ideal_snap,
                    "Solicitado": x.total_solicitado,
                    "Qtd Sugerida": x.quantidade_sugerida,
                    "Qtd Final": (
                        x.quantidade_final_definida
                        if x.quantidade_final_definida is not None
                        else x.quantidade_sugerida
                    ),
                    "Incluir na Lista": x.incluir_na_lista_final,
                    "Motivo do Sistema": x.motivo_sugestao or "—",
                })
            for ca in avulsas_periodo:
                _motivo_av = (
                    f"Compra pontual aprovada"
                    f"{' · Urgente' if ca.urgente else ''}"
                    f" · Solicitante: {ca.solicitante}"
                )
                rows_ed.append({
                    "_id":  ca.id,
                    "_tipo": "avulsa",
                    "Status": "Compra Avulsa",
                    "Item": ca.nome_item,
                    "Estoque": float("nan"),
                    "Mín.": float("nan"),
                    "Ideal": float("nan"),
                    "Solicitado": ca.quantidade,
                    "Qtd Sugerida": float("nan"),
                    "Qtd Final": ca.quantidade,
                    "Incluir na Lista": ca.incluir_na_lista_final,
                    "Motivo do Sistema": _motivo_av,
                })

            _col_order = ["_id", "Status", "Item", "Estoque", "Mín.", "Ideal",
                          "Solicitado", "Qtd Sugerida", "Qtd Final", "Incluir na Lista", "Motivo do Sistema"]
            df_ed = pd.DataFrame(rows_ed)
            col_config = {
                "_id":              st.column_config.NumberColumn("ID", disabled=True),
                "_tipo":            None,
                "Status":           st.column_config.TextColumn("Status", disabled=True),
                "Item":             st.column_config.TextColumn("Item", disabled=True),
                "Estoque":          st.column_config.NumberColumn("Estoque", disabled=True),
                "Mín.":             st.column_config.NumberColumn("Mín.", disabled=True),
                "Ideal":            st.column_config.NumberColumn("Ideal", disabled=True),
                "Solicitado":       st.column_config.NumberColumn("Solicitado", disabled=True),
                "Qtd Sugerida":     st.column_config.NumberColumn("Qtd Sugerida", disabled=True),
                "Qtd Final":           st.column_config.NumberColumn(
                    "Qtd Final", min_value=1, step=1, required=True,
                    help="Quantidade a comprar — obrigatória e maior que zero.",
                ),
                "Incluir na Lista":    st.column_config.CheckboxColumn("Incluir na Lista"),
                "Motivo do Sistema":   st.column_config.TextColumn("Motivo do Sistema", disabled=True, width="large"),
            }
            _tem_qtd_manual = any(x.quantidade_final_definida is not None for x in itens_lista)

            if _consolidacao_readonly:
                st.dataframe(
                    df_ed,
                    column_config=col_config,
                    column_order=_col_order,
                    hide_index=True,
                    use_container_width=True,
                )
            else:
                _col_btn1, _col_btn2, _col_btn3, _ = st.columns([1, 1.2, 1.5, 7.6])
                with _col_btn1:
                    if st.button("☑ Marcar Todos", key="btn_sel_tudo"):
                        st.session_state["consolidacao_sel_tudo"] = True
                with _col_btn2:
                    if st.button("☐ Desmarcar Todos", key="btn_limpar_sel"):
                        st.session_state["consolidacao_sel_tudo"] = False
                with _col_btn3:
                    if st.button(
                        "↺ Resetar Qtd",
                        key="btn_resetar_qtd",
                        disabled=not _tem_qtd_manual,
                        help="Reverte todas as Qtd Final editadas manualmente para a Qtd Sugerida.",
                    ):
                        st.session_state["consolidacao_confirmar_reset"] = True

                _sel_override = st.session_state.get("consolidacao_sel_tudo")
                if _sel_override is not None:
                    df_ed["Incluir na Lista"] = _sel_override

                edited_df = st.data_editor(
                    df_ed,
                    column_config=col_config,
                    column_order=_col_order,
                    hide_index=True,
                    use_container_width=True,
                    key="consolidacao_editor",
                )

                if st.session_state.get("consolidacao_confirmar_reset"):
                    st.warning(
                        "⚠️ Isso irá reverter **todas as Qtd Final editadas** para a Qtd Sugerida "
                        "e remover os itens da Lista Final. Confirma?",
                    )
                    _col_conf, _col_canc, _ = st.columns([1, 1, 8])
                    with _col_conf:
                        if st.button("Confirmar", type="primary", key="btn_confirmar_reset"):
                            with SessionLocal() as _s_reset:
                                _n_reset = resetar_quantidades_consolidacao(_s_reset, periodo)
                            st.session_state.pop("consolidacao_confirmar_reset", None)
                            st.session_state.pop("consolidacao_sel_tudo", None)
                            st.success(f"{_n_reset} item(ns) resetado(s) para a quantidade sugerida.")
                            st.rerun()
                    with _col_canc:
                        if st.button("Cancelar", key="btn_cancelar_reset"):
                            st.session_state.pop("consolidacao_confirmar_reset", None)
                            st.rerun()

            if not _consolidacao_readonly and st.button("Salvar Alterações", type="primary", key="salvar_consolidacao"):
                # Valida antes de persistir: Qtd Final é obrigatória e >= 1 para
                # itens marcados na lista e para toda compra avulsa. Nada é salvo
                # enquanto houver valor inválido.
                _itens_invalidos = []
                for _, row in edited_df.iterrows():
                    _qtd_invalida = pd.isna(row["Qtd Final"]) or int(row["Qtd Final"]) < 1
                    _exige_qtd = row["_tipo"] == "avulsa" or bool(row["Incluir na Lista"])
                    if _exige_qtd and _qtd_invalida:
                        _itens_invalidos.append(str(row["Item"]))
                if _itens_invalidos:
                    st.error(
                        f"**Nada foi salvo.** Corrija a Qtd Final de: {', '.join(_itens_invalidos)} — "
                        f"o valor é obrigatório e deve ser um número inteiro maior que zero."
                    )
                else:
                    try:
                        with SessionLocal() as _s:
                            # IDs que estão visíveis na tabela agora
                            ids_na_tabela = {int(r["_id"]) for _, r in edited_df.iterrows() if r["_tipo"] == "lista"}
                            # Itens aprovados anteriormente que sumiram da tabela (qtd_sugerida voltou a 0)
                            # precisam ser removidos da lista final para manter consistência
                            for x in get_consolidacao_periodo(_s, periodo):
                                if x.id not in ids_na_tabela and x.incluir_na_lista_final:
                                    remover_da_lista(_s, x.id)
                            # Processa o que está visível na tabela
                            for _, row in edited_df.iterrows():
                                item_id   = int(row["_id"])
                                qtd_final = int(row["Qtd Final"]) if pd.notna(row["Qtd Final"]) else None
                                incluir   = bool(row["Incluir na Lista"])
                                if row["_tipo"] == "avulsa":
                                    atualizar_compra_avulsa(_s, item_id, quantidade=qtd_final, incluir_na_lista_final=incluir)
                                else:
                                    if incluir:
                                        aprovar_item(_s, item_id, qtd_final, None)
                                    else:
                                        remover_da_lista(_s, item_id)
                    except ValueError as _exc_salvar:
                        st.error(f"Não foi possível salvar: {_exc_salvar}")
                    else:
                        st.success("Alterações salvas com sucesso.")
                        st.session_state.pop("consolidacao_sel_tudo", None)
                        st.rerun()

        else:
            if sem_param_conso:
                st.warning(
                    f"**{len(sem_param_conso)} item(ns) sem parâmetros definidos** — o motor não pôde analisar a necessidade de compra destes itens.  \n"
                    f"Configure mínimo/ideal em **Estoque** e rode novamente a **Análise Mensal de Compras**.",
                    icon="⚠️",
                )
            elif _n_sols_pendentes:
                st.warning(
                    f"Estoque adequado para os itens analisados, mas há "
                    f"**{_n_sols_pendentes} solicitação(ões) pendente(s)** que não puderam ser processadas.  \n"
                    f"Resolva as pendências na aba **Solicitações e Pendências** e rode novamente "
                    f"a **Análise Mensal de Compras** para incluí-las.",
                    icon="⚠️",
                )
            else:
                empty_state("✅", "Todos os itens estão com estoque adequado para o período.")

    # ── Lista Final Aprovada ──────────────────────────────────────────────────
    st.divider()
    section_title("Lista Final Aprovada")

    with SessionLocal() as _s:
        lista_final  = get_lista_final(_s, periodo)
        avulsas_final = get_compras_avulsas_periodo(_s, periodo)
        lista_final_info = [
            {
                "item_nome": x.item.nome if x.item else "—",
                "categoria": x.item.categoria.nome if x.item and x.item.categoria else "—",
                "tipo": "Estoque",
                "estoque_atual": x.estoque_atual_snap,
                "qtd_compra": x.quantidade_final_definida or x.quantidade_sugerida,
            }
            for x in lista_final
        ] + [
            {
                "item_nome": ca.nome_item,
                "categoria": "—",
                "tipo": "Compra Avulsa",
                "estoque_atual": None,
                "qtd_compra": ca.quantidade,
            }
            for ca in avulsas_final
        ]

    if not lista_final_info:
        empty_state(
            "✅",
            "Lista final vazia",
            "Aprove itens acima marcando 'Incluir na Lista' e salvando.",
        )
    else:
        st.markdown(
            f"**{len(lista_final_info)} item(ns) aprovado(s) para orçamento — {periodo_label}**"
        )
        rows_final = [
            {
                "Item": info["item_nome"],
                "Categoria": info["categoria"],
                "Tipo": info["tipo"],
                "Estoque Atual": info["estoque_atual"],
                "Qtd Compra": info["qtd_compra"],
            }
            for info in lista_final_info
        ]
        st.dataframe(pd.DataFrame(rows_final), use_container_width=True, hide_index=True)

        df_docx = pd.DataFrame([
            {
                "Item": i["item_nome"],
                "Categoria": i["categoria"],
                "Tipo": i["tipo"],
                "Estoque Atual": i["estoque_atual"],
                "Qtd Compra": i["qtd_compra"],
            }
            for i in lista_final_info
        ])
        caminho_docx = gerar_lista_compras(
            df_docx,
            periodo=periodo_label,
            data_geracao=tempo.hoje().strftime("%d/%m/%Y"),
        )
        with open(caminho_docx, "rb") as f:
            docx_bytes = f.read()
        st.download_button(
            "Baixar Lista de Compras (DOCX)",
            data=docx_bytes,
            file_name=f"lista_compras_{periodo_label}.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            key="download_lista_final",
        )

        # ── Feedback de aprovação para os setores ─────────────────────────────
        if notificacao_service.credenciais_configuradas() and _ciclo_id:
            st.divider()
            section_title("Feedback aos Setores")
            st.caption(
                "Notifica cada setor via WhatsApp com o resumo dos itens aprovados e rejeitados do pedido."
            )

            # Monta feedbacks por setor a partir das solicitações aprovadas/rejeitadas
            with SessionLocal() as _sfb:
                from services.compras_service import listar_solicitacoes as _ls
                _todas_fb = _ls(_sfb, periodo)
                _feedbacks: dict[int, dict] = {}
                for _sol in _todas_fb:
                    if _sol.setor_id is None or _sol.item_id is None:
                        continue
                    nome_item = _sol.item.nome if _sol.item else "—"
                    _entry = _feedbacks.setdefault(_sol.setor_id, {"aprovados": [], "rejeitados": []})
                    if _sol.status == "aprovada":
                        _entry["aprovados"].append(nome_item)
                    elif _sol.status == "rejeitada":
                        _entry["rejeitados"].append(nome_item)

            if _feedbacks:
                if st.button(
                    "📲 Enviar feedback aos setores",
                    key="btn_enviar_feedback",
                    type="primary",
                    help="Envia WhatsApp para cada setor com resumo dos itens aprovados e rejeitados.",
                ):
                    with SessionLocal() as _sfb2:
                        _res_fb = enviar_feedbacks_aprovacao(_sfb2, _ciclo_id, _feedbacks)
                    st.success(
                        f"Feedback enviado: ✅ {_res_fb['enviados']} setor(es) · "
                        f"❌ {_res_fb['falhas_api']} falhas · "
                        f"⚠️ {_res_fb['sem_whatsapp']} sem WhatsApp"
                    )
            else:
                st.caption("Nenhuma solicitação aprovada ou rejeitada encontrada para este período.")


