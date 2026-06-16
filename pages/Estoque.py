""" Tela de estoque, movimentações e cadastros.

Concentra consulta de itens, registro de entradas/saídas e manutenção de itens,
fornecedores e categorias. As ações de escrita chamam serviços que fazem
`commit` e usam `st.rerun()` para atualizar a interface.
"""

import re

import streamlit as st
import pandas as pd

from core.auth import require_admin
from core.database import get_session_factory
from core.ui import colorir_linhas_status, formatar_telefone, setup_page, page_header, section_title
from services import estoque_service, fornecedor_service, calculos_service
from services.estoque_service import (
    registrar_devolucao, get_devolucoes, reintegrar_devolucao, descartar_devolucao,
)


def _formatar_telefone(tel: str):
    """Extrai dígitos e formata (XX) XXXX-XXXX ou (XX) XXXXX-XXXX.
    Retorna string formatada, "" se vazio, ou None se dígitos insuficientes."""
    digits = re.sub(r'\D', '', tel)
    if not digits:
        return ""
    if len(digits) == 10:
        return f"({digits[:2]}) {digits[2:6]}-{digits[6:]}"
    if len(digits) == 11:
        return f"({digits[:2]}) {digits[2:7]}-{digits[7:]}"
    return None


def _validar_email(email: str) -> bool:
    if not email.strip():
        return True
    return bool(re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email.strip()))

setup_page("Estoque", "📋")
require_admin()
page_header("Estoque", subtitle="Consulta, movimentações e edição de itens, fornecedores e categorias.")

# CSS para dar aparência de abas nativas aos st.radio usados como navegação
st.markdown("""
<style>
/* Barra de abas: o container role=radiogroup */
[data-testid="stRadio"] [role="radiogroup"] {
    display: flex !important;
    flex-direction: row !important;
    gap: 0 !important;
    flex-wrap: nowrap !important;
    border-bottom: 1px solid rgba(49, 51, 63, 0.2) !important;
    padding-bottom: 0 !important;
    margin-bottom: 0.75rem !important;
}

/* Cada aba (label de opção) */
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

/* Oculta apenas o círculo BasesWeb e o input nativo */
[data-testid="stRadio"] [role="radiogroup"] > label [data-baseweb="radio"],
[data-testid="stRadio"] [role="radiogroup"] > label input[type="radio"] {
    display: none !important;
}

/* Aba selecionada */
[data-testid="stRadio"] [role="radiogroup"] > label:has(input:checked) {
    border-bottom: 2px solid rgb(255, 75, 75) !important;
    color: rgb(255, 75, 75) !important;
    font-weight: 600 !important;
}

/* Hover */
[data-testid="stRadio"] [role="radiogroup"] > label:hover {
    color: rgba(49, 51, 63, 0.85) !important;
}
</style>
""", unsafe_allow_html=True)

SessionLocal = get_session_factory()

# Feedback persistente gerado em ação anterior, exibido após rerun
if _fb := st.session_state.pop("_fb", None):
    getattr(st, _fb[0])(_fb[1])

tab_sel = st.radio(
    "Navegação", ["Visualizar", "Registrar Movimentação", "Devoluções", "Editar"],
    key="estoque_tab", horizontal=True, label_visibility="collapsed"
)

# ── Tab 1: Visualizar ─────────────────────────────────────────────────────────
if tab_sel == "Visualizar":
    with SessionLocal() as session:
        categorias = estoque_service.get_categorias(session)
        cat_opcoes = {"Todas": None} | {c.nome: c.id for c in categorias}

    section_title("Filtros")
    col1, col2 = st.columns([3, 2])
    with col1:
        busca = st.text_input("Buscar por nome", placeholder="Digite parte do nome...")
    with col2:
        cat_sel = st.selectbox("Filtrar por categoria", list(cat_opcoes.keys()))

    with SessionLocal() as session:
        master_rows = estoque_service.get_tabela_mestre(
            session, categoria_id=cat_opcoes[cat_sel]
        )

    busca_lower = busca.strip().lower()
    filtradas = [
        r for r in master_rows
        if not busca_lower or busca_lower in r["item"].lower()
    ]

    _STATUS_DISPLAY = {
        "zerado":        "Zerado",
        "abaixo_minimo": "Abaixo do Mínimo",
        "abaixo_ideal":  "Abaixo do Ideal",
        "sem_parametro": "Sem Parâmetro",
        "ok":            "OK",
    }
    _STATUS_SORT = {"zerado": 0, "abaixo_minimo": 1, "abaixo_ideal": 2, "ok": 3, "sem_parametro": 4}

    df = pd.DataFrame([
        {
            "ID": r["id"],
            "Categoria": r["categoria"],
            "Item": r["item"],
            "Und.": r["unidade"],
            "Status": _STATUS_DISPLAY.get(r["status"], r["status"]),
            "Atual": r["atual"],
            "Mínimo": r["minimo"],
            "Ideal": r["ideal"],
            "Ult. Movimentação": (
                r["ultima_mov_data"].strftime("%d/%m/%Y %H:%M")
                if r["ultima_mov_data"] else "-"
            ),
            "Tipo Mov.": (
                "↓ Entrada" if r["ultima_mov_tipo"] == "entrada"
                else "↑ Saída" if r["ultima_mov_tipo"] == "saida"
                else "-"
            ),
            "Setor": r["ultima_mov_setor"] or "" if r["ultima_mov_tipo"] == "saida" else "",
            "Qtd. Mov.": str(r["ultima_mov_quantidade"]) if r["ultima_mov_quantidade"] is not None else "",
            "Fornecedor(es)": r["fornecedores"],
            "Obs.": r["observacoes"],
            "_sort": _STATUS_SORT.get(r["status"], 99),
        }
        for r in filtradas
    ])
    df = df.sort_values("_sort").drop(columns=["_sort"]).reset_index(drop=True)
    styled = df.style.apply(
        lambda row: colorir_linhas_status(row, campo="Status"), axis=1
    )
    st.dataframe(styled, width='stretch', hide_index=True)
    total = len(master_rows)
    label = f"{len(filtradas)} itens exibidos"
    if len(filtradas) < total:
        label += f" (de {total} no total)"
    st.caption(label)

