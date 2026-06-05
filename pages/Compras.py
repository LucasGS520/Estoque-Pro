""" Tela da camada de Compras — governança da necessidade de compra.

Fluxo: seleção de período → solicitações (formulário externo /solicitar) →
classificar → consolidar → revisar painel → lista final.
"""

import datetime
from collections import defaultdict

import pandas as pd
import streamlit as st

from core.database import get_session_factory
from core.ui import empty_state, fmt_brl, page_header, section_title, setup_page
from services.compras_service import (
    aprovar_item,
    classificar_solicitacoes_periodo,
    consolidar_periodo,
    deletar_solicitacao,
    get_consolidacao_periodo,
    get_lista_final,
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
    "comprar":             "Comprar",
    "ok":                  "OK",
    "sem_minimo_definido": "Sem Mínimo",
    "excesso":             "Excesso",
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
with col_btn:
    consolidar = st.button("▶ Consolidar Período", type="primary", use_container_width=True)

periodo = datetime.date(ano_sel, mes_sel, 1)
periodo_label = f"{MESES_PT[mes_sel]}/{ano_sel}"

with SessionLocal() as _s:
    periodos_existentes = get_periodos_com_consolidacao(_s)

if periodo in periodos_existentes:
    st.info(f"Consolidação disponível para **{periodo_label}**", icon="✅")
else:
    st.warning(f"Nenhuma consolidação para **{periodo_label}** — clique em Consolidar Período.", icon="⚠️")

if consolidar:
    with st.spinner("Consolidando..."):
        with SessionLocal() as _s:
            results, summary = consolidar_periodo(_s, periodo)
    st.success(
        f"**{periodo_label}** consolidado — "
        f"{summary.itens_zerados} zerado(s) · "
        f"{summary.itens_abaixo_minimo} abaixo do mínimo · "
        f"{summary.itens_comprar} com pedido pressiona · "
        f"{summary.itens_excesso} excesso"
    )
    st.rerun()

st.divider()

# ── Dados do período ──────────────────────────────────────────────────────────
with SessionLocal() as _s:
    itens_lista = get_consolidacao_periodo(_s, periodo)
    cats = get_categorias(_s)
    cat_nomes = ["Todas"] + sorted({x.item.categoria.nome for x in itens_lista if x.item and x.item.categoria})

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

    if not itens_lista:
        empty_state(
            "🛒",
            "Sem dados para este período",
            f"Clique em 'Consolidar Período' para gerar a análise de {periodo_label}.",
        )
    else:
        zerados      = [x for x in itens_lista if x.status == "zerado"]
        abaixo_min   = [x for x in itens_lista if x.status == "abaixo_minimo"]
        comprar_list = [x for x in itens_lista if x.status == "comprar"]
        excesso_list = [x for x in itens_lista if x.status == "excesso"]
        ok_list      = [x for x in itens_lista if x.status == "ok"]
        sem_min      = [x for x in itens_lista if x.status == "sem_minimo_definido"]

        c1, c2, c3, c4, c5, c6 = st.columns(6)
        c1.metric("Zerados",        len(zerados))
        c2.metric("Abaixo do Mín.", len(abaixo_min))
        c3.metric("Comprar",        len(comprar_list))
        c4.metric("Excesso",        len(excesso_list))
        c5.metric("OK",             len(ok_list))
        c6.metric("Sem Mínimo",     len(sem_min))

        st.markdown("<div style='height:12px;'></div>", unsafe_allow_html=True)

        # Filtros — padrão Estoque.py
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
                "Comprar": "comprar",
                "Sem Mínimo": "sem_minimo_definido",
                "OK": "ok",
            }
            status_sel = st.selectbox("Status", list(status_opcoes.keys()), key="painel_status")

        # Tabela filtrada — exclui excesso (tem seção própria abaixo)
        STATUS_PAINEL = {"zerado", "abaixo_minimo", "comprar", "sem_minimo_definido", "ok"}
        itens_painel = [x for x in itens_lista if x.status in STATUS_PAINEL]

        # Aplicar filtros
        busca_lower = busca.strip().lower()
        status_code = status_opcoes[status_sel]
        if status_code:
            itens_painel = [x for x in itens_painel if x.status == status_code]
        if cat_sel != "Todas":
            itens_painel = [
                x for x in itens_painel
                if x.item and x.item.categoria and x.item.categoria.nome == cat_sel
            ]
        if busca_lower:
            itens_painel = [
                x for x in itens_painel
                if x.item and busca_lower in x.item.nome.lower()
            ]

        if not itens_painel:
            empty_state("✅", "Nenhum item encontrado para os filtros selecionados.")
        else:
            rows = []
            for x in itens_painel:
                rows.append({
                    "Status": _STATUS_LABEL.get(x.status, x.status),
                    "Item": x.item.nome if x.item else "—",
                    "Categoria": x.item.categoria.nome if x.item and x.item.categoria else "—",
                    "Estoque": x.estoque_atual_snap,
                    "Mínimo": x.estoque_minimo_snap,
                    "Ideal": x.estoque_ideal_snap,
                    "Solicitado": x.total_solicitado,
                    "Qtd Sugerida": x.quantidade_sugerida,
                    "Fornecedor": x.fornecedor_sugerido.nome if x.fornecedor_sugerido else "—",
                    "Valor Est.": fmt_brl(x.valor_estimado) if x.valor_estimado else "—",
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        if excesso_list:
            with st.expander(f"⚠️ {len(excesso_list)} item(ns) com excesso de estoque"):
                rows_exc = []
                for x in excesso_list:
                    rows_exc.append({
                        "Item": x.item.nome if x.item else "—",
                        "Categoria": x.item.categoria.nome if x.item and x.item.categoria else "—",
                        "Estoque": x.estoque_atual_snap,
                        "Ideal": x.estoque_ideal_snap,
                    })
                st.dataframe(pd.DataFrame(rows_exc), use_container_width=True, hide_index=True)
                st.caption("Itens com estoque acima de 1,5× o ideal. Não entram na lista de compras.")

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

    # ── Auto-classificação: processar pendentes antes de exibir ──────────────
    with SessionLocal() as _s:
        _raw = listar_solicitacoes(_s, periodo)
        if any(s.status == "pendente" for s in _raw):
            classificar_solicitacoes_periodo(_s, periodo)
        todas_sols = listar_solicitacoes(_s, periodo)

    if not todas_sols:
        empty_state("📝", "Nenhuma solicitação", f"Nenhuma solicitação recebida para {periodo_label}.")
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
        n_acao        = sum(1 for s in todas_sols if s.status in {"pendente_cadastro", "pendente_parametrizacao"})

        col_m1, col_m2, col_m3 = st.columns(3)
        col_m1.metric("📋 Formulários recebidos", n_formularios)
        col_m2.metric("✅ Itens prontos",          n_prontos)
        col_m3.metric("⚠️ Requerem ação",          n_acao)

        st.markdown("---")

        # ── Helpers ───────────────────────────────────────────────────────────
        _STATUS_BADGE_MAP = {
            "validada":                ("✅ Validada",       "#28a745"),
            "pendente":                ("⏳ Pendente",       "#6c757d"),
            "pendente_cadastro":       ("🆕 Novo Item",      "#fd7e14"),
            "pendente_parametrizacao": ("⚙️ Sem Parâmetros", "#6f42c1"),
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
            n_n = sum(1 for s in sols if s.status == "pendente_cadastro")
            n_s = sum(1 for s in sols if s.status == "pendente_parametrizacao")
            n_p = sum(1 for s in sols if s.status == "pendente")
            if n_v: partes.append(f"✅ {n_v} pronto(s)")
            if n_n: partes.append(f"🆕 {n_n} novo(s)")
            if n_s: partes.append(f"⚙️ {n_s} sem parâm.")
            if n_p: partes.append(f"⏳ {n_p} pendente(s)")
            return " · ".join(partes) if partes else "—"

        # ── Documentos ────────────────────────────────────────────────────────
        section_title("Formulários Recebidos")

        for (setor_nome, solicitante), sols in grupos.items():
            data_doc     = max(s.criado_em for s in sols).strftime("%d/%m/%Y")
            n_itens      = len(sols)
            resumo       = _resumo_grupo(sols)
            tem_validada = any(s.status == "validada" for s in sols)
            label_exp    = (
                f"🏢  {setor_nome}  ·  {solicitante}  ·  {data_doc}"
                f"  —  {n_itens} item(ns)  ·  {resumo}"
            )

            with st.expander(label_exp):
                if not tem_validada:
                    if st.button(
                        "🗑 Excluir formulário completo",
                        key=f"del_doc_{setor_nome}_{solicitante}",
                        help="Remove todos os itens deste formulário",
                    ):
                        with SessionLocal() as _s:
                            for sol in sols:
                                deletar_solicitacao(_s, sol.id)
                        st.rerun()
                else:
                    st.caption("⚠️ Revise cada item solicitado para uma aprovação mais precisa e confiável.")

                st.markdown("<div style='height:4px;'></div>", unsafe_allow_html=True)

                ch1, ch2, ch3, ch4, _, _ = st.columns([4, 1, 3, 2, 1, 1])
                ch1.caption("Item")
                ch2.caption("Qtd")
                ch3.caption("Observação")
                ch4.caption("Status")

                for sol in sols:
                    nome_item = sol.item.nome if sol.item else (sol.nome_item_livre or "—")
                    obs       = sol.observacao or "—"
                    c1, c2, c3, c4, c_acao, c_rm = st.columns([4, 1, 3, 2, 1, 1])
                    c1.markdown(f"**{nome_item}**")
                    c2.markdown(str(sol.quantidade_solicitada))
                    c3.caption(obs if obs != "—" else "")
                    c4.markdown(_badge(sol.status), unsafe_allow_html=True)

                    if sol.status == "validada":
                        if c_acao.button("✓", key=f"aceitar_sol_{sol.id}", help="Aceitar e aprovar para a lista de compras", use_container_width=True):
                            with SessionLocal() as _s:
                                consolidar_periodo(_s, periodo)
                                itens_lc = get_consolidacao_periodo(_s, periodo)
                                item_lc = next((x for x in itens_lc if x.item_id == sol.item_id), None)
                                if item_lc:
                                    aprovar_item(_s, item_lc.id, item_lc.quantidade_sugerida)
                            st.rerun()
                    elif sol.status == "pendente_cadastro":
                        if c_acao.button("📝", key=f"nav_cad_{sol.id}", help=f'Cadastrar "{sol.nome_item_livre or nome_item}" em Estoque', use_container_width=True):
                            st.switch_page("pages/Estoque.py")
                    elif sol.status == "pendente_parametrizacao":
                        if c_acao.button("⚙️", key=f"nav_param_{sol.id}", help=f'Configurar parâmetros de "{nome_item}" em Estoque', use_container_width=True):
                            st.switch_page("pages/Estoque.py")

                    if c_rm.button("✕", key=f"del_sol_doc_{sol.id}", help="Remover este item", use_container_width=True):
                        with SessionLocal() as _s:
                            deletar_solicitacao(_s, sol.id)
                        st.rerun()

                # ── Aprovação por formulário ───────────────────────────────────
                validadas_grupo = [s for s in sols if s.status == "validada"]
                if validadas_grupo:
                    st.markdown("<div style='height:6px;'></div>", unsafe_allow_html=True)
                    col_apr_doc, _ = st.columns([2, 4])
                    with col_apr_doc:
                        if st.button(
                            f"Aprovar Pedidos",
                            key=f"apr_doc_{setor_nome}_{solicitante}",
                            type="primary",
                            use_container_width=True,
                            help="Aprova todos os itens validados deste formulário para a lista de compras",
                        ):
                            with SessionLocal() as _s:
                                consolidar_periodo(_s, periodo)
                                itens_lc = get_consolidacao_periodo(_s, periodo)
                                for sol_v in validadas_grupo:
                                    item_lc = next((x for x in itens_lc if x.item_id == sol_v.item_id), None)
                                    if item_lc:
                                        aprovar_item(_s, item_lc.id, item_lc.quantidade_sugerida)
                            st.rerun()


# =============================================================================
# ABA 3 — CONSOLIDAÇÃO
# =============================================================================
elif aba == "Consolidação":

    with SessionLocal() as _s:
        sols = listar_solicitacoes(_s, periodo)
        sols_info = [
            {
                "id": s.id,
                "item_nome": s.item.nome if s.item else f"{s.nome_item_livre} (não cadastrado)",
                "item_id": s.item_id,
                "setor_nome": s.setor.nome if s.setor else "—",
                "solicitante": s.solicitante,
                "quantidade": s.quantidade_solicitada,
                "obs": s.observacao or "",
            }
            for s in sols
        ]

    # ── Tabela de consolidação ────────────────────────────────────────────────
    if not itens_lista:
        empty_state(
            "🔗",
            "Sem consolidação para este período",
            "Clique em 'Consolidar Período' para cruzar estoque e solicitações.",
        )
    else:
        STATUS_ATIVOS = {"zerado", "abaixo_minimo", "comprar"}
        STATUS_PENDENCIAS = {"sem_minimo_definido"}

        principais = [x for x in itens_lista if x.status in STATUS_ATIVOS]
        pendencias = [x for x in itens_lista if x.status in STATUS_PENDENCIAS]
        sols_sem_cadastro = [i for i in sols_info if i["item_id"] is None]

        if principais:
            section_title("Itens para Decisão de Compra")
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
            edited_df = st.data_editor(
                df_ed,
                column_config=col_config,
                hide_index=True,
                use_container_width=True,
                key="consolidacao_editor",
            )

            if st.button("💾 Salvar Alterações", type="primary", key="salvar_consolidacao"):
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

        if pendencias:
            section_title("Pendências — Itens Sem Parâmetros")
            st.caption("Defina mínimo e ideal em Estoque → Editar Item e reconsolide.")
            rows_pend = [
                {
                    "Item": x.item.nome if x.item else "—",
                    "Categoria": x.item.categoria.nome if x.item and x.item.categoria else "—",
                    "Estoque Atual": x.estoque_atual_snap,
                    "Solicitado": x.total_solicitado,
                }
                for x in pendencias
            ]
            st.dataframe(pd.DataFrame(rows_pend), use_container_width=True, hide_index=True)

        if sols_sem_cadastro:
            section_title("Itens Solicitados Não Cadastrados")
            st.caption("Cadastre os itens abaixo em Estoque antes de incluí-los na consolidação.")
            rows_nc = [
                {
                    "Nome informado": info["item_nome"],
                    "Quantidade": info["quantidade"],
                    "Solicitante": info["solicitante"],
                    "Setor": info["setor_nome"],
                }
                for info in sols_sem_cadastro
            ]
            st.dataframe(pd.DataFrame(rows_nc), use_container_width=True, hide_index=True)

        if not principais and not pendencias and not sols_sem_cadastro:
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

