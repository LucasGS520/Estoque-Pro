""" Tela de estoque, movimentações e cadastros.

Concentra consulta de itens, registro de entradas/saídas e manutenção de itens,
fornecedores e categorias. As ações de escrita chamam serviços que fazem
`commit` e usam `st.rerun()` para atualizar a interface.
"""

import streamlit as st
import pandas as pd

from core.database import get_session_factory
from core.ui import setup_page, page_header, section_title
from services import estoque_service, fornecedor_service

setup_page("Estoque", "📋")
page_header("Estoque", subtitle="Consulta, movimentações e edição de itens, fornecedores e categorias.")

SessionLocal = get_session_factory()

# Feedback persistente gerado em ação anterior, exibido após rerun
if _fb := st.session_state.pop("_fb", None):
    getattr(st, _fb[0])(_fb[1])

tab_visualizar, tab_movimentacao, tab_editar = st.tabs(
    ["Visualizar", "Registrar Movimentação", "Editar"]
)

# ── Tab 1: Visualizar ─────────────────────────────────────────────────────────
with tab_visualizar:
    # Carrega filtros antes dos itens para reduzir a consulta ao selecionar categoria.
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
        itens = estoque_service.get_all_itens(session, categoria_id=cat_opcoes[cat_sel])

    busca_lower = busca.strip().lower()
    rows = []
    for item in itens:
        if busca_lower and busca_lower not in item.nome.lower():
            continue
        rows.append({
            "ID": item.id,
            "Categoria": item.categoria.nome,
            "Item": item.nome,
            "Und.": item.unidade,
            "Atual": item.estoque_atual,
            "Mínimo": item.estoque_minimo,
            "Ideal": item.estoque_ideal,
            "Obs.": item.observacoes or "",
        })

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)
    st.caption(f"{len(df)} itens exibidos")

# ── Tab 2: Registrar Movimentação ─────────────────────────────────────────────
with tab_movimentacao:
    section_title("Selecionar item")

    with SessionLocal() as session:
        categorias_mov = estoque_service.get_categorias(session)
        cat_opcoes_mov = {c.nome: c.id for c in categorias_mov}

    cat_mov = st.selectbox("Categoria", list(cat_opcoes_mov.keys()), key="mov_cat")

    with SessionLocal() as session:
        itens_mov = estoque_service.get_all_itens(session, categoria_id=cat_opcoes_mov[cat_mov])
        item_opcoes_mov = {f"{i.nome} (atual: {i.estoque_atual})": i.id for i in itens_mov}

    item_mov_sel = st.selectbox("Item", list(item_opcoes_mov.keys()), key="mov_item")
    item_mov_id = item_opcoes_mov[item_mov_sel]

    section_title("Dados da movimentação")
    col1, col2 = st.columns(2)
    with col1:
        tipo_mov = st.selectbox("Tipo", ["entrada", "saida"], key="mov_tipo")
    with col2:
        qtd_mov = st.number_input("Quantidade", min_value=1, value=1, key="mov_qtd")
    motivo_mov = st.text_input("Motivo (opcional)", key="mov_motivo")
    operador_mov = st.text_input("Operador (opcional)", key="mov_operador")

    if st.button("Registrar movimentação", key="btn_mov_registrar", type="primary", use_container_width=True):
        with st.spinner("Registrando..."):
            with SessionLocal() as session:
                item_upd = estoque_service.registrar_movimentacao(
                    session, item_mov_id, tipo_mov, qtd_mov, motivo_mov or None, operador_mov or None
                )
        # Limpa campos controlados para evitar reaplicar a mesma movimentação após o rerun.
        for k in ["mov_tipo", "mov_qtd", "mov_motivo", "mov_operador"]:
            st.session_state.pop(k, None)
        st.session_state["_fb"] = (
            "success",
            f"Movimentação registrada. Novo estoque de **{item_upd.nome}**: {item_upd.estoque_atual}"
        )
        st.rerun()