# ── Tab 2: Registrar Movimentação ─────────────────────────────────────────────
elif tab_sel == "Registrar Movimentação":
    section_title("Selecionar item")

    _mov_v = st.session_state.get("_mov_v", 0)

    with SessionLocal() as session:
        categorias_mov = estoque_service.get_categorias(session)
        cat_opcoes_mov = {c.nome: c.id for c in categorias_mov}

    if not cat_opcoes_mov:
        st.info("Nenhuma categoria cadastrada. Cadastre categorias na aba Editar antes de registrar movimentações.")
        st.stop()

    cat_mov = st.selectbox(
        "Categoria", list(cat_opcoes_mov.keys()),
        index=None, placeholder="Selecione uma categoria...",
        key=f"mov_cat_{_mov_v}",
    )
    if cat_mov is None:
        st.info("Selecione uma categoria para continuar.")
        st.stop()

    with SessionLocal() as session:
        itens_mov = estoque_service.get_all_itens(session, categoria_id=cat_opcoes_mov[cat_mov])
        item_opcoes_mov = {i.nome: i.id for i in itens_mov}
        item_estoque_map = {i.id: (i.estoque_atual, i.unidade) for i in itens_mov}

    if not item_opcoes_mov:
        st.info("Nenhum item cadastrado nesta categoria. Cadastre itens na aba Editar > Itens antes de registrar movimentações.")
        st.stop()

    item_mov_sel = st.selectbox(
        "Item", list(item_opcoes_mov.keys()),
        index=None, placeholder="Selecione um item...",
        key=f"mov_item_{_mov_v}",
    )
    if item_mov_sel is None:
        st.info("Selecione um item para continuar.")
        st.stop()

    item_mov_id = item_opcoes_mov[item_mov_sel]

    estoque_disp, unidade_disp = item_estoque_map.get(item_mov_id, (0, "un"))
    st.info(f"Estoque atual: **{estoque_disp} {unidade_disp}**")

    section_title("Dados da movimentação")
    col1, col2 = st.columns(2)
    with col1:
        tipo_mov = st.selectbox("Tipo", ["entrada", "saida"], key=f"mov_tipo_{_mov_v}")
    with col2:
        qtd_mov = st.number_input("Quantidade", min_value=1, value=1, key=f"mov_qtd_{_mov_v}")

    setor_mov_id = None
    retirado_por_mov = None
    if tipo_mov == "saida":
        with SessionLocal() as session:
            setores_mov = estoque_service.get_setores(session)
            setor_opcoes_mov = {s.nome: s.id for s in setores_mov}

        if not setor_opcoes_mov:
            st.warning("Nenhum setor cadastrado. Cadastre um setor na aba Editar > Setores antes de registrar saídas.")
        else:
            setor_sel_mov = st.selectbox("Setor *", list(setor_opcoes_mov.keys()), key=f"mov_setor_{_mov_v}")
            setor_mov_id = setor_opcoes_mov[setor_sel_mov]

        retirado_por_mov = st.text_input("Retirado por (opcional)", key=f"mov_retirado_por_{_mov_v}")

    motivo_mov = st.text_input("Motivo (opcional)", key=f"mov_motivo_{_mov_v}")

    if st.button("Registrar movimentação", key="btn_mov_registrar", type="primary", use_container_width=True):
        if tipo_mov == "saida" and setor_mov_id is None:
            st.error("Cadastre e selecione um setor para registrar uma saída.")
        else:
            try:
                with st.spinner("Registrando..."):
                    with SessionLocal() as session:
                        item_upd = estoque_service.registrar_movimentacao(
                            session, item_mov_id, tipo_mov, qtd_mov,
                            motivo_mov or None,
                            retirado_por=retirado_por_mov or None,
                            setor_id=setor_mov_id,
                        )
                        upd_nome = item_upd.nome
                        upd_estoque = item_upd.estoque_atual
                        upd_unidade = item_upd.unidade
                st.session_state["_mov_v"] = _mov_v + 1
                st.session_state["_fb"] = (
                    "success",
                    f"Movimentação registrada. Novo estoque de **{upd_nome}**: {upd_estoque} {upd_unidade}"
                )
                st.rerun()
            except ValueError as e:
                st.error(str(e))

# ── Tab 3: Devoluções ────────────────────────────────────────────────────────
elif tab_sel == "Devoluções":
    _dev_v = st.session_state.get("_dev_v", 0)

    # Carrega dados sempre — a tabela de pendentes precisa renderizar independente do formulário
    with SessionLocal() as session:
        categorias_dev = estoque_service.get_categorias(session)
        setores_dev = estoque_service.get_setores(session)
        pendentes = get_devolucoes(session, status="pendente")

    cat_opcoes_dev = {c.nome: c.id for c in categorias_dev}
    setor_opcoes_dev = {s.nome: s.id for s in setores_dev}

    # ── Formulário de registro ────────────────────────────────────────────────
    section_title("Selecionar item de Devolução")

    if not cat_opcoes_dev:
        st.info("Nenhuma categoria cadastrada. Cadastre categorias na aba Editar antes de registrar devoluções.")
    else:
        cat_dev = st.selectbox(
            "Categoria", list(cat_opcoes_dev.keys()),
            index=None, placeholder="Selecione uma categoria de devolução...",
            key=f"dev_cat_{_dev_v}",
        )

        if cat_dev is None:
            st.info("Selecione uma categoria para continuar.")
        else:
            with SessionLocal() as session:
                itens_dev = estoque_service.get_all_itens(session, categoria_id=cat_opcoes_dev[cat_dev])
            item_opcoes_dev = {i.nome: i.id for i in itens_dev}
            item_estoque_dev = {i.id: (i.estoque_atual, i.unidade) for i in itens_dev}

            if not item_opcoes_dev:
                st.info("Nenhum item cadastrado nesta categoria.")
            else:
                item_dev_sel = st.selectbox(
                    "Item", list(item_opcoes_dev.keys()),
                    index=None, placeholder="Selecione um item para devolver...",
                    key=f"dev_item_{_dev_v}",
                )

                if item_dev_sel is None:
                    st.info("Selecione um item para continuar.")
                else:
                    item_dev_id = item_opcoes_dev[item_dev_sel]
                    estoque_dev, unidade_dev = item_estoque_dev.get(item_dev_id, (0, "un"))
                    st.info(f"Estoque atual: **{estoque_dev} {unidade_dev}**")

                    section_title("Dados da devolução")
                    qtd_dev = st.number_input("Quantidade", min_value=1, value=1, key=f"dev_qtd_{_dev_v}")

                    if not setor_opcoes_dev:
                        st.warning("Nenhum setor cadastrado. Cadastre um setor na aba Editar > Setores antes de registrar devoluções.")
                    else:
                        setor_dev_sel = st.selectbox(
                            "Setor que devolveu *", list(setor_opcoes_dev.keys()), key=f"dev_setor_{_dev_v}"
                        )
                        setor_dev_id = setor_opcoes_dev[setor_dev_sel]

                    motivo_dev = st.text_input("Motivo (opcional)", key=f"dev_motivo_{_dev_v}")

                    if st.button("Registrar devolução", key="btn_registrar_dev", type="primary", use_container_width=True):
                        if not setor_opcoes_dev:
                            st.error("Cadastre e selecione um setor para registrar uma devolução.")
                        else:
                            try:
                                with st.spinner("Registrando..."):
                                    with SessionLocal() as session:
                                        registrar_devolucao(
                                            session,
                                            item_id=item_dev_id,
                                            quantidade=int(qtd_dev),
                                            setor_id=setor_dev_id,
                                            motivo=motivo_dev or None,
                                        )
                                st.session_state["_dev_v"] = _dev_v + 1
                                st.session_state["_fb"] = (
                                    "success",
                                    f"Devolução de **{item_dev_sel}** registrada e aguardando processamento.",
                                )
                                st.rerun()
                            except ValueError as e:
                                st.error(str(e))

    # ── Tabela de itens devolvidos (sempre visível) ───────────────────────────
    st.divider()
    section_title(f"Itens Devolvidos — {len(pendentes)} pendente(s)")

    if not pendentes:
        st.info("Nenhuma devolução pendente no momento.")
    else:
        df_pendentes = pd.DataFrame([
            {
                "Categoria": dev.item.categoria.nome if dev.item.categoria else "-",
                "Item": dev.item.nome,
                "Und.": dev.item.unidade,
                "Qtd. Devolvida": dev.quantidade,
                "Setor": dev.setor.nome if dev.setor else "-",
                "Data": dev.criado_em.strftime("%d/%m/%Y %H:%M") if dev.criado_em else "-",
                "Motivo": dev.motivo or "-",
            }
            for dev in pendentes
        ])
        st.dataframe(df_pendentes, width='stretch', hide_index=True)

        st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)
        section_title("Processar Devolução")

        opcoes_proc = {
            f"{d.item.nome} — {d.quantidade} {d.item.unidade} ({d.setor.nome if d.setor else '-'})": d.id
            for d in pendentes
        }
        sel_proc = st.selectbox(
            "Selecionar devolução para processar",
            list(opcoes_proc.keys()),
            index=None,
            placeholder="Escolha uma devolução...",
            key="dev_sel_proc",
        )

        col_reint, col_desc = st.columns(2)
        with col_reint:
            if st.button(
                "Reintegrar ao Estoque",
                disabled=not sel_proc,
                use_container_width=True,
                type="primary",
                key="btn_reintegrar",
            ):
                try:
                    with st.spinner("Reintegrando..."):
                        with SessionLocal() as session:
                            reintegrar_devolucao(session, devolucao_id=opcoes_proc[sel_proc])
                    st.session_state["_fb"] = ("success", "Item reintegrado ao estoque com entrada registrada.")
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))
        with col_desc:
            if st.button(
                "Descartar",
                disabled=not sel_proc,
                use_container_width=True,
                key="btn_descartar_dev",
            ):
                try:
                    with st.spinner("Descartando..."):
                        with SessionLocal() as session:
                            descartar_devolucao(session, devolucao_id=opcoes_proc[sel_proc])
                    st.session_state["_fb"] = ("success", "Devolução descartada — item não retorna ao estoque.")
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))

