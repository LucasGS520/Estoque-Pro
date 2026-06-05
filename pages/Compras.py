""" Tela da camada de Compras — governança da necessidade de compra.

Fluxo: seleção de período → solicitações (formulário externo /solicitar) →
classificar → consolidar → revisar painel → lista final.
"""

import calendar
import datetime
from collections import defaultdict

import pandas as pd
import streamlit as st

from core.database import get_session_factory
from core.ui import empty_state, fmt_brl, page_header, section_title, setup_page
from services.compras_service import (
    aprovar_item,
    aprovar_solicitacao,
    rejeitar_solicitacao,
    revertir_solicitacao,
    classificar_solicitacoes_periodo,
    consolidar_periodo,
    deletar_solicitacao,
    get_consolidacao_periodo,
    get_lista_final,
    get_painel_reposicao,
    get_periodos_com_consolidacao,
    listar_solicitacoes,
    remover_da_lista,
)
from documents.lista_compras import gerar_lista_compras
from services.estoque_service import get_categorias

setup_page("Compras", "🛒")
page_header("Compras", subtitle="Governança da necessidade de compra.")

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
</style>
""", unsafe_allow_html=True)

SessionLocal = get_session_factory()

MESES_PT = {
    1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril",
    5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto",
    9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro",
}

_STATUS_LABEL = {
    "zerado":              "Zerado",
    "abaixo_minimo":       "Abaixo do Mínimo",
    "ok":                  "OK",
    "excesso":             "Excesso",
    "sem_parametro":       "Sem Parâmetro",
    # Legado (registros antigos na BD)
    "comprar":             "Abaixo do Mínimo",
    "sem_minimo_definido": "Sem Parâmetro",
}

# ── Seletor de período ────────────────────────────────────────────────────────
section_title("Período de Referência")

hoje = datetime.date.today()
anos_disponiveis = list(range(hoje.year - 2, hoje.year + 2))

col_mes, col_ano, col_btn = st.columns([2, 1, 2])
with col_mes:
    mes_sel = st.selectbox(
        "Mês",
        options=list(MESES_PT.keys()),
        format_func=lambda m: MESES_PT[m],
        index=hoje.month - 1,
        key="sel_mes",
        label_visibility="collapsed",
    )
with col_ano:
    ano_sel = st.selectbox(
        "Ano",
        options=anos_disponiveis,
        index=anos_disponiveis.index(hoje.year),
        key="sel_ano",
        label_visibility="collapsed",
    )
periodo           = datetime.date(ano_sel, mes_sel, 1)
periodo_label     = f"{MESES_PT[mes_sel]}/{ano_sel}"
_periodo_atual_ref = datetime.date(hoje.year, hoje.month, 1)
_periodo_tipo     = (
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
    itens_lista = get_consolidacao_periodo(_s, periodo)
    painel_lista = get_painel_reposicao(_s)
    cats = get_categorias(_s)
    cat_nomes = ["Todas"] + sorted({r.categoria for r in painel_lista if r.categoria})

_ultimo_dia    = calendar.monthrange(ano_sel, mes_sel)[1]
_janela_inicio = f"01/{mes_sel:02d}/{ano_sel}"
_janela_fim    = (
    f"hoje ({hoje.strftime('%d/%m/%Y')})"
    if _periodo_tipo == "atual"
    else f"{_ultimo_dia:02d}/{mes_sel:02d}/{ano_sel}"
)

if _periodo_tipo == "futuro":
    st.error(
        f"🚫 **Período futuro** — não é possível executar análises para **{periodo_label}**. "
        "Selecione o mês atual.",
        icon="🚫",
    )
elif periodo in periodos_existentes:
    _ultima_analise = max((x.atualizado_em for x in itens_lista), default=None)
    _n_total        = len(itens_lista)
    _n_comprar      = sum(1 for x in itens_lista if x.status in {"zerado", "abaixo_minimo", "comprar"})
    _n_sem_min      = sum(1 for x in itens_lista if x.status in {"sem_parametro", "sem_minimo_definido"})
    _n_lista_final  = sum(1 for x in itens_lista if x.incluir_na_lista_final)
    _data_str       = _ultima_analise.strftime("%d/%m/%Y às %H:%M") if _ultima_analise else "—"
    _sem_min_str    = f" · ⚠️ {_n_sem_min} sem mínimo/ideal" if _n_sem_min else ""
    _lock_str       = "  \n🔒 Período encerrado — somente leitura" if _periodo_tipo == "passado" else ""
    _banner_icon    = "⚠️" if _n_sem_min else "✅"
    st.info(
        f"**Análise Mensal — {periodo_label}**  \n"
        f"📅 Janela: {_janela_inicio} – {_janela_fim} · Última análise: {_data_str}  \n"
        f"🔢 {_n_total} item(ns) analisado(s) · {_n_comprar} a comprar{_sem_min_str} · {_n_lista_final} aprovado(s) na lista final{_lock_str}",
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

if consolidar:
    _aba_atual = st.session_state.get("compras_aba", "Painel de Reposição")
    with st.spinner("Analisando período..."):
        with SessionLocal() as _s:
            results, summary = consolidar_periodo(_s, periodo)
    st.success(
        f"Análise de **{periodo_label}** concluída — "
        f"{summary.itens_zerados} zerado(s) · "
        f"{summary.itens_abaixo_minimo} abaixo do mínimo · "
        f"{summary.itens_excesso} em excesso"
    )
    st.session_state["compras_aba"] = _aba_atual
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
        zerados      = [r for r in painel_lista if r.status.value == "zerado"]
        abaixo_min   = [r for r in painel_lista if r.status.value == "abaixo_minimo"]
        excesso_list = [r for r in painel_lista if r.status.value == "excesso"]
        ok_list      = [r for r in painel_lista if r.status.value == "ok"]
        sem_param    = [r for r in painel_lista if r.status.value == "sem_parametro"]

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Zerados",         len(zerados))
        c2.metric("Abaixo do Mín.",  len(abaixo_min))
        c3.metric("Excesso",         len(excesso_list))
        c4.metric("OK",              len(ok_list))
        c5.metric("Sem Parâmetro",   len(sem_param))

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
                "Sem Parâmetro": "sem_parametro",
                "OK": "ok",
            }
            status_sel = st.selectbox("Status", list(status_opcoes.keys()), key="painel_status")

        STATUS_PAINEL = {"zerado", "abaixo_minimo", "sem_parametro", "ok"}
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

        if excesso_list:
            with st.expander(f"⚠️ {len(excesso_list)} item(ns) com excesso de estoque"):
                rows_exc = []
                for r in excesso_list:
                    rows_exc.append({
                        "Item": r.nome,
                        "Categoria": r.categoria,
                        "Estoque": r.qtd_atual,
                        "Ideal": r.estoque_ideal,
                    })
                st.dataframe(pd.DataFrame(rows_exc), use_container_width=True, hide_index=True)
                st.caption("Itens com estoque acima do ideal. Não entram na lista de compras.")

# =============================================================================
# ABA 2 — SOLICITAÇÕES
# =============================================================================
elif aba == "Solicitações e Pendências":

    # ── Link do formulário externo ────────────────────────────────────────────
    st.info(
        "**Formulário de Solicitação Externa** — Compartilhe o link abaixo com os setores:\n\n"
        "`http://localhost:8501/solicitar`",
        icon="🔗",
    )

    st.markdown("---")

    _sol_readonly = (_periodo_tipo != "atual")
    if _sol_readonly:
        _lock_icon = "🚫" if _periodo_tipo == "futuro" else "🔒"
        _lock_msg  = "Período futuro" if _periodo_tipo == "futuro" else "Período encerrado"
        st.warning(f"{_lock_icon} {_lock_msg} — solicitações em modo somente leitura.", icon=_lock_icon)

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
        # ── Agrupamento por (setor, solicitante) ──────────────────────────────
        grupos: dict = defaultdict(list)
        for sol in todas_sols:
            chave = (sol.setor.nome if sol.setor else "—", sol.solicitante)
            grupos[chave].append(sol)
        grupos = dict(sorted(grupos.items()))

        # ── KPIs ──────────────────────────────────────────────────────────────
        n_formularios = len(grupos)
        n_prontos     = sum(1 for s in todas_sols if s.status == "validada")
        n_aprovadas   = sum(1 for s in todas_sols if s.status == "aprovada")
        n_rejeitadas  = sum(1 for s in todas_sols if s.status == "rejeitada")
        n_novos       = sum(1 for s in todas_sols if s.status in {"novo_item", "pendente_cadastro"})
        n_sem_param   = sum(1 for s in todas_sols if s.status in {"sem_parametros", "pendente_parametrizacao"})

        col_m1, col_m2, col_m3, col_m4, col_m5, col_m6 = st.columns(6)
        col_m1.metric("📋 Formulários",      n_formularios)
        col_m2.metric("⏳ Para revisar",     n_prontos)
        col_m3.metric("✅ Aprovadas",        n_aprovadas)
        col_m4.metric("❌ Rejeitadas",       n_rejeitadas)
        col_m5.metric("🆕 Novos Itens",      n_novos)
        col_m6.metric("⚙️ Sem Parâmetros",   n_sem_param)

        if n_aprovadas > 0 and not _sol_readonly:
            st.info(
                f"✅ {n_aprovadas} solicitação(ões) aprovada(s) aguardando Consolidação. "
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
        }

        def _badge(status: str) -> str:
            label, cor = _STATUS_BADGE_MAP.get(status, (status, "#6c757d"))
            return (
                f"<span style='background:{cor}22;color:{cor};padding:2px 8px;"
                f"border-radius:4px;font-size:12px;font-weight:600;'>{label}</span>"
            )

        def _resumo_grupo(sols: list) -> str:
            partes = []
            n_v = sum(1 for s in sols if s.status == "validada")
            n_a = sum(1 for s in sols if s.status == "aprovada")
            n_r = sum(1 for s in sols if s.status == "rejeitada")
            n_n = sum(1 for s in sols if s.status in {"novo_item", "pendente_cadastro"})
            n_s = sum(1 for s in sols if s.status in {"sem_parametros", "pendente_parametrizacao"})
            n_p = sum(1 for s in sols if s.status == "pendente")
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

        for (setor_nome, solicitante), sols in grupos.items():
            data_doc     = max(s.criado_em for s in sols).strftime("%d/%m/%Y")
            n_itens      = len(sols)
            resumo       = _resumo_grupo(sols)
            _PENDENTE_STATUS = {
                "validada", "novo_item", "sem_parametros", "pendente",
                "pendente_cadastro", "pendente_parametrizacao",
            }
            pendentes_grupo  = any(s.status in _PENDENTE_STATUS for s in sols)
            aprovadas_grupo  = [s for s in sols if s.status == "aprovada"]
            concluido        = not pendentes_grupo
            sufixo_label     = "  · ✅ Concluído" if concluido else ""
            label_exp        = (
                f"🏢  {setor_nome}  ·  {solicitante}  ·  {data_doc}"
                f"  —  {n_itens} item(ns)  ·  {resumo}{sufixo_label}"
            )

            with st.expander(label_exp):
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
                    nome_item = sol.item.nome if sol.item else (sol.nome_item_livre or "—")
                    obs       = sol.observacao or "—"
                    if _sol_readonly:
                        c1, c2, c3, c4 = st.columns([4, 1, 3, 2])
                    else:
                        c1, c2, c3, c4, c_acao, c_rm = st.columns([4, 1, 3, 2, 1, 1])
                    c1.markdown(f"**{nome_item}**")
                    c2.markdown(str(sol.quantidade_solicitada))
                    c3.caption(obs if obs != "—" else "")
                    c4.markdown(_badge(sol.status), unsafe_allow_html=True)

                    if not _sol_readonly:
                        if sol.status == "validada":
                            if c_acao.button("✓", key=f"aceitar_sol_{sol.id}", help="Aprovar esta solicitação", use_container_width=True):
                                with SessionLocal() as _s:
                                    aprovar_solicitacao(_s, sol.id)
                                st.rerun()
                            if c_rm.button("✗", key=f"rejeitar_sol_{sol.id}", help="Rejeitar esta solicitação", use_container_width=True):
                                with SessionLocal() as _s:
                                    rejeitar_solicitacao(_s, sol.id)
                                st.rerun()
                        elif sol.status in {"aprovada", "rejeitada"}:
                            if c_acao.button("↩", key=f"desfazer_sol_{sol.id}", help="Desfazer — reverter para revisão", use_container_width=True):
                                with SessionLocal() as _s:
                                    revertir_solicitacao(_s, sol.id)
                                st.rerun()
                            if c_rm.button("🗑️", key=f"del_sol_doc_{sol.id}", help="Remover este item", use_container_width=True):
                                with SessionLocal() as _s:
                                    deletar_solicitacao(_s, sol.id)
                                st.rerun()
                        else:
                            if sol.status in {"novo_item", "pendente_cadastro"}:
                                if c_acao.button("📝", key=f"nav_cad_{sol.id}", help=f'Cadastrar "{sol.nome_item_livre or nome_item}" em Estoque → Editar → Itens', use_container_width=True):
                                    st.session_state["estoque_tab"] = "Editar"
                                    st.session_state["estoque_subtab"] = "Itens"
                                    st.switch_page("pages/Estoque.py")
                            elif sol.status in {"sem_parametros", "pendente_parametrizacao"}:
                                if c_acao.button("⚙️", key=f"nav_param_{sol.id}", help=f'Configurar parâmetros de "{nome_item}" em Estoque → Editar → Itens', use_container_width=True):
                                    st.session_state["estoque_tab"] = "Editar"
                                    st.session_state["estoque_subtab"] = "Itens"
                                    st.switch_page("pages/Estoque.py")
                            if c_rm.button("🗑️", key=f"del_sol_doc_{sol.id}", help="Remover este item", use_container_width=True):
                                with SessionLocal() as _s:
                                    deletar_solicitacao(_s, sol.id)
                                st.rerun()

                # ── Ações do formulário (apenas no período atual) ─────────────
                if not _sol_readonly:
                    validadas_grupo  = [s for s in sols if s.status == "validada"]
                    _confirm_key     = f"confirm_del_{setor_nome}_{solicitante}"
                    _aguard_confirm  = st.session_state.get(_confirm_key, False)

                    st.markdown("<div style='height:6px;'></div>", unsafe_allow_html=True)
                    col_apr_doc, col_del_doc, _ = st.columns([2, 2, 2])

                    with col_apr_doc:
                        if validadas_grupo:
                            if st.button(
                                "Aprovar Pedidos",
                                key=f"apr_doc_{setor_nome}_{solicitante}",
                                type="primary",
                                use_container_width=True,
                                help="Aprova todos os itens validados deste formulário",
                            ):
                                with SessionLocal() as _s:
                                    for sol_v in validadas_grupo:
                                        aprovar_solicitacao(_s, sol_v.id)
                                st.rerun()
                        elif aprovadas_grupo:
                            st.success("✅ Pedidos aprovados")

                    with col_del_doc:
                        if not _aguard_confirm:
                            if st.button(
                                "🗑 Excluir Formulário",
                                key=f"del_doc_{setor_nome}_{solicitante}",
                                use_container_width=True,
                                help="Remove todos os itens deste formulário permanentemente",
                            ):
                                st.session_state[_confirm_key] = True
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
                            key=f"confirm_yes_{setor_nome}_{solicitante}",
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
                            key=f"confirm_no_{setor_nome}_{solicitante}",
                            use_container_width=True,
                        ):
                            st.session_state[_confirm_key] = False
                            st.rerun()


# =============================================================================
# ABA 3 — CONSOLIDAÇÃO
# =============================================================================
elif aba == "Consolidação":

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
        STATUS_ATIVOS = {"zerado", "abaixo_minimo", "comprar"}

        principais    = [x for x in itens_lista if x.status in STATUS_ATIVOS]
        sem_param_conso = [x for x in itens_lista if x.status in {"sem_parametro", "sem_minimo_definido"}]

        if principais:
            section_title("Itens para Decisão de Compra")
            _avisos_conso = []
            if sem_param_conso:
                _avisos_conso.append(f"{len(sem_param_conso)} item(ns) sem parâmetros")
            if _n_sols_pendentes:
                _avisos_conso.append(f"{_n_sols_pendentes} solicitação(ões) pendente(s)")
            if _avisos_conso:
                st.caption(
                    f"⚠️ {' · '.join(_avisos_conso)} — "
                    f"resolva em **Solicitações e Pendências** e rode novamente a análise."
                )
            st.caption(
                "Edite 'Qtd Final' e 'Motivo' quando necessário. "
                "Marque 'Incluir na Lista' e clique em Salvar para aprovar."
            )

            rows_ed = []
            for x in principais:
                rows_ed.append({
                    "_id": x.id,
                    "Status": _STATUS_LABEL.get(x.status, x.status),
                    "Item": x.item.nome if x.item else "—",
                    "Categoria": x.item.categoria.nome if x.item and x.item.categoria else "—",
                    "Estoque": x.estoque_atual_snap,
                    "Mínimo": x.estoque_minimo_snap,
                    "Ideal": x.estoque_ideal_snap,
                    "Solicitado": x.total_solicitado,
                    "Qtd Sugerida": x.quantidade_sugerida,
                    "Qtd Final": (
                        x.quantidade_final_definida
                        if x.quantidade_final_definida is not None
                        else x.quantidade_sugerida
                    ),
                    "Motivo": x.motivo or "",
                    "Incluir na Lista": x.incluir_na_lista_final,
                })

            df_ed = pd.DataFrame(rows_ed)
            col_config = {
                "_id":            st.column_config.NumberColumn("ID", disabled=True, width="small"),
                "Status":         st.column_config.TextColumn("Status", disabled=True),
                "Item":           st.column_config.TextColumn("Item", disabled=True, width="medium"),
                "Categoria":      st.column_config.TextColumn("Categoria", disabled=True),
                "Estoque":        st.column_config.NumberColumn("Estoque", disabled=True, width="small"),
                "Mínimo":         st.column_config.NumberColumn("Mínimo", disabled=True, width="small"),
                "Ideal":          st.column_config.NumberColumn("Ideal", disabled=True, width="small"),
                "Solicitado":     st.column_config.NumberColumn("Solicitado", disabled=True, width="small"),
                "Qtd Sugerida":   st.column_config.NumberColumn("Qtd Sugerida", disabled=True, width="small"),
                "Qtd Final":      st.column_config.NumberColumn("Qtd Final", min_value=0, width="small"),
                "Motivo":         st.column_config.TextColumn("Motivo", width="large"),
                "Incluir na Lista": st.column_config.CheckboxColumn("Incluir na Lista", width="small"),
            }
            if _consolidacao_readonly:
                st.dataframe(
                    df_ed,
                    column_config=col_config,
                    hide_index=True,
                    use_container_width=True,
                )
            else:
                edited_df = st.data_editor(
                    df_ed,
                    column_config=col_config,
                    hide_index=True,
                    use_container_width=True,
                    key="consolidacao_editor",
                )

            if not _consolidacao_readonly and st.button("💾 Salvar Alterações", type="primary", key="salvar_consolidacao"):
                sug_map = {
                    x.id: (x.quantidade_sugerida, x.item.nome if x.item else str(x.id))
                    for x in principais
                }
                erros_salvar = []
                for _, row in edited_df.iterrows():
                    lista_id = int(row["_id"])
                    qtd_final = int(row["Qtd Final"])
                    motivo = str(row["Motivo"]).strip() or None
                    incluir = bool(row["Incluir na Lista"])
                    qtd_sug, item_nome = sug_map.get(lista_id, (0, str(lista_id)))
                    if incluir and qtd_final != qtd_sug and not motivo:
                        erros_salvar.append(
                            f"**{item_nome}**: motivo obrigatório quando a quantidade "
                            f"final ({qtd_final}) difere da sugerida ({qtd_sug})."
                        )
                if erros_salvar:
                    for e in erros_salvar:
                        st.error(e)
                else:
                    with SessionLocal() as _s:
                        for _, row in edited_df.iterrows():
                            lista_id = int(row["_id"])
                            qtd_final = int(row["Qtd Final"])
                            motivo = str(row["Motivo"]).strip() or None
                            incluir = bool(row["Incluir na Lista"])
                            if incluir:
                                aprovar_item(_s, lista_id, qtd_final, motivo)
                            else:
                                remover_da_lista(_s, lista_id)
                    st.success("Alterações salvas com sucesso.")
                    st.rerun()

        if not principais:
            if sem_param_conso:
                st.warning(
                    f"**{len(sem_param_conso)} item sem parâmetros definidos** — o motor não pôde analisar a necessidade de compra destes itens.  \n"
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
        lista_final = get_lista_final(_s, periodo)
        lista_final_info = [
            {
                "item_nome": x.item.nome if x.item else "—",
                "categoria": x.item.categoria.nome if x.item and x.item.categoria else "—",
                "qtd_sugerida": x.quantidade_sugerida,
                "qtd_final": (
                    x.quantidade_final_definida
                    if x.quantidade_final_definida is not None
                    else x.quantidade_sugerida
                ),
                "motivo": x.motivo or "—",
                "fornecedor": x.fornecedor_sugerido.nome if x.fornecedor_sugerido else "—",
                "valor_est": x.valor_estimado,
                "estoque_atual": x.estoque_atual_snap,
                "estoque_minimo": x.estoque_minimo_snap,
                "estoque_ideal": x.estoque_ideal_snap,
            }
            for x in lista_final
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
                "Qtd Sugerida": info["qtd_sugerida"],
                "Qtd Final": info["qtd_final"],
                "Motivo": info["motivo"],
                "Fornecedor": info["fornecedor"],
                "Valor Est.": fmt_brl(info["valor_est"]) if info["valor_est"] else "—",
            }
            for info in lista_final_info
        ]
        st.dataframe(pd.DataFrame(rows_final), use_container_width=True, hide_index=True)

        total_est = sum(i["valor_est"] for i in lista_final_info if i["valor_est"])
        if total_est:
            st.metric("Valor total estimado", fmt_brl(total_est))

        df_docx = pd.DataFrame([
            {
                "Item": i["item_nome"],
                "Categoria": i["categoria"],
                "Atual": i["estoque_atual"],
                "Mínimo": i["estoque_minimo"],
                "Ideal": i["estoque_ideal"],
                "Comprar": i["qtd_final"],
                "Fornecedor": i["fornecedor"],
                "Valor Est.": fmt_brl(i["valor_est"]) if i["valor_est"] else "—",
            }
            for i in lista_final_info
        ])
        caminho_docx = gerar_lista_compras(df_docx)
        with open(caminho_docx, "rb") as f:
            docx_bytes = f.read()
        st.download_button(
            "📄 Baixar Lista de Compras (DOCX)",
            data=docx_bytes,
            file_name=f"lista_compras_{periodo_label}.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            key="download_lista_final",
        )

