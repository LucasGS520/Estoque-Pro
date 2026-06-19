"""Aba Registrar Movimentação — página Estoque."""
import streamlit as st

from data.database import get_session_factory
from core.ui import section_title
from services import estoque_service


def render() -> None:
    """Renderiza a aba Registrar Movimentação."""
    SessionLocal = get_session_factory()
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