# ── Tab 4: Editar ─────────────────────────────────────────────────────────────
elif tab_sel == "Editar":
    subtab_sel = st.radio(
        "Edição", ["Itens", "Categorias", "Setores", "Fornecedores"],
        key="estoque_subtab", horizontal=True, label_visibility="collapsed"
    )

    # ══════════════════════════════════════════════════════════════════════════
    # Sub-tab: Itens
    # ══════════════════════════════════════════════════════════════════════════
    if subtab_sel == "Itens":
        section_title("Itens cadastrados")

        with SessionLocal() as session:
            # Consulta única para montar tabela e filtros da subaba de itens.
            cats_filtro = estoque_service.get_categorias(session)
            todos_itens = estoque_service.get_all_itens(session, apenas_ativos=False)
            todos_rows = [
                {
                    "ID": i.id,
                    "Categoria": i.categoria.nome,
                    "Item": i.nome,
                    "Und.": i.unidade,
                    "Atual": i.estoque_atual,
                    "Mínimo Vigente": i.estoque_minimo_vigente,
                    "Ideal Vigente": i.estoque_ideal_vigente,
                    "Origem": i.origem_minimo or "—",
                    "Ativo": "Sim" if i.ativo else "Não",
                    "Obs.": i.observacoes or "",
                }
                for i in todos_itens
            ]

        fc1, fc2, fc3 = st.columns([3, 2, 1])
        with fc1:
            fi_busca = st.text_input(
                "Buscar por nome", placeholder="Digite parte do nome...", key="fi_itens_busca"
            )
        with fc2:
            fi_cat_opts = ["Todas"] + [c.nome for c in cats_filtro]
            fi_cat = st.selectbox("Categoria", fi_cat_opts, key="fi_itens_cat")
        with fc3:
            fi_status = st.selectbox(
                "Status", ["Todos", "Ativos", "Inativos"], key="fi_itens_status"
            )

        fi_busca_lower = fi_busca.strip().lower()
        df_itens_rows = [
            r for r in todos_rows
            if (not fi_busca_lower or fi_busca_lower in r["Item"].lower())
            and (fi_cat == "Todas" or r["Categoria"] == fi_cat)
            and (
                fi_status == "Todos"
                or (fi_status == "Ativos" and r["Ativo"] == "Sim")
                or (fi_status == "Inativos" and r["Ativo"] == "Não")
            )
        ]

        if todos_rows:
            st.dataframe(pd.DataFrame(df_itens_rows), width='stretch', hide_index=True)
            label = f"{len(df_itens_rows)} de {len(todos_rows)} itens"
            if len(df_itens_rows) < len(todos_rows):
                label += " (filtrado)"
            st.caption(label)
        else:
            st.info("Nenhum item cadastrado.")

        st.divider()

        col_ni, _sep_itens, col_ei = st.columns([1, 0.04, 1])

        with _sep_itens:
            st.markdown(
                '<div style="width:2px; background:#dee2e6; height:1100px; margin:0 auto;"></div>',
                unsafe_allow_html=True,
            )

        # ── Cadastrar novo item ───────────────────────────────────────────────
        with col_ni:
            section_title("Cadastrar novo item")

            with SessionLocal() as session:
                cats_ni = estoque_service.get_categorias(session)
                cat_opcoes_ni = {c.nome: c.id for c in cats_ni}

            if not cat_opcoes_ni:
                st.warning("Cadastre uma categoria antes de adicionar itens.")
            else:
                _ni_v = st.session_state.get("_ni_v", 0)
                with st.container(border=True):
                    ni_nome = st.text_input("Nome do produto", key=f"ni_nome_{_ni_v}")
                    ni_cat = st.selectbox(
                        "Categoria", list(cat_opcoes_ni.keys()),
                        index=None, placeholder="Selecione uma categoria...",
                        key=f"ni_cat_{_ni_v}",
                    )
                    col_a, col_b = st.columns(2)
                    with col_a:
                        ni_und = st.text_input("Unidade", value="un", key=f"ni_und_{_ni_v}")
                    with col_b:
                        ni_atual = st.number_input("Estoque Atual", min_value=0, value=0, key=f"ni_atual_{_ni_v}")
                    with st.expander("Valores manuais de estoque (opcional)"):
                        st.caption("Deixe em 0 para usar o cálculo automático após a próxima revisão mensal.")
                        col_c, col_d = st.columns(2)
                        with col_c:
                            ni_minimo = st.number_input("Mínimo manual", min_value=0, value=0, key=f"ni_minimo_{_ni_v}")
                        with col_d:
                            ni_ideal = st.number_input("Ideal manual", min_value=ni_minimo, value=ni_minimo, key=f"ni_ideal_{_ni_v}")
                    with SessionLocal() as session:
                        forn_opts_ni = fornecedor_service.get_all_fornecedores(session)
                        forn_map_ni = {f.nome: f.id for f in forn_opts_ni}

                    ni_fornecedores = st.multiselect(
                        "Fornecedores",
                        options=list(forn_map_ni.keys()),
                        placeholder="Selecione os fornecedores...",
                        key=f"ni_fornecedores_{_ni_v}",
                    )
                    ni_obs = st.text_area("Observações", height=68, key=f"ni_obs_{_ni_v}")
                    ni_ativo = st.checkbox("Ativo", value=True, key=f"ni_ativo_{_ni_v}")

                    if st.button("Cadastrar", key="btn_ni_cadastrar", type="primary", use_container_width=True):
                        if ni_cat is None:
                            st.error("Selecione uma categoria.")
                        elif not ni_nome.strip():
                            st.error("Nome não pode ficar em branco.")
                        elif ni_ideal > 0 and ni_minimo == 0:
                            st.error("Se informar o Ideal, informe também o Mínimo.")
                        elif ni_ideal > 0 and ni_ideal < ni_minimo:
                            st.error(f"Ideal ({ni_ideal}) não pode ser menor que Mínimo ({ni_minimo}).")
                        else:
                            try:
                                with st.spinner("Salvando..."):
                                    with SessionLocal() as session:
                                        item_criado = estoque_service.create_item(
                                            session, cat_opcoes_ni[ni_cat], ni_nome, ni_und,
                                            ni_atual,
                                            estoque_minimo_manual=ni_minimo if ni_minimo > 0 else None,
                                            estoque_ideal_manual=ni_ideal if ni_ideal > 0 else None,
                                            observacoes=ni_obs or None,
                                            ativo=ni_ativo,
                                        )
                                        item_nome_criado = item_criado.nome
                                        if ni_fornecedores:
                                            estoque_service.atualizar_fornecedores_item(
                                                session, item_criado.id,
                                                [forn_map_ni[n] for n in ni_fornecedores],
                                            )
                                st.session_state["_ni_v"] = _ni_v + 1
                                st.session_state["_fb"] = ("success", f"Item **{item_nome_criado}** cadastrado.")
                                st.rerun()
                            except ValueError as e:
                                st.error(str(e))

        # ── Editar / Remover item ─────────────────────────────────────────────
        with col_ei:
            section_title("Editar / Remover item")

            with SessionLocal() as session:
                cats_ei = estoque_service.get_categorias(session)
                cat_opcoes_ei = {c.nome: c.id for c in cats_ei}

            if not cat_opcoes_ei:
                st.info("Nenhuma categoria disponível.")
            else:
                cat_ei_sel = st.selectbox(
                    "Categoria", list(cat_opcoes_ei.keys()), key="ei_cat"
                )

                with SessionLocal() as session:
                    itens_ei = estoque_service.get_all_itens(
                        session,
                        categoria_id=cat_opcoes_ei[cat_ei_sel],
                        apenas_ativos=False,
                    )
                    item_opcoes_ei = {i.nome: i.id for i in itens_ei}

                if not item_opcoes_ei:
                    st.info("Nenhum item nessa categoria.")
                else:
                    item_ei_sel = st.selectbox(
                        "Item", list(item_opcoes_ei.keys()), key="ei_item"
                    )
                    item_ei_id = item_opcoes_ei[item_ei_sel]

                    with SessionLocal() as session:
                        _i = estoque_service.get_item_by_id(session, item_ei_id)
                        ei_nome = _i.nome
                        ei_cat_id = _i.categoria_id
                        ei_unidade = _i.unidade
                        ei_forn_atuais = [f.nome for f in _i.fornecedores_associados]
                        ei_obs = _i.observacoes or ""
                        ei_ativo = _i.ativo
                        ei_minimo_vigente = _i.estoque_minimo_vigente
                        ei_ideal_vigente = _i.estoque_ideal_vigente
                        ei_minimo_sugerido = _i.estoque_minimo_sugerido
                        ei_ideal_sugerido = _i.estoque_ideal_sugerido
                        ei_minimo_manual = _i.estoque_minimo_manual
                        ei_ideal_manual = _i.estoque_ideal_manual
                        ei_origem_minimo = _i.origem_minimo
                        forn_opts_ei = fornecedor_service.get_all_fornecedores(session)
                        forn_map_ei = {f.nome: f.id for f in forn_opts_ei}
                        # Última revisão para exibir badge de confiabilidade
                        _ultimas_revs = calculos_service.get_revisoes_item(session, item_ei_id, limit=1)
                        ei_ultima_rev = _ultimas_revs[0] if _ultimas_revs else None
                        ei_status_conf = ei_ultima_rev.status_confiabilidade if ei_ultima_rev else None
                        ei_ultima_rev_data = ei_ultima_rev.criado_em if ei_ultima_rev else None

                    with st.container(border=True):
                        ei_novo_nome = st.text_input(
                            "Nome do produto", value=ei_nome, key=f"ei_{item_ei_id}_nome"
                        )
                        ei_nova_cat = st.selectbox(
                            "Categoria",
                            list(cat_opcoes_ei.keys()),
                            index=list(cat_opcoes_ei.values()).index(ei_cat_id),
                            key=f"ei_{item_ei_id}_cat",
                        )
                        col_a, col_b = st.columns(2)
                        with col_a:
                            ei_nova_und = st.text_input(
                                "Unidade", value=ei_unidade, key=f"ei_{item_ei_id}_und"
                            )
                        with col_b:
                            ei_novo_ativo = st.checkbox(
                                "Ativo", value=ei_ativo, key=f"ei_{item_ei_id}_ativo"
                            )
                        ei_fornecedores = st.multiselect(
                            "Fornecedores",
                            options=list(forn_map_ei.keys()),
                            default=ei_forn_atuais,
                            placeholder="Selecione os fornecedores...",
                            key=f"ei_{item_ei_id}_fornecedores",
                        )
                        ei_nova_obs = st.text_area(
                            "Observações", value=ei_obs, height=68, key=f"ei_{item_ei_id}_obs"
                        )

                        if st.button(
                            "Salvar alterações", key="btn_ei_salvar", type="primary", use_container_width=True
                        ):
                            if not ei_novo_nome.strip():
                                st.error("Nome não pode ficar em branco.")
                            else:
                                try:
                                    with st.spinner("Salvando..."):
                                        with SessionLocal() as session:
                                            estoque_service.update_item_completo(
                                                session, item_ei_id,
                                                cat_opcoes_ei[ei_nova_cat],
                                                ei_novo_nome, ei_nova_und,
                                                ei_nova_obs or None, ei_novo_ativo,
                                            )
                                            estoque_service.atualizar_fornecedores_item(
                                                session, item_ei_id,
                                                [forn_map_ei[n] for n in ei_fornecedores],
                                            )
                                    for k in [k for k in st.session_state if k.startswith(f"ei_{item_ei_id}_")]:
                                        st.session_state.pop(k)
                                    st.session_state["_fb"] = ("success", f"Item **{ei_novo_nome}** atualizado.")
                                    st.rerun()
                                except ValueError as e:
                                    st.error(str(e))

                    # ── Seção: Mínimo e Ideal ────────────────────────────────
                    with st.container(border=True):
                        st.markdown("**Estoque Mínimo e Ideal**")

                        col_v1, col_v2 = st.columns(2)
                        with col_v1:
                            origem_label = ei_origem_minimo or "Não definido"
                            st.metric("Mínimo vigente", ei_minimo_vigente, help=f"Origem: {origem_label}")
                        with col_v2:
                            st.metric("Ideal vigente", ei_ideal_vigente)

                        col_s1, col_s2 = st.columns(2)
                        with col_s1:
                            st.caption(f"Automático: {ei_minimo_sugerido if ei_minimo_sugerido is not None else '—'}")
                        with col_s2:
                            st.caption(f"Automático: {ei_ideal_sugerido if ei_ideal_sugerido is not None else '—'}")

                        col_s3, col_s4 = st.columns(2)
                        with col_s3:
                            st.caption(f"Manual: {ei_minimo_manual if ei_minimo_manual is not None else '—'}")
                        with col_s4:
                            st.caption(f"Manual: {ei_ideal_manual if ei_ideal_manual is not None else '—'}")

                        # Badge de confiabilidade da última revisão
                        _conf_cfg = {
                            "ok":                   ("success", "✅ Cálculo confiável — 3 meses de dados"),
                            "historico_recente":     ("warning", "🕐 Dados recentes — menos de 3 meses de histórico"),
                            "irregular":             ("warning", "⚠️ Consumo irregular — cálculo aplicado com ressalva"),
                            "sem_consumo_recente":   ("info",    "ℹ️ Sem saídas recentes — possível item obsoleto"),
                            "sem_entradas_recentes": ("info",    "ℹ️ Sem entradas no período — intervalo não calculado"),
                            "historico_insuficiente":("error",   "❌ Histórico insuficiente — aguardando movimentações"),
                        }
                        if ei_status_conf and ei_status_conf in _conf_cfg:
                            _fn, _msg = _conf_cfg[ei_status_conf]
                            getattr(st, _fn)(_msg)
                            if ei_ultima_rev_data:
                                st.caption(f"Última revisão: {ei_ultima_rev_data.strftime('%d/%m/%Y')}")
                        elif ei_status_conf is None:
                            st.caption("Nenhuma revisão automática registrada ainda.")

                        col_btn1, col_btn2 = st.columns(2)
                        with col_btn1:
                            if st.button("Definir valor manual", key=f"btn_def_manual_{item_ei_id}", use_container_width=True):
                                st.session_state[f"show_manual_form_{item_ei_id}"] = True

                        if ei_minimo_manual is not None:
                            with col_btn2:
                                if st.button("Remover manual", key=f"btn_rem_manual_{item_ei_id}", use_container_width=True):
                                    st.session_state[f"confirm_rem_manual_{item_ei_id}"] = True

                        if st.session_state.get(f"show_manual_form_{item_ei_id}"):
                            st.markdown("**Definir valores manuais**")
                            col_m1, col_m2 = st.columns(2)
                            with col_m1:
                                novo_min = st.number_input(
                                    "Mínimo manual", min_value=0,
                                    value=ei_minimo_manual or ei_minimo_vigente or 0,
                                    key=f"manual_min_{item_ei_id}",
                                )
                            with col_m2:
                                _ideal_default = max(ei_ideal_manual or ei_ideal_vigente or 0, novo_min)
                                novo_ideal = st.number_input(
                                    "Ideal manual", min_value=novo_min,
                                    value=_ideal_default,
                                    key=f"manual_ideal_{item_ei_id}",
                                )
                            col_fs, col_fc = st.columns(2)
                            with col_fs:
                                if st.button("Salvar manual", type="primary", use_container_width=True, key=f"btn_save_manual_{item_ei_id}"):
                                    if novo_ideal > 0 and novo_min == 0:
                                        st.error("Se informar o Ideal, informe também o Mínimo.")
                                    elif novo_ideal > 0 and novo_ideal < novo_min:
                                        st.error(f"Ideal ({novo_ideal}) não pode ser menor que Mínimo ({novo_min}).")
                                    else:
                                        with SessionLocal() as session:
                                            calculos_service.aplicar_minimo_ideal_manual(
                                                session, item_ei_id, novo_min, novo_ideal
                                            )
                                        st.session_state.pop(f"show_manual_form_{item_ei_id}", None)
                                        st.session_state["_fb"] = ("success", "Valores manuais definidos.")
                                        st.rerun()
                            with col_fc:
                                if st.button("Cancelar", use_container_width=True, key=f"btn_cancel_manual_{item_ei_id}"):
                                    st.session_state.pop(f"show_manual_form_{item_ei_id}", None)
                                    st.rerun()

                        if st.session_state.get(f"confirm_rem_manual_{item_ei_id}"):
                            st.warning("Remover valores manuais e voltar ao cálculo automático?")
                            col_cr1, col_cr2 = st.columns(2)
                            with col_cr1:
                                if st.button("Confirmar", key=f"btn_confirm_rem_manual_{item_ei_id}", type="primary", use_container_width=True):
                                    with SessionLocal() as session:
                                        calculos_service.remover_manual(session, item_ei_id)
                                    st.session_state.pop(f"confirm_rem_manual_{item_ei_id}", None)
                                    st.session_state["_fb"] = ("success", "Manual removido. Usando cálculo automático.")
                                    st.rerun()
                            with col_cr2:
                                if st.button("Cancelar", key=f"btn_cancel_rem_manual_{item_ei_id}", use_container_width=True):
                                    st.session_state.pop(f"confirm_rem_manual_{item_ei_id}", None)
                                    st.rerun()

                    st.divider()
                    if st.button(
                        "Remover item", key=f"btn_del_item_{item_ei_id}", type="secondary"
                    ):
                        st.session_state[f"confirm_del_item_{item_ei_id}"] = True

                    if st.session_state.get(f"confirm_del_item_{item_ei_id}"):
                        st.warning(
                            f"Remover **{item_ei_sel}**? Esta ação excluirá permanentemente o item "
                            "e todo seu histórico: movimentações, preços de cotação e análises vinculadas."
                        )
                        col_yes, col_no = st.columns(2)
                        with col_yes:
                            if st.button(
                                "Confirmar exclusão",
                                key=f"btn_confirm_item_{item_ei_id}",
                                type="primary",
                            ):
                                try:
                                    with st.spinner("Removendo..."):
                                        with SessionLocal() as session:
                                            estoque_service.delete_item(session, item_ei_id)
                                    st.session_state.pop(f"confirm_del_item_{item_ei_id}", None)
                                    st.session_state["_fb"] = ("success", f"Item **{item_ei_sel}** removido.")
                                    st.rerun()
                                except ValueError as e:
                                    st.error(str(e))
                        with col_no:
                            if st.button("Cancelar", key=f"btn_cancel_item_{item_ei_id}"):
                                st.session_state.pop(f"confirm_del_item_{item_ei_id}", None)
                                st.rerun()


    # ══════════════════════════════════════════════════════════════════════════
    # Sub-tab: Fornecedores
    # ══════════════════════════════════════════════════════════════════════════
    elif subtab_sel == "Fornecedores":
        section_title("Fornecedores cadastrados")

        with SessionLocal() as session:
            # Mantém dados tabulares e dados brutos separados para simplificar edição.
            fornecedores = fornecedor_service.get_all_fornecedores(session, apenas_ativos=False)
            df_forn_rows = [
                {
                    "ID": f.id,
                    "Nome": f.nome,
                    "Contato": f.contato_nome or "",
                    "Telefone": f.telefone or "",
                    "E-mail": f.email or "",
                    "Website": f.website or "",
                    "Preferencial": "Sim" if f.preferencial else "Não",
                    "Ativo": "Sim" if f.ativo else "Não",
                }
                for f in fornecedores
            ]
            forn_data = [
                {
                    "id": f.id,
                    "nome": f.nome,
                    "contato_nome": f.contato_nome or "",
                    "telefone": f.telefone or "",
                    "email": f.email or "",
                    "website": f.website or "",
                    "preferencial": f.preferencial,
                    "ativo": f.ativo,
                }
                for f in fornecedores
            ]

        col_fi_forn_busca, col_fi_forn_status = st.columns([3, 2])
        with col_fi_forn_busca:
            fi_forn_busca = st.text_input(
                "Buscar por nome", placeholder="Digite parte do nome...", key="fi_forn_busca"
            )
        with col_fi_forn_status:
            fi_forn_status = st.selectbox("Status", ["Todos", "Ativos", "Inativos"], key="fi_forn_status")

        df_forn_rows_filtered = [
            r for r in df_forn_rows
            if fi_forn_busca.lower() in r["Nome"].lower()
            and (
                fi_forn_status == "Todos"
                or (fi_forn_status == "Ativos" and r["Ativo"] == "Sim")
                or (fi_forn_status == "Inativos" and r["Ativo"] == "Não")
            )
        ]

        if df_forn_rows:
            st.dataframe(pd.DataFrame(df_forn_rows_filtered), width='stretch', hide_index=True)
            st.caption(f"{len(df_forn_rows_filtered)} de {len(df_forn_rows)} fornecedores")
        else:
            st.info("Nenhum fornecedor cadastrado.")

        st.divider()
        col_nf, _sep_forn, col_ef = st.columns([1, 0.04, 1])

        with _sep_forn:
            st.markdown(
                '<div style="width:2px; background:#dee2e6; height:650px; margin:0 auto;"></div>',
                unsafe_allow_html=True,
            )

        # ── Cadastrar novo fornecedor ─────────────────────────────────────────
        with col_nf:
            section_title("Cadastrar novo fornecedor")

            _nf_v = st.session_state.get("_nf_v", 0)
            with st.container(border=True):
                nf_nome = st.text_input("Nome", key=f"nf_nome_{_nf_v}")
                nf_contato = st.text_input("Contato", key=f"nf_contato_{_nf_v}")
                nf_tel = st.text_input("Telefone", placeholder="Ex: 11999998888", help="Digite apenas os números com DDD", key=f"nf_tel_{_nf_v}")
                nf_email = st.text_input("E-mail", key=f"nf_email_{_nf_v}")
                nf_website = st.text_input("Website", placeholder="https://www.site.com.br ou https://lista.mercadolivre.com.br/{query}", help="Use `{query}` no URL para pesquisa automática pelo nome do item", key=f"nf_website_{_nf_v}")
                nf_pref = st.checkbox("Preferencial", key=f"nf_pref_{_nf_v}")
                nf_ativo = st.checkbox("Ativo", value=True, key=f"nf_ativo_{_nf_v}")

                if st.button("Cadastrar", key="btn_nf_cadastrar", type="primary", use_container_width=True):
                    _erros_nf = []
                    _nf_tel_fmt = _formatar_telefone(nf_tel)
                    if not nf_nome.strip():
                        _erros_nf.append("Nome não pode ficar em branco.")
                    if _nf_tel_fmt is None:
                        _erros_nf.append("Telefone inválido. Digite 10 ou 11 dígitos com DDD (ex: 11999998888).")
                    if not _validar_email(nf_email):
                        _erros_nf.append("E-mail inválido.")
                    if _erros_nf:
                        for _e in _erros_nf:
                            st.error(_e)
                    else:
                        try:
                            with st.spinner("Salvando..."):
                                with SessionLocal() as session:
                                    forn_criado = fornecedor_service.create_fornecedor(
                                        session, nf_nome, nf_contato, _nf_tel_fmt, nf_email,
                                        nf_website.strip() or None, nf_pref, nf_ativo,
                                    )
                                    forn_nome_criado = forn_criado.nome
                            st.session_state["_nf_v"] = _nf_v + 1
                            st.session_state["_fb"] = ("success", f"Fornecedor **{forn_nome_criado}** cadastrado.")
                            st.rerun()
                        except ValueError as e:
                            st.error(str(e))

        # ── Editar / Remover fornecedor ───────────────────────────────────────
        with col_ef:
            section_title("Editar / Remover fornecedor")

            if not forn_data:
                st.info("Nenhum fornecedor disponível para editar.")
            else:
                forn_map = {f["nome"]: f for f in forn_data}
                forn_sel_nome = st.selectbox(
                    "Selecionar fornecedor", list(forn_map.keys()), key="forn_ed_sel"
                )
                forn_sel = forn_map[forn_sel_nome]
                forn_sel_id = forn_sel["id"]

                with st.container(border=True):
                    ef_nome = st.text_input(
                        "Nome", value=forn_sel["nome"], key=f"ef_{forn_sel_id}_nome"
                    )
                    ef_contato = st.text_input(
                        "Contato", value=forn_sel["contato_nome"], key=f"ef_{forn_sel_id}_contato"
                    )
                    ef_tel = st.text_input(
                        "Telefone", value=forn_sel["telefone"], placeholder="Ex: 11999998888",
                        help="Digite apenas os números com DDD", key=f"ef_{forn_sel_id}_tel"
                    )
                    ef_email = st.text_input(
                        "E-mail", value=forn_sel["email"], key=f"ef_{forn_sel_id}_email"
                    )
                    ef_website = st.text_input(
                        "Website", value=forn_sel["website"],
                        placeholder="https://www.site.com.br ou https://lista.mercadolivre.com.br/{query}",
                        help="Use `{query}` no URL para pesquisa automática pelo nome do item",
                        key=f"ef_{forn_sel_id}_website",
                    )
                    ef_pref = st.checkbox(
                        "Preferencial", value=forn_sel["preferencial"], key=f"ef_{forn_sel_id}_pref"
                    )
                    ef_ativo = st.checkbox(
                        "Ativo", value=forn_sel["ativo"], key=f"ef_{forn_sel_id}_ativo"
                    )

                    if st.button(
                        "Salvar alterações", key="btn_ef_salvar", type="primary", use_container_width=True
                    ):
                        _erros_ef = []
                        _ef_tel_fmt = _formatar_telefone(ef_tel)
                        if not ef_nome.strip():
                            _erros_ef.append("Nome não pode ficar em branco.")
                        if _ef_tel_fmt is None:
                            _erros_ef.append("Telefone inválido. Digite 10 ou 11 dígitos com DDD (ex: 11999998888).")
                        if not _validar_email(ef_email):
                            _erros_ef.append("E-mail inválido.")
                        if _erros_ef:
                            for _e in _erros_ef:
                                st.error(_e)
                        else:
                            try:
                                with st.spinner("Salvando..."):
                                    with SessionLocal() as session:
                                        fornecedor_service.update_fornecedor(
                                            session, forn_sel_id,
                                            ef_nome, ef_contato, _ef_tel_fmt, ef_email,
                                            ef_website.strip() or None, ef_pref, ef_ativo,
                                        )
                                for k in [k for k in st.session_state if k.startswith(f"ef_{forn_sel_id}_")]:
                                    st.session_state.pop(k)
                                st.session_state["_fb"] = ("success", f"Fornecedor **{ef_nome}** atualizado.")
                                st.rerun()
                            except ValueError as e:
                                st.error(str(e))

                st.divider()
                if st.button(
                    "Remover fornecedor", key=f"btn_del_forn_{forn_sel_id}", type="secondary"
                ):
                    st.session_state[f"confirm_del_forn_{forn_sel_id}"] = True

                if st.session_state.get(f"confirm_del_forn_{forn_sel_id}"):
                    st.warning(
                        f"Remover **{forn_sel_nome}**? Todos os preços de cotação vinculados "
                        "serão excluídos e referências em análises serão removidas."
                    )
                    col_yes, col_no = st.columns(2)
                    with col_yes:
                        if st.button(
                            "Confirmar exclusão",
                            key=f"btn_confirm_forn_{forn_sel_id}",
                            type="primary",
                        ):
                            try:
                                with st.spinner("Removendo..."):
                                    with SessionLocal() as session:
                                        fornecedor_service.delete_fornecedor(session, forn_sel_id)
                                st.session_state.pop(f"confirm_del_forn_{forn_sel_id}", None)
                                st.session_state["_fb"] = ("success", f"Fornecedor **{forn_sel_nome}** removido.")
                                st.rerun()
                            except ValueError as e:
                                st.error(str(e))
                    with col_no:
                        if st.button("Cancelar", key=f"btn_cancel_forn_{forn_sel_id}"):
                            st.session_state.pop(f"confirm_del_forn_{forn_sel_id}", None)
                            st.rerun()

    # ══════════════════════════════════════════════════════════════════════════
    # Sub-tab: Categorias
    # ══════════════════════════════════════════════════════════════════════════
    elif subtab_sel == "Categorias":
        section_title("Categorias cadastradas")

        with SessionLocal() as session:
            # Dados duplicados em formatos diferentes: tabela para leitura e dicts para formulário.
            categorias_all = estoque_service.get_categorias(session)
            df_cat_rows = [
                {"ID": c.id, "Nome": c.nome, "Descrição": c.descricao or ""}
                for c in categorias_all
            ]
            cat_data = [
                {"id": c.id, "nome": c.nome, "descricao": c.descricao or ""}
                for c in categorias_all
            ]

        fi_cat_busca = st.text_input(
            "Buscar por nome", placeholder="Digite parte do nome...", key="fi_cat_busca"
        )

        df_cat_rows_filtered = [
            r for r in df_cat_rows
            if fi_cat_busca.lower() in r["Nome"].lower()
        ]

        if df_cat_rows:
            st.dataframe(pd.DataFrame(df_cat_rows_filtered), width='stretch', hide_index=True)
            st.caption(f"{len(df_cat_rows_filtered)} de {len(df_cat_rows)} categorias")
        else:
            st.info("Nenhuma categoria cadastrada.")

        st.divider()
        col_nc, _sep_cat, col_ec = st.columns([1, 0.04, 1])

        with _sep_cat:
            st.markdown(
                '<div style="width:2px; background:#dee2e6; height:450px; margin:0 auto;"></div>',
                unsafe_allow_html=True,
            )

        # ── Cadastrar nova categoria ──────────────────────────────────────────
        with col_nc:
            section_title("Cadastrar nova categoria")

            _nc_v = st.session_state.get("_nc_v", 0)
            with st.container(border=True):
                nc_nome = st.text_input("Nome da categoria", key=f"nc_nome_{_nc_v}")
                nc_desc = st.text_input("Descrição (opcional)", key=f"nc_desc_{_nc_v}")

                if st.button("Cadastrar", key="btn_nc_cadastrar", type="primary", use_container_width=True):
                    if not nc_nome.strip():
                        st.error("Nome não pode ficar em branco.")
                    else:
                        try:
                            with st.spinner("Salvando..."):
                                with SessionLocal() as session:
                                    cat_criada = estoque_service.create_categoria(
                                        session, nc_nome, nc_desc or None
                                    )
                                    cat_nome_criada = cat_criada.nome
                            st.session_state["_nc_v"] = _nc_v + 1
                            st.session_state["_fb"] = ("success", f"Categoria **{cat_nome_criada}** cadastrada.")
                            st.rerun()
                        except ValueError as e:
                            st.error(str(e))

        # ── Editar / Remover categoria ────────────────────────────────────────
        with col_ec:
            section_title("Editar / Remover categoria")

            if not cat_data:
                st.info("Nenhuma categoria disponível para editar.")
            else:
                cat_map = {c["nome"]: c for c in cat_data}
                cat_ec_sel_nome = st.selectbox(
                    "Selecionar categoria", list(cat_map.keys()), key="cat_ed_sel"
                )
                cat_ec_sel = cat_map[cat_ec_sel_nome]
                cat_ec_id = cat_ec_sel["id"]

                with st.container(border=True):
                    ec_nome = st.text_input(
                        "Nome", value=cat_ec_sel["nome"], key=f"ec_{cat_ec_id}_nome"
                    )
                    ec_desc = st.text_input(
                        "Descrição", value=cat_ec_sel["descricao"], key=f"ec_{cat_ec_id}_desc"
                    )

                    if st.button(
                        "Salvar alterações", key="btn_ec_salvar", type="primary", use_container_width=True
                    ):
                        if not ec_nome.strip():
                            st.error("Nome não pode ficar em branco.")
                        else:
                            try:
                                with st.spinner("Salvando..."):
                                    with SessionLocal() as session:
                                        estoque_service.update_categoria(
                                            session, cat_ec_id, ec_nome, ec_desc or None
                                        )
                                for k in [k for k in st.session_state if k.startswith(f"ec_{cat_ec_id}_")]:
                                    st.session_state.pop(k)
                                st.session_state["_fb"] = ("success", f"Categoria **{ec_nome}** atualizada.")
                                st.rerun()
                            except ValueError as e:
                                st.error(str(e))

                st.divider()
                if st.button(
                    "Remover categoria", key=f"btn_del_cat_{cat_ec_id}", type="secondary"
                ):
                    st.session_state[f"confirm_del_cat_{cat_ec_id}"] = True

                if st.session_state.get(f"confirm_del_cat_{cat_ec_id}"):
                    with SessionLocal() as _s_check:
                        _n_itens_cat = estoque_service.count_itens_categoria(_s_check, cat_ec_id)
                    if _n_itens_cat > 0:
                        st.warning(
                            f"A categoria **{cat_ec_sel_nome}** possui **{_n_itens_cat} item(ns)** vinculado(s). "
                            "Ao confirmar, **todos os itens e seus históricos serão excluídos permanentemente** "
                            "junto com a categoria. Esta ação não pode ser desfeita.",
                            icon="⚠️",
                        )
                    else:
                        st.warning(
                            f"Remover a categoria **{cat_ec_sel_nome}**? Esta ação não pode ser desfeita.",
                            icon="⚠️",
                        )
                    col_yes, col_no = st.columns(2)
                    with col_yes:
                        if st.button(
                            "Confirmar exclusão",
                            key=f"btn_confirm_cat_{cat_ec_id}",
                            type="primary",
                        ):
                            try:
                                with st.spinner("Removendo..."):
                                    with SessionLocal() as session:
                                        estoque_service.delete_categoria(session, cat_ec_id)
                                st.session_state.pop(f"confirm_del_cat_{cat_ec_id}", None)
                                st.session_state["_fb"] = ("success", f"Categoria **{cat_ec_sel_nome}** removida.")
                                st.rerun()
                            except ValueError as e:
                                st.error(str(e))
                    with col_no:
                        if st.button("Cancelar", key=f"btn_cancel_cat_{cat_ec_id}"):
                            st.session_state.pop(f"confirm_del_cat_{cat_ec_id}", None)
                            st.rerun()

    # ══════════════════════════════════════════════════════════════════════════
    # Sub-tab: Setores
    # ══════════════════════════════════════════════════════════════════════════
    elif subtab_sel == "Setores":
        section_title("Setores cadastrados")

        with SessionLocal() as session:
            setores_all = estoque_service.get_setores(session, apenas_ativos=False)
            df_set_rows = [
                {
                    "ID": s.id,
                    "Nome": s.nome,
                    "Descrição": s.descricao or "",
                    "WhatsApp": formatar_telefone(s.whatsapp) if s.whatsapp else "",
                    "Ativo": "Sim" if s.ativo else "Não",
                }
                for s in setores_all
            ]
            setor_data = [
                {
                    "id": s.id, "nome": s.nome, "descricao": s.descricao or "",
                    "whatsapp": s.whatsapp or "", "ativo": s.ativo, "mov_count": len(s.movimentacoes),
                }
                for s in setores_all
            ]

        col_fi_set_busca, col_fi_set_status = st.columns([3, 2])
        with col_fi_set_busca:
            fi_set_busca = st.text_input(
                "Buscar por nome", placeholder="Digite parte do nome...", key="fi_set_busca"
            )
        with col_fi_set_status:
            fi_set_status = st.selectbox("Status", ["Todos", "Ativos", "Inativos"], key="fi_set_status")

        df_set_rows_filtered = [
            r for r in df_set_rows
            if fi_set_busca.lower() in r["Nome"].lower()
            and (
                fi_set_status == "Todos"
                or (fi_set_status == "Ativos" and r["Ativo"] == "Sim")
                or (fi_set_status == "Inativos" and r["Ativo"] == "Não")
            )
        ]

        if df_set_rows:
            st.dataframe(pd.DataFrame(df_set_rows_filtered), width='stretch', hide_index=True)
            st.caption(f"{len(df_set_rows_filtered)} de {len(df_set_rows)} setor(es)")
        else:
            st.info("Nenhum setor cadastrado.")

        st.divider()
        col_ns, _sep_set, col_es = st.columns([1, 0.04, 1])

        with _sep_set:
            st.markdown(
                '<div style="width:2px; background:#dee2e6; height:400px; margin:0 auto;"></div>',
                unsafe_allow_html=True,
            )

        # ── Cadastrar novo setor ──────────────────────────────────────────────
        with col_ns:
            section_title("Cadastrar novo setor")

            _ns_v = st.session_state.get("_ns_v", 0)
            with st.container(border=True):
                ns_nome = st.text_input("Nome do setor", key=f"ns_nome_{_ns_v}")
                ns_desc = st.text_input("Descrição (opcional)", key=f"ns_desc_{_ns_v}")
                ns_wpp = st.text_input(
                    "WhatsApp (opcional)",
                    placeholder="(11) 99999-9999",
                    help="Usado para enviar o formulário de solicitação diretamente ao setor. Informe DDD + número.",
                    key=f"ns_wpp_{_ns_v}",
                )
                _ns_wpp_digitos = "".join(c for c in ns_wpp if c.isdigit())
                if _ns_wpp_digitos:
                    _ns_norm = "55" + _ns_wpp_digitos if len(_ns_wpp_digitos) in (10, 11) else _ns_wpp_digitos
                    if len(_ns_norm) in (12, 13) and _ns_norm.startswith("55"):
                        st.caption(f"✅ Será salvo como: **{formatar_telefone(_ns_norm)}**")
                    else:
                        st.caption(f"⚠️ Número incompleto. Informe DDD + número, ex: (11) 99999-9999.")

                if st.button("Cadastrar", key="btn_ns_cadastrar", type="primary", use_container_width=True):
                    if not ns_nome.strip():
                        st.error("Nome não pode ficar em branco.")
                    else:
                        try:
                            with st.spinner("Salvando..."):
                                with SessionLocal() as session:
                                    setor_criado = estoque_service.criar_setor(
                                        session, ns_nome, ns_desc or None,
                                        whatsapp=ns_wpp.strip() or None,
                                    )
                                    setor_nome_criado = setor_criado.nome
                            st.session_state["_ns_v"] = _ns_v + 1
                            st.session_state["_fb"] = ("success", f"Setor **{setor_nome_criado}** cadastrado.")
                            st.rerun()
                        except ValueError as e:
                            st.error(str(e))

        # ── Editar setor ──────────────────────────────────────────────────────
        with col_es:
            section_title("Editar setor")

            if not setor_data:
                st.info("Nenhum setor disponível para editar.")
            else:
                set_map = {s["nome"]: s for s in setor_data}
                set_sel_nome = st.selectbox(
                    "Selecionar setor", list(set_map.keys()), key="set_ed_sel"
                )
                set_sel = set_map[set_sel_nome]
                set_sel_id = set_sel["id"]

                with st.container(border=True):
                    es_nome = st.text_input(
                        "Nome", value=set_sel["nome"], key=f"es_{set_sel_id}_nome"
                    )
                    es_desc = st.text_input(
                        "Descrição", value=set_sel["descricao"], key=f"es_{set_sel_id}_desc"
                    )
                    _es_wpp_salvo = set_sel["whatsapp"]
                    _es_wpp_display = formatar_telefone(_es_wpp_salvo) if _es_wpp_salvo else ""
                    es_wpp = st.text_input(
                        "WhatsApp (opcional)",
                        value=_es_wpp_display,
                        placeholder="(11) 99999-9999",
                        help="Usado para enviar o formulário de solicitação diretamente ao setor. Informe DDD + número.",
                        key=f"es_{set_sel_id}_wpp",
                    )
                    _es_wpp_digitos = "".join(c for c in es_wpp if c.isdigit())
                    if _es_wpp_digitos:
                        _es_norm = "55" + _es_wpp_digitos if len(_es_wpp_digitos) in (10, 11) else _es_wpp_digitos
                        if len(_es_norm) in (12, 13) and _es_norm.startswith("55"):
                            st.caption(f"✅ Será salvo como: **{formatar_telefone(_es_norm)}**")
                        else:
                            st.caption(f"⚠️ Número incompleto. Informe DDD + número, ex: (11) 99999-9999.")
                    es_ativo = st.checkbox(
                        "Ativo", value=set_sel["ativo"], key=f"es_{set_sel_id}_ativo"
                    )

                    if st.button(
                        "Salvar alterações", key="btn_es_salvar", type="primary", use_container_width=True
                    ):
                        if not es_nome.strip():
                            st.error("Nome não pode ficar em branco.")
                        else:
                            try:
                                with st.spinner("Salvando..."):
                                    with SessionLocal() as session:
                                        estoque_service.atualizar_setor(
                                            session, set_sel_id, es_nome, es_desc or None, es_ativo,
                                            whatsapp=es_wpp.strip() or None,
                                        )
                                for k in [k for k in st.session_state if k.startswith(f"es_{set_sel_id}_")]:
                                    st.session_state.pop(k)
                                st.session_state["_fb"] = ("success", f"Setor **{es_nome}** atualizado.")
                                st.rerun()
                            except ValueError as e:
                                st.error(str(e))

                st.divider()
                set_mov_count = set_sel.get("mov_count", 0)

                if st.button(
                    "Remover setor", key=f"btn_del_set_{set_sel_id}", type="secondary"
                ):
                    st.session_state[f"confirm_del_set_{set_sel_id}"] = (
                        "simple" if set_mov_count == 0 else "warn"
                    )

                _del_state = st.session_state.get(f"confirm_del_set_{set_sel_id}")

                if _del_state == "simple":
                    st.warning(f"Remover **{set_sel_nome}** permanentemente? Esta ação não pode ser desfeita.")
                    col_yes, col_no = st.columns(2)
                    with col_yes:
                        if st.button("Confirmar exclusão", key=f"btn_confirm_set_{set_sel_id}", type="primary"):
                            try:
                                with st.spinner("Removendo..."):
                                    with SessionLocal() as session:
                                        estoque_service.delete_setor(session, set_sel_id)
                                st.session_state.pop(f"confirm_del_set_{set_sel_id}", None)
                                st.session_state["_fb"] = ("success", f"Setor **{set_sel_nome}** removido.")
                                st.rerun()
                            except ValueError as e:
                                st.error(str(e))
                    with col_no:
                        if st.button("Cancelar", key=f"btn_cancel_set_{set_sel_id}"):
                            st.session_state.pop(f"confirm_del_set_{set_sel_id}", None)
                            st.rerun()

                elif _del_state == "warn":
                    st.info(
                        f"**{set_sel_nome}** possui **{set_mov_count} movimentação(ões)** vinculada(s). "
                        "Recomendamos **desativar** o setor para preservar o histórico intacto."
                    )
                    col_desat, col_force = st.columns(2)
                    with col_desat:
                        if st.button(
                            "Desativar setor", key=f"btn_desat_set_{set_sel_id}", use_container_width=True
                        ):
                            try:
                                with st.spinner("Desativando..."):
                                    with SessionLocal() as session:
                                        estoque_service.atualizar_setor(
                                            session, set_sel_id, set_sel_nome,
                                            set_sel.get("descricao") or None, False,
                                            whatsapp=set_sel.get("whatsapp") or None,
                                        )
                                st.session_state.pop(f"confirm_del_set_{set_sel_id}", None)
                                st.session_state["_fb"] = ("success", f"Setor **{set_sel_nome}** desativado.")
                                st.rerun()
                            except ValueError as e:
                                st.error(str(e))
                    with col_force:
                        if st.button(
                            "Remover mesmo assim", key=f"btn_force_set_{set_sel_id}",
                            type="secondary", use_container_width=True
                        ):
                            st.session_state[f"confirm_del_set_{set_sel_id}"] = "force"
                            st.rerun()
                    if st.button("Cancelar", key=f"btn_cancel_set_{set_sel_id}"):
                        st.session_state.pop(f"confirm_del_set_{set_sel_id}", None)
                        st.rerun()

                elif _del_state == "force":
                    st.warning(
                        f"Atenção: **{set_mov_count} movimentação(ões)** perderão a referência a este setor "
                        "(o campo setor ficará em branco). Esta ação não pode ser desfeita."
                    )
                    col_confirm, col_cancel = st.columns(2)
                    with col_confirm:
                        if st.button(
                            "Confirmar remoção", key=f"btn_force_confirm_set_{set_sel_id}", type="primary"
                        ):
                            try:
                                with st.spinner("Removendo..."):
                                    with SessionLocal() as session:
                                        estoque_service.delete_setor(session, set_sel_id, force=True)
                                st.session_state.pop(f"confirm_del_set_{set_sel_id}", None)
                                st.session_state["_fb"] = (
                                    "success",
                                    f"Setor **{set_sel_nome}** removido. "
                                    f"{set_mov_count} movimentação(ões) desvinculada(s).",
                                )
                                st.rerun()
                            except ValueError as e:
                                st.error(str(e))
                    with col_cancel:
                        if st.button("Cancelar", key=f"btn_cancel2_set_{set_sel_id}"):
                            st.session_state.pop(f"confirm_del_set_{set_sel_id}", None)
                            st.rerun()