# ── Tab 3: Editar ─────────────────────────────────────────────────────────────
with tab_editar:
    sub_itens, sub_forn, sub_cat = st.tabs(["Itens", "Fornecedores", "Categorias"])

    # ══════════════════════════════════════════════════════════════════════════
    # Sub-tab: Itens
    # ══════════════════════════════════════════════════════════════════════════
    with sub_itens:
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
                    "Mínimo": i.estoque_minimo,
                    "Ideal": i.estoque_ideal,
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
            st.dataframe(pd.DataFrame(df_itens_rows), use_container_width=True, hide_index=True)
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
                '<div style="width:2px; background:#dee2e6; height:850px; margin:0 auto;"></div>',
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
                ni_nome = st.text_input("Nome do produto", key="ni_nome")
                ni_cat = st.selectbox("Categoria", list(cat_opcoes_ni.keys()), key="ni_cat")
                col_a, col_b = st.columns(2)
                with col_a:
                    ni_und = st.text_input("Unidade", value="un", key="ni_und")
                with col_b:
                    ni_atual = st.number_input("Estoque Atual", min_value=0, value=0, key="ni_atual")
                col_c, col_d = st.columns(2)
                with col_c:
                    ni_minimo = st.number_input("Mínimo", min_value=0, value=0, key="ni_minimo")
                with col_d:
                    ni_ideal = st.number_input("Ideal", min_value=0, value=0, key="ni_ideal")
                ni_obs = st.text_area("Observações", height=68, key="ni_obs")
                ni_ativo = st.checkbox("Ativo", value=True, key="ni_ativo")

                if st.button("Cadastrar", key="btn_ni_cadastrar", type="primary", use_container_width=True):
                    if not ni_nome.strip():
                        st.error("Nome não pode ficar em branco.")
                    elif ni_ideal < ni_minimo:
                        st.error("Ideal não pode ser menor que Mínimo.")
                    else:
                        try:
                            with st.spinner("Salvando..."):
                                with SessionLocal() as session:
                                    item_criado = estoque_service.create_item(
                                        session, cat_opcoes_ni[ni_cat], ni_nome, ni_und,
                                        ni_atual, ni_minimo, ni_ideal, ni_obs or None, ni_ativo,
                                    )
                            for k in ["ni_nome", "ni_cat", "ni_und", "ni_atual", "ni_minimo",
                                      "ni_ideal", "ni_obs", "ni_ativo"]:
                                st.session_state.pop(k, None)
                            st.session_state["_fb"] = ("success", f"Item **{item_criado.nome}** cadastrado.")
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
                        ei_minimo = _i.estoque_minimo
                        ei_ideal = _i.estoque_ideal
                        ei_obs = _i.observacoes or ""
                        ei_ativo = _i.ativo

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
                        ei_novo_minimo = st.number_input(
                            "Mínimo", min_value=0, value=ei_minimo, key=f"ei_{item_ei_id}_minimo"
                        )
                    col_c, col_d = st.columns(2)
                    with col_c:
                        ei_novo_ideal = st.number_input(
                            "Ideal", min_value=0, value=ei_ideal, key=f"ei_{item_ei_id}_ideal"
                        )
                    with col_d:
                        ei_novo_ativo = st.checkbox(
                            "Ativo", value=ei_ativo, key=f"ei_{item_ei_id}_ativo"
                        )
                    ei_nova_obs = st.text_area(
                        "Observações", value=ei_obs, height=68, key=f"ei_{item_ei_id}_obs"
                    )

                    if st.button(
                        "Salvar alterações", key="btn_ei_salvar", type="primary", use_container_width=True
                    ):
                        if not ei_novo_nome.strip():
                            st.error("Nome não pode ficar em branco.")
                        elif ei_novo_ideal < ei_novo_minimo:
                            st.error("Ideal não pode ser menor que Mínimo.")
                        else:
                            try:
                                with st.spinner("Salvando..."):
                                    with SessionLocal() as session:
                                        estoque_service.update_item_completo(
                                            session, item_ei_id,
                                            cat_opcoes_ei[ei_nova_cat],
                                            ei_novo_nome, ei_nova_und,
                                            ei_novo_minimo, ei_novo_ideal,
                                            ei_nova_obs or None, ei_novo_ativo,
                                        )
                                for k in [k for k in st.session_state if k.startswith(f"ei_{item_ei_id}_")]:
                                    st.session_state.pop(k)
                                st.session_state["_fb"] = ("success", f"Item **{ei_novo_nome}** atualizado.")
                                st.rerun()
                            except ValueError as e:
                                st.error(str(e))

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
    with sub_forn:
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
                    "preferencial": f.preferencial,
                    "ativo": f.ativo,
                }
                for f in fornecedores
            ]

        if df_forn_rows:
            st.dataframe(pd.DataFrame(df_forn_rows), use_container_width=True, hide_index=True)
            st.caption(f"{len(df_forn_rows)} fornecedores no total")
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

            nf_nome = st.text_input("Nome", key="nf_nome")
            nf_contato = st.text_input("Contato", key="nf_contato")
            nf_tel = st.text_input("Telefone", key="nf_tel")
            nf_email = st.text_input("E-mail", key="nf_email")
            nf_pref = st.checkbox("Preferencial", key="nf_pref")
            nf_ativo = st.checkbox("Ativo", value=True, key="nf_ativo")

            if st.button("Cadastrar", key="btn_nf_cadastrar", type="primary", use_container_width=True):
                if not nf_nome.strip():
                    st.error("Nome não pode ficar em branco.")
                else:
                    try:
                        with st.spinner("Salvando..."):
                            with SessionLocal() as session:
                                forn_criado = fornecedor_service.create_fornecedor(
                                    session, nf_nome, nf_contato, nf_tel, nf_email, nf_pref, nf_ativo
                                )
                        for k in ["nf_nome", "nf_contato", "nf_tel", "nf_email", "nf_pref", "nf_ativo"]:
                            st.session_state.pop(k, None)
                        st.session_state["_fb"] = ("success", f"Fornecedor **{forn_criado.nome}** cadastrado.")
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

                ef_nome = st.text_input(
                    "Nome", value=forn_sel["nome"], key=f"ef_{forn_sel_id}_nome"
                )
                ef_contato = st.text_input(
                    "Contato", value=forn_sel["contato_nome"], key=f"ef_{forn_sel_id}_contato"
                )
                ef_tel = st.text_input(
                    "Telefone", value=forn_sel["telefone"], key=f"ef_{forn_sel_id}_tel"
                )
                ef_email = st.text_input(
                    "E-mail", value=forn_sel["email"], key=f"ef_{forn_sel_id}_email"
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
                    if not ef_nome.strip():
                        st.error("Nome não pode ficar em branco.")
                    else:
                        try:
                            with st.spinner("Salvando..."):
                                with SessionLocal() as session:
                                    fornecedor_service.update_fornecedor(
                                        session, forn_sel_id,
                                        ef_nome, ef_contato, ef_tel, ef_email, ef_pref, ef_ativo,
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
    with sub_cat:
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

        if df_cat_rows:
            st.dataframe(pd.DataFrame(df_cat_rows), use_container_width=True, hide_index=True)
            st.caption(f"{len(df_cat_rows)} categorias no total")
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

            nc_nome = st.text_input("Nome da categoria", key="nc_nome")
            nc_desc = st.text_input("Descrição (opcional)", key="nc_desc")

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
                        for k in ["nc_nome", "nc_desc"]:
                            st.session_state.pop(k, None)
                        st.session_state["_fb"] = ("success", f"Categoria **{cat_criada.nome}** cadastrada.")
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
                    st.warning(
                        f"Remover **{cat_ec_sel_nome}**? "
                        "A remoção só é permitida se não houver itens nessa categoria."
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
